import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class DistributionTests(unittest.TestCase):
    def test_windows_setup_keeps_profiles_outside_install_dir(self):
        script = (ROOT/'packaging'/'MultiCodex.iss').read_text(encoding='utf8')
        self.assertIn('PrivilegesRequired=lowest', script)
        self.assertIn('recurseSubdirs', script)
        self.assertNotIn('MultiCodex\\profiles', script)
        self.assertIn('[Icons]', script)

    def test_release_requires_artifact_from_green_build(self):
        workflow = (ROOT/'.github'/'workflows'/'windows.yml').read_text(encoding='utf8')
        self.assertIn('needs: build', workflow)
        self.assertIn('if: startsWith(github.ref', workflow)
        self.assertIn('actions/download-artifact', workflow)
        self.assertIn('actions/upload-artifact', workflow)

    def test_bridge_upstream_is_pinned(self):
        from json import loads
        package = loads((ROOT/'bridge'/'package.json').read_text())
        self.assertEqual(package['dependencies']['codex-multi-auth'], '2.26.0')


if __name__=='__main__': unittest.main()
