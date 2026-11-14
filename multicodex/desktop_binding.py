"""Read exact process identity and auth-home environment before optional focus.

This verifies launcher binding, not internal UI account state. No foreground-lock
bypass, synthetic keys, global process lookup by title, or forced close is used.
"""
from __future__ import annotations
from pathlib import Path
import os


def _same_path(actual, expected):
    return isinstance(actual, str) and bool(actual) and os.path.normcase(
        str(Path(actual).resolve())) == os.path.normcase(str(Path(expected).resolve()))


class DesktopBinding:
    def __init__(self, instances, *, window_api=None):
        self.instances = instances
        self.window_api = window_api

    def _record(self, profile):
        records = self.instances.controller.matching(profile.home)
        if len(records) != 1: return None
        root = records[0]
        process = root.process
        if (root.pid != process.pid or not process.is_running() or
            process.create_time() != root.created or process.cmdline() != list(root.command)):
            return None
        environment = process.environ()
        if not _same_path(environment.get('CODEX_HOME'), profile.codex_home): return None
        if not _same_path(environment.get('CODEX_ELECTRON_USER_DATA_PATH'), profile.home / 'electron'): return None
        if not process.is_running() or process.create_time() != root.created: return None
        return root

    def verify(self, profile):
        try: return self._record(profile) is not None
        except Exception: return False

    def focus(self, profile):
        try:
            root = self._record(profile)
            if root is None: return False
            def valid():
                current = self._record(profile)
                return current is not None and (current.pid, current.created) == (root.pid, root.created)
            api = self.window_api
            if api is None:
                if os.name != 'nt': return False
                api = WindowsFocus()
            return bool(api.focus(root.pid, valid)) and valid()
        except Exception:
            return False


class WindowsFocus:
    """Best-effort focus only; Windows may legitimately deny foreground changes."""
    def focus(self, pid, valid):
        if os.name != 'nt' or not valid(): return False
        import ctypes
        from ctypes import wintypes
        user = ctypes.WinDLL('user32', use_last_error=True)
        callback_type = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
        user.EnumWindows.argtypes = [callback_type, wintypes.LPARAM]
        user.EnumWindows.restype = wintypes.BOOL
        user.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
        user.GetWindowThreadProcessId.restype = wintypes.DWORD
        for name in ('IsWindowVisible','IsIconic','SetForegroundWindow'):
            getattr(user, name).argtypes = [wintypes.HWND]
            getattr(user, name).restype = wintypes.BOOL
        user.ShowWindow.argtypes = [wintypes.HWND, ctypes.c_int]
        user.ShowWindow.restype = wintypes.BOOL
        user.GetForegroundWindow.restype = wintypes.HWND
        windows = []
        @callback_type
        def collect(hwnd, _):
            owner = wintypes.DWORD()
            user.GetWindowThreadProcessId(hwnd, ctypes.byref(owner))
            if owner.value == pid and user.IsWindowVisible(hwnd): windows.append(hwnd)
            return True
        if not user.EnumWindows(collect, 0): return False
        for hwnd in windows:
            if not valid(): return False
            owner = wintypes.DWORD()
            user.GetWindowThreadProcessId(hwnd, ctypes.byref(owner))
            if owner.value != pid: continue
            if user.IsIconic(hwnd): user.ShowWindow(hwnd, 9)
            if not valid(): return False
            user.SetForegroundWindow(hwnd)
            if user.GetForegroundWindow() == hwnd and valid(): return True
        return False
