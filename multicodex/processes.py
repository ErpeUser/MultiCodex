"""Per-instance process isolation; never kill all processes by executable name."""
from __future__ import annotations

import os
import subprocess
import time
from pathlib import Path


class ProcessSafetyError(RuntimeError):
    pass


def _normalize(s: str) -> str:
    # Windows command paths are case-insensitive; on Unix test paths are not.
    path = os.path.normpath(s.strip('"'))
    # Windows may report the same local directory via an 8.3 short name.
    # Canonicalize only local absolute paths; never resolve network paths.
    if os.name == 'nt' and os.path.isabs(path) and not path.startswith('\\\\'):
        path = os.path.realpath(path)
    return os.path.normcase(path)


def _profile_from_command(command: list[str]) -> str | None:
    values = []
    for i, arg in enumerate(command):
        if not isinstance(arg, str):
            return None
        if arg == '--user-data-dir':
            if i + 1 >= len(command) or not command[i + 1]:
                return None
            values.append(_normalize(command[i + 1]))
        elif arg.startswith('--user-data-dir='):
            values.append(_normalize(arg.split('=', 1)[1]))
    # Multiple flags are ambiguous even if both values happen to be equal.
    return values[0] if len(values) == 1 else None


class PsutilPlatform:
    def list_processes(self):
        try:
            import psutil
        except ImportError as exc:
            raise ProcessSafetyError('psutil is required for scoped Windows process discovery') from exc
        records = []
        for p in psutil.process_iter(['pid', 'cmdline', 'name', 'exe']):
            candidate = False
            try:
                candidate = (p.info['name'] or '').lower() == 'chatgpt.exe'
                if not candidate:
                    continue
                # An unreadable candidate is not proof that a profile is idle.
                # Refuse state-changing actions rather than guess its identity.
                if not p.info['exe']:
                    raise ProcessSafetyError('Cannot verify a candidate desktop process')
                exe = Path(p.info['exe'])
                if (exe.parent.name.casefold() == 'app'
                    and exe.parent.parent.name.startswith('OpenAI.Codex_')
                    and p.is_running()):
                    if not p.info['cmdline']:
                        raise ProcessSafetyError('Cannot verify a candidate desktop command line')
                    records.append(_PsutilProcess(p, p.info['cmdline']))
            except psutil.NoSuchProcess:
                continue
            except psutil.AccessDenied as exc:
                if candidate:
                    raise ProcessSafetyError('Desktop process access was denied; status is unknown') from exc
        return records

    def start(self, executable, args, env):
        flags = (0x00000008 | 0x00000200) if os.name == 'nt' else 0
        return subprocess.Popen([str(executable), *args], env=env, close_fds=True,
                                creationflags=flags, stdout=subprocess.DEVNULL,
                                stderr=subprocess.DEVNULL, stdin=subprocess.DEVNULL)


def _request_window_close(pid: int) -> None:
    """Post WM_CLOSE only to windows owned by the already verified root PID."""
    import ctypes
    from ctypes import wintypes
    user32 = ctypes.WinDLL('user32', use_last_error=True)
    callback_type = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    user32.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
    user32.GetWindowThreadProcessId.restype = wintypes.DWORD
    user32.PostMessageW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
    user32.PostMessageW.restype = wintypes.BOOL
    user32.EnumWindows.argtypes = [callback_type, wintypes.LPARAM]
    user32.EnumWindows.restype = wintypes.BOOL
    @callback_type
    def visit(hwnd, _unused):
        owner = wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(owner))
        if owner.value == pid:
            user32.PostMessageW(hwnd, 0x0010, 0, 0)
        return True
    if not user32.EnumWindows(visit, 0):
        raise ProcessSafetyError('Could not enumerate the selected instance windows')


class _PsutilProcess:
    def __init__(self, process, cmdline):
        self.process = process
        self.pid = process.pid
        self.command = cmdline
        self.created = process.create_time()

    def _alive(self):
        # psutil.is_running checks PID reuse; retain the original Process object.
        return self.process.is_running() and self.process.create_time() == self.created

    def children(self):
        import psutil
        try:
            if not self._alive():
                return []
            return [_PsutilProcess(p, p.cmdline()) for p in self.process.children(recursive=True)]
        except psutil.NoSuchProcess:
            return []
        except psutil.AccessDenied as exc:
            raise ProcessSafetyError('Cannot verify the selected process tree') from exc

    def request_close(self):
        import psutil
        try:
            if not self._alive():
                return
            if self.process.cmdline() != self.command:
                raise ProcessSafetyError('Process identity changed before close')
            if os.name == 'nt':
                _request_window_close(self.pid)
            else:
                self.process.terminate()
        except psutil.NoSuchProcess:
            return

    def kill(self):
        import psutil
        try:
            if self._alive():
                self.process.kill()
        except psutil.NoSuchProcess:
            return

    def wait(self, timeout):
        import psutil
        try:
            self.process.wait(timeout=timeout)
        except psutil.NoSuchProcess:
            pass


