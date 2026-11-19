"""Official Codex stdio auth API. No OAuth implementation, passwords or token copying.

References: learn.chatgpt.com/docs/app-server and /docs/auth.
The server owns keyring persistence. Only account metadata crosses this API.
"""
from __future__ import annotations
import json
import os
import queue
import re
import subprocess
import threading
import time
from collections import deque
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlsplit
from . import __version__

_ERRORS = {
    'UNAVAILABLE': 'Official Codex app-server is unavailable',
    'PROTOCOL': 'The installed Codex client returned an unsupported response',
    'TIMEOUT': 'The Codex operation timed out',
    'CANCELLED': 'Sign-in was cancelled; the previous session was not replaced',
    'AUTH_FAILED': 'Codex did not complete sign-in successfully',
    'NOT_AUTHENTICATED': 'No supported saved ChatGPT sign-in was found',
    'ACCOUNT_MISMATCH': 'The signed-in account differs from the selected account',
    'UNSAFE_URL': 'Codex returned an unexpected sign-in URL',
    'PLAINTEXT_AUTH': 'Unexpected file-based authentication; activation was blocked',
}

class CodexError(RuntimeError):
    def __init__(self, code: str):
        self.code = code if code in _ERRORS else 'PROTOCOL'
        super().__init__(_ERRORS[self.code])

@dataclass(frozen=True)
class AccountIdentity:
    email: str
    plan: str | None = None
    account_id: str | None = None

    @classmethod
    def from_response(cls, response):
        account = response.get('account') if isinstance(response, dict) else None
        if not isinstance(account, dict) or account.get('type') != 'chatgpt':
            raise CodexError('NOT_AUTHENTICATED')
        email = account.get('email')
        if not isinstance(email, str) or len(email) > 320 or '@' not in email or re.search(r'[\x00-\x20\x7f]', email):
            raise CodexError('NOT_AUTHENTICATED')
        plan = account.get('planType')
        if not isinstance(plan, str) or len(plan) > 64 or re.search(r'[\x00-\x1f]', plan):
            plan = None
        # Providers have emitted both keys over time; a null accountId must
        # not hide a valid legacy id fallback.
        ident = account.get('accountId')
        if ident is None:
            ident = account.get('id')
        if not isinstance(ident, str) or not ident or len(ident) > 256 or re.search(r'[\x00-\x1f]', ident):
            ident = None
        return cls(email, plan, ident)

    def same_account(self, other: AccountIdentity) -> bool:
        if not isinstance(other, AccountIdentity):
            return False
        ids_match = ((self.account_id is None and other.account_id is None) or
                     (self.account_id is not None and other.account_id is not None and
                      self.account_id == other.account_id))
        return self.email.casefold() == other.email.casefold() and ids_match

    def public(self) -> dict:
        return {'email': self.email, 'plan': self.plan, 'account_id': self.account_id}


def validate_login_url(value: str) -> str:
    try:
        u = urlsplit(value)
        valid = (isinstance(value, str) and len(value) <= 8192 and u.scheme == 'https'
                 and u.hostname in {'auth.openai.com', 'chatgpt.com'}
                 and not u.username and not u.password and u.port in (None, 443)
                 and not re.search(r'[\x00-\x20\x7f]', value))
    except (ValueError, TypeError, AttributeError):
        valid = False
    if not valid:
        raise CodexError('UNSAFE_URL')
    return value


