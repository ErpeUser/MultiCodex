"""Worker-only bridge from the existing profile/session services to quota history."""
from __future__ import annotations
import threading
import time
from .automation_settings import AutomationSettings
from .codex_client import CodexError
from .locks import BusyError
from .profiles import validate_name, ProfileError
from .quota import evaluate_snapshot
from .quota_monitor import QuotaMonitor
from .quota_store import QuotaStore
from .quota_view import summarize_rows


class QuotaService:
    def __init__(self, root, application, *, provider=None, clock=time.time, cancel=None):
        self.application = application
        self.clock = clock
        self.store = QuotaStore(root / 'quota-history')
        self.settings = AutomationSettings(root)
        if provider is None:
            from .quota_provider import QuotaAccountService
            provider = QuotaAccountService(cli_resolver=application.auth.cli_resolver,clock=clock)
        self.provider = provider
        self.monitor = QuotaMonitor(self.store,self._observe,self.settings.load,clock=clock)
        if cancel is not None:self.monitor.cancel=cancel
        self.cancel = self.monitor.cancel
        self.bindings = {}
        self.last_operation = {'state':'IDLE','account_key':None,'error_code':None}
        self._gate = threading.RLock()

    def _sync(self):
        # A profile/session/email tuple is not sufficient when the same login is
        # visible in more than one workspace. Keep candidates and bind only when
        # the workspace context is unambiguous.
        known={}
        for row in self.store.accounts():
            base=(row['profile_id'],row['session_id'],row['email'].casefold(),row.get('account_id'))
            known.setdefault(base, []).append(row)
        bindings={};issues=[];profiles=[]
        for profile in self.application.store.list():
            if profile.linked:continue
            profiles.append(profile.name)
            try:
                with self.application.sessions.lock(profile.name):
                    for session in self.application.sessions.list(profile.name):
                        workspace=session.get('workspace_id')
                        base=(profile.name,session['id'],session['email'].casefold(),session.get('account_id'))
                        candidates=known.get(base, [])
                        if workspace is not None:
                            candidates=[row for row in candidates if row.get('workspace_id') == workspace]
                        if len(candidates) > 1:
                            issues.append({'profile':profile.name,'code':'WORKSPACE_CONTEXT_REQUIRED'})
                            continue
                        row=candidates[0] if candidates else None
                        key=(row['account_key'] if row else
                             self.store.register(profile_id=profile.name,session_id=session['id'],
                                email=session['email'],account_id=session.get('account_id'),
                                workspace_id=workspace,plan_type=session.get('plan'),
                                now=int(self.clock())))
                        bindings[key]=(profile.name,session['id'])
            except Exception:
                # Corrupt metadata or an active login is not an empty healthy account list.
                issues.append({'profile':profile.name,'code':'PROFILE_UNAVAILABLE'})
        for issue in getattr(self.application.store, 'issues', []):
            try:
                name = validate_name(issue.get('name'))
            except (ProfileError, AttributeError):
                name = 'Profilkatalog'
            issues.append({'profile': name, 'code': 'PROFILE_UNAVAILABLE'})
        self.bindings=bindings
        return sorted(profiles,key=str.casefold),issues

    def _observe(self, account, cancel):
        binding=self.bindings.get(account['account_key'])
        if binding is None:raise CodexError('NOT_AUTHENTICATED')
        name,sid=binding
        try:
            with self.application.sessions.lock(name):
                if self.application.sessions.journal(name) is not None:
                    raise BusyError('Pending session transaction')
                expected=self.application.sessions.identity(name,sid)
                if (expected.email.casefold()!=account['email'].casefold() or
                    (expected.account_id is None) != (account.get('account_id') is None) or
                    (expected.account_id is not None and expected.account_id != account.get('account_id'))):
                    raise CodexError('ACCOUNT_MISMATCH')
                home, fingerprint = self.application.sessions.home_fingerprint(name, sid)
                home = self.application.sessions.revalidate_home(name, sid, fingerprint)
                return self.provider.observe(home,expected=expected,cancel=cancel,secure=True)
        except BusyError as exc:
            # The monitor allowlists this code; no filesystem/path exception is exposed.
            error=RuntimeError('BUSY');error.code='BUSY'
            raise error from exc

    def work(self, *, force_key=None):
        with self._gate:
            config=self.settings.load()
            profiles,issues=self._sync()
            if self.cancel.is_set():
                operation={'state':'CANCELLED','account_key':None,'error_code':None}
            elif force_key is not None and force_key not in self.bindings:
                operation={'state':'AUTHENTICATION_REQUIRED','account_key':force_key,'error_code':'NOT_AUTHENTICATED'}
            else:
                operation=self.monitor.tick(force_key=force_key,eligible_keys=set(self.bindings))
            if operation['state'] not in ('IDLE','PAUSED'):
                self.last_operation={**operation,'completed_at':int(self.clock())}
            now=int(self.clock())
            rows=[]
            for account in self.store.accounts():
                snap=self.store.latest(account['account_key'])
                rows.append({'account':account,'snapshot':snap,
                    'quota':evaluate_snapshot(snap,account,now=now,max_age_seconds=config['max_age_seconds'],
                                              warning_threshold_percent=config['warning_threshold_percent']),
                    'binding_available':account['account_key'] in self.bindings,
                    'polling':self.store.poll_state(account['account_key'])})
            return {'rows':rows,'settings':config,'profiles':profiles,'issues':issues,'operation':operation,
                    'last_operation':self.last_operation,'summary':summarize_rows(rows),'updated_at':now}

    def save_settings(self, changes):
        return self.settings.save(changes)

    def history(self, key, *, offset=0):
        return self.store.history(key,limit=100,offset=offset)

    def backup(self):
        return self.store.backup()
