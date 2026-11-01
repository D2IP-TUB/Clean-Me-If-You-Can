import sqlite3
import unittest
import zipfile
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from nad_join import (
    INDEX_FORMAT,
    _install_built_index,
    build_nad_index,
    cities_match,
    decide,
    join_from_index,
    load_query_rows,
    make_key,
    nad_index_rows,
    nad_record,
    norm_city,
    norm_number,
    street_core,
    index_postcode,
    state_abbr,
    zip5,
    norm_street,
)


def _join_nad(queries, csv_body, **kwargs):
    with TemporaryDirectory() as tmp:
        zpath = Path(tmp) / "nad.zip"
        ipath = Path(tmp) / "nad.sqlite"
        with zipfile.ZipFile(zpath, "w") as zf:
            zf.writestr("NAD.txt", csv_body)
        build_nad_index(zpath, ipath)
        return join_from_index(queries, ipath, **kwargs)


class NormalizeTests(unittest.TestCase):
    def test_street_expands_type_and_direction(self):
        self.assertEqual(norm_street("Geary Boulevard"), "GEARY BOULEVARD")
        self.assertEqual(norm_street("GEARY BLVD"), "GEARY BOULEVARD")
        self.assertEqual(norm_street("Eddy St"), "EDDY STREET")
        self.assertEqual(
            street_core("116Th Ave Ne"),
            street_core("116th Avenue Northeast"),
        )
        self.assertEqual(street_core("S 1St Street"), street_core("South 1st Street"))

    def test_number_digits(self):
        self.assertEqual(norm_number("6201"), "6201")
        self.assertEqual(norm_number("51"), "51")

    def test_zip5(self):
        self.assertEqual(zip5("94109.0"), "94109")
        self.assertEqual(zip5("94124-3502"), "94124")
        self.assertEqual(zip5("94121"), "94121")
        # Do not strip every ".0" substring (would turn 10.094109 into 19410).
        self.assertEqual(zip5("10.094109"), "")
        # Float-truncated New England ZIPs need zero-padding.
        self.assertEqual(zip5("2110.0"), "02110")
        self.assertEqual(zip5("2110"), "02110")
        self.assertEqual(zip5("02110"), "02110")
        self.assertEqual(zip5("501"), "00501")

    def test_state_abbr(self):
        self.assertEqual(state_abbr("California"), "CA")
        self.assertEqual(state_abbr("CA"), "CA")
        self.assertEqual(state_abbr("Washington"), "WA")
        self.assertEqual(state_abbr("Ontario"), "ON")
        self.assertEqual(state_abbr("QC"), "QC")

    def test_index_postcode_us_and_ca(self):
        self.assertEqual(index_postcode("94121-3502"), "94121")
        self.assertEqual(index_postcode("M5V 2T6"), "M5V2T6")
        self.assertEqual(index_postcode("m5v"), "M5V")
        self.assertEqual(index_postcode(""), "")

    def test_city_strips_municipality_words(self):
        self.assertEqual(norm_city("City of Albany"), "ALBANY")
        self.assertEqual(norm_city("Village of Floral Park"), "FLORAL PARK")
        self.assertEqual(norm_city("West Hempfield Township"), "WEST HEMPFIELD")
        self.assertEqual(norm_city("Kansas City"), "KANSAS CITY")
        self.assertEqual(norm_city("New York City"), "NEW YORK CITY")
        self.assertEqual(norm_city("Saint Paul"), "ST PAUL")
        self.assertEqual(norm_city("St. Paul"), "ST PAUL")

    def test_cities_match_nyc_boroughs_not_other_towns(self):
        self.assertTrue(cities_match("New York", "Manhattan"))
        self.assertTrue(cities_match("New York", "New York City"))
        self.assertTrue(cities_match("Saint Paul", "St. Paul"))
        self.assertFalse(cities_match("New York", "Buffalo"))
        self.assertFalse(cities_match("Cornwall", "Hartford"))

    def test_street_core_strips_suffix_type(self):
        self.assertEqual(street_core("Geary Boulevard"), "GEARY")
        self.assertEqual(street_core("GEARY BLVD"), "GEARY")
        self.assertEqual(street_core("Eddy St"), "EDDY")

    def test_street_core_strips_dir_when_a_name_token_remains(self):
        self.assertEqual(street_core("South Pearl Street"), "PEARL")
        self.assertEqual(street_core("North Halsted Street"), "HALSTED")

    def test_street_core_keeps_dir_when_rest_is_only_a_number(self):
        self.assertEqual(street_core("West 95th Street"), "W 95")
        self.assertEqual(street_core("South 1st Street"), "S 1")
        self.assertEqual(street_core("116th Ave NE"), "NE 116")

    def test_street_core_trailing_dir_before_type(self):
        self.assertEqual(street_core("Main St"), "MAIN")
        self.assertEqual(street_core("Main St N"), "MAIN")
        self.assertEqual(street_core("N Main St"), "MAIN")
        self.assertEqual(street_core("95th St W"), "W 95")
        self.assertEqual(street_core("W 95th St"), "W 95")
        self.assertEqual(street_core("95th St E"), "E 95")

    def test_street_core_ordinal_without_dir(self):
        self.assertEqual(street_core("8th Street"), "8")
        self.assertEqual(street_core("8 Street"), "8")

    def test_street_core_west_as_the_street_name(self):
        self.assertEqual(street_core("West Street"), "W")


