import tempfile
import unittest
from pathlib import Path
from multicodex.profiles import ProfileStore
from multicodex.application import ApplicationServices, user_error
from multicodex.codex_client import CodexError
from helpers.sessions import AuthFixture

class SnapshotRuntime:
    def __init__(self):
        self.scans = 0
        self.fail = False
    def snapshot(self, profiles):
        self.scans += 1
        if self.fail:
            raise OSError('Bearer SECRET-DO-NOT-SHOW')
        return {p.name: {'running': p.name == 'Work', 'pids': [444] if p.name == 'Work' else []} for p in profiles}

class ApplicationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.store = ProfileStore(Path(self.tmp.name)/'profiles')
        for name in ('Work', 'Research', 'Private'):
            self.store.create(name)
        self.runtime = SnapshotRuntime()
        self.app = ApplicationServices(self.store, self.runtime, AuthFixture())

    def test_snapshot_uses_one_process_scan_for_three_profiles(self):
        result = self.app.snapshot()
        self.assertEqual(self.runtime.scans, 1)
        self.assertEqual(result['processes']['Work']['pids'], [444])
        self.assertFalse(result['processes']['Private']['running'])

    def test_process_failure_is_unknown_not_idle_and_contains_no_raw_error(self):
        self.runtime.fail = True
        result = self.app.snapshot()
        self.assertIsNone(result['processes']['Work']['running'])
        self.assertTrue(result['issues'])
        self.assertNotIn('SECRET', str(result))

    def test_corrupt_profile_is_reported_without_hiding_healthy_rows(self):
        (self.store.root/'Work'/'profile.json').write_text('[]')
        result = self.app.snapshot()
        self.assertEqual([p.name for p in result['profiles']], ['Private', 'Research'])
        self.assertTrue(any(i['name'] == 'Work' for i in result['issues']))

    def test_journal_is_visible_as_recovery_not_an_active_session(self):
        self.app.sessions.write_journal('Work', {'version':1, 'old':'default', 'new':'default', 'was_running':True, 'phase':'prepared'})
        result = self.app.snapshot()
        self.assertTrue(result['recovery']['Work'])
        self.assertEqual(result['sessions']['Work'], [])

    def test_unknown_exception_is_never_rendered_verbatim(self):
        rendered = user_error(RuntimeError('access_token=SECRET'))
        self.assertNotIn('SECRET', rendered)
        self.assertNotIn('access_token', rendered)

    def test_cancelled_login_has_distinct_user_visible_outcome(self):
        self.assertNotEqual(user_error(CodexError('CANCELLED')), user_error(CodexError('AUTH_FAILED')))

if __name__ == '__main__':
    unittest.main()

class UsagePresentationTests(unittest.TestCase):
    def test_official_limits_shape_keeps_reset_and_duration(self):
        from multicodex.application import usage_lines
        data = {'source':'official-app-server', 'windows':[{'label':'primary','used_percent':25,'minutes':300,'reset_at':1794528000}]}
        lines = usage_lines(data)
        self.assertTrue(any('25%' in text and '300' in text for text in lines))
        self.assertTrue(any('Reset:' in text for text in lines))

    def test_empty_windows_is_not_zero_usage(self):
        from multicodex.application import usage_lines
        lines = usage_lines({'source':'official-app-server','windows':[]})
        self.assertNotIn('0%', str(lines))
        self.assertTrue(any('keine' in text.casefold() for text in lines))

    def test_unknown_provider_payload_is_not_rendered(self):
        from multicodex.application import usage_lines
        with self.assertRaises(ValueError):
            usage_lines({'token':'SECRET'})
