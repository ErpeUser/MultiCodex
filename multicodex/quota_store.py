"""Credential-free quota history. Access/session changes never delete observations.

Each operation owns a short SQLite transaction. Unknown workspace identities remain
session-scoped; verified account/workspace pairs can retain history across re-login.
No provider response, authentication home, cookie or token is persisted here.
"""
from __future__ import annotations

from contextlib import contextmanager, closing
import hashlib
import json
import math
import os
from pathlib import Path

from .locks import BusyError, FileLock
import re
import shutil
import sqlite3
import stat
import tempfile
import time
import uuid


class QuotaError(ValueError):
    """Fixed error codes only: provider/file contents must not reach the GUI."""
    def __init__(self, code='INVALID_DATA'):
        self.code = code if code in {'INVALID_DATA', 'STORAGE', 'SCHEMA', 'NO_SNAPSHOT',
                                    'ACCOUNT_MISMATCH', 'UNKNOWN_ACCOUNT', 'CONTEXT_CHANGED'} else 'INVALID_DATA'
        super().__init__('Quota operation failed: ' + self.code)


ERROR_CODES = frozenset({'TIMEOUT', 'UNAVAILABLE', 'AUTH_FAILED', 'NOT_AUTHENTICATED',
    'ACCOUNT_MISMATCH', 'PROTOCOL', 'CANCELLED', 'ACCESS_DENIED', 'STORAGE', 'UNKNOWN', 'BUSY'})
ACCESS_STATES = frozenset({'WORKSPACE_MEMBER', 'WORKSPACE_ACCESS_UNKNOWN', 'ACCESS_REMOVED',
    'WORKSPACE_ACCESS_REMOVED', 'INVITATION_PENDING', 'INVITATION_ACCEPTED', 'SEAT_UNAVAILABLE'})
AUTH_STATES = frozenset({'REGISTERED', 'AUTHENTICATED', 'SESSION_EXPIRED', 'DISABLED', 'ERROR'})
CAPTURE_REASONS = frozenset({'poll', 'manual_refresh', 'before_removal', 'access_restored', 'relogin'})
LIMIT_TYPES = frozenset({'workspaceMemberUsageLimitReached', 'workspaceCreditLimitReached',
    'userRateLimitReached', 'rateLimitReached', 'workspaceUsageLimitReached'})
RESET_TYPES = frozenset({'codexRateLimits', 'unknown'})
CREDIT_STATUSES = frozenset({'available', 'redeeming', 'redeemed', 'unknown'})
SNAPSHOT_FRESHNESS = frozenset({'LIVE_VERIFIED', 'CACHED', 'UNKNOWN'})
VERIFICATION_STATES = frozenset({'VERIFIED', 'UNVERIFIED', 'REQUIRES_RECHECK'})
MAX_TIMESTAMP = 253402300799


def _text(value, maximum=256, *, optional=False):
    if value is None and optional:
        return None
    if not isinstance(value, str) or not value or len(value) > maximum or re.search(r'[\x00-\x1f\x7f]', value):
        raise QuotaError()
    return value


def _stamp(value):
    if type(value) is not int or not 0 <= value <= MAX_TIMESTAMP:
        raise QuotaError()
    return value


def _number(value):
    if value is None:
        return None
    if type(value) not in (int, float) or not math.isfinite(value) or not 0 <= value <= 1000:
        raise QuotaError()
    return value


def _optional_bool(value):
    if value is not None and type(value) is not bool:
        raise QuotaError()
    return value


def _reset_credits(value):
    if value is None:
        return None
    if not isinstance(value, dict) or set(value) - {'available_count', 'credits'} or 'available_count' not in value:
        raise QuotaError()
    count = value['available_count']
    if type(count) is not int or count < 0 or count > 1000000:
        raise QuotaError()
    credits = value.get('credits')
    if credits is not None and (not isinstance(credits, list) or len(credits) > 10000):
        raise QuotaError()
    if credits is not None:
        for credit in credits:
            if (not isinstance(credit, dict) or set(credit) - {
                    'id', 'reset_type', 'status', 'granted_at', 'expires_at', 'title', 'description'} or
                    not {'id', 'reset_type', 'status', 'granted_at'}.issubset(credit)):
                raise QuotaError()
            _text(credit['id'], 160)
            if credit['reset_type'] not in RESET_TYPES or credit['status'] not in CREDIT_STATUSES:
                raise QuotaError()
            _stamp(credit['granted_at'])
            if credit.get('expires_at') is not None:
                _stamp(credit['expires_at'])
            for field in ('title', 'description'):
                _text(credit.get(field), 1000, optional=True)
    return value


