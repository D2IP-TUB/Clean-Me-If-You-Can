"""Locality matching tests for France, Spain, and Australia."""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from countries import AU, ES, FR
from fix_localities import (
    Gazetteer,
    SettlementHit,
    classify,
    fix_row,
    load_gazetteer,
    pc_ok,
    strip_alias,
)
from io_csv import invert_article_name, names_match, title_locality


def _gaz(**kwargs) -> Gazetteer:
    return Gazetteer(
        settlements=kwargs.get("settlements", {}),
        admin_names=kwargs.get("admin_names", {}),
        postcodes=kwargs.get("postcodes", {}),
        capital_collapse=kwargs.get("capital_collapse", {}),
        locality_names=kwargs.get("locality_names", {}),
    )


class NamesMatchTests(unittest.TestCase):
    def test_trailing_number_is_not_part_of_the_name(self):
        self.assertTrue(names_match("Toledo", "Toledo 12"))
        self.assertFalse(names_match("Cockburn", "Cockburn Central"))


class StripAliasTests(unittest.TestCase):
    def test_city_of_prefix(self):
        self.assertEqual(strip_alias("City of Brisbane", set()), "Brisbane")


class SpainNameTests(unittest.TestCase):
    def test_invert_galician_article(self):
        self.assertEqual(invert_article_name("Coruña, A"), "A Coruña")
        self.assertEqual(invert_article_name("A Coruña"), "Coruña, A")

    def test_bilingual_slash_classifies_as_settlement(self):
        gaz = _gaz(
            settlements={
                "gijón": SettlementHit("Gijón", frozenset(), frozenset()),
            }
        )
        self.assertEqual(classify(gaz, ES, "Gijón / Xixón"), "settlement")
        self.assertEqual(classify(gaz, ES, "A Coruña"), "unmatched")
        gaz.settlements["coruña, a"] = SettlementHit("Coruña, A", frozenset(), frozenset())
        self.assertEqual(classify(gaz, ES, "A Coruña"), "settlement")


