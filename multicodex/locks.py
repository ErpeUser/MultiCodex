"""OS-released, reentrant per-profile locks; a crash never leaves a stale lock claim."""
from __future__ import annotations
import os
import threading
from pathlib import Path

class BusyError(RuntimeError):
    pass

_registry_guard = threading.Lock()
_registry: dict[str, threading.RLock] = {}
_held = threading.local()

class FileLock:
    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.key = os.path.normcase(str(self.path.absolute()))
        with _registry_guard:
            self.mutex = _registry.setdefault(self.key, threading.RLock())

    def __enter__(self):
        if not self.mutex.acquire(blocking=False):
            raise BusyError('Another operation is already using this profile')
        held = getattr(_held, 'files', None)
        if held is None:
            held = _held.files = {}
        if self.key in held:
            held[self.key][1] += 1
            return self
        stream = None
        try:
            for parent in self.path.parents:
                if parent.is_symlink() or (hasattr(parent, 'is_junction') and parent.is_junction()):
                    raise BusyError('Redirected lock directory')
            self.path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
            if self.path.is_symlink() or (hasattr(self.path, 'is_junction') and self.path.is_junction()):
                raise BusyError('Unsafe operation lock')
            flags = os.O_RDWR | os.O_CREAT | getattr(os, 'O_NOFOLLOW', 0)
            fd = os.open(self.path, flags, 0o600)
            stream = os.fdopen(fd, 'r+b', buffering=0)
            if os.name == 'nt':
                import msvcrt
                if os.fstat(fd).st_size == 0:
                    stream.write(b'\0')
                stream.seek(0)
                msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            held[self.key] = [stream, 1]
            return self
        except (OSError, BusyError) as exc:
            if stream is not None:
                stream.close()
            self.mutex.release()
            raise BusyError('Another operation is already using this profile, or its lock is unavailable') from exc

    def __exit__(self, *_exc):
        held = _held.files
        stream, depth = held[self.key]
        try:
            if depth > 1:
                held[self.key][1] -= 1
                return
            del held[self.key]
            try:
                if os.name == 'nt':
                    import msvcrt
                    stream.seek(0)
                    msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
                else:
                    import fcntl
                    fcntl.flock(stream.fileno(), fcntl.LOCK_UN)
            finally:
                stream.close()
        finally:
            self.mutex.release()
