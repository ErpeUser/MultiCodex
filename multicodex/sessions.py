"""Profile-owned auth homes and metadata-only recovery journals.

Credentials are persisted only by the official client with keyring mode.
No account token is copied, decrypted, serialized or logged here.
"""
from __future__ import annotations
import hashlib
import json
import time
import tomllib
import uuid
from .codex_client import AccountIdentity
from .locks import FileLock
from .profiles import (MAX_PROFILE_BYTES, MAX_PROFILE_SESSIONS, ProfileStore, ProfileError,
                       _atomic_bytes, _atomic_json, _checked_bytes, _file_revision, is_redirect)


class MissingIdentityError(ProfileError):
    """The profile is valid but has no verified identity for this session."""


def valid_session_id(value):
    return value == 'default' or (isinstance(value, str) and len(value) == 32
                                 and all(c in '0123456789abcdef' for c in value))

class SessionStore:
    def __init__(self, profiles: ProfileStore):
        self.profiles = profiles

    def lock(self, name):
        self.profiles._entry(name)
        key = hashlib.sha256(name.casefold().encode('utf-8')).hexdigest()
        return FileLock(self.profiles.root / '.locks' / (key + '.lock'))

    def _entry(self, name):
        return self._snapshot(name)[0].home

    def _snapshot(self, name):
        snapshot = self.profiles.snapshot(name)
        profile = snapshot[0]
        if profile.linked:
            raise ProfileError('Linked source profiles cannot be rebound; create a managed profile')
        return snapshot

    def _data(self, name):
        return self._snapshot(name)[1]

    def _save(self, name, data, expected_revision):
        if len(data.get('sessions', {})) > MAX_PROFILE_SESSIONS:
            raise ProfileError('Session catalogue exceeds size limit')
        payload = json.dumps(data, indent=2).encode('utf-8')
        if len(payload) > MAX_PROFILE_BYTES:
            raise ProfileError('Profile metadata exceeds size limit')
        profile, previous, revision = self._snapshot(name)
        if revision != expected_revision:
            raise ProfileError('Profile changed during operation; newer metadata preserved')
        entry = profile.home
        self.profiles._profile_from_data(name, entry, data)
        _atomic_json(entry/'profile.json.previous', previous)
        if self._snapshot(name)[2] != expected_revision:
            raise ProfileError('Profile changed during operation; newer metadata preserved')
        _atomic_bytes(entry/'profile.json', payload)

    def home(self, name, session_id):
        if not valid_session_id(session_id):
            raise ProfileError('Invalid session identity')
        profile, _data, revision = self._snapshot(name)
        entry = profile.home
        home = entry/'.codex' if session_id == 'default' else entry/'.sessions'/session_id
        if is_redirect(home) or is_redirect(home.parent) or not home.is_dir():
            raise ProfileError('Authentication home is unavailable or redirected')
        config = home/'config.toml'
        try:
            payload, _revision = _checked_bytes(config, 65536)
            mode = tomllib.loads(payload.decode('utf-8')).get('cli_auth_credentials_store')
        except (ValueError, OSError) as exc:
            raise ProfileError('Authentication configuration is unreadable') from exc
        if mode != 'keyring' or (home/'auth.json').exists() or is_redirect(home/'auth.json'):
            raise ProfileError('Managed sign-ins require keyring storage, without file fallback')
        if self._snapshot(name)[2] != revision:
            raise ProfileError('Profile changed during authentication home validation')
        return home

    def home_fingerprint(self, name, session_id):
        """Return a validated home and immutable metadata for the next I/O step."""
        home = self.home(name, session_id)
        config = home / 'config.toml'
        try:
            home_stat = home.stat()
            config_stat = config.stat()
            auth = home / 'auth.json'
            return home, (home_stat.st_dev, home_stat.st_ino, config_stat.st_size,
                          config_stat.st_mtime_ns, auth.exists())
        except OSError as exc:
            raise ProfileError('Authentication home is unavailable') from exc

    def revalidate_home(self, name, session_id, fingerprint):
        """Recheck redirect, keyring-only policy and metadata before provider I/O."""
        home, current = self.home_fingerprint(name, session_id)
        if current != fingerprint:
            raise ProfileError('Authentication home changed during operation')
        return home

    def prepare(self, name):
        with self.lock(name):
            entry = self._entry(name)
            parent = entry/'.sessions'
            if is_redirect(parent):
                raise ProfileError('Unsafe session directory')
            parent.mkdir(exist_ok=True, mode=0o700)
            sid = uuid.uuid4().hex
            home = parent/sid
            home.mkdir(mode=0o700)
            (home/'config.toml').write_text('cli_auth_credentials_store = "keyring"\n', encoding='utf-8')
            return sid, home

    def register(self, name, session_id, identity: AccountIdentity):
        with self.lock(name):
            self.home(name, session_id)
            if not isinstance(identity, AccountIdentity):
                raise ProfileError('Only verified account metadata can be registered')
            _profile, data, revision = self._snapshot(name)
            previous = data.get('sessions', {}).get(session_id)
            label = identity.email
            if previous and (previous.get('label') or '').strip():
                saved = AccountIdentity(previous['email'], previous.get('plan'), previous.get('account_id'))
                if saved.same_account(identity):
                    label = previous['label']
            data.setdefault('sessions', {})[session_id] = {**identity.public(), 'verified_at': int(time.time()),
                                                          'label': label}
            self._save(name, data, revision)

    def identity(self, name, session_id):
        data = self._data(name)
        row = data.get('sessions', {}).get(session_id)
        if not isinstance(row, dict) or not isinstance(row.get('email'), str):
            raise MissingIdentityError('Session has no verified account metadata')
        return AccountIdentity(row['email'], row.get('plan'), row.get('account_id'))

    def list(self, name):
        data = self._data(name)
        return [{'id': key, **value} for key, value in data.get('sessions', {}).items()]

    def rename(self, name, session_id, label):
        if not isinstance(label, str) or not label.strip() or len(label) > 80 or any(ord(c) < 32 for c in label):
            raise ProfileError('Account label must contain 1 to 80 printable characters')
        with self.lock(name):
            _profile, data, revision = self._snapshot(name)
            if session_id not in data.get('sessions', {}):
                raise ProfileError('Unknown session')
            data['sessions'][session_id]['label'] = label.strip()
            self._save(name, data, revision)

    def activate(self, name, session_id):
        with self.lock(name):
            self.home(name, session_id)
            _profile, data, revision = self._snapshot(name)
            if session_id != 'default' and session_id not in data.get('sessions', {}):
                raise ProfileError('Unknown session')
            data['active_session'] = session_id
            self._save(name, data, revision)

    def journal(self, name):
        profile, _data, profile_revision = self._snapshot(name)
        path = profile.home/'.operation.json'
        if is_redirect(path):
            raise ProfileError('Unsafe operation journal')
        if not path.exists():
            if self._snapshot(name)[2] != profile_revision:
                raise ProfileError('Profile changed during journal validation')
            return None
        try:
            payload, revision = _checked_bytes(path, 65536)
            data = json.loads(payload.decode('utf-8'))
            if (not isinstance(data, dict) or set(data) != {'version', 'old', 'new', 'was_running', 'phase'}
                or type(data.get('version')) is not int or data.get('version') != 1
                or not valid_session_id(data.get('old')) or not valid_session_id(data.get('new'))
                or type(data.get('was_running')) is not bool
                or not isinstance(data.get('phase'), str)
                or data.get('phase') not in {'prepared','stopped','bound','started'}):
                raise ValueError('schema')
            if _file_revision(path) != revision:
                raise ValueError('changed')
            if self._snapshot(name)[2] != profile_revision:
                raise ValueError('profile changed')
            return data
        except (ValueError, OSError) as exc:
            raise ProfileError('Operation journal is unreadable; automatic recovery is blocked') from exc

    def write_journal(self, name, data):
        entry = self._entry(name)
        if is_redirect(entry/'.operation.json'):
            raise ProfileError('Unsafe operation journal')
        _atomic_json(entry/'.operation.json', data)

    def clear_journal(self, name):
        path = self._entry(name)/'.operation.json'
        if is_redirect(path):
            raise ProfileError('Unsafe operation journal')
        path.unlink(missing_ok=True)