class DecideTests(unittest.TestCase):
    def test_keep_dirty_when_unique_matches_dirty(self):
        self.assertEqual(decide("94114", "94121", {"94114"}), "keep_dirty")

    def test_keep_clean_when_unique_matches_clean(self):
        self.assertEqual(decide("94114", "94121", {"94121"}), "keep_clean")

    def test_no_match(self):
        self.assertEqual(decide("94114", "94121", set()), "no_match")

    def test_has_both(self):
        self.assertEqual(decide("94114", "94121", {"94114", "94121"}), "has_both")

    def test_other_zip(self):
        self.assertEqual(decide("94114", "94121", {"94118"}), "other")

    def test_membership_keep_clean_when_list_contains_clean(self):
        self.assertEqual(decide("", "78203", {"78203", "78205"}), "keep_clean")

    def test_confirm_when_dirty_and_clean_already_match(self):
        self.assertEqual(decide("94121", "94121", {"94121"}), "confirm")

    def test_confirm_when_agree_zip_plus_another(self):
        self.assertEqual(decide("99201", "99201", {"99201", "99202"}), "confirm")

    def test_third_zip_stays_other_even_if_same_zip3(self):
        self.assertEqual(decide("", "66251", {"66211"}), "other")
        self.assertEqual(decide("10001", "94121", {"94118"}), "other")
        self.assertEqual(decide("10001", "94121", {"10018"}), "other")


class CombineResolveTests(unittest.TestCase):
    def test_unique_addresses_drops_id_name_url_dupes(self):
        from compare_nad import unique_addresses
        rows = unique_addresses([
            {"id": "1", "name": "A", "house_number": "1", "road": "Main", "locality": "X",
             "state": "PA", "dirty_zip": "", "clean_zip": "19107", "dirty_house": "", "dirty_road": ""},
            {"id": "2", "name": "B", "house_number": "1", "road": "Main", "locality": "X",
             "state": "PA", "dirty_zip": "19107", "clean_zip": "19107", "dirty_house": "1", "dirty_road": "Main"},
        ])
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["n_dupes"], "2")
        self.assertEqual(rows[0]["dirty_zip"], "19107")


