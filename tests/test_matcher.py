import unittest

from ocr.matcher import match_player_name


class NameMatcherTests(unittest.TestCase):
    def test_exact_match_is_auto_confirmable(self) -> None:
        result = match_player_name("李珉碩", ("李珉碩", "金賢殖"))

        self.assertEqual(result.matched_name, "李珉碩")
        self.assertEqual(result.score, 100.0)
        self.assertEqual(result.match_source, "exact")
        self.assertFalse(result.requires_review)

    def test_empty_ocr_never_becomes_an_official_name(self) -> None:
        result = match_player_name("", ("李珉碩",))

        self.assertIsNone(result.matched_name)
        self.assertTrue(result.requires_review)

    def test_close_top_two_candidates_require_review(self) -> None:
        # One glyph difference in a long string keeps the score gap below the
        # configured 10-point safety margin.
        result = match_player_name("あいうえおかきくけこさ", ("あいうえおかきくけこさ", "あいうえおかきくけこし"))

        self.assertTrue(result.requires_review)
        self.assertEqual(result.matched_name, "あいうえおかきくけこさ")

    def test_normalizes_middle_dot_and_long_vowel_ocr_variants(self) -> None:
        result = match_player_name("H·S·ロバ-ト", ("H・S・ロバート",))

        self.assertEqual(result.matched_name, "H・S・ロバート")
        self.assertEqual(result.score, 100.0)

    def test_alias_exact_match_has_priority_and_needs_no_review(self) -> None:
        result = match_player_name(
            "天宮",
            ("天宮悠季", "天宮凪澄"),
            {"天宮": "天宮悠季", "天宮凪": "天宮凪澄"},
        )

        self.assertEqual(result.matched_name, "天宮悠季")
        self.assertEqual(result.match_source, "alias")
        self.assertFalse(result.requires_review)

    def test_alias_comparison_is_full_string_only(self) -> None:
        aliases = {"天宮": "天宮悠季", "天宮凪": "天宮凪澄"}
        result = match_player_name("天宮凪", ("天宮悠季", "天宮凪澄"), aliases)

        self.assertEqual(result.matched_name, "天宮凪澄")
        self.assertEqual(result.match_source, "alias")

    def test_nonmatching_text_never_fuzzy_matches_aliases(self) -> None:
        result = match_player_name("天宮風", ("全く別の選手",), {"天宮": "天宮悠季"})

        self.assertEqual(result.match_source, "fuzzy")
        self.assertNotEqual(result.matched_name, "天宮悠季")
