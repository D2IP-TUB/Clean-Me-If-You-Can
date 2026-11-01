import unittest

from classify_postcode import classify_postcode


class ClassifyPostcodeTests(unittest.TestCase):
    def test_a_exact_match_ignores_spaces_and_hyphens(self):
        self.assertEqual(classify_postcode("02127", "02127", "us"), "A_match")
        self.assertEqual(classify_postcode("H2L 3Y7", "H2L3Y7", "ca"), "A_match")

    def test_b_dirty_missing(self):
        self.assertEqual(classify_postcode("", "66212", "us"), "B_missing_dirty")
        self.assertEqual(classify_postcode("   ", "94158", "us"), "B_missing_dirty")

    def test_c_extra_precision_us_zip4(self):
        self.assertEqual(
            classify_postcode("78412-3910", "78412", "us"), "C_precision"
        )
        self.assertEqual(
            classify_postcode("80221-1099", "80221", "us"), "C_precision"
        )

    def test_c_extra_precision_ca_ldu_vs_fsa(self):
        self.assertEqual(classify_postcode("V6C2C2", "V6C", "ca"), "C_precision")

    def test_d_canada_same_fsa_different_ldu(self):
        self.assertEqual(
            classify_postcode("E3B 2T8", "E3B 3H5", "ca"), "D_same_area"
        )
        self.assertEqual(
            classify_postcode("J3L 3R8", "J3L 3R9", "ca"), "D_same_area"
        )
        self.assertEqual(
            classify_postcode("H2L3Y7", "H2L 2E2", "ca"), "D_same_area"
        )

    def test_d_us_nearby_zip5(self):
        self.assertEqual(
            classify_postcode("15217", "15221", "us"), "D_same_area"
        )
        self.assertEqual(
            classify_postcode("92111", "92101", "us"), "D_same_area"
        )

    def test_d_ireland_same_routing_key(self):
        self.assertEqual(
            classify_postcode("A96 X7W1", "A96 HF51", "ie"), "D_same_area"
        )

    def test_e_far_mismatch(self):
        self.assertEqual(
            classify_postcode("01840", "11559", "us"), "E_far"
        )
        self.assertEqual(
            classify_postcode("02476", "02174", "us"), "E_far"
        )

    def test_f_malformed(self):
        self.assertEqual(
            classify_postcode("331391", "33139", "us"), "F_malformed"
        )
        self.assertEqual(
            classify_postcode(
                "98541",
                "98541-9285 region:WA country:US Version 0 Sources property: dataset:meta",
                "us",
            ),
            "F_malformed",
        )


if __name__ == "__main__":
    unittest.main()
