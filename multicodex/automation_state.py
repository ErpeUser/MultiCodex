"""Durable, credential-free profile start requests and explicit state transitions."""
from __future__ import annotations
from contextlib import contextmanager
from pathlib import Path
import os
import re
import sqlite3
import uuid

from .profiles import validate_name
from .quota_store import _safe_path

TERMINAL = frozenset({'COMPLETED', 'CANCELLED', 'FAILED'})
WAITING = frozenset({'QUEUED', 'WAITING_FOR_RESET', 'VERIFICATION_REQUIRED',
                    'AUTHENTICATION_REQUIRED', 'PAUSED'})
ERRORS = frozenset({'DISABLED', 'NOT_ALLOWLISTED', 'BUSY', 'QUOTA_UNAVAILABLE',
    'ACCESS_REMOVED', 'ACCOUNT_MISMATCH', 'AUTH_REQUIRED', 'CANCELLED', 'UNAVAILABLE',
    'CONTEXT_CHANGED', 'PROCESS_UNVERIFIED', 'FOCUS_UNAVAILABLE', 'INTERRUPTED',
    'RETRY_LIMIT', 'UNKNOWN', 'JOURNAL_PENDING'})
TRANSITIONS = {state: {'CHECKING_TARGET', 'CANCELLED', 'PAUSED'} for state in WAITING}
TRANSITIONS['PAUSED'].add('QUEUED')
TRANSITIONS['AUTHENTICATION_REQUIRED'].add('QUEUED')
TRANSITIONS.update({
    'CHECKING_TARGET': {'WAITING_FOR_RESET', 'VERIFICATION_REQUIRED',
        'AUTHENTICATION_REQUIRED', 'PAUSED', 'FAILED', 'CANCELLED', 'ACTIVATING_TARGET',
        'VERIFYING_INSTANCE'},
    'ACTIVATING_TARGET': {'VERIFYING_INSTANCE', 'ROLLBACK_REQUIRED', 'FAILED'},
    'VERIFYING_INSTANCE': {'COMPLETED', 'ROLLBACK_REQUIRED', 'FAILED'},
    'ROLLBACK_REQUIRED': {'CANCELLED'},
    'FAILED': {'QUEUED'},
    'COMPLETED': set(), 'CANCELLED': set(),
})


class RunError(ValueError):
    def __init__(self, code='INVALID_DATA'):
        self.code = code if code in {'INVALID_DATA', 'STORAGE', 'CONFLICT', 'INVALID_TRANSITION'} else 'INVALID_DATA'
        super().__init__('Activation journal: ' + self.code)


def _id(value, length):
    if not isinstance(value, str) or not re.fullmatch('[0-9a-f]{'+str(length)+'}', value):
        raise RunError()
    return value


def _sid(value):
    return value if value == 'default' else _id(value, 32)


def _time(value):
    if type(value) is not int or not 0 <= value <= 253402300799:
        raise RunError()
    return value


