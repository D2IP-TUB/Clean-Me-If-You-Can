"""Regression tests for the multi-label taxonomy layer order."""

import os
import sys
import unittest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import analyze_error_types as m  # noqa: E402

LP = unittest.skipUnless(m.HAVE_LIBPOSTAL, "libpostal not installed (run install_libpostal.sh)")
LG = unittest.skipUnless(m.HAVE_LINGUA, "lingua not installed")

def C(val, tru, col="road", lang=True, parsing=True, abbrev=True, word_level=False):
    return set(m.classify(m.normalize_cell(val), m.normalize_cell(tru), col, lang, parsing,
                           abbrev, None, True, word_level))

def CW(val, tru, col="road"):
    return C(val, tru, col, word_level=True)

class TestExclusiveLayer(unittest.TestCase):

    def test_case_only_difference_is_clean(self):
        for v, t in [("coffee perfect GmbH", "Coffee Perfect GmbH"),
                     ("BERLIN", "berlin"), ("MÜNCHEN", "München")]:
            with self.subTest(v=v):
                self.assertEqual(C(v, t), {"Clean"})

    def test_public_labels(self):
        self.assertEqual(
            m.ERROR_TYPES,
            ["Clean", "Missing", "Special_Character", "Abbreviation", "Language",
             "Formatting", "Token_Subset", "Typo", "Semantic", "Unresolved_Type"],
        )

    def test_missing_is_alone(self):
        self.assertEqual(C("", "anything"), {"Missing"})

    def test_pure_special_character_is_exclusive(self):
        self.assertEqual(C("foo-bar", "foo bar", "road"), {"Special_Character"})
        self.assertEqual(C("Strasse", "Straße", "road"), {"Special_Character"})
        self.assertEqual(C("Shuttleworth®, Inc.", "Shuttleworth Inc", "name"),
                         {"Special_Character"})

    def test_encoding_and_quotes_are_special_character(self):
        self.assertEqual(C("Petula’s", "Petula's", "name"), {"Special_Character"})
        self.assertEqual(C("MÃ¼nchen", "München", "locality"), {"Special_Character"})
        self.assertEqual(C("foo&amp;bar", "foo&bar", "name"), {"Special_Character"})

    def test_encoding_still_runs_on_raw_case(self):
        self.assertEqual(C("MÃ¼nchen", "München", "locality"), {"Special_Character"})
        self.assertFalse(m.is_parsing_artifact("mã¼nchen", "münchen"))
        self.assertTrue(m.is_parsing_artifact("MÃ¼nchen", "München"))

    @LG
    def test_language_is_alone(self):
        for v, t, col in [("Köln", "Cologne", "locality"),
                          ("Deutschland", "Germany", "country"),
                          ("Москва", "Moscow", "locality")]:
            with self.subTest(v=v):
                self.assertEqual(C(v, t, col), {"Language"})

    @LG
    @LP
    def test_language_shared_token_guard(self):
        self.assertFalse(m.is_language("main st", "main street"))

    @LG
    @LP
    def test_language_guard_allows_a_translated_single_token_swap(self):
        for v, t, col in [("North Holland", "Noord-Holland", "region"),
                          ("Saxony-Anhalt", "Sachsen-Anhalt", "region"),
                          ("Noordrijn-Westfalen", "Nordrhein-Westfalen", "region")]:
            with self.subTest(v=v):
                self.assertEqual(C(v, t, col), {"Language"})

    @LG
    @LP
    def test_language_asks_about_the_differing_word_not_the_whole_cell(self):
        self.assertEqual(m._detect_lang("north-brabant"), m._detect_lang("noord-brabant"))
        self.assertNotEqual(m._detect_lang("north"), m._detect_lang("noord"))
        self.assertEqual(CW("North-Brabant", "Noord-Brabant", "region"), {"Language"})
        self.assertEqual(CW("Australia Occidental", "Western Australia", "region"),
                         {"Language"})
        self.assertEqual(C("North-Brabant", "Noord-Brabant", "region"), {"Language"})

    @LG
    @LP
    def test_differing_word_check_is_an_extra_trigger_not_a_replacement(self):
        self.assertIsNone(m._detect_lang("ул"))
        self.assertTrue(m.is_language("ул. пучкова", "вуліца пучкова", use_word_level=True))
        self.assertTrue(m.is_language("ул. пучкова", "вуліца пучкова"))

    @LG
    @LP
    def test_language_guard_still_blocks_non_swap_shared_token_pairs(self):
        self.assertFalse(m.is_language("london", "greater london"))
        self.assertFalse(m.is_language("quebec", "québec"))

    def test_language_needs_letters_on_both_sides(self):
        self.assertFalse(m.is_language("�", "ладожская улица"))
        self.assertFalse(m.is_language("123", "улица"))

    @LG
    def test_language_use_lingua_false_keeps_only_the_script_signal(self):
        self.assertTrue(m.is_language("london", "city of westminster"))
        self.assertFalse(m.is_language("london", "city of westminster", use_lingua=False))
        self.assertTrue(m.is_language("london", "москва", use_lingua=False))

