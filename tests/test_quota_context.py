import tempfile
import unittest
from pathlib import Path
from multicodex.quota_store import QuotaStore, QuotaError
from multicodex.quota import evaluate_snapshot

class ContextTests(unittest.TestCase):
    def setUp(self):
        temp=tempfile.TemporaryDirectory();self.addCleanup(temp.cleanup)
        self.store=QuotaStore(Path(temp.name))
        self.key=self.store.register(profile_id='Work',session_id='default',email='a@example.invalid',
            account_id='a',workspace_id='w',plan_type='business',seat_type='standard',now=1000)
        self.data={'source':'official-app-server','windows':[
            {'label':'primary','used_percent':20,'minutes':300,'reset_at':18000},
            {'label':'secondary','used_percent':40,'minutes':10080,'reset_at':604800}]}

    def test_registration_does_not_claim_a_live_login(self):
        self.assertIsNone(self.store.account(self.key)['last_verified_at'])

    def test_restoration_in_same_second_invalidates_previous_observation(self):
        self.store.capture(self.key,self.data,observed_at=1100)
        self.store.record_access(self.key,'ACCESS_REMOVED',now=1100)
        self.store.record_access(self.key,'WORKSPACE_MEMBER',now=1100)
        result=evaluate_snapshot(self.store.latest(self.key),self.store.account(self.key),now=1100)
        self.assertFalse(result['capacity_confirmed'])

    def test_context_change_during_probe_rejects_late_observation(self):
        before=self.store.account(self.key).get('context_revision',0)
        self.store.record_access(self.key,'ACCESS_REMOVED',now=1100)
        with self.assertRaises(QuotaError) as caught:
            self.store.capture(self.key,self.data,observed_at=1200,expected_revision=before)
        self.assertEqual(caught.exception.code,'CONTEXT_CHANGED')
        self.assertIsNone(self.store.latest(self.key))

    def test_additional_unhandled_budgets_block_capacity_confirmation(self):
        self.data['additional_limits_reported']=True
        snap=self.store.capture(self.key,self.data,observed_at=1100)
        self.assertFalse(evaluate_snapshot(snap,self.store.account(self.key),now=1100)['capacity_confirmed'])

    def test_verified_plan_is_recorded_with_the_observation(self):
        snap=self.store.capture(self.key,self.data,observed_at=1100,observed_plan='pro')
        self.assertEqual(snap['plan_type'],'pro')
        self.assertEqual(self.store.account(self.key)['last_verified_at'],1100)

    def test_late_plan_observation_keeps_newer_current_plan_and_verification(self):
        self.store.capture(self.key,self.data,observed_at=2000,observed_plan='pro')
        self.store.capture(self.key,self.data,observed_at=1500,observed_plan='business')
        record=self.store.account(self.key)
        self.assertEqual(record['plan_type'],'pro')
        self.assertEqual(record['last_verified_at'],2000)
        self.assertEqual([row['plan_type'] for row in self.store.history(self.key)],['pro','business'])

    def test_first_observed_account_id_is_retained_when_catalogue_id_is_unknown(self):
        key=self.store.register(profile_id='Unknown',session_id='default',email='a@example.invalid',now=1000)
        snapshot=self.store.capture(key,{**self.data,'account_id':'provider-a'},observed_at=1100)
        self.assertEqual(snapshot['account_id'],'provider-a')
        self.assertIsNone(snapshot['workspace_id'])
        self.assertIsNone(self.store.account(key)['account_id'])
        self.assertEqual(self.store.account(key)['provider_account_id'],'provider-a')

    def test_changed_provider_account_id_never_merges_same_email_history(self):
        key=self.store.register(profile_id='Unknown',session_id='default',email='a@example.invalid',now=1000)
        self.store.capture(key,{**self.data,'account_id':'provider-a'},observed_at=1100)
        with self.assertRaises(QuotaError) as caught:
            self.store.capture(key,{**self.data,'account_id':'provider-b'},observed_at=1200)
        self.assertEqual(caught.exception.code,'ACCOUNT_MISMATCH')
        self.assertEqual(len(self.store.history(key)),1)

    def test_observed_account_id_must_be_safe_text(self):
        for value in ([],123,'provider\nraw',True):
            with self.subTest(value=value),self.assertRaises(QuotaError):
                self.store.capture(self.key,{**self.data,'account_id':value},observed_at=1100)

    def test_poll_schedule_survives_restart(self):
        self.store.schedule_poll(self.key,next_at=1500,failures=3,suspended=True,last_attempt=1200)
        self.assertEqual(QuotaStore(self.store.root).poll_state(self.key),
                         {'next_at':1500,'failures':3,'suspended':True,'last_attempt':1200})

if __name__=='__main__':unittest.main()
