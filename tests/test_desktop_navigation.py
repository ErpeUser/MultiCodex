"""Production view dispatch without pretending to run CustomTkinter or Windows."""
import unittest
from types import SimpleNamespace
from test_admin_navigation import method


class DesktopNavigationTests(unittest.TestCase):
    def host(self):
        events=[]
        host=SimpleNamespace(closing=False,mutating=False,snapshot_ready=False,view={},
            _snapshot_structure=method('_snapshot_structure'),
            _render=lambda:events.append('render'),_sync_desktop_data=lambda:events.append('sync'),
            _instance_action=lambda n,a:events.append((n,a)),_recover=lambda n:events.append((n,'recover')),
            _login=lambda n,**kw:events.append((n,'login',kw)),_inspect_account=lambda n:events.append((n,'inspect')),
            _switch=lambda n,s:events.append((n,'switch',s)),_rename=lambda n,s:events.append((n,'rename',s)))
        return host,events
    def test_empty_first_snapshot_becomes_loaded(self):
        h,e=self.host();method('_snapshot_loaded')(h,{})
        self.assertTrue(h.snapshot_ready);self.assertEqual(e,['render'])
    def test_unchanged_snapshot_refreshes_cached_metrics_without_rebuild(self):
        h,e=self.host();h.snapshot_ready=True;method('_snapshot_loaded')(h,{})
        self.assertEqual(e,['sync'])
    def test_inactive_login_switch_dispatches_exact_session(self):
        h,e=self.host();method('_data_action')(h,'switch',{'profile':'Work','session_id':'saved','actions':('switch',)})
        self.assertEqual(e,[('Work','switch','saved')])
    def test_unavailable_action_does_not_dispatch(self):
        h,e=self.host();method('_data_action')(h,'reauth',{'profile':'Work','actions':('rename',)})
        self.assertEqual(e,[])
    def test_mutation_or_closing_blocks_table_action(self):
        for field in ('closing','mutating'):
            h,e=self.host();setattr(h,field,True)
            method('_data_action')(h,'launch',{'profile':'Work','actions':('launch',)})
            self.assertEqual(e,[])
    def test_reauth_remains_the_existing_official_login_path(self):
        h,e=self.host();method('_data_action')(h,'reauth',{'profile':'Work','actions':('reauth',)})
        self.assertEqual(e,[('Work','login',{'reauthenticate':True})])
    def test_table_state_is_captured_before_widgets_are_destroyed(self):
        h,e=self.host();h.table_states={};h.data_tables={'profiles':SimpleNamespace(winfo_exists=lambda:True,get_state=lambda:{'selected':'Work'})}
        method('_remember_tables')(h)
        self.assertEqual(h.table_states['profiles'],{'selected':'Work'})
    def test_settings_subview_is_whitelisted(self):
        h,e=self.host();h.settings_section='general';h._set_page=lambda page:e.append(page)
        method('_set_settings_section')(h,'monitoring')
        self.assertEqual(h.settings_section,'monitoring');self.assertEqual(e,['Settings'])
        method('_set_settings_section')(h,'invalid');self.assertEqual(e,['Settings'])
    def test_diagnostics_subview_is_whitelisted(self):
        h,e=self.host();h.diagnostics_section='runtime';h._set_page=lambda page:e.append(page)
        method('_set_diagnostics_section')(h,'recovery')
        self.assertEqual(h.diagnostics_section,'recovery');self.assertEqual(e,['Diagnostics'])
        method('_set_diagnostics_section')(h,'invalid');self.assertEqual(e,['Diagnostics'])
    def test_usage_subview_is_whitelisted(self):
        h,e=self.host();h.usage_section='history';h._set_page=lambda page:e.append(page)
        method('_set_usage_section')(h,'queue');self.assertEqual(h.usage_section,'queue');self.assertEqual(e,['Usage'])
        method('_set_usage_section')(h,'invalid');self.assertEqual(e,['Usage'])

if __name__=='__main__':unittest.main()
