import tempfile
import json
import os
import sqlite3
import subprocess
import sys
import threading
import time
import unittest
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from pathlib import Path
from unittest.mock import patch

from multicodex.quota_store import QuotaError, QuotaStore
from multicodex.locks import BusyError, FileLock


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

    def _capture_while_operation_waits(self, operation):
        script = '''import json, sys
from multicodex.quota_store import QuotaStore
s = QuotaStore(sys.argv[1])
with s._storage_guard():
    print("held", flush=True)
    sys.stdin.readline()
    s.capture(sys.argv[2], json.loads(sys.argv[3]), observed_at=1200)
'''
        child = subprocess.Popen([sys.executable, '-c', script, str(self.root), self.key,
            json.dumps(self.usage)], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            stderr=subprocess.PIPE, text=True)
        try:
            self.assertEqual(child.stdout.readline().strip(), 'held')
            contended = threading.Event()
            enter = FileLock.__enter__
            def enter_and_signal(lock):
                try:
                    return enter(lock)
                except BusyError:
                    contended.set()
                    raise
            with patch.object(FileLock, '__enter__', enter_and_signal):
                with ThreadPoolExecutor(max_workers=1) as executor:
                    future = executor.submit(operation)
                    try:
                        self.assertTrue(contended.wait(3), 'Operation did not use the shared OS lock')
                        self.assertFalse(future.done())
                    finally:
                        output, error = child.communicate('\n', timeout=5)
                    result = future.result(timeout=5)
            self.assertEqual(child.returncode, 0, error)
            return result
        finally:
            if child.poll() is None:
                child.communicate('\n', timeout=5)

    def test_backup_waits_for_capture_in_another_process(self):
        self.store.capture(self.key, self.usage, observed_at=1100)
        backup = self._capture_while_operation_waits(self.store.backup)
        with closing(sqlite3.connect(backup)) as db:
            self.assertEqual(db.execute('SELECT count(*) FROM snapshots').fetchone()[0], 2)
            self.assertEqual(db.execute('PRAGMA quick_check').fetchone()[0], 'ok')

    def test_restore_waits_for_capture_and_preserves_committed_database(self):
        self.store.capture(self.key, self.usage, observed_at=1100)
        backup = self.store.backup()
        preserved = self._capture_while_operation_waits(lambda: self.store.restore_from_backup(backup))
        with closing(sqlite3.connect(preserved)) as db:
            self.assertEqual(db.execute('SELECT count(*) FROM snapshots').fetchone()[0], 2)
        reopened = QuotaStore(self.root)
        self.assertEqual(len(reopened.history(self.key)), 1)
        self.assertEqual(reopened.latest(self.key)['observed_at'], 1100)

    def test_changed_backup_during_copy_preserves_current_database(self):
        import shutil
        self.store.capture(self.key, self.usage, observed_at=1100)
        backup = self.store.backup()
        before = self.store.path.read_bytes()
        copy = shutil.copyfileobj
        def mutate_source(source, target):
            copy(source, target)
            if Path(source.name) == backup:
                with backup.open('ab') as stream:
                    stream.write(b'changed while copying')
        with patch('multicodex.quota_store.shutil.copyfileobj', side_effect=mutate_source):
            with self.assertRaises(QuotaError) as caught:
                self.store.restore_from_backup(backup)
        self.assertEqual(caught.exception.code, 'STORAGE')
        self.assertEqual(self.store.path.read_bytes(), before)
        self.assertEqual(list(self.root.glob('quota.damaged-*')), [])

    def test_interrupted_final_replace_keeps_database_reopenable(self):
        self.store.capture(self.key, self.usage, observed_at=1100)
        backup = self.store.backup()
        self.store.capture(self.key, self.usage, observed_at=1200)
        before = self.store.path.read_bytes()
        replace = os.replace
        def fail_final(source, destination):
            if Path(destination) == self.store.path:
                raise PermissionError('Synthetic Windows sharing violation')
            return replace(source, destination)
        with patch('multicodex.quota_store.os.replace', side_effect=fail_final):
            with self.assertRaises(QuotaError):
                self.store.restore_from_backup(backup)
        self.assertEqual(self.store.path.read_bytes(), before)
        self.assertEqual(len(QuotaStore(self.root).history(self.key)), 2)
        self.assertEqual(list(self.root.glob('.quota-restore-*')), [])
        self.assertEqual(list(self.root.glob('.quota-damaged-*')), [])

    @unittest.skipUnless(os.name == 'nt', 'Windows file sharing contract')
    def test_real_open_sqlite_handle_blocks_replace_without_data_loss(self):
        self.store.capture(self.key, self.usage, observed_at=1100)
        backup = self.store.backup()
        self.store.capture(self.key, self.usage, observed_at=1200)
        before = self.store.path.read_bytes()
        db = sqlite3.connect(self.store.path)
        try:
            db.execute('SELECT * FROM accounts').fetchall()
            with self.assertRaises(QuotaError):
                self.store.restore_from_backup(backup)
            self.assertEqual(self.store.path.read_bytes(), before)
        finally:
            db.close()
        self.assertEqual(len(QuotaStore(self.root).history(self.key)), 2)

    def test_wal_backup_contains_committed_observations(self):
        self.store.capture(self.key, self.usage, observed_at=1100)
        db = sqlite3.connect(self.store.path)
        try:
            self.assertEqual(db.execute('PRAGMA journal_mode=WAL').fetchone()[0], 'wal')
            self.store.capture(self.key, self.usage, observed_at=1200)
            backup = self.store.backup()
            with closing(sqlite3.connect(backup)) as backup_db:
                self.assertEqual(backup_db.execute('PRAGMA quick_check').fetchone()[0], 'ok')
                self.assertEqual(backup_db.execute('SELECT count(*) FROM snapshots').fetchone()[0], 2)
            if os.name == 'nt':
                with self.assertRaises(QuotaError):
                    self.store.restore_from_backup(backup)
                self.assertEqual(len(self.store.history(self.key)), 2)
        finally:
            db.close()
        self.assertEqual(len(QuotaStore(self.root).history(self.key)), 2)

    def test_shared_lock_timeout_preserves_data_and_releases_local_mutex(self):
        script = '''from multicodex.locks import FileLock
import sys
with FileLock(sys.argv[1]):
    print("held", flush=True)
    sys.stdin.readline()
'''
        before = self.store.path.read_bytes()
        child = subprocess.Popen([sys.executable, '-c', script, str(self.store.lock_path)],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        try:
            self.assertEqual(child.stdout.readline().strip(), 'held')
            start = time.monotonic()
            with self.assertRaises(QuotaError) as caught:
                self.store.accounts()
            self.assertEqual(caught.exception.code, 'STORAGE')
            self.assertGreaterEqual(time.monotonic() - start, 4.8)
            self.assertEqual(self.store.path.read_bytes(), before)
        finally:
            _output, error = child.communicate('\n', timeout=5)
        self.assertEqual(child.returncode, 0, error)
        self.assertEqual(self.store.accounts()[0]['account_key'], self.key)


if __name__ == '__main__':
    unittest.main()
