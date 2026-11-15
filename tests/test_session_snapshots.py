"""Metadata changes cannot bypass validation or overwrite a newer profile."""
import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from multicodex.codex_client import AccountIdentity
from multicodex.profiles import ProfileError, ProfileStore
from multicodex.sessions import SessionStore
from multicodex.profiles import _checked_bytes


class SessionSnapshotTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.profiles = ProfileStore(self.root / 'profiles')
        self.profile = self.profiles.create('Work')
        self.sessions = SessionStore(self.profiles)
        self.sessions.register('Work', 'default', AccountIdentity('a@example.invalid', 'pro', 'a'))
        self.meta = self.profile.home / 'profile.json'

    def test_changed_profile_after_decode_is_not_returned_as_validated_session(self):
        original = json.loads
        changed = []
        def decode(payload, *args, **kwargs):
            data = original(payload, *args, **kwargs)
            if isinstance(data, dict) and data.get('name') == 'Work' and not changed:
                changed.append(True)
                replacement = {**data, 'unexpected_private_field': 'DO_NOT_COPY'}
                self.meta.write_text(json.dumps(replacement), encoding='utf-8')
            return data
        with patch('json.loads', side_effect=decode):
            with self.assertRaises(ProfileError):
                self.sessions.list('Work')
        self.assertEqual(changed, [True])
        self.assertFalse((self.profile.home / 'profile.json.previous').read_text().find('DO_NOT_COPY') >= 0)

    def test_concurrent_valid_update_before_save_is_preserved(self):
        save = self.sessions._save
        replacement = []
        def intervene(name, data, *args, **kwargs):
            newer = json.loads(self.meta.read_bytes())
            newer['sessions']['default']['label'] = 'External change'
            self.meta.write_text(json.dumps(newer), encoding='utf-8')
            replacement.append(self.meta.read_bytes())
            return save(name, data, *args, **kwargs)
        with patch.object(self.sessions, '_save', side_effect=intervene):
            with self.assertRaises(ProfileError):
                self.sessions.rename('Work', 'default', 'Stale change')
        self.assertEqual(self.meta.read_bytes(), replacement[0])
        self.assertEqual(self.sessions.list('Work')[0]['label'], 'External change')

    def test_unrecognized_journal_fields_block_recovery(self):
        path = self.profile.home / '.operation.json'
        path.write_text(json.dumps({'version': 1, 'old': 'default', 'new': 'default',
            'phase': 'prepared', 'was_running': False, 'unexpected': 'DO_NOT_COPY'}))
        with self.assertRaises(ProfileError):
            self.sessions.journal('Work')
        self.assertIn('DO_NOT_COPY', path.read_text())

    def test_boolean_journal_version_is_not_version_one(self):
        path = self.profile.home / '.operation.json'
        path.write_text(json.dumps({'version': True, 'old': 'default', 'new': 'default',
            'phase': 'prepared', 'was_running': False}))
        with self.assertRaises(ProfileError):
            self.sessions.journal('Work')

    def test_nonstring_journal_phase_is_a_controlled_error(self):
        path = self.profile.home / '.operation.json'
        path.write_text(json.dumps({'version': 1, 'old': 'default', 'new': 'default',
            'phase': [], 'was_running': False}))
        with self.assertRaises(ProfileError):
            self.sessions.journal('Work')

    def test_replaced_metadata_file_is_rejected_even_with_identical_bytes(self):
        original = json.loads
        changed = []
        def decode(payload, *args, **kwargs):
            data = original(payload, *args, **kwargs)
            if isinstance(data, dict) and data.get('name') == 'Work' and not changed:
                changed.append(True)
                replacement = self.profile.home / 'replacement.json'
                replacement.write_bytes(self.meta.read_bytes())
                replacement.replace(self.meta)
            return data
        with patch('json.loads', side_effect=decode):
            with self.assertRaises(ProfileError):
                self.sessions.list('Work')
        self.assertEqual(changed, [True])

    def test_changed_journal_after_decode_blocks_recovery(self):
        path = self.profile.home / '.operation.json'
        path.write_text(json.dumps({'version': 1, 'old': 'default', 'new': 'default',
            'phase': 'prepared', 'was_running': False}))
        original = json.loads
        def decode(payload, *args, **kwargs):
            data = original(payload, *args, **kwargs)
            if isinstance(data, dict) and 'phase' in data:
                path.write_text('{"changed": true}')
            return data
        with patch('json.loads', side_effect=decode):
            with self.assertRaises(ProfileError):
                self.sessions.journal('Work')
        self.assertEqual(path.read_text(), '{"changed": true}')

    def test_replaced_profile_directory_cannot_supply_a_recovery_journal(self):
        path = self.profile.home / '.operation.json'
        journal = json.dumps({'version': 1, 'old': 'default', 'new': 'default',
            'phase': 'prepared', 'was_running': False})
        path.write_text(journal)
        original_home = self.profiles.root / 'Original'
        def replace_parent(target, limit):
            if target.name == '.operation.json':
                self.profile.home.rename(original_home)
                self.profile.home.mkdir()
                (self.profile.home / 'profile.json').write_text('{"unvalidated": true}')
                (self.profile.home / '.operation.json').write_text(journal)
            return _checked_bytes(target, limit)
        with patch('multicodex.sessions._checked_bytes', side_effect=replace_parent):
            with self.assertRaises(ProfileError):
                self.sessions.journal('Work')
        self.assertEqual((original_home / '.operation.json').read_text(), journal)
        self.assertTrue((original_home / 'profile.json').is_file())

    @unittest.skipUnless(os.name == 'nt', 'Windows junction contract')
    def test_windows_junction_profile_is_rejected_without_touching_target(self):
        original_home = self.profiles.root / 'Original'
        original_bytes = self.meta.read_bytes()
        self.profile.home.rename(original_home)
        result = subprocess.run(['cmd.exe', '/d', '/c', 'mklink', '/J',
            str(self.profile.home), str(original_home)], capture_output=True, text=True)
        if result.returncode:
            self.skipTest('Host cannot create a temporary test junction')
        try:
            for operation in (lambda: self.profiles.get('Work'),
                              lambda: self.sessions.home('Work', 'default'),
                              lambda: self.sessions.journal('Work')):
                with self.subTest(operation=operation), self.assertRaises(ProfileError):
                    operation()
            self.assertEqual((original_home / 'profile.json').read_bytes(), original_bytes)
        finally:
            # rmdir removes the junction itself, never its target or contents.
            self.profile.home.rmdir()


if __name__ == '__main__':
    unittest.main()
