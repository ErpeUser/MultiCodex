"""Credential-free history must survive access changes and interrupted reads."""
import importlib
import importlib.util
import json
from contextlib import closing
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path


class QuotaStoreTests(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(importlib.util.find_spec('multicodex.quota_store'),
                             'Persistent quota store is not implemented')
        self.module = importlib.import_module('multicodex.quota_store')
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / 'quota'
        self.store = self.module.QuotaStore(self.root)
        self.key = self.store.register(profile_id='Work', session_id='default',
            email='one@example.invalid', account_id='account-one', workspace_id='workspace-one',
            plan_type='business', seat_type='standard', now=1000)

    def usage(self, value=100, reset=18000):
        return {'source': 'official-app-server', 'windows': [
            {'label': 'primary', 'used_percent': value, 'minutes': 300, 'reset_at': reset},
            {'label': 'secondary', 'used_percent': 64, 'minutes': 10080, 'reset_at': 604800}],
            'reported': {'primary': True, 'secondary': True}}

    def capture(self, **kwargs):
        return self.store.capture(self.key, self.usage(), observed_at=1100, **kwargs)

    def test_snapshot_survives_store_reopen_and_access_removed(self):
        snap = self.capture()
        self.store.record_access(self.key, 'ACCESS_REMOVED', now=1200)
        other = self.module.QuotaStore(self.root)
        self.assertEqual(other.latest(self.key)['snapshot_id'], snap['snapshot_id'])
        self.assertEqual(other.latest(self.key)['primary_used_percent'], 100)
        self.assertEqual(other.accounts()[0]['membership_state'], 'ACCESS_REMOVED')
        self.assertEqual(len(other.history(self.key)), 1)

    def test_failed_refresh_preserves_values_and_records_redacted_code(self):
        self.capture()
        self.store.record_failure(self.key, 'TIMEOUT', now=1300)
        self.assertEqual(self.store.latest(self.key)['observed_at'], 1100)
        self.assertEqual(self.store.accounts()[0]['last_error_code'], 'TIMEOUT')
        with self.assertRaises(self.module.QuotaError):
            self.store.record_failure(self.key, 'secret raw exception', now=1301)

    def test_workspace_context_is_not_merged(self):
        second = self.store.register(profile_id='Work', session_id='default',
            email='one@example.invalid', account_id='account-one', workspace_id='workspace-two',
            plan_type='business', now=1001)
        self.capture()
        self.assertNotEqual(second, self.key)
        self.assertIsNone(self.store.latest(second))

    def test_registration_relogin_preserves_known_account_history(self):
        self.capture()
        key = self.store.register(profile_id='Work', session_id='a' * 32,
            email='ONE@example.invalid', account_id='account-one', workspace_id='workspace-one',
            plan_type='business', now=1300)
        self.assertEqual(key, self.key)
        self.assertEqual(self.store.latest(key)['primary_reset_at'], 18000)

    def test_unknown_workspace_sessions_are_not_silently_merged(self):
        a = self.store.register(profile_id='Other', session_id='a'*32,
            email='one@example.invalid', account_id=None, now=1000)
        b = self.store.register(profile_id='Other', session_id='b'*32,
            email='one@example.invalid', account_id=None, now=1000)
        self.assertNotEqual(a,b)

    def test_unknown_fields_never_persist_secrets(self):
        payload = self.usage()
        payload['access_token'] = 'SENTINEL_NOT_TO_PERSIST'
        self.store.capture(self.key, payload, observed_at=1100)
        self.assertNotIn(b'SENTINEL_NOT_TO_PERSIST', self.store.path.read_bytes())

    def test_nan_boolean_and_out_of_range_are_rejected(self):
        for value in [float('nan'), float('inf'), True, -1, 1001, '100']:
            with self.subTest(value=value), self.assertRaises(self.module.QuotaError):
                self.store.capture(self.key, self.usage(value), observed_at=1100)
        self.assertIsNone(self.store.latest(self.key))

    def test_explicitly_absent_window_differs_from_unknown_window(self):
        data = {'source': 'official-app-server', 'windows': [],
                'reported': {'primary': False, 'secondary': None}}
        snap = self.store.capture(self.key, data, observed_at=1100)
        self.assertIs(snap['primary_present'], False)
        self.assertIsNone(snap['secondary_present'])
        self.assertIsNone(snap['primary_used_percent'])

    def test_out_of_order_observation_does_not_replace_latest(self):
        self.store.capture(self.key, self.usage(20), observed_at=2000)
        self.store.capture(self.key, self.usage(90), observed_at=1000)
        self.assertEqual(self.store.latest(self.key)['primary_used_percent'], 20)
        self.assertEqual(len(self.store.history(self.key)), 2)

    def test_plan_change_is_recorded_without_destroying_history(self):
        self.capture()
        self.store.register(profile_id='Work', session_id='default',
            email='one@example.invalid', account_id='account-one', workspace_id='workspace-one',
            plan_type='pro', now=1200)
        self.store.capture(self.key, self.usage(0), observed_at=1300)
        plans = {s['plan_type'] for s in self.store.history(self.key)}
        self.assertEqual(plans, {'business', 'pro'})

    def test_access_removed_requires_existing_snapshot(self):
        with self.assertRaises(self.module.QuotaError):
            self.store.prepare_removal(self.key)
        self.capture()
        self.assertEqual(self.store.prepare_removal(self.key)['primary_used_percent'], 100)

    def test_concurrent_writers_keep_every_snapshot(self):
        self.capture()
        def write(i):
            return self.module.QuotaStore(self.root).capture(self.key, self.usage(i), observed_at=2000+i)
        with ThreadPoolExecutor(max_workers=4) as pool:
            list(pool.map(write,range(12)))
        self.assertEqual(len(self.store.history(self.key)),13)

    def test_backup_is_valid_and_corrupt_original_is_not_overwritten(self):
        self.capture()
        backup = self.store.backup()
        before = backup.read_bytes()
        self.store.path.write_bytes(b'broken-db')
        with self.assertRaises(self.module.QuotaError):
            self.module.QuotaStore(self.root).accounts()
        self.assertEqual(self.store.path.read_bytes(), b'broken-db')
        self.assertEqual(backup.read_bytes(), before)

    def test_database_symlink_is_refused(self):
        other = Path(self.temp.name)/'external'
        other.write_bytes(b'valuable')
        root=Path(self.temp.name)/'redirect';root.mkdir()
        try:
            (root/'quota.sqlite3').symlink_to(other)
        except (OSError,NotImplementedError):
            self.skipTest('Host cannot create symlinks')
        with self.assertRaises(self.module.QuotaError):
            self.module.QuotaStore(root)
        self.assertEqual(other.read_bytes(),b'valuable')

    def test_late_success_cannot_clear_a_newer_authentication_failure(self):
        self.capture()
        self.store.record_failure(self.key, 'NOT_AUTHENTICATED', now=1500)
        self.store.capture(self.key, self.usage(30), observed_at=1200)
        row = self.store.account(self.key)
        self.assertEqual(row['auth_state'], 'SESSION_EXPIRED')
        self.assertEqual(row['last_error_code'], 'NOT_AUTHENTICATED')

    def test_missing_database_backup_does_not_replace_valid_backup(self):
        self.capture()
        backup = self.store.backup()
        original = backup.read_bytes()
        self.store.path.unlink()
        with self.assertRaises(self.module.QuotaError):
            self.store.backup()
        self.assertEqual(backup.read_bytes(), original)
        self.assertFalse(self.store.path.exists())

    def test_corrupt_metadata_cannot_escape_as_a_successful_record(self):
        import sqlite3
        with closing(sqlite3.connect(self.store.path)) as db, db:
            db.execute('UPDATE accounts SET record=?', ('[]',))
        with self.assertRaises(self.module.QuotaError):
            self.store.accounts()

    def test_backup_closes_both_database_connections(self):
        import gc
        import warnings
        gc.collect()
        self.capture()
        with warnings.catch_warnings(record=True) as seen:
            warnings.simplefilter('always', ResourceWarning)
            self.store.backup()
            gc.collect()
        self.assertFalse([item for item in seen if issubclass(item.category, ResourceWarning)])

    def test_corrupt_account_fields_are_rejected_before_rendering(self):
        import sqlite3
        original=self.store.account(self.key)
        for changes in ({'email':[]},{'membership_state':'SENTINEL_RAW'},
                        {'next_probe_at':'tomorrow'},{'probe_suspended':'false'},
                        {'context_revision':True},{'access_token':'SENTINEL_SECRET'}):
            with self.subTest(changes=changes):
                with closing(sqlite3.connect(self.store.path)) as db,db:
                    db.execute('UPDATE accounts SET record=?',(json.dumps({**original,**changes}),))
                with self.assertRaises(self.module.QuotaError):self.store.accounts()

    def test_corrupt_snapshot_scope_is_not_returned_as_another_account_history(self):
        import sqlite3
        snap=self.capture()
        payload={**snap,'account_key':'b'*64}
        with closing(sqlite3.connect(self.store.path)) as db,db:
            db.execute('UPDATE snapshots SET payload=?',(json.dumps(payload),))
        with self.assertRaises(self.module.QuotaError):self.store.latest(self.key)
        with self.assertRaises(self.module.QuotaError):self.store.history(self.key)

    def test_corrupt_snapshot_values_do_not_escape_to_ui(self):
        import sqlite3
        snap=self.capture()
        for changes in ({'primary_used_percent':True},{'primary_reset_at':'soon'},
                        {'source':'untrusted'},{'refresh_token':'SENTINEL_SECRET'}):
            with self.subTest(changes=changes):
                with closing(sqlite3.connect(self.store.path)) as db,db:
                    db.execute('UPDATE snapshots SET payload=?',(json.dumps({**snap,**changes}),))
                with self.assertRaises(self.module.QuotaError):self.store.latest(self.key)

    def test_future_schema_is_refused_without_reset(self):
        import sqlite3
        with closing(sqlite3.connect(self.store.path)) as db, db:
            db.execute('PRAGMA user_version = 99')
        with self.assertRaises(self.module.QuotaError):
            self.module.QuotaStore(self.root)
        with closing(sqlite3.connect(self.store.path)) as db, db:
            self.assertEqual(db.execute('PRAGMA user_version').fetchone()[0],99)

if __name__ == '__main__':
    unittest.main()
