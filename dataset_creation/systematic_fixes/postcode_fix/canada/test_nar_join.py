import csv
import io
import sqlite3
import unittest
import zipfile
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from nar_join import (
    INDEX_FORMAT,
    build_nar_index,
    cities_match,
    decide,
    index_postcode,
    join_from_index,
    load_query_rows,
    nar_index_rows,
    nar_record,
    norm_city,
    norm_number,
    norm_street,
    postal_code,
    province_abbr,
    street_core,
)


def _join_nar(queries, csv_body, **kwargs):
    with TemporaryDirectory() as tmp:
        zpath = Path(tmp) / "nar.zip"
        ipath = Path(tmp) / "nar.sqlite"
        with zipfile.ZipFile(zpath, "w") as zf:
            zf.writestr("Addresses/Address_35.csv", csv_body)
        build_nar_index(zpath, ipath)
        return join_from_index(queries, ipath, **kwargs)


NAR_HDR = (
    "CIVIC_NO,CIVIC_NO_SUFFIX,OFFICIAL_STREET_NAME,OFFICIAL_STREET_TYPE,"
    "OFFICIAL_STREET_DIR,CSD_ENG_NAME,CSD_FRE_NAME,MAIL_MUN_NAME,"
    "MAIL_PROV_ABVN,MAIL_POSTAL_CODE,MAIL_STREET_NAME,MAIL_STREET_TYPE,"
    "MAIL_STREET_DIR,PROV_CODE"
)


class NormalizeTests(unittest.TestCase):
    def test_postal_code_keeps_full_ldu(self):
        self.assertEqual(postal_code("M5V 2T6"), "M5V2T6")
        self.assertEqual(postal_code("m5v2t6"), "M5V2T6")
        self.assertEqual(postal_code("V6T"), "V6T")
        self.assertEqual(postal_code("94121"), "")
        self.assertEqual(postal_code(""), "")

    def test_index_postcode_is_full_ldu(self):
        self.assertEqual(index_postcode("E3B 2T8"), "E3B2T8")
        self.assertEqual(index_postcode("e3b"), "E3B")

    def test_province_abbr_slash_and_accent(self):
        self.assertEqual(province_abbr("Ontario"), "ON")
        self.assertEqual(province_abbr("QC"), "QC")
        self.assertEqual(province_abbr("Québec"), "QC")
        self.assertEqual(province_abbr("New Brunswick / Nouveau-Brunswick"), "NB")
        self.assertEqual(province_abbr("British Columbia"), "BC")

    def test_number_digits(self):
        self.assertEqual(norm_number("465"), "465")
        self.assertEqual(norm_number("123A"), "123")

    def test_norm_street_moves_french_prefix_type_to_suffix(self):
        self.assertEqual(
            norm_street("Boulevard Saint-Joseph"),
            "ST JOSEPH BOULEVARD",
        )
        self.assertEqual(norm_street("Rue Sainte-Catherine"), "STE CATHERINE RUE")
        self.assertEqual(norm_street("Chemin du Lac-Wilson"), "DU LAC WILSON CHEMIN")

    def test_norm_street_english_keeps_suffix_type(self):
        self.assertEqual(norm_street("Dundas Street West"), "DUNDAS STREET W")
        self.assertEqual(norm_street("Wonderland Rd N"), "WONDERLAND ROAD N")

    def test_middle_st_is_street_not_saint(self):
        self.assertEqual(norm_street("Dundas St West"), "DUNDAS STREET W")
        self.assertEqual(norm_street("Dundas Street West"), norm_street("Dundas St W"))
        self.assertEqual(street_core("Dundas St West"), "DUNDAS")
        self.assertEqual(norm_street("St Joseph Blvd"), "ST JOSEPH BOULEVARD")
        self.assertEqual(street_core("St Joseph Blvd"), "ST JOSEPH")
        self.assertEqual(norm_street("Eddy St"), "EDDY STREET")

    def test_street_core_strips_french_prefix_and_english_suffix(self):
        self.assertEqual(street_core("Boulevard Saint-Joseph"), "ST JOSEPH")
        self.assertEqual(street_core("Saint-Joseph Blvd"), "ST JOSEPH")
        self.assertEqual(street_core("Rue Sainte-Catherine"), "STE CATHERINE")
        self.assertEqual(street_core("Chemin du Lac-Wilson"), "DU LAC WILSON")
        self.assertEqual(street_core("Dundas Street West"), "DUNDAS")

    def test_street_core_keeps_dir_when_rest_is_numeric(self):
        self.assertEqual(street_core("West 95th Street"), "W 95")
        self.assertEqual(street_core("95e Rue Ouest"), "W 95")

    def test_french_ordinal_rang(self):
        self.assertEqual(norm_street("7e Rang"), "7 RANG")
        self.assertEqual(street_core("7e Rang"), "7")

    def test_ouest_is_west(self):
        self.assertEqual(norm_street("Rue Principale Ouest"), "PRINCIPALE RUE W")
        self.assertEqual(street_core("Rue Principale O"), "PRINCIPALE")

    def test_city_folds_accents_and_saint(self):
        self.assertEqual(norm_city("Montréal"), "MONTREAL")
        self.assertEqual(norm_city("Saint-Théophile"), "ST THEOPHILE")
        self.assertEqual(norm_city("Ville de Québec"), "QUEBEC")
        self.assertTrue(cities_match("Montreal", "Montréal"))
        self.assertTrue(cities_match("Québec", "Ville de Quebec"))
        self.assertFalse(cities_match("Toronto", "Ottawa"))


