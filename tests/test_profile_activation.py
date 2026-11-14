"""Real profile/session/quota stores; only external provider and desktop are doubles."""
from pathlib import Path
from types import SimpleNamespace
import importlib
import importlib.util
import tempfile
import threading
import unittest
from multicodex.codex_client import AccountIdentity
from multicodex.profiles import ProfileStore
from multicodex.sessions import SessionStore
from multicodex.quota_service import QuotaService

class Instances:
    def __init__(self): self.live={'Other'};self.launched=[];self.fail=False
    def running(self,name):return name in self.live
    def launch(self,name):
        self.launched.append(name)
        if self.fail:raise RuntimeError('SENTINEL_SECRET')
        self.live.add(name)
    def stop(self,*args,**kwargs):raise AssertionError('Automation must never close a window')

class ActivationTests(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(importlib.util.find_spec('multicodex.profile_activation'),'Profile activation engine is missing')
        self.mod=importlib.import_module('multicodex.profile_activation')
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name);self.now=1000
        self.profiles=ProfileStore(self.root/'profiles');self.profiles.create('Work')
        self.sessions=SessionStore(self.profiles)
        self.one=AccountIdentity('one@example.invalid','business','one')
        self.two=AccountIdentity('two@example.invalid','business','two')
        self.sessions.register('Work','default',self.one)
        self.sid,self.home=self.sessions.prepare('Work');self.sessions.register('Work',self.sid,self.two)
        self.identities={str(self.profiles.get('Work').codex_home):self.one,str(self.home):self.two}
        self.instances=Instances();self.used=25;self.calls=0;self.binding_verified=True
        auth=SimpleNamespace(describe=lambda home,**kw:self.identities[str(home)])
        self.app=SimpleNamespace(store=self.profiles,sessions=self.sessions,instances=self.instances,auth=auth)
        self.quota=QuotaService(self.root,self.app,provider=SimpleNamespace(observe=self.observe),clock=lambda:self.now)
        self.quota.settings.save({'automatic_activation_enabled':True,'allowed_profiles':['Work']})
        self.native=SimpleNamespace(verify=lambda p:self.binding_verified,focus=lambda p:False)
        self.engine=self.mod.ProfileActivation(self.root,self.quota,self.app,native=self.native,clock=lambda:self.now)
        model=self.quota.work();self.key=next(r['account']['account_key'] for r in model['rows'] if r['account']['session_id']==self.sid)

    def observe(self,home,*,expected,cancel,secure):
        self.calls+=1
        return {'identity':self.identities[str(home)].public(),'observed_at':self.now,'usage':{
            'source':'official-app-server','account_id':expected.account_id,'ordinary_usage_allowed':True,
            'spend_control_reached':False,'windows':[
            {'label':'primary','used_percent':self.used,'minutes':300,'reset_at':self.now+18000},
            {'label':'secondary','used_percent':10,'minutes':10080,'reset_at':self.now+604800}]}}

    def request(self):return self.engine.request(self.key)

    def test_explicit_target_is_started_without_touching_other_windows(self):
        run=self.request();result=self.engine.tick()
        self.assertEqual(result['state'],'COMPLETED')
        self.assertTrue(result['binding_verified']);self.assertFalse(result['foreground'])
        self.assertEqual(self.profiles.get('Work').session_id,self.sid)
        self.assertEqual(self.instances.live,{'Work','Other'})
        self.assertIsNone(self.sessions.journal('Work'))
        self.assertEqual(len(self.engine.runs.list()),1)

    def test_exhausted_target_waits_without_switching_to_another_account(self):
        self.used=100;self.request();result=self.engine.tick()
        self.assertEqual(result['state'],'WAITING_FOR_RESET')
        self.assertEqual(self.instances.launched,[])
        self.assertEqual(self.profiles.get('Work').session_id,'default')
        self.assertEqual(self.calls,1)

    def test_waiting_target_is_reprobed_at_due_time_and_then_started(self):
        self.used=100;self.request();wait=self.engine.tick()
        self.used=20;self.now=wait['next_at'];result=self.engine.tick()
        self.assertEqual(result['state'],'COMPLETED')
        self.assertEqual(self.calls,3)  # first denial, second preflight, post-start verification

    def test_disabled_setting_does_not_probe_or_launch(self):
        self.request();self.quota.settings.save({'automatic_activation_enabled':False})
        self.assertEqual(self.engine.tick()['state'],'PAUSED')
        self.assertEqual(self.calls,0);self.assertEqual(self.instances.launched,[])

    def test_not_allowlisted_profile_is_rejected_before_enqueue(self):
        self.quota.settings.save({'allowed_profiles':[]})
        with self.assertRaises(self.mod.ActivationError):self.request()
        self.assertEqual(self.engine.runs.list(),[])

    def test_running_profile_with_other_session_is_not_rebound(self):
        self.instances.live.add('Work');self.request();result=self.engine.tick()
        self.assertEqual(result['state'],'PAUSED')
        self.assertEqual(result['error_code'],'BUSY')
        self.assertEqual(self.profiles.get('Work').session_id,'default')
        self.assertEqual(self.instances.launched,[])

    def test_already_running_matching_profile_is_reused_not_restarted(self):
        self.sessions.activate('Work',self.sid);self.instances.live.add('Work')
        self.request();result=self.engine.tick()
        self.assertEqual(result['state'],'COMPLETED')
        self.assertEqual(self.instances.launched,[])

    def test_changed_catalogue_identity_blocks_old_request(self):
        self.request();self.sessions.register('Work',self.sid,AccountIdentity('third@example.invalid','business','third'))
        result=self.engine.tick()
        self.assertEqual(result['state'],'AUTHENTICATION_REQUIRED')
        self.assertEqual(self.instances.launched,[])

    def test_wrong_live_identity_never_changes_binding(self):
        self.identities[str(self.home)]=self.one;self.request();result=self.engine.tick()
        self.assertNotEqual(result['state'],'COMPLETED')
        self.assertEqual(self.instances.launched,[])
        self.assertEqual(self.profiles.get('Work').session_id,'default')

    def test_failed_launch_restores_previous_binding_when_no_process_exists(self):
        self.instances.fail=True;self.request();result=self.engine.tick()
        self.assertEqual(result['state'],'FAILED')
        self.assertEqual(self.profiles.get('Work').session_id,'default')
        self.assertIsNone(self.sessions.journal('Work'))
        self.assertNotIn('SENTINEL_SECRET',str(self.engine.runs.list()))

    def test_unverified_live_process_is_preserved_for_recovery(self):
        self.binding_verified=False;self.request();result=self.engine.tick()
        self.assertEqual(result['state'],'ROLLBACK_REQUIRED')
        self.assertIn('Work',self.instances.live)
        self.assertIsNotNone(self.sessions.journal('Work'))

    def test_crash_during_cutover_cannot_be_replayed_as_new_launch(self):
        run=self.request()
        self.engine.runs.transition(run['run_id'],'QUEUED','CHECKING_TARGET',now=self.now)
        self.engine.runs.transition(run['run_id'],'CHECKING_TARGET','ACTIVATING_TARGET',now=self.now,old_session='default')
        self.sessions.write_journal('Work',{'version':1,'old':'default','new':self.sid,'was_running':False,'phase':'bound'})
        self.sessions.activate('Work',self.sid)
        result=self.engine.tick()
        self.assertEqual(result['state'],'ROLLBACK_REQUIRED')
        self.assertEqual(self.instances.launched,[])
        self.engine.recover(run['run_id'])
        self.assertEqual(self.profiles.get('Work').session_id,'default')
        self.assertIsNone(self.sessions.journal('Work'))

    def test_recovery_refuses_to_stop_a_running_instance(self):
        self.binding_verified=False;run=self.request();self.engine.tick()
        with self.assertRaises(self.mod.ActivationError):self.engine.recover(run['run_id'])
        self.assertIn('Work',self.instances.live)

    def test_provider_permission_denial_does_not_become_capacity(self):
        original=self.quota.provider.observe
        def denied(*args,**kw):
            result=original(*args,**kw);result['usage']['ordinary_usage_allowed']=False;return result
        self.quota.provider.observe=denied;self.request();result=self.engine.tick()
        self.assertEqual(result['state'],'WAITING_FOR_RESET');self.assertEqual(self.instances.launched,[])

    def test_cancelled_queue_does_not_trigger_network_or_desktop(self):
        run=self.request();self.engine.runs.cancel(run['run_id'],now=self.now)
        self.assertEqual(self.engine.tick()['state'],'IDLE')
        self.assertEqual(self.calls,0);self.assertEqual(self.instances.launched,[])

    def test_disabling_during_preflight_prevents_cutover(self):
        old=self.app.auth.describe
        def changed(home,**kw):
            self.quota.settings.save({'automatic_activation_enabled':False})
            return old(home,**kw)
        self.app.auth.describe=changed
        self.request();result=self.engine.tick()
        self.assertEqual(result['state'],'PAUSED')
        self.assertEqual(self.instances.launched,[])
        self.assertEqual(self.profiles.get('Work').session_id,'default')

    def test_context_changed_during_post_start_read_is_not_committed(self):
        old=self.quota.provider.observe
        def changed(*args,**kw):
            result=old(*args,**kw)
            if self.calls==2:
                self.quota.store.record_access(self.key,'WORKSPACE_MEMBER',now=self.now)
            return result
        self.quota.provider.observe=changed
        self.request();result=self.engine.tick()
        self.assertEqual(result['state'],'ROLLBACK_REQUIRED')
        self.assertFalse(result['binding_verified'])

    def test_crash_after_session_journal_cleared_is_explicitly_recoverable(self):
        run=self.request()
        self.engine.runs.transition(run['run_id'],'QUEUED','CHECKING_TARGET',now=self.now)
        self.engine.runs.transition(run['run_id'],'CHECKING_TARGET','ACTIVATING_TARGET',now=self.now,old_session='default')
        self.engine.runs.transition(run['run_id'],'ACTIVATING_TARGET','VERIFYING_INSTANCE',now=self.now)
        self.sessions.activate('Work',self.sid)
        self.assertEqual(self.engine.tick()['state'],'ROLLBACK_REQUIRED')
        self.engine.recover(run['run_id'])
        self.assertEqual(self.profiles.get('Work').session_id,'default')

    def test_crash_while_verifying_existing_window_can_cancel_without_stopping_it(self):
        self.sessions.activate('Work',self.sid);self.instances.live.add('Work')
        run=self.request()
        self.engine.runs.transition(run['run_id'],'QUEUED','CHECKING_TARGET',now=self.now)
        self.engine.runs.transition(run['run_id'],'CHECKING_TARGET','VERIFYING_INSTANCE',now=self.now)
        self.engine.tick()
        self.engine.recover(run['run_id'])
        self.assertIn('Work',self.instances.live)
        self.assertEqual(self.engine.runs.get(run['run_id'])['state'],'CANCELLED')

    def test_access_change_during_auth_preflight_blocks_new_process(self):
        old=self.app.auth.describe
        def changed(home,**kw):
            self.quota.store.record_access(self.key,'WORKSPACE_ACCESS_REMOVED',now=self.now)
            return old(home,**kw)
        self.app.auth.describe=changed
        self.request();result=self.engine.tick()
        self.assertEqual(self.instances.launched,[])
        self.assertEqual(result['state'],'PAUSED')
