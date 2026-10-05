"""Local PaddleOCR implementation for fixed PowerPro table cells."""

from __future__ import annotations

import os
import re
import traceback
from datetime import datetime
from pathlib import Path
from typing import Any

from ocr.engine import OcrEngine, OcrEngineUnavailableError
from ocr.preprocess import preprocess_name_cell, preprocess_number_cell


class PaddleOcrEngine(OcrEngine):
    """One local Japanese-capable recognizer shared across every table cell.

    The fixed-layout parser already isolates individual text lines, so this uses
    PaddleOCR's recognition module directly and does not spend time running a
    text-detector on every cell.
    """

    MODEL_NAME = "PP-OCRv5_mobile_rec"

    def __init__(self, model_name: str = MODEL_NAME) -> None:
        try:
            # Official docs support BOS as a model source when HuggingFace is
            # unavailable.  Keep an explicit user choice intact.
            os.environ.setdefault("PADDLE_PDX_MODEL_SOURCE", "BOS")
            # PaddleX defaults to ~/.paddlex, which is unsuitable for a
            # portable Windows application and can be permission-restricted.
            # Keep its downloaded model/cache inside this project instead.
            cache_dir = Path(__file__).resolve().parents[2] / "runtime" / "paddlex"
            os.environ.setdefault("PADDLE_PDX_CACHE_HOME", str(cache_dir))
            from paddleocr import TextRecognition
        except ImportError as error:
            raise OcrEngineUnavailableError(
                "PaddleOCRがありません。`python -m pip install -r requirements.txt` を実行してください"
            ) from error
        try:
            self._recognizer = TextRecognition(
                model_name=model_name,
                device="cpu",
                engine="paddle",
            )
        except Exception as error:
            raise self._initialization_error(error) from error

    def recognize_text(self, image: Any) -> str:
        return self._recognize(self._as_bgr(preprocess_name_cell(image)))

    def recognize_number(self, image: Any) -> str:
        # Deliberately preserve non-digits here. recognize_stat_number converts
        # any ambiguous result to None instead of silently writing zero.
        return self._recognize(self._as_bgr(preprocess_number_cell(image)))

    @staticmethod
    def _as_bgr(image: Any) -> Any:
        """PaddleOCR TextRecognition requires a three-channel input image."""
        if getattr(image, "ndim", 0) == 2:
            import cv2
            return cv2.cvtColor(image, cv2.COLOR_GRAY2BGR)
        return image

    def _recognize(self, image: Any) -> str:
        try:
            results = self._recognizer.predict(input=image, batch_size=1)
            result = next(iter(results), None)
            return self._extract_text(result)
        except Exception as error:
            raise OcrEngineUnavailableError("PaddleOCRによるセル認識に失敗しました") from error

    @staticmethod
    def _initialization_error(error: Exception) -> OcrEngineUnavailableError:
        """Keep the actionable frozen-app failure visible without losing its traceback.

        A windowed PyInstaller build has no console, so an exception chained to
        ``OcrEngineUnavailableError`` would otherwise be invisible.  Persist it
        in the user's local app-data folder and include the exception summary in
        the GUI error dialog.  This is especially useful for a missing DLL or a
        PaddleX dynamic-import omission in a packaged build.
        """
        log_path: Path | None = None
        try:
            app_data = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
            log_dir = app_data / "JPBL PowerPro Importer" / "logs"
            log_dir.mkdir(parents=True, exist_ok=True)
            log_path = log_dir / "paddleocr-initialization.log"
            with log_path.open("a", encoding="utf-8") as log_file:
                log_file.write(f"\n{'=' * 72}\n{datetime.now().isoformat(timespec='seconds')}\n")
                log_file.writelines(traceback.format_exception(type(error), error, error.__traceback__))
        except OSError:
            # Failing to write a diagnostic must not hide the OCR error itself.
            log_path = None

        detail = " ".join(str(error).split()) or "詳細メッセージなし"
        # A GUI notification should remain readable even when a backend emits
        # a very long environment dump.
        if len(detail) > 600:
            detail = f"{detail[:597]}..."
        message = (
            "PaddleOCRの認識モデルを初期化できません。\n"
            f"詳細: {type(error).__name__}: {detail}"
        )
        if log_path is not None:
            message += f"\n詳細ログ: {log_path}"
        return OcrEngineUnavailableError(message)

    @staticmethod
    def _extract_text(result: Any) -> str:
        """Read the documented TextRecognition Result.json response shape."""
        if result is None:
            return ""
        payload = getattr(result, "json", result)
        if callable(payload):
            payload = payload()
        if not isinstance(payload, dict):
            return ""
        value = payload.get("res", {}).get("rec_text", "")
        return re.sub(r"\s+", "", value) if isinstance(value, str) else ""
