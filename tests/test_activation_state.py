from pathlib import Path
import importlib
import importlib.util
import tempfile
import unittest

class RunStoreTests(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(importlib.util.find_spec('multicodex.automation_state'), 'Durable activation journal is missing')
        self.mod = importlib.import_module('multicodex.automation_state')
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.store = self.mod.RunStore(self.root)

    def create(self, **kwargs):
        return self.store.enqueue(account_key='a'*64, profile='Work', session_id='default', now=1000, **kwargs)

    def test_duplicate_requests_reuse_one_pending_run(self):
        one=self.create(); two=self.create()
        self.assertEqual(one['run_id'],two['run_id'])
        self.assertEqual(len(self.store.list()),1)

    def test_another_target_cannot_replace_pending_profile_request(self):
        self.create()
        with self.assertRaises(self.mod.RunError):
            self.store.enqueue(account_key='b'*64, profile='Work',session_id='b'*32,now=1000)
        self.assertEqual(self.store.list()[0]['account_key'],'a'*64)

    def test_waiting_state_survives_reopening(self):
        run=self.create()
        self.store.transition(run['run_id'],'QUEUED','CHECKING_TARGET',now=1001)
        self.store.transition(run['run_id'],'CHECKING_TARGET','WAITING_FOR_RESET',now=1002,next_at=1300)
        other=self.mod.RunStore(self.root)
        self.assertEqual(other.list()[0]['next_at'],1300)
        self.assertEqual(other.list()[0]['state'],'WAITING_FOR_RESET')

    def test_illegal_success_transition_is_rejected(self):
        run=self.create()
        with self.assertRaises(self.mod.RunError):
            self.store.transition(run['run_id'],'QUEUED','COMPLETED',now=1001)
        self.assertEqual(self.store.get(run['run_id'])['state'],'QUEUED')

    def test_compare_and_swap_rejects_stale_writer(self):
        run=self.create()
        self.store.transition(run['run_id'],'QUEUED','CHECKING_TARGET',now=1001)
        with self.assertRaises(self.mod.RunError):
            self.store.transition(run['run_id'],'QUEUED','CANCELLED',now=1002)

    def test_cancel_is_terminal_but_does_not_delete_history(self):
        run=self.create()
        self.store.cancel(run['run_id'],now=1001)
        self.assertEqual(self.store.get(run['run_id'])['state'],'CANCELLED')
        self.assertNotEqual(self.create()['run_id'],run['run_id'])
        self.assertEqual(len(self.store.list()),2)

    def test_cancel_during_cutover_requires_recovery(self):
        run=self.create()
        for a,b in [('QUEUED','CHECKING_TARGET'),('CHECKING_TARGET','ACTIVATING_TARGET')]:
            self.store.transition(run['run_id'],a,b,now=1001)
        with self.assertRaises(self.mod.RunError):self.store.cancel(run['run_id'],now=1002)
        self.assertEqual(self.store.get(run['run_id'])['state'],'ACTIVATING_TARGET')

    def test_unknown_error_string_cannot_be_persisted(self):
        run=self.create()
        with self.assertRaises(self.mod.RunError):
            self.store.transition(run['run_id'],'QUEUED','PAUSED',now=1001,error_code='SECRET_TOKEN')
        self.assertNotIn(b'SECRET_TOKEN',self.store.path.read_bytes())

    def test_path_redirect_is_refused(self):
        external=self.root/'external';external.mkdir()
        link=self.root/'alias'
        try:link.symlink_to(external,target_is_directory=True)
        except (OSError,NotImplementedError):self.skipTest('symlink unsupported')
        with self.assertRaises(self.mod.RunError):self.mod.RunStore(link)

    def test_corrupt_database_is_preserved(self):
        self.store.path.write_bytes(b'not a database')
        with self.assertRaises(self.mod.RunError):self.mod.RunStore(self.root)
        self.assertEqual(self.store.path.read_bytes(),b'not a database')

    def test_invalid_ids_and_profiles_never_create_runs(self):
        for key,profile,sid in [('bad','Work','default'),('a'*64,'../escape','default'),('a'*64,'Work','../../secret')]:
            with self.subTest(profile=profile,sid=sid),self.assertRaises(self.mod.RunError):
                self.store.enqueue(account_key=key,profile=profile,session_id=sid,now=1000)
        self.assertEqual(self.store.list(),[])