class RunStore:
    def __init__(self, root: str | Path):
        self.root = Path(root).absolute()
        self.path = self.root / 'profile-activation.sqlite3'
        try:
            _safe_path(self.root)
            self.root.mkdir(parents=True, exist_ok=True, mode=0o700)
            _safe_path(self.path)
            try:
                fd = os.open(self.path, os.O_CREAT | os.O_EXCL | os.O_WRONLY |
                             getattr(os, 'O_NOFOLLOW', 0), 0o600)
            except FileExistsError:
                pass
            else:
                os.close(fd)
            with self._db(write=True) as db:
                version = db.execute('PRAGMA user_version').fetchone()[0]
                if version == 0:
                    if db.execute("SELECT 1 FROM sqlite_master WHERE type='table'").fetchone():
                        raise RunError('STORAGE')
                    db.execute('CREATE TABLE runs (run_id TEXT PRIMARY KEY, account_key TEXT NOT NULL, '
                        'profile TEXT NOT NULL, session_id TEXT NOT NULL, state TEXT NOT NULL, '
                        'created_at INTEGER NOT NULL, updated_at INTEGER NOT NULL, next_at INTEGER NOT NULL, '
                        'attempts INTEGER NOT NULL, error_code TEXT, old_session TEXT, '
                        'binding_verified INTEGER NOT NULL, foreground INTEGER NOT NULL)')
                    db.execute("CREATE UNIQUE INDEX one_pending_profile ON runs(profile COLLATE NOCASE) "
                               "WHERE state NOT IN ('COMPLETED','CANCELLED','FAILED')")
                    db.execute('PRAGMA user_version=1')
                elif version != 1:
                    raise RunError('STORAGE')
        except RunError:
            raise
        except (OSError, ValueError, sqlite3.Error) as exc:
            raise RunError('STORAGE') from exc

    @contextmanager
    def _db(self, write=False):
        db = None
        try:
            for suffix in ('', '-journal', '-wal', '-shm'):
                _safe_path(Path(str(self.path) + suffix))
            if not self.path.is_file():
                raise RunError('STORAGE')
            db = sqlite3.connect(self.path, timeout=5, isolation_level=None)
            db.row_factory = sqlite3.Row
            db.execute('PRAGMA trusted_schema=OFF')
            db.execute('BEGIN IMMEDIATE' if write else 'BEGIN')
            yield db
            db.commit()
        except RunError:
            if db: db.rollback()
            raise
        except (sqlite3.Error, OSError, ValueError) as exc:
            if db: db.rollback()
            raise RunError('STORAGE') from exc
        finally:
            if db: db.close()

    @staticmethod
    def _row(row):
        if row is None:
            raise RunError('CONFLICT')
        data = dict(row)
        try:
            _id(data['run_id'], 32); _id(data['account_key'], 64)
            validate_name(data['profile']); _sid(data['session_id'])
            if data['state'] not in TRANSITIONS:
                raise RunError()
            for field in ('created_at', 'updated_at', 'next_at'): _time(data[field])
            if type(data['attempts']) is not int or not 0 <= data['attempts'] <= 100000:
                raise RunError()
            if data['error_code'] is not None and data['error_code'] not in ERRORS:
                raise RunError()
            if data['old_session'] is not None: _sid(data['old_session'])
            for name in ('binding_verified', 'foreground'):
                if data[name] not in (0, 1): raise RunError()
                data[name] = bool(data[name])
        except (KeyError, TypeError, ValueError) as exc:
            raise RunError('STORAGE') from exc
        return data

    def enqueue(self, *, account_key, profile, session_id, now):
        _id(account_key, 64); _sid(session_id); _time(now)
        try: validate_name(profile)
        except ValueError as exc: raise RunError() from exc
        with self._db(write=True) as db:
            pending = db.execute("SELECT * FROM runs WHERE profile=? COLLATE NOCASE "
                "AND state NOT IN ('COMPLETED','CANCELLED','FAILED')", (profile,)).fetchone()
            if pending:
                result = self._row(pending)
                if result['account_key'] != account_key or result['session_id'] != session_id:
                    raise RunError('CONFLICT')
                return result
            ident = uuid.uuid4().hex
            db.execute('INSERT INTO runs VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)',
                (ident, account_key, profile, session_id, 'QUEUED', now, now, now, 0, None, None, 0, 0))
            return self._row(db.execute('SELECT * FROM runs WHERE run_id=?', (ident,)).fetchone())

    def get(self, run_id):
        _id(run_id, 32)
        with self._db() as db:
            return self._row(db.execute('SELECT * FROM runs WHERE run_id=?', (run_id,)).fetchone())

    def list(self, limit=100):
        if type(limit) is not int or not 1 <= limit <= 1000: raise RunError()
        with self._db() as db:
            return [self._row(row) for row in db.execute(
                'SELECT * FROM runs ORDER BY created_at DESC, rowid DESC LIMIT ?', (limit,))]

    def pending(self):
        with self._db() as db:
            return [self._row(row) for row in db.execute(
                "SELECT * FROM runs WHERE state NOT IN ('COMPLETED','CANCELLED','FAILED') "
                "ORDER BY created_at, rowid")]

    def transition(self, run_id, expected, state, *, now, next_at=None, error_code=None,
                   old_session=None, binding_verified=False, foreground=False):
        _id(run_id, 32); _time(now)
        due = now if next_at is None else _time(next_at)
        if state not in TRANSITIONS.get(expected, ()):
            raise RunError('INVALID_TRANSITION')
        if error_code is not None and error_code not in ERRORS: raise RunError()
        if old_session is not None: _sid(old_session)
        if type(binding_verified) is not bool or type(foreground) is not bool: raise RunError()
        if state == 'COMPLETED' and not binding_verified: raise RunError('INVALID_TRANSITION')
        with self._db(write=True) as db:
            old = self._row(db.execute('SELECT * FROM runs WHERE run_id=?', (run_id,)).fetchone())
            if old['state'] != expected or now < old['updated_at']: raise RunError('CONFLICT')
            attempts = old['attempts'] + (state == 'CHECKING_TARGET')
            db.execute('UPDATE runs SET state=?, updated_at=?, next_at=?, attempts=?, error_code=?, '
                'old_session=?, binding_verified=?, foreground=? WHERE run_id=?',
                (state, now, due, attempts, error_code, old_session if old_session is not None else old['old_session'],
                 int(binding_verified), int(foreground), run_id))
            return self._row(db.execute('SELECT * FROM runs WHERE run_id=?', (run_id,)).fetchone())

    def cancel(self, run_id, *, now):
        run = self.get(run_id)
        if run['state'] in TERMINAL: return run
        if run['old_session'] is not None or run['state'] not in WAITING:
            raise RunError('INVALID_TRANSITION')
        return self.transition(run_id, run['state'], 'CANCELLED', now=now)