class AustraliaGrainTests(unittest.TestCase):
    def test_brisbane_city_is_a_settlement(self):
        gaz = _gaz(
            settlements={
                "brisbane": SettlementHit("Brisbane", frozenset(), frozenset({"Queensland"})),
                "brisbane city": SettlementHit("Brisbane", frozenset(), frozenset({"Queensland"})),
                "west end": SettlementHit("West End", frozenset(), frozenset({"Queensland"})),
            },
            admin_names={"brisbane": "Brisbane"},
            postcodes={
                "4101": {
                    "populated_place": "West End",
                    "populated_place_type": "locality",
                    "district_borough": "",
                    "county_unitary": "Queensland",
                    "region": "Queensland",
                    "country": "Australia",
                    "ambiguous": False,
                }
            },
            capital_collapse=AU.capital_collapse,
        )
        row = fix_row(
            gaz,
            AU,
            clean_locality="Brisbane",
            dirty_locality="Tivoli",
            clean_postcode="4101",
            dirty_postcode="4101",
        )
        self.assertEqual(row["rule"], "keep")
        self.assertEqual(row["new_locality"], "Brisbane")

    def test_city_of_unknown_lga_not_stripped_to_token(self):
        gaz = _gaz(settlements={}, admin_names={"canning": "Canning"})
        row = fix_row(
            gaz,
            AU,
            clean_locality="City of Canning",
            dirty_locality="Willetton",
            clean_postcode="",
            dirty_postcode="",
        )
        self.assertEqual(row["new_locality"], "City of Canning")

    def test_unique_postcode_replaces_an_lga_name(self):
        gaz = _gaz(
            settlements={
                "noosaville": SettlementHit("Noosaville", frozenset(), frozenset({"Queensland"})),
            },
            postcodes={
                "4566": {
                    "populated_place": "Noosaville",
                    "populated_place_type": "locality",
                    "district_borough": "",
                    "county_unitary": "Queensland",
                    "region": "Queensland",
                    "country": "Australia",
                    "ambiguous": False,
                },
                "4551": {
                    "populated_place": "",
                    "place_names": ["Kings Beach", "Moffat Beach"],
                    "populated_place_type": "locality",
                    "district_borough": "",
                    "county_unitary": "Queensland",
                    "region": "Queensland",
                    "country": "Australia",
                    "ambiguous": True,
                },
            },
        )
        unique = fix_row(
            gaz,
            AU,
            clean_locality="Noosa Shire",
            dirty_locality="Noosa Shire",
            clean_postcode="4566",
            dirty_postcode="4566",
        )
        self.assertEqual(unique["new_locality"], "Noosaville")
        self.assertEqual(unique["accepted"], "true")
        self.assertEqual(unique["rule"], "postcode")
        shared = fix_row(
            gaz,
            AU,
            clean_locality="Sunshine Coast Regional",
            dirty_locality="Caloundra",
            clean_postcode="4551",
            dirty_postcode="",
        )
        self.assertEqual(shared["new_locality"], "Sunshine Coast Regional")

    def test_council_namesake_without_postcode_evidence_stays(self):
        gaz = _gaz(
            settlements={
                "brisbane": SettlementHit("Brisbane", frozenset(), frozenset({"Queensland"})),
            },
            locality_names={"brisbane": {"queensland": "Brisbane"}},
            postcodes={
                "4032": {
                    "populated_place": "",
                    "place_names": ["Chermside", "Aspley"],
                    "populated_place_type": "locality",
                    "district_borough": "",
                    "county_unitary": "Queensland",
                    "region": "Queensland",
                    "country": "Australia",
                    "ambiguous": True,
                }
            },
        )
        row = fix_row(
            gaz,
            AU,
            clean_locality="City of Brisbane",
            dirty_locality="Wooloowin",
            clean_postcode="4032",
            dirty_postcode="",
        )
        self.assertEqual(row["new_locality"], "City of Brisbane")
        self.assertNotEqual(row["clean_pc_ok"], "ok")

    def test_dirty_suburb_is_used_when_the_postcode_lists_it(self):
        gaz = _gaz(
            settlements={
                "scarborough": SettlementHit("Redcliffe", frozenset(), frozenset({"Queensland"})),
                "stirling": SettlementHit("Stirling", frozenset(), frozenset({"Western Australia"})),
                "brisbane": SettlementHit("Brisbane", frozenset(), frozenset({"Queensland"})),
                "vincent": SettlementHit("Vincent", frozenset(), frozenset({"Queensland"})),
                "aspley": SettlementHit("Aspley", frozenset(), frozenset({"Queensland"})),
            },
            postcodes={
                "6019": {
                    "populated_place": "",
                    "place_names": ["Scarborough", "Wembley Downs"],
                    "populated_place_type": "locality",
                    "district_borough": "",
                    "county_unitary": "Western Australia",
                    "region": "Western Australia",
                    "country": "Australia",
                    "ambiguous": True,
                },
                "4008": {
                    "populated_place": "",
                    "place_names": ["Keperra", "Sunnybank"],
                    "populated_place_type": "locality",
                    "district_borough": "",
                    "county_unitary": "Queensland",
                    "region": "Queensland",
                    "country": "Australia",
                    "ambiguous": True,
                },
                "4034": {
                    "populated_place": "",
                    "place_names": ["Aspley", "Geebung"],
                    "populated_place_type": "locality",
                    "district_borough": "",
                    "county_unitary": "Queensland",
                    "region": "Queensland",
                    "country": "Australia",
                    "ambiguous": True,
                },
                "6016": {
                    "populated_place": "",
                    "place_names": ["Mount Hawthorn", "Glendalough"],
                    "populated_place_type": "locality",
                    "district_borough": "",
                    "county_unitary": "Western Australia",
                    "region": "Western Australia",
                    "country": "Australia",
                    "ambiguous": True,
                },
            },
        )
        listed = fix_row(
            gaz,
            AU,
            clean_locality="City of Stirling",
            dirty_locality="Scarborough",
            clean_postcode="6019",
            dirty_postcode="6019",
        )
        self.assertEqual(listed["new_locality"], "Scarborough")
        self.assertEqual(listed["accepted"], "true")
        self.assertEqual(listed["rule"], "dirty")
        city = fix_row(
            gaz,
            AU,
            clean_locality="City of Brisbane",
            dirty_locality="Brisbane",
            clean_postcode="4008",
            dirty_postcode="",
        )
        self.assertEqual(city["new_locality"], "City of Brisbane")
        self.assertEqual(city["accepted"], "false")
        wrapped = fix_row(
            gaz,
            AU,
            clean_locality="City of Brisbane",
            dirty_locality="Aspley,",
            clean_postcode="4034",
            dirty_postcode="",
        )
        self.assertEqual(wrapped["new_locality"], "Aspley")
        self.assertEqual(wrapped["rule"], "dirty")
        other_state = fix_row(
            gaz,
            AU,
            clean_locality="City of Vincent",
            dirty_locality="Perth",
            clean_postcode="6016",
            dirty_postcode="",
        )
        self.assertEqual(other_state["new_locality"], "City of Vincent")
        mount = fix_row(
            gaz,
            AU,
            clean_locality="City of Vincent",
            dirty_locality="Mt Hawthorn",
            clean_postcode="6016",
            dirty_postcode="",
        )
        self.assertEqual(mount["new_locality"], "Mount Hawthorn")

    def test_scraped_suburb_does_not_block_capital_collapse(self):
        gaz = _gaz(
            settlements={
                "brisbane": SettlementHit("Brisbane", frozenset(), frozenset({"Queensland"})),
                "tivoli": SettlementHit("Tivoli", frozenset(), frozenset({"Queensland"})),
            },
            postcodes={
                "4000": {
                    "populated_place": "Brisbane",
                    "populated_place_type": "locality",
                    "district_borough": "",
                    "county_unitary": "Queensland",
                    "region": "Queensland",
                    "country": "Australia",
                    "ambiguous": False,
                },
                "2000": {
                    "populated_place": "Sydney",
                    "populated_place_type": "locality",
                    "district_borough": "",
                    "county_unitary": "New South Wales",
                    "region": "New South Wales",
                    "country": "Australia",
                    "ambiguous": False,
                },
            },
            capital_collapse=AU.capital_collapse,
        )
        row = fix_row(
            gaz,
            AU,
            clean_locality="Greater Brisbane",
            dirty_locality="Tivoli",
            clean_postcode="4000",
            dirty_postcode="2000",
        )
        self.assertEqual(row["new_locality"], "Brisbane")
        self.assertEqual(row["accepted"], "true")
        self.assertEqual(row["conflict"], "")
        self.assertNotEqual(row["dirty_loc_ok"], "fail")
        self.assertNotEqual(row["dirty_pc_ok"], "fail")

    def test_title_locality_from_gnaf_caps(self):
        self.assertEqual(title_locality("WEST END"), "West End")
        self.assertEqual(title_locality("BRISBANE CITY"), "Brisbane City")


