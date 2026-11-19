import hashlib
import io
import json
import os
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from unittest.mock import patch
from datetime import datetime, timedelta, timezone
from pathlib import Path
from tools.release_gate import check_acceptance, check_supply_chain, ReleaseBlocked, REQUIRED_CHECKS, main

class ReleaseGateTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.setup=Path(self.temp.name)/'setup.exe'
        self.setup.write_bytes(b'Not an installer: synthetic gate-test payload only')
        self.commit='a'*40
        self.evidence={'schema':1,'source_commit':self.commit,'setup_sha256':hashlib.sha256(self.setup.read_bytes()).hexdigest(),
                       'reviewer':'fixture-reviewer','checked_at':datetime.now(timezone.utc).isoformat(),
                       'checks':{key:True for key in REQUIRED_CHECKS}}

    def check(self):
        return check_acceptance(self.evidence,self.commit,self.setup)

    def test_ci_public_repository_is_blocked_before_native_acceptance(self):
        argv = ['release_gate.py', '--commit', self.commit, '--setup', str(self.setup),
                '--sbom', 'missing.json', '--license-report', 'missing-license.json']
        environment = {'GITHUB_ACTIONS': 'true', 'MULTICODEX_GITHUB_REPOSITORY_PRIVATE': 'false',
                       'MULTICODEX_RELEASE_ACCEPTANCE': ''}
        output = io.StringIO()
        with patch.dict(os.environ, environment, clear=True), patch.object(sys, 'argv', argv), redirect_stdout(output):
            self.assertEqual(main(), 1)
        self.assertIn('private repository', output.getvalue().lower())

    def test_ci_missing_visibility_is_blocked_even_before_acceptance(self):
        argv = ['release_gate.py', '--commit', self.commit, '--setup', str(self.setup),
                '--sbom', 'missing.json', '--license-report', 'missing-license.json']
        output = io.StringIO()
        with patch.dict(os.environ, {'GITHUB_ACTIONS': 'true'}, clear=True), patch.object(sys, 'argv', argv), redirect_stdout(output):
            self.assertEqual(main(), 1)
        self.assertIn('private repository', output.getvalue().lower())

    def test_ci_private_repository_still_requires_native_acceptance(self):
        argv = ['release_gate.py', '--commit', self.commit, '--setup', str(self.setup),
                '--sbom', 'missing.json', '--license-report', 'missing-license.json']
        environment = {'GITHUB_ACTIONS': 'true', 'MULTICODEX_GITHUB_REPOSITORY_PRIVATE': 'true',
                       'MULTICODEX_RELEASE_ACCEPTANCE': ''}
        output = io.StringIO()
        with patch.dict(os.environ, environment, clear=True), patch.object(sys, 'argv', argv), redirect_stdout(output):
            self.assertEqual(main(), 1)
        self.assertIn('native acceptance', output.getvalue().lower())
        self.assertNotIn('private repository', output.getvalue().lower())

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

    def supply_fixture(self):
        self.sbom = Path(self.temp.name) / 'SBOM.cdx.json'
        self.license_report = Path(self.temp.name) / 'license-report.json'
        self.sbom.write_text(json.dumps({'bomFormat': 'CycloneDX', 'specVersion': '1.6',
            'metadata': {'component': {'version': self.commit}},
            'components': [{'type': 'library', 'name': 'fixture'}]}))
        self.license_report.write_text(json.dumps({'schema': 1, 'source_commit': self.commit,
            'sbom_sha256': hashlib.sha256(self.sbom.read_bytes()).hexdigest(),
            'ready': True, 'blockers': [], 'components': 1}))
        self.evidence['sbom_sha256'] = hashlib.sha256(self.sbom.read_bytes()).hexdigest()
        self.evidence['license_report_sha256'] = hashlib.sha256(self.license_report.read_bytes()).hexdigest()

    def test_missing_supply_chain_evidence_blocks_release(self):
        self.supply_fixture()
        del self.evidence['sbom_sha256']
        with self.assertRaises(ReleaseBlocked):
            check_supply_chain(self.evidence, self.commit, self.sbom, self.license_report)

    def test_changed_sbom_invalidates_review(self):
        self.supply_fixture()
        self.sbom.write_text('{}')
        with self.assertRaises(ReleaseBlocked):
            check_supply_chain(self.evidence, self.commit, self.sbom, self.license_report)

    def test_unknown_licenses_block_even_with_matching_hashes(self):
        self.supply_fixture()
        report = json.loads(self.license_report.read_text())
        report.update(ready=False, blockers=['LICENSE_REVIEW_REQUIRED:fixture'])
        self.license_report.write_text(json.dumps(report))
        self.evidence['license_report_sha256'] = hashlib.sha256(self.license_report.read_bytes()).hexdigest()
        with self.assertRaises(ReleaseBlocked):
            check_supply_chain(self.evidence, self.commit, self.sbom, self.license_report)

    def test_bound_supply_fixture_checks_gate_logic_only(self):
        self.supply_fixture()
        result = check_supply_chain(self.evidence, self.commit, self.sbom, self.license_report)
        self.assertEqual(result['sbom_sha256'], self.evidence['sbom_sha256'])

    def reviewed_supply_fixture(self, blocker='RUNTIME_LICENSE_REVIEW_REQUIRED:CPython'):
        self.supply_fixture()
        bom = json.loads(self.sbom.read_text())
        bom['components'].append({'type': 'file', 'name': 'licenses/runtime.txt',
            'hashes': [{'alg': 'SHA-256', 'content': 'c' * 64}]})
        self.sbom.write_text(json.dumps(bom))
        self.evidence['sbom_sha256'] = hashlib.sha256(self.sbom.read_bytes()).hexdigest()
        report = json.loads(self.license_report.read_text())
        report.update(ready=False, blockers=[blocker], components=2,
                      sbom_sha256=self.evidence['sbom_sha256'])
        self.license_report.write_text(json.dumps(report))
        self.evidence['license_report_sha256'] = hashlib.sha256(self.license_report.read_bytes()).hexdigest()
        self.evidence['license_review'] = [{'blocker': blocker, 'reviewer': 'fixture-reviewer',
            'license_expression': 'PSF-2.0', 'notice': 'licenses/runtime.txt', 'notice_sha256': 'c' * 64}]

    def test_explicit_human_license_disposition_uses_a_real_inventoried_notice(self):
        self.reviewed_supply_fixture()
        result = check_supply_chain(self.evidence, self.commit, self.sbom, self.license_report)
        self.assertEqual(result['manually_reviewed_license_blockers'], 1)

    def test_manual_review_cannot_waive_lock_mismatch(self):
        self.reviewed_supply_fixture('PYTHON_LOCK_MISMATCH:fixture')
        with self.assertRaises(ReleaseBlocked):
            check_supply_chain(self.evidence, self.commit, self.sbom, self.license_report)

    def test_manual_review_cannot_reference_unshipped_or_changed_notice(self):
        self.reviewed_supply_fixture()
        self.evidence['license_review'][0]['notice_sha256'] = 'd' * 64
        with self.assertRaises(ReleaseBlocked):
            check_supply_chain(self.evidence, self.commit, self.sbom, self.license_report)

    def test_manual_review_must_cover_every_blocker_without_duplicates(self):
        self.reviewed_supply_fixture()
        self.evidence['license_review'] *= 2
        with self.assertRaises(ReleaseBlocked):
            check_supply_chain(self.evidence, self.commit, self.sbom, self.license_report)

    def test_unreviewed_license_expression_is_not_approved_by_a_truthy_flag(self):
        self.reviewed_supply_fixture()
        self.evidence['license_review'][0]['license_expression'] = 'UNKNOWN'
        with self.assertRaises(ReleaseBlocked):
            check_supply_chain(self.evidence, self.commit, self.sbom, self.license_report)

    def test_stale_acceptance_is_rejected(self):
        self.evidence['checked_at'] = (datetime.now(timezone.utc) - timedelta(days=15)).isoformat()
        with self.assertRaises(ReleaseBlocked):
            self.check()

    def test_future_acceptance_is_rejected(self):
        self.evidence['checked_at'] = (datetime.now(timezone.utc) + timedelta(minutes=6)).isoformat()
        with self.assertRaises(ReleaseBlocked):
            self.check()
