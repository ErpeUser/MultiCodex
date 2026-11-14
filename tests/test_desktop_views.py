"""Cached desktop models preserve uncertainty and selected identities."""
import importlib
import importlib.util
import tkinter as tk
import unittest
from types import SimpleNamespace


def profile(name='Work', **changes):
    return SimpleNamespace(**{'name':name,'account_email':'a@example.invalid','session_id':'default','linked':False,**changes})


def view():
    return {'profiles':[profile()],'processes':{'Work':{'running':False,'pids':[]}},
            'sessions':{'Work':[{'id':'default','email':'a@example.invalid','label':'A'},
                                {'id':'b'*32,'email':'b@example.invalid','label':'B'}]},'recovery':{},'issues':[]}


class DesktopModelTests(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(importlib.util.find_spec('multicodex.desktop_views'))
        self.m=importlib.import_module('multicodex.desktop_views')
    def test_unloaded_dashboard_never_claims_zero_or_live_capacity(self):
        model=self.m.dashboard_metrics(view(),{},loaded=False)
        self.assertTrue(all(value is None for _,value in model))
    def test_unknown_process_remains_unknown_not_stopped(self):
        v=view();v['processes']={}
        self.assertIsNone(dict(self.m.dashboard_metrics(v,{},loaded=True))['Instanzen aktiv'])
        self.assertEqual(self.m.profile_records(v)[0]['actions'],())
    def test_running_profile_actions_do_not_offer_duplicate_start(self):
        v=view();v['processes']['Work']['running']=True
        self.assertEqual(self.m.profile_records(v)[0]['actions'],('stop','restart'))
    def test_recovery_profile_cannot_start_before_recovery(self):
        v=view();v['recovery']['Work']=True
        self.assertEqual(self.m.profile_records(v)[0]['actions'],('recover',))
    def test_inactive_saved_login_does_not_reauthenticate_other_active_account(self):
        rows=self.m.session_records(view(),[])
        self.assertIn('reauth',rows[0]['actions']);self.assertNotIn('reauth',rows[1]['actions'])
        self.assertIn('switch',rows[1]['actions'])
    def test_account_without_saved_session_still_offers_first_login(self):
        v=view();v['sessions']={}
        rows=self.m.session_records(v,[])
        self.assertEqual(rows[0]['actions'],('login',))
    def test_multiple_workspace_contexts_are_not_arbitrarily_merged(self):
        quota=[]
        for workspace in ('one','two'):
            quota.append({'account':{'profile_id':'Work','session_id':'default','email':'a@example.invalid',
                'workspace_id':workspace},'quota':{'windows':[],'freshness':'CACHED'}})
        row=self.m.session_records(view(),quota)[0]
        self.assertEqual(row['cells']['workspace'],'Mehrere Kontexte')
        self.assertEqual(row['cells']['five'],'Unbekannt')
    def test_profile_search_data_keeps_full_long_identity(self):
        v=view();v['profiles']=[profile('Long name '+('x'*40))]
        self.assertIn('x'*40,self.m.profile_records(v)[0]['cells']['profile'])


class DesktopTableTests(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(importlib.util.find_spec('multicodex.desktop_views'))
        self.m=importlib.import_module('multicodex.desktop_views')
        self.root=tk.Tk();self.root.geometry('800x600');self.addCleanup(self.root.destroy);self.events=[]
        self.panel=self.m.ActionTable(self.root,title='Profiles',columns=[('profile','Profil',220),('state','Status',180)],
            actions=[('launch','Starten'),('stop','Stoppen')],on_action=lambda a,r:self.events.append((a,r['id'])))
        self.panel.pack(fill='both',expand=True);self.root.update()
    def rows(self,n=3):
        return [{'id':str(i),'cells':{'profile':f'Profile {i:03}','state':'Gestoppt'},
            'actions':('launch',),'detail':'Details','profile':str(i)} for i in range(n)]
    def select(self,key):
        self.panel.table.selection_set(key);self.panel.table.event_generate('<<TreeviewSelect>>');self.root.update()
    def test_selected_identity_not_row_position_is_dispatched(self):
        self.panel.set_rows(self.rows());self.select('2');self.panel.buttons['launch'].invoke()
        self.assertEqual(self.events,[('launch','2')])
    def test_filtering_away_selection_disables_actions(self):
        self.panel.set_rows(self.rows());self.select('2');self.panel.query.set('Profile 000')
        self.panel.buttons['launch'].invoke();self.assertEqual(self.events,[])
    def test_unavailable_action_is_disabled(self):
        self.panel.set_rows(self.rows());self.select('1');self.panel.buttons['stop'].invoke();self.assertEqual(self.events,[])
    def test_busy_blocks_actions_without_dropping_selection(self):
        self.panel.set_rows(self.rows());self.select('1');self.panel.set_busy(True);self.panel.buttons['launch'].invoke()
        self.assertEqual(self.events,[]);self.panel.set_busy(False);self.panel.buttons['launch'].invoke()
        self.assertEqual(self.events,[('launch','1')])
    def test_paging_bounds_widgets_without_dropping_records(self):
        self.panel.set_rows(self.rows(205));self.assertEqual(len(self.panel.table.get_children()),100)
        self.panel.next_button.invoke();self.assertEqual(self.panel.table.get_children()[0],'100')
        self.panel.next_button.invoke();self.assertEqual(len(self.panel.table.get_children()),5)
    def test_state_restores_query_and_selection_after_rebuild(self):
        self.panel.set_rows(self.rows());self.panel.query.set('Profile 001');self.select('1');state=self.panel.get_state()
        self.panel.set_rows(self.rows(),state=state)
        self.assertEqual(self.panel.table.selection(),('1',))
    def test_loading_is_not_an_empty_success(self):
        self.panel.set_rows([],loaded=False)
        self.assertIn('geladen',self.panel.count_label.cget('text'))
    def test_refresh_preserves_current_selection(self):
        self.panel.set_rows(self.rows());self.select('1');self.panel.set_rows(self.rows())
        self.assertEqual(self.panel.table.selection(),('1',))


if __name__=='__main__':unittest.main()