class SpellingAndUnmatchedTests(unittest.TestCase):
    def test_apostrophe_is_not_dropped_to_match_the_gazetteer(self):
        gaz = _gaz(
            settlements={
                "penmarch": SettlementHit("Penmarch", frozenset(), frozenset({"Finistère"})),
            }
        )
        row = fix_row(
            gaz,
            FR,
            clean_locality="Penmarc'h",
            dirty_locality="Penmarc'h",
            clean_postcode="29760",
            dirty_postcode="",
        )
        self.assertEqual(row["new_locality"], "Penmarc'h")
        self.assertEqual(row["accepted"], "true")
        self.assertEqual(row["rule"], "keep")

    def test_article_form_keeps_the_clean_spelling(self):
        gaz = _gaz(
            settlements={
                "coruña, a": SettlementHit("Coruña, A", frozenset(), frozenset({"Galicia"})),
            }
        )
        row = fix_row(
            gaz,
            ES,
            clean_locality="A Coruña",
            dirty_locality="A Coruña",
            clean_postcode="15001",
            dirty_postcode="",
        )
        self.assertEqual(row["new_locality"], "A Coruña")
        self.assertEqual(row["rule"], "keep")

    def test_unmatched_hamlet_uses_scraped_commune(self):
        gaz = _gaz(
            settlements={
                "quiberon": SettlementHit("Quiberon", frozenset(), frozenset({"Bretagne"})),
            },
            postcodes={
                "56170": {
                    "populated_place": "Quiberon",
                    "populated_place_type": "commune",
                    "district_borough": "",
                    "county_unitary": "Morbihan",
                    "region": "Bretagne",
                    "country": "France",
                    "ambiguous": False,
                }
            },
        )
        row = fix_row(
            gaz,
            FR,
            clean_locality="Kermorvan",
            dirty_locality="Quiberon",
            clean_postcode="56170",
            dirty_postcode="",
        )
        self.assertEqual(row["new_locality"], "Quiberon")
        self.assertEqual(row["rule"], "dirty")
        self.assertEqual(row["accepted"], "true")


