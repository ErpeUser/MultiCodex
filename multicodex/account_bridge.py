"""Bounded metadata-only client; raw upstream errors are never user-visible."""
from __future__ import annotations
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

MESSAGES = {
    'BAD_PARAMS': 'Invalid account-operation parameters',
    'METHOD_NOT_FOUND': 'Unsupported account operation',
    'SERVICE_UNAVAILABLE': 'Local account service unavailable',
    'SERVICE_FAILED': 'Local account service exited unexpectedly',
    'INVALID_RESPONSE': 'Local account service returned an invalid response',
    'UPSTREAM_UNAVAILABLE': 'The required account-manager package is unavailable',
    'UPSTREAM_VERSION': 'The installed account-manager version is unsupported',
    'STORAGE_INVALID': 'Saved account data is unreadable or unsupported; original data was not changed',
    'UNSAFE_GLOBAL_SWITCH': 'Global pinning cannot change an isolated desktop session',
    'INTERNAL': 'Account operation failed; raw details are withheld',
}

class AccountBridgeError(RuntimeError):
    def __init__(self, code: str, message: str | None = None):
        self.code = code if code in MESSAGES else 'INTERNAL'
        super().__init__(MESSAGES[self.code])

class AccountBridge:
    def __init__(self, node: str | Path | None = None, service: Path | None = None):
        frozen = getattr(sys, 'frozen', False)
        runtime = (Path(sys.executable).resolve().parent / 'runtime' if frozen
                   else Path(__file__).resolve().parents[1] / 'bridge')
        self.node = str(node or (runtime / 'node.exe' if frozen else shutil.which('node') or 'node'))
        self.service = Path(service or runtime / 'service.mjs')

    def request(self, method: str, params: dict | None = None, *, timeout: float = 30.0):
        if method not in ('health', 'accounts.list', 'accounts.switch', 'accounts.limits'):
            raise AccountBridgeError('METHOD_NOT_FOUND')
        if params is not None and not isinstance(params, dict):
            raise AccountBridgeError('BAD_PARAMS')
        request = json.dumps({'id': 1, 'method': method, 'params': params or {}}, separators=(',', ':'))
        if len(request.encode('utf-8')) > 65536:
            raise AccountBridgeError('BAD_PARAMS')
        try:
            result = subprocess.run([self.node, str(self.service)], input=request + '\n',
                stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True, encoding='utf-8',
                errors='strict', timeout=timeout, check=False,
                creationflags=0x08000000 if os.name == 'nt' else 0)
        except (OSError, subprocess.TimeoutExpired, UnicodeError) as exc:
            raise AccountBridgeError('SERVICE_UNAVAILABLE') from exc
        if result.returncode:
            raise AccountBridgeError('SERVICE_FAILED')
        if len(result.stdout) > 1024 * 1024:
            raise AccountBridgeError('INVALID_RESPONSE')
        try:
            response = json.loads(result.stdout)
        except (ValueError, TypeError) as exc:
            raise AccountBridgeError('INVALID_RESPONSE') from exc
        if not isinstance(response, dict) or type(response.get('id')) is not int or response['id'] != 1:
            raise AccountBridgeError('INVALID_RESPONSE')
        if 'error' in response:
            error = response['error']
            if not isinstance(error, dict) or not isinstance(error.get('code'), str):
                raise AccountBridgeError('INVALID_RESPONSE')
            raise AccountBridgeError(error['code'])
        if not isinstance(response.get('result'), dict):
            raise AccountBridgeError('INVALID_RESPONSE')
        return response['result']

    def list_accounts(self) -> list[dict]:
        rows = self.request('accounts.list').get('accounts')
        if not isinstance(rows, list) or any(not isinstance(row, dict) for row in rows):
            raise AccountBridgeError('INVALID_RESPONSE')
        return rows

    def switch(self, index: int) -> bool:
        # Retain the old API only to fail safely instead of silently pinning a global account.
        if type(index) is not int or index < 1:
            raise AccountBridgeError('BAD_PARAMS')
        raise AccountBridgeError('UNSAFE_GLOBAL_SWITCH')

    def limits(self) -> dict:
        return self.request('accounts.limits')
