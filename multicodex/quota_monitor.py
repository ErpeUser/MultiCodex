"""One bounded read-only quota probe per worker tick, with persistent backoff.

The host dispatches tick() off its GUI thread. This class never logs in, starts a
Desktop process, changes membership, or uses an account's quota to rotate seats.
"""
from __future__ import annotations
import threading
import time
from .automation_settings import validate_settings
from .codex_client import CodexError
from .locks import FileLock, BusyError
from .quota_store import ERROR_CODES

REMOVED = frozenset({'ACCESS_REMOVED','WORKSPACE_ACCESS_REMOVED','SEAT_UNAVAILABLE'})


class QuotaMonitor:
    def __init__(self, store, observe, settings, *, clock=time.time):
        self.store = store
        self.observe = observe
        self.settings = settings
        self.clock = clock
        self.cancel = threading.Event()
        self._gate = threading.Lock()

    @staticmethod
    def _result(state, key=None, code=None):
        return {'state':state,'account_key':key,'error_code':code}

    def tick(self, *, force_key=None, eligible_keys=None):
        if self.cancel.is_set():
            return self._result('CANCELLED')
        if not self._gate.acquire(blocking=False):
            return self._result('PAUSED',code='BUSY')
        try:
            config = validate_settings(self.settings())
            if not config['enabled'] and force_key is None:
                return self._result('PAUSED')
            allowed = {p.casefold() for p in config['allowed_profiles']}
            accounts = [self.store.account(force_key)] if force_key is not None else self.store.accounts()
            # Stable order; oldest scheduled observation first prevents starvation.
            accounts.sort(key=lambda row:(row.get('next_probe_at',0),row['account_key']))
            for account in accounts:
                key = account['account_key']
                if eligible_keys is not None and key not in eligible_keys:
                    continue
                if account['membership_state'] in REMOVED:
                    if force_key is not None:
                        return self._result('ACCESS_REMOVED',key)
                    continue
                if force_key is None and (account['profile_id'].casefold() not in allowed or
                        account['auth_state'] in ('SESSION_EXPIRED','DISABLED','ERROR')):
                    continue
                try:
                    with FileLock(self.store.root / '.locks' / ('poll-' + key + '.lock')):
                        account = self.store.account(key)
                        if account['membership_state'] in REMOVED:
                            continue
                        schedule = self.store.poll_state(key)
                        now = int(self.clock())
                        if force_key is None and (schedule['suspended'] or schedule['next_at'] > now):
                            continue
                        return self._probe(account,config,schedule,forced=force_key is not None)
                except BusyError:
                    if force_key is not None:
                        return self._result('PAUSED',key,'BUSY')
                    continue
            return self._result('IDLE')
        finally:
            self._gate.release()

    def _probe(self, account, config, schedule, *, forced):
        key = account['account_key']
        now = int(self.clock())
        try:
            if self.cancel.is_set():
                return self._result('CANCELLED',key)
            result = self.observe(account,self.cancel)
            if self.cancel.is_set():
                return self._result('CANCELLED',key)
            identity = result['identity']
            observed_id = identity.get('account_id')
            stored_id = account.get('account_id')
            if (identity['email'].casefold() != account['email'].casefold() or
                (stored_id is None) != (observed_id is None) or
                (stored_id is not None and stored_id != observed_id)):
                raise CodexError('ACCOUNT_MISMATCH')
            observed = result['observed_at']
            now = int(self.clock())
            if type(observed) is not int or observed > now or observed < now - config['max_age_seconds']:
                raise CodexError('PROTOCOL')
            self.store.capture(key,result['usage'],observed_at=observed,
                capture_reason='manual_refresh' if forced else 'poll',
                expected_revision=account.get('context_revision',0),observed_plan=identity.get('plan'))
            self.store.schedule_poll(key,next_at=now+config['poll_interval_seconds'],failures=0,
                                     suspended=False,last_attempt=now)
            return self._result('SNAPSHOT_PERSISTED',key)
        except Exception as exc:
            code = getattr(exc,'code','UNKNOWN')
            if code == 'CANCELLED' or self.cancel.is_set():
                return self._result('CANCELLED',key)
            if code == 'CONTEXT_CHANGED':
                return self._result('VERIFICATION_REQUIRED',key,'CONTEXT_CHANGED')
            code = code if code in ERROR_CODES else 'UNKNOWN'
            self.store.record_failure(key,code,now=now)
            failures = 1 if forced else min(100,schedule['failures']+1)
            suspended = failures >= config['maximum_retries'] or code in ('NOT_AUTHENTICATED','ACCOUNT_MISMATCH')
            delay = min(config['cooldown_seconds'],config['poll_interval_seconds'] * 2 ** min(failures-1,10))
            self.store.schedule_poll(key,next_at=now+delay,failures=failures,suspended=suspended,last_attempt=now)
            return self._result('PAUSED' if suspended else 'FAILED',key,code)
