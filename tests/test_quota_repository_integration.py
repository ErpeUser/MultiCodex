"""New quota code against unchanged, blob-verified upstream profile/session code.

Only the external Codex provider is simulated. No login, OS keyring or Desktop
process is used. Every profile and catalogue is created in a temporary directory.
"""
from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest

from multicodex.codex_client import AccountIdentity
from multicodex.profiles import ProfileStore
from multicodex.sessions import SessionStore
from multicodex.quota_service import QuotaService


class RepositoryIntegrationTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.profiles = ProfileStore(self.root / 'profiles')
        self.profiles.create('Work')
        self.sessions = SessionStore(self.profiles)
        self.identity = AccountIdentity('one@example.invalid', 'business', 'one')
        self.sessions.register('Work', 'default', self.identity)
        self.calls = []
        self.app = SimpleNamespace(store=self.profiles, sessions=self.sessions)
        self.provider = SimpleNamespace(observe=self.observe)
        self.service = QuotaService(self.root, self.app, provider=self.provider, clock=lambda: 1000)

    def observe(self, home, *, expected, cancel, secure):
        self.assertTrue(secure)
        self.assertFalse((home / 'auth.json').exists())
        self.calls.append(home)
        return {'identity': expected.public(), 'observed_at': 1000, 'usage': {
            'source': 'official-app-server', 'account_id': expected.account_id,
            'ordinary_usage_allowed': True, 'spend_control_reached': False,
            'windows': [{'label': 'primary', 'used_percent': 25, 'minutes': 300, 'reset_at': 18000},
                        {'label': 'secondary', 'used_percent': 65, 'minutes': 10080, 'reset_at': 604800}]}}

    def key(self):
        return self.service.work()['rows'][0]['account']['account_key']

    def test_refresh_uses_existing_secure_auth_home_without_rewriting_profile(self):
        meta = self.profiles.get('Work').home / 'profile.json'
        before = meta.read_bytes()
        key = self.key()
        model = self.service.work(force_key=key)
        self.assertEqual(self.calls, [self.profiles.get('Work').codex_home])
        self.assertTrue(model['rows'][0]['quota']['capacity_confirmed'])
        self.assertEqual(meta.read_bytes(), before)
        self.assertEqual(self.profiles.get('Work').session_id, 'default')

    def test_history_survives_independent_service_reopen(self):
        key = self.key()
        self.service.work(force_key=key)
        second = QuotaService(self.root, self.app, provider=self.provider, clock=lambda: 1000)
        model = second.work()
        self.assertEqual(model['rows'][0]['snapshot']['secondary_used_percent'], 65)
        self.assertEqual(len(self.calls), 1)

    def test_saved_sessions_are_observed_without_switching_active_session(self):
        sid, home = self.sessions.prepare('Work')
        self.sessions.register('Work', sid, AccountIdentity('two@example.invalid', 'business', 'two'))
        rows = self.service.work()['rows']
        target = next(row for row in rows if row['account']['account_id'] == 'two')
        self.service.work(force_key=target['account']['account_key'])
        self.assertEqual(self.calls, [home])
        self.assertEqual(self.profiles.get('Work').session_id, 'default')

    def test_pending_original_session_journal_prevents_provider_call(self):
        key = self.key()
        self.sessions.write_journal('Work', {'version': 1, 'old': 'default', 'new': 'default',
                                           'was_running': False, 'phase': 'prepared'})
        model = self.service.work(force_key=key)
        self.assertEqual(self.calls, [])
        self.assertEqual(model['operation']['error_code'], 'BUSY')
        self.assertIsNotNone(self.sessions.journal('Work'))

    def test_plaintext_fallback_is_rejected_without_reading_or_deleting_it(self):
        key = self.key()
        unsafe = self.profiles.get('Work').codex_home / 'auth.json'
        unsafe.write_text('SENTINEL_NOT_A_REAL_TOKEN')
        model = self.service.work(force_key=key)
        self.assertEqual(self.calls, [])
        self.assertIsNone(model['rows'][0]['snapshot'])
        self.assertEqual(unsafe.read_text(), 'SENTINEL_NOT_A_REAL_TOKEN')
        self.assertNotIn('SENTINEL_NOT_A_REAL_TOKEN', str(model))

    def test_corrupt_profile_is_reported_instead_of_being_a_healthy_empty_catalogue(self):
        key = self.key()
        self.service.work(force_key=key)
        meta = self.profiles.get('Work').home / 'profile.json'
        meta.write_text('invalid metadata')
        model = self.service.work()
        self.assertEqual(len(model['rows']), 1)
        self.assertFalse(model['rows'][0]['binding_available'])
        self.assertTrue(model['issues'])
        self.assertEqual(meta.read_text(), 'invalid metadata')

    def test_access_removed_preserves_snapshot_and_stops_background_calls(self):
        key = self.key()
        self.service.work(force_key=key)
        self.service.store.record_access(key, 'ACCESS_REMOVED', now=1000)
        self.service.save_settings({'enabled': True, 'allowed_profiles': ['Work']})
        model = self.service.work()
        self.assertEqual(len(self.calls), 1)
        self.assertEqual(model['rows'][0]['snapshot']['primary_used_percent'], 25)
        self.assertEqual(model['rows'][0]['quota']['status'], 'ACCESS_REMOVED')

    def test_catalogue_identity_replacement_keeps_old_history_unbound(self):
        key = self.key()
        self.service.work(force_key=key)
        self.sessions.register('Work', 'default', AccountIdentity('two@example.invalid', 'business', 'two'))
        rows = self.service.work()['rows']
        old = next(row for row in rows if row['account']['account_key'] == key)
        self.assertFalse(old['binding_available'])
        self.assertEqual(old['snapshot']['secondary_used_percent'], 65)
        self.assertEqual(len(rows), 2)


if __name__ == '__main__':
    unittest.main()