class NadIndexTests(unittest.TestCase):
    def test_nad_record_composes_street_and_prefers_muni_city(self):
        rec = nad_record({
            "Add_Number": "6201",
            "St_PreDir": "",
            "St_Name": "Geary",
            "St_PosTyp": "Blvd",
            "St_PosDir": "",
            "State": "California",
            "Zip_Code": "94121",
            "Inc_Muni": "San Francisco",
            "Post_City": "SF",
        })
        self.assertEqual(rec, (make_key("CA", "6201", "GEARY BOULEVARD"), "SAN FRANCISCO", "94121"))

    def test_nad_index_rows_also_stores_post_city(self):
        rows = nad_index_rows({
            "Add_Number": "6201",
            "St_Name": "Geary",
            "St_PosTyp": "Blvd",
            "State": "CA",
            "Zip_Code": "94121",
            "Inc_Muni": "San Francisco",
            "Post_City": "SF",
        })
        cities = {c for _, c, _ in rows}
        self.assertEqual(cities, {"SAN FRANCISCO", "SF"})
        keys = {k for k, _, _ in rows}
        self.assertEqual(
            keys,
            {
                "F|CA|6201|GEARY BOULEVARD",
                "C|CA|6201|GEARY",
            },
        )

    def test_nad_join_matches_query_with_type_to_index_without_type(self):
        csv_body = (
            "Add_Number,St_Name,St_PosTyp,State,Zip_Code,Inc_Muni\n"
            "6201,GEARY,,CA,94121,San Francisco\n"
        )
        queries = [
            {
                "id": "bc595135",
                "name": "Sullivan",
                "house_number": "6201",
                "road": "Geary Boulevard",
                "locality": "San Francisco",
                "state": "CA",
                "dirty_zip": "94114",
                "clean_zip": "94121",
            }
        ]
        rows = _join_nad(queries, csv_body)
        self.assertEqual(rows[0]["nad_zips"], "94121")
        self.assertEqual(rows[0]["match_method"], "core")
        self.assertEqual(rows[0]["decision"], "other")
        self.assertEqual(rows[0]["n_nad_zips"], "1")

    def test_nad_join_post_city_when_query_uses_postal_name(self):
        csv_body = (
            "Add_Number,St_Name,St_PosTyp,State,Zip_Code,Inc_Muni,Post_City\n"
            "1,MAIN,St,FL,32821,Bay Lake,Orlando\n"
        )
        queries = [
            {
                "id": "epcot",
                "name": "Epcot",
                "house_number": "1",
                "road": "Main Street",
                "locality": "Orlando",
                "state": "FL",
                "dirty_zip": "32821",
                "clean_zip": "32821",
            }
        ]
        rows = _join_nad(queries, csv_body)
        self.assertEqual(rows[0]["decision"], "confirm")

    def test_keeps_only_matching_city(self):
        csv_body = (
            "Add_Number,St_Name,St_PosTyp,State,Zip_Code,Inc_Muni\n"
            "51,S PEARL,St,NY,12207,Albany\n"
            "51,S PEARL,St,NY,12953,Malone\n"
        )
        queries = [
            {
                "id": "3e1da043",
                "name": "MVP Arena",
                "house_number": "51",
                "road": "South Pearl Street",
                "locality": "City of Albany",
                "state": "NY",
                "dirty_zip": "12207",
                "clean_zip": "12202",
            }
        ]
        rows = _join_nad(queries, csv_body)
        self.assertEqual(rows[0]["nad_zips"], "12207")
        self.assertEqual(rows[0]["decision"], "keep_dirty")
        self.assertEqual(rows[0]["match_method"], "exact")
        self.assertEqual(rows[0]["n_nad_zips"], "1")

    def test_dirty_city_only_is_not_exact_keep(self):
        csv_body = (
            "Add_Number,St_Name,St_PosTyp,State,Zip_Code,Inc_Muni\n"
            "51,S PEARL,St,NY,12953,Malone\n"
        )
        queries = [
            {
                "id": "dcity",
                "name": "MVP Arena",
                "house_number": "51",
                "road": "South Pearl Street",
                "locality": "Albany",
                "state": "NY",
                "dirty_zip": "12953",
                "clean_zip": "12207",
                "dirty_locality": "Malone",
            }
        ]
        rows = _join_nad(queries, csv_body)
        self.assertEqual(rows[0]["nad_zips"], "12953")
        self.assertEqual(rows[0]["match_method"], "exact_dirtycity")
        self.assertEqual(rows[0]["decision"], "other")

    def test_clean_city_still_exact_when_dirty_city_differs(self):
        csv_body = (
            "Add_Number,St_Name,St_PosTyp,State,Zip_Code,Inc_Muni\n"
            "51,S PEARL,St,NY,12207,Albany\n"
            "51,S PEARL,St,NY,12953,Malone\n"
        )
        queries = [
            {
                "id": "bothcity",
                "name": "MVP Arena",
                "house_number": "51",
                "road": "South Pearl Street",
                "locality": "Albany",
                "state": "NY",
                "dirty_zip": "12953",
                "clean_zip": "12207",
                "dirty_locality": "Malone",
            }
        ]
        rows = _join_nad(queries, csv_body)
        self.assertEqual(rows[0]["nad_zips"], "12207")
        self.assertEqual(rows[0]["match_method"], "exact")
        self.assertEqual(rows[0]["decision"], "keep_clean")
        self.assertEqual(rows[0]["n_nad_zips"], "1")

    def test_typed_street_is_exact_when_index_has_type(self):
        csv_body = (
            "Add_Number,St_Name,St_PosTyp,State,Zip_Code,Inc_Muni\n"
            "6201,GEARY,Blvd,CA,94121,San Francisco\n"
        )
        queries = [
            {
                "id": "bc595135",
                "name": "Sullivan",
                "house_number": "6201",
                "road": "Geary Boulevard",
                "locality": "San Francisco",
                "state": "CA",
                "dirty_zip": "94114",
                "clean_zip": "94121",
            }
        ]
        rows = _join_nad(queries, csv_body)
        self.assertEqual(rows[0]["decision"], "keep_clean")
        self.assertEqual(rows[0]["match_method"], "exact")
        self.assertEqual(rows[0]["nad_zips"], "94121")
        self.assertIn("F|CA|6201|GEARY BOULEVARD", rows[0]["join_key"])

    def test_north_and_south_main_do_not_share_exact_zips(self):
        csv_body = (
            "Add_Number,St_PreDir,St_Name,St_PosTyp,State,Zip_Code,Inc_Muni\n"
            "100,N,MAIN,St,NY,12207,Albany\n"
            "100,S,MAIN,St,NY,12202,Albany\n"
        )
        queries = [
            {
                "id": "nmain",
                "name": "North",
                "house_number": "100",
                "road": "North Main Street",
                "locality": "Albany",
                "state": "NY",
                "dirty_zip": "12207",
                "clean_zip": "12202",
            }
        ]
        rows = _join_nad(queries, csv_body)
        self.assertEqual(rows[0]["nad_zips"], "12207")
        self.assertEqual(rows[0]["match_method"], "exact")
        self.assertEqual(rows[0]["decision"], "keep_dirty")

    def test_bare_pearl_is_not_exact_against_south_pearl_core(self):
        csv_body = (
            "Add_Number,St_PreDir,St_Name,St_PosTyp,State,Zip_Code,Inc_Muni\n"
            "123,S,PEARL,St,NY,12207,Albany\n"
            "123,,PEARL,Ave,NY,12202,Albany\n"
        )
        queries = [
            {
                "id": "pearl",
                "name": "Pearl",
                "house_number": "123",
                "road": "Pearl",
                "locality": "Albany",
                "state": "NY",
                "dirty_zip": "12207",
                "clean_zip": "12202",
            }
        ]
        rows = _join_nad(queries, csv_body)
        self.assertEqual(rows[0]["match_method"], "core")
        self.assertEqual(rows[0]["decision"], "has_both")
        self.assertIn("C|NY|123|PEARL", rows[0]["join_key"])

    def test_city_core_beats_full_unique_zip_other_town(self):
        csv_body = (
            "Add_Number,St_PreDir,St_Name,St_PosTyp,State,Zip_Code,Inc_Muni\n"
            "51,,PEARL,,NY,11111,Malone\n"
            "51,S,PEARL,St,NY,12207,Albany\n"
        )
        queries = [
            {
                "id": "p",
                "name": "P",
                "house_number": "51",
                "road": "Pearl",
                "locality": "Albany",
                "state": "NY",
                "dirty_zip": "12207",
                "clean_zip": "12202",
            }
        ]
        rows = _join_nad(queries, csv_body, unique_zip_fallback=True)
        self.assertEqual(rows[0]["nad_zips"], "12207")
        self.assertEqual(rows[0]["match_method"], "core")
        self.assertEqual(rows[0]["decision"], "other")

    def test_east_and_west_95th_do_not_share_core(self):
        csv_body = (
            "Add_Number,St_Name,St_PosTyp,St_PosDir,State,Zip_Code,Inc_Muni\n"
            "100,95th,St,W,MN,55416,Minneapolis\n"
            "100,95th,St,E,MN,55417,Minneapolis\n"
        )
        w_query = {
            "id": "w95",
            "name": "West",
            "house_number": "100",
            "road": "95th St W",
            "locality": "Minneapolis",
            "state": "MN",
            "dirty_zip": "55416",
            "clean_zip": "55417",
        }
        prefix_query = dict(w_query, id="w95pre", road="W 95th St")
        rows = _join_nad([w_query], csv_body)
        self.assertEqual(rows[0]["nad_zips"], "55416")
        self.assertEqual(rows[0]["match_method"], "exact")
        self.assertEqual(rows[0]["decision"], "keep_dirty")
        core_rows = _join_nad([prefix_query], csv_body)
        self.assertEqual(core_rows[0]["nad_zips"], "55416")
        self.assertEqual(core_rows[0]["match_method"], "core")
        self.assertIn("C|MN|100|W 95", core_rows[0]["join_key"])

    def test_ignores_row_with_blank_city(self):
        csv_body = (
            "Add_Number,St_Name,St_PosTyp,State,Zip_Code,Inc_Muni\n"
            "30,PINE,St,CT,06111,\n"
        )
        queries = [
            {
                "id": "99395fb0",
                "name": "The Cornwall Library",
                "house_number": "30",
                "road": "Pine St",
                "locality": "Cornwall",
                "state": "CT",
                "dirty_zip": "06753",
                "clean_zip": "06796",
            }
        ]
        rows = _join_nad(queries, csv_body)
        self.assertEqual(rows[0]["decision"], "no_match")
        self.assertEqual(rows[0]["nad_zips"], "")

    def test_unique_zip_fallback_when_city_string_differs(self):
        csv_body = (
            "Add_Number,St_Name,St_PosTyp,State,Zip_Code,Inc_Muni\n"
            "2200,GOOD HOPE,Rd,PA,17025,Hampden\n"
        )
        queries = [
            {
                "id": "hamp",
                "name": "Hampden Medical Center",
                "house_number": "2200",
                "road": "Good Hope Road",
                "locality": "Enola",
                "state": "PA",
                "dirty_zip": "17025",
                "clean_zip": "17011",
            }
        ]
        miss = _join_nad(queries, csv_body)
        hit = _join_nad(queries, csv_body, unique_zip_fallback=True)
        self.assertEqual(miss[0]["decision"], "no_match")
        self.assertEqual(miss[0]["match_method"], "")
        self.assertEqual(miss[0]["n_nad_zips"], "0")
        self.assertEqual(hit[0]["nad_zips"], "17025")
        self.assertEqual(hit[0]["decision"], "other")
        self.assertEqual(hit[0]["match_method"], "unique_zip_full")

    def test_dirty_retry_when_clean_street_misses(self):
        csv_body = (
            "Add_Number,St_Name,St_PosTyp,State,Zip_Code,Inc_Muni\n"
            "6201,GEARY,Blvd,CA,94121,San Francisco\n"
        )
        queries = [
            {
                "id": "sull",
                "name": "Sullivan",
                "house_number": "6201",
                "road": "Not A Real Street",
                "locality": "San Francisco",
                "state": "CA",
                "dirty_zip": "94114",
                "clean_zip": "94121",
                "dirty_house": "6201",
                "dirty_road": "Geary Boulevard",
                "dirty_locality": "San Francisco",
            }
        ]
        miss = _join_nad(queries, csv_body)
        hit = _join_nad(queries, csv_body, dirty_retry=True)
        self.assertEqual(miss[0]["decision"], "no_match")
        self.assertEqual(hit[0]["decision"], "other")
        self.assertEqual(hit[0]["nad_zips"], "94121")
        self.assertEqual(hit[0]["match_method"], "dirty_full")

    def test_join_third_zip_stays_other(self):
        csv_body = (
            "Add_Number,St_Name,St_PosTyp,State,Zip_Code,Inc_Muni\n"
            "1,MAIN,St,KS,66211,Overland Park\n"
        )
        queries = [
            {
                "id": "z3",
                "name": "Place",
                "house_number": "1",
                "road": "Main Street",
                "locality": "Overland Park",
                "state": "KS",
                "dirty_zip": "",
                "clean_zip": "66251",
            }
        ]
        rows = _join_nad(queries, csv_body)
        self.assertEqual(rows[0]["nad_zips"], "66211")
        self.assertEqual(rows[0]["decision"], "other")

    def test_blank_city_query_is_not_exact_keep(self):
        csv_body = (
            "Add_Number,St_Name,St_PosTyp,State,Zip_Code,Inc_Muni\n"
            "100,MAIN,St,KS,66211,Overland Park\n"
        )
        queries = [
            {
                "id": "nocity",
                "name": "Place",
                "house_number": "100",
                "road": "Main Street",
                "locality": "",
                "state": "KS",
                "dirty_zip": "94114",
                "clean_zip": "66211",
            }
        ]
        rows = _join_nad(queries, csv_body)
        self.assertEqual(rows[0]["nad_zips"], "66211")
        self.assertEqual(rows[0]["match_method"], "exact_nocity")
        self.assertEqual(rows[0]["decision"], "other")

    def test_blank_city_core_query_is_core_nocity(self):
        csv_body = (
            "Add_Number,St_Name,St_PosTyp,State,Zip_Code,Inc_Muni\n"
            "6201,GEARY,,CA,94121,San Francisco\n"
        )
        queries = [
            {
                "id": "nocitycore",
                "name": "Sullivan",
                "house_number": "6201",
                "road": "Geary Boulevard",
                "locality": "",
                "state": "CA",
                "dirty_zip": "94114",
                "clean_zip": "94121",
            }
        ]
        rows = _join_nad(queries, csv_body)
        self.assertEqual(rows[0]["match_method"], "core_nocity")
        self.assertEqual(rows[0]["decision"], "other")

    def test_rejects_stale_index_without_key_format_meta(self):
        queries = [
            {
                "id": "bc595135",
                "name": "Sullivan",
                "house_number": "6201",
                "road": "Geary Boulevard",
                "locality": "San Francisco",
                "state": "CA",
                "dirty_zip": "94114",
                "clean_zip": "94121",
            }
        ]
        with TemporaryDirectory() as tmp:
            ipath = Path(tmp) / "legacy.sqlite"
            conn = sqlite3.connect(ipath)
            conn.execute(
                "CREATE TABLE nad (key TEXT NOT NULL, city TEXT NOT NULL, "
                "zip TEXT NOT NULL, PRIMARY KEY (key, city, zip)) WITHOUT ROWID"
            )
            conn.execute(
                "INSERT INTO nad VALUES (?, ?, ?)",
                (make_key("CA", "6201", "GEARY"), "SAN FRANCISCO", "94121"),
            )
            conn.commit()
            conn.close()
            with self.assertRaises(SystemExit) as ctx:
                join_from_index(queries, ipath)
        self.assertIn("key_format", str(ctx.exception))

    def test_rejects_wrong_key_format_version(self):
        queries = [
            {
                "id": "bc595135",
                "name": "Sullivan",
                "house_number": "6201",
                "road": "Geary Boulevard",
                "locality": "San Francisco",
                "state": "CA",
                "dirty_zip": "94114",
                "clean_zip": "94121",
            }
        ]
        with TemporaryDirectory() as tmp:
            ipath = Path(tmp) / "oldfmt.sqlite"
            conn = sqlite3.connect(ipath)
            conn.execute(
                "CREATE TABLE nad (key TEXT NOT NULL, city TEXT NOT NULL, "
                "zip TEXT NOT NULL, PRIMARY KEY (key, city, zip)) WITHOUT ROWID"
            )
            conn.execute("CREATE TABLE meta (k TEXT PRIMARY KEY, v TEXT NOT NULL)")
            conn.execute("INSERT INTO meta VALUES ('key_format', 'core_only_v0')")
            conn.commit()
            conn.close()
            with self.assertRaises(SystemExit) as ctx:
                join_from_index(queries, ipath)
        self.assertIn("core_only_v0", str(ctx.exception))

    def test_rejects_index_without_complete_flag(self):
        queries = [
            {
                "id": "bc595135",
                "name": "Sullivan",
                "house_number": "6201",
                "road": "Geary Boulevard",
                "locality": "San Francisco",
                "state": "CA",
                "dirty_zip": "94114",
                "clean_zip": "94121",
            }
        ]
        with TemporaryDirectory() as tmp:
            ipath = Path(tmp) / "partial.sqlite"
            conn = sqlite3.connect(ipath)
            conn.execute(
                "CREATE TABLE nad (key TEXT NOT NULL, city TEXT NOT NULL, "
                "zip TEXT NOT NULL, PRIMARY KEY (key, city, zip)) WITHOUT ROWID"
            )
            conn.execute("CREATE TABLE meta (k TEXT PRIMARY KEY, v TEXT NOT NULL)")
            conn.execute("INSERT INTO meta VALUES ('key_format', ?)", (INDEX_FORMAT,))
            conn.commit()
            conn.close()
            with self.assertRaises(SystemExit) as ctx:
                join_from_index(queries, ipath)
        self.assertIn("complete", str(ctx.exception))

    def test_rebuild_failure_keeps_existing_index(self):
        csv_body = (
            "Add_Number,St_Name,St_PosTyp,State,Zip_Code,Inc_Muni\n"
            "6201,GEARY,Blvd,CA,94121,San Francisco\n"
        )
        queries = [
            {
                "id": "bc595135",
                "name": "Sullivan",
                "house_number": "6201",
                "road": "Geary Boulevard",
                "locality": "San Francisco",
                "state": "CA",
                "dirty_zip": "94114",
                "clean_zip": "94121",
            }
        ]
        with TemporaryDirectory() as tmp:
            zpath = Path(tmp) / "nad.zip"
            ipath = Path(tmp) / "nad.sqlite"
            with zipfile.ZipFile(zpath, "w") as zf:
                zf.writestr("NAD.txt", csv_body)
            build_nad_index(zpath, ipath)
            hit = join_from_index(queries, ipath)
            self.assertEqual(hit[0]["nad_zips"], "94121")
            with self.assertRaises(SystemExit):
                build_nad_index(Path(tmp) / "missing.zip", ipath)
            still = join_from_index(queries, ipath)
            self.assertEqual(still[0]["nad_zips"], "94121")
            self.assertEqual(still[0]["match_method"], "exact")

    def test_install_removes_dest_wal_before_replace(self):
        with TemporaryDirectory() as tmp:
            dest = Path(tmp) / "nad.sqlite"
            building = Path(tmp) / "nad.sqlite.building"
            dest.write_bytes(b"old")
            wal = Path(str(dest) + "-wal")
            wal.write_bytes(b"wal")
            building.write_bytes(b"new")
            wal_at_replace: list[bool] = []
            real_replace = Path.replace

            def tracked_replace(self, target):
                wal_at_replace.append(wal.exists())
                return real_replace(self, target)

            with patch.object(Path, "replace", tracked_replace):
                _install_built_index(building, dest)
            self.assertEqual(wal_at_replace, [False])
            self.assertEqual(dest.read_bytes(), b"new")
            self.assertFalse(wal.exists())
            self.assertFalse(building.exists())


