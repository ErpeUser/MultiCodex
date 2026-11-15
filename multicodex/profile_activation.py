"""Opt-in queued starts of exact saved logins; no quota-driven account rotation.

No automatic stop/kill, credential copy, membership edit, or browser login occurs.
A successful run verifies the process's auth-home binding and official quota read,
not the internals of an uninstrumented desktop window.
"""
from __future__ import annotations
from pathlib import Path
import time

from .automation_state import RunStore
from .locks import FileLock, BusyError
from .profile_router import eligibility


class ActivationError(RuntimeError):
    def __init__(self, code='UNAVAILABLE'):
        self.code = code if code in {'DISABLED', 'NOT_ALLOWLISTED', 'BUSY', 'AUTH_REQUIRED',
            'ACCOUNT_MISMATCH', 'PROCESS_UNVERIFIED', 'JOURNAL_PENDING', 'CONTEXT_CHANGED',
            'CANCELLED', 'UNAVAILABLE'} else 'UNAVAILABLE'
        super().__init__('Profile activation: ' + self.code)


class ProfileActivation:
    def __init__(self, root, quota, application, *, native=None, clock=time.time):
        self.root = Path(root)
        self.quota = quota
        self.application = application
        self.runs = RunStore(self.root / 'profile-automation')
        self.clock = clock
        self.cancel = quota.cancel
        if native is None:
            from .desktop_binding import DesktopBinding
            native = DesktopBinding(application.instances)
        self.native = native

    def request(self, account_key):
        config = self.quota.settings.load()
        if not config['automatic_activation_enabled']: raise ActivationError('DISABLED')
        account = self.quota.store.account(account_key)
        expected_revision = account['context_revision']
        if account['profile_id'] not in config['allowed_profiles']:
            raise ActivationError('NOT_ALLOWLISTED')
        self.quota._sync()
        account = self.quota.store.account(account_key)
        if account['context_revision'] != expected_revision:
            raise ActivationError('CONTEXT_CHANGED')
        if self.quota.bindings.get(account_key) != (account['profile_id'], account['session_id']):
            raise ActivationError('AUTH_REQUIRED')
        return self.runs.enqueue(account_key=account_key, profile=account['profile_id'],
            session_id=account['session_id'], now=int(self.clock()))

    def _step(self, run, state, **kwargs):
        return self.runs.transition(run['run_id'], run['state'], state, now=int(self.clock()), **kwargs)

    def _row(self, model, run):
        return next((row for row in model['rows'] if row['account']['account_key'] == run['account_key']), None)

    def _defer(self, run, code, config):
        state = {'AUTH_REQUIRED': 'AUTHENTICATION_REQUIRED', 'NOT_ALLOWLISTED': 'PAUSED',
                 'ACCESS_REMOVED': 'PAUSED', 'CONTEXT_CHANGED': 'PAUSED'}.get(code, 'VERIFICATION_REQUIRED')
        return self._step(run, state, error_code=code, next_at=int(self.clock())+config['poll_interval_seconds'])

    def tick(self):
        try:
            with FileLock(self.root / '.locks' / 'profile-activation.lock'):
                return self._tick()
        except BusyError:
            return {'state': 'PAUSED', 'error_code': 'BUSY'}

    def _tick(self):
        config = self.quota.settings.load()
        if self.cancel.is_set() or not config['automatic_activation_enabled']:
            return {'state': 'PAUSED', 'error_code': 'DISABLED'}
        pending = self.runs.pending()
        # A persisted cutover is evidence of an interruption, not a request to replay.
        for run in pending:
            if run['state'] in {'ACTIVATING_TARGET', 'VERIFYING_INSTANCE'}:
                return self._step(run, 'ROLLBACK_REQUIRED', error_code='INTERRUPTED')
            if run['state'] == 'CHECKING_TARGET':
                return self._step(run, 'PAUSED', error_code='INTERRUPTED')
        due = [r for r in pending if r['state'] in {'QUEUED', 'WAITING_FOR_RESET', 'VERIFICATION_REQUIRED'}
               and r['next_at'] <= int(self.clock())]
        if not due: return {'state': 'IDLE', 'error_code': None}
        run = self._step(due[0], 'CHECKING_TARGET')
        try:
            if run['profile'] not in config['allowed_profiles']:
                return self._defer(run, 'NOT_ALLOWLISTED', config)
            model = self.quota.work(force_key=run['account_key'])
            row = self._row(model, run)
            reason = eligibility(row, config['allowed_profiles'])
            if reason:
                if row and row['quota']['status'] == 'QUOTA_EXHAUSTED':
                    return self._step(run, 'WAITING_FOR_RESET', error_code='QUOTA_UNAVAILABLE',
                        next_at=int(self.clock())+config['poll_interval_seconds'])
                if model['operation'].get('error_code') in {'NOT_AUTHENTICATED','AUTH_FAILED','ACCOUNT_MISMATCH'}:
                    reason = 'AUTH_REQUIRED'
                elif model['operation'].get('error_code') and run['attempts'] >= config['maximum_retries']:
                    return self._step(run, 'FAILED', error_code='RETRY_LIMIT')
                return self._defer(run, reason, config)
            if self.cancel.is_set(): return self._step(run, 'CANCELLED', error_code='CANCELLED')
            return self._activate(run, row, config)
        except Exception as exc:
            current = self.runs.get(run['run_id'])
            code = getattr(exc, 'code', 'UNAVAILABLE')
            if code not in {'BUSY', 'ACCOUNT_MISMATCH', 'AUTH_REQUIRED', 'JOURNAL_PENDING',
                            'PROCESS_UNVERIFIED', 'CONTEXT_CHANGED', 'CANCELLED', 'DISABLED', 'NOT_ALLOWLISTED'}:
                code = 'UNAVAILABLE'
            if current['state'] in {'ACTIVATING_TARGET', 'VERIFYING_INSTANCE'}:
                return self._failed_cutover(current, code)
            if current['state'] == 'CHECKING_TARGET':
                return self._step(current, 'PAUSED', error_code=code)
            raise

    def _activate(self, run, row, config):
        app = self.application
        name, sid = run['profile'], run['session_id']
        with app.sessions.lock(name):
            if app.sessions.journal(name) is not None: raise ActivationError('JOURNAL_PENDING')
            profile = app.store.get(name)
            if profile.linked: raise ActivationError('CONTEXT_CHANGED')
            identity = app.sessions.identity(name, sid)
            account = row['account']
            if (identity.email.casefold() != account['email'].casefold() or
                identity.account_id != account['account_id']):
                raise ActivationError('ACCOUNT_MISMATCH')
            home = app.sessions.home(name, sid)
            observed = app.auth.describe(home, refresh=True, cancel=self.cancel)
            if not identity.same_account(observed): raise ActivationError('ACCOUNT_MISMATCH')
            if self.cancel.is_set(): raise ActivationError('CANCELLED')
            config = self.quota.settings.load()
            if not config['automatic_activation_enabled']: raise ActivationError('DISABLED')
            if name not in config['allowed_profiles']: raise ActivationError('NOT_ALLOWLISTED')
            if self.quota.store.account(run['account_key'])['context_revision'] != account['context_revision']:
                raise ActivationError('CONTEXT_CHANGED')
            running = app.instances.running(name)
            if type(running) is not bool: raise ActivationError('PROCESS_UNVERIFIED')
            if running and profile.session_id != sid: raise ActivationError('BUSY')
            if running:
                run = self._step(run, 'VERIFYING_INSTANCE')
            else:
                run = self._step(run, 'ACTIVATING_TARGET', old_session=profile.session_id)
                journal = {'version': 1, 'old': profile.session_id, 'new': sid,
                           'was_running': False, 'phase': 'prepared'}
                app.sessions.write_journal(name, journal)
                app.sessions.activate(name, sid)
                journal['phase'] = 'bound'; app.sessions.write_journal(name, journal)
                app.instances.launch(name)
                run = self._step(run, 'VERIFYING_INSTANCE')
            selected = app.store.get(name)
            if selected.session_id != sid or app.instances.running(name) is not True:
                raise ActivationError('PROCESS_UNVERIFIED')
            if self.native.verify(selected) is not True: raise ActivationError('PROCESS_UNVERIFIED')
            # Our own cutover journal blocks the regular monitor by design. Read
            # the exact auth home directly and persist the same sanitized contract.
            expected_revision = self.quota.store.account(run['account_key'])['context_revision']
            observation = self.quota.provider.observe(home, expected=identity, cancel=self.cancel, secure=True)
            self.quota.store.capture(run['account_key'], observation['usage'],
                observed_at=observation['observed_at'], expected_revision=expected_revision,
                observed_plan=observation['identity'].get('plan'), capture_reason='manual_refresh')
            from .quota import evaluate_snapshot
            current = self.quota.store.account(run['account_key'])
            check = evaluate_snapshot(self.quota.store.latest(run['account_key']), current,
                now=int(self.clock()), max_age_seconds=config['max_age_seconds'],
                warning_threshold_percent=config['warning_threshold_percent'])
            if not check['capacity_confirmed']: raise ActivationError('PROCESS_UNVERIFIED')
            if self.native.verify(selected) is not True: raise ActivationError('PROCESS_UNVERIFIED')
            foreground = False
            try: foreground = self.native.focus(selected) is True
            except Exception: pass  # Focus is optional; never emulate keyboard input.
            if run['old_session'] is not None: app.sessions.clear_journal(name)
            return self._step(run, 'COMPLETED', binding_verified=True, foreground=foreground)

    def _failed_cutover(self, run, code):
        with self.application.sessions.lock(run['profile']):
            if run['old_session'] is not None:
                try:
                    self._restore_binding(run)
                except Exception:
                    return self._step(run, 'ROLLBACK_REQUIRED', error_code=code)
            return self._step(run, 'FAILED', error_code=code)

    def _restore_binding(self, run):
        app = self.application; name = run['profile']
        if app.instances.running(name) is not False: raise ActivationError('BUSY')
        journal = app.sessions.journal(name)
        if journal is not None and (journal['old'] != run['old_session'] or
            journal['new'] != run['session_id'] or journal['was_running'] is not False):
            raise ActivationError('CONTEXT_CHANGED')
        # The durable run also owns the cutover if a crash followed journal cleanup.
        # Recovery is explicit, and no process may be alive before restoring metadata.
        if app.store.get(name).session_id not in {run['old_session'], run['session_id']}:
            raise ActivationError('CONTEXT_CHANGED')
        app.sessions.activate(name, run['old_session'])
        app.sessions.clear_journal(name)

    def recover(self, run_id):
        with FileLock(self.root / '.locks' / 'profile-activation.lock'):
            run = self.runs.get(run_id)
            if run['state'] != 'ROLLBACK_REQUIRED': raise ActivationError('JOURNAL_PENDING')
            with self.application.sessions.lock(run['profile']):
                if run['old_session'] is None:
                    if (self.application.sessions.journal(run['profile']) is not None or
                        self.application.store.get(run['profile']).session_id != run['session_id']):
                        raise ActivationError('CONTEXT_CHANGED')
                else:
                    self._restore_binding(run)
                return self._step(run, 'CANCELLED')

    def resume(self, run_id):
        with FileLock(self.root / '.locks' / 'profile-activation.lock'):
            run = self.runs.get(run_id)
            if run['state'] not in {'PAUSED','AUTHENTICATION_REQUIRED','FAILED'}:
                raise ActivationError('BUSY')
            if run['old_session'] is not None: raise ActivationError('JOURNAL_PENDING')
            return self._step(run, 'QUEUED')
