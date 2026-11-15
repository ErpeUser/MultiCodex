"""Quota bindings must retain the exact account and workspace context."""
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from multicodex.codex_client import AccountIdentity
from multicodex.profiles import ProfileStore
from multicodex.sessions import SessionStore
from multicodex.quota_service import QuotaService
from multicodex.quota_store import QuotaError


class QuotaIsolationTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.profiles = ProfileStore(self.root / 'profiles')
        self.profiles.create('Work')
        self.sessions = SessionStore(self.profiles)
        self.sessions.register('Work', 'default', AccountIdentity('a@example.invalid', 'business', 'a'))
        self.calls = []
        self.mutate = lambda: None
        self.service = QuotaService(self.root,
            SimpleNamespace(store=self.profiles, sessions=self.sessions),
            provider=SimpleNamespace(observe=self.observe), clock=lambda: 1000)

    def observe(self, home, *, expected, cancel, secure):
        self.calls.append(home)
        self.mutate()
        return {'identity': expected.public(), 'observed_at': 1000, 'usage': {
            'source': 'official-app-server', 'account_id': 'a', 'windows': [
                {'label': 'primary', 'used_percent': 20, 'minutes': 300, 'reset_at': 18000}]}}

    def register(self, workspace):
        return self.service.store.register(profile_id='Work', session_id='default',
            email='a@example.invalid', account_id='a', workspace_id=workspace,
            plan_type='business', now=1000)

    def test_single_workspace_candidate_does_not_supply_missing_session_context(self):
        key = self.register('workspace-one')
        model = self.service.work(force_key=key)
        self.assertFalse(model['rows'][0]['binding_available'])
        self.assertEqual(model['issues'], [{'profile': 'Work', 'code': 'WORKSPACE_CONTEXT_REQUIRED'}])
        self.assertEqual(self.calls, [])
        self.assertIsNone(self.service.store.latest(key))

    def test_two_workspaces_with_same_session_and_account_remain_unbound(self):
        self.register('workspace-one')
        self.register('workspace-two')
        model = self.service.work()
        self.assertFalse(any(row['binding_available'] for row in model['rows']))
        self.assertEqual(model['issues'][0]['code'], 'WORKSPACE_CONTEXT_REQUIRED')

    def test_explicit_workspace_binds_only_matching_candidate(self):
        first = self.register('workspace-one')
        second = self.register('workspace-two')
        rows = [{**self.sessions.list('Work')[0], 'workspace_id': 'workspace-two'}]
        with patch.object(self.sessions, 'list', return_value=rows):
            model = self.service.work(force_key=second)
        by_key = {row['account']['account_key']: row for row in model['rows']}
        self.assertFalse(by_key[first]['binding_available'])
        self.assertTrue(by_key[second]['binding_available'])
        self.assertEqual(model['operation']['state'], 'SNAPSHOT_PERSISTED')

    def test_workspace_change_during_provider_request_rejects_late_result(self):
        key = self.register('workspace-one')
        rows = [{**self.sessions.list('Work')[0], 'workspace_id': 'workspace-one'}]
        self.mutate = lambda: rows[0].update(workspace_id='workspace-two')
        with patch.object(self.sessions, 'list', side_effect=lambda name: [dict(rows[0])]):
            model = self.service.work(force_key=key)
        self.assertEqual(model['operation']['error_code'], 'CONTEXT_CHANGED')
        self.assertIsNone(self.service.store.latest(key))

    def test_identity_change_during_provider_request_rejects_late_result(self):
        key = self.register(None)
        self.mutate = lambda: self.sessions.register(
            'Work', 'default', AccountIdentity('b@example.invalid', 'business', 'b'))
        model = self.service.work(force_key=key)
        self.assertEqual(model['operation']['error_code'], 'CONTEXT_CHANGED')
        self.assertIsNone(self.service.store.latest(key))
        self.assertEqual(self.sessions.identity('Work', 'default').account_id, 'b')

    def test_changed_catalogue_email_invalidates_inflight_revision(self):
        key = self.register('workspace-one')
        before = self.service.store.account(key)['context_revision']
        self.service.store.register(profile_id='Work', session_id='default',
            email='renamed@example.invalid', account_id='a', workspace_id='workspace-one',
            plan_type='business', now=1001)
        with self.assertRaises(QuotaError) as caught:
            self.service.store.capture(key, {'source': 'official-app-server', 'windows': []},
                observed_at=1002, expected_revision=before)
        self.assertEqual(caught.exception.code, 'CONTEXT_CHANGED')


if __name__ == '__main__':
    unittest.main()
