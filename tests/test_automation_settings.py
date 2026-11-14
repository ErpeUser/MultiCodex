import importlib
import importlib.util
from pathlib import Path
import tempfile
import unittest

class SettingsTests(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(importlib.util.find_spec('multicodex.automation_settings'),'Automation settings are missing')
        self.mod=importlib.import_module('multicodex.automation_settings')
        tmp=tempfile.TemporaryDirectory();self.addCleanup(tmp.cleanup)
        self.root=Path(tmp.name);self.settings=self.mod.AutomationSettings(self.root)

    def test_defaults_are_disabled_and_no_profile_is_implicitly_authorized(self):
        data=self.settings.load()
        self.assertFalse(data['enabled']);self.assertEqual(data['allowed_profiles'],[])
        self.assertEqual(data['poll_interval_seconds'],60)

    def test_save_survives_reopen_without_changing_theme(self):
        (self.root/'settings.json').write_text('{"theme":"light"}')
        self.settings.save({'enabled':True,'allowed_profiles':['Work'],'warning_threshold_percent':85})
        got=self.mod.AutomationSettings(self.root).load()
        self.assertTrue(got['enabled']);self.assertEqual(got['allowed_profiles'],['Work'])
        self.assertEqual((self.root/'settings.json').read_text(),'{"theme":"light"}')

    def test_partial_save_preserves_prior_options(self):
        self.settings.save({'allowed_profiles':['Work'],'maximum_retries':4})
        self.settings.save({'enabled':True})
        self.assertEqual(self.settings.load()['maximum_retries'],4)

    def test_corrupt_settings_are_not_overwritten(self):
        self.settings.path.write_text('broken')
        with self.assertRaises(self.mod.SettingsError):self.settings.load()
        with self.assertRaises(self.mod.SettingsError):self.settings.save({'enabled':True})
        self.assertEqual(self.settings.path.read_text(),'broken')

    def test_unknown_fields_and_bad_types_are_rejected(self):
        for value in ({'enabled':'true'},{'maximum_retries':True},{'poll_interval_seconds':0},
                      {'warning_threshold_percent':float('nan')},{'token':'secret'},
                      {'allowed_profiles':['../escape']},{'automatic_activation_enabled':'yes'}):
            with self.subTest(value=value),self.assertRaises(self.mod.SettingsError):self.settings.save(value)
        self.assertFalse(self.settings.load()['enabled'])

    def test_explicit_activation_opt_in_does_not_authorize_any_profile(self):
        self.settings.save({'automatic_activation_enabled':True})
        self.assertTrue(self.settings.load()['automatic_activation_enabled'])
        self.assertEqual(self.settings.load()['allowed_profiles'],[])

    def test_settings_symlink_is_refused(self):
        external=self.root/'external';external.write_text('original')
        try:self.settings.path.symlink_to(external)
        except OSError:self.skipTest('Symlinks unavailable')
        with self.assertRaises(self.mod.SettingsError):self.settings.save({'enabled':True})
        self.assertEqual(external.read_text(),'original')

if __name__=='__main__':unittest.main()
