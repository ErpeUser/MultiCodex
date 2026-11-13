import json
import tempfile
import unittest
from pathlib import Path

from multicodex.profiles import ProfileStore, ProfileError


class ProfileTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.store = ProfileStore(Path(self.temp.name) / 'managed')

    def test_creates_isolated_profile_without_touching_others(self):
        a = self.store.create('Work')
        b = self.store.create('Personal')
        self.assertNotEqual(a.home, b.home)
        self.assertEqual([p.name for p in self.store.list()], ['Personal', 'Work'])
        self.assertTrue((a.home / 'electron').is_dir())
        self.assertTrue((b.home / '.codex').is_dir())

    def test_rejects_traversal_and_windows_reserved_names(self):
        for name in ['../bad', '.', 'CON', 'NUL.txt', 'COM1', 'Work/other', 'A ', '']:
            with self.subTest(name=name), self.assertRaises(ProfileError):
                self.store.create(name)

    def test_adoption_is_link_only_and_idempotent(self):
        legacy = Path(self.temp.name) / 'CodexProfiles' / 'Old'
        (legacy / '.codex').mkdir(parents=True)
        token = legacy / '.codex' / 'auth.json'
        token.write_text('do-not-copy', encoding='utf8')
        self.store.adopt('Old', legacy)
        self.store.adopt('Old', legacy)
        profile = self.store.get('Old')
        self.assertEqual(profile.home, legacy.resolve())
        self.assertEqual(token.read_text(), 'do-not-copy')
        self.assertFalse((self.store.root / 'Old' / '.codex' / 'auth.json').exists())
        self.assertEqual(len(self.store.list()), 1)

    def test_adopt_will_not_replace_existing_profile(self):
        self.store.create('Work')
        alt = Path(self.temp.name) / 'external'
        alt.mkdir()
        with self.assertRaises(ProfileError):
            self.store.adopt('Work', alt)


if __name__ == '__main__':
    unittest.main()
