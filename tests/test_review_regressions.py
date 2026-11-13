import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from multicodex.profiles import ProfileStore, ProfileError
from multicodex.sessions import SessionStore
from multicodex.runtime import LocalInstances
from multicodex.locks import FileLock, BusyError
from multicodex.settings import SettingsStore

class ReviewRegressions(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.store = ProfileStore(self.root/'profiles')
        self.profile = self.store.create('Work')

    def edit(self, **values):
        p = self.profile.home/'profile.json'
        data = json.loads(p.read_text()); data.update(values)
        p.write_text(json.dumps(data))

    def test_malformed_inactive_session_cannot_crash_account_list(self):
        self.edit(sessions={'f'*32: ['not', 'metadata']})
        with self.assertRaises(ProfileError):
            SessionStore(self.store).list('Work')

    def test_secret_bearing_unknown_metadata_is_not_copied_to_backup(self):
        self.edit(access_token='private-fixture')
        with self.assertRaises(ProfileError):
            self.store.get('Work')
        self.assertFalse((self.profile.home/'profile.json.previous').exists())

    def test_boolean_schema_version_is_not_accepted_as_integer_one(self):
        self.edit(version=True)
        with self.assertRaises(ProfileError):
            self.store.get('Work')

    def test_tampered_link_cannot_resolve_to_catalogue_ancestor(self):
        self.edit(mode='linked', path=str(self.root))
        with self.assertRaises(ProfileError):
            self.store.get('Work')

    def test_redirected_lock_parent_cannot_create_foreign_lock(self):
        foreign = self.root/'foreign'; foreign.mkdir()
        redirect = self.root/'redirect'
        try:
            redirect.symlink_to(foreign, target_is_directory=True)
        except OSError:
            self.skipTest('Host does not permit symlinks')
        with self.assertRaises(BusyError):
            with FileLock(redirect/'profile.lock'):
                pass
        self.assertFalse((foreign/'profile.lock').exists())

    def test_default_managed_auth_cannot_fall_back_to_plaintext(self):
        (self.profile.codex_home/'config.toml').write_text('cli_auth_credentials_store = "file"\n')
        with self.assertRaises(ProfileError):
            SessionStore(self.store).home('Work', 'default')

    def test_managed_launch_checks_auth_policy_before_process_start(self):
        (self.profile.codex_home/'auth.json').write_text('{"fixture": true}')
        with patch('multicodex.runtime.find_legacy_codex_executable', side_effect=AssertionError('Must not resolve/start process')):
            with self.assertRaises(ProfileError):
                LocalInstances(self.store).launch('Work')

    def test_catalogue_mutation_obeys_cross_process_lock(self):
        import subprocess
        import sys
        # The other interpreter holds the actual OS lock, not a mocked lock.
        script = 'from multicodex.locks import FileLock; import sys; f=FileLock(sys.argv[1]); f.__enter__(); print("ready",flush=True); sys.stdin.readline()'
        child = subprocess.Popen([sys.executable,'-c',script,str(self.store.root/'.locks'/'catalogue.lock')],stdin=subprocess.PIPE,stdout=subprocess.PIPE,text=True)
        try:
            self.assertEqual(child.stdout.readline().strip(),'ready')
            with self.assertRaises(BusyError):
                self.store.create('Other')
            self.assertFalse((self.store.root/'Other').exists())
        finally:
            child.communicate('\n',timeout=5)

    def test_redirected_settings_root_is_rejected(self):
        target = self.root/'settings-target'; target.mkdir()
        root = self.root/'settings-link'
        try:
            root.symlink_to(target,target_is_directory=True)
        except OSError:
            self.skipTest('Host does not permit symlinks')
        with self.assertRaises(ValueError):
            SettingsStore(root)
