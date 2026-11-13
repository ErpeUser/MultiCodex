import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from tools.release_gate import check_acceptance, ReleaseBlocked, REQUIRED_CHECKS

class ReleaseGateTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.setup=Path(self.temp.name)/'setup.exe'
        self.setup.write_bytes(b'Not an installer: synthetic gate-test payload only')
        self.commit='a'*40
        self.evidence={'schema':1,'source_commit':self.commit,'setup_sha256':hashlib.sha256(self.setup.read_bytes()).hexdigest(),
                       'reviewer':'fixture-reviewer','checked_at':'2026-11-13T10:00:00+00:00',
                       'checks':{key:True for key in REQUIRED_CHECKS}}

    def check(self):
        return check_acceptance(self.evidence,self.commit,self.setup)

    def test_empty_evidence_blocks_release(self):
        with self.assertRaises(ReleaseBlocked):
            check_acceptance({},self.commit,self.setup)

    def test_failed_native_requirement_blocks_release(self):
        self.evidence['checks']['existing_pool_secure_import']=False
        with self.assertRaises(ReleaseBlocked):self.check()

    def test_truthy_text_is_not_a_pass(self):
        self.evidence['checks']['oauth_relogin']='true'
        with self.assertRaises(ReleaseBlocked):self.check()

    def test_different_code_commit_invalidates_approval(self):
        self.evidence['source_commit']='b'*40
        with self.assertRaises(ReleaseBlocked):self.check()

    def test_changed_installer_invalidates_approval(self):
        self.setup.write_bytes(b'different fixture')
        with self.assertRaises(ReleaseBlocked):self.check()

    def test_missing_reviewer_blocks_publication(self):
        self.evidence['reviewer']=''
        with self.assertRaises(ReleaseBlocked):self.check()

    def test_fully_bound_fixture_passes_gate_logic_not_native_acceptance(self):
        result=self.check()
        self.assertEqual(result['source_commit'],self.commit)
        self.assertEqual(result['setup_sha256'],self.evidence['setup_sha256'])
