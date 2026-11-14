"""Reset forecasts are not new quota, and both reported windows are considered."""
import importlib
import importlib.util
import unittest


class QuotaDecisionTests(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(importlib.util.find_spec('multicodex.quota'), 'Quota evaluator is not implemented')
        self.evaluate = importlib.import_module('multicodex.quota').evaluate_snapshot
        self.account = {'membership_state': 'WORKSPACE_MEMBER', 'auth_state':'AUTHENTICATED',
                        'last_error_code':None, 'plan_type':'business', 'seat_type':'standard'}
        self.snapshot = {'observed_at':1000,'source':'official-app-server','plan_type':'business','seat_type':'standard',
            'primary_present':True,'primary_used_percent':20,'primary_duration_minutes':300,'primary_reset_at':1100,
            'secondary_present':True,'secondary_used_percent':64,'secondary_duration_minutes':10080,'secondary_reset_at':2000,
            'ordinary_usage_allowed': True, 'spend_control_reached':False, 'rate_limit_reached_type':None}

    def run_view(self, now=1050, **changes):
        return self.evaluate({**self.snapshot, **changes}, self.account, now=now)

    def test_two_live_windows_are_available(self):
        view=self.run_view()
        self.assertEqual(view['status'],'VERIFIED_AVAILABLE')
        self.assertTrue(view['capacity_confirmed'])
        self.assertEqual(view['windows'][0]['remaining_percent'],80)

    def test_weekly_exhaustion_blocks_even_with_five_hour_capacity(self):
        view=self.run_view(secondary_used_percent=100)
        self.assertEqual(view['status'],'QUOTA_EXHAUSTED')
        self.assertFalse(view['capacity_confirmed'])

    def test_warning_threshold_is_configurable(self):
        snap={**self.snapshot,'primary_used_percent':85}
        view=self.evaluate(snap,self.account,now=1050,warning_threshold_percent=80)
        self.assertEqual(view['status'],'QUOTA_WARNING')
        self.assertTrue(view['capacity_confirmed'])

    def test_reset_boundary_is_forecast_and_keeps_last_usage(self):
        view=self.run_view(now=1100,primary_used_percent=100)
        self.assertEqual(view['status'],'VERIFICATION_REQUIRED')
        self.assertEqual(view['windows'][0]['state'],'RESET_TIME_REACHED')
        self.assertEqual(view['windows'][0]['used_percent'],100)
        self.assertEqual(view['windows'][0]['remaining_percent'],0)
        self.assertEqual(view['windows'][1]['reset_in_seconds'],900)
        self.assertFalse(view['capacity_confirmed'])

    def test_offline_never_rolls_timestamps_forward(self):
        self.account['membership_state']='ACCESS_REMOVED'
        view=self.run_view(now=900000)
        self.assertEqual(view['status'],'ACCESS_REMOVED')
        self.assertEqual(view['windows'][0]['reset_at'],1100)
        self.assertEqual(view['windows'][1]['reset_at'],2000)
        self.assertFalse(view['capacity_confirmed'])

    def test_restore_access_requires_observation_after_change(self):
        self.account['access_changed_at']=1040
        self.assertEqual(self.run_view()['status'],'VERIFICATION_REQUIRED')
        self.assertFalse(self.run_view(observed_at=1040)['capacity_confirmed'])
        self.assertTrue(self.run_view(observed_at=1045)['capacity_confirmed'])

    def test_expired_session_is_not_usable(self):
        self.account['auth_state']='SESSION_EXPIRED'
        self.assertEqual(self.run_view()['status'],'AUTHENTICATION_REQUIRED')

    def test_failed_refresh_marks_cached_not_live(self):
        self.account.update(last_error_code='TIMEOUT',last_error_at=1020)
        view=self.run_view()
        self.assertEqual(view['freshness'],'CACHED')
        self.assertFalse(view['capacity_confirmed'])

    def test_stale_snapshot_is_not_available(self):
        view=self.run_view(now=1201,primary_reset_at=18000)
        self.assertEqual(view['freshness'],'STALE')
        self.assertFalse(view['capacity_confirmed'])

    def test_future_observation_is_not_trusted(self):
        view=self.run_view(now=999)
        self.assertEqual(view['status'],'UNKNOWN')
        self.assertFalse(view['capacity_confirmed'])

    def test_missing_value_is_not_zero(self):
        view=self.run_view(primary_used_percent=None)
        self.assertEqual(view['status'],'UNKNOWN')
        self.assertIsNone(view['windows'][0]['remaining_percent'])

    def test_unknown_window_blocks_but_explicit_null_is_not_invented(self):
        a=self.run_view(primary_present=None,primary_used_percent=None,primary_duration_minutes=None,primary_reset_at=None)
        b=self.run_view(primary_present=False,primary_used_percent=None,primary_duration_minutes=None,primary_reset_at=None)
        self.assertFalse(a['capacity_confirmed'])
        self.assertTrue(b['capacity_confirmed'])
        self.assertEqual(b['windows'][0]['state'],'NOT_REPORTED')

    def test_all_absent_windows_are_not_unlimited(self):
        view=self.run_view(primary_present=False,secondary_present=False)
        self.assertFalse(view['capacity_confirmed'])

    def test_duration_not_position_identifies_window(self):
        view=self.run_view(primary_duration_minutes=10080,secondary_duration_minutes=300)
        self.assertEqual([w['kind'] for w in view['windows']],['weekly','five_hour'])

    def test_unknown_duration_does_not_become_five_hour(self):
        view=self.run_view(primary_duration_minutes=15)
        self.assertEqual(view['windows'][0]['kind'],'other')
        self.assertFalse(view['capacity_confirmed'])

    def test_missing_reset_requires_verification(self):
        self.assertFalse(self.run_view(primary_reset_at=None)['capacity_confirmed'])

    def test_plan_or_seat_change_requires_new_snapshot(self):
        self.account['seat_type']='codex-only'
        self.assertEqual(self.run_view()['status'],'VERIFICATION_REQUIRED')

    def test_spend_control_or_provider_denial_overrides_percentages(self):
        for changes in [{'ordinary_usage_allowed':False},{'spend_control_reached':True},
                        {'rate_limit_reached_type':'UNKNOWN_PROVIDER_LIMIT'}]:
            with self.subTest(changes=changes):
                self.assertFalse(self.run_view(**changes)['capacity_confirmed'])
                self.assertEqual(self.run_view(**changes)['status'],'QUOTA_EXHAUSTED')

    def test_new_official_snapshot_corrects_forecast(self):
        view=self.run_view(now=1150,observed_at=1140,primary_used_percent=0,primary_reset_at=19140)
        self.assertTrue(view['capacity_confirmed'])
        self.assertEqual(view['windows'][0]['remaining_percent'],100)

    def test_unavailable_backend_permission_does_not_confirm_capacity(self):
        for permission in (None,'true',1):
            with self.subTest(permission=permission):
                view=self.run_view(ordinary_usage_allowed=permission)
                self.assertFalse(view['capacity_confirmed'])
                self.assertNotEqual(view['status'],'VERIFIED_AVAILABLE')
                self.assertEqual(view['windows'][0]['used_percent'],20)

    def test_no_snapshot_is_unknown(self):
        self.assertEqual(self.evaluate(None,self.account,now=1050)['status'],'UNKNOWN')

if __name__=='__main__':
    unittest.main()
