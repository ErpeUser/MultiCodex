"""Validate the recorded requirements without interpreting historical claims as acceptance."""
import json
import unittest
from pathlib import Path

STATUS = Path(__file__).resolve().parents[1] / "generated" / "project" / "docs" / "implementation-status.json"


class ImplementationStatusTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.manifest = json.loads(STATUS.read_text(encoding="utf-8"))

    def test_declared_count_matches_unique_numbered_requirements(self):
        records = self.manifest["records"]
        self.assertEqual(self.manifest["count"], len(records))
        ids = [item["ID"] for item in records]
        self.assertEqual(ids, [f"{index:03d}" for index in range(1, len(records) + 1)])

    def test_error_case_count_matches_actual_records(self):
        self.assertEqual(self.manifest["error_case_count"], len(self.manifest["error_cases"]))

    def test_records_have_nonempty_status_fields(self):
        self.assertIsInstance(self.manifest.get("status"), str)
        self.assertTrue(self.manifest["status"])
        self.assertTrue(all(isinstance(item.get("Status"), str) and item["Status"]
                            for item in self.manifest["records"]))


if __name__ == "__main__":
    unittest.main()
