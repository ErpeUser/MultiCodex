"""Real Tk widgets on an isolated display; no provider or production accounts."""
import importlib
import importlib.util
import os
import unittest
import tkinter as tk
from multicodex.automation_settings import DEFAULTS


def fixture_model():
    return {'settings':{**DEFAULTS,'allowed_profiles':['Work']},'profiles':['Work','Other'],
        'rows':[{'account':{'account_key':'a'*64,'profile_id':'Work','email':'sample@example.invalid',
                           'workspace_id':None,'plan_type':'business','membership_state':'ACCESS_REMOVED',
                           'last_error_code':None,'auth_state':'AUTHENTICATED'},
                 'binding_available':True,'polling':{'suspended':False},
                 'quota':{'status':'ACCESS_REMOVED','freshness':'CACHED','observed_at':1000,
                          'capacity_confirmed':False,'next_reset_at':604800,'max_used_percent':100,
                          'windows':[{'slot':'primary','kind':'five_hour','used_percent':100,'remaining_percent':0,
                                      'state':'RESET_TIME_REACHED','reset_at':18000,'reset_in_seconds':0},
                                     {'slot':'secondary','kind':'weekly','used_percent':64,'remaining_percent':36,
                                      'state':'AVAILABLE','reset_at':604800,'reset_in_seconds':500000}]}}]}


@unittest.skipUnless(os.environ.get('DISPLAY') or os.name=='nt','A real Tk display is required')
class WidgetTests(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(importlib.util.find_spec('multicodex.quota_ui'),'Quota widgets are missing')
        self.mod=importlib.import_module('multicodex.quota_ui')
        self.root=tk.Tk();self.root.geometry('900x640');self.addCleanup(self.root.destroy)
        self.calls=[]
        self.panel=self.mod.QuotaPanel(self.root,theme='dark',on_refresh=self.calls.append,
            on_history=lambda *args:None)
        self.panel.pack(fill='both',expand=True,padx=16,pady=16)
        self.panel.set_model(fixture_model());self.root.update()
    def test_removed_account_keeps_historical_percent_and_unverified_reset(self):
        self.assertEqual(len(self.panel.table.get_children()),1)
        self.panel.table.selection_set('a'*64);self.panel.select_row()
        self.assertIn('100',self.panel.primary.value_label.cget('text'))
        self.assertIn('best',self.panel.primary.reset_label.cget('text'))
        self.assertEqual(str(self.panel.refresh_button.cget('state')),'disabled')
    def test_search_filters_without_destroying_input(self):
        self.panel.query.set('no match');self.panel.refresh_rows()
        self.assertEqual(self.panel.table.get_children(),())
        self.assertEqual(self.panel.query.get(),'no match')
        self.panel.query.set('SAMPLE');self.panel.refresh_rows()
        self.assertEqual(len(self.panel.table.get_children()),1)
    def test_unknown_data_does_not_display_fabricated_zero(self):
        model=fixture_model();model['rows'][0]['quota']['windows']=[]
        self.panel.set_model(model);self.panel.table.selection_set('a'*64);self.panel.select_row()
        self.assertEqual(self.panel.primary.value_label.cget('text'),'Unbekannt')
    def test_refresh_calls_exact_selected_key(self):
        model=fixture_model();model['rows'][0]['account']['membership_state']='WORKSPACE_ACCESS_UNKNOWN'
        model['rows'][0]['quota']['status']='VERIFIED_AVAILABLE'
        self.panel.set_model(model);self.panel.table.selection_set('a'*64);self.panel.select_row()
        self.panel.refresh_button.invoke()
        self.assertEqual(self.calls,['a'*64])
    def test_update_keeps_user_filter_and_selection(self):
        self.panel.query.set('Work');self.panel.refresh_rows();self.panel.table.selection_set('a'*64)
        self.panel.set_model(fixture_model())
        self.assertEqual(self.panel.query.get(),'Work')
        self.assertEqual(self.panel.table.selection(),('a'*64,))
    def test_settings_save_validates_before_callback(self):
        saved=[];settings=self.mod.QuotaSettingsPanel(self.root,theme='light',model=fixture_model(),on_save=saved.append)
        settings.interval.set('0');settings.save()
        self.assertEqual(saved,[])
        settings.interval.set('120');settings.enabled.set(True);settings.save()
        self.assertEqual(saved[0]['poll_interval_seconds'],120)
        self.assertTrue(saved[0]['enabled'])
        self.assertFalse(saved[0]['automatic_activation_enabled'])
        settings.destroy()
    def test_small_window_toolbar_actions_remain_inside_panel(self):
        self.root.geometry('680x650');self.root.update()
        right=self.panel.refresh_button.winfo_rootx()+self.panel.refresh_button.winfo_width()
        self.assertLessEqual(right,self.panel.winfo_rootx()+self.panel.winfo_width()+1)
    def test_table_uses_readable_compact_usage_with_status_kept_separate(self):
        value=self.panel.table.item('a'*64,'values')[1]
        self.assertEqual(value,'100 %')
        self.assertIn('best',self.panel.primary.reset_label.cget('text'))
        self.assertEqual(self.panel.primary.value_label.cget('text'),'100 %')

    def test_disabled_refresh_is_not_styled_as_an_available_primary_action(self):
        self.assertEqual(str(self.panel.refresh_button.cget('state')),'disabled')
        self.assertNotEqual(self.panel.refresh_button.cget('background'),self.panel.palette['accent'])
        model=fixture_model();model['rows'][0]['account']['membership_state']='WORKSPACE_ACCESS_UNKNOWN'
        self.panel.set_model(model)
        self.assertEqual(self.panel.refresh_button.cget('background'),self.panel.palette['accent'])

    def test_reselected_account_is_scrolled_into_view_after_refresh(self):
        from copy import deepcopy
        model=fixture_model()
        original=model['rows'][0]
        model['rows']=[]
        for i in range(30):
            row=deepcopy(original);row['account']['account_key']=f'{i:064x}'
            row['account']['email']=f'user{i:02d}@example.invalid';model['rows'].append(row)
        self.panel.set_model(model)
        target=f'{29:064x}';self.panel.table.selection_set(target);self.panel.select_row()
        self.panel.set_model(model);self.root.update()
        self.assertTrue(self.panel.table.bbox(target),'Selected account was outside the visible table')

    def test_history_pagination_is_visible_in_small_window(self):
        self.panel.show_history('a'*64,[],0)
        window=self.panel.history_window;window.geometry('680x360');self.root.update()
        buttons=[]
        def visit(parent):
            for child in parent.winfo_children():
                if isinstance(child,tk.Button):buttons.append(child)
                visit(child)
        visit(window)
        self.assertEqual(len(buttons),2)
        for button in buttons:
            self.assertTrue(button.winfo_ismapped())
            self.assertLessEqual(button.winfo_rooty()+button.winfo_height(),window.winfo_rooty()+window.winfo_height())

    def test_light_theme_uses_same_account_data(self):
        other=self.mod.QuotaPanel(self.root,theme='light',on_refresh=self.calls.append,on_history=lambda *a:None)
        other.set_model(fixture_model())
        self.assertEqual(len(other.table.get_children()),1)
        other.destroy()

if __name__=='__main__':unittest.main()
