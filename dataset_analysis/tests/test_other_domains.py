import os
import sys
import unittest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import run_other_domains_multilabel as rod  # noqa: E402


class TestOtherDomains(unittest.TestCase):
    def test_only_books_and_movies(self):
        self.assertEqual([d.label for d in rod.DOMAINS], ["books", "movies"])

    def test_paths_stay_under_repo_data(self):
        for d in rod.DOMAINS:
            self.assertEqual(d.dirty_path.parent.name, d.label)
            self.assertEqual(d.dirty_path.parent.parent, rod.DATA)
            self.assertEqual(d.clean_path.parent, d.dirty_path.parent)


if __name__ == "__main__":
    unittest.main()
