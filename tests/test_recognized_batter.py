import unittest

from app.models import RecognizedBatter


class RecognizedBatterTests(unittest.TestCase):
    def test_unrecognized_number_remains_an_error(self) -> None:
        batter = RecognizedBatter(matched_name="京極遥人", at_bats=None)

        self.assertEqual(batter.status, "エラー")
        self.assertEqual(batter.ocr_stats["at_bats"], None)
        with self.assertRaises(ValueError):
            batter.to_batter_stats()

    def test_manual_edit_preserves_original_ocr_value(self) -> None:
        batter = RecognizedBatter(matched_name="京極遥人", requires_review=False, at_bats=3, runs=0, hits=1,
                                  doubles=0, triples=0, home_runs=0, rbi=1, strikeouts=0, walks_hbp=0,
                                  sacrifices=0, steals=0, double_plays=0, errors=0, sac_flies=0)

        batter.set_stat("at_bats", 2)

        self.assertEqual(batter.ocr_stats["at_bats"], 3)
        self.assertEqual(batter.at_bats, 2)
        self.assertIn("at_bats", batter.manually_corrected_stats)
        self.assertEqual(batter.status, "OK")

    def test_review_reasons_name_missing_stats_and_remarks_are_serialized(self) -> None:
        batter = RecognizedBatter(at_bats=None, remarks="代打")

        self.assertIn("正式名が未選択", batter.review_reasons)
        self.assertIn("数値が未入力: 打数", batter.review_reason_text)
        self.assertEqual(batter.to_serializable_dict()["remarks"], "代打")
