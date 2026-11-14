import importlib
import importlib.util
from pathlib import Path
import tempfile
import threading
import unittest
from types import SimpleNamespace
from multicodex.automation_settings import DEFAULTS

class Host:
    def __init__(self):
        self.services=object();self.closing=False;self.mutating=False;self.page='Overview'
        self.jobs=[];self.status='';self.rendered=0
    def _submit(self,key,work,callback,**kwargs):
        if self.jobs:return False
        self.jobs.append((key,work,callback,kwargs));return True
    def _set_status(self,text):self.status=text
    def _render(self):self.rendered+=1

class GuiBridgeTests(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(importlib.util.find_spec('multicodex.quota_gui'),'Quota GUI bridge is missing')
        self.mod=importlib.import_module('multicodex.quota_gui')
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.path=Path(self.temp.name)/'uncreated';self.host=Host()
        self.controller=self.mod.QuotaGuiController(self.host,self.path)
    def test_constructor_performs_no_storage_or_network_io(self):
        self.assertFalse(self.path.exists())
        self.assertFalse(self.controller.ready)
    def test_refresh_only_enqueues_work(self):
        self.controller.refresh()
        self.assertFalse(self.path.exists())
        self.assertEqual(len(self.host.jobs),1)
        self.assertEqual(self.host.jobs[0][0],'quota-monitor')
    def test_mutation_and_closing_block_new_probe(self):
        self.host.mutating=True;self.controller.refresh();self.assertEqual(self.host.jobs,[])
        self.host.mutating=False;self.host.closing=True;self.controller.refresh();self.assertEqual(self.host.jobs,[])
    def test_callback_alone_updates_cached_model(self):
        model={'rows':[],'settings':dict(DEFAULTS),'profiles':[],'issues':[],'summary':{},'operation':{'state':'IDLE'}}
        self.controller._loaded(model)
        self.assertTrue(self.controller.ready)
        self.assertIs(self.controller.model,model)
    def test_close_cancels_probe_without_starting_service(self):
        self.controller.close()
        self.assertTrue(self.controller.cancel.is_set())
        self.assertFalse(self.path.exists())
    def test_provider_exception_does_not_escape_into_ui(self):
        self.controller._failed(RuntimeError('SENTINEL_SECRET'))
        self.assertNotIn('SENTINEL_SECRET',self.host.status)
        self.assertFalse(self.controller.ready)
    def test_duplicate_request_does_not_replace_pending_callback(self):
        self.controller.refresh();first=self.host.jobs[0]
        self.controller.refresh(force_key='a'*64)
        self.assertIs(self.host.jobs[0],first)
        self.assertEqual(len(self.host.jobs),1)

    def test_manual_refresh_shows_progress_until_worker_completion(self):
        self.controller.refresh(force_key='a'*64)
        self.assertTrue(self.controller.foreground)
        self.controller._loaded({'rows':[],'settings':dict(DEFAULTS),'profiles':[],'issues':[],'operation':{'state':'IDLE'}})
        self.assertFalse(self.controller.foreground)

    def test_background_refresh_does_not_announce_foreground_work(self):
        self.controller.refresh()
        self.assertFalse(self.controller.foreground)

    def test_initial_summary_does_not_report_unread_catalogue_as_zero(self):
        text=self.controller._summary_text()
        self.assertNotIn('0 gespeicherte',text)
        self.assertIn('geladen',text)

    def test_initial_usage_load_renders_actual_data_after_worker_completes(self):
        self.host.page='Usage'
        self.controller._loaded({'rows':[],'settings':dict(DEFAULTS),'profiles':[],'issues':[],'operation':{'state':'IDLE'}})
        self.assertEqual(self.host.rendered,1)

if __name__=='__main__':unittest.main()
