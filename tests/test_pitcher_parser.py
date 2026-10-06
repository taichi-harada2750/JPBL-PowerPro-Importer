import unittest

from app.models import RecognizedPitcher
from ocr.engine import OcrEngine
from parser.batter_parser import PlayerRowImage
from parser.pitcher_parser import merge_pitcher_screens, parse_innings_text, parse_pitcher_decision, parse_pitcher_screen, recognize_innings
from parser.screen_regions import Region, load_pitcher_layout


class PitcherOcrEngine(OcrEngine):
    def recognize_text(self, image) -> str:  # type: ignore[no-untyped-def]
        return "朴陶恒"

    def recognize_number(self, image) -> str:  # type: ignore[no-untyped-def]
        return "6"


class FractionGlyphOcrEngine(OcrEngine):
    """Represents PaddleOCR's observed 6⅔ -> 6% output."""

    def recognize_text(self, image) -> str:  # type: ignore[no-untyped-def]
        return ""

    def recognize_number(self, image) -> str:  # type: ignore[no-untyped-def]
        height, width = image.shape[:2]
        if (height, width) == (56, 140):
            return "6%"
        if (height, width) == (56, 84):
            return "6"
        if height == 28 and width == 82:
            # The upper/lower crops have identical dimensions; a simple test
            # fixture marks the upper crop with a distinct first pixel.
            return "22/" if image[0, 0, 0] == 1 else "073"
        return ""


class WholeInningsOcrEngine(OcrEngine):
    def __init__(self) -> None:
        self.number_calls = 0

    def recognize_text(self, image) -> str:  # type: ignore[no-untyped-def]
        return ""

    def recognize_number(self, image) -> str:  # type: ignore[no-untyped-def]
        self.number_calls += 1
        return "1"