@LP
class TestAbbreviationLayer(unittest.TestCase):

    def test_pure_abbreviation_is_alone(self):
        for v, t, col in [("Str", "Street", "road"),
                          ("Main St", "Main Street", "road"),
                          ("James St.", "James Street", "road"),
                          ("Hauptstr.", "Hauptstraße", "road"),
                          ("n.w. 5th ave", "northwest 5th avenue", "road"),
                          ("USA", "United States", "country"),
                          ("U.S.A.", "United States", "country"),
                          ("DE", "Germany", "country"),
                          ("NY", "New York", "region")]:
            with self.subTest(v=v):
                self.assertEqual(C(v, t, col), {"Abbreviation"})

    def test_pure_abbreviation_precedes_language(self):
        self.assertTrue(m.PURE_ABBREVIATION_BEFORE_LANGUAGE)
        self.assertEqual(C("USA", "United States", "country"), {"Abbreviation"})

    def test_mixed_abbreviation_keeps_label_and_continues(self):
        labels = C("jems str", "james street", "road", lang=False)
        self.assertIn("Abbreviation", labels)
        self.assertIn("Typo", labels)

    def test_ordinals_make_the_pair_a_pure_abbreviation(self):
        self.assertEqual(C("E 50 St", "East 50th Street", "road", lang=False),
                         {"Abbreviation"})
        self.assertEqual(C("8 Ave", "8th Avenue", "road", lang=False),
                         {"Abbreviation"})

    def test_ordinal_expansion_is_one_way(self):
        self.assertEqual(m._ordinal_forms("8"), frozenset({("8th",)}))
        self.assertEqual(m._ordinal_forms("8th"), frozenset())
        self.assertEqual(m._ordinal_forms("21"), frozenset({("21st",)}))
        self.assertEqual(m._ordinal_forms("11"), frozenset({("11th",)}))

    def test_expansion_does_not_corrupt_compound_tokens(self):
        out, _ = m._expand_toward("s. sewall's point road", "south sewalls point road")
        self.assertNotIn("sewall'south", out)
        out, _ = m._expand_toward("buchholz i.d. nordheide", "buchholz in der nordheide")
        self.assertNotIn("in.d.", out)

    def test_article_difference_is_containment_not_abbreviation(self):
        self.assertEqual(C("UPS Store", "The UPS Store", "name", lang=False),
                         {"Token_Subset"})

    def test_names_in_two_languages_are_not_abbreviation(self):
        self.assertFalse(m.is_abbreviation("germany", "deutschland", "country"))
        self.assertTrue(m.is_abbreviation("de", "deutschland", "country"))

    def test_transliteration_is_not_abbreviation(self):
        for v, t in [("München", "Muenchen"), ("Straße", "Strasse")]:
            with self.subTest(v=v):
                self.assertNotIn("Abbreviation", C(v, t, "locality"))
                self.assertIn("Special_Character", C(v, t, "locality"))

    def test_punctuation_only_is_not_abbreviation(self):
        labels = C("Foo, Bar", "Foo Bar", "name")
        self.assertNotIn("Abbreviation", labels)
        self.assertIn("Special_Character", labels)

    def test_expansion_uses_other_sides_original_tokens(self):
        fired, v2, t2 = m.abbreviation_layer("hauptstr.", "hauptstraße", "road")
        self.assertTrue(fired)
        self.assertEqual(v2, t2)

