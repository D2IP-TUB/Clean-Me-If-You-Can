"""Unit tests for Nominatim baseline mapping and cell decisions."""

import unittest

from nominatim_baseline import (
    ADDRESS_COLUMNS,
    build_query_params,
    cells_from_mapped_row,
    map_feature_to_row,
    pick_best_osm_field,
)


class TestPickBestOsmField(unittest.TestCase):
    def test_prefers_city_over_village(self):
        address = {"city": "Boston", "village": "Cambridge"}
        self.assertEqual(
            pick_best_osm_field("Boston", address, ["city", "town"], ["village"]),
            "Boston",
        )

    def test_fallback_when_preferred_absent(self):
        address = {"village": "Hamletville"}
        self.assertEqual(
            pick_best_osm_field("Hamletville", address, ["city", "town"], ["village"]),
            "Hamletville",
        )

    def test_tiebreak_closest_levenshtein(self):
        address = {"city": "Munchen", "town": "Munich"}
        self.assertEqual(
            pick_best_osm_field("Munich", address, ["city", "town"], []),
            "Munich",
        )

    def test_none_when_no_candidates(self):
        self.assertIsNone(pick_best_osm_field("Boston", {}, ["city"], ["village"]))


class TestBuildQueryParams(unittest.TestCase):
    def test_street_is_housenumber_plus_road(self):
        row = {
            "name": "Mesa Community College",
            "house_number": "1833",
            "road": "West Southern Avenue",
            "locality": "Phoenix",
            "region": "Arizona",
            "country": "United States",
            "postcode": "85202",
        }
        q = build_query_params(row)
        self.assertEqual(q["amenity"], "Mesa Community College")
        self.assertEqual(q["street"], "1833 West Southern Avenue")
        self.assertEqual(q["city"], "Phoenix")
        self.assertEqual(q["state"], "Arizona")
        self.assertEqual(q["country"], "United States")
        self.assertEqual(q["postalcode"], "85202")

    def test_omits_empty_fields(self):
        q = build_query_params({"name": "", "road": "Main Street", "house_number": ""})
        self.assertNotIn("amenity", q)
        self.assertEqual(q["street"], "Main Street")


class TestMapFeatureToRow(unittest.TestCase):
    def test_maps_core_and_pick_best_fields(self):
        feature = {
            "properties": {
                "name": "Ignored Top Level",
                "namedetails": {"name": "Mesa Community College"},
                "address": {
                    "house_number": "1833",
                    "road": "West Southern Avenue",
                    "postcode": "85202",
                    "city": "Mesa",
                    "town": "Phoenix",
                    "state": "Arizona",
                    "country": "United States",
                    "country_code": "us",
                    "village": "Tempe",
                },
            }
        }
        mapped = map_feature_to_row(
            feature,
            dirty_locality="Phoenix",
            dirty_region="Arizona",
        )
        self.assertEqual(mapped["name"], "Mesa Community College")
        self.assertEqual(mapped["house_number"], "1833")
        self.assertEqual(mapped["road"], "West Southern Avenue")
        self.assertEqual(mapped["postcode"], "85202")
        self.assertEqual(mapped["locality"], "Phoenix")
        self.assertEqual(mapped["region"], "Arizona")
        self.assertEqual(mapped["country"], "United States")
        self.assertEqual(mapped["country_code"], "us")

    def test_no_feature_maps_all_none(self):
        mapped = map_feature_to_row(None, dirty_locality="X", dirty_region="Y")
        for col in ADDRESS_COLUMNS:
            self.assertIsNone(mapped[col])


class TestQueryRowsRetry(unittest.TestCase):
    def test_retries_none_slots(self):
        import nominatim_baseline as nb

        calls = []

        def fake_query(params, nominatim_url, timeout=60.0, retries=3):
            calls.append(params["amenity"])
            if params["amenity"] == "miss-first" and calls.count("miss-first") == 1:
                return None
            return {"properties": {"name": params["amenity"]}}

        original = nb.query_nominatim
        nb.query_nominatim = fake_query
        try:
            features = nb.query_rows(
                [{"name": "hit"}, {"name": "miss-first"}],
                nominatim_url="http://example.invalid",
                max_workers=2,
                progress_every=0,
            )
        finally:
            nb.query_nominatim = original
        self.assertEqual(len(features), 2)
        self.assertIsNotNone(features[0])
        self.assertIsNotNone(features[1])
        self.assertGreaterEqual(calls.count("miss-first"), 2)


class TestCellsFromMappedRow(unittest.TestCase):
    COLS = ["name", "house_number", "road"]

    def test_detect_when_different_and_correct_when_value_present(self):
        dirty = {"name": "mesa college", "house_number": "1833", "road": "W Southern Ave"}
        mapped = {"name": "Mesa Community College", "house_number": "1833", "road": "West Southern Avenue"}
        detected, corrected = cells_from_mapped_row(0, dirty, mapped, self.COLS)
        self.assertIn((0, 0), detected)
        self.assertNotIn((0, 1), detected)  # same house number
        self.assertIn((0, 2), detected)
        self.assertEqual(set(corrected), {(0, 0), (0, 1), (0, 2)})
        self.assertEqual(corrected[(0, 1)], "1833")

    def test_abstain_when_missing(self):
        dirty = {"name": "mesa college", "house_number": "1833", "road": "W Southern Ave"}
        mapped = {"name": None, "house_number": "1833", "road": ""}
        detected, corrected = cells_from_mapped_row(0, dirty, mapped, self.COLS)
        self.assertNotIn((0, 0), detected)
        self.assertNotIn((0, 0), corrected)
        self.assertNotIn((0, 2), detected)
        self.assertNotIn((0, 2), corrected)
        self.assertIn((0, 1), corrected)

    def test_no_hit_abstains_all_cells(self):
        dirty = {"name": "mesa college", "house_number": "1833", "road": "W Southern Ave"}
        mapped = {c: None for c in self.COLS}
        detected, corrected = cells_from_mapped_row(0, dirty, mapped, self.COLS)
        self.assertEqual(detected, {})
        self.assertEqual(corrected, {})


if __name__ == "__main__":
    unittest.main()