class PitcherParserTests(unittest.TestCase):
    def test_excluded_pitcher_has_a_distinct_non_blocking_status(self) -> None:
        pitcher = RecognizedPitcher(excluded_from_export=True)

        self.assertEqual(pitcher.status, "除外")
        self.assertEqual(pitcher.review_reason_text, "GameJSON出力から手動で除外")
        self.assertTrue(pitcher.to_serializable_dict()["excludedFromExport"])

    def test_parses_whole_and_fractional_innings_without_guessing(self) -> None:
        self.assertEqual(parse_innings_text("5"), (5, 0))
        self.assertEqual(parse_innings_text("8 2/3"), (8, 2))
        self.assertEqual(parse_innings_text("0 1/3"), (0, 1))
        self.assertEqual(parse_innings_text("82/3"), (8, 2))
        self.assertEqual(parse_innings_text("8⅔"), (8, 2))
        self.assertEqual(parse_innings_text("５⅓"), (5, 1))
        self.assertEqual(parse_innings_text("１⅔"), (1, 2))
        self.assertEqual(parse_innings_text("０ ２／３"), (0, 2))
        self.assertIsNone(parse_innings_text("8.5"))

    def test_recognizes_compact_powerpro_fraction_glyph_after_percent_misread(self) -> None:
        import numpy as np

        cell = np.zeros((56, 140, 3), dtype=np.uint8)
        cell[0, 58, 0] = 1  # First pixel of the numerator subcrop.
        self.assertEqual(recognize_innings(cell, FractionGlyphOcrEngine()), (6, 2))

    def test_recognizes_whole_innings_without_fraction_subcrops(self) -> None:
        import numpy as np

        engine = WholeInningsOcrEngine()
        self.assertEqual(recognize_innings(np.zeros((56, 140, 3), dtype=np.uint8), engine), (1, 0))
        self.assertEqual(engine.number_calls, 1)

    def test_maps_name_side_decision_markers_to_manual_flags(self) -> None:
        self.assertEqual(parse_pitcher_decision("勝"), {"wins": 1, "losses": 0, "holds": 0, "saves": 0})
        self.assertEqual(parse_pitcher_decision("敗"), {"wins": 0, "losses": 1, "holds": 0, "saves": 0})
        self.assertEqual(parse_pitcher_decision("H"), {"wins": 0, "losses": 0, "holds": 1, "saves": 0})
        self.assertEqual(parse_pitcher_decision("S"), {"wins": 0, "losses": 0, "holds": 0, "saves": 1})

    def test_reads_pitcher_row_and_matches_pitcher_candidates(self) -> None:
        import numpy as np

        layout = load_pitcher_layout()
        image = np.full((1080, 1920, 3), 255, dtype=np.uint8)
        name = layout.columns["name"]
        image[layout.first_row_y + 8:layout.first_row_y + 26, name.x + 12:name.x + 42] = 0
        pitches = layout.columns["pitches"]
        image[layout.first_row_y + 12:layout.first_row_y + 36, pitches.x + 24:pitches.x + 40] = 90

        records, rows = parse_pitcher_screen(image, ("朴陶恒",), PitcherOcrEngine(), layout)

        self.assertEqual(len(rows), 1)
        self.assertEqual(records[0].matched_name, "朴陶恒")
        self.assertEqual((records[0].innings, records[0].inning_fraction), (6, 0))
        self.assertEqual(records[0].pitches, 6)
        self.assertEqual(records[0].starts, 1)

    def test_recognized_pitcher_qs_hqs_and_validation(self) -> None:
        values = {name: 0 for name in (
            "innings", "inning_fraction", "pitches", "batters_faced", "hits_allowed", "strikeouts",
            "walks_hbp", "runs", "earned_runs", "wild_pitches", "home_runs_allowed",
        )}
        pitcher = RecognizedPitcher(matched_name="朴陶恒", requires_review=False, **values)

        pitcher.set_stat("innings", 6)
        pitcher.set_stat("earned_runs", 3)
        self.assertEqual(pitcher.qs_hqs, (1, 0))
        pitcher.set_stat("innings", 7)
        pitcher.set_stat("earned_runs", 2)
        self.assertEqual(pitcher.qs_hqs, (1, 1))
        pitcher.set_stat("innings", 5)
        pitcher.set_stat("inning_fraction", 2)
        self.assertEqual(pitcher.qs_hqs, (0, 0))
        with self.assertRaises(ValueError):
            pitcher.set_stat("inning_fraction", 3)

    def test_automatic_pitcher_flags_treat_a_single_pitcher_as_complete_game(self) -> None:
        values = {name: 0 for name in (
            "innings", "inning_fraction", "pitches", "batters_faced", "hits_allowed", "strikeouts",
            "walks_hbp", "runs", "earned_runs", "wild_pitches", "home_runs_allowed",
        )}
        values["innings"] = 5
        single = RecognizedPitcher(**values)
        single.refresh_automatic_fields(is_starting_pitcher=True, only_pitcher=True)
        self.assertEqual((single.starts, single.complete_games, single.shutouts, single.no_walk_games), (1, 1, 1, 1))

        values["innings"] = 8
        multiple = RecognizedPitcher(**values)
        multiple.refresh_automatic_fields(is_starting_pitcher=False, only_pitcher=False)
        self.assertEqual((multiple.starts, multiple.complete_games, multiple.shutouts, multiple.no_walk_games), (0, 0, 0, 0))

    def test_manual_automatic_flag_correction_is_not_overwritten(self) -> None:
        values = {name: 0 for name in (
            "innings", "inning_fraction", "pitches", "batters_faced", "hits_allowed", "strikeouts",
            "walks_hbp", "runs", "earned_runs", "wild_pitches", "home_runs_allowed",
        )}
        values["innings"] = 9
        pitcher = RecognizedPitcher(**values)
        pitcher.refresh_automatic_fields(only_pitcher=True)
        self.assertEqual((pitcher.qs, pitcher.hqs, pitcher.complete_games), (1, 1, 1))
        pitcher.set_stat("qs", 0)
        pitcher.set_stat("hqs", 0)
        pitcher.set_stat("complete_games", 0)
        pitcher.refresh_automatic_fields(only_pitcher=True)
        self.assertEqual((pitcher.qs, pitcher.hqs, pitcher.complete_games), (0, 0, 0))

    def test_unrecognized_pitcher_value_and_name_remain_review_errors(self) -> None:
        pitcher = RecognizedPitcher(innings=None, inning_fraction=None)

        self.assertEqual(pitcher.status, "エラー")
        self.assertIn("正式名が未選択", pitcher.review_reasons)
        self.assertIn("投球回", pitcher.review_reason_text)
        with self.assertRaises(ValueError):
            pitcher.to_pitcher_stats()

    def test_merges_two_overlapping_pitcher_screens_for_preview_and_review(self) -> None:
        def row(index: int) -> PlayerRowImage:
            return PlayerRowImage(index, Region(0, 0, 1, 1), object(), object(), {})

        first = RecognizedPitcher(ocr_name="荒崎", matched_name="荒崎", source_row_index=0)
        duplicate = RecognizedPitcher(ocr_name="荒崎", matched_name="荒崎", source_row_index=0)
        second = RecognizedPitcher(ocr_name="千葉", matched_name="千葉", source_row_index=1)

        import parser.pitcher_parser as module
        original = module.parse_pitcher_screen
        results = iter([([first], [row(0)]), ([duplicate, second], [row(0), row(1)])])
        module.parse_pitcher_screen = lambda *_args, **_kwargs: next(results)
        try:
            records, rows = merge_pitcher_screens([object(), object()], (), PitcherOcrEngine())
        finally:
            module.parse_pitcher_screen = original

        self.assertEqual([record.matched_name for record in records], ["荒崎", "千葉"])
        self.assertEqual([record.source_row_index for record in records], [0, 1])
        self.assertEqual([value.row_index for value in rows], [0, 1])
        self.assertEqual([record.starts for record in records], [1, 0])
