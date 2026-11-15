import importlib
import importlib.util
import json
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

    def test_oversized_settings_preserve_readable_previous_file(self):
        cases = [
            ('ascii', [f'P{i:04}' + 'x'*55 for i in range(1000)]),
            ('unicode', [f'P{i:04}' + '界'*55 for i in range(200)]),
            ('one_byte_over', [f'P{i:04}' + 'x'*55 for i in range(958)] + ['Q' + 'x'*48]),
        ]
        for label, profiles in cases:
            with self.subTest(case=label), tempfile.TemporaryDirectory(dir=self.root) as tmp:
                settings = self.mod.AutomationSettings(Path(tmp))
                settings.save({'allowed_profiles':['Work'],'maximum_retries':4})
                previous = settings.path.read_bytes()
                with self.assertRaises(self.mod.SettingsError) as caught:
                    settings.save({'allowed_profiles':profiles})
                self.assertEqual(caught.exception.code, 'INVALID_SETTINGS')
                self.assertEqual(settings.path.read_bytes(), previous)
                self.assertEqual(settings.load()['allowed_profiles'], ['Work'])
                settings.save({'enabled':True})
                self.assertTrue(settings.load()['enabled'])
                self.assertEqual(settings.load()['maximum_retries'], 4)
                self.assertEqual(list(Path(tmp).glob('.quota-settings-*')), [])

    def test_oversized_first_save_does_not_create_settings_file(self):
        profiles = [f'P{i:04}' + '界'*55 for i in range(200)]
        with self.assertRaises(self.mod.SettingsError):
            self.settings.save({'allowed_profiles':profiles})
        self.assertFalse(self.settings.path.exists())
        self.assertFalse(self.settings.load()['enabled'])
        self.assertEqual(list(self.root.glob('.quota-settings-*')), [])

    def test_valid_unicode_and_maximum_count_roundtrip(self):
        for profiles in ([f'P{i:04}' for i in range(1000)], [f'界{i:04}' for i in range(200)]):
            with self.subTest(profile_count=len(profiles)):
                saved = self.settings.save({'allowed_profiles':profiles})
                self.assertLessEqual(self.settings.path.stat().st_size, 65536)
                self.assertEqual(self.mod.AutomationSettings(self.root).load(), saved)

    def test_exact_byte_limit_roundtrip(self):
        # These 959 names fill the existing JSON representation to the reader boundary.
        profiles = [f'P{i:04}' + 'x'*55 for i in range(958)] + ['Q' + 'x'*47]
        saved = self.settings.save({'allowed_profiles':profiles})
        self.assertEqual(self.settings.path.stat().st_size, 65536)
        self.assertEqual(self.mod.AutomationSettings(self.root).load(), saved)
        self.settings.save({'enabled':True})
        self.settings.save({'enabled':False})
        self.assertFalse(self.settings.load()['enabled'])
        self.assertEqual(self.settings.path.stat().st_size, 65536)

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

    def test_invalid_numeric_thresholds_have_fixed_errors_and_preserve_settings(self):
        self.settings.save({'allowed_profiles':['Work'],'warning_threshold_percent':90})
        previous = self.settings.path.read_bytes()
        cases = [('huge_positive',10**400),('huge_negative',-(10**400)),
                 ('zero',0),('above_range',101),('boolean',True),
                 ('nan',float('nan')),('positive_inf',float('inf')),('negative_inf',float('-inf'))]
        for label, value in cases:
            for operation in (self.mod.validate_settings,self.settings.save):
                with self.subTest(case=label,operation=operation.__name__):
                    with self.assertRaises(self.mod.SettingsError) as caught:
                        operation({'warning_threshold_percent':value})
                    self.assertEqual(caught.exception.code,'INVALID_SETTINGS')
                    self.assertEqual(self.settings.path.read_bytes(),previous)
                    self.assertEqual(self.settings.load()['allowed_profiles'],['Work'])
        self.assertEqual(list(self.root.glob('.quota-settings-*')),[])

    def test_invalid_integer_threshold_file_has_corrupt_error_and_is_preserved(self):
        for label, value in [('huge_positive',10**400),('huge_negative',-(10**400)),('above_range',101)]:
            original = json.dumps({'warning_threshold_percent':value}).encode('utf-8')
            self.settings.path.write_bytes(original)
            for operation in (self.settings.load,lambda:self.settings.save({'enabled':True})):
                with self.subTest(case=label,operation=operation.__name__):
                    with self.assertRaises(self.mod.SettingsError) as caught:
                        operation()
                    self.assertEqual(caught.exception.code,'CORRUPT_SETTINGS')
                    self.assertEqual(self.settings.path.read_bytes(),original)
        self.assertEqual(list(self.root.glob('.quota-settings-*')),[])

    def test_valid_numeric_thresholds_roundtrip(self):
        for value in (1,100,0.5,99.5):
            with self.subTest(threshold=value):
                saved = self.settings.save({'warning_threshold_percent':value})
                self.assertEqual(saved['warning_threshold_percent'],value)
                self.assertEqual(self.settings.load()['warning_threshold_percent'],value)

    def test_settings_symlink_is_refused(self):
        external=self.root/'external';external.write_text('original')
        try:self.settings.path.symlink_to(external)
        except OSError:self.skipTest('Symlinks unavailable')
        with self.assertRaises(self.mod.SettingsError):self.settings.save({'enabled':True})
        self.assertEqual(external.read_text(),'original')

if __name__=='__main__':unittest.main()