def _safe_path(path):
    for candidate in (path, *path.parents):
        try:
            info = candidate.lstat()
        except FileNotFoundError:
            continue
        if stat.S_ISLNK(info.st_mode) or bool(getattr(info, 'st_file_attributes', 0) & 0x400):
            raise QuotaError('STORAGE')


def normalized_usage(data: dict) -> dict:
    """Allowlist a sanitized app-server result; absent and unknown stay distinct."""
    if not isinstance(data, dict) or data.get('source') != 'official-app-server':
        raise QuotaError()
    rows = data.get('windows')
    if not isinstance(rows, list) or len(rows) > 2:
        raise QuotaError()
    reported = data.get('reported', {})
    if not isinstance(reported, dict):
        raise QuotaError()
    out = {}
    seen = set()
    for label in ('primary', 'secondary'):
        out.update({label + '_present': _optional_bool(reported.get(label)),
                    label + '_used_percent': None, label + '_duration_minutes': None,
                    label + '_reset_at': None})
    for row in rows:
        if not isinstance(row, dict):
            raise QuotaError()
        label = row.get('label')
        if label not in ('primary', 'secondary') or label in seen or reported.get(label) is False:
            raise QuotaError()
        seen.add(label)
        minutes = row.get('minutes')
        if minutes is not None and (type(minutes) is not int or not 0 < minutes <= 52560000):
            raise QuotaError()
        reset = row.get('reset_at')
        out.update({label + '_present': True,
                    label + '_used_percent': _number(row.get('used_percent')),
                    label + '_duration_minutes': minutes,
                    label + '_reset_at': None if reset is None else _stamp(reset)})
    out['additional_limits_reported'] = _optional_bool(data.get('additional_limits_reported'))
    out['ordinary_usage_allowed'] = _optional_bool(data.get('ordinary_usage_allowed'))
    out['spend_control_reached'] = _optional_bool(data.get('spend_control_reached'))
    reached = data.get('rate_limit_reached_type')
    # Do not echo an arbitrary string from the provider into storage/diagnostics.
    out['rate_limit_reached_type'] = (None if reached is None else
        reached if isinstance(reached, str) and reached in LIMIT_TYPES else 'UNKNOWN_PROVIDER_LIMIT')
    out['reset_credits'] = _reset_credits(data.get('reset_credits'))
    return out


