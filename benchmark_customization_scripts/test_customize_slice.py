import os
import sys
import unittest

import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import customize_slice as cs  # noqa: E402


class TestCustomizeSlice(unittest.TestCase):
    def test_drops_columns_from_both_sides(self):
        dirty = pd.DataFrame({"road": ["Main"], "country_code": ["de"], "id": ["1"]})
        clean = pd.DataFrame({"road": ["Main"], "country_code": ["DE"], "id": ["1"]})
        out_d, out_c, report = cs.customize(
            dirty, clean, ["country_code"], [], domain="address", workers=1,
        )
        self.assertEqual(list(out_d.columns), ["road", "id"])
        self.assertEqual(list(out_c.columns), ["road", "id"])
        self.assertEqual(report["cells_restored"], 0)
        self.assertEqual(out_d.loc[0, "road"], "Main")

    def test_unknown_column_is_rejected(self):
        dirty = pd.DataFrame({"road": ["Main"]})
        clean = pd.DataFrame({"road": ["Main Street"]})
        with self.assertRaises(SystemExit):
            cs.customize(dirty, clean, ["postcode"], [], workers=1)

    def test_unknown_type_is_rejected(self):
        with self.assertRaises(SystemExit):
            cs.resolve_types(["NotAType"])

    @unittest.skipUnless(
        __import__("analyze_error_types").HAVE_LIBPOSTAL,
        "libpostal not installed",
    )
    def test_selected_type_is_replaced_with_clean_value(self):
        dirty = pd.DataFrame({
            "road": ["South 37th Avenue", "Mingerstrasse"],
            "id": ["1", "2"],
        })
        clean = pd.DataFrame({
            "road": ["37th Avenue South", "Tschäppätstrasse"],
            "id": ["1", "2"],
        })
        out_d, out_c, report = cs.customize(
            dirty, clean, [], ["Formatting"], domain="address", workers=1,
        )
        self.assertEqual(out_d.loc[0, "road"], "37th Avenue South")
        self.assertEqual(out_d.loc[1, "road"], "Mingerstrasse")
        self.assertEqual(out_c.loc[1, "road"], "Tschäppätstrasse")
        self.assertEqual(report["cells_restored"], 1)
        self.assertEqual(report["restored_by_column"], {"road": 1})

    @unittest.skipUnless(
        __import__("analyze_error_types").HAVE_LIBPOSTAL,
        "libpostal not installed",
    )
    def test_restores_only_when_every_label_is_excluded(self):
        # "1st Av" is Abbreviation and Formatting.
        # "Rd 12" is Abbreviation and Token_Subset.
        dirty = pd.DataFrame({"road": ["1st Av", "Rd 12"], "id": ["1", "2"]})
        clean = pd.DataFrame({"road": ["First Avenue", "Road 12 extra"], "id": ["1", "2"]})

        out_d, _, report = cs.customize(
            dirty, clean, [], ["Abbreviation"], domain="address", workers=1,
        )
        self.assertEqual(out_d.loc[0, "road"], "1st Av")
        self.assertEqual(out_d.loc[1, "road"], "Rd 12")
        self.assertEqual(report["cells_restored"], 0)

        out_d, _, report = cs.customize(
            dirty, clean, [], ["Abbreviation", "Formatting"], domain="address", workers=1,
        )
        self.assertEqual(out_d.loc[0, "road"], "First Avenue")
        self.assertEqual(out_d.loc[1, "road"], "Rd 12")
        self.assertEqual(report["cells_restored"], 1)
        self.assertEqual(report["restored_by_column"], {"road": 1})


if __name__ == "__main__":
    unittest.main()
