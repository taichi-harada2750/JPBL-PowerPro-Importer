"""Pitcher-screen extraction and OCR-to-review-model conversion."""

from __future__ import annotations

import re
from typing import Any, Mapping

from app.models import PITCHER_OCR_FIELDS, RecognizedPitcher
from ocr.engine import OcrEngine
from ocr.matcher import match_player_name
from parser.batter_parser import PlayerRowImage, extract_player_rows, recognize_stat_number
from parser.screen_regions import BatterScreenLayout, align_pitcher_layout, load_pitcher_layout


def parse_innings_text(raw: str) -> tuple[int, int] | None:
    """Parse PowerPro's whole/third-inning display without guessing failures."""
    value = raw.strip().replace(" ", "")
    if re.fullmatch(r"\d+", value):
        return int(value), 0
    thirds = {"⅓": 1, "⅔": 2}
    for symbol, fraction in thirds.items():
        match = re.fullmatch(rf"(\d+){symbol}", value)
        if match:
            return int(match.group(1)), fraction
    # Covers 8 2/3, 8.2/3 and OCR output 82/3 (last digit is the fraction).
    match = re.fullmatch(r"(\d+?)[ .]?([12])/3", value)
    if match:
        return int(match.group(1)), int(match.group(2))
    return None


def recognize_innings(image: Any, ocr_engine: OcrEngine) -> tuple[int, int] | None:
    parsed = parse_innings_text(ocr_engine.recognize_number(image))
    if parsed is not None:
        return parsed
    # PowerPro draws 1/3 and 2/3 as compact, stacked fraction glyphs.  The
    # general recognizer currently reads both glyphs as "%" (for example,
    # "6⅔" -> "6%"), so retry only this failed cell as three regions.
    height, width = image.shape[:2]
    whole_text = ocr_engine.recognize_number(image[:, :int(width * 0.60)]).strip()
    numerator_text = ocr_engine.recognize_number(image[:height // 2, int(width * 0.42):])
    denominator_text = ocr_engine.recognize_number(image[height // 2:, int(width * 0.42):])
    if not re.fullmatch(r"\d+", whole_text):
        return None
    numerator_digits = re.findall(r"[12]", numerator_text)
    denominator_digits = re.findall(r"\d", denominator_text)
    if not numerator_digits or not denominator_digits or denominator_digits[-1] != "3":
        return None
    return int(whole_text), int(numerator_digits[-1])


def parse_pitcher_decision(raw: str) -> dict[str, int]:
    """Map the small result marker beside a pitcher name to GameJSON flags."""
    normalized = raw.upper().replace(" ", "")
    return {
        "wins": int("勝" in normalized),
        "losses": int("敗" in normalized),
        "holds": int("H" in normalized),
        "saves": int("S" in normalized),
    }


def recognize_pitcher_decision(image: Any, ocr_engine: OcrEngine) -> tuple[str, dict[str, int]]:
    raw = ocr_engine.recognize_text(image).strip()
    return raw, parse_pitcher_decision(raw)


def extract_pitcher_rows(image: Any, layout: BatterScreenLayout | None = None) -> list[PlayerRowImage]:
    return extract_player_rows(
        image,
        layout or load_pitcher_layout(),
        align_layout=align_pitcher_layout,
        exclude_red_pitcher=False,
    )


def parse_pitcher_screen(
    image: Any,
    candidate_names: tuple[str, ...],
    ocr_engine: OcrEngine,
    layout: BatterScreenLayout | None = None,
    aliases: Mapping[str, str] | None = None,
) -> tuple[list[RecognizedPitcher], list[PlayerRowImage]]:
    """Read one pitcher screen; ERA is intentionally absent from the layout."""
    rows = extract_pitcher_rows(image, layout)
    recognized: list[RecognizedPitcher] = []
    number_fields = tuple(name for name in PITCHER_OCR_FIELDS if name not in ("innings", "inning_fraction"))
    for row in rows:
        ocr_name = ocr_engine.recognize_text(row.cells["name"])
        match = match_player_name(ocr_name, candidate_names, aliases)
        innings = recognize_innings(row.cells["innings"], ocr_engine)
        decision_text, decisions = recognize_pitcher_decision(row.cells["decision"], ocr_engine)
        values: dict[str, int | None] = {
            field_name: recognize_stat_number(row.cells[field_name], ocr_engine)
            for field_name in number_fields
        }
        values["innings"], values["inning_fraction"] = innings if innings is not None else (None, None)
        recognized.append(RecognizedPitcher(
            ocr_name=ocr_name,
            matched_name=match.matched_name,
            match_score=match.score,
            match_source=match.match_source,
            second_name=match.second_name,
            second_score=match.second_score,
            requires_review=match.requires_review,
            source_row_index=row.row_index,
            ocr_stats={**values, **decisions},
            ocr_decision=decision_text,
            **decisions,
            **values,
        ))
    for index, pitcher in enumerate(recognized):
        pitcher.refresh_automatic_fields(
            is_starting_pitcher=index == 0,
            only_pitcher=len(recognized) == 1,
        )
    return recognized, rows


def merge_pitcher_screens(
    images: list[Any],
    candidate_names: tuple[str, ...],
    ocr_engine: OcrEngine,
    layout: BatterScreenLayout | None = None,
    aliases: Mapping[str, str] | None = None,
) -> tuple[list[RecognizedPitcher], list[PlayerRowImage]]:
    """Parse one or two pitcher captures while removing their overlap.

    A pitcher list can be scrolled just like the batting list.  Retain the
    first appearance of a formal NameList match and give each retained preview
    row a unique index, so selecting a review row always shows its own source
    crop.  Empty OCR names intentionally remain separate review errors.
    """
    merged_records: list[RecognizedPitcher] = []
    merged_rows: list[PlayerRowImage] = []
    seen_keys: set[tuple[str, str]] = set()
    for image in images:
        records, rows = parse_pitcher_screen(image, candidate_names, ocr_engine, layout, aliases)
        for record, row in zip(records, rows):
            if record.matched_name:
                key: tuple[str, str] | None = ("name", record.matched_name)
            else:
                normalized_ocr = re.sub(r"\s+", "", record.ocr_name)
                key = ("ocr", normalized_ocr) if normalized_ocr else None
            if key is not None and key in seen_keys:
                continue
            if key is not None:
                seen_keys.add(key)
            row.row_index = len(merged_rows)
            record.source_row_index = row.row_index
            merged_rows.append(row)
            merged_records.append(record)
    # When two scrolling screenshots are merged, only the actual top pitcher
    # is the starter.  Reapply the initial flag after de-duplication.
    for index, pitcher in enumerate(merged_records):
        pitcher.refresh_automatic_fields(
            is_starting_pitcher=index == 0,
            only_pitcher=len(merged_records) == 1,
        )
    return merged_records, merged_rows