class QuotaStore:
    """Append-only observations plus independent account/access metadata."""
    def __init__(self, root: str | Path):
        self.root = Path(root).absolute()
        self.path = self.root / 'quota.sqlite3'
        self.lock_path = self.root / '.locks' / 'quota-store.lock'
        try:
            _safe_path(self.root)
            self.root.mkdir(parents=True, exist_ok=True, mode=0o700)
            self._check_paths()
            try:
                fd = os.open(self.path, os.O_CREAT | os.O_EXCL | os.O_WRONLY |
                             getattr(os, 'O_NOFOLLOW', 0), 0o600)
            except FileExistsError:
                pass
            else:
                os.close(fd)
            with self._db(write=True) as db:
                version = db.execute('PRAGMA user_version').fetchone()[0]
                if version not in (0, 1, 2):
                    raise QuotaError('SCHEMA')
                if version == 0:
                    if db.execute("SELECT 1 FROM sqlite_master WHERE type='table'").fetchone():
                        raise QuotaError('SCHEMA')
                    db.execute('CREATE TABLE accounts (account_key TEXT PRIMARY KEY, record TEXT NOT NULL)')
                    db.execute('CREATE TABLE snapshots (snapshot_id TEXT PRIMARY KEY, account_key TEXT NOT NULL REFERENCES accounts(account_key), observed_at INTEGER NOT NULL, captured_at INTEGER NOT NULL, payload TEXT NOT NULL)')
                    db.execute('CREATE INDEX snapshot_account_time ON snapshots(account_key, observed_at DESC, captured_at DESC)')
                    db.execute('CREATE TABLE events (event_id INTEGER PRIMARY KEY, account_key TEXT NOT NULL REFERENCES accounts(account_key), occurred_at INTEGER NOT NULL, kind TEXT NOT NULL, code TEXT NOT NULL)')
                    db.execute('PRAGMA user_version = 2')
                elif version == 1:
                    required = {'accounts', 'snapshots', 'events'}
                    found = {r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
                    if not required.issubset(found):
                        raise QuotaError('SCHEMA')
                    # Version 2 adds only JSON fields with backward-compatible
                    # defaults; advancing the marker is the complete migration.
                    db.execute('PRAGMA user_version = 2')
                else:
                    required = {'accounts', 'snapshots', 'events'}
                    found = {r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
                    if not required.issubset(found):
                        raise QuotaError('SCHEMA')
        except QuotaError:
            raise
        except (OSError, sqlite3.Error) as exc:
            raise QuotaError('STORAGE') from exc

    def _check_paths(self):
        for suffix in ('', '-journal', '-wal', '-shm'):
            _safe_path(Path(str(self.path) + suffix))
        if self.path.exists() and not self.path.is_file():
            raise QuotaError('STORAGE')

    @contextmanager
    def _storage_guard(self):
        """Serialize SQLite replacement and backups across processes."""
        lock = FileLock(self.lock_path)
        deadline = time.monotonic() + 5.0
        delay = 0.01
        while True:
            try:
                lock.__enter__()
                break
            except BusyError as exc:
                if time.monotonic() >= deadline:
                    raise QuotaError('STORAGE') from exc
                time.sleep(delay)
                delay = min(delay * 2, 0.1)
        try:
            yield
        finally:
            lock.__exit__(None, None, None)

    @contextmanager
    def _db(self, *, write=False):
        db = None
        with self._storage_guard():
            try:
                self._check_paths()
                if not self.path.is_file():
                    raise QuotaError('STORAGE')
                db = sqlite3.connect(self.path, timeout=5, isolation_level=None)
                db.row_factory = sqlite3.Row
                db.execute('PRAGMA foreign_keys = ON')
                db.execute('PRAGMA trusted_schema = OFF')
                db.execute('BEGIN IMMEDIATE' if write else 'BEGIN')
                yield db
                db.commit()
            except (sqlite3.Error, OSError, json.JSONDecodeError, UnicodeError) as exc:
                if db is not None:
                    db.rollback()
                raise QuotaError('STORAGE') from exc
            except BaseException:
                if db is not None:
                    db.rollback()
                raise
            finally:
                if db is not None:
                    db.close()

    @staticmethod
    def _key(key):
        if not isinstance(key, str) or not re.fullmatch(r'[0-9a-f]{64}', key):
            raise QuotaError()
        return key

    @staticmethod
    def _json(data):
        return json.dumps(data, ensure_ascii=True, separators=(',', ':'), allow_nan=False)

    @staticmethod
    def _stored_object(payload, allowed, required):
        if not isinstance(payload, str) or len(payload) > 16384:
            raise QuotaError('STORAGE')
        value = json.loads(payload)
        if (not isinstance(value, dict) or set(value) - allowed or
                not required.issubset(value)):
            raise QuotaError('STORAGE')
        if type(value.get('schema_version')) is not int or value['schema_version'] != 1:
            raise QuotaError('SCHEMA')
        return value

    def _account(self, db, key):
        row = db.execute('SELECT record FROM accounts WHERE account_key=?', (self._key(key),)).fetchone()
        if row is None:
            raise QuotaError('UNKNOWN_ACCOUNT')
        required = {'account_key', 'schema_version', 'membership_state', 'auth_state',
            'last_error_code', 'last_error_at', 'access_changed_at', 'created_at',
            'context_revision', 'last_verified_at', 'profile_id', 'session_id',
            'email', 'account_id', 'workspace_id', 'plan_type', 'seat_type', 'catalogued_at'}
        allowed = required | {'next_probe_at', 'probe_failures', 'probe_suspended',
                              'last_probe_at', 'provider_account_id', 'active_session_id'}
        record = self._stored_object(row[0], allowed, required)
        try:
            if record['account_key'] != key:
                raise QuotaError()
            _text(record['profile_id'], 60)
            email = _text(record['email'], 320)
            if '@' not in email or re.search(r'\s', email):
                raise QuotaError()
            sid = record['session_id']
            if sid != 'default' and (not isinstance(sid, str) or not re.fullmatch('[0-9a-f]{32}', sid)):
                raise QuotaError()
            active_sid = record.get('active_session_id', sid)
            if active_sid != 'default' and (not isinstance(active_sid, str) or not re.fullmatch('[0-9a-f]{32}', active_sid)):
                raise QuotaError()
            record['active_session_id'] = active_sid
            for field in ('account_id', 'workspace_id', 'provider_account_id'):
                _text(record.get(field), optional=True)
            for field in ('plan_type', 'seat_type'):
                _text(record[field], 64, optional=True)
            if record['membership_state'] not in ACCESS_STATES or record['auth_state'] not in AUTH_STATES:
                raise QuotaError()
            if record['last_error_code'] is not None and record['last_error_code'] not in ERROR_CODES:
                raise QuotaError()
            for field in ('created_at', 'catalogued_at'):
                _stamp(record[field])
            for field in ('last_error_at', 'access_changed_at', 'last_verified_at', 'last_probe_at', 'next_probe_at'):
                if record.get(field) is not None:
                    _stamp(record[field])
            revision = record['context_revision']
            if type(revision) is not int or revision < 0:
                raise QuotaError()
            failures = record.get('probe_failures', 0)
            if type(failures) is not int or not 0 <= failures <= 100:
                raise QuotaError()
            if type(record.get('probe_suspended', False)) is not bool:
                raise QuotaError()
        except (QuotaError, TypeError) as exc:
            raise QuotaError('STORAGE') from exc
        return record

    def _snapshot(self, payload, key):
        window_fields = {slot + '_' + field for slot in ('primary', 'secondary')
                         for field in ('present', 'used_percent', 'duration_minutes', 'reset_at')}
        required = window_fields | {'snapshot_id', 'account_key', 'account_id', 'workspace_id',
            'plan_type', 'seat_type', 'observed_at', 'source', 'access_state', 'capture_reason',
            'schema_version', 'context_revision', 'additional_limits_reported',
            'ordinary_usage_allowed', 'spend_control_reached', 'rate_limit_reached_type'}
        snapshot = self._stored_object(payload,
            required | {'reset_credits', 'freshness', 'verification_state'}, required)
        try:
            if snapshot['account_key'] != key or snapshot['source'] != 'official-app-server':
                raise QuotaError()
            ident = snapshot['snapshot_id']
            if not isinstance(ident, str) or not re.fullmatch('[0-9a-f]{32}', ident):
                raise QuotaError()
            for field in ('account_id', 'workspace_id'):
                _text(snapshot[field], optional=True)
            for field in ('plan_type', 'seat_type'):
                _text(snapshot[field], 64, optional=True)
            _stamp(snapshot['observed_at'])
            if snapshot['access_state'] not in ACCESS_STATES or snapshot['capture_reason'] not in CAPTURE_REASONS:
                raise QuotaError()
            revision = snapshot['context_revision']
            if type(revision) is not int or revision < 0:
                raise QuotaError()
            for slot in ('primary', 'secondary'):
                present = _optional_bool(snapshot[slot + '_present'])
                _number(snapshot[slot + '_used_percent'])
                duration = snapshot[slot + '_duration_minutes']
                if duration is not None and (type(duration) is not int or not 0 < duration <= 52560000):
                    raise QuotaError()
                reset = snapshot[slot + '_reset_at']
                if reset is not None:
                    _stamp(reset)
                if present is not True and any(snapshot[slot + '_' + f] is not None
                        for f in ('used_percent', 'duration_minutes', 'reset_at')):
                    raise QuotaError()
            for field in ('additional_limits_reported', 'ordinary_usage_allowed', 'spend_control_reached'):
                _optional_bool(snapshot[field])
            reached = snapshot['rate_limit_reached_type']
            if reached is not None and reached not in LIMIT_TYPES | {'UNKNOWN_PROVIDER_LIMIT'}:
                raise QuotaError()
            if 'reset_credits' in snapshot:
                _reset_credits(snapshot['reset_credits'])
            if 'freshness' in snapshot and snapshot['freshness'] not in SNAPSHOT_FRESHNESS:
                raise QuotaError()
            if ('verification_state' in snapshot and
                    snapshot['verification_state'] not in VERIFICATION_STATES):
                raise QuotaError()
        except (QuotaError, TypeError) as exc:
            raise QuotaError('STORAGE') from exc
        return snapshot

    def register(self, *, profile_id, session_id, email, account_id=None, workspace_id=None,
                 plan_type=None, seat_type=None, now=None):
        now = _stamp(int(time.time()) if now is None else now)
        profile_id = _text(profile_id, 60)
        if session_id != 'default' and (not isinstance(session_id, str) or not re.fullmatch('[0-9a-f]{32}', session_id)):
            raise QuotaError()
        email = _text(email, 320)
        if '@' not in email or re.search(r'\s', email):
            raise QuotaError()
        account_id = _text(account_id, optional=True)
        workspace_id = _text(workspace_id, optional=True)
        plan_type = _text(plan_type, 64, optional=True)
        seat_type = _text(seat_type, 64, optional=True)
        # Unknown context is deliberately not coalesced across login sessions.
        scope = ([profile_id.casefold(), account_id, workspace_id] if account_id and workspace_id
                 else [profile_id.casefold(), session_id, email.casefold(), account_id, workspace_id])
        key = hashlib.sha256(self._json(scope).encode('utf-8')).hexdigest()
        with self._db(write=True) as db:
            row = db.execute('SELECT record FROM accounts WHERE account_key=?', (key,)).fetchone()
            record = self._account(db, key) if row else {
                'account_key': key, 'schema_version': 1, 'membership_state': 'WORKSPACE_ACCESS_UNKNOWN',
                'auth_state': 'REGISTERED', 'last_error_code': None, 'last_error_at': None,
                'access_changed_at': None, 'created_at': now, 'context_revision': 0,
                'last_verified_at': None}
            if row and any(record.get(field) != value for field, value in
                (('session_id', session_id), ('plan_type', plan_type), ('seat_type', seat_type))):
                record['context_revision'] = record.get('context_revision', 0) + 1
            record.update(profile_id=profile_id, session_id=session_id, email=email,
                          account_id=account_id, workspace_id=workspace_id, plan_type=plan_type,
                          seat_type=seat_type, active_session_id=session_id, catalogued_at=now)
            db.execute('INSERT INTO accounts VALUES (?,?) ON CONFLICT(account_key) DO UPDATE SET record=excluded.record',
                       (key, self._json(record)))
        return key

    def account(self, key):
        with self._db() as db:
            return self._account(db, key)

    def accounts(self):
        with self._db() as db:
            return [self._account(db, r[0]) for r in db.execute('SELECT account_key FROM accounts ORDER BY account_key')]

    def capture(self, key, usage, *, observed_at=None, capture_reason='poll',
                expected_revision=None, observed_plan=None):
        observed_at = _stamp(int(time.time()) if observed_at is None else observed_at)
        if capture_reason not in CAPTURE_REASONS:
            raise QuotaError()
        values = normalized_usage(usage)
        if expected_revision is not None and (type(expected_revision) is not int or expected_revision < 0):
            raise QuotaError()
        observed_plan = _text(observed_plan, 64, optional=True)
        observed_id = _text(usage.get('account_id'), optional=True)
        with self._db(write=True) as db:
            account = self._account(db, key)
            if expected_revision is not None and account.get('context_revision', 0) != expected_revision:
                raise QuotaError('CONTEXT_CHANGED')
            current_id = account['account_id'] or account.get('provider_account_id')
            if observed_id is not None and current_id is not None and observed_id != current_id:
                raise QuotaError('ACCOUNT_MISMATCH')
            current_observation = observed_at >= (account.get('last_verified_at') or 0)
            snapshot_plan = observed_plan if observed_plan is not None else account['plan_type']
            if current_observation and snapshot_plan != account['plan_type']:
                account['plan_type'] = snapshot_plan
                account['context_revision'] = account.get('context_revision', 0) + 1
            if observed_id is not None:
                # Bind provider identity without mistaking it for a workspace ID or
                # changing the catalogue/session key underneath an existing login.
                account['provider_account_id'] = observed_id
            snapshot = {**values, 'snapshot_id': uuid.uuid4().hex, 'account_key': key,
                'account_id': observed_id or current_id, 'workspace_id': account['workspace_id'],
                'plan_type': snapshot_plan, 'seat_type': account['seat_type'],
                'observed_at': observed_at, 'source': 'official-app-server',
                'access_state': account['membership_state'], 'capture_reason': capture_reason,
                'schema_version': 1, 'context_revision': account.get('context_revision', 0),
                'freshness': 'LIVE_VERIFIED', 'verification_state': 'VERIFIED'}
            db.execute('INSERT INTO snapshots VALUES (?,?,?,?,?)',
                (snapshot['snapshot_id'], key, observed_at, time.time_ns(), self._json(snapshot)))
            # A successful quota call verifies this authentication, not a workspace role.
            if current_observation and (account.get('last_error_at') is None or observed_at >= account['last_error_at']):
                account['auth_state'] = 'AUTHENTICATED'
                account['last_verified_at'] = observed_at
                account['last_error_code'] = None
                account['last_error_at'] = None
            db.execute('UPDATE accounts SET record=? WHERE account_key=?', (self._json(account), key))
        return snapshot

    def latest(self, key):
        with self._db() as db:
            row = db.execute('SELECT payload FROM snapshots WHERE account_key=? ORDER BY observed_at DESC, captured_at DESC LIMIT 1',
                             (self._key(key),)).fetchone()
            return self._snapshot(row[0], key) if row else None

    def history(self, key, *, limit=200, offset=0):
        if type(limit) is not int or not 1 <= limit <= 1000 or type(offset) is not int or offset < 0:
            raise QuotaError()
        with self._db() as db:
            return [self._snapshot(r[0], key) for r in db.execute(
                'SELECT payload FROM snapshots WHERE account_key=? ORDER BY observed_at DESC, captured_at DESC LIMIT ? OFFSET ?',
                (self._key(key), limit, offset))]

    def _event(self, key, *, kind, code, updates, now):
        now = _stamp(int(time.time()) if now is None else now)
        with self._db(write=True) as db:
            record = self._account(db, key)
            if kind == 'access':
                record['context_revision'] = record.get('context_revision', 0) + 1
            record.update(updates)
            db.execute('UPDATE accounts SET record=? WHERE account_key=?', (self._json(record), key))
            db.execute('INSERT INTO events(account_key,occurred_at,kind,code) VALUES (?,?,?,?)', (key, now, kind, code))

    def record_access(self, key, state, *, now=None):
        if state not in ACCESS_STATES:
            raise QuotaError()
        now = _stamp(int(time.time()) if now is None else now)
        self._event(key, kind='access', code=state, now=now,
                    updates={'membership_state': state, 'access_changed_at': now})

    def record_failure(self, key, code, *, now=None):
        if code not in ERROR_CODES:
            raise QuotaError()
        now = _stamp(int(time.time()) if now is None else now)
        updates = {'last_error_code': code, 'last_error_at': now}
        if code == 'NOT_AUTHENTICATED':
            updates['auth_state'] = 'SESSION_EXPIRED'
        self._event(key, kind='failure', code=code, updates=updates, now=now)

    def poll_state(self, key):
        record = self.account(key)
        return {'next_at': record.get('next_probe_at', 0),
                'failures': record.get('probe_failures', 0),
                'suspended': record.get('probe_suspended', False),
                'last_attempt': record.get('last_probe_at')}

    def schedule_poll(self, key, *, next_at, failures, suspended, last_attempt):
        _stamp(next_at)
        _stamp(last_attempt)
        if type(failures) is not int or not 0 <= failures <= 100 or type(suspended) is not bool:
            raise QuotaError()
        with self._db(write=True) as db:
            record = self._account(db, key)
            record.update(next_probe_at=next_at, probe_failures=failures,
                          probe_suspended=suspended, last_probe_at=last_attempt)
            db.execute('UPDATE accounts SET record=? WHERE account_key=?', (self._json(record), key))

    def prepare_removal(self, key):
        """Evidence prerequisite only; does not remove a member or grant permission."""
        snapshot = self.latest(key)
        if snapshot is None:
            raise QuotaError('NO_SNAPSHOT')
        return snapshot

    def backup(self):
        with self._storage_guard():
            """Explicit consistent backup. Never auto-replace a damaged original."""
            destination = self.root / 'quota.previous.sqlite3'
            _safe_path(destination)
            temp_path = None
            try:
                fd, temp = tempfile.mkstemp(prefix='.quota-backup-', dir=self.root)
                os.close(fd)
                temp_path = Path(temp)
                self._check_paths()
                if not self.path.is_file():
                    raise QuotaError('STORAGE')
                with closing(sqlite3.connect(self.path.as_uri() + '?mode=ro', uri=True)) as source, closing(sqlite3.connect(temp_path)) as target:
                    if source.execute('PRAGMA quick_check').fetchone()[0] != 'ok':
                        raise QuotaError('STORAGE')
                    source.backup(target)
                # Windows rejects fsync on a read-only handle (EBADF/WinError 9).
                # Open the staged backup read-write solely for the durability barrier.
                with temp_path.open('r+b') as stream:
                    os.fsync(stream.fileno())
                _safe_path(destination)
                os.replace(temp_path, destination)
                return destination
            except (OSError, sqlite3.Error) as exc:
                raise QuotaError('STORAGE') from exc
            finally:
                if temp_path is not None:
                    temp_path.unlink(missing_ok=True)

    def restore_from_backup(self, backup_path=None):
        """Restore an explicitly verified backup while preserving the current file.

        The source must be a regular file in this store's directory. It is checked
        read-only before any destination mutation, then copied to a staged file.
        The current database is copied to a unique preservation file before the
        staged copy is atomically installed.
        """
        if backup_path is None:
            raise QuotaError()
        try:
            source = Path(backup_path).absolute()
        except (TypeError, ValueError) as exc:
            raise QuotaError('STORAGE') from exc
        if source.parent != self.root or source == self.path:
            raise QuotaError('STORAGE')
        _safe_path(source)
        _safe_path(self.path)
        if not source.is_file() or not self.path.is_file():
            raise QuotaError('STORAGE')

        try:
            with closing(sqlite3.connect(source.as_uri() + '?mode=ro', uri=True)) as db:
                if db.execute('PRAGMA quick_check').fetchone()[0] != 'ok':
                    raise QuotaError('STORAGE')
                version = db.execute('PRAGMA user_version').fetchone()[0]
                if version not in (1, 2):
                    raise QuotaError('SCHEMA')
                tables = {row[0] for row in db.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'")}
                if not {'accounts', 'snapshots', 'events'}.issubset(tables):
                    raise QuotaError('SCHEMA')

            staged_fd, staged_name = tempfile.mkstemp(prefix='.quota-restore-', dir=self.root)
            os.close(staged_fd)
            staged = Path(staged_name)
            preservation_fd, preservation_name = tempfile.mkstemp(
                prefix='.quota-damaged-', dir=self.root)
            os.close(preservation_fd)
            preservation_temp = Path(preservation_name)
            preservation = self.root / ('quota.damaged-' + uuid.uuid4().hex + '.sqlite3')
            with source.open('rb') as stream, staged.open('wb') as target:
                shutil.copyfileobj(stream, target)
                target.flush()
                os.fsync(target.fileno())
            with self.path.open('rb') as stream, preservation_temp.open('wb') as target:
                shutil.copyfileobj(stream, target)
                target.flush()
                os.fsync(target.fileno())
            _safe_path(preservation)
            os.replace(preservation_temp, preservation)
            os.replace(staged, self.path)
            return preservation
        except QuotaError:
            raise
        except (OSError, sqlite3.Error, ValueError) as exc:
            raise QuotaError('STORAGE') from exc
        finally:
            for candidate in locals().get('staged', None), locals().get('preservation_temp', None):
                if candidate is not None:
                    candidate.unlink(missing_ok=True)
