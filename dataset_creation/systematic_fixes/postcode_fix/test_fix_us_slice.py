import csv
import tempfile
import unittest
from pathlib import Path

from fix_us_slice import (
    FIX_COL,
    address_key,
    choose_fix,
    is_fight,
    load_nad_by_id,
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
    def test_nad_keep_clean_wins(self):
        self.assertEqual(choose_fix("keep_clean"), "keep_clean, NAD")

    def test_nad_keep_dirty(self):
        self.assertEqual(choose_fix("keep_dirty"), "keep_dirty, NAD")

class FightAndKeyTests(unittest.TestCase):
    def test_blank_dirty_is_a_fight(self):
        self.assertTrue(is_fight("", "75028"))
        self.assertFalse(is_fight("75028", "75028"))
        self.assertFalse(is_fight("75028-1234", "75028"))

    def test_leading_zero_zip_stays_in_key_as_zip5(self):
        dirty = {"house_number": "", "road": "", "locality": "", "region": "", "postcode": ""}
        clean = {
            "house_number": "29", "road": "Federal Street", "locality": "Brunswick",
            "region": "Maine", "postcode": "04011",
        }
        self.assertEqual(address_key(dirty, clean)[0], "04011")


class RewriteTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.dirty = self.root / "slice_us_dirty.csv"
        self.clean = self.root / "slice_us_clean.csv"
        self.nad = self.root / "unique_nad.csv"
        self.out_dirty = self.root / "slice_us_dirty_fixed.csv"
        self.out_clean = self.root / "slice_us_clean_fixed.csv"

    def tearDown(self):
        self.tmp.cleanup()

    def _run(self, dirty_rows, clean_rows, nad_rows):
        _write_csv(self.dirty, SLICE_FIELDS, dirty_rows)
        _write_csv(self.clean, SLICE_FIELDS, clean_rows)
        _write_csv(
            self.nad,
            ["id", "nad_decision", "dirty_zip", "clean_zip", "kind"],
            nad_rows,
        )
        rewrite_pair(
            self.dirty, self.clean, self.nad, self.out_dirty, self.out_clean,
        )
        with self.out_clean.open(newline="", encoding="utf-8") as f:
            return list(csv.DictReader(f))

    def test_keep_dirty_writes_zip5_not_plus4(self):
        dirty = [{
            "id": "a", "name": "Cafe", "road": "Main St", "house_number": "1",
            "postcode": "10001-1234", "locality": "New York", "region": "",
            "country": "United States", "country_code": "", "provenance_graph_iri": "u",
        }]
        clean = [{
            "id": "a", "name": "Cafe", "road": "Main St", "house_number": "1",
            "postcode": "10002", "locality": "New York", "region": "New York",
            "country": "United States", "country_code": "us", "provenance_graph_iri": "u",
        }]
        out = self._run(
            dirty, clean,
            [{"id": "a", "nad_decision": "keep_dirty", "dirty_zip": "10001",
              "clean_zip": "10002", "kind": "both_differ"}],
        )
        self.assertEqual(out[0]["postcode"], "10001")
        self.assertEqual(out[0][FIX_COL], "keep_dirty, NAD")
        self.assertEqual(out[0]["house_number"], "1")
        self.assertEqual(out[0]["country_code"], "us")

    def test_keep_dirty_blank_does_not_wipe_clean(self):
        dirty = [{
            "id": "a", "name": "Fenway Park", "road": "Lansdowne Street",
            "house_number": "4", "postcode": "", "locality": "Boston", "region": "",
            "country": "United States", "country_code": "", "provenance_graph_iri": "u",
        }]
        clean = [{
            "id": "a", "name": "Fenway Park", "road": "Lansdowne Street",
            "house_number": "4", "postcode": "02215", "locality": "Boston",
            "region": "Massachusetts", "country": "United States",
            "country_code": "us", "provenance_graph_iri": "u",
        }]
        out = self._run(
            dirty, clean,
            [{"id": "a", "nad_decision": "keep_dirty", "dirty_zip": "",
              "clean_zip": "02215", "kind": "dirty_blank"}],
        )
        self.assertEqual(out[0]["postcode"], "02215")
        self.assertEqual(out[0][FIX_COL], "")

    def test_keep_dirty_unpadded_zips_are_zip5(self):
        dirty = [{
            "id": "a", "name": "Inn", "road": "St Botolph", "house_number": "1",
            "postcode": "2116", "locality": "Boston", "region": "",
            "country": "United States", "country_code": "", "provenance_graph_iri": "u",
        }]
        clean = [{
            "id": "a", "name": "Inn", "road": "St Botolph", "house_number": "1",
            "postcode": "02115", "locality": "Boston", "region": "Massachusetts",
            "country": "United States", "country_code": "us", "provenance_graph_iri": "u",
        }]
        out = self._run(
            dirty, clean,
            [{"id": "a", "nad_decision": "keep_dirty", "dirty_zip": "02116",
              "clean_zip": "02115", "kind": "both_differ"}],
        )
        self.assertEqual(out[0]["postcode"], "02116")
        self.assertEqual(out[0][FIX_COL], "keep_dirty, NAD")

    def test_keep_dirty_junk_leaves_clean(self):
        dirty = [{
            "id": "a", "name": "Club", "road": "Main", "house_number": "1",
            "postcode": "-", "locality": "Cleveland", "region": "",
            "country": "United States", "country_code": "", "provenance_graph_iri": "u",
        }]
        clean = [{
            "id": "a", "name": "Club", "road": "Main", "house_number": "1",
            "postcode": "44113", "locality": "Cleveland", "region": "Ohio",
            "country": "United States", "country_code": "us", "provenance_graph_iri": "u",
        }]
        out = self._run(
            dirty, clean,
            [{"id": "a", "nad_decision": "keep_dirty", "dirty_zip": "-",
              "clean_zip": "44113", "kind": "both_differ"}],
        )
        self.assertEqual(out[0]["postcode"], "44113")
        self.assertEqual(out[0][FIX_COL], "")

    def test_keep_clean_leaves_postcode(self):
        dirty = [{
            "id": "a", "name": "Cafe", "road": "Main St", "house_number": "1",
            "postcode": "", "locality": "Austin", "region": "",
            "country": "United States", "country_code": "", "provenance_graph_iri": "u",
        }]
        clean = [{
            "id": "a", "name": "Cafe", "road": "Main St", "house_number": "1",
            "postcode": "78701", "locality": "Austin", "region": "Texas",
            "country": "United States", "country_code": "us", "provenance_graph_iri": "u",
        }]
        out = self._run(
            dirty, clean,
            [{"id": "a", "nad_decision": "keep_clean", "dirty_zip": "",
              "clean_zip": "78701", "kind": "dirty_blank"}],
        )
        self.assertEqual(out[0]["postcode"], "78701")
        self.assertEqual(out[0][FIX_COL], "keep_clean, NAD")

    def test_agree_row_is_untouched(self):
        dirty = [{
            "id": "a", "name": "Cafe", "road": "Main St", "house_number": "1",
            "postcode": "78701", "locality": "Austin", "region": "",
            "country": "United States", "country_code": "", "provenance_graph_iri": "u",
        }]
        clean = [{
            "id": "a", "name": "Cafe", "road": "Main St", "house_number": "1",
            "postcode": "78701", "locality": "Austin", "region": "Texas",
            "country": "United States", "country_code": "us", "provenance_graph_iri": "u",
        }]
        out = self._run(
            dirty, clean,
            [{"id": "a", "nad_decision": "keep_clean", "dirty_zip": "78701",
              "clean_zip": "78701", "kind": "agree"}],
        )
        self.assertEqual(out[0]["postcode"], "78701")
        self.assertEqual(out[0][FIX_COL], "")

    def test_duplicate_url_gets_same_nad_decision(self):
        dirty = [
            {
                "id": "rep", "name": "A", "road": "Main St", "house_number": "1",
                "postcode": "10001", "locality": "New York", "region": "",
                "country": "United States", "country_code": "", "provenance_graph_iri": "u1",
            },
            {
                "id": "dup", "name": "B", "road": "Main St", "house_number": "1",
                "postcode": "10001", "locality": "New York", "region": "",
                "country": "United States", "country_code": "", "provenance_graph_iri": "u2",
            },
        ]
        clean = [
            {
                "id": "rep", "name": "A", "road": "Main St", "house_number": "1",
                "postcode": "10002", "locality": "New York", "region": "New York",
                "country": "United States", "country_code": "us", "provenance_graph_iri": "u1",
            },
            {
                "id": "dup", "name": "B", "road": "Main St", "house_number": "1",
                "postcode": "10002", "locality": "New York", "region": "New York",
                "country": "United States", "country_code": "us", "provenance_graph_iri": "u2",
            },
        ]
        out = self._run(
            dirty, clean,
            [{"id": "rep", "nad_decision": "keep_dirty", "dirty_zip": "10001",
              "clean_zip": "10002", "kind": "both_differ"}],
        )
        self.assertEqual([r[FIX_COL] for r in out], ["keep_dirty, NAD", "keep_dirty, NAD"])
        self.assertEqual([r["postcode"] for r in out], ["10001", "10001"])

    def test_dirty_copy_is_unchanged_strings(self):
        dirty = [{
            "id": "a", "name": "Cafe", "road": "Main St", "house_number": "1",
            "postcode": "04011", "locality": "Brunswick", "region": "",
            "country": "United States", "country_code": "", "provenance_graph_iri": "u",
        }]
        clean = [{
            "id": "a", "name": "Cafe", "road": "Main St", "house_number": "1",
            "postcode": "04011", "locality": "Brunswick", "region": "Maine",
            "country": "United States", "country_code": "us", "provenance_graph_iri": "u",
        }]
        self._run(dirty, clean, [{"id": "a", "nad_decision": "confirm"}])
        with self.out_dirty.open(newline="", encoding="utf-8") as f:
            row = next(csv.DictReader(f))
        self.assertEqual(row["postcode"], "04011")
        self.assertEqual(row["country_code"], "")
        self.assertNotIn(FIX_COL, row)

if __name__ == "__main__":
    unittest.main()
