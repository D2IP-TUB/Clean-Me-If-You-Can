"""Dirty fields must not veto a clean-postcode locality rewrite."""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from fix_uk_localities import (
    Gazetteer,
    SettlementHit,
    adjust_repaired_row,
    classify,
    display_place,
    fix_row,
    load_gazetteer,
    load_ni_placenames,
    unmatched_configured_ids,
    drop_cell_label_addresses,
    drop_csv_ids,
    row_value,
)


def _pc(place: str, *, district: str = "", county: str = "") -> dict[str, str]:
    return {
        "populated_place": place,
        "populated_place_type": "",
        "district_borough": district,
        "county_unitary": county,
        "region": "",
        "country": "United Kingdom",
    }


def _gaz() -> Gazetteer:
    return Gazetteer(
        settlements={
            "edinburgh": SettlementHit(
                "Edinburgh", frozenset({"City of Edinburgh"}), frozenset()
            ),
            "currie": SettlementHit(
                "Currie", frozenset({"City of Edinburgh"}), frozenset()
            ),
            "nottingham": SettlementHit(
                "Nottingham", frozenset({"City of Nottingham"}), frozenset()
            ),
            "sherwood": SettlementHit(
                "Sherwood", frozenset({"City of Nottingham"}), frozenset()
            ),
        },
        admin_names={
            "greater london": "Greater London",
            "city of edinburgh": "City of Edinburgh",
            "city of nottingham": "City of Nottingham",
        },
        london_boroughs={"city of westminster": "City of Westminster"},
        postcodes={
            "WC2B4BZ": _pc(
                "City of Westminster",
                district="City of Westminster",
                county="Greater London",
            ),
            "EH13BG": _pc("Edinburgh", district="City of Edinburgh"),
            "NG52JL": _pc("Nottingham", district="City of Nottingham"),
            "NG91AA": _pc("Beeston", district="Broxtowe"),
            "B147EG": _pc("Birmingham"),
        },
    )


class NorthernIrelandTests(unittest.TestCase):
    def test_osni_name_is_kept_and_does_not_replace_gb_homonym(self):
        import tempfile
        from pathlib import Path

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "ni.csv"
            path.write_text(
                "PLACENAME,X,Y,OBJECTID\nBELFAST,1,2,1\nNEWCASTLE,3,4,2\n",
                encoding="utf-8",
            )
            buckets = {
                "newcastle": {
                    "name1": "Newcastle",
                    "districts": set(),
                    "counties": {"Tyne and Wear"},
                }
            }
            added = load_ni_placenames(path, buckets)
        self.assertEqual(added, 1)
        self.assertEqual(buckets["belfast"]["name1"], "Belfast")
        self.assertEqual(buckets["belfast"]["counties"], {"Northern Ireland"})
        self.assertEqual(buckets["newcastle"]["name1"], "Newcastle")
        self.assertEqual(buckets["newcastle"]["counties"], {"Tyne and Wear"})

    def test_slash_form_matches_one_known_side(self):
        gaz = _gaz()
        gaz.settlements["londonderry"] = SettlementHit(
            "Londonderry", frozenset(), frozenset({"Northern Ireland"})
        )
        gaz.settlements["rosslea"] = SettlementHit(
            "Rosslea", frozenset(), frozenset({"Northern Ireland"})
        )
        self.assertEqual(classify(gaz, "Derry/Londonderry"), "settlement")
        self.assertEqual(classify(gaz, "Roslea / Rosslea"), "settlement")
        result = fix_row(
            gaz,
            clean_locality="Derry/Londonderry",
            dirty_locality="Derry",
            clean_postcode="BT48 6DQ",
            dirty_postcode="BT48 6DQ",
        )
        self.assertEqual(result["new_locality"], "Derry/Londonderry")
        self.assertEqual(result["accepted"], "true")
        self.assertEqual(result["rule"], "keep")

    def test_display_place_keeps_apostrophes_and_macosquin(self):
        self.assertEqual(display_place("HELEN'S BAY"), "Helen's Bay")
        self.assertEqual(display_place("O'NEILL"), "O'Neill")
        self.assertEqual(display_place("MACOSQUIN"), "Macosquin")


