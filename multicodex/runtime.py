"""Named profile runtime; launch success requires observing the scoped root process."""
from __future__ import annotations
import subprocess
import time
from .discovery import find_legacy_codex_executable
from .processes import InstanceController, ProcessSafetyError
from .profiles import ProfileStore
from .sessions import SessionStore

class LocalInstances:
    def __init__(self, store: ProfileStore, controller: InstanceController | None = None):
        self.store = store
        self.controller = controller or InstanceController()
        self.sessions = SessionStore(store)

    def running(self, name: str) -> bool:
        return self.controller.running(self.store.get(name).home)

    def snapshot(self, profiles=None):
        profiles = self.store.list() if profiles is None else profiles
        records = self.controller.platform.list_processes()
        return {p.name: {'running': bool(matches), 'pids': [r.pid for r in matches]}
                for p in profiles for matches in [self.controller.matching(p.home, records)]}

    def stop(self, name: str, *, force=False) -> int:
        with self.sessions.lock(name):
            return self.controller.stop(self.store.get(name).home, force=force)

    def launch(self, name: str, *, timeout=8):
        with self.sessions.lock(name):
            profile = self.store.get(name)
            if not profile.linked:
                self.sessions.home(name, profile.session_id)
            executable = find_legacy_codex_executable()
            process = self.controller.launch(executable, profile.home, auth_home=profile.codex_home)
            deadline = time.monotonic() + timeout
            while time.monotonic() < deadline:
                if self.controller.running(profile.home):
                    return process.pid
                status = process.poll()
                if status is not None and status != 0:
                    raise ProcessSafetyError('Desktop process exited before its profile could be verified')
                time.sleep(.1)
            # This is the newly created startup process, never an arbitrary PID
            # discovered by name. Do not leave an unverified launcher alive.
            if process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=3)
                except subprocess.TimeoutExpired as exc:
                    raise ProcessSafetyError('Startup cleanup failed; inspect the selected instance before retrying') from exc
            raise ProcessSafetyError('Desktop startup was not observed for the selected profile')

    def restart(self, name: str):
        with self.sessions.lock(name):
            if self.running(name):
                self.stop(name)
            return self.launch(name)