class TestFreeLayer(unittest.TestCase):

    def test_reordering_fires_name_reformat_only(self):
        v = "Howson Branch, Austin Public Library"
        t = "Austin Public Library Howson Branch"
        self.assertTrue(m.is_name_reformat(v.lower(), t.lower()))
        self.assertFalse(m.is_special_character(v.lower(), t.lower()))

    def test_same_order_accent_pair_is_not_reformat(self):
        self.assertFalse(m.is_name_reformat("münchen", "munchen"))

    def test_token_subset_multiset(self):
        self.assertTrue(m.is_token_subset("la pharmacie de la mazelle", "pharmacie de la mazelle"))
        self.assertTrue(m.is_token_subset("new york", "new york city"))
        self.assertFalse(m.is_token_subset("new york", "new york"))

    def test_free_layer_overlaps(self):
        labels = C("VA Clinic", "Outpatient Clinic", "name", lang=False)
        self.assertIn("Semantic", labels)
        labels = C("North Attleboro", "North Attleborough", "locality", lang=False)
        self.assertEqual(labels, {"Formatting"})

    def test_special_character_is_terminal(self):
        for v, t, col in [("foo-bar", "foo bar", "road"),
                          ("Notre-Dame Street", "Notre Dame Street", "road"),
                          ("Strasse", "Straße", "road"),
                          ("Koetschachtaler Strasse", "Kötschachtaler Straße", "road"),
                          ("Shuttleworth®, Inc.", "Shuttleworth Inc", "name"),
                          ("LTD Brewing Co", "LTD Brewing Co.", "name")]:
            with self.subTest(v=v):
                self.assertEqual(C(v, t, col, lang=False), {"Special_Character"})

    def test_name_reformat_is_terminal(self):
        self.assertEqual(
            C("Via Galilei Galileo", "Via Galileo Galilei", "road", lang=False),
            {"Formatting"},
        )

    @LP
    def test_terminal_does_not_erase_abbreviation(self):
        self.assertEqual(
            C("ST HILAIRE DE RIEZ", "Saint-Hilaire-de-Riez", "locality", lang=False),
            {"Abbreviation", "Special_Character"},
        )

    def test_terminal_list_matches_implementation(self):
        self.assertEqual(m.TERMINAL_FREE_RULES, ("Special_Character", "Formatting"))

    def test_word_variant_is_not_string_similarity(self):
        self.assertFalse(m._are_lexically_related("oriente", "poniente"))
        self.assertFalse(m._are_lexically_related("east", "west"))
        self.assertFalse(m._are_lexically_related("north", "northwest"))

    def test_word_variant_catches_real_name_variants(self):
        for a, b in [("attleboro", "attleborough"), ("kiev", "kyiv"),
                     ("cave", "caves"), ("noordrijn", "nordrhein"),
                     ("navarra", "nafarroa"), ("sassonia", "sachsen")]:
            with self.subTest(a=a, b=b):
                self.assertTrue(m._are_lexically_related(a, b))

    def test_no_tuned_constants_remain_in_the_rule(self):
        self.assertEqual([n for n in dir(m) if n.startswith(("MIN_", "MAX_"))], [])

    def test_non_alphabetic_tokens_are_rejected(self):
        self.assertFalse(m._are_lexically_related("01310", "01404"))
        self.assertFalse(m._are_lexically_related("048", "050"))

    def test_short_function_words_do_not_relate(self):
        self.assertFalse(m._are_lexically_related("d", "der"))

    def test_typo_suppresses_the_swap_rule(self):
        self.assertIsNone(m.is_word_variant_or_semantic("manzanares avenue",
                                                        "manzaneres avenue"))

    def test_semantic_rejects_a_non_alphabetic_swap(self):
        self.assertIsNone(m.is_word_variant_or_semantic("t7z 1y4", "t7z 0a2"))
        self.assertEqual(C("T7Z 1Y4", "T7Z 0A2", "road", lang=False, abbrev=False), {"Semantic"})

    def test_number_and_word_are_not_a_substitution(self):
        self.assertIsNone(m._single_token_swap(
            "the guernsey literary & potato peel pie society (2018)",
            "the guernsey literary and potato peel pie society"))
        self.assertIsNone(m.is_word_variant_or_semantic("barb & star go (2021)",
                                                        "barb and star go"))

    @LP
    def test_ampersand_expands_to_the_local_word_for_and(self):
        self.assertEqual(C("Best Western Dothan Inn & Suites",
                           "Best Western Dothan Inn and Suites", "name", lang=False),
                         {"Abbreviation"})
        self.assertEqual(C("Hotel Bourgogne & Montana",
                           "Hotel Bourgogne et Montana", "name", lang=False),
                         {"Abbreviation"})

    def test_symbol_only_abbreviations_survive_normalisation(self):
        self.assertEqual(m._dict_key("&"), "&")
        self.assertIn(("and",), m._dictionary_expansions().get("&", ()))