class DirtyDoesNotVetoTests(unittest.TestCase):
    def test_missing_nearby_dirty_postcode_does_not_block_london(self):
        result = fix_row(
            _gaz(),
            clean_locality="Greater London",
            dirty_locality="London",
            clean_postcode="WC2B 4BZ",
            dirty_postcode="WC2B 4RH",
        )
        self.assertEqual(result["new_locality"], "London")
        self.assertEqual(result["accepted"], "true")
        self.assertEqual(result["conflict"], "")
        self.assertNotEqual(result["dirty_pc_ok"], "fail")

    def test_dirty_suburb_does_not_block_city_alias(self):
        result = fix_row(
            _gaz(),
            clean_locality="City of Edinburgh",
            dirty_locality="Currie",
            clean_postcode="EH1 3BG",
            dirty_postcode="EH1 3BG",
        )
        self.assertEqual(result["new_locality"], "Edinburgh")
        self.assertEqual(result["accepted"], "true")
        self.assertEqual(result["conflict"], "")
        self.assertNotEqual(result["dirty_loc_ok"], "fail")

    def test_dirty_postcode_in_another_city_does_not_block(self):
        result = fix_row(
            _gaz(),
            clean_locality="Greater London",
            dirty_locality="London",
            clean_postcode="WC2B 4BZ",
            dirty_postcode="B14 7EG",
        )
        self.assertEqual(result["new_locality"], "London")
        self.assertEqual(result["accepted"], "true")
        self.assertEqual(result["conflict"], "")
        self.assertNotEqual(result["dirty_pc_ok"], "fail")

    def test_greater_london_with_postcode_missing_from_gazetteer_is_london(self):
        result = fix_row(
            _gaz(),
            clean_locality="Greater London",
            dirty_locality="London",
            clean_postcode="W6 7BY",
            dirty_postcode="",
        )
        self.assertEqual(result["new_locality"], "London")
        self.assertEqual(result["accepted"], "true")
        self.assertEqual(result["conflict"], "")

    def test_other_london_admin_with_missing_postcode_is_london(self):
        result = fix_row(
            _gaz(),
            clean_locality="City of Westminster",
            dirty_locality="London",
            clean_postcode="W1W 8HA",
            dirty_postcode="",
        )
        self.assertEqual(result["new_locality"], "London")
        self.assertEqual(result["accepted"], "true")
        self.assertEqual(result["conflict"], "")

    def test_london_postcode_outside_london_still_rejects(self):
        result = fix_row(
            _gaz(),
            clean_locality="Greater London",
            dirty_locality="London",
            clean_postcode="B14 7EG",
            dirty_postcode="",
        )
        self.assertEqual(result["new_locality"], "Greater London")
        self.assertEqual(result["accepted"], "false")
        self.assertEqual(result["conflict"], "clean_pc_mismatch")

    def test_nottingham_alias_when_postcodes_do_not_agree(self):
        result = fix_row(
            _gaz(),
            clean_locality="City of Nottingham",
            dirty_locality="Nottingham",
            clean_postcode="NG9 1AA",
            dirty_postcode="",
        )
        self.assertEqual(result["new_locality"], "Nottingham")
        self.assertEqual(result["accepted"], "true")
        self.assertEqual(result["rule"], "alias")
        self.assertEqual(result["conflict"], "")

    def test_other_city_postcode_mismatch_still_rejects(self):
        result = fix_row(
            _gaz(),
            clean_locality="City of Edinburgh",
            dirty_locality="Currie",
            clean_postcode="B14 7EG",
            dirty_postcode="NG5 2JL",
        )
        self.assertEqual(result["new_locality"], "City of Edinburgh")
        self.assertEqual(result["accepted"], "false")
        self.assertEqual(result["conflict"], "clean_pc_mismatch")

    def test_missing_postcode_accepts_city_alias_when_scraped_matches(self):
        result = fix_row(
            _gaz(),
            clean_locality="City of Nottingham",
            dirty_locality="Nottingham",
            clean_postcode="NG1 1HE",
            dirty_postcode="NG1 1HE",
        )
        self.assertEqual(result["new_locality"], "Nottingham")
        self.assertEqual(result["accepted"], "true")
        self.assertEqual(result["conflict"], "")

    def test_both_postcodes_agree_on_the_town_outside_the_city(self):
        result = fix_row(
            _gaz(),
            clean_locality="City of Nottingham",
            dirty_locality="Nottingham",
            clean_postcode="NG9 1AA",
            dirty_postcode="NG9 1AA",
        )
        self.assertEqual(result["new_locality"], "Beeston")
        self.assertEqual(result["accepted"], "true")
        self.assertEqual(result["rule"], "postcode")
        self.assertEqual(result["conflict"], "")


