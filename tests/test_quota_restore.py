import tempfile
import unittest
from pathlib import Path

from multicodex.quota_store import QuotaError, QuotaStore


class QuotaRestoreTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / 'quota'
        self.store = QuotaStore(self.root)
        self.key = self.store.register(
            profile_id='Work', session_id='default', email='one@example.invalid',
            account_id='account-one', workspace_id='workspace-one',
            plan_type='business', seat_type='standard', now=1000)
        self.usage = {
            'source': 'official-app-server',
            'windows': [
                {'label': 'primary', 'used_percent': 20, 'minutes': 300, 'reset_at': 18000},
                {'label': 'secondary', 'used_percent': 40, 'minutes': 10080, 'reset_at': 604800},
            ],
            'reported': {'primary': True, 'secondary': True},
        }

    def test_restore_requires_an_explicit_verified_backup_and_preserves_original(self):
        self.store.capture(self.key, self.usage, observed_at=1100)
        backup = self.store.backup()
        self.store.path.write_bytes(b'damaged')

        with self.assertRaises(QuotaError):
            self.store.restore_from_backup()
        self.assertEqual(self.store.path.read_bytes(), b'damaged')

        preserved = self.store.restore_from_backup(backup)
        self.assertTrue(preserved.is_file())
        self.assertEqual(preserved.read_bytes(), b'damaged')
        restored = QuotaStore(self.root)
        self.assertEqual(restored.latest(self.key)['primary_used_percent'], 20)

    def test_invalid_backup_does_not_replace_or_preserve_original(self):
        self.store.capture(self.key, self.usage, observed_at=1100)
        original = self.store.path.read_bytes()
        bad = self.root / 'bad.sqlite3'
        bad.write_bytes(b'not-a-database')

        with self.assertRaises(QuotaError):
            self.store.restore_from_backup(bad)
        self.assertEqual(self.store.path.read_bytes(), original)
        self.assertEqual(list(self.root.glob('quota.damaged-*.sqlite3')), [])


if __name__ == '__main__':
    unittest.main()
