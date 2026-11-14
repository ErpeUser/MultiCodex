"""Exercise the real local packaging CLI and Node renderer contract tests."""
from pathlib import Path
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from tools import build_figma_plugin as builder

ROOT = Path(__file__).resolve().parents[1]
PLUGIN_ID = '1234567890123456789'  # Synthetic ID; never published to Figma.


class FigmaPackageTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.output = Path(self.tmp.name) / 'plugin'

    def test_packaged_manifest_denies_network_and_uses_user_supplied_id(self):
        builder.build_package(ROOT, self.output, PLUGIN_ID)
        manifest = json.loads((self.output / 'manifest.json').read_text())
        self.assertEqual(manifest['id'], PLUGIN_ID)
        self.assertEqual(manifest['networkAccess'], {'allowedDomains': ['none']})
        self.assertEqual(manifest['editorType'], ['figma'])
        self.assertEqual(manifest['documentAccess'], 'dynamic-page')
        self.assertTrue((self.output / manifest['main']).is_file())
        self.assertFalse(any(p.suffix in {'.ttf', '.otf', '.woff', '.woff2'} for p in self.output.iterdir()))
        self.assertTrue(builder.verify_package(ROOT, self.output, PLUGIN_ID))

    def test_embedded_palette_comes_from_application_tokens(self):
        from multicodex.ui_tokens import THEMES, NAV_WIDTH
        builder.build_package(ROOT, self.output, PLUGIN_ID)
        code = (self.output / 'code.js').read_text()
        payload, _ = json.JSONDecoder().raw_decode(code.split(' = ', 1)[1])
        self.assertEqual(payload['themes'], THEMES)
        self.assertEqual(payload['navWidth'], NAV_WIDTH)

    def test_invalid_or_missing_real_plugin_id_does_not_create_output(self):
        for value in ('', 'REPLACE_ME', '../plugin', '123', '1' * 41, '12\n3456789012'):
            with self.subTest(value=value), self.assertRaises(builder.PackageError):
                builder.build_package(ROOT, self.output, value)
            self.assertFalse(self.output.exists())

    def test_existing_package_and_user_edits_are_never_overwritten(self):
        builder.build_package(ROOT, self.output, PLUGIN_ID)
        (self.output / 'code.js').write_text('user edits')
        with self.assertRaises(builder.PackageError): builder.build_package(ROOT, self.output, PLUGIN_ID)
        self.assertEqual((self.output / 'code.js').read_text(), 'user edits')
        with self.assertRaises(builder.PackageError): builder.verify_package(ROOT, self.output, PLUGIN_ID)

    def test_changed_source_tokens_make_old_package_stale(self):
        source = Path(self.tmp.name) / 'source'
        (source / 'multicodex').mkdir(parents=True)
        (source / 'design/figma').mkdir(parents=True)
        shutil.copyfile(ROOT / 'multicodex/ui_tokens.py', source / 'multicodex/ui_tokens.py')
        shutil.copyfile(ROOT / 'design/figma/renderer.js', source / 'design/figma/renderer.js')
        builder.build_package(source, self.output, PLUGIN_ID)
        token_file = source / 'multicodex/ui_tokens.py'
        token_file.write_text(token_file.read_text().replace('#0D1114', '#0C1013'))
        with self.assertRaises(builder.PackageError): builder.verify_package(source, self.output, PLUGIN_ID)

    def test_symlink_destination_parent_is_refused(self):
        link = Path(self.tmp.name) / 'redirect'
        try: link.symlink_to(Path(self.tmp.name), target_is_directory=True)
        except OSError: self.skipTest('Host does not allow symlinks')
        with self.assertRaises(builder.PackageError): builder.build_package(ROOT, link / 'plugin', PLUGIN_ID)
        self.assertFalse(self.output.exists())

    def test_package_check_rejects_unexpected_files(self):
        builder.build_package(ROOT, self.output, PLUGIN_ID)
        (self.output / 'unexpected.txt').write_text('not part of the package')
        with self.assertRaises(builder.PackageError): builder.verify_package(ROOT, self.output, PLUGIN_ID)

    def test_real_cli_builds_then_checks_and_returns_failure_for_tampering(self):
        command = [sys.executable, str(ROOT / 'tools/build_figma_plugin.py'), '--output', str(self.output), '--plugin-id', PLUGIN_ID]
        run = subprocess.run(command, cwd=ROOT, capture_output=True, text=True, timeout=30)
        self.assertEqual(run.returncode, 0, run.stdout + run.stderr)
        run = subprocess.run(command + ['--check'], cwd=ROOT, capture_output=True, text=True, timeout=30)
        self.assertEqual(run.returncode, 0, run.stdout + run.stderr)
        (self.output / 'code.js').write_text('changed')
        run = subprocess.run(command + ['--check'], cwd=ROOT, capture_output=True, text=True, timeout=30)
        self.assertNotEqual(run.returncode, 0)

    @unittest.skipUnless(shutil.which('node'), 'Node.js is required for plugin contract tests')
    def test_node_renderer_suite(self):
        run = subprocess.run([shutil.which('node'), '--test', 'design/figma/tests/renderer.test.cjs'],
                             cwd=ROOT, capture_output=True, text=True, timeout=60)
        self.assertEqual(run.returncode, 0, run.stdout + run.stderr)

if __name__ == '__main__': unittest.main()
