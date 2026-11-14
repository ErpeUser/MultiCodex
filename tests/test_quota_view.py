import importlib
import importlib.util
import unittest

class ViewTests(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(importlib.util.find_spec('multicodex.quota_view'),'Quota view models are missing')
        self.mod=importlib.import_module('multicodex.quota_view')
        self.rows=[{'account':{'account_key':'a','email':'a@example.invalid','profile_id':'Work','membership_state':'ACCESS_REMOVED'},
                    'quota':{'status':'ACCESS_REMOVED','freshness':'CACHED','capacity_confirmed':False,'windows':[], 'next_reset_at':2000}},
                   {'account':{'account_key':'b','email':'b@example.invalid','profile_id':'Private','membership_state':'WORKSPACE_ACCESS_UNKNOWN'},
                    'quota':{'status':'QUOTA_WARNING','freshness':'LIVE_VERIFIED','capacity_confirmed':True,'windows':[], 'next_reset_at':1500}}]
    def test_search_and_removed_filter_keep_historical_accounts(self):
        result=self.mod.filter_rows(self.rows,query='WORK',status='removed')
        self.assertEqual([r['account']['account_key'] for r in result],['a'])
    def test_warning_filter_does_not_hide_unknown_values_as_healthy(self):
        self.assertEqual(len(self.mod.filter_rows(self.rows,status='warning')),1)
        self.assertEqual(len(self.mod.filter_rows(self.rows,status='check')),1)
    def test_sort_by_reset_uses_numeric_timestamps_not_localized_text(self):
        rows=self.mod.filter_rows(self.rows,sort_by='reset')
        self.assertEqual([r['account']['account_key'] for r in rows],['b','a'])
    def test_summary_counts_unknown_and_removed_without_fabricating_capacity(self):
        summary=self.mod.summarize_rows(self.rows)
        self.assertEqual(summary['accounts'],2)
        self.assertEqual(summary['needs_check'],1)
        self.assertEqual(summary['removed'],1)
        self.assertEqual(summary['live'],1)
    def test_omitted_window_is_not_rendered_as_zero(self):
        self.assertEqual(self.mod.window_text(None),'Unbekannt')
    def test_historical_reset_is_explicitly_unverified(self):
        value={'used_percent':100,'state':'RESET_TIME_REACHED'}
        self.assertIn('100',self.mod.window_text(value))
        self.assertIn('Pr',self.mod.window_text(value))
    def test_absent_window_is_not_called_unlimited(self):
        self.assertEqual(self.mod.window_text({'state':'NOT_REPORTED'}),'Nicht gemeldet')

    def test_explicit_absent_five_hour_window_remains_not_reported(self):
        windows=[{'kind':'not_reported','state':'NOT_REPORTED'},
                 {'kind':'weekly','state':'AVAILABLE','used_percent':20}]
        result=self.mod.display_windows(windows)
        self.assertEqual(result['five_hour']['state'],'NOT_REPORTED')
        self.assertEqual(result['weekly']['used_percent'],20)

    def test_unrecognized_duration_does_not_turn_other_window_into_unlimited(self):
        result=self.mod.display_windows([{'kind':'other','state':'UNKNOWN'},
                                        {'kind':'not_reported','state':'NOT_REPORTED'}])
        self.assertIsNone(result.get('five_hour'))
        self.assertIsNone(result.get('weekly'))

if __name__=='__main__':unittest.main()
