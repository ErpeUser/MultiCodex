"""Real profile metadata + controller; process/auth boundaries use explicit fixtures."""
import json
import tempfile
import threading
import unittest
from unittest.mock import patch
from pathlib import Path
from multicodex.controller import SessionController, OperationError
from multicodex.profiles import ProfileStore
from multicodex.sessions import SessionStore
from multicodex.codex_client import AccountIdentity, CodexError
from helpers.sessions import AuthFixture, InstancesFixture

class RestartTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.store=ProfileStore(Path(self.tmp.name)/'profiles')
        for name in ['Work','Research','Private']: self.store.create(name)
        self.sessions=SessionStore(self.store);self.auth=AuthFixture()
        self.instances=InstancesFixture(self.store);self.instances.live.update(['Work','Research','Private'])
        self.ctl=SessionController(self.store,self.instances,self.auth)
        self.auth.identities[str(self.store.get('Work').codex_home)]=AccountIdentity('old@example.invalid','plus',None)

    def session(self,email='new@example.invalid'):
        sid,home=self.sessions.prepare('Work')
        identity=AccountIdentity(email,'plus',None)
        self.auth.identities[str(home)]=identity
        self.sessions.register('Work',sid,identity)
        return sid,home

    def test_successful_switch_restarts_target_and_keeps_other_two(self):
        sid,_=self.session()
        self.ctl.switch('Work',sid,confirmed=True)
        self.assertEqual(self.store.get('Work').session_id,sid)
        self.assertEqual(self.instances.actions,[('stop','Work'),('launch','Work',sid)])
        self.assertEqual(self.instances.live,{'Work','Research','Private'})
        self.assertIsNone(self.sessions.journal('Work'))

    def test_switch_requires_confirmation_before_any_side_effect(self):
        sid,_=self.session()
        with self.assertRaises(OperationError): self.ctl.switch('Work',sid,confirmed=False)
        self.assertEqual(self.instances.actions,[])
        self.assertEqual(self.store.get('Work').session_id,'default')

    def test_invalid_auth_is_rejected_before_stop(self):
        sid,home=self.session();del self.auth.identities[str(home)]
        with self.assertRaises(CodexError): self.ctl.switch('Work',sid,confirmed=True)
        self.assertEqual(self.instances.actions,[])

    def test_failed_stop_does_not_bind_or_launch(self):
        sid,_=self.session();self.instances.stop_error=True
        with self.assertRaises(OperationError): self.ctl.switch('Work',sid,confirmed=True)
        self.assertEqual(self.store.get('Work').session_id,'default')
        self.assertFalse(any(a[0]=='launch' for a in self.instances.actions))

    def test_failed_new_launch_rolls_back_and_restarts_previous(self):
        sid,_=self.session();self.instances.fail_session=sid
        with self.assertRaises(OperationError): self.ctl.switch('Work',sid,confirmed=True)
        self.assertEqual(self.store.get('Work').session_id,'default')
        self.assertIn(('launch','Work','default'),self.instances.actions)
        self.assertIn('Research',self.instances.live)

    def test_idle_profile_is_started_after_switch(self):
        sid,_=self.session();self.instances.live.remove('Work')
        self.ctl.switch('Work',sid,confirmed=True)
        self.assertEqual(self.instances.actions,[('launch','Work',sid)])

    def test_failed_idle_launch_does_not_start_old_session(self):
        sid,_=self.session();self.instances.live.remove('Work');self.instances.fail_session=sid
        with self.assertRaises(OperationError): self.ctl.switch('Work',sid,confirmed=True)
        self.assertEqual(self.store.get('Work').session_id,'default')
        self.assertNotIn(('launch','Work','default'),self.instances.actions)

    def test_cancelled_login_does_not_stop_current_instance(self):
        self.auth.error='CANCELLED'
        with self.assertRaises(CodexError):
            self.ctl.login('Work',confirmed=True,on_browser=lambda u:None,cancel=threading.Event())
        self.assertEqual(self.instances.actions,[])
        self.assertEqual(self.store.get('Work').session_id,'default')

    def test_cancelled_login_does_not_prepare_an_account_read(self):
        cancel = threading.Event()
        cancel.set()
        with patch.object(self.auth, 'describe', side_effect=AssertionError('Cancelled login read an account')):
            with self.assertRaises(CodexError) as caught:
                self.ctl.login('Work', confirmed=True, on_browser=lambda _: None, cancel=cancel)
            self.assertEqual(caught.exception.code, 'CANCELLED')
        self.assertEqual(self.instances.actions, [])

    def test_wrong_identity_on_relogin_keeps_old_binding(self):
        with self.assertRaises(CodexError) as caught:
            self.ctl.login('Work',confirmed=True,reauthenticate=True,on_browser=lambda u:None,cancel=threading.Event())
        self.assertEqual(caught.exception.code,'ACCOUNT_MISMATCH')
        self.assertEqual(self.instances.actions,[])

    def test_successful_relogin_restarts_selected_instance(self):
        self.auth.next_identity=AccountIdentity('old@example.invalid','plus',None)
        self.ctl.login('Work',confirmed=True,reauthenticate=True,on_browser=lambda u:None,cancel=threading.Event())
        self.assertNotEqual(self.store.get('Work').session_id,'default')
        self.assertEqual(self.instances.actions[0],('stop','Work'))
        self.assertEqual(self.instances.actions[1][0:2],('launch','Work'))
        self.assertEqual(self.instances.live,{'Work','Research','Private'})

    def test_managed_session_config_never_uses_plaintext_auth(self):
        _,home=self.session()
        self.assertIn('cli_auth_credentials_store = "keyring"',(home/'config.toml').read_text())
        self.assertEqual(list(self.store.root.rglob('auth.json')),[])

    def test_unknown_session_id_cannot_point_outside_profile(self):
        with self.assertRaises((OperationError,ValueError)):
            self.ctl.switch('Work','../../foreign',confirmed=True)
        self.assertEqual(self.instances.actions,[])

    def test_pending_journal_blocks_new_operations_and_can_recover(self):
        sid,_=self.session()
        self.sessions.write_journal('Work',{'version':1,'old':'default','new':sid,'was_running':True,'phase':'prepared'})
        self.sessions.activate('Work',sid)
        with self.assertRaises(OperationError): self.ctl.switch('Work',sid,confirmed=True)
        self.ctl.recover('Work',confirmed=True)
        self.assertEqual(self.store.get('Work').session_id,'default')
        self.assertIsNone(self.sessions.journal('Work'))

    def test_session_binding_survives_manager_restart(self):
        sid,_=self.session();self.ctl.switch('Work',sid,confirmed=True)
        reopened=ProfileStore(self.store.root)
        self.assertEqual(reopened.get('Work').session_id,sid)
        self.assertEqual(reopened.get('Work').account_email,'new@example.invalid')

    def test_adding_login_preserves_previous_account_as_selectable_session(self):
        self.ctl.login('Work', confirmed=True, on_browser=lambda u: None, cancel=threading.Event())
        stored = self.sessions.list('Work')
        self.assertTrue(any(s['id']=='default' and s['email']=='old@example.invalid' for s in stored))
        self.ctl.switch('Work', 'default', confirmed=True)
        self.assertEqual(self.store.get('Work').account_email, 'old@example.invalid')

    def test_corrupt_session_catalogue_does_not_fall_back_to_live_auth(self):
        profile = self.store._entry('Work')
        (profile / 'profile.json').write_text('{"version": 1,', encoding='utf-8')
        with self.assertRaises(ValueError):
            self.ctl.login('Work', confirmed=True, on_browser=lambda u: None,
                           cancel=threading.Event())
        self.assertEqual(self.instances.actions, [])
