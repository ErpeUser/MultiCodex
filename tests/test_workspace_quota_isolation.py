"""Workspace mutations require positively matched quota identity and scope."""
import tempfile
import unittest
from pathlib import Path

from multicodex.quota_store import QuotaStore
from multicodex.workspace_admin_api import AdminAPI, AdminContract
from multicodex.workspace_operations import WorkspaceOperations, OperationError
from test_workspace_admin_api import contract
from test_workspace_operations import Provider


class WorkspaceQuotaIsolationTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.provider = Provider()
        self.provider.users['user-a']['account_id'] = 'account-a'
        self.quota = QuotaStore(self.root / 'quota')
        self.ops = WorkspaceOperations(self.root / 'admin',
            AdminAPI(AdminContract(contract()), self.provider), self.quota, clock=lambda: 1000)

    def account(self, identity, workspace='w'):
        key = self.quota.register(profile_id='Work', session_id='default', email='a@example.com',
            account_id=identity, workspace_id=workspace, now=900)
        self.quota.capture(key, {'source': 'official-app-server', 'windows': []}, observed_at=950)
        return key

    def assert_rejected(self, key):
        with self.assertRaises(OperationError) as caught:
            self.ops.prepare('remove_user', 'w', 'synthetic-key', target='user-a', account_key=key)
        self.assertEqual(caught.exception.code, 'ACCOUNT_MISMATCH')
        self.assertEqual(self.provider.writes, [])

    def test_missing_local_account_id_does_not_confirm_provider_identity(self):
        self.assert_rejected(self.account(None))

    def test_missing_provider_account_id_does_not_confirm_local_identity(self):
        self.provider.users['user-a'].pop('account_id')
        self.assert_rejected(self.account('account-a'))

    def test_account_ids_missing_on_both_sides_are_not_a_confirmed_match(self):
        self.provider.users['user-a'].pop('account_id')
        self.assert_rejected(self.account(None))

    def test_unknown_workspace_does_not_supply_evidence_for_a_specific_workspace(self):
        self.assert_rejected(self.account('account-a', workspace=None))

    def test_known_matching_account_and_workspace_allow_review_without_write(self):
        key = self.account('account-a')
        operation = self.ops.prepare('remove_user', 'w', 'synthetic-key',
            target='user-a', account_key=key)
        self.assertEqual(operation['state'], 'REVIEW_REQUIRED')
        self.assertEqual(self.provider.writes, [])


if __name__ == '__main__':
    unittest.main()
