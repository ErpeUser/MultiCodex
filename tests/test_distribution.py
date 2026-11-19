import re
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

    def test_workflows_pin_actions_and_cover_pull_requests(self):
        for name in ('windows.yml', 'feature-checks.yml'):
            workflow = (ROOT/'.github'/'workflows'/name).read_text(encoding='utf8')
            refs = re.findall(r'uses:\s*([^\s]+)@([0-9a-f]{40})', workflow)
            self.assertTrue(refs, name)
            self.assertNotRegex(workflow, r'uses:\s*[^\s]+@v[0-9]')
            self.assertIn('persist-credentials: false', workflow)
        feature = (ROOT/'.github'/'workflows'/'feature-checks.yml').read_text(encoding='utf8')
        self.assertIn('pull_request:', feature)
        push_branches = re.search(r'^\s*branches:\s*\[([^]]+)\]', feature, re.MULTILINE)
        self.assertIsNotNone(push_branches)
        selected = {value.strip().strip('"').strip("'") for value in push_branches.group(1).split(',')}
        self.assertEqual(selected, {'main'})
        self.assertIn('--require-hashes', feature)

    def test_windows_build_is_clean_and_toolchain_bound(self):
        script = (ROOT/'tools'/'build_windows.ps1').read_text(encoding='utf8')
        self.assertIn('-TimeoutSec 120', script)
        self.assertIn('Remove-Item -LiteralPath $nodeRoot', script)
        self.assertIn('inno_version', script)
        self.assertIn('Build requires a clean source tree', script)


if __name__=='__main__': unittest.main()
