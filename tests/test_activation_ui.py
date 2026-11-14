import importlib
import importlib.util
import tkinter as tk
import unittest
from multicodex.automation_settings import DEFAULTS

class ActivationWidgetTests(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(importlib.util.find_spec('multicodex.activation_ui'),'Activation controls are missing')
        self.mod=importlib.import_module('multicodex.activation_ui')
        try:self.root=tk.Tk()
        except tk.TclError as exc:self.skipTest('Native Tk display unavailable: '+str(exc))
        self.addCleanup(self.root.destroy);self.calls=[]
        self.panel=self.mod.ActivationPanel(self.root,on_enqueue=lambda key:self.calls.append(('enqueue',key)),
            on_action=lambda key,action:self.calls.append((action,key)),on_enabled=lambda val:self.calls.append(('enabled',val)))
        self.panel.pack(fill='both',expand=True);self.root.geometry('850x450')
        self.model={'rows':[{'account':{'profile_id':'Work','email':'one@example.invalid',
            'session_id':'default','account_key':'a'*64},'binding_available':True}],
            'settings':{**DEFAULTS,'automatic_activation_enabled':True,'allowed_profiles':['Work']},'activation_runs':[]}
        self.panel.set_model(self.model);self.root.update()
    def test_queue_passes_exact_account_key_without_io(self):
        self.panel.target.current(0);self.panel.enqueue_button.invoke()
        self.assertEqual(self.calls,[('enqueue','a'*64)])
    def test_disabled_automation_does_not_offer_enqueue(self):
        self.model['settings']['automatic_activation_enabled']=False;self.panel.set_model(self.model)
        self.assertEqual(str(self.panel.enqueue_button['state']),'disabled')
    def test_non_allowlisted_accounts_are_not_selectable(self):
        self.model['settings']['allowed_profiles']=[];self.panel.set_model(self.model)
        self.assertEqual(len(self.panel.target['values']),0)
    def test_unbound_historical_account_is_not_selectable(self):
        self.model['rows'][0]['binding_available']=False;self.panel.set_model(self.model)
        self.assertEqual(len(self.panel.target['values']),0)
    def test_waiting_state_is_visible_without_claiming_success(self):
        self.model['activation_runs']=[{'run_id':'c'*32,'profile':'Work','session_id':'default',
            'state':'WAITING_FOR_RESET','updated_at':1000,'error_code':'QUOTA_UNAVAILABLE','old_session':None}]
        self.panel.set_model(self.model)
        values=self.panel.tree.item('c'*32,'values')
        self.assertTrue(any('Kapazit' in str(v) for v in values))
    def test_recovery_action_only_dispatches_selected_run(self):
        self.model['activation_runs']=[{'run_id':'c'*32,'profile':'Work','session_id':'default',
            'state':'ROLLBACK_REQUIRED','updated_at':1000,'error_code':'INTERRUPTED','old_session':'default'}]
        self.panel.set_model(self.model);self.panel.tree.selection_set('c'*32);self.panel.selected()
        self.panel.recover_button.invoke()
        self.assertEqual(self.calls,[('recover','c'*32)])
    def test_completed_run_cannot_be_cancelled(self):
        self.model['activation_runs']=[{'run_id':'c'*32,'profile':'Work','session_id':'default',
            'state':'COMPLETED','updated_at':1000,'error_code':None,'old_session':None}]
        self.panel.set_model(self.model);self.panel.tree.selection_set('c'*32);self.panel.selected()
        self.assertEqual(str(self.panel.cancel_button['state']),'disabled')

    def test_paused_busy_request_explains_required_action(self):
        self.model['activation_runs']=[{'run_id':'c'*32,'profile':'Work','session_id':'default',
            'state':'PAUSED','updated_at':1000,'error_code':'BUSY','old_session':None}]
        self.panel.set_model(self.model);self.panel.tree.selection_set('c'*32);self.panel.selected()
        self.assertTrue(hasattr(self.panel,'detail'))
        self.assertIn('laufende',self.panel.detail.cget('text'))
