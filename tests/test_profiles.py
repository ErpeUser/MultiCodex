import json
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch

from multicodex.profiles import ProfileStore, ProfileError
from multicodex.sessions import SessionStore
from multicodex.codex_client import AccountIdentity
from multicodex.controller import SessionController
from helpers.sessions import AuthFixture, InstancesFixture


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


class SessionCapacityTests(unittest.TestCase):
    BYTE_LIMIT = 1024 * 1024
    SHORT = AccountIdentity('old@example.invalid', 'plus', 'old-account')
    LONG = AccountIdentity('a' * 300 + '@example.invalid', 'p' * 64, 'i' * 256)

    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.store = ProfileStore(Path(temp.name) / 'profiles')
        self.store.create('Work')
        self.store.create('Other')
        self.sessions = SessionStore(self.store)
        self.path = self.store.root / 'Work' / 'profile.json'
        self.previous = self.path.with_name('profile.json.previous')
        self.previous.write_bytes(self.path.read_bytes())
        self.other = self.store.root / 'Other' / 'profile.json'
        self.other_before = self.other.read_bytes()

    def seed(self, count, identity, *, label=None, pad_to=None, with_target=False):
        # Large catalogues are local fixtures, accepted by the actual reader.
        row = {**identity.public(), 'verified_at': 1_900_000_000, 'label': identity.email}
        rows = {'default': dict(row)}
        rows.update({f'{n:032x}': dict(row) for n in range(1, count)})
        target = None
        if with_target:
            target, _ = self.sessions.prepare('Work')
            rows[target] = rows.pop(f'{1:032x}')
        if label is not None:
            rows['default']['label'] = label
        data = {'version': 1, 'name': 'Work', 'mode': 'managed',
                'active_session': 'default', 'sessions': rows}
        if pad_to is not None:
            remaining = pad_to - len(json.dumps(data, indent=2).encode('utf-8'))
            self.assertGreaterEqual(remaining, 0)
            for saved in rows.values():
                extra = min(remaining, 320 - len(saved['label']))
                saved['label'] += 'x' * extra
                remaining -= extra
            self.assertEqual(remaining, 0)
        encoded = json.dumps(data, indent=2).encode('utf-8')
        if pad_to is not None:
            self.assertEqual(len(encoded), pad_to)
        self.assertLessEqual(len(encoded), self.BYTE_LIMIT)
        self.path.write_bytes(encoded)
        self.assertEqual(self.store.get('Work').session_id, 'default')
        return target

    def assert_rejected_save_preserved(self, current, previous):
        self.assertEqual(self.path.read_bytes(), current)
        self.assertEqual(self.previous.read_bytes(), previous)
        self.assertEqual(self.store.get('Work').session_id, 'default')
        self.assertEqual(self.other.read_bytes(), self.other_before)
        self.assertEqual(list(self.path.parent.glob('.profile-*.tmp')), [])
        self.assertEqual(list(self.store.root.rglob('auth.json')), [])

    def test_count_overflow_preserves_current_and_backup(self):
        self.seed(1000, self.SHORT)
        sid, _ = self.sessions.prepare('Work')
        current, previous = self.path.read_bytes(), self.previous.read_bytes()
        for _ in range(2):
            with self.assertRaises(ProfileError):
                self.sessions.register('Work', sid, self.SHORT)
            self.assert_rejected_save_preserved(current, previous)

    def test_count_boundary_and_existing_session_refresh_remain_valid(self):
        self.seed(999, self.SHORT)
        sid, _ = self.sessions.prepare('Work')
        self.sessions.register('Work', sid, self.SHORT)
        self.assertEqual(len(self.sessions.list('Work')), 1000)
        self.sessions.rename('Work', 'default', 'Kept label')
        self.sessions.register('Work', 'default', self.SHORT)
        saved = {row['id']: row for row in self.sessions.list('Work')}
        self.assertEqual(len(saved), 1000)
        self.assertEqual(saved['default']['label'], 'Kept label')
        self.assertEqual(self.store.get('Work').session_id, 'default')

    def test_registration_byte_overflow_preserves_current_and_backup(self):
        self.seed(942, self.LONG, pad_to=self.BYTE_LIMIT)
        sid, _ = self.sessions.prepare('Work')
        current, previous = self.path.read_bytes(), self.previous.read_bytes()
        with self.assertRaises(ProfileError):
            self.sessions.register('Work', sid, self.LONG)
        self.assert_rejected_save_preserved(current, previous)

    def test_exact_byte_boundary_remains_readable_after_refresh(self):
        self.seed(942, self.LONG, pad_to=self.BYTE_LIMIT)
        with patch('multicodex.sessions.time.time', return_value=1_900_000_001):
            self.sessions.register('Work', 'default', self.LONG)
        current = self.path.read_bytes()
        self.assertEqual(len(current), self.BYTE_LIMIT)
        self.assertEqual(current, json.dumps(json.loads(current), indent=2).encode('utf-8'))
        self.assertEqual(self.store.get('Work').account_email, self.LONG.email)
        self.assertEqual(json.loads(current)['sessions']['default']['verified_at'], 1_900_000_001)

    def test_activation_one_byte_over_limit_preserves_binding_and_backup(self):
        target = self.seed(942, self.LONG, pad_to=self.BYTE_LIMIT - 24, with_target=True)
        current, previous = self.path.read_bytes(), self.previous.read_bytes()
        proposed = json.loads(current)
        proposed['active_session'] = target
        self.assertEqual(len(json.dumps(proposed, indent=2).encode('utf-8')), self.BYTE_LIMIT + 1)
        with self.assertRaises(ProfileError):
            self.sessions.activate('Work', target)
        self.assert_rejected_save_preserved(current, previous)

    def test_unicode_rename_checks_serialized_byte_limit(self):
        self.seed(942, self.LONG, label='')
        current, previous = self.path.read_bytes(), self.previous.read_bytes()
        proposed = json.loads(current)
        proposed['sessions']['default']['label'] = '界' * 80
        self.assertGreater(len(json.dumps(proposed, indent=2).encode('utf-8')), self.BYTE_LIMIT)
        with self.assertRaises(ProfileError):
            self.sessions.rename('Work', 'default', '界' * 80)
        self.assert_rejected_save_preserved(current, previous)

    def test_controller_capacity_failure_keeps_profile_readable(self):
        self.seed(1000, self.SHORT)
        auth = AuthFixture()
        auth.identities[str(self.store.get('Work').codex_home)] = self.SHORT
        instances = InstancesFixture(self.store)
        instances.live.update(('Work', 'Other'))
        callbacks = []
        with self.assertRaises(ProfileError):
            SessionController(self.store, instances, auth).login(
                'Work', confirmed=True, on_browser=callbacks.append, cancel=threading.Event())
        self.assertEqual(len(json.loads(self.path.read_bytes())['sessions']), 1000)
        self.assertEqual(self.store.get('Work').session_id, 'default')
        self.assertEqual(len(json.loads(self.previous.read_bytes())['sessions']), 1000)
        self.assertEqual(instances.actions, [])
        self.assertEqual(instances.live, {'Work', 'Other'})
        self.assertEqual(len(callbacks), 1)
        self.assertIsNone(self.sessions.journal('Work'))
        self.assertEqual(self.other.read_bytes(), self.other_before)
        self.assertEqual(list(self.path.parent.glob('.profile-*.tmp')), [])
        self.assertEqual(list(self.store.root.rglob('auth.json')), [])


if __name__ == '__main__':
    unittest.main()