class DistrictTests(unittest.TestCase):
    def test_district_homonym_uses_the_postcode_town(self):
        gaz = _gaz()
        gaz.admin_names["elmbridge"] = "Elmbridge"
        gaz.settlements["elmbridge"] = SettlementHit(
            "Elmbridge", frozenset(), frozenset({"Gloucestershire"})
        )
        gaz.settlements["esher"] = SettlementHit("Esher", frozenset({"Elmbridge"}), frozenset())
        gaz.postcodes["KT109QE"] = _pc("Esher", district="Elmbridge")
        result = fix_row(
            gaz,
            clean_locality="Elmbridge",
            dirty_locality="Surrey",
            clean_postcode="KT10 9QE",
            dirty_postcode="KT10 9QE",
        )
        self.assertEqual(result["new_locality"], "Esher")
        self.assertEqual(result["accepted"], "true")
        self.assertEqual(result["conflict"], "")

    def test_empty_postcode_place_uses_the_sector_town(self):
        gaz = _gaz()
        gaz.admin_names["adur"] = "Adur"
        gaz.postcodes["BN158RA"] = _pc("", district="Adur")
        gaz.postcode_sectors["BN158"] = "Lancing"
        result = fix_row(
            gaz,
            clean_locality="Adur",
            dirty_locality="Lancing",
            clean_postcode="BN15 8RA",
            dirty_postcode="BN15 8RA",
        )
        self.assertEqual(result["new_locality"], "Lancing")
        self.assertEqual(result["accepted"], "true")
        self.assertEqual(result["conflict"], "")

    def test_comma_dirty_town_in_the_district(self):
        gaz = _gaz()
        gaz.admin_names["west lancashire"] = "West Lancashire"
        gaz.settlements["ormskirk"] = SettlementHit(
            "Ormskirk", frozenset({"West Lancashire"}), frozenset()
        )
        gaz.postcodes["L398SE"] = _pc("", district="West Lancashire")
        result = fix_row(
            gaz,
            clean_locality="West Lancashire",
            dirty_locality="Ormskirk, Lancashire",
            clean_postcode="L39 8SE",
            dirty_postcode="L39 8SE",
        )
        self.assertEqual(result["new_locality"], "Ormskirk")
        self.assertEqual(result["accepted"], "true")
        self.assertEqual(result["rule"], "dirty")

    def test_record_name_supplies_the_town_when_the_scrape_is_the_street(self):
        gaz = _gaz()
        gaz.admin_names["east suffolk"] = "East Suffolk"
        gaz.settlements["beccles"] = SettlementHit(
            "Beccles", frozenset({"East Suffolk"}), frozenset()
        )
        gaz.settlements["warwick"] = SettlementHit(
            "Warwick", frozenset({"Warwick"}), frozenset()
        )
        gaz.postcodes["NR347FD"] = _pc("", district="East Suffolk")
        result = fix_row(
            gaz,
            clean_locality="East Suffolk",
            dirty_locality="Warwick",
            clean_postcode="NR34 7FD",
            dirty_postcode="",
            clean_name="Beccles Royals Gymnastics Club",
            dirty_name="Beccles",
        )
        self.assertEqual(result["new_locality"], "Beccles")
        self.assertEqual(result["accepted"], "true")

    def test_city_of_edinburgh_with_no_postcode_place_is_edinburgh(self):
        result = fix_row(
            _gaz(),
            clean_locality="City of Edinburgh",
            dirty_locality="Edimburgo",
            clean_postcode="EH1 1SD",
            dirty_postcode="EH1 1SD",
        )
        self.assertEqual(result["new_locality"], "Edinburgh")
        self.assertEqual(result["accepted"], "true")
        self.assertEqual(result["conflict"], "")

    def test_city_of_edinburgh_keeps_a_town_in_the_postcode_county(self):
        gaz = _gaz()
        gaz.settlements["dalkeith"] = SettlementHit("Dalkeith", frozenset(), frozenset({"Midlothian"}))
        gaz.postcodes["EH221RR"] = _pc("", county="Midlothian")
        result = fix_row(
            gaz,
            clean_locality="City of Edinburgh",
            dirty_locality="Dalkeith",
            clean_postcode="EH22 1RR",
            dirty_postcode="EH22 1RR",
        )
        self.assertEqual(result["new_locality"], "Dalkeith")
        self.assertEqual(result["accepted"], "true")
        self.assertEqual(result["rule"], "dirty")

    def test_hart_district_uses_the_postcode_town(self):
        gaz = _gaz()
        gaz.admin_names["hart"] = "Hart"
        gaz.settlements["hart"] = SettlementHit("Hart", frozenset(), frozenset({"Hartlepool"}))
        gaz.postcodes["GU170AA"] = _pc("Blackwater", district="Hart", county="Hampshire")
        result = fix_row(
            gaz,
            clean_locality="Hart",
            dirty_locality="Camberley",
            clean_postcode="GU17 0AA",
            dirty_postcode="GU17 0AA",
        )
        self.assertEqual(result["new_locality"], "Blackwater")
        self.assertEqual(result["accepted"], "true")

    def test_punctuation_pairs_use_one_open_names_spelling(self):
        gaz = _gaz()
        gaz.settlements["st ives"] = SettlementHit("St Ives", frozenset(), frozenset({"Cornwall"}))
        gaz.settlements["st neots"] = SettlementHit(
            "St Neots", frozenset({"Huntingdonshire"}), frozenset()
        )
        gaz.settlements["wells-next-the-sea"] = SettlementHit(
            "Wells-next-the-Sea", frozenset({"North Norfolk"}), frozenset()
        )
        cases = {
            "St. Ives": "St Ives",
            "St. Neots": "St Neots",
            "Wells-Next-the-Sea": "Wells-next-the-Sea",
            "Lytham St Annes": "Lytham St Anne's",
            "Newark on Trent": "Newark-on-Trent",
        }
        for clean, expected in cases.items():
            result = fix_row(
                gaz,
                clean_locality=clean,
                dirty_locality=clean,
                clean_postcode="",
                dirty_postcode="",
            )
            self.assertEqual(result["new_locality"], expected, clean)


