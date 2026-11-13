"""Regressions against the recovered baseline; all inputs are synthetic."""
import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from multicodex.account_bridge import AccountBridge, AccountBridgeError
from multicodex.profiles import ProfileStore, ProfileError, validate_name
from multicodex.processes import InstanceController


class ProfileSafetyTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.base = Path(self.tmp.name)
        self.store = ProfileStore(self.base / 'profiles')

    def test_nonobject_metadata_is_a_controlled_error(self):
        self.store.create('Work')
        (self.store.root/'Work'/'profile.json').write_text('[]')
        with self.assertRaises(ProfileError):
            self.store.get('Work')

    def test_windows_superscript_devices_and_space_before_extension(self):
        for name in ['COM\u00b9', 'LPT\u00b2.txt', 'CON .txt', 'NUL .data']:
            with self.subTest(name=name), self.assertRaises(ProfileError):
                validate_name(name)

    def test_case_insensitive_names_do_not_create_duplicate_profiles(self):
        self.store.create('Work')
        with self.assertRaises(ProfileError):
            self.store.create('work')

    def test_second_alias_to_same_external_profile_is_rejected(self):
        source = self.base/'legacy'
        (source/'.codex').mkdir(parents=True)
        self.store.adopt('Work', source)
        with self.assertRaises(ProfileError):
            self.store.adopt('Alias', source)

    def test_child_auth_symlink_cannot_escape_managed_profile(self):
        profile = self.store.create('Work')
        outside = self.base/'outside'; outside.mkdir()
        (profile.home/'.codex'/'config.toml').unlink()
        (profile.home/'.codex').rmdir()
        try:
            (profile.home/'.codex').symlink_to(outside, target_is_directory=True)
        except OSError:
            self.skipTest('Host does not permit test symlinks')
        with self.assertRaises(ProfileError):
            self.store.get('Work')

    def test_corrupt_profile_is_visible_in_diagnostics(self):
        self.store.create('Work')
        (self.store.root/'Work'/'profile.json').write_text('bad json')
        self.assertEqual(self.store.list(), [])
        self.assertEqual(len(self.store.issues), 1)


class BridgeSafetyTests(unittest.TestCase):
    def call_with(self, value):
        response = subprocess.CompletedProcess(['node'], 0, json.dumps(value), '')
        with patch('multicodex.account_bridge.subprocess.run', return_value=response):
            return AccountBridge().request('health')

    def test_array_response_is_controlled(self):
        with self.assertRaises(AccountBridgeError) as caught:
            self.call_with([])
        self.assertEqual(caught.exception.code, 'INVALID_RESPONSE')

    def test_missing_result_is_controlled(self):
        with self.assertRaises(AccountBridgeError) as caught:
            self.call_with({'id': 1})
        self.assertEqual(caught.exception.code, 'INVALID_RESPONSE')

    def test_boolean_id_is_not_integer_one(self):
        with self.assertRaises(AccountBridgeError):
            self.call_with({'id': True, 'result': {'serviceReady': True}})

    def test_raw_error_message_is_never_exposed(self):
        with self.assertRaises(AccountBridgeError) as caught:
            self.call_with({'id': 1, 'error': {'code':'EACCES','message':'fixture-secret-value'}})
        self.assertNotIn('fixture-secret-value', str(caught.exception))

    def test_error_shape_is_validated(self):
        with self.assertRaises(AccountBridgeError):
            self.call_with({'id': 1, 'error': []})


class ProcessMatchingTests(unittest.TestCase):
    def test_legacy_profile_root_argument_is_recognised(self):
        from test_processes import FakeProcess, FakePlatform
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'Work'; p.mkdir()
            proc=FakeProcess(1,['ChatGPT.exe', '--user-data-dir='+str(p)])
            self.assertEqual(len(InstanceController(FakePlatform([proc])).matching(p)),1)

    def test_renderer_is_not_treated_as_an_independent_root(self):
        from test_processes import FakeProcess, FakePlatform
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'Work'; p.mkdir()
            proc=FakeProcess(1,['ChatGPT.exe','--type=renderer','--user-data-dir='+str(p/'electron')])
            self.assertEqual(InstanceController(FakePlatform([proc])).matching(p), [])

    def test_conflicting_profile_arguments_fail_closed(self):
        from test_processes import FakeProcess, FakePlatform
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'Work'; p.mkdir()
            proc=FakeProcess(1,['ChatGPT.exe','--user-data-dir='+str(p/'electron'),'--user-data-dir=other'])
            self.assertEqual(InstanceController(FakePlatform([proc])).matching(p), [])

    def test_launch_clears_global_credentials_and_sets_bundled_cli(self):
        from test_processes import FakePlatform
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'Work';p.mkdir(); exe=Path(d)/'app'/'ChatGPT.exe'
            exe.parent.mkdir();exe.touch(); cli=exe.parent/'resources'/'codex.exe'
            cli.parent.mkdir();cli.touch(); platform=FakePlatform([])
            with patch.dict(os.environ, {'OPENAI_API_KEY':'fixture-secret','CODEX_CLI_PATH':'wrong','CODEX_MULTI_AUTH_DIR':'global'}):
                InstanceController(platform).launch(exe,p)
            env=platform.launched[0][2]
            self.assertNotIn('OPENAI_API_KEY',env)
            self.assertEqual(env['CODEX_CLI_PATH'],str(cli))
            self.assertNotEqual(env.get('CODEX_MULTI_AUTH_DIR'),'global')
            self.assertEqual(env['CODEX_MULTI_AUTH_RUNTIME_ROTATION_PROXY'],'0')
