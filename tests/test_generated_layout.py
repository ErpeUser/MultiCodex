"""Guard the source-only root and the central generated data layout."""
from pathlib import Path
import subprocess
import unittest

ROOT = Path(__file__).resolve().parents[1]
ALLOWED_ROOT = {
    ".git", ".github", ".gitignore", "multicodex", "bridge", "tests",
    "tools", "packaging", "plugins", "run.py", "generated", "AGENTS.md",
    "README.md", "docs",
}


class GeneratedLayoutTests(unittest.TestCase):
    def test_every_root_entry_is_source_or_required_git_integration(self):
        extras = {path.name for path in ROOT.iterdir()} - ALLOWED_ROOT - {"__pycache__"}
        self.assertEqual(extras, set(), f"Unexpected root artifacts: {sorted(extras)}")

    def test_reference_files_are_present_at_canonical_paths(self):
        for name in (
            "generated/project/docs/README.md",
            "generated/project/docs/CHANGELOG.md",
            "generated/project/governance/AGENTS.md",
            "generated/project/licenses/LICENSE",
            "generated/project/config/python/requirements-build.windows-x64.lock",
            "generated/project/specifications/DESIGN.md",
            "plugins/figma/renderer.js",
            "tests/figma/renderer.test.cjs",
        ):
            with self.subTest(name=name):
                self.assertTrue((ROOT / name).is_file(), name)

    def test_completed_one_time_migrations_are_not_active_tools(self):
        for name in ('migrate_generated.py', 'repair_generated_references.py',
                     'update_docs_paths.py'):
            self.assertFalse((ROOT / 'tools' / name).exists(), name)
        self.assertTrue((ROOT / 'tools/cleanup_generated.py').is_file())

    def test_document_links_resolve_after_migration(self):
        from tools.check_references import broken_links
        self.assertEqual(broken_links(), [])

    def test_required_git_integrations_remain_at_root(self):
        self.assertTrue((ROOT / ".git").exists())
        self.assertTrue((ROOT / ".gitignore").is_file())
        self.assertTrue((ROOT / ".github/workflows/windows.yml").is_file())
        self.assertTrue((ROOT / ".github/workflows/feature-checks.yml").is_file())

    def test_runtime_is_ignored_but_reference_files_are_tracked_candidates(self):
        ignored = subprocess.run(
            ["git", "-C", str(ROOT), "check-ignore", "-q",
             "generated/runtime/cache/multicodex-probe.tmp"],
            check=False, timeout=10)
        self.assertEqual(ignored.returncode, 0)
        for candidate in ('bridge/node_modules/any-package/index.js',
                          '.ruff_cache/last-scan.bin', '.DS_Store'):
            with self.subTest(candidate=candidate):
                result = subprocess.run(
                    ['git', '-C', str(ROOT), 'check-ignore', '-q', candidate],
                    check=False, timeout=10)
                self.assertEqual(result.returncode, 0)
        reference = subprocess.run(
            ["git", "-C", str(ROOT), "check-ignore", "-q",
             "generated/project/docs/README.md"], check=False, timeout=10)
        self.assertEqual(reference.returncode, 1)

    def test_generated_layout_checker_accepts_only_canonical_categories(self):
        from tools.check_generated_layout import violations
        self.assertEqual(violations(), [])


if __name__ == "__main__":
    unittest.main()
