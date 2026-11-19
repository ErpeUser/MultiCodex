"""The installed smoke must fail closed without a usable bundled facade."""
import json
import shutil
import subprocess
import tempfile
import unittest


class BridgeSmokeTests(unittest.TestCase):
    def test_missing_installed_dependency_is_a_failure_with_controlled_output(self):
        node = shutil.which('node')
        if not node:
            self.skipTest('Node is not installed')
        with tempfile.TemporaryDirectory() as directory:
            result = subprocess.run([node, 'bridge/smoke_installed.mjs', directory],
                                    capture_output=True, text=True, timeout=15)
        self.assertEqual(result.returncode, 1)
        self.assertEqual(json.loads(result.stdout), {'ready': False, 'error': 'INSTALLED_STORAGE_SMOKE_FAILED'})
        self.assertEqual(result.stderr, '')
