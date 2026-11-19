"""Safety regressions for the allowlisted generated-artifact cleanup utility."""
from contextlib import redirect_stdout
import io
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from tools import cleanup_generated as cleanup


class CleanupGeneratedTests(unittest.TestCase):
    def test_only_explicit_cache_and_validation_paths_are_allowed(self):
        for candidate in (
            ".git", "generated/local/git/pre-migration-backup",
            "generated/project/docs/README.md", "generated/runtime/output",
            "generated/runtime/evidence", "generated/runtime/build",
            "generated/runtime/build/rollback-MultiCodex-0.2.0-dev",
            "generated/runtime/dependencies", "../output",
        ):
            with self.subTest(candidate=candidate):
                self.assertFalse(cleanup.allowed(candidate))
                with self.assertRaises(ValueError):
                    cleanup.inventory(candidate)

    def test_dry_run_does_not_delete_or_write_a_cleanup_report(self):
        baseline = set((cleanup.ROOT / "generated/runtime/reports").glob("cleanup-*.json"))
        with io.StringIO() as output, redirect_stdout(output):
            self.assertEqual(cleanup.main(["--categories", "cache"]), 0)
            self.assertIn("MODE=DRY_RUN", output.getvalue())
        self.assertEqual(set((cleanup.ROOT / "generated/runtime/reports").glob("cleanup-*.json")), baseline)

    def test_unknown_cleanup_category_is_rejected(self):
        with self.assertRaises(ValueError):
            cleanup.plan(("output",))

    def test_symlinked_cache_subdirectory_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            dest = root / "generated/runtime/cache/pip"
            dest.parent.mkdir(parents=True)
            target = root / "user-data"
            target.mkdir()
            try:
                dest.symlink_to(target, target_is_directory=True)
            except OSError:
                self.skipTest("Host does not permit test directory symlinks")
            with patch.object(cleanup, "ROOT", root):
                with self.assertRaises(ValueError):
                    cleanup.inventory("generated/runtime/cache/pip")

    def test_unverified_pyinstaller_build_is_protected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            work = root / "generated/runtime/build/pyinstaller/MultiCodex/MultiCodex.exe"
            dist = root / "generated/runtime/dist/MultiCodex/MultiCodex.exe"
            log = root / "generated/runtime/reports/pyinstaller-migration-validation.log"
            for file in (work, dist, log):
                file.parent.mkdir(parents=True, exist_ok=True)
            work.write_bytes(b"one")
            dist.write_bytes(b"two")
            log.write_text("Build complete!\n", encoding="utf-8")
            with patch.object(cleanup, "ROOT", root):
                with self.assertRaises(ValueError):
                    cleanup.validate_category("validation-build")

    def test_verified_build_accepts_powershell_utf16_log(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            work = root / 'generated/runtime/build/pyinstaller/MultiCodex/MultiCodex.exe'
            dist = root / 'generated/runtime/dist/MultiCodex/MultiCodex.exe'
            log = root / 'generated/runtime/reports/pyinstaller-migration-validation.log'
            for file in (work, dist, log):
                file.parent.mkdir(parents=True, exist_ok=True)
            work.write_bytes(b'identical binary')
            dist.write_bytes(b'identical binary')
            log.write_bytes('INFO: Build complete!'.encode('utf-16'))
            with patch.object(cleanup, 'ROOT', root):
                cleanup.validate_category('validation-build')

    def test_unverified_download_is_protected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            archive = root / "generated/runtime/downloads/actionlint_1.7.12_windows_amd64.zip"
            exe = root / "generated/runtime/dependencies/toolchains/actionlint-1.7.12/actionlint.exe"
            archive.parent.mkdir(parents=True)
            exe.parent.mkdir(parents=True)
            archive.write_bytes(b"wrong archive")
            exe.write_bytes(b"tool")
            with patch.object(cleanup, "ROOT", root):
                with self.assertRaises(ValueError):
                    cleanup.validate_category("downloads")


if __name__ == "__main__":
    unittest.main()
