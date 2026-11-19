import unittest

from tools.post_pull import classify_paths


class PostPullImpactTests(unittest.TestCase):
    def test_documentation_only_change_needs_no_regeneration(self):
        impact = classify_paths(["generated/project/docs/README.md"])
        self.assertFalse(impact.extension)
        self.assertFalse(impact.desktop_exe)
        self.assertFalse(impact.desktop_shortcut)

    def test_figma_source_change_requires_extension_package(self):
        impact = classify_paths(["plugins/figma/renderer.js"])
        self.assertTrue(impact.extension)
        self.assertFalse(impact.desktop_exe)

    def test_application_change_requires_exe_and_installer(self):
        impact = classify_paths(["multicodex/quota_service.py"])
        self.assertTrue(impact.desktop_exe)
        self.assertTrue(impact.desktop_installer)
        self.assertFalse(impact.desktop_shortcut)

    def test_shortcut_definition_change_requires_installer(self):
        impact = classify_paths(["packaging/MultiCodex.iss"])
        self.assertFalse(impact.desktop_exe)
        self.assertTrue(impact.desktop_shortcut)
        self.assertTrue(impact.desktop_installer)


if __name__ == "__main__":
    unittest.main()
