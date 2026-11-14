"""Use the actual PowerShell parser when running native Windows tests."""
from pathlib import Path
import shutil
import subprocess
import sys
import unittest


class NativeScriptTests(unittest.TestCase):
    @unittest.skipUnless(sys.platform == 'win32', 'Requires the actual Windows PowerShell parser')
    def test_new_native_runner_parses_without_errors(self):
        executable = shutil.which('pwsh')
        self.assertIsNotNone(executable, 'Native verification requires PowerShell 7')
        root = Path(__file__).resolve().parents[1]
        script = ("$tokens=$null; $errors=$null; "
                  "[System.Management.Automation.Language.Parser]::ParseFile("
                  "(Join-Path (Get-Location) 'tools/verify_native.ps1'),[ref]$tokens,[ref]$errors) | Out-Null; "
                  "if ($errors.Count -ne 0) { $errors | ForEach-Object { $_.ErrorId }; exit 1 }")
        run = subprocess.run([executable, '-NoLogo', '-NoProfile', '-NonInteractive', '-Command', script],
                             cwd=root, capture_output=True, text=True, timeout=30)
        self.assertEqual(run.returncode, 0, run.stdout + run.stderr)

if __name__ == '__main__': unittest.main()