class LoadQueryTests(unittest.TestCase):
    def test_loads_all_us_categories_when_unfiltered(self):
        dirty = (
            "id,name,house_number,road,locality,region,postcode,country_code,provenance_graph_iri\n"
            "a,Levi,4900,Marie Way,Santa Clara,CA,95054,us,\n"
            "b,Tire,2360,Schoenersville Rd,Bethlehem,PA,18017,us,\n"
        )
        clean = (
            "id,name,house_number,road,locality,region,postcode,country_code,provenance_graph_iri\n"
            "a,Levi,4900,Marie Way,Santa Clara,California,95054,us,\n"
            "b,Tire,2360,Schoenersville Rd,Bethlehem,Pennsylvania,18018,us,\n"
        )
        with TemporaryDirectory() as tmp:
            dp, cp = Path(tmp) / "d.csv", Path(tmp) / "c.csv"
            dp.write_text(dirty)
            cp.write_text(clean)
            all_rows = load_query_rows(dp, cp)
            d_only = load_query_rows(dp, cp, categories=["D_same_area"])
        cats = sorted(r["category"] for r in all_rows)
        self.assertEqual(cats, ["A_match", "D_same_area"])
        self.assertEqual([r["category"] for r in d_only], ["D_same_area"])

    def test_join_key_uses_clean_street_house_city_name(self):
        dirty = (
            "id,name,house_number,road,locality,region,postcode,country_code,provenance_graph_iri\n"
            "h,Wrong Name,3656,North Halsted,Chicago,IL,60613,us,\n"
        )
        clean = (
            "id,name,house_number,road,locality,region,postcode,country_code,provenance_graph_iri\n"
            "h,Center on Halsted,3656,North Halsted Street,Chicago,Illinois,60613,us,\n"
        )
        with TemporaryDirectory() as tmp:
            dp, cp = Path(tmp) / "d.csv", Path(tmp) / "c.csv"
            dp.write_text(dirty)
            cp.write_text(clean)
            rows = load_query_rows(dp, cp)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["name"], "Center on Halsted")
        self.assertEqual(rows[0]["road"], "North Halsted Street")
        self.assertEqual(rows[0]["house_number"], "3656")
        self.assertEqual(rows[0]["locality"], "Chicago")
        self.assertEqual(rows[0]["state"], "IL")
        self.assertEqual(rows[0]["dirty_zip"], "60613")
        self.assertEqual(rows[0]["clean_zip"], "60613")

    def test_rejects_when_dirty_and_clean_row_counts_differ(self):
        dirty = (
            "id,name,house_number,road,locality,region,postcode,country_code,provenance_graph_iri\n"
            "a,A,1,Main,X,CA,94109,us,\n"
            "b,B,2,Main,X,CA,94109,us,\n"
        )
        clean = (
            "id,name,house_number,road,locality,region,postcode,country_code,provenance_graph_iri\n"
            "a,A,1,Main,X,California,94109,us,\n"
        )
        with TemporaryDirectory() as tmp:
            dp, cp = Path(tmp) / "d.csv", Path(tmp) / "c.csv"
            dp.write_text(dirty)
            cp.write_text(clean)
            with self.assertRaises(SystemExit) as ctx:
                load_query_rows(dp, cp)
        self.assertIn("row count mismatch", str(ctx.exception))

    def test_classify_valueerror_is_not_reported_as_row_count_mismatch(self):
        dirty = (
            "id,name,house_number,road,locality,region,postcode,country_code,provenance_graph_iri\n"
            "a,A,1,Main,X,CA,94109,us,\n"
        )
        clean = (
            "id,name,house_number,road,locality,region,postcode,country_code,provenance_graph_iri\n"
            "a,A,1,Main,X,California,94109,us,\n"
        )
        with TemporaryDirectory() as tmp:
            dp, cp = Path(tmp) / "d.csv", Path(tmp) / "c.csv"
            dp.write_text(dirty)
            cp.write_text(clean)
            with patch("nad_join.classify_postcode", side_effect=ValueError("bad pc")):
                with self.assertRaises(ValueError) as ctx:
                    load_query_rows(dp, cp)
        self.assertEqual(str(ctx.exception), "bad pc")


if __name__ == "__main__":
    unittest.main()
