import importlib
import importlib.util
import tempfile
import unittest
from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace
from multicodex.codex_client import AccountIdentity


class ExistingSessions:
    """Narrow fake of existing profile I/O, not of the new quota implementation."""
    def __init__(self):self.locked=False;self.pending=False
    def list(self,name):return [{'id':'default','email':'one@example.invalid','plan':'business','account_id':'one','label':'Work'}]
    @contextmanager
    def lock(self,name):
        self.locked=True
        try:yield
        finally:self.locked=False
    def journal(self,name):return {} if self.pending else None
    def home(self,name,sid):return Path('/fixture')/name/sid
    def home_fingerprint(self,name,sid):return self.home(name,sid), ('fixture',)
    def revalidate_home(self,name,sid,fingerprint):
        if fingerprint != ('fixture',):raise AssertionError('Changed fixture home')
        return self.home(name,sid)
    def identity(self,name,sid):return AccountIdentity('one@example.invalid','business','one')

class ServiceTests(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(importlib.util.find_spec('multicodex.quota_service'),'Quota service is missing')
        self.mod=importlib.import_module('multicodex.quota_service')
        tmp=tempfile.TemporaryDirectory();self.addCleanup(tmp.cleanup);self.root=Path(tmp.name)
        self.profiles=[SimpleNamespace(name='Work',linked=False)]
        self.sessions=ExistingSessions();self.calls=[]
        self.app=SimpleNamespace(store=SimpleNamespace(list=lambda:self.profiles),sessions=self.sessions)
        self.provider=SimpleNamespace(observe=self.observe)
        self.service=self.mod.QuotaService(self.root,self.app,provider=self.provider,clock=lambda:1000)
    def observe(self,home,*,expected,cancel,secure=True):
        self.assertTrue(self.sessions.locked)
        self.assertEqual(home.as_posix(),'/fixture/Work/default')
        self.calls.append(home)
        return {'identity':expected.public(),'observed_at':1000,'usage':{
            'source':'official-app-server','account_id':'one','ordinary_usage_allowed':True,
            'spend_control_reached':False,'windows':[
            {'label':'primary','used_percent':70,'minutes':300,'reset_at':18000},
            {'label':'secondary','used_percent':45,'minutes':10080,'reset_at':604800}]}}
    def test_catalogue_sync_performs_no_authentication_request(self):
        model=self.service.work()
        self.assertEqual(len(model['rows']),1);self.assertEqual(self.calls,[])
        self.assertEqual(model['rows'][0]['quota']['status'],'UNKNOWN')
    def test_manual_refresh_probes_under_original_profile_lock(self):
        key=self.service.work()['rows'][0]['account']['account_key']
        model=self.service.work(force_key=key)
        self.assertEqual(len(self.calls),1)
        self.assertEqual(model['rows'][0]['quota']['status'],'VERIFIED_AVAILABLE')
        self.assertEqual(model['rows'][0]['account']['membership_state'],'WORKSPACE_ACCESS_UNKNOWN')
    def test_deleted_profile_history_is_still_visible_and_not_probed(self):
        key=self.service.work()['rows'][0]['account']['account_key'];self.service.work(force_key=key)
        self.profiles.clear()
        model=self.service.work(force_key=key)
        self.assertEqual(len(model['rows']),1)
        self.assertFalse(model['rows'][0]['binding_available'])
        self.assertEqual(len(self.calls),1)
    def test_pending_session_transaction_blocks_probe(self):
        key=self.service.work()['rows'][0]['account']['account_key'];self.sessions.pending=True
        model=self.service.work(force_key=key)
        self.assertEqual(self.calls,[])
        self.assertNotEqual(model['rows'][0]['quota']['status'],'VERIFIED_AVAILABLE')
    def test_linked_legacy_profiles_are_not_rebound_or_auto_registered(self):
        self.profiles[0].linked=True
        self.assertEqual(self.service.work()['rows'],[])
    def test_enabled_monitor_keeps_theme_settings_separate(self):
        (self.root/'settings.json').write_text('{"theme":"light"}')
        self.service.save_settings({'enabled':True,'allowed_profiles':['Work']})
        model=self.service.work()
        self.assertEqual(len(self.calls),1)
        self.assertEqual((self.root/'settings.json').read_text(),'{"theme":"light"}')
        self.assertTrue(model['settings']['enabled'])
    def test_history_is_loaded_only_for_selected_known_key(self):
        key=self.service.work()['rows'][0]['account']['account_key'];self.service.work(force_key=key)
        self.assertEqual(self.service.history(key)[0]['primary_used_percent'],70)
    def test_shutdown_cancels_without_touching_accounts(self):
        self.service.cancel.set()
        self.assertEqual(self.service.work()['operation']['state'],'CANCELLED')
        self.assertEqual(self.calls,[])

if __name__=='__main__':unittest.main()
