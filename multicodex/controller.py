"""Isolated session transactions. Never change the global multi-auth pool."""
from __future__ import annotations
import threading
from .codex_client import CodexError
from .sessions import MissingIdentityError, SessionStore

class OperationError(RuntimeError):
    pass

class SessionController:
    def __init__(self, store, instances, auth):
        self.store = store
        self.instances = instances
        self.auth = auth
        self.sessions = SessionStore(store)

    def _ready(self, name, confirmed):
        if not confirmed:
            raise OperationError('Confirm the restart and possible unsaved work first')
        if self.sessions.journal(name) is not None:
            raise OperationError('A previous operation needs recovery before another switch')

    def switch(self, name, session_id, *, confirmed):
        with self.sessions.lock(name):
            self._ready(name, confirmed)
            home = self.sessions.home(name, session_id)
            expected = self.sessions.identity(name, session_id)
            observed = self.auth.describe(home, refresh=False)
            if not expected.same_account(observed):
                raise CodexError('ACCOUNT_MISMATCH')
            old = self.store.get(name).session_id
            was_running = self.instances.running(name)
            journal = {'version': 1, 'old': old, 'new': session_id,
                       'was_running': was_running, 'phase': 'prepared'}
            self.sessions.write_journal(name, journal)
            if was_running:
                try:
                    if self.instances.stop(name) == 0 or self.instances.running(name):
                        raise OperationError('Selected instance did not stop')
                except Exception as exc:
                    # The old assignment is still intact. Keep evidence for an
                    # explicit recovery, not an unrequested force-kill/restart.
                    raise OperationError('Selected instance could not close; assignment was not changed. Recovery is required.') from exc
            try:
                journal['phase'] = 'stopped'; self.sessions.write_journal(name, journal)
                self.sessions.activate(name, session_id)
                journal['phase'] = 'bound'; self.sessions.write_journal(name, journal)
                self.instances.launch(name)
                if not self.instances.running(name):
                    raise OperationError('New process was not observed')
                journal['phase'] = 'started'; self.sessions.write_journal(name, journal)
                self.sessions.clear_journal(name)
            except Exception as exc:
                try:
                    self._rollback(name, journal)
                except Exception as rollback_error:
                    raise OperationError('Switch failed and recovery remains pending; saved authentication homes were preserved') from rollback_error
                raise OperationError('Switch failed; the previous assignment was restored') from exc
            return observed

    def _rollback(self, name, journal):
        if self.instances.running(name):
            if self.instances.stop(name) == 0 or self.instances.running(name):
                raise OperationError('Cannot restore metadata while the changed instance is still running')
        self.sessions.activate(name, journal['old'])
        if journal['was_running']:
            self.instances.launch(name)
            if not self.instances.running(name):
                raise OperationError('Previous instance restart was not observed')
        self.sessions.clear_journal(name)

    def login(self, name, *, confirmed, on_browser, cancel: threading.Event,
              reauthenticate=False):
        with self.sessions.lock(name):
            self._ready(name, confirmed)
            profile = self.store.get(name)
            # Preserve the previous identity so adding a second login does not
            # strand the first. Existing metadata also permits re-login when an
            # expired session can no longer be read by the official app server.
            try:
                previous = self.sessions.identity(name, profile.session_id)
            except MissingIdentityError:
                # A newly created profile has no registered identity yet. A
                # corrupt profile or unreadable session catalogue remains a
                # hard error instead of being mistaken for that state.
                try:
                    previous = self.auth.describe(profile.codex_home)
                except CodexError as exc:
                    if exc.code != 'NOT_AUTHENTICATED' or reauthenticate:
                        raise
                    previous = None
            expected = previous if reauthenticate else None
            if cancel.is_set():
                raise CodexError('CANCELLED')
            sid, home = self.sessions.prepare(name)
            identity = self.auth.login(home, on_browser=on_browser, cancel=cancel, expected=expected)
            if cancel.is_set():
                raise CodexError('CANCELLED')
            if expected is not None and not expected.same_account(identity):
                raise CodexError('ACCOUNT_MISMATCH')
            if previous is not None:
                self.sessions.register(name, profile.session_id, previous)
            self.sessions.register(name, sid, identity)
            return self.switch(name, sid, confirmed=True)

    def recover(self, name, *, confirmed):
        if not confirmed:
            raise OperationError('Recovery must be explicitly confirmed')
        with self.sessions.lock(name):
            journal = self.sessions.journal(name)
            if journal is None:
                return
            self._rollback(name, journal)

    def operate(self, name, action, *, confirmed=False, force=False):
        if action not in {'launch', 'stop', 'restart'}:
            raise OperationError('Unknown instance operation')
        if action != 'launch' and not confirmed:
            raise OperationError('Confirm possible unsaved work first')
        with self.sessions.lock(name):
            # Stopping remains available during recovery. Re-launching cannot
            # hide or silently finalize an interrupted assignment transaction.
            profile = self.store.get(name)
            if not profile.linked and action != 'stop' and self.sessions.journal(name) is not None:
                raise OperationError('Recover the interrupted account change first')
            if action == 'stop':
                return self.instances.stop(name, force=force)
            if action == 'restart' and self.instances.running(name):
                self.instances.stop(name, force=force)
                if self.instances.running(name):
                    raise OperationError('Selected instance has not stopped')
            return self.instances.launch(name)