class DecideTests(unittest.TestCase):
    def test_keep_dirty_on_ldu_fight(self):
        self.assertEqual(decide("E3B 2T8", "E3B 3H5", {"E3B2T8"}), "keep_dirty")

    def test_keep_clean_on_ldu_fight(self):
        self.assertEqual(decide("E3B 2T8", "E3B 3H5", {"E3B3H5"}), "keep_clean")

    def test_confirm_full_ldu(self):
        self.assertEqual(decide("M9A 1B6", "M9A 1B6", {"M9A1B6"}), "confirm")

    def test_confirm_fsa_only_when_nar_ldu_shares_fsa(self):
        self.assertEqual(decide("V6T", "V6T", {"V6T1Z1"}), "confirm")

    def test_precision_full_dirty_vs_fsa_clean_is_keep_dirty(self):
        self.assertEqual(decide("V6T1Z1", "V6T", {"V6T1Z1"}), "keep_dirty")

    def test_fsa_clean_does_not_count_as_hit_against_other_ldu(self):
        self.assertEqual(decide("V6T1Z1", "V6T", {"V6T9Z9"}), "other")

    def test_has_both_ldus(self):
        self.assertEqual(decide("E3B2T8", "E3B3H5", {"E3B2T8", "E3B3H5"}), "has_both")

    def test_third_ldu_stays_other(self):
        self.assertEqual(decide("E3B2T8", "E3B3H5", {"E3B1A1"}), "other")

    def test_no_match(self):
        self.assertEqual(decide("E3B2T8", "E3B3H5", set()), "no_match")


