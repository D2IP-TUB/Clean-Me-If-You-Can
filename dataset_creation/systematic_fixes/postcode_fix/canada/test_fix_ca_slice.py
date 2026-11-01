import csv
import tempfile
import unittest
from pathlib import Path

from fix_ca_slice import (
    FIX_COL,
    address_key,
    choose_fix,
    is_fight,
    load_nar_by_id,
    rewrite_pair,
)


def _write_csv(path: Path, fieldnames: list[str], rows: list[dict], lineterminator="\r\n") -> None:
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames, lineterminator=lineterminator)
        w.writeheader()
        for row in rows:
            w.writerow({k: row.get(k, "") for k in fieldnames})


SLICE_FIELDS = [
    "id", "name", "road", "house_number", "postcode", "locality",
    "region", "country", "country_code", "provenance_graph_iri",
]


class ChooseFixTests(unittest.TestCase):
    def test_nar_keep_clean_wins(self):
        self.assertEqual(choose_fix("keep_clean"), "keep_clean, NAR")

    def test_nar_keep_dirty(self):
        self.assertEqual(choose_fix("keep_dirty"), "keep_dirty, NAR")

class FightAndKeyTests(unittest.TestCase):
    def test_blank_dirty_is_a_fight(self):
        self.assertTrue(is_fight("", "M5J 2H5"))
        self.assertFalse(is_fight("M5J 2H5", "M5J2H5"))
        self.assertTrue(is_fight("M5J 2H5", "M5J 2H6"))

    def test_key_uses_alnum_clean_pc_and_province(self):
        dirty = {"house_number": "", "road": "", "locality": "", "region": "", "postcode": ""}
        clean = {
            "house_number": "1", "road": "Front Street", "locality": "Toronto",
            "region": "Ontario", "postcode": "M5J 2H5",
        }
        k = address_key(dirty, clean)
        self.assertEqual(k[0], "M5J2H5")
        self.assertEqual(k[-1], "ON")


class RewriteTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.dirty = self.root / "slice_ca_dirty.csv"
        self.clean = self.root / "slice_ca_clean.csv"
        self.nar = self.root / "unique_nar.csv"
        self.out_dirty = self.root / "slice_ca_dirty_fixed.csv"
        self.out_clean = self.root / "slice_ca_clean_fixed.csv"

    def tearDown(self):
        self.tmp.cleanup()

    def _run(self, dirty_rows, clean_rows, nar_rows):
        _write_csv(self.dirty, SLICE_FIELDS, dirty_rows)
        _write_csv(self.clean, SLICE_FIELDS, clean_rows)
        _write_csv(self.nar, ["id", "nar_decision"], nar_rows)
        rewrite_pair(
            self.dirty, self.clean, self.nar, self.out_dirty, self.out_clean,
        )
        with self.out_clean.open(newline="", encoding="utf-8") as f:
            return list(csv.DictReader(f))

    def test_keep_dirty_copies_dirty_postcode_string(self):
        dirty = [{
            "id": "a", "name": "Cafe", "road": "Front Street", "house_number": "1",
            "postcode": "M5J 2H5", "locality": "Toronto", "region": "",
            "country": "Canada", "country_code": "", "provenance_graph_iri": "u",
        }]
        clean = [{
            "id": "a", "name": "Cafe", "road": "Front Street", "house_number": "1",
            "postcode": "M5J 2H6", "locality": "Toronto", "region": "Ontario",
            "country": "Canada", "country_code": "ca", "provenance_graph_iri": "u",
        }]
        out = self._run(
            dirty, clean,
            [{"id": "a", "nar_decision": "keep_dirty"}],
        )
        self.assertEqual(out[0]["postcode"], "M5J 2H5")
        self.assertEqual(out[0][FIX_COL], "keep_dirty, NAR")

    def test_keep_dirty_uses_clean_spacing(self):
        dirty = [{
            "id": "a", "name": "Cafe", "road": "East Broadway", "house_number": "78",
            "postcode": "V5T1V6", "locality": "Vancouver", "region": "",
            "country": "Canada", "country_code": "", "provenance_graph_iri": "u",
        }]
        clean = [{
            "id": "a", "name": "Cafe", "road": "East Broadway", "house_number": "78",
            "postcode": "V5T 1V5", "locality": "Vancouver", "region": "British Columbia",
            "country": "Canada", "country_code": "ca", "provenance_graph_iri": "u",
        }]
        out = self._run(
            dirty, clean,
            [{"id": "a", "nar_decision": "keep_dirty"}],
        )
        self.assertEqual(out[0]["postcode"], "V5T 1V6")
        self.assertEqual(out[0][FIX_COL], "keep_dirty, NAR")

    def test_keep_dirty_blank_does_not_wipe_clean(self):
        dirty = [{
            "id": "a", "name": "Scotiabank Arena", "road": "Bremner", "house_number": "40",
            "postcode": "", "locality": "Toronto", "region": "",
            "country": "Canada", "country_code": "", "provenance_graph_iri": "u",
        }]
        clean = [{
            "id": "a", "name": "Scotiabank Arena", "road": "Bremner", "house_number": "40",
            "postcode": "M5J 2J2", "locality": "Toronto", "region": "Ontario",
            "country": "Canada", "country_code": "ca", "provenance_graph_iri": "u",
        }]
        out = self._run(
            dirty, clean,
            [{"id": "a", "nar_decision": "keep_dirty"}],
        )
        self.assertEqual(out[0]["postcode"], "M5J 2J2")
        self.assertNotEqual(out[0]["postcode"], "")

    def test_province_prefixed_pc_becomes_spaced_ldu(self):
        dirty = [{
            "id": "a", "name": "Falher Hotel", "road": "Main", "house_number": "1",
            "postcode": "AB T0H 1M0", "locality": "Falher", "region": "",
            "country": "Canada", "country_code": "", "provenance_graph_iri": "u",
        }]
        clean = [{
            "id": "a", "name": "Falher Hotel", "road": "Main", "house_number": "1",
            "postcode": "AB T0H 1M0", "locality": "Falher", "region": "Alberta",
            "country": "Canada", "country_code": "ca", "provenance_graph_iri": "u",
        }]
        out = self._run(dirty, clean, [])
        self.assertEqual(out[0]["postcode"], "T0H 1M0")

    def test_keep_clean_leaves_postcode(self):
        dirty = [{
            "id": "a", "name": "Cafe", "road": "Front Street", "house_number": "1",
            "postcode": "", "locality": "Toronto", "region": "",
            "country": "Canada", "country_code": "", "provenance_graph_iri": "u",
        }]
        clean = [{
            "id": "a", "name": "Cafe", "road": "Front Street", "house_number": "1",
            "postcode": "M5J 2H5", "locality": "Toronto", "region": "Ontario",
            "country": "Canada", "country_code": "ca", "provenance_graph_iri": "u",
        }]
        out = self._run(
            dirty, clean,
            [{"id": "a", "nar_decision": "keep_clean"}],
        )
        self.assertEqual(out[0]["postcode"], "M5J 2H5")
        self.assertEqual(out[0][FIX_COL], "keep_clean, NAR")

    def test_agree_row_is_untouched(self):
        dirty = [{
            "id": "a", "name": "Cafe", "road": "Front Street", "house_number": "1",
            "postcode": "M5J 2H5", "locality": "Toronto", "region": "",
            "country": "Canada", "country_code": "", "provenance_graph_iri": "u",
        }]
        clean = [{
            "id": "a", "name": "Cafe", "road": "Front Street", "house_number": "1",
            "postcode": "M5J 2H5", "locality": "Toronto", "region": "Ontario",
            "country": "Canada", "country_code": "ca", "provenance_graph_iri": "u",
        }]
        out = self._run(
            dirty, clean,
            [{"id": "a", "nar_decision": "keep_clean"}],
        )
        self.assertEqual(out[0]["postcode"], "M5J 2H5")
        self.assertEqual(out[0][FIX_COL], "")

    def test_duplicate_url_gets_same_nar_decision(self):
        dirty = [
            {
                "id": "rep", "name": "A", "road": "Front Street", "house_number": "1",
                "postcode": "M5J 2H5", "locality": "Toronto", "region": "",
                "country": "Canada", "country_code": "", "provenance_graph_iri": "u1",
            },
            {
                "id": "dup", "name": "B", "road": "Front Street", "house_number": "1",
                "postcode": "M5J 2H5", "locality": "Toronto", "region": "",
                "country": "Canada", "country_code": "", "provenance_graph_iri": "u2",
            },
        ]
        clean = [
            {
                "id": "rep", "name": "A", "road": "Front Street", "house_number": "1",
                "postcode": "M5J 2H6", "locality": "Toronto", "region": "Ontario",
                "country": "Canada", "country_code": "ca", "provenance_graph_iri": "u1",
            },
            {
                "id": "dup", "name": "B", "road": "Front Street", "house_number": "1",
                "postcode": "M5J 2H6", "locality": "Toronto", "region": "Ontario",
                "country": "Canada", "country_code": "ca", "provenance_graph_iri": "u2",
            },
        ]
        out = self._run(
            dirty, clean,
            [{"id": "rep", "nar_decision": "keep_dirty"}],
        )
        self.assertEqual([r[FIX_COL] for r in out], ["keep_dirty, NAR", "keep_dirty, NAR"])
        self.assertEqual([r["postcode"] for r in out], ["M5J 2H5", "M5J 2H5"])

    def test_dirty_copy_is_unchanged_strings(self):
        dirty = [{
            "id": "a", "name": "Cafe", "road": "Front Street", "house_number": "1",
            "postcode": "M5J 2H5", "locality": "Toronto", "region": "",
            "country": "Canada", "country_code": "", "provenance_graph_iri": "u",
        }]
        clean = [{
            "id": "a", "name": "Cafe", "road": "Front Street", "house_number": "1",
            "postcode": "M5J 2H5", "locality": "Toronto", "region": "Ontario",
            "country": "Canada", "country_code": "ca", "provenance_graph_iri": "u",
        }]
        self._run(dirty, clean, [{"id": "a", "nar_decision": "confirm"}])
        with self.out_dirty.open(newline="", encoding="utf-8") as f:
            row = next(csv.DictReader(f))
        self.assertEqual(row["postcode"], "M5J 2H5")
        self.assertEqual(row["country_code"], "")
        self.assertNotIn(FIX_COL, row)

if __name__ == "__main__":
    unittest.main()