class CodexClient:
    """One sequential RPC conversation, with a bounded reader thread."""
    METHODS = {'initialize', 'account/read', 'account/login/start', 'account/login/cancel',
               'account/rateLimits/read'}
    MAX_LINE = 1024 * 1024

    def __init__(self, command: list[str], home: Path, *, secure: bool = True,
                 environment: dict | None = None, timeout: float = 15):
        self.command = list(command)
        self.home = Path(home).resolve()
        self.secure = secure
        self.timeout = timeout
        self.environment = {k: v for k, v in os.environ.items()
                            if not k.upper().startswith(('CODEX_', 'OPENAI_'))}
        self.environment.update(environment or {})
        self.environment.update(CODEX_HOME=str(self.home), RUST_LOG='error', RUST_BACKTRACE='0',
                                CODEX_MULTI_AUTH_RUNTIME_ROTATION_PROXY='0')
        self.process = None
        self.reader = None
        self.messages = queue.Queue(maxsize=256)
        self.notifications = deque(maxlen=64)
        self._failure = None
        self._next_id = 0
        self.cancel = None

    def __enter__(self):
        args = self.command + (['-c', 'cli_auth_credentials_store="keyring"'] if self.secure else []) + ['app-server']
        try:
            self.process = subprocess.Popen(args, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL, env=self.environment, bufsize=-1,
                creationflags=0x08000000 if os.name == 'nt' else 0)
            self.reader = threading.Thread(target=self._read, daemon=True)
            self.reader.start()
            self.request('initialize', {'clientInfo': {'name': 'multicodex', 'title': 'MultiCodex',
                'version': __version__}, 'capabilities': {'experimentalApi': False}})
            self._send({'method': 'initialized', 'params': {}})
            return self
        except Exception as exc:
            self.close()
            if isinstance(exc, CodexError):
                raise
            raise CodexError('UNAVAILABLE') from exc

    def _read(self):
        try:
            while True:
                line = self.process.stdout.readline(self.MAX_LINE + 1)
                if not line:
                    self.messages.put_nowait(None)
                    return
                if len(line) > self.MAX_LINE:
                    self._failure = 'PROTOCOL'
                    return
                obj = json.loads(line)
                if not isinstance(obj, dict):
                    self._failure = 'PROTOCOL'
                    return
                self.messages.put_nowait(obj)
        except (ValueError, UnicodeError, OSError, queue.Full):
            self._failure = 'PROTOCOL'

    def _send(self, value):
        try:
            self.process.stdin.write((json.dumps(value, separators=(',', ':')) + '\n').encode('utf-8'))
            self.process.stdin.flush()
        except (OSError, ValueError, AttributeError) as exc:
            raise CodexError('UNAVAILABLE') from exc

    def _receive(self, deadline, cancel=None):
        while time.monotonic() < deadline:
            if cancel is not None and cancel.is_set():
                raise CodexError('CANCELLED')
            if self._failure:
                raise CodexError(self._failure)
            try:
                value = self.messages.get(timeout=min(.1, max(.001, deadline-time.monotonic())))
            except queue.Empty:
                continue
            if value is None:
                raise CodexError('UNAVAILABLE')
            # Refuse all server-initiated actions, including external-token refresh.
            if 'method' in value and 'id' in value:
                self._send({'id': value['id'], 'error': {'code': -32601, 'message': 'Unsupported server request'}})
                continue
            return value
        raise CodexError('TIMEOUT')

    def request(self, method, params, *, timeout=None):
        if method not in self.METHODS or not isinstance(params, dict):
            raise CodexError('PROTOCOL')
        cancel = self.cancel if method != 'account/login/cancel' else None
        if cancel is not None and cancel.is_set():
            raise CodexError('CANCELLED')
        self._next_id += 1
        ident = self._next_id
        self._send({'id': ident, 'method': method, 'params': params})
        deadline = time.monotonic() + (self.timeout if timeout is None else timeout)
        while True:
            value = self._receive(deadline, cancel)
            if value.get('method') == 'account/login/completed':
                self.notifications.append(value.get('params', {}))
                continue
            if 'method' in value:
                continue
            if type(value.get('id')) is not int or value['id'] != ident:
                raise CodexError('PROTOCOL')
            if 'error' in value:
                raise CodexError('AUTH_FAILED')
            if not isinstance(value.get('result'), dict):
                raise CodexError('PROTOCOL')
            return value['result']

    def wait_login(self, login_id, cancel: threading.Event, *, timeout=600):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if cancel.is_set():
                try:
                    self.request('account/login/cancel', {'loginId': login_id}, timeout=2)
                except CodexError:
                    pass
                raise CodexError('CANCELLED')
            while self.notifications:
                event = self.notifications.popleft()
                if isinstance(event, dict) and event.get('loginId') == login_id:
                    if event.get('success') is not True:
                        raise CodexError('AUTH_FAILED')
                    return event
            try:
                value = self._receive(min(deadline, time.monotonic() + .1))
            except CodexError as exc:
                if exc.code == 'TIMEOUT':
                    continue
                raise
            if value.get('method') == 'account/login/completed':
                self.notifications.append(value.get('params', {}))
        try:
            self.request('account/login/cancel', {'loginId': login_id}, timeout=2)
        except CodexError:
            pass
        raise CodexError('TIMEOUT')

    def close(self):
        if self.process is None:
            return
        try:
            if self.process.stdin:
                self.process.stdin.close()
            self.process.wait(timeout=1)
        except (OSError, subprocess.TimeoutExpired):
            try:
                self.process.terminate()
                self.process.wait(timeout=2)
            except (OSError, subprocess.TimeoutExpired):
                self.process.kill()
                self.process.wait(timeout=2)
        finally:
            if self.reader:
                self.reader.join(timeout=1)
            if self.process.stdout:
                self.process.stdout.close()

    def __exit__(self, *_exc):
        self.close()