class HighcliffeTests(unittest.TestCase):
    def _gaz(self) -> Gazetteer:
        gaz = _gaz()
        gaz.settlements["christchurch"] = SettlementHit(
            "Christchurch", frozenset(), frozenset({"Dorset"})
        )
        gaz.postcodes["BH235ET"] = _pc("Christchurch", county="Dorset")
        gaz.postcodes["BN34GR"] = _pc("Brighton and Hove")
        return gaz

    def test_highcliffe_becomes_christchurch(self):
        result = fix_row(
            self._gaz(),
            clean_locality="Highcliffe-on-Sea",
            dirty_locality="Christchurch",
            clean_postcode="BH23 5ET",
            dirty_postcode="BH23 5ET",
        )
        self.assertEqual(result["new_locality"], "Christchurch")
        self.assertEqual(result["accepted"], "true")
        self.assertEqual(result["conflict"], "")
        self.assertEqual(result["rule"], "manual")

    def test_other_unmatched_locality_stays(self):
        result = fix_row(
            self._gaz(),
            clean_locality="Portslade by Sea",
            dirty_locality="Hove",
            clean_postcode="BN3 4GR",
            dirty_postcode="BN3 4GR",
        )
        self.assertEqual(result["new_locality"], "Portslade by Sea")
        self.assertEqual(result["accepted"], "false")
        self.assertEqual(result["conflict"], "no_proposal")


class RepairedRowOverrideTests(unittest.TestCase):
    def test_ards_row_becomes_bangor_and_the_other_two_are_dropped(self):
        unresolved = {
            "old_locality": "Ards and North Down District Council",
            "new_locality": "Ards and North Down District Council",
            "proposed": "",
            "accepted": "false",
            "rule": "unresolved",
            "conflict": "no_proposal",
        }
        bangor = adjust_repaired_row("2992b2d3-3186-472e-a7f2-8223ddded687", unresolved)
        self.assertEqual(bangor["new_locality"], "Bangor")
        self.assertEqual(bangor["proposed"], "Bangor")
        self.assertEqual(bangor["accepted"], "true")
        self.assertEqual(bangor["rule"], "manual")
        self.assertEqual(bangor["conflict"], "")
        self.assertEqual(bangor["clean_pc_ok"], "n/a")
        self.assertEqual(bangor["dirty_pc_ok"], "n/a")
        self.assertEqual(bangor["dirty_loc_ok"], "n/a")
        self.assertIsNone(adjust_repaired_row("9e6a3b2d-d5bc-4b23-aed7-5720e4cbfed3", unresolved))
        self.assertIsNone(adjust_repaired_row("c4e27a09-5865-477c-b08b-3aa4722427b0", unresolved))

    def test_unknown_configured_id_is_reported(self):
        self.assertEqual(
            unmatched_configured_ids({"2992b2d3-3186-472e-a7f2-8223ddded687"}),
            [
                "9e6a3b2d-d5bc-4b23-aed7-5720e4cbfed3",
                "c4e27a09-5865-477c-b08b-3aa4722427b0",
            ],
        )
        self.assertEqual(
            unmatched_configured_ids(
                {
                    "2992b2d3-3186-472e-a7f2-8223ddded687",
                    "9e6a3b2d-d5bc-4b23-aed7-5720e4cbfed3",
                    "c4e27a09-5865-477c-b08b-3aa4722427b0",
                }
            ),
            [],
        )


