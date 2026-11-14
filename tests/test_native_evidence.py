"""Exercise real files/hashes; synthetic reports are not native acceptance."""
from __future__ import annotations
import copy
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from PIL import Image
from tools import native_evidence as ne
from tools.release_gate import check_acceptance, ReleaseBlocked, REQUIRED_CHECKS

COMMIT = 'a' * 40
PAGES = ('Overview', 'Instances', 'Accounts', 'Usage', 'Settings', 'Diagnostics')
REPORTS = ('source-runtime.json', 'source-gui.json', 'packaged-runtime.json',
           'packaged-gui.json', 'installed/installed-runtime.json', 'installed/installed-gui.json')


def put(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value), encoding='utf-8')


class EvidenceTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.evidence = self.root / 'evidence'
        self.setup = self.root / 'test-setup.exe'
        self.setup.write_bytes(b'synthetic installer, never executed')
        self.sha = hashlib.sha256(self.setup.read_bytes()).hexdigest()
        self.build = {'source_commit': COMMIT, 'source_dirty': False,
                      'setup_sha256': self.sha, 'windows': 'fixture Windows'}
        put(self.evidence / 'build.json', self.build)
        for name in REPORTS:
            put(self.evidence / name, {'ready': True})
        put(self.evidence / 'installed/installer-smoke.json',
            {'ready': True, 'setup_sha256': self.sha})

    def capture(self, percent=100):
        folder = self.root / f'capture-{percent}'
        folder.mkdir()
        rows = []
        for theme in ('dark', 'light'):
            for size in ((900, 640), (1180, 760)):
                for page in PAGES:
                    name = f'{theme}-{size[0]}x{size[1]}-{page.lower()}.png'
                    path = folder / name
                    Image.new('RGB', (320, 240)).save(path)
                    rows.append({'page': page, 'theme': theme, 'window_size': list(size),
                                 'file': name, 'sha256': hashlib.sha256(path.read_bytes()).hexdigest(),
                                 'native_dpi': percent * 96 // 100, 'dpi_awareness': 'per-monitor', 'image_size': [320, 240]})
        manifest = {'schema': 1, 'source_commit': COMMIT, 'setup_sha256': self.sha,
                    'platform': 'win32', 'capture_kind': 'owned-window',
                    'dpi_percent': percent, 'files': rows}
        put(folder / 'manifest.json', manifest)
        return folder, manifest

    def collect(self, captures=()):
        return ne.collect_evidence(self.evidence, self.setup, COMMIT, captures)

    def test_no_dpi_captures_is_incomplete_despite_green_runtime_reports(self):
        report = self.collect()
        self.assertFalse(report['automated_ready'])
        self.assertEqual(report['missing_dpi_percent'], [100, 125, 150, 200])
        self.assertEqual(report['capture_count'], 0)

    def test_96_bound_images_complete_machine_checks_but_not_manual_acceptance(self):
        folders = [self.capture(p)[0] for p in (100, 125, 150, 200)]
        ne.seal_build(self.evidence, self.setup, COMMIT)
        report = self.collect(folders)
        self.assertTrue(report['automated_ready'])
        self.assertFalse(report['release_ready'])
        self.assertEqual(report['capture_count'], 96)
        self.assertEqual(report['missing_dpi_percent'], [])
        draft = ne.acceptance_draft(report)
        self.assertEqual(set(draft['checks']), set(REQUIRED_CHECKS))
        self.assertTrue(all(value is False for value in draft['checks'].values()))
        with self.assertRaises(ReleaseBlocked):
            check_acceptance(draft, COMMIT, self.setup)

    def test_wrong_commit_or_dirty_build_is_rejected(self):
        for changes in ({'source_commit': 'b' * 40}, {'source_dirty': True},
                        {'source_dirty': 0}, {'source_dirty': 'false'}):
            with self.subTest(changes=changes):
                put(self.evidence / 'build.json', {**self.build, **changes})
                with self.assertRaises(ne.EvidenceError): self.collect()

    def test_changed_installer_bytes_are_rejected(self):
        self.setup.write_bytes(b'different installer')
        with self.assertRaises(ne.EvidenceError): self.collect()

    def test_missing_report_is_named_not_ignored(self):
        (self.evidence / 'source-gui.json').unlink()
        report = self.collect()
        self.assertEqual(report['checks']['source-gui.json'], 'MISSING')
        self.assertFalse(report['automated_ready'])

    def test_truthy_ready_values_do_not_count_as_success(self):
        for value in (1, 'true', {}, None, False):
            with self.subTest(value=value):
                put(self.evidence / 'source-runtime.json', {'ready': value})
                self.assertEqual(self.collect()['checks']['source-runtime.json'], 'NOT_READY')

    def test_installer_smoke_must_match_this_installer(self):
        put(self.evidence / 'installed/installer-smoke.json', {'ready': True, 'setup_sha256': 'b' * 64})
        self.assertEqual(self.collect()['checks']['installed/installer-smoke.json'], 'BINDING_MISMATCH')

    def test_changed_capture_bytes_are_detected(self):
        folder, manifest = self.capture()
        (folder / manifest['files'][0]['file']).write_bytes(b'changed')
        with self.assertRaises(ne.EvidenceError): self.collect([folder])

    def test_duplicate_missing_and_extra_frames_are_rejected(self):
        folder, manifest = self.capture()
        for rows in (manifest['files'][:-1], manifest['files'] + manifest['files'][:1],
                     manifest['files'][:-1] + manifest['files'][:1]):
            with self.subTest(count=len(rows)):
                put(folder / 'manifest.json', {**manifest, 'files': rows})
                with self.assertRaises(ne.EvidenceError): self.collect([folder])

    def test_capture_dpi_must_be_measured_for_each_frame(self):
        folder, manifest = self.capture(125)
        manifest['files'][0]['native_dpi'] = 96
        put(folder / 'manifest.json', manifest)
        with self.assertRaises(ne.EvidenceError): self.collect([folder])

    def test_unaware_or_unrecorded_dpi_context_is_not_native_dpi_evidence(self):
        folder, manifest = self.capture()
        for awareness in ('unaware', 'system', None):
            with self.subTest(awareness=awareness):
                manifest['files'][0]['dpi_awareness'] = awareness
                put(folder / 'manifest.json', manifest)
                with self.assertRaises(ne.EvidenceError): self.collect([folder])

    def test_duplicate_dpi_directory_does_not_inflate_coverage(self):
        folder, _ = self.capture()
        with self.assertRaises(ne.EvidenceError): self.collect([folder, folder])

    def test_non_native_or_wrong_build_capture_manifest_is_rejected(self):
        folder, manifest = self.capture()
        for changes in ({'platform': 'linux'}, {'capture_kind': 'desktop'},
                        {'source_commit': 'b' * 40}, {'setup_sha256': 'b' * 64},
                        {'schema': True}, {'dpi_percent': True}):
            with self.subTest(changes=changes):
                put(folder / 'manifest.json', {**manifest, **changes})
                with self.assertRaises(ne.EvidenceError): self.collect([folder])

    def test_manifest_paths_cannot_escape_capture_directory(self):
        folder, manifest = self.capture()
        for value in ('../secret.png', '/tmp/secret.png', 'C:\\private.png', 'wrong.png'):
            with self.subTest(path=value):
                manifest['files'][0]['file'] = value
                put(folder / 'manifest.json', manifest)
                with self.assertRaises(ne.EvidenceError): self.collect([folder])

    def test_png_is_decoded_and_dimensions_checked_not_only_hashed(self):
        folder, manifest = self.capture()
        record = manifest['files'][0]
        record['image_size'] = [321, 240]
        put(folder / 'manifest.json', manifest)
        with self.assertRaises(ne.EvidenceError): self.collect([folder])
        path = folder / record['file']
        path.write_bytes(b'not a png')
        record['sha256'] = hashlib.sha256(path.read_bytes()).hexdigest()
        put(folder / 'manifest.json', manifest)
        with self.assertRaises(ne.EvidenceError): self.collect([folder])

    def test_symlink_report_and_parent_are_rejected(self):
        target = self.root / 'external.json'
        put(target, {'ready': True})
        link = self.evidence / 'source-gui.json'
        link.unlink()
        try: link.symlink_to(target)
        except OSError: self.skipTest('Host does not permit creating symlinks')
        self.assertEqual(self.collect()['checks']['source-gui.json'], 'INVALID')
        link.unlink()
        parent = self.root / 'redirect'
        parent.symlink_to(self.evidence, target_is_directory=True)
        with self.assertRaises(ne.EvidenceError):
            ne.collect_evidence(parent, self.setup, COMMIT)

    def test_json_duplicates_constants_and_oversized_input_are_rejected(self):
        path = self.evidence / 'build.json'
        for text in ('{"source_dirty":false,"source_dirty":true}', '{"x":NaN}', ' ' * 262145):
            with self.subTest(size=len(text)):
                path.write_text(text)
                with self.assertRaises(ne.EvidenceError): self.collect()

    def test_report_never_copies_untrusted_report_fields(self):
        put(self.evidence / 'source-gui.json', {'ready': True, 'raw_provider': 'test-secret'})
        self.build['raw_provider'] = 'test-secret'
        put(self.evidence / 'build.json', self.build)
        self.assertNotIn('test-secret', json.dumps(self.collect()))

    def test_existing_output_is_never_overwritten(self):
        path = self.root / 'existing.json'
        path.write_text('keep exactly')
        with self.assertRaises(ne.EvidenceError): ne.write_report(path, self.collect())
        self.assertEqual(path.read_text(), 'keep exactly')

    def test_unsealed_old_build_cannot_be_declared_ready(self):
        folders = [self.capture(p)[0] for p in (100, 125, 150, 200)]
        report = self.collect(folders)
        self.assertFalse(report['automated_ready'])
        self.assertEqual(report['checks']['build-index.json'], 'MISSING')

    def test_sealed_build_detects_replaced_ready_report(self):
        ne.seal_build(self.evidence, self.setup, COMMIT)
        put(self.evidence / 'source-gui.json', {'ready': True, 'new_run': True})
        report = self.collect()
        self.assertEqual(report['checks']['build-index.json'], 'BINDING_MISMATCH')

    def test_utf8_bom_from_windows_reports_is_supported(self):
        (self.evidence / 'build.json').write_text(json.dumps(self.build), encoding='utf-8-sig')
        self.assertEqual(self.collect()['source_commit'], COMMIT)

    def test_capture_plan_covers_each_page_theme_and_size_once(self):
        plan = ne.capture_plan()
        self.assertEqual(len(plan), 24)
        self.assertEqual(len({x['file'] for x in plan}), 24)
        self.assertEqual({x['page'] for x in plan}, set(PAGES))
        self.assertEqual({x['theme'] for x in plan}, {'dark', 'light'})
        self.assertEqual({tuple(x['window_size']) for x in plan}, {(900, 640), (1180, 760)})


class GitIdentityTests(unittest.TestCase):
    def test_real_git_worktree_is_bound_and_dirty_tree_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            def git(*args):
                return subprocess.run(['git', '-C', str(root), *args], check=True,
                                      stdout=subprocess.PIPE, stderr=subprocess.PIPE).stdout.decode().strip()
            git('init', '-q')
            (root / 'source.txt').write_text('original')
            git('add', '.')
            git('-c', 'user.name=Fixture', '-c', 'user.email=test@example.test', 'commit', '-qm', 'fixture')
            commit = git('rev-parse', 'HEAD')
            self.assertEqual(ne.source_identity(root), commit)
            (root / 'source.txt').write_text('changed')
            with self.assertRaises(ne.EvidenceError): ne.source_identity(root)

    def test_native_capture_refuses_non_windows_before_creating_output(self):
        if sys.platform == 'win32': self.skipTest('Non-Windows guard')
        from tools.capture_native_matrix import capture
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / 'capture'
            with self.assertRaises(ne.EvidenceError):
                capture(Path(tmp), output, Path(tmp) / 'setup.exe', COMMIT, 100)
            self.assertFalse(output.exists())

if __name__ == '__main__': unittest.main()