class CodexAccountService:
    def __init__(self, cli_resolver=None):
        if cli_resolver is None:
            from .discovery import find_codex_cli
            cli_resolver = find_codex_cli
        self.cli_resolver = cli_resolver

    def client(self, home, *, secure=True):
        return CodexClient([str(self.cli_resolver())], Path(home), secure=secure)

    def describe(self, home, *, secure=True, refresh=False, cancel=None):
        client = self.client(home, secure=secure)
        client.cancel = cancel
        with client:
            return AccountIdentity.from_response(client.request('account/read', {'refreshToken': bool(refresh)}))

    def login(self, home, *, on_browser, cancel, expected=None):
        if cancel.is_set():
            raise CodexError('CANCELLED')
        client = self.client(home)
        client.cancel = cancel
        with client:
            result = client.request('account/login/start', {'type': 'chatgpt'})
            login_id = result.get('loginId')
            if not isinstance(login_id, str) or not login_id or len(login_id) > 256:
                raise CodexError('PROTOCOL')
            on_browser(validate_login_url(result.get('authUrl')))
            client.wait_login(login_id, cancel)
            identity = AccountIdentity.from_response(client.request('account/read', {'refreshToken': False}))
        if cancel.is_set():
            raise CodexError('CANCELLED')
        if (Path(home) / 'auth.json').exists():
            raise CodexError('PLAINTEXT_AUTH')
        # A fresh process must be able to read the saved keyring state. An
        # in-memory account update alone is not proof of successful persistence.
        persisted = self.describe(home, cancel=cancel)
        if not identity.same_account(persisted) or (expected is not None and not expected.same_account(persisted)):
            raise CodexError('ACCOUNT_MISMATCH')
        return persisted

    def limits(self, home, *, secure=True):
        with self.client(home, secure=secure) as client:
            data = client.request('account/rateLimits/read', {})
        windows = []
        limits = data.get('rateLimits')
        if isinstance(limits, dict):
            for key in ('primary', 'secondary'):
                win = limits.get(key)
                if not isinstance(win, dict):
                    continue
                value = win.get('usedPercent')
                if type(value) not in (int, float) or not (0 <= value <= 1000):
                    continue
                minutes = win.get('windowDurationMins')
                reset = win.get('resetsAt')
                windows.append({'label': key, 'used_percent': value,
                    'minutes': minutes if type(minutes) is int and minutes > 0 else None,
                    'reset_at': reset if type(reset) is int and reset >= 0 else None})
        return {'source': 'official-app-server', 'windows': windows}
