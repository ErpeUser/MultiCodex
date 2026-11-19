import unittest

from tools.github_sync import classify_branch


class GithubSyncTests(unittest.TestCase):
    def test_branch_classification(self):
        cases = {
            (0, 0): "up_to_date",
            (3, 0): "behind",
            (0, 2): "ahead",
            (3, 2): "diverged",
        }
        for counts, expected in cases.items():
            with self.subTest(counts=counts):
                self.assertEqual(classify_branch(*counts), expected)


if __name__ == "__main__":
    unittest.main()
