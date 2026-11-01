"""Spelling, fall-through, native-language, and label-refresh tests."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from countries import ES, FR
from fix_localities import Gazetteer, SettlementHit, fix_row
from fix_regions import decide
from io_csv import in_native_script, names_match, richer_spelling
from refresh_labels import relabel


def _pc(place, **extra):
    row = {
        "populated_place": place,
        "place_names": [place],
        "populated_place_type": "",
        "district_borough": "",
        "county_unitary": "",
        "region": "",
        "country": "",
        "ambiguous": False,
    }
    row.update(extra)
    return row


def _gaz(settlements, postcodes=None, admin=None):
    return Gazetteer(
        settlements={key.casefold(): SettlementHit(name, frozenset(), frozenset()) for key, name in settlements.items()},
        admin_names=admin or {},
        postcodes=postcodes or {},
        capital_collapse={},
    )


class RicherSpellingTests(unittest.TestCase):
    def test_gazetteer_without_accent_does_not_win(self):
        self.assertEqual(richer_spelling("Les Epesses", "Les Épesses"), "Les Épesses")
        self.assertEqual(richer_spelling("Penmarch", "Penmarc'h"), "Penmarc'h")

    def test_all_caps_scrape_is_not_a_source(self):
        self.assertEqual(richer_spelling("Les Epesses", "LES ÉPESSES"), "Les Epesses")

    def test_gazetteer_hyphens_still_win(self):
        self.assertEqual(richer_spelling("Crêts en Belledonne", "Crêts-en-Belledonne"), "Crêts en Belledonne")
        self.assertEqual(richer_spelling("Bazouges-la-Pérouse", "Bazouges la Perouse"), "Bazouges-la-Pérouse")

    def test_different_places_are_not_merged(self):
        self.assertEqual(richer_spelling("Quiberon", "Kermorvan"), "Quiberon")

    def test_names_match_folds_accents(self):
        self.assertTrue(names_match("Les Épesses", "Les Epesses"))
        self.assertFalse(names_match("Quiberon", "Kermorvan"))


class FranceSpellingTests(unittest.TestCase):
    def test_clean_accents_are_kept_when_gazetteer_lost_them(self):
        gaz = _gaz(
            {"moliets-et-maa": "Moliets-et-Maa"},
            {"40660": _pc("Moliets-et-Maa")},
        )
        row = fix_row(
            gaz, FR,
            clean_locality="Moliets-et-Maâ",
            dirty_locality="MOLIETS-ET-MAA",
            clean_postcode="40660",
            dirty_postcode="40660",
        )
        self.assertEqual(row["new_locality"], "Moliets-et-Maâ")

    def test_hamlet_becomes_commune_with_scraped_accents(self):
        gaz = _gaz(
            {"les epesses": "Les Epesses"},
            {"85590": _pc("Les Epesses")},
        )
        row = fix_row(
            gaz, FR,
            clean_locality="Le Hameau",
            dirty_locality="Les Épesses",
            clean_postcode="85590",
            dirty_postcode="",
        )
        self.assertEqual(row["new_locality"], "Les Épesses")


class NativeLanguageTests(unittest.TestCase):
    def test_scripts(self):
        self.assertTrue(in_native_script("Plombières-les-Bains", "fr"))
        self.assertFalse(in_native_script("巴黎", "fr"))
        self.assertFalse(in_native_script("서울", "es"))

    def test_foreign_script_proposal_is_not_applied(self):
        gaz = _gaz({"巴黎": "巴黎"}, {"75001": _pc("巴黎")})
        row = fix_row(
            gaz, FR,
            clean_locality="Le Hameau",
            dirty_locality="巴黎",
            clean_postcode="75001",
            dirty_postcode="",
        )
        self.assertEqual(row["new_locality"], "Le Hameau")


class SpainPostcodeTests(unittest.TestCase):
    def test_clean_code_not_in_table_takes_scraped_code_of_same_region(self):
        pcs = {"45006": {"region": "Castilla-La Mancha", "county_unitary": "", "district_borough": "", "populated_place": "Toledo"}}
        new_region, new_pc, rule, _ = decide(ES, "Castilla-La Mancha", "45090", pcs, None, "45006", "Toledo")
        self.assertEqual((new_region, new_pc, rule), ("Castilla-La Mancha", "45006", "dirty"))

    def test_scraped_code_of_another_region_is_not_used(self):
        pcs = {"28010": {"region": "Madrid", "county_unitary": "", "district_borough": "", "populated_place": "Madrid"}}
        new_region, new_pc, rule, _ = decide(ES, "Castilla-La Mancha", "45090", pcs, None, "28010", "Toledo")
        self.assertEqual((new_pc, rule), ("45090", "keep"))


class RelabelTests(unittest.TestCase):
    def test_equal_ignoring_case_is_clean(self):
        self.assertEqual(relabel("PIROU", "Pirou", "Typo", None), ("Clean", True))

    def test_was_clean_but_value_changed_is_not_clean(self):
        label, certain = relabel("Kermorvan", "Quiberon", "Clean", None)
        self.assertEqual((label, certain), ("Unlabeled", False))

    def test_other_labels_are_kept(self):
        self.assertEqual(relabel("Gold Coast", "Surfers Paradise", "Token_Subset", None), ("Token_Subset", False))


if __name__ == "__main__":
    unittest.main()
