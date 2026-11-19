import importlib
import importlib.util
from pathlib import Path
import tempfile
import unittest
from multicodex.codex_client import CodexError
from multicodex.quota_store import QuotaStore


class MonitorTests(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(importlib.util.find_spec('multicodex.quota_monitor'), 'Monitor is not implemented')
        self.mod=importlib.import_module('multicodex.quota_monitor')
        temp=tempfile.TemporaryDirectory();self.addCleanup(temp.cleanup)
        self.store=QuotaStore(Path(temp.name))
        self.key=self.store.register(profile_id='Work',session_id='default',email='one@example.invalid',account_id='one',now=1000)
        self.now=1000;self.calls=[]
        self.config={'enabled':True,'allowed_profiles':['Work'],'poll_interval_seconds':60,'maximum_retries':3}
        self.result={'identity':{'email':'one@example.invalid','account_id':'one','plan':'business'},'observed_at':1000,
            'usage':{'source':'official-app-server','windows':[{'label':'primary','used_percent':25,'minutes':300,'reset_at':18000}],
                     'reported':{'primary':True,'secondary':False},'account_id':'one'}}
        self.monitor=self.mod.QuotaMonitor(self.store,self.observe,lambda:self.config,clock=lambda:self.now)

    def observe(self,account,cancel):
        self.calls.append(account['account_key'])
        return {**self.result,'observed_at':self.now}

    def test_one_due_probe_persists_success_and_obeys_interval(self):
        self.assertEqual(self.monitor.tick()['state'],'SNAPSHOT_PERSISTED')
        self.assertEqual(self.store.latest(self.key)['primary_used_percent'],25)
        self.now=1059;self.assertEqual(self.monitor.tick()['state'],'IDLE')
        self.now=1060;self.monitor.tick()
        self.assertEqual(len(self.calls),2)

    def test_disabled_automation_never_probes(self):
        self.config['enabled']=False
        self.assertEqual(self.monitor.tick()['state'],'PAUSED')
        self.assertEqual(self.calls,[])

    def test_explicit_refresh_does_not_require_enabling_automation(self):
        self.config['enabled']=False
        self.assertEqual(self.monitor.tick(force_key=self.key)['state'],'SNAPSHOT_PERSISTED')
        self.assertFalse(self.config['enabled'])

    def test_only_allowed_profiles_are_polled(self):
        self.config['allowed_profiles']=[]
        self.assertEqual(self.monitor.tick()['state'],'IDLE')
        self.assertEqual(self.calls,[])

    def test_removed_accounts_keep_snapshot_without_network_probes(self):
        self.monitor.tick();self.store.record_access(self.key,'ACCESS_REMOVED',now=1010)
        self.now=1100
        self.assertEqual(self.monitor.tick()['state'],'IDLE')
        self.assertEqual(len(self.calls),1)
        self.assertEqual(self.store.latest(self.key)['primary_used_percent'],25)
        self.assertEqual(self.monitor.tick(force_key=self.key)['state'],'ACCESS_REMOVED')

    def test_backoff_and_retry_exhaustion_are_persistent(self):
        def fail(*args): raise CodexError('TIMEOUT')
        self.monitor.observe=fail
        self.assertEqual(self.monitor.tick()['state'],'FAILED')
        self.assertEqual(self.store.poll_state(self.key)['next_at'],1060)
        self.now=1060;self.monitor.tick()
        self.assertEqual(self.store.poll_state(self.key)['next_at'],1180)
        self.now=1180;self.assertEqual(self.monitor.tick()['state'],'PAUSED')
        other=self.mod.QuotaMonitor(self.store,self.observe,lambda:self.config,clock=lambda:2000)
        self.assertEqual(other.tick()['state'],'IDLE')
        self.assertEqual(self.calls,[])

    def test_manual_refresh_resumes_a_suspended_probe(self):
        self.store.schedule_poll(self.key,next_at=5000,failures=3,suspended=True,last_attempt=1000)
        self.assertEqual(self.monitor.tick(force_key=self.key)['state'],'SNAPSHOT_PERSISTED')
        self.assertFalse(self.store.poll_state(self.key)['suspended'])

    def test_provider_failure_cannot_erase_last_known_usage(self):
        self.monitor.tick()
        def fail(*args):raise CodexError('UNAVAILABLE')
        self.monitor.observe=fail;self.now=1060;self.monitor.tick()
        self.assertEqual(self.store.latest(self.key)['observed_at'],1000)
        self.assertEqual(self.store.account(self.key)['last_error_code'],'UNAVAILABLE')

    def test_unexpected_error_is_redacted(self):
        def fail(*args):raise RuntimeError('SENTINEL_TOKEN')
        self.monitor.observe=fail
        out=self.monitor.tick()
        self.assertEqual(out['error_code'],'UNKNOWN')
        self.assertNotIn('SENTINEL_TOKEN',str(out))
        self.assertNotIn(b'SENTINEL_TOKEN',self.store.path.read_bytes())

    def test_expired_session_is_not_retried_without_user_login(self):
        def fail(*args):raise CodexError('NOT_AUTHENTICATED')
        self.monitor.observe=fail;self.monitor.tick();self.now=2000
        self.assertEqual(self.monitor.tick()['state'],'IDLE')
        self.assertEqual(self.store.account(self.key)['auth_state'],'SESSION_EXPIRED')

    def test_wrong_identity_does_not_persist_quota(self):
        self.result['identity']['email']='wrong@example.invalid'
        out=self.monitor.tick()
        self.assertEqual(out['error_code'],'ACCOUNT_MISMATCH')
        self.assertIsNone(self.store.latest(self.key))

    def test_cancel_before_start_performs_no_network_or_history_write(self):
        self.monitor.cancel.set()
        self.assertEqual(self.monitor.tick()['state'],'CANCELLED')
        self.assertEqual(self.calls,[])
        self.assertIsNone(self.store.latest(self.key))

    def test_cancel_after_provider_return_does_not_capture(self):
        def observe(account,cancel):cancel.set();return self.result
        self.monitor.observe=observe
        self.assertEqual(self.monitor.tick()['state'],'CANCELLED')
        self.assertIsNone(self.store.latest(self.key))

    def test_second_monitor_rechecks_due_time_under_shared_lock(self):
        self.monitor.tick()
        other=self.mod.QuotaMonitor(self.store,self.observe,lambda:self.config,clock=lambda:1000)
        self.assertEqual(other.tick()['state'],'IDLE')
        self.assertEqual(len(self.calls),1)

    def test_only_one_account_is_probed_per_tick(self):
        self.store.register(profile_id='Work',session_id='a'*32,email='two@example.invalid',now=1000)
        self.monitor.tick()
        self.assertEqual(len(self.calls),1)

    def test_context_changed_during_network_call_is_not_committed(self):
        def observe(account,cancel):
            self.store.record_access(self.key,'ACCESS_REMOVED',now=1000)
            return self.result
        self.monitor.observe=observe
        result=self.monitor.tick()
        self.assertEqual(result['state'],'VERIFICATION_REQUIRED')
        self.assertIsNone(self.store.latest(self.key))

if __name__=='__main__':unittest.main()
