"""Clean French regions come from the clean postcode or from an INSEE commune code."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from countries import CONFIGS
from fix_regions import decide


def _pc(region: str) -> dict[str, str]:
    return {
        "region": region,
        "county_unitary": region,
        "district_borough": "",
        "populated_place": "",
    }


class FranceRegionTests(unittest.TestCase):
    def test_valid_postcode_sets_region_and_keeps_the_postcode(self):
        region, postcode, rule, conflict = decide(
            CONFIGS["fr"],
            "France métropolitaine",
            "74000",
            {"74000": _pc("Auvergne-Rhône-Alpes")},
        )
        self.assertEqual(region, "Auvergne-Rhône-Alpes")
        self.assertEqual(postcode, "74000")
        self.assertEqual(rule, "postcode")
        self.assertEqual(conflict, "")

    def test_unique_commune_postcode_replaces_an_insee_code(self):
        region, postcode, rule, conflict = decide(
            CONFIGS["fr"],
            "France métropolitaine",
            "74010",
            {},
            {"74010": ("Auvergne-Rhône-Alpes", "74000")},
        )
        self.assertEqual(region, "Auvergne-Rhône-Alpes")
        self.assertEqual(postcode, "74000")
        self.assertEqual(rule, "insee")
        self.assertEqual(conflict, "")

    def test_several_commune_postcodes_set_the_region_only(self):
        region, postcode, rule, conflict = decide(
            CONFIGS["fr"],
            "France métropolitaine",
            "10003",
            {},
            {"10003": ("Grand Est", None)},
        )
        self.assertEqual(region, "Grand Est")
        self.assertEqual(postcode, "10003")
        self.assertEqual(rule, "insee")
        self.assertEqual(conflict, "")

    def test_valid_dirty_postcode_breaks_a_tie(self):
        region, postcode, rule, conflict = decide(
            CONFIGS["fr"],
            "France métropolitaine",
            "83137",
            {"83000": _pc("Provence-Alpes-Côte d'Azur")},
            {"83137": ("Provence-Alpes-Côte d'Azur", None)},
            "83000",
        )
        self.assertEqual(region, "Provence-Alpes-Côte d'Azur")
        self.assertEqual(postcode, "83000")
        self.assertEqual(rule, "dirty")
        self.assertEqual(conflict, "")

    def test_invalid_dirty_postcode_leaves_the_commune_code(self):
        region, postcode, rule, conflict = decide(
            CONFIGS["fr"],
            "France métropolitaine",
            "10003",
            {},
            {"10003": ("Grand Est", None)},
            "13000",
        )
        self.assertEqual(region, "Grand Est")
        self.assertEqual(postcode, "10003")
        self.assertEqual(rule, "insee")
        self.assertEqual(conflict, "")

    def test_valid_dirty_postcode_fills_an_unknown_clean_code(self):
        region, postcode, rule, conflict = decide(
            CONFIGS["fr"],
            "France métropolitaine",
            "06299",
            {"06200": _pc("Provence-Alpes-Côte d'Azur")},
            {},
            "06200",
        )
        self.assertEqual(region, "Provence-Alpes-Côte d'Azur")
        self.assertEqual(postcode, "06200")
        self.assertEqual(rule, "dirty")
        self.assertEqual(conflict, "")

    def test_unknown_code_stays(self):
        region, postcode, rule, conflict = decide(
            CONFIGS["fr"],
            "France métropolitaine",
            "12345",
            {},
            {},
        )
        self.assertEqual(region, "France métropolitaine")
        self.assertEqual(postcode, "12345")
        self.assertEqual(rule, "unresolved")
        self.assertEqual(conflict, "pc_unknown")

    def test_insee_code_does_not_rewrite_an_overseas_region(self):
        region, postcode, rule, conflict = decide(
            CONFIGS["fr"],
            "Saint-Barthélemy",
            "97123",
            {},
            {"97123": ("Guadeloupe", "97100")},
        )
        self.assertEqual(region, "Saint-Barthélemy")
        self.assertEqual(postcode, "97123")
        self.assertEqual(rule, "keep")
        self.assertEqual(conflict, "")

    def test_known_locality_replaces_france_metropolitaine(self):
        region, postcode, rule, conflict = decide(
            CONFIGS["fr"],
            "France métropolitaine",
            "06299",
            {},
            {},
            "06299",
            "Nice",
            {"nice": "Provence-Alpes-Côte d'Azur"},
        )
        self.assertEqual(region, "Provence-Alpes-Côte d'Azur")
        self.assertEqual(postcode, "06299")
        self.assertEqual(rule, "locality")
        self.assertEqual(conflict, "")

    def test_marseille_keeps_a_valid_region_and_takes_the_scraped_postcode(self):
        region, postcode, rule, conflict = decide(
            CONFIGS["fr"],
            "Provence-Alpes-Côte d'Azur",
            "10003",
            {"13003": _pc("Provence-Alpes-Côte d'Azur")},
            {"10003": ("Grand Est", None)},
            "13003",
            "Marseille",
        )
        self.assertEqual(region, "Provence-Alpes-Côte d'Azur")
        self.assertEqual(postcode, "13003")
        self.assertEqual(rule, "dirty")
        self.assertEqual(conflict, "")

    def test_marseille_insee_code_does_not_take_the_aube_region(self):
        region, postcode, rule, conflict = decide(
            CONFIGS["fr"],
            "France métropolitaine",
            "10003",
            {},
            {"10003": ("Grand Est", None)},
            "13000",
            "Marseille",
            {"marseille": "Provence-Alpes-Côte d'Azur"},
        )
        self.assertEqual(region, "Provence-Alpes-Côte d'Azur")
        self.assertEqual(postcode, "10003")
        self.assertEqual(rule, "locality")
        self.assertEqual(conflict, "")

    def test_benidorm_replaces_a_code_that_is_not_a_postcode(self):
        region, postcode, rule, conflict = decide(
            CONFIGS["es"],
            "la Marina Baixa",
            "03053",
            {"03501": _pc("Comunidad Valenciana")},
            {},
            "03501",
            "Benidorm",
        )
        self.assertEqual(region, "Comunitat Valenciana")
        self.assertEqual(postcode, "03501")
        self.assertEqual(rule, "dirty")
        self.assertEqual(conflict, "")



if __name__ == "__main__":
    unittest.main()