class PostcodeUniquenessTests(unittest.TestCase):
    def test_ambiguous_postcode_does_not_ok_wrong_suburb(self):
        gaz = _gaz(
            postcodes={
                "3350": {
                    "populated_place": "",
                    "populated_place_type": "",
                    "district_borough": "",
                    "county_unitary": "Victoria",
                    "region": "Victoria",
                    "country": "Australia",
                    "ambiguous": True,
                }
            }
        )
        self.assertEqual(pc_ok(gaz, AU, "Golden Point", gaz.lookup_postcode("3350"), required=True), "fail")

    def test_listed_locality_confirms_a_shared_postcode(self):
        gaz = _gaz(
            postcodes={
                "4552": {
                    "populated_place": "",
                    "place_names": ["Maleny", "Conondale"],
                    "populated_place_type": "locality",
                    "district_borough": "",
                    "county_unitary": "Queensland",
                    "region": "Queensland",
                    "country": "Australia",
                    "ambiguous": True,
                }
            }
        )
        self.assertEqual(pc_ok(gaz, AU, "Maleny", gaz.lookup_postcode("4552"), required=True), "ok")
        self.assertEqual(pc_ok(gaz, AU, "Brisbane", gaz.lookup_postcode("4552"), required=True), "fail")


class AliasIndexTests(unittest.TestCase):
    def test_main_name_is_not_replaced_by_an_earlier_alias(self):
        with tempfile.TemporaryDirectory() as tmp:
            derived = Path(tmp)
            (derived / "settlements.csv").write_text(
                "name1,name2,local_type,district_borough,county_unitary,country,id\n"
                "Main Beach,Surfers Paradise,G,,Queensland,Australia,alias-first\n"
                "Surfers Paradise,Bundall,G,,Queensland,Australia,main\n",
                encoding="utf-8",
            )
            (derived / "admin_units.csv").write_text(
                "name,role,n_settlement_children,also_settlement_name,example_children\n",
                encoding="utf-8",
            )
            (derived / "postcode_to_place.csv").write_text(
                "postcode,populated_place,populated_place_type,district_borough,"
                "county_unitary,region,country\n",
                encoding="utf-8",
            )
            gaz = load_gazetteer(derived, AU)
        self.assertEqual(gaz.settlement("Surfers Paradise").name1, "Surfers Paradise")
        self.assertEqual(gaz.settlement("Main Beach").name1, "Main Beach")
        self.assertEqual(gaz.settlement("Bundall").name1, "Surfers Paradise")


class PostcodePlaceTests(unittest.TestCase):
    def test_same_province_does_not_confirm_a_different_place(self):
        gaz = _gaz(
            settlements={
                "burgos": SettlementHit("Burgos", frozenset({"Burgos"}), frozenset({"Castilla y León"})),
                "villarcayo": SettlementHit(
                    "Villarcayo", frozenset({"Burgos"}), frozenset({"Castilla y León"})
                ),
            },
            postcodes={
                "09550": {
                    "populated_place": "Villarcayo",
                    "place_names": ["Villarcayo"],
                    "populated_place_type": "geonames",
                    "district_borough": "Burgos",
                    "county_unitary": "Castilla y León",
                    "region": "Castilla y León",
                    "country": "Spain",
                    "ambiguous": False,
                }
            },
        )
        row = gaz.lookup_postcode("09550")
        self.assertEqual(pc_ok(gaz, ES, "Villarcayo", row, required=True), "ok")
        self.assertEqual(pc_ok(gaz, ES, "Burgos", row, required=True), "fail")

    def test_district_match_when_the_postcode_names_no_place(self):
        gaz = _gaz(
            settlements={
                "esher": SettlementHit("Esher", frozenset({"Elmbridge"}), frozenset()),
            },
            postcodes={
                "KT109QE": {
                    "populated_place": "",
                    "place_names": [],
                    "populated_place_type": "",
                    "district_borough": "Elmbridge",
                    "county_unitary": "Surrey",
                    "region": "",
                    "country": "United Kingdom",
                    "ambiguous": False,
                }
            },
        )
        self.assertEqual(
            pc_ok(gaz, ES, "Esher", gaz.lookup_postcode("KT109QE"), required=True),
            "ok",
        )

    def test_capital_collapse_source_still_confirms_the_city(self):
        gaz = _gaz(
            settlements={
                "sydney": SettlementHit("Sydney", frozenset(), frozenset({"New South Wales"})),
            },
            postcodes={
                "2150": {
                    "populated_place": "Parramatta",
                    "place_names": ["Parramatta"],
                    "populated_place_type": "locality",
                    "district_borough": "",
                    "county_unitary": "Greater Sydney",
                    "region": "New South Wales",
                    "country": "Australia",
                    "ambiguous": False,
                }
            },
            capital_collapse=AU.capital_collapse,
        )
        self.assertEqual(
            pc_ok(gaz, AU, "Sydney", gaz.lookup_postcode("2150"), required=True),
            "ok",
        )


if __name__ == "__main__":
    unittest.main()