class InstanceController:
    def __init__(self, platform=None):
        self.platform = platform if platform is not None else PsutilPlatform()

    @staticmethod
    def _check_home(home: Path) -> Path:
        from .profiles import is_redirect, check_profile_children, ProfileError
        home = Path(home).expanduser()
        if is_redirect(home):
            raise ProcessSafetyError('Redirected profile directories are forbidden')
        home = home.resolve()
        try:
            check_profile_children(home)
        except ProfileError as exc:
            raise ProcessSafetyError('Redirected profile data is forbidden') from exc
        if not home.is_dir() or len(home.parts) < 3 or home == Path(home.anchor):
            raise ProcessSafetyError('Refusing unsafe or missing profile directory')
        return home

    def matching(self, home: Path, records=None):
        home = self._check_home(home)
        expected = {_normalize(str(home)), _normalize(str(home / 'electron'))}
        return [p for p in (self.platform.list_processes() if records is None else records)
                if not any(a == '--type' or a.startswith('--type=') for a in p.command)
                and _profile_from_command(list(p.command)) in expected]

    def running(self, home: Path) -> bool:
        return bool(self.matching(home))

    def stop(self, home: Path, timeout: float = 10.0, *, force: bool = False) -> int:
        roots = self.matching(home)
        tree = list(roots)
        for root in roots:
            tree.extend(root.children() if hasattr(root, 'children') else [])
        unique = {p.pid: p for p in tree}
        deadline = time.monotonic() + timeout
        try:
            if force:
                for process in reversed(list(unique.values())):
                    (process.kill if hasattr(process, 'kill') else process.terminate)()
            else:
                for process in roots:
                    (process.request_close if hasattr(process, 'request_close') else process.terminate)()
            for process in unique.values():
                process.wait(timeout=max(.001, deadline - time.monotonic()))
            if self.matching(home):
                raise ProcessSafetyError('Selected instance is still running')
        except Exception as exc:
            raise ProcessSafetyError('Selected instance did not close. No automatic force-kill was performed.') from exc
        return len(roots)

    def launch(self, executable: Path, home: Path, *, auth_home: Path | None = None):
        home = self._check_home(home)
        executable = Path(executable)
        if not executable.is_file():
            raise ProcessSafetyError('Supported desktop executable not found')
        if self.running(home):
            raise ProcessSafetyError('Profile already running')
        (home / '.codex').mkdir(exist_ok=True, mode=0o700)
        (home / 'electron').mkdir(exist_ok=True, mode=0o700)
        from .profiles import is_redirect
        auth_home = Path(auth_home or home / '.codex')
        if is_redirect(auth_home) or not auth_home.resolve().is_relative_to(home):
            raise ProcessSafetyError('Authentication home must remain inside its profile')
        auth_home = auth_home.resolve()
        if not auth_home.is_dir():
            raise ProcessSafetyError('Authentication home is missing')
        env = {key: value for key, value in os.environ.items()
               if not key.upper().startswith(('CODEX_', 'OPENAI_'))}
        env['CODEX_HOME'] = str(auth_home)
        env['CODEX_ELECTRON_USER_DATA_PATH'] = str(home / 'electron')
        env['CODEX_MULTI_AUTH_DIR'] = str(auth_home / 'multi-auth')
        env['CODEX_MULTI_AUTH_RUNTIME_ROTATION_PROXY'] = '0'
        env['CODEX_MULTI_AUTH_FORCE_FILE_AUTH_STORE'] = '0'
        env['CODEX_MULTI_AUTH_ENFORCE_CLI_FILE_AUTH_STORE'] = '0'
        cli = executable.parent / 'resources' / 'codex.exe'
        if cli.is_file():
            env['CODEX_CLI_PATH'] = str(cli)
        return self.platform.start(str(executable), ['--user-data-dir', str(home / 'electron')], env)