class TestValueColumns(unittest.TestCase):

    def P(self, val, tru, col):
        return C(val, tru, col, lang=False, parsing=(col == "postcode"), abbrev=False)

    def test_close_values_are_semantic_not_typo(self):
        for v, t, col in [("J3L 3R8", "J3L 3R9", "postcode"),
                          ("119021", "119034", "postcode"),
                          ("T7Z 1Y4", "T7Z 0A2", "postcode"),
                          ("2611 PK", "2611 PN", "postcode"),
                          ("288", "285", "number_of_pages"),
                          ("500", "918", "number_of_pages")]:
            with self.subTest(v=v, t=t):
                self.assertEqual(self.P(v, t, col), {"Semantic"})

    def test_format_only_differences_keep_their_labels(self):
        self.assertEqual(self.P("H2Z1R1", "H2Z 1R1", "postcode"), {"Special_Character"})
        self.assertEqual(self.P("78412-3910", "78412", "postcode"), {"Token_Subset"})
        self.assertEqual(self.P("624 pages", "624", "number_of_pages"), {"Token_Subset"})
        self.assertEqual(self.P("", "416", "number_of_pages"), {"Missing"})

    def test_empty_clean_side_has_nothing_to_disagree_with(self):
        self.assertEqual(self.P("320", "", "number_of_pages"), set())

@LP
class TestWordForms(unittest.TestCase):

    def test_number_forms_are_word_variants(self):
        for v, t in [("Viale Xx Settembre", "Viale Venti Settembre"),
                     ("Viale XX Settembre", "Viale 20 Settembre"),
                     ("5th Avenue", "Fifth Avenue"),
                     ("Calle II", "Calle 2")]:
            with self.subTest(v=v, t=t):
                self.assertEqual(CW(v, t), {"Formatting"})

    def test_number_form_keeps_the_other_change(self):
        self.assertEqual(CW("1° Maggio", "Via Primo Maggio"), {"Formatting", "Token_Subset"})
        self.assertEqual(CW("5th Ave", "Fifth Avenue"), {"Formatting", "Abbreviation"})

    def test_different_numbers_and_house_letters_are_not(self):
        self.assertEqual(CW("5th Ave", "6th Ave"), {"Typo"})
        self.assertNotIn("Formatting", C("12/14", "12/14D", "house_number"))

    def test_street_types_of_one_language(self):
        self.assertEqual(CW("Main Highway", "Main Road"), {"Formatting"})
        self.assertEqual(CW("Washington St", "Washington Avenue"), {"Formatting"})
        self.assertEqual(CW("Calle Amador Fernández", "Rúa Amador Fernández"), {"Language"})

    def test_compound_street_abbreviation(self):
        self.assertEqual(CW("James-F.-Byrnes-Str.", "James-F.-Byrnes-Straße"), {"Abbreviation"})

    def test_street_types_only_on_roads(self):
        self.assertNotIn("Formatting", C("Java Center", "Java Village", "locality"))

