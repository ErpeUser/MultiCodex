import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from multicodex.discovery import discover_legacy_profiles, default_legacy_roots, UnsupportedDesktop

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

    def test_default_roots_include_known_user_locations_without_recursive_scan(self):
        with tempfile.TemporaryDirectory() as d:
            base = Path(d)
            env = {
                'LOCALAPPDATA': str(base / 'local'),
                'APPDATA': str(base / 'roaming'),
                'USERPROFILE': str(base / 'user'),
            }
            with patch.dict(os.environ, env, clear=False), patch('pathlib.Path.home', return_value=base / 'home'):
                roots = default_legacy_roots()
            self.assertIn(base / 'local' / 'CodexProfiles', roots)
            self.assertIn(base / 'roaming' / 'CodexProfiles', roots)
            self.assertIn(base / 'user' / 'CodexProfiles', roots)
            self.assertIn(base / 'user' / '.codex' / 'CodexProfiles', roots)
            self.assertEqual(len({os.path.normcase(str(p.resolve(strict=False))) for p in roots}), len(roots))
            self.assertFalse(any(p == base / 'user' for p in roots))


if __name__=='__main__': unittest.main()