class NarIndexTests(unittest.TestCase):
    def test_nar_record_expands_type_st_before_dir(self):
        rec = nar_record({
            "CIVIC_NO": "4943",
            "OFFICIAL_STREET_NAME": "Dundas",
            "OFFICIAL_STREET_TYPE": "ST",
            "OFFICIAL_STREET_DIR": "W",
            "MAIL_MUN_NAME": "TORONTO",
            "MAIL_PROV_ABVN": "ON",
            "MAIL_POSTAL_CODE": "M9A1B6",
        })
        self.assertEqual(rec[0], "ON|4943|DUNDAS STREET W")
        self.assertEqual(rec[2], "M9A1B6")

    def test_nar_record_composes_official_street_and_mail_city(self):
        rec = nar_record({
            "CIVIC_NO": "965",
            "OFFICIAL_STREET_NAME": "Saint-Joseph",
            "OFFICIAL_STREET_TYPE": "BOUL",
            "OFFICIAL_STREET_DIR": "",
            "CSD_ENG_NAME": "",
            "CSD_FRE_NAME": "",
            "MAIL_MUN_NAME": "GATINEAU",
            "MAIL_PROV_ABVN": "QC",
            "MAIL_POSTAL_CODE": "J8Z1W8",
        })
        self.assertEqual(
            rec,
            ("QC|965|ST JOSEPH BOULEVARD", "GATINEAU", "J8Z1W8"),
        )

    def test_nar_index_rows_store_full_core_and_bilingual_cities(self):
        rows = nar_index_rows({
            "CIVIC_NO": "880",
            "OFFICIAL_STREET_NAME": "Prospect",
            "OFFICIAL_STREET_TYPE": "ST",
            "CSD_ENG_NAME": "Fredericton",
            "CSD_FRE_NAME": "Fredericton",
            "MAIL_MUN_NAME": "FREDERICTON",
            "MAIL_PROV_ABVN": "NB",
            "MAIL_POSTAL_CODE": "E3B 2T8",
        })
        cities = {c for _, c, _ in rows}
        self.assertEqual(cities, {"FREDERICTON"})
        keys = {k for k, _, _ in rows}
        self.assertEqual(
            keys,
            {
                "F|NB|880|PROSPECT STREET",
                "C|NB|880|PROSPECT",
            },
        )
        self.assertEqual({z for _, _, z in rows}, {"E3B2T8"})

    def test_indexes_mail_street_when_it_differs(self):
        rows = nar_index_rows({
            "CIVIC_NO": "990",
            "OFFICIAL_STREET_NAME": "du Président-Kennedy",
            "OFFICIAL_STREET_TYPE": "ROUTE",
            "MAIL_STREET_NAME": "DU PRESIDENT-KENNEDY",
            "MAIL_STREET_TYPE": "RTE",
            "MAIL_MUN_NAME": "SAINT-THEOPHILE",
            "MAIL_PROV_ABVN": "QC",
            "MAIL_POSTAL_CODE": "G0M2A0",
        })
        keys = {k for k, _, _ in rows}
        self.assertIn("F|QC|990|DU PRESIDENT KENNEDY ROUTE", keys)
        self.assertIn("C|QC|990|DU PRESIDENT KENNEDY", keys)

    def test_skips_locations_csv_in_zip(self):
        loc = (
            "LOC_GUID,BG_X,BG_Y\n"
            "abc,1,2\n"
        )
        addr = (
            f"{NAR_HDR}\n"
            "100,,MAIN,ST,,Toronto,,TORONTO,ON,M5V2T6,MAIN,ST,,35\n"
        )
        queries = [{
            "id": "1",
            "name": "X",
            "house_number": "100",
            "road": "Main Street",
            "locality": "Toronto",
            "state": "ON",
            "dirty_zip": "M5V2T6",
            "clean_zip": "M5V2T6",
        }]
        with TemporaryDirectory() as tmp:
            zpath = Path(tmp) / "nar.zip"
            ipath = Path(tmp) / "nar.sqlite"
            with zipfile.ZipFile(zpath, "w") as zf:
                zf.writestr("Locations/Location_35.csv", loc)
                zf.writestr("Addresses/Address_35.csv", addr)
            build_nar_index(zpath, ipath)
            rows = join_from_index(queries, ipath)
        self.assertEqual(rows[0]["match_method"], "exact")
        self.assertEqual(rows[0]["nar_pcs"], "M5V2T6")

    def test_french_prefix_query_is_exact_against_nar_type_field(self):
        csv_body = (
            f"{NAR_HDR}\n"
            "965,,Saint-Joseph,BOUL,,Gatineau,Gatineau,GATINEAU,QC,J8Z1W8,"
            "SAINT-JOSEPH,BOUL,,24\n"
        )
        queries = [{
            "id": "sub",
            "name": "Subaru Outaouais",
            "house_number": "965",
            "road": "Boulevard Saint-Joseph",
            "locality": "Gatineau",
            "state": "QC",
            "dirty_zip": "J8Z 1W8",
            "clean_zip": "J8Z 1W8",
        }]
        rows = _join_nar(queries, csv_body)
        self.assertEqual(rows[0]["match_method"], "exact")
        self.assertEqual(rows[0]["decision"], "confirm")
        self.assertEqual(rows[0]["nar_pcs"], "J8Z1W8")
        self.assertIn("F|QC|965|ST JOSEPH BOULEVARD", rows[0]["join_key"])

    def test_dundas_st_w_is_exact_against_street_west_query(self):
        csv_body = (
            f"{NAR_HDR}\n"
            "4943,,Dundas,ST,W,Toronto,Toronto,ETOBICOKE,ON,M9A1B6,DUNDAS,ST,W,35\n"
        )
        queries = [{
            "id": "vape",
            "name": "Vape4Change",
            "house_number": "4943",
            "road": "Dundas Street West",
            "locality": "Toronto",
            "state": "ON",
            "dirty_zip": "M9A 1B6",
            "clean_zip": "M9A 1B6",
        }]
        rows = _join_nar(queries, csv_body)
        self.assertEqual(rows[0]["match_method"], "exact")
        self.assertEqual(rows[0]["decision"], "confirm")
        self.assertEqual(rows[0]["nar_pcs"], "M9A1B6")
        self.assertIn("F|ON|4943|DUNDAS STREET W", rows[0]["join_key"])

    def test_ldu_fight_keep_dirty_on_exact(self):
        csv_body = (
            f"{NAR_HDR}\n"
            "880,,Prospect,ST,,Fredericton,Fredericton,FREDERICTON,NB,E3B2T8,"
            "PROSPECT,ST,,13\n"
        )
        queries = [{
            "id": "wood",
            "name": "Wood Motors Ford",
            "house_number": "880",
            "road": "Prospect Street",
            "locality": "Fredericton",
            "state": "NB",
            "dirty_zip": "E3B 2T8",
            "clean_zip": "E3B 3H5",
        }]
        rows = _join_nar(queries, csv_body)
        self.assertEqual(rows[0]["match_method"], "exact")
        self.assertEqual(rows[0]["decision"], "keep_dirty")
        self.assertEqual(rows[0]["nar_pcs"], "E3B2T8")

    def test_core_hit_is_not_keep(self):
        csv_body = (
            f"{NAR_HDR}\n"
            "655,,Wonderland,RD,N,London,London,LONDON,ON,N6H0J5,WONDERLAND,RD,N,35\n"
        )
        queries = [{
            "id": "nash",
            "name": "Nash",
            "house_number": "655",
            "road": "Wonderland",
            "locality": "London",
            "state": "ON",
            "dirty_zip": "N6H 0J5",
            "clean_zip": "N6H 1T6",
        }]
        rows = _join_nar(queries, csv_body)
        self.assertEqual(rows[0]["match_method"], "core")
        self.assertEqual(rows[0]["decision"], "other")
        self.assertEqual(rows[0]["nar_pcs"], "N6H0J5")

    def test_unique_pc_fallback_is_not_keep(self):
        csv_body = (
            f"{NAR_HDR}\n"
            "2200,,Good Hope,RD,,Hampden,,ENOLA,BC,V6T1Z1,GOOD HOPE,RD,,59\n"
        )
        queries = [{
            "id": "brock",
            "name": "Brock Hall",
            "house_number": "2200",
            "road": "Good Hope Road",
            "locality": "Vancouver",
            "state": "BC",
            "dirty_zip": "V6T1Z1",
            "clean_zip": "V6T",
        }]
        miss = _join_nar(queries, csv_body)
        hit = _join_nar(queries, csv_body, unique_zip_fallback=True)
        self.assertEqual(miss[0]["decision"], "no_match")
        self.assertEqual(hit[0]["nar_pcs"], "V6T1Z1")
        self.assertEqual(hit[0]["match_method"], "unique_zip_full")
        self.assertEqual(hit[0]["decision"], "other")

    def test_mail_city_matches_when_csd_blank(self):
        csv_body = (
            f"{NAR_HDR}\n"
            "15,,du Lac-Wilson,CH,,,,SAINT-THÉOPHILE,QC,G0M2A0,DU LAC-WILSON,CH,,24\n"
        )
        queries = [{
            "id": "lac",
            "name": "X",
            "house_number": "15",
            "road": "Chemin du Lac-Wilson",
            "locality": "Saint-Théophile",
            "state": "QC",
            "dirty_zip": "G0M 2A0",
            "clean_zip": "G0M 2A0",
        }]
        rows = _join_nar(queries, csv_body)
        self.assertEqual(rows[0]["match_method"], "exact")
        self.assertEqual(rows[0]["decision"], "confirm")

    def test_dirty_retry_is_not_keep(self):
        csv_body = (
            f"{NAR_HDR}\n"
            "100,,MAIN,ST,,Toronto,,TORONTO,ON,M5V2T6,MAIN,ST,,35\n"
        )
        queries = [{
            "id": "d",
            "name": "X",
            "house_number": "100",
            "road": "Not A Street",
            "locality": "Toronto",
            "state": "ON",
            "dirty_zip": "M5V 2T6",
            "clean_zip": "M5V 1A1",
            "dirty_house": "100",
            "dirty_road": "Main Street",
            "dirty_locality": "Toronto",
        }]
        miss = _join_nar(queries, csv_body)
        hit = _join_nar(queries, csv_body, dirty_retry=True)
        self.assertEqual(miss[0]["decision"], "no_match")
        self.assertEqual(hit[0]["match_method"], "dirty_full")
        self.assertEqual(hit[0]["decision"], "other")

    def test_rejects_stale_index(self):
        queries = [{
            "id": "1", "name": "X", "house_number": "1", "road": "Main",
            "locality": "Toronto", "state": "ON",
            "dirty_zip": "M5V2T6", "clean_zip": "M5V2T6",
        }]
        with TemporaryDirectory() as tmp:
            ipath = Path(tmp) / "legacy.sqlite"
            conn = sqlite3.connect(ipath)
            conn.execute(
                "CREATE TABLE nar (key TEXT NOT NULL, city TEXT NOT NULL, "
                "zip TEXT NOT NULL, PRIMARY KEY (key, city, zip)) WITHOUT ROWID"
            )
            conn.commit()
            conn.close()
            with self.assertRaises(SystemExit) as ctx:
                join_from_index(queries, ipath)
        self.assertIn("key_format", str(ctx.exception))