@LP
class TestFatemehDoc(unittest.TestCase):

    ADDRESS = [
        ("locality", "London", "City of Westminster", {"Semantic"}),
        ("locality", "Unionville", "Farmington", {"Semantic"}),
        ("locality", "Lido di Savio", "Ravenna", {"Semantic"}),
        ("locality", "Allston", "Boston", {"Semantic"}),
        ("locality", "Flushing", "New York", {"Semantic"}),
        ("locality", "Alameda-County", "Berkeley", {"Semantic"}),
        ("region", "Tenerife", "Canarias", {"Semantic"}),
        ("road", "Burg. Winklerplein", "Burgemeester Winklerplein", {"Abbreviation"}),
        ("road", "De-La-Chevallerie-Str.", "De-la-Chevallerie-Straße", {"Abbreviation"}),
        ("road", "Metro Pkwy", "Metropolitan Parkway", {"Abbreviation"}),
        ("road", "C/La Ermita", "Calle La Ermita", {"Abbreviation"}),
        ("road", "Washington St", "Washington Avenue", {"Formatting"}),
        ("road", "Wisconsin Highway 155", "State Highway 155", {"Formatting"}),
        ("road", "Viale Xx Settembre", "Viale Venti Settembre", {"Formatting"}),
        ("road", "Rue St Jean En Isle", "Rue Saint-Jean-en-Île", {"Abbreviation", "Typo"}),
        ("road", "Calle Amador Fernández", "Rúa Amador Fernández", {"Language"}),
        ("road", "Calle Guillem De Castro", "Carrer de Guillem de Castro", {"Language"}),
        ("road", "Calle Perez Galdos", "Perez Galdos kalea", {"Language"}),
        ("road", "Saint Jacques Street", "Rue Saint-Jacques", {"Language"}),
        ("road", "Laan", "Leonardo Da Vincilaan", {"Token_Subset"}),
        ("locality", "Warsaw", "Warszawa", {"Language"}),
        ("region", "Galice", "Galicia", {"Language"}),
        ("country", "Canadá", "Canada", {"Language"}),
        ("country", "스페인", "España", {"Language"}),
        ("locality", "Columbia Station", "Columbia Township", {"Formatting"}),
        ("locality", "Spokane WA", "Spokane Valley", {"Token_Subset"}),
        ("region", "Noordrijn-Westfalen", "Nordrhein-Westfalen", {"Language"}),
        ("region", "North Holland", "Noord-Holland", {"Language"}),
        ("country", "ABD", "United States", {"Language"}),
    ]

    OTHER = [
        ("isbn", "978-5-389-04324-4", "9785389043244, 5389043243", {"Formatting"}),
        ("author", "Шамиль Идиатуллин", "Shamilʹ Idiatullin", {"Language"}),
        ("duration", "PT2M00S", "PT1M59S", {"Formatting"}),
        ("date_published", "Feb 21, 2014", "2014-02-21", {"Formatting"}),
        ("publisher", "Editorial Blue Dolphin Publishing", "Blue Dolphin Pub.",
         {"Abbreviation", "Token_Subset"}),
        ("title", "Clown Motel (2023)", "The Curse of the Clown Motel", {"Token_Subset"}),
    ]

    def test_address_pairs(self):
        for col, v, t, want in self.ADDRESS:
            with self.subTest(col=col, v=v, t=t):
                self.assertEqual(set(m.classify(m.normalize_cell(v), m.normalize_cell(t), col,
                                                True, True, True, None, col != "locality",
                                                True)), want)

    def test_other_domain_pairs(self):
        text = {"title", "author", "publisher"}
        for col, v, t, want in self.OTHER:
            with self.subTest(col=col, v=v, t=t):
                c = col in text
                self.assertEqual(set(m.classify(m.normalize_cell(v), m.normalize_cell(t), col,
                                                c, c, c)), want)

    def test_same_language_names_and_ambiguous_places(self):
        self.assertNotIn("Language", self.cls("country", "Czechia", "Czech Republic"))
        self.assertEqual(self.cls("country", "Polen", "Polska"), {"Language"})
        self.assertEqual(self.cls("locality", "Manhattan", "New York"), {"Semantic"})
        self.assertEqual(self.cls("region", "Manhattan", "New York"), {"Semantic"})

    def test_two_listed_names_a_letter_apart_are_not_a_typo(self):
        for col, v, t in [("region", "Misuri", "Missouri"), ("country", "Itali", "Italia"),
                          ("locality", "Bilbo", "Bilbao")]:
            with self.subTest(v=v, t=t):
                self.assertEqual(self.cls(col, v, t), {"Language"})
        self.assertNotIn("Language", self.cls("locality", "St-Eustache", "Saint-Eustache"))
        self.assertNotIn("Language", self.cls("country", "Česká republika", "Česko"))

    def cls(self, col, v, t):
        return set(m.classify(m.normalize_cell(v), m.normalize_cell(t), col,
                              True, True, True, None, col != "locality", True))

    def test_value_columns_compare_values(self):
        self.assertEqual(C("2014", "Feb 21, 2014", "date_published"), {"Token_Subset"})
        self.assertEqual(C("2019-01-25", "2018", "date_published"), {"Semantic"})
        self.assertEqual(C("PT98M", "98", "duration"), {"Formatting"})
        self.assertEqual(C("T0DT0H2M7S", "130", "duration"), {"Semantic"})
        self.assertEqual(C("9780143102434", "9788418789243", "isbn"), {"Semantic"})

    def test_residual_is_semantic_but_not_without_a_clean_value(self):
        self.assertEqual(C("Mingerstrasse", "Tschäppätstrasse"), {"Semantic"})
        self.assertEqual(C("Triangle Square", "", "publisher"), set())

