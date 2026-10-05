import unittest

from app.models import RecognizedBatter
from ocr.engine import OcrEngine
from ocr.preprocess import normalize_screen
from parser.batter_parser import PlayerRowImage, extract_player_rows, merge_batter_screens, parse_batter_screen, recognize_stat_number
from parser.screen_regions import Region, load_batter_layout


class FakeOcrEngine(OcrEngine):
    def __init__(self, number: str) -> None:
        self.number = number

    def recognize_text(self, image) -> str:  # type: ignore[no-untyped-def]
        return ""

    def recognize_number(self, image) -> str:  # type: ignore[no-untyped-def]
        return self.number


class ParserOcrEngine(OcrEngine):
    def recognize_text(self, image) -> str:  # type: ignore[no-untyped-def]
        return "京極遥人"

    def recognize_number(self, image) -> str:  # type: ignore[no-untyped-def]
        return "3"


class AliasOcrEngine(ParserOcrEngine):
    def recognize_text(self, image) -> str:  # type: ignore[no-untyped-def]
        return "天宮凪"


class BatterParserTests(unittest.TestCase):
    def test_stat_number_keeps_empty_and_unreadable_distinct(self) -> None:
        import numpy as np

        cell = object()
        self.assertEqual(recognize_stat_number(cell, FakeOcrEngine("")), 0)
        self.assertEqual(recognize_stat_number(cell, FakeOcrEngine("12")), 12)
        self.assertIsNone(recognize_stat_number(cell, FakeOcrEngine("O?")))

        # A blank PowerPro stat cell must be 0 even if OCR mistakes its border
        # for punctuation. A cell containing dark ink remains a review error.
        blank_cell = np.full((56, 88, 3), (245, 245, 245), dtype=np.uint8)
        self.assertEqual(recognize_stat_number(blank_cell, FakeOcrEngine("O?")), 0)
        inked_cell = blank_cell.copy()
        inked_cell[16:40, 32:48] = 90
        self.assertIsNone(recognize_stat_number(inked_cell, FakeOcrEngine("O?")))

    def test_extracts_a_detected_row_into_a_review_record(self) -> None:
        import numpy as np

        layout = load_batter_layout()
        image = np.full((1080, 1920, 3), 255, dtype=np.uint8)
        name = layout.columns["name"]
        # A synthetic dark glyph in the first row should pass the isolated
        # name-cell ink test; no fixed player count is assumed.
        image[layout.first_row_y + 8:layout.first_row_y + 26, name.x + 12:name.x + 42] = 0
        for field_name, region in layout.columns.items():
            if field_name != "name":
                image[layout.first_row_y + 12:layout.first_row_y + 36, region.x + 24:region.x + 40] = 90

        records, rows = parse_batter_screen(image, ("京極遥人",), ParserOcrEngine(), layout)

        self.assertEqual(len(rows), 1)
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0].matched_name, "京極遥人")
        self.assertEqual(records[0].at_bats, 3)
        self.assertEqual(records[0].sac_flies, 0)

    def test_passes_aliases_to_name_matching_without_prefix_matching(self) -> None:
        import numpy as np

        layout = load_batter_layout()
        image = np.full((1080, 1920, 3), 255, dtype=np.uint8)
        name = layout.columns["name"]
        image[layout.first_row_y + 8:layout.first_row_y + 26, name.x + 12:name.x + 42] = 0

        records, _rows = parse_batter_screen(
            image,
            ("天宮悠季", "天宮凪澄"),
            AliasOcrEngine(),
            layout,
            {"天宮": "天宮悠季", "天宮凪": "天宮凪澄"},
        )

        self.assertEqual(records[0].matched_name, "天宮凪澄")
        self.assertEqual(records[0].match_source, "alias")
        self.assertFalse(records[0].requires_review)

    def test_normalizes_half_resolution_screenshots_before_extraction(self) -> None:
        import cv2
        import numpy as np

        layout = load_batter_layout()
        full_size = np.full((1080, 1920, 3), 255, dtype=np.uint8)
        name = layout.columns["name"]
        full_size[layout.first_row_y + 8:layout.first_row_y + 26, name.x + 12:name.x + 42] = 0
        half_size = cv2.resize(full_size, (960, 540), interpolation=cv2.INTER_AREA)

        records, rows = parse_batter_screen(half_size, ("京極遥人",), ParserOcrEngine(), layout)

        self.assertEqual(len(rows), 1)
        self.assertEqual(len(records), 1)

    def test_normalization_removes_window_chrome_around_letterboxed_game_viewport(self) -> None:
        import cv2
        import numpy as np

        # Simulate a 1793x1009 (16:9) game render inside a 1920x1080 desktop
        # capture with a title bar, taskbar, and black pillar boxes.
        game = np.full((1080, 1920, 3), (50, 180, 90), dtype=np.uint8)
        viewport = cv2.resize(game, (1793, 1009), interpolation=cv2.INTER_AREA)
        capture = np.zeros((1080, 1920, 3), dtype=np.uint8)
        capture[:23] = (245, 245, 245)
        capture[1032:] = (45, 45, 45)
        capture[23:1032, 64:1857] = viewport

        normalized = normalize_screen(capture)

        self.assertEqual(normalized.shape, (1080, 1920, 3))
        self.assertTrue(np.array_equal(normalized[20, 20], game[20, 20]))

    def test_normalization_keeps_native_black_framed_game_screenshot_unscaled(self) -> None:
        import numpy as np

        image = np.zeros((1080, 1920, 3), dtype=np.uint8)
        image[32:1048, 58:1862] = (50, 180, 90)

        normalized = normalize_screen(image)

        self.assertTrue(np.array_equal(normalized, image))

    def test_red_pitcher_name_plate_is_excluded_before_ocr(self) -> None:
        import numpy as np

        layout = load_batter_layout()
        image = np.full((1080, 1920, 3), 255, dtype=np.uint8)
        name = layout.columns["name"]
        y = layout.first_row_y
        image[y:y + layout.row_height, name.x:name.x + name.width] = (121, 121, 255)
        image[y + 8:y + 26, name.x + 12:name.x + 42] = 0

        self.assertEqual(extract_player_rows(image, layout), [])

    def test_merges_overlapping_screens_and_keeps_empty_ocr_failures(self) -> None:
        def row(index: int) -> PlayerRowImage:
            return PlayerRowImage(index, Region(0, 0, 1, 1), object(), object(), {})

        first = RecognizedBatter(ocr_name="浅井", matched_name="浅井太郎", source_row_index=0)
        duplicate = RecognizedBatter(ocr_name="浅井", matched_name="浅井太郎", source_row_index=0)
        failure_one = RecognizedBatter(ocr_name="", source_row_index=1)
        failure_two = RecognizedBatter(ocr_name="", source_row_index=1)

        # Exercise the isolated merge policy without an OCR/image dependency.
        import parser.batter_parser as module
        original = module.parse_batter_screen
        results = iter([([first, failure_one], [row(0), row(1)]), ([duplicate, failure_two], [row(0), row(1)])])
        module.parse_batter_screen = lambda *_args, **_kwargs: next(results)
        try:
            records, rows = merge_batter_screens([object(), object()], (), ParserOcrEngine())
        finally:
            module.parse_batter_screen = original

        self.assertEqual([record.matched_name for record in records], ["浅井太郎", None, None])
        self.assertEqual([record.source_row_index for record in records], [0, 1, 2])
        self.assertEqual([value.row_index for value in rows], [0, 1, 2])
