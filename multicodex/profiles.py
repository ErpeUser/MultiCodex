"""Profile catalogue. Adoption links to existing profiles; it NEVER moves credentials."""
from __future__ import annotations

import json
import os
import re
import tempfile
from dataclasses import dataclass
from pathlib import Path


class ProfileError(ValueError):
    pass


MAX_PROFILE_BYTES = 1024 * 1024
MAX_PROFILE_SESSIONS = 1000


@dataclass(frozen=True)
class Profile:
    name: str
    home: Path
    linked: bool = False
    auth_home: Path | None = None
    session_id: str = 'default'
    account_email: str | None = None
    account_id: str | None = None

    @property
    def codex_home(self) -> Path:
        return self.auth_home if self.auth_home is not None else self.home / '.codex'


_RESERVED = {'CON', 'PRN', 'AUX', 'NUL', 'CONIN$', 'CONOUT$'}
_RESERVED |= {f'{prefix}{n}' for prefix in ('COM', 'LPT') for n in '123456789\u00b9\u00b2\u00b3'}
_NAME = re.compile(r'^[\w .()-]{1,60}$', re.UNICODE)


def validate_name(name: str) -> str:
    if not isinstance(name, str) or not _NAME.fullmatch(name) or name.strip() != name:
        raise ProfileError('Invalid Windows profile name')
    if name.startswith('.') or name.endswith(('.', ' ')) or name in ('.', '..') or name.split('.')[0].rstrip().upper() in _RESERVED:
        raise ProfileError('Reserved or unsafe Windows profile name')
    return name


def _atomic_json(path: Path, obj: dict) -> None:
    _atomic_bytes(path, json.dumps(obj, indent=2).encode('utf-8'))


def _atomic_bytes(path: Path, data: bytes) -> None:
    fd, tmp = tempfile.mkstemp(prefix='.profile-', suffix='.tmp', dir=path.parent)
    try:
        with os.fdopen(fd, 'wb') as fh:
            fh.write(data)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


def is_redirect(path: Path) -> bool:
    """Reject symlinks and Windows junctions/reparse points, including dangling links."""
    import stat
    try:
        info = path.lstat()
    except FileNotFoundError:
        return False
    return stat.S_ISLNK(info.st_mode) or bool(getattr(info, 'st_file_attributes', 0) & 0x400)


def check_profile_children(home: Path) -> None:
    for child in ('.codex', 'electron', 'profile.json', '.sessions'):
        if is_redirect(home / child):
            raise ProfileError('Redirected profile data is not safe to manage')


