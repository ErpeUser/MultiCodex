import os
import tempfile
import unittest
from pathlib import Path
from multicodex.discovery import discover_legacy_profiles, UnsupportedDesktop

class DiscoveryTests(unittest.TestCase):
    def test_discovery_only_finds_real_directories_and_does_not_write(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d,'CodexProfiles');root.mkdir()
            a=root/'A';a.mkdir()
            (root/'not-profile.txt').write_text('file')
            before=sorted(str(p) for p in root.rglob('*'))
            found=discover_legacy_profiles([root])
            self.assertEqual([(x.name,x.path) for x in found],[('A',a.resolve())])
            self.assertEqual(before,sorted(str(p) for p in root.rglob('*')))

    def test_non_windows_executable_discovery_explicitly_unsupported(self):
        if os.name=='nt': self.skipTest('Windows only')
        from multicodex.discovery import find_legacy_codex_executable
        with self.assertRaises(UnsupportedDesktop): find_legacy_codex_executable()


if __name__=='__main__': unittest.main()