class TestRegionHoldsLocality(unittest.TestCase):

    def R(self, dr, cr, dl, cl, labels):
        return set(m.region_holds_locality(frozenset(labels), dr, cr, dl, cl))

    def test_town_in_region_is_semantic(self):
        self.assertEqual(self.R("Kitzbühel", "Tirol", "Kitzbühel", "Kitzbühel", {"Language"}),
                         {"Semantic"})
        self.assertEqual(self.R("Baden", "Niederösterreich", "Baden", "Baden", set()),
                         {"Semantic"})

    def test_shared_name_and_placeholders_are_left_alone(self):
        self.assertEqual(self.R("Madrid", "Comunidad de Madrid", "Madrid", "Madrid",
                                {"Token_Subset"}), {"Token_Subset"})
        self.assertEqual(self.R("-", "Texas", "-", "Fort Worth", set()), set())

    def test_city_state_translation_is_left_alone(self):
        self.assertEqual(self.R("Lisbon", "Lisboa", "Lisbon", "Lisboa", {"Language"}),
                         {"Language"})

    def test_spelling_and_short_forms_are_left_alone(self):
        self.assertEqual(self.R("Quebec", "Québec", "Quebec", "Montréal", {"Typo"}), {"Typo"})
        self.assertEqual(self.R("TX", "Texas", "TX", "Austin", {"Abbreviation"}),
                         {"Abbreviation"})

    def test_region_that_is_not_the_town_is_left_alone(self):
        self.assertEqual(self.R("Tyrol", "Tirol", "Kitzbühel", "Kitzbühel", {"Language"}),
                         {"Language"})

class TestFormattingMerge(unittest.TestCase):
    def test_formatting_is_a_label(self):
        self.assertIn("Formatting", m.LABELS)

    def test_both_rules_firing_gives_one_label(self):
        self.assertEqual(C("5th avenue", "avenue fifth", "road"), {"Formatting"})

    def test_reorder_alone(self):
        self.assertEqual(C("South 37th Avenue", "37th Avenue South", "road"), {"Formatting"})

if __name__ == "__main__":
    unittest.main()