class DropExcludedRowTests(unittest.TestCase):
    def test_dirty_row_is_deleted_and_other_records_stay_byte_for_byte(self):
        import tempfile
        from pathlib import Path

        raw = (
            "id,locality\n"
            "keep,\"\n  Bangor  \"\n"
            "9e6a3b2d-d5bc-4b23-aed7-5720e4cbfed3,Coleraine\n"
            "also,\"\n  still here  \"\n"
        )
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "dirty.csv"
            path.write_text(raw, encoding="utf-8")
            removed = drop_csv_ids(path, {"9e6a3b2d-d5bc-4b23-aed7-5720e4cbfed3"})
            self.assertEqual(removed, 1)
            self.assertEqual(
                path.read_text(encoding="utf-8"),
                "id,locality\nkeep,\"\n  Bangor  \"\nalso,\"\n  still here  \"\n",
            )

    def test_cell_label_copies_are_deleted_and_later_indexes_move(self):
        import tempfile
        from pathlib import Path

        raw = (
            "row_index,new_row_index,feature,dirty_value,clean_value,labels\n"
            "1,0,id,keep,keep,Clean\n"
            "1,0,locality,A,A,Clean\n"
            "2,1,id,drop,9e6a3b2d-d5bc-4b23-aed7-5720e4cbfed3,Clean\n"
            "2,1,locality,Coleraine,Causeway,Language\n"
            "3,2,id,later,later,Clean\n"
            "3,2,name,Treetops,Treetops,Clean\n"
        )
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "labels.csv"
            path.write_text(raw, encoding="utf-8")
            removed = drop_cell_label_addresses(path, {"9e6a3b2d-d5bc-4b23-aed7-5720e4cbfed3"})
            self.assertEqual(removed, 1)
            self.assertEqual(
                path.read_text(encoding="utf-8"),
                "row_index,new_row_index,feature,dirty_value,clean_value,labels\n"
                "1,0,id,keep,keep,Clean\n"
                "1,0,locality,A,A,Clean\n"
                "3,1,id,later,later,Clean\n"
                "3,1,name,Treetops,Treetops,Clean\n",
            )


class AliasIndexTests(unittest.TestCase):
    def test_main_name_is_not_replaced_by_an_earlier_alias(self):
        with tempfile.TemporaryDirectory() as tmp:
            derived = Path(tmp)
            (derived / "settlements.csv").write_text(
                "name1,name2,local_type,district_borough,county_unitary,country\n"
                "Main Beach,Surfers Paradise,Suburban Area,,Queensland,Australia\n"
                "Surfers Paradise,Bundall,Town,,Queensland,Australia\n",
                encoding="utf-8",
            )
            (derived / "admin_units.csv").write_text("name\n", encoding="utf-8")
            (derived / "postcode_to_place.csv").write_text(
                "postcode,populated_place,populated_place_type,district_borough,"
                "county_unitary,region,country\n",
                encoding="utf-8",
            )
            gaz = load_gazetteer(derived, Path(tmp) / "missing-ni.csv")
        self.assertEqual(gaz.settlement("Surfers Paradise").name1, "Surfers Paradise")
        self.assertEqual(gaz.settlement("Bundall").name1, "Surfers Paradise")


class OptionalNameColumnTests(unittest.TestCase):
    def test_missing_name_column_is_empty(self):
        import pandas as pd

        frame = pd.DataFrame({"id": ["a"], "locality": ["London"]})
        self.assertEqual(row_value(frame, 0, "name"), "")
        self.assertEqual(row_value(frame, 0, "locality"), "London")


if __name__ == "__main__":
    unittest.main()
