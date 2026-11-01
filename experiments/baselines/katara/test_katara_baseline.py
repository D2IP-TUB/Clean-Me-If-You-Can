"""Unit tests for the domain-KB KATARA detect/correct port."""

import os
import tempfile
import unittest

from katara_baseline import detect_and_correct, load_domain_specific_kb


def _write_kb(root, name, lines):
    path = os.path.join(root, name)
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    return path


class TestLoadDomainSpecificKB(unittest.TestCase):
    def test_loads_type_and_rel_files(self):
        with tempfile.TemporaryDirectory() as td:
            _write_kb(td, "city.type.txt", ["Berlin", "Munich"])
            _write_kb(
                td,
                "cityInCountry.rel.txt",
                [
                    "Berlin\tcityInCountry\tGermany",
                    "Munich\tcityInCountry\tGermany",
                    "Paris\tcityInCountry\tFrance",
                ],
            )
            types, rels = load_domain_specific_kb(td)
            self.assertEqual(len(types), 2)
            self.assertIn("Berlin", types[0] | types[1])
            self.assertEqual(rels["cityInCountry"]["Paris"], "France")


class TestTypeDetection(unittest.TestCase):
    def test_flags_values_outside_covered_type(self):
        rows = [
            ["Berlin"],
            ["Munich"],
            ["Berlin"],
            ["Xyzland"],
        ]
        types = [{"Berlin", "Munich", "Paris"}]
        detected, corrected = detect_and_correct(
            rows, types, {}, type_coverage=0.2, pair_coverage=0.15
        )
        self.assertIn((3, 0), detected)
        self.assertNotIn((0, 0), detected)
        self.assertEqual(detected[(3, 0)], "")
        self.assertEqual(corrected, {})

    def test_skips_column_below_type_coverage(self):
        # 1/5 = 0.2 is not strictly greater than the Java threshold.
        rows = [["Berlin"], ["Nope"], ["Nope"], ["Nope"], ["Nope"]]
        types = [{"Berlin", "Munich"}]
        detected, _ = detect_and_correct(
            rows, types, {}, type_coverage=0.2, pair_coverage=0.15
        )
        self.assertEqual(detected, {})

    def test_type_match_is_case_insensitive(self):
        rows = [["berlin"], ["MUNICH"], ["typo"]]
        types = [{"Berlin", "Munich"}]
        detected, _ = detect_and_correct(
            rows, types, {}, type_coverage=0.2, pair_coverage=0.15, ignore_case=True
        )
        self.assertEqual(set(detected), {(2, 0)})


class TestPairDetection(unittest.TestCase):
    def test_repairs_object_when_subject_is_in_kb(self):
        # 3/4 rows support city -> country, so coverage is 0.75 >= 0.15
        rows = [
            ["Berlin", "Germany"],
            ["Munich", "Germany"],
            ["Paris", "France"],
            ["Berlin", "France"],
        ]
        rels = {
            "cityInCountry": {
                "Berlin": "Germany",
                "Munich": "Germany",
                "Paris": "France",
            }
        }
        detected, corrected = detect_and_correct(
            rows, [], rels, type_coverage=0.2, pair_coverage=0.15
        )
        self.assertIn((3, 0), detected)
        self.assertIn((3, 1), detected)
        self.assertEqual(corrected[(3, 1)], "Germany")
        self.assertNotIn((3, 0), corrected)

    def test_flags_row_when_subject_missing_from_kb(self):
        rows = [
            ["Berlin", "Germany"],
            ["Munich", "Germany"],
            ["Nowhere", "Atlantis"],
        ]
        rels = {"cityInCountry": {"Berlin": "Germany", "Munich": "Germany"}}
        detected, corrected = detect_and_correct(
            rows, [], rels, type_coverage=0.2, pair_coverage=0.15
        )
        self.assertIn((2, 0), detected)
        self.assertIn((2, 1), detected)
        self.assertEqual(corrected, {})

    def test_pair_match_is_case_insensitive(self):
        rows = [
            ["berlin", "GERMANY"],
            ["MUNICH", "germany"],
            ["Berlin", "France"],
        ]
        rels = {"cityInCountry": {"Berlin": "Germany", "Munich": "Germany"}}
        detected, corrected = detect_and_correct(
            rows, [], rels, type_coverage=0.2, pair_coverage=0.15, ignore_case=True
        )
        self.assertNotIn((0, 0), detected)
        self.assertNotIn((0, 1), detected)
        self.assertNotIn((1, 0), detected)
        self.assertNotIn((1, 1), detected)
        self.assertIn((2, 1), detected)
        self.assertEqual(corrected[(2, 1)], "Germany")

    def test_pair_match_can_stay_case_sensitive(self):
        rows = [
            ["Berlin", "Germany"],
            ["Munich", "Germany"],
            ["Berlin", "germany"],
        ]
        rels = {"cityInCountry": {"Berlin": "Germany", "Munich": "Germany"}}
        detected, corrected = detect_and_correct(
            rows, [], rels, type_coverage=0.2, pair_coverage=0.15, ignore_case=False
        )
        self.assertIn((2, 1), detected)
        self.assertEqual(corrected[(2, 1)], "Germany")

    def test_skips_pair_below_coverage(self):
        rows = [
            ["Berlin", "Germany"],
            ["X", "Y"],
            ["X", "Y"],
            ["X", "Y"],
            ["X", "Y"],
            ["X", "Y"],
            ["X", "Y"],
        ]
        rels = {"cityInCountry": {"Berlin": "Germany"}}
        detected, _ = detect_and_correct(
            rows, [], rels, type_coverage=0.2, pair_coverage=0.15
        )
        self.assertEqual(detected, {})


class TestEndToEndTinyKB(unittest.TestCase):
    def test_directory_kb_type_and_pair(self):
        with tempfile.TemporaryDirectory() as td:
            _write_kb(td, "city.type.txt", ["Berlin", "Munich", "Paris"])
            _write_kb(
                td,
                "cityInCountry.rel.txt",
                [
                    "Berlin\tcityInCountry\tGermany",
                    "Munich\tcityInCountry\tGermany",
                    "Paris\tcityInCountry\tFrance",
                ],
            )
            types, rels = load_domain_specific_kb(td)
            rows = [
                ["Berlin", "Germany"],
                ["Munich", "Germany"],
                ["Paris", "France"],
                ["Paris", "Germany"],
                ["Xyzland", "Germany"],
            ]
            detected, corrected = detect_and_correct(rows, types, rels)
            self.assertIn((3, 1), detected)
            self.assertEqual(corrected[(3, 1)], "France")
            self.assertIn((4, 0), detected)
            self.assertEqual(detected[(4, 0)], "")


if __name__ == "__main__":
    unittest.main()
