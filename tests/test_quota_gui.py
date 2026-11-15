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


    def test_activation_request_is_queued_not_executed_on_tk_thread(self):
        self.assertTrue(callable(getattr(self.controller,'enqueue_activation',None)))
        self.controller.enqueue_activation('a'*64)
        self.assertFalse(self.path.exists())
        self.assertEqual(len(self.host.jobs),1)

    def test_close_blocks_activation_request(self):
        self.assertTrue(callable(getattr(self.controller,'enqueue_activation',None)))
        self.controller.close();self.controller.enqueue_activation('a'*64)
        self.assertEqual(self.host.jobs,[])

    def test_unknown_activation_action_does_not_enqueue(self):
        self.assertTrue(callable(getattr(self.controller,'activation_action',None)))
        self.controller.activation_action('a'*32,'delete')
        self.assertEqual(self.host.jobs,[])

    def test_busy_quota_work_reports_rejected_activation_commands(self):
        self.controller.refresh();pending=self.host.jobs[0]
        for action in ('enqueue','cancel','resume','recover'):
            with self.subTest(action=action):
                self.host.status=''
                if action=='enqueue':self.controller.enqueue_activation('a'*64)
                else:self.controller.activation_action('b'*32,action)
                self.assertEqual(len(self.host.jobs),1)
                self.assertIs(self.host.jobs[0],pending)
                self.assertFalse(self.controller.foreground)
                self.assertFalse(self.path.exists())
                self.assertIn('l\u00e4uft',self.host.status)
                self.assertIn('erneut',self.host.status)

    def test_busy_quota_work_reports_rejected_backup(self):
        self.controller.refresh();pending=self.host.jobs[0]
        self.controller.backup()
        self.assertEqual(len(self.host.jobs),1)
        self.assertIs(self.host.jobs[0],pending)
        self.assertFalse(self.controller.foreground)
        self.assertFalse(self.path.exists())
        self.assertIn('l\u00e4uft',self.host.status)
        self.assertIn('erneut',self.host.status)
        self.assertNotIn('Sicherung erstellt',self.host.status)

    def test_accepted_manual_commands_have_no_busy_warning(self):
        for action in ('enqueue','cancel','resume','recover','backup'):
            with self.subTest(action=action):
                host=Host();controller=self.mod.QuotaGuiController(host,self.path)
                if action=='enqueue':controller.enqueue_activation('a'*64)
                elif action=='backup':controller.backup()
                else:controller.activation_action('b'*32,action)
                self.assertEqual(len(host.jobs),1)
                self.assertEqual(host.status,'')
                self.assertTrue(controller.foreground)
                self.assertFalse(self.path.exists())

    def test_refresh_keeps_workspace_reads_explicit(self):
        self.assertTrue(callable(getattr(self.controller,'_work',None)))
        class Service:
            def work(self,**kw):return {'rows':[],'settings':dict(DEFAULTS),'profiles':[]}
        class Engine:
            runs=SimpleNamespace(list=lambda **kwargs:[])
            def tick(self):return {'state':'IDLE'}
        self.controller.service=Service();self.controller.activation=Engine()
        model=self.controller._work()
        self.assertEqual(model['activation_runs'],[])
        self.assertEqual(model['activation_operation']['state'],'IDLE')

    def test_model_keeps_pending_runs_older_than_recent_history(self):
        from multicodex.automation_state import RunStore
        for state in ('QUEUED','ROLLBACK_REQUIRED'):
            with self.subTest(state=state):
                store=RunStore(Path(self.temp.name)/state)
                target=store.enqueue(account_key='a'*64,profile='Waiting',session_id='a'*32,now=1000)
                if state=='ROLLBACK_REQUIRED':
                    for old,new in [('QUEUED','CHECKING_TARGET'),('CHECKING_TARGET','ACTIVATING_TARGET'),
                                    ('ACTIVATING_TARGET','ROLLBACK_REQUIRED')]:
                        target=store.transition(target['run_id'],old,new,now=1001,old_session='default')
                for i in range(100):
                    recent=store.enqueue(account_key='b'*64,profile='Recent',session_id='default',now=2000+i*2)
                    store.cancel(recent['run_id'],now=2001+i*2)
                self.controller.service=SimpleNamespace(work=lambda **kwargs:{'rows':[],'settings':{}})
                self.controller.activation=SimpleNamespace(runs=store)
                model=self.controller._work(execute=False)
                self.assertIn(target['run_id'],[r['run_id'] for r in model['activation_runs']])
                self.assertEqual(len(model['activation_runs']),101)
                self.assertEqual(store.get(target['run_id']),target)
                self.assertFalse(self.path.exists())

    def test_workspace_read_is_queued_and_does_not_store_secret_in_model(self):
        self.assertTrue(callable(getattr(self.controller,'read_workspace',None)))
        self.controller.read_workspace('ws_test','SENTINEL_SECRET')
        self.assertEqual(len(self.host.jobs),1)
        self.assertEqual(self.host.jobs[0][0],'workspace-directory')
        self.assertNotIn('SENTINEL_SECRET',str(self.controller.model))

    def test_workspace_read_is_blocked_after_close(self):
        self.assertTrue(callable(getattr(self.controller,'read_workspace',None)))
        self.controller.close();self.controller.read_workspace('ws_test','SENTINEL_SECRET')
        self.assertEqual(self.host.jobs,[])

if __name__=='__main__':unittest.main()