class ProfileStore:
    def __init__(self, root: Path):
        raw = Path(root).expanduser()
        if is_redirect(raw):
            raise ProfileError('Redirected catalogue root is forbidden')
        self.root = raw.resolve()
        self.issues: list[dict[str, str]] = []
        self.root.mkdir(parents=True, exist_ok=True, mode=0o700)

    def _entry(self, name: str) -> Path:
        validate_name(name)
        path = self.root / name
        if is_redirect(path):
            raise ProfileError('Symlinked profile entries are forbidden')
        if path.resolve().parent != self.root:
            raise ProfileError('Profile traversal is forbidden')
        return path

    def _catalogue_lock(self):
        from .locks import FileLock
        return FileLock(self.root / '.locks' / 'catalogue.lock')

    def create(self, name: str) -> Profile:
        with self._catalogue_lock():
            return self._create(name)

    def _create(self, name: str) -> Profile:
        path = self._entry(name)
        if any(p.name.casefold() == name.casefold() for p in self.root.iterdir()):
            raise ProfileError('Profile already exists; never overwrite data')
        path.mkdir(mode=0o700)
        try:
            (path / '.codex').mkdir(mode=0o700)
            (path / '.codex' / 'config.toml').write_text('cli_auth_credentials_store = "keyring"\n', encoding='utf-8')
            (path / 'electron').mkdir(mode=0o700)
            _atomic_json(path / 'profile.json', {'version': 1, 'name': name, 'mode': 'managed'})
        except Exception:
            # Do not clean up potentially valuable files after a partial write.
            raise
        return Profile(name, path)

    def adopt(self, name: str, legacy: Path) -> Profile:
        with self._catalogue_lock():
            return self._adopt(name, legacy)

    def _adopt(self, name: str, legacy: Path) -> Profile:
        """Register an explicit read/launch link. Never read/copy/move auth files."""
        entry = self._entry(name)
        external = Path(legacy).expanduser()
        if not external.is_dir() or is_redirect(external):
            raise ProfileError('Existing profile directory must be a real directory')
        external = external.resolve()
        if external == entry or self.root == external or self.root in external.parents or external in self.root.parents:
            raise ProfileError('Link targets must be external existing profiles')
        if entry.exists():
            existing = self.get(name)
            if existing.linked and existing.home == external:
                return existing
            raise ProfileError('Different profile already exists; never replace it')
        check_profile_children(external)
        if any(p.home == external for p in self.list()):
            raise ProfileError('This directory is already linked to another profile')
        if any(p.name.casefold() == name.casefold() for p in self.root.iterdir()):
            raise ProfileError('A case-insensitive profile name already exists')
        entry.mkdir(mode=0o700)
        _atomic_json(entry / 'profile.json', {'version': 1, 'name': name, 'mode': 'linked', 'path': str(external)})
        return Profile(name, external, True)

    def get(self, name: str) -> Profile:
        entry = self._entry(name)
        try:
            check_profile_children(entry)
            meta = entry / 'profile.json'
            if meta.stat().st_size > MAX_PROFILE_BYTES:
                raise ProfileError('Profile metadata exceeds size limit')
            data = json.loads(meta.read_text(encoding='utf-8'))
        except (OSError, ValueError) as exc:
            raise ProfileError('Profile metadata missing or corrupt') from exc
        if not isinstance(data, dict):
            raise ProfileError('Profile metadata must be an object')
        if type(data.get('version')) is not int or data['version'] != 1 or data.get('name') != name:
            raise ProfileError('Profile metadata identity mismatch')
        allowed = {'version', 'name', 'mode', 'active_session', 'sessions'} if data.get('mode') == 'managed' else {'version', 'name', 'mode', 'path'}
        if set(data) - allowed:
            raise ProfileError('Unknown metadata fields; preserve original without copying')
        if data.get('mode') == 'managed':
            sid = data.get('active_session', 'default')
            sessions = data.get('sessions', {})
            if not isinstance(sessions, dict) or len(sessions) > MAX_PROFILE_SESSIONS:
                raise ProfileError('Invalid session catalogue')
            if sid != 'default' and (not isinstance(sid, str) or not re.fullmatch('[0-9a-f]{32}', sid) or sid not in sessions):
                raise ProfileError('Invalid active session')
            fields = {'email', 'plan', 'account_id', 'verified_at', 'label'}
            for key, row in sessions.items():
                if not isinstance(key, str) or (key != 'default' and not re.fullmatch('[0-9a-f]{32}', key)):
                    raise ProfileError('Invalid saved session identifier')
                if not isinstance(row, dict) or set(row) - fields:
                    raise ProfileError('Invalid account metadata')
                email = row.get('email')
                if not isinstance(email, str) or '@' not in email or len(email) > 320 or re.search(r'[\x00-\x20\x7f]', email):
                    raise ProfileError('Invalid saved account identity')
                for field, length in (('label', 320), ('plan', 64), ('account_id', 256)):
                    value = row.get(field)
                    if value is not None and (not isinstance(value, str) or len(value) > length or re.search(r'[\x00-\x1f\x7f]', value)):
                        raise ProfileError('Invalid saved account field')
                verified = row.get('verified_at')
                if type(verified) is not int or verified < 0:
                    raise ProfileError('Invalid account observation timestamp')
            identity = sessions.get(sid, {})
            if not isinstance(identity, dict):
                raise ProfileError('Invalid account metadata')
            auth_home = entry / '.codex' if sid == 'default' else entry / '.sessions' / sid
            if is_redirect(auth_home) or not auth_home.is_dir():
                raise ProfileError('Authentication home is unavailable or redirected')
            return Profile(name, entry, False, auth_home, sid, identity.get('email'), identity.get('account_id'))
        if data.get('mode') == 'linked':
            raw = data.get('path')
            if not isinstance(raw, str) or not raw:
                raise ProfileError('Linked profile path missing')
            external = Path(raw)
            if not external.is_absolute() or not external.is_dir() or is_redirect(external):
                raise ProfileError('Linked profile is no longer available')
            external = external.resolve()
            if external == self.root or self.root in external.parents or external in self.root.parents:
                raise ProfileError('Linked profile must remain outside the catalogue')
            check_profile_children(external)
            return Profile(name, external.resolve(), True)
        raise ProfileError('Unknown profile type')

    def list(self) -> list[Profile]:
        out = []
        self.issues = []
        for path in sorted(self.root.iterdir(), key=lambda p: p.name.casefold()):
            if path.name.startswith('.'):
                continue
            if path.is_dir() and not is_redirect(path):
                try:
                    out.append(self.get(path.name))
                except ProfileError:
                    self.issues.append({'name': path.name, 'error': 'Invalid profile metadata'})
        return out