class LoadQueryTests(unittest.TestCase):
    def test_loads_ca_not_us(self):
        dirty = (
            "id,name,house_number,road,locality,region,postcode,country_code,provenance_graph_iri\n"
            "a,Subaru,965,Boulevard Saint-Joseph,Gatineau,Québec,J8Z 1W8,ca,\n"
            "b,Levi,4900,Marie Way,Santa Clara,CA,95054,us,\n"
        )
        clean = (
            "id,name,house_number,road,locality,region,postcode,country_code,provenance_graph_iri\n"
            "a,Subaru,965,Boulevard Saint-Joseph,Gatineau,Québec,J8Z 1W8,ca,\n"
            "b,Levi,4900,Marie Way,Santa Clara,California,95054,us,\n"
        )
        with TemporaryDirectory() as tmp:
            dp, cp = Path(tmp) / "d.csv", Path(tmp) / "c.csv"
            dp.write_text(dirty)
            cp.write_text(clean)
            rows = load_query_rows(dp, cp)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["state"], "QC")
        self.assertEqual(rows[0]["dirty_zip"], "J8Z 1W8")
        self.assertEqual(rows[0]["category"], "A_match")

    def test_rejects_row_count_mismatch(self):
        dirty = (
            "id,name,house_number,road,locality,region,postcode,country_code,provenance_graph_iri\n"
            "a,A,1,Main,X,ON,M5V2T6,ca,\n"
            "b,B,2,Main,X,ON,M5V2T6,ca,\n"
        )
        clean = (
            "id,name,house_number,road,locality,region,postcode,country_code,provenance_graph_iri\n"
            "a,A,1,Main,X,Ontario,M5V2T6,ca,\n"
        )
        with TemporaryDirectory() as tmp:
            dp, cp = Path(tmp) / "d.csv", Path(tmp) / "c.csv"
            dp.write_text(dirty)
            cp.write_text(clean)
            with self.assertRaises(SystemExit) as ctx:
                load_query_rows(dp, cp)
        self.assertIn("row count mismatch", str(ctx.exception))


class CompareTests(unittest.TestCase):
    def test_unique_addresses_use_full_ldu(self):
        from compare_nar import unique_addresses
        rows = unique_addresses([
            {"id": "1", "name": "A", "house_number": "880", "road": "Prospect Street",
             "locality": "Fredericton", "state": "NB",
             "dirty_zip": "E3B 2T8", "clean_zip": "E3B 3H5",
             "dirty_house": "", "dirty_road": ""},
            {"id": "2", "name": "B", "house_number": "880", "road": "Prospect Street",
             "locality": "Fredericton", "state": "NB",
             "dirty_zip": "E3B 2T8", "clean_zip": "E3B 3H5",
             "dirty_house": "880", "dirty_road": "Prospect Street"},
            {"id": "3", "name": "C", "house_number": "880", "road": "Prospect Street",
             "locality": "Fredericton", "state": "NB",
             "dirty_zip": "", "clean_zip": "E3B 3H5",
             "dirty_house": "", "dirty_road": ""},
        ])
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["n_dupes"], "3")
        self.assertEqual(rows[0]["dirty_zip"], "E3B 2T8")


if __name__ == "__main__":
    unittest.main()
