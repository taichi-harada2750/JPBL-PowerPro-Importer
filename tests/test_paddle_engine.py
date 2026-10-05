import unittest

import numpy as np

from ocr.engines.paddle_engine import PaddleOcrEngine


class FakeResult:
    def __init__(self, payload) -> None:
        self.json = payload


class PaddleOcrEngineTests(unittest.TestCase):
    def test_reads_documented_recognition_result_shape(self) -> None:
        result = FakeResult({"res": {"rec_text": " 有 島 登 \n", "rec_score": 0.99}})

        self.assertEqual(PaddleOcrEngine._extract_text(result), "有島登")

    def test_empty_or_unexpected_result_is_not_invented(self) -> None:
        self.assertEqual(PaddleOcrEngine._extract_text(None), "")
        self.assertEqual(PaddleOcrEngine._extract_text(FakeResult({"res": {}})), "")

    def test_converts_preprocessed_gray_image_to_three_channels(self) -> None:
        gray = np.zeros((3, 5), dtype=np.uint8)

        image = PaddleOcrEngine._as_bgr(gray)

        self.assertEqual(image.shape, (3, 5, 3))
