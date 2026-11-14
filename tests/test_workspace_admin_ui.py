"""Real Tk form events must preserve exact reviews and clear transient keys."""
import copy
import importlib
import importlib.util
import tkinter as tk
import unittest


MODEL = {'workspace_id':'workspace-a','contract_version':'test-only','observed_at':1000,
    'capabilities': {
        'create_invite': {'enabled':True,'roles':['standard-user'],'seats':[]},
        'update_user': {'enabled':True,'roles':['standard-user','account-owner'],'seats':['default','usage_based']},
        'remove_user': {'enabled':True,'roles':[],'seats':[]},
        'resend_invite': {'enabled':False,'reason':'CONTRACT_MISSING','roles':[],'seats':[]},
        'cancel_invite': {'enabled':False,'reason':'CONTRACT_MISSING','roles':[],'seats':[]}},
    'members':[{'id':'user-a','email':'user@example.invalid','role':'standard-user','seat_type':'default'}],
    'invitations':[], 'quota_accounts':[{'account_key':'a'*64,'email':'user@example.invalid','profile_id':'Work','workspace_id':'workspace-a'}],
    'records':[], 'selected':None}
REVIEW = {'operation_id':'a'*32,'digest':'b'*64,'state':'REVIEW_REQUIRED','expires_at':9999999999,
    'snapshot_id':42,'review':{'action':'remove_user','workspace_id':'workspace-a','target':'user-a',
    'body':None,'account_key':'a'*64,'preflight':{'target':MODEL['members'][0]},'snapshot_id':42,'contract_version':'test-only'}}


class AdminUITests(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(importlib.util.find_spec('multicodex.workspace_admin_ui'))
        module=importlib.import_module('multicodex.workspace_admin_ui')
        self.root=tk.Tk();self.root.geometry('900x900');self.addCleanup(self.root.destroy)
        self.events=[]
        self.panel=module.WorkspaceAdminPanel(self.root,on_event=lambda event,data:self.events.append((event,data)))
        self.panel.pack(fill='both',expand=True);self.root.update()

    def load(self, review=False):
        model=copy.deepcopy(MODEL)
        if review:model.update(records=[copy.deepcopy(REVIEW)],selected=copy.deepcopy(REVIEW))
        self.panel.set_model(model);self.root.update()

    def key(self):self.panel.key.insert(0,'temporary-secret')

    def test_connection_clears_key_before_dispatch(self):
        self.panel.workspace.set('workspace-a');self.key();self.panel.connect_button.invoke()
        self.assertEqual(self.panel.key.get(),'')
        self.assertEqual(self.events,[('connect',{'workspace_id':'workspace-a','key':'temporary-secret'})])

    def test_actions_come_from_capabilities_not_all_possible_labels(self):
        self.load()
        self.assertEqual(set(self.panel.action_choices),{'create_invite','update_user','remove_user'})
        self.assertNotIn('resend_invite',self.panel.action_choices)

    def test_role_and_seat_values_are_readonly_provider_choices(self):
        self.load();self.panel.choose_action('update_user')
        self.assertEqual(tuple(self.panel.role_combo.cget('values')),('', 'standard-user','account-owner'))
        self.assertEqual(str(self.panel.role_combo.cget('state')),'readonly')

    def test_prepare_needs_member_target_and_dispatches_selected_snapshot(self):
        self.load();self.panel.choose_action('remove_user');self.key()
        self.panel.prepare_button.invoke();self.assertEqual(self.events,[])
        self.panel.directory.selection_set('member:user-a');self.panel.directory.event_generate('<<TreeviewSelect>>')
        self.root.update();self.panel.prepare_button.invoke()
        event,data=self.events[-1];self.assertEqual(event,'prepare')
        self.assertEqual(data['target'],'user-a');self.assertEqual(data['account_key'],'a'*64)
        self.assertEqual(self.panel.key.get(),'')

    def test_review_shows_workspace_target_and_snapshot(self):
        self.load(review=True)
        text=self.panel.review_text.get('1.0','end')
        for value in ('workspace-a','user-a','42'):self.assertIn(value,text)
        self.assertEqual(self.panel.current_review['digest'],'b'*64)

    def test_execution_requires_new_explicit_confirmation(self):
        self.load(review=True);self.key();self.panel.execute_button.invoke();self.assertEqual(self.events,[])
        self.panel.confirmed.set(True);self.panel.execute_button.invoke()
        self.assertEqual(self.events[-1][0],'execute')
        self.assertEqual(self.events[-1][1]['digest'],'b'*64)
        self.assertEqual(self.events[-1][1]['identity'],'a'*32)
        self.assertEqual(self.panel.key.get(),'')

    def test_changing_workspace_invalidates_confirmation_and_write_controls(self):
        self.load(review=True);self.panel.confirmed.set(True)
        self.panel.workspace.set('different');self.key();self.panel.execute_button.invoke()
        self.assertFalse(self.panel.confirmed.get());self.assertEqual(self.events,[])

    def test_form_edits_revoke_previous_approval(self):
        self.load(review=True);self.panel.confirmed.set(True);self.panel.email.set('other@example.invalid')
        self.assertFalse(self.panel.confirmed.get())

    def test_busy_blocks_duplicate_submission(self):
        self.load(review=True);self.panel.confirmed.set(True);self.key();self.panel.set_busy(True)
        self.panel.execute_button.invoke();self.assertEqual(self.events,[])

    def test_unknown_result_offers_readback_not_reexecution(self):
        self.load(review=True);model=copy.deepcopy(MODEL);row=copy.deepcopy(REVIEW);row['state']='OUTCOME_UNKNOWN'
        model.update(records=[row],selected=row);self.panel.set_model(model);self.panel.confirmed.set(True);self.key()
        self.panel.execute_button.invoke();self.assertEqual(self.events,[])
        self.panel.reconcile_button.invoke()
        self.assertEqual(self.events[-1],('reconcile',{'identity':'a'*32,'key':'temporary-secret'}))

    def test_error_hides_raw_details_and_disables_writes(self):
        self.load(review=True);self.panel.confirmed.set(True);self.panel.set_error('SECRET_PROVIDER_TEXT')
        self.assertNotIn('SECRET_PROVIDER_TEXT',self.panel.status.cget('text'))
        self.key();self.panel.execute_button.invoke();self.assertEqual(self.events,[])

    def test_reloading_directory_clears_stale_quota_mapping(self):
        self.load();self.panel.directory.selection_set('member:user-a')
        self.panel.directory.event_generate('<<TreeviewSelect>>');self.root.update()
        self.assertTrue(self.panel.quota_choices)
        model=copy.deepcopy(MODEL);model['members']=[]
        self.panel.set_model(model)
        self.assertEqual(self.panel.quota_choices,{})
        self.assertEqual(self.panel.quota.get(),'')

    def test_disabled_primary_action_does_not_look_enabled(self):
        self.load(review=True)
        self.assertEqual(self.panel.execute_button.cget('bg'),self.panel.p['selected'])
        self.panel.confirmed.set(True)
        self.assertEqual(self.panel.execute_button.cget('bg'),self.panel.p['accent'])

    def test_no_capability_is_not_displayed_as_empty_member_directory(self):
        self.load();model=copy.deepcopy(MODEL)
        for entry in model['capabilities'].values():entry['enabled']=False
        self.panel.set_model(model)
        self.assertEqual(self.panel.action_choices,[])
        self.assertEqual(len(self.panel.directory.get_children()),1)
        self.assertEqual(str(self.panel.prepare_button.cget('state')),'disabled')


if __name__=='__main__':unittest.main()
