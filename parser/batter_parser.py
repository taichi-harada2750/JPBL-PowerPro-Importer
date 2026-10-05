"""Batter-screen extraction and OCR-to-review-model conversion."""

from __future__ import annotations

import re
from dataclasses import dataclass
from collections.abc import Callable
from typing import Any, Mapping

from app.models import BATTER_STAT_FIELDS, RecognizedBatter
from ocr.engine import OcrEngine
from ocr.matcher import match_player_name
from ocr.preprocess import normalize_screen
from parser.screen_regions import BatterScreenLayout, Region, align_batter_layout, load_batter_layout


@dataclass(slots=True)
class PlayerRowImage:
    row_index: int
    row_region: Region
    image: Any
    preview_image: Any
    cells: dict[str, Any]


def _is_red_pitcher_row(name_cell: Any, cv2: Any) -> bool:
    """Return whether PowerPro marks this lineup row as the red pitcher row."""
    if name_cell is None or name_cell.size == 0 or len(name_cell.shape) != 3:
        return False
    interior = name_cell[6:-6, 6:-6] if name_cell.shape[0] > 12 and name_cell.shape[1] > 12 else name_cell
    hsv = cv2.cvtColor(interior, cv2.COLOR_BGR2HSV)
    hue, saturation, value = hsv[:, :, 0], hsv[:, :, 1], hsv[:, :, 2]
    red = ((hue < 10) | (hue > 170)) & (saturation > 70) & (value > 100)
    # Text and the plate outline are allowed to occupy a small area; the red
    # pitcher plate itself covers nearly the whole cell in supplied captures.
    return float(red.mean()) >= 0.55


def _cv2() -> Any:
    try:
        import cv2
    except ImportError as error:
        raise RuntimeError("OpenCVがありません。`python -m pip install -r requirements.txt` を実行してください") from error
    return cv2


def extract_player_rows(
    image: Any,
    layout: BatterScreenLayout | None = None,
    *,
    align_layout: Callable[[Any, BatterScreenLayout], BatterScreenLayout] = align_batter_layout,
    exclude_red_pitcher: bool = True,
) -> list[PlayerRowImage]:
    """Extract occupied rows by normalized geometry plus table-grid alignment.

    Geometry is deliberately isolated here so later line/background detection can
    replace it without changing OCR, matching, or GUI code.
    """
    layout = layout or load_batter_layout()
    cv2 = _cv2()
    normalized = normalize_screen(image)
    layout = align_layout(normalized, layout)
    name_column = layout.columns["name"]
    rows: list[PlayerRowImage] = []
    row_geometry = layout.row_bounds or tuple(
        (layout.first_row_y + index * layout.row_stride, layout.row_height)
        for index in range(layout.max_rows)
    )
    table_left = max(0, min(region.x for region in layout.columns.values()) - 4)
    table_right = min(
        normalized.shape[1],
        max(region.x + region.width for region in layout.columns.values()) + 4,
    )
    # Keep the header visible for every selected row.  Joining it directly to
    # the selected row avoids making lower-line previews unnecessarily tall.
    header_top = max(0, row_geometry[0][0] - max(layout.row_stride * 2, layout.row_height * 3))
    header_image = normalized[header_top:row_geometry[0][0], table_left:table_right]
    found_occupied_row = False
    for index, (y, row_height) in enumerate(row_geometry):
        if y + row_height > normalized.shape[0]:
            break
        name_cell = normalized[y:y + row_height, name_column.x:name_column.x + name_column.width]
        gray = cv2.cvtColor(name_cell, cv2.COLOR_BGR2GRAY) if len(name_cell.shape) == 3 else name_cell
        # Text pixels are normally much darker than the bright table background.
        # Ignore the cell borders, which would otherwise make empty grid rows
        # appear occupied.
        content = gray[4:-4, 4:-4] if gray.shape[0] > 8 and gray.shape[1] > 8 else gray
        ink_ratio = float((content < 120).mean())
        if ink_ratio < layout.row_ink_threshold:
            # Player entries are contiguous.  Once the first blank name cell
            # is reached, later table borders/background artwork must not be
            # treated as a far-away player row.
            if found_occupied_row:
                break
            continue
        # This is the pitcher shown beneath a batting order.  Filter it before
        # OCR only for batter parsing; every pitcher-row plate is valid here.
        if exclude_red_pitcher and _is_red_pitcher_row(name_cell, cv2):
            continue
        cells = {
            name: normalized[y:y + row_height, region.x:region.x + region.width]
            for name, region in layout.columns.items()
        }
        row_image = normalized[y:y + row_height, table_left:table_right]
        preview_image = cv2.vconcat((header_image, row_image)) if header_image.size else row_image
        rows.append(PlayerRowImage(
            index,
            Region(table_left, y, table_right - table_left, row_height),
            row_image,
            preview_image,
            cells,
        ))
        found_occupied_row = True
    return rows


def recognize_stat_number(image: Any, ocr_engine: OcrEngine) -> int | None:
    """Map blank cells to 0, valid digits to int, and ambiguous OCR to None."""
    if _is_visually_blank_stat_cell(image):
        return 0
    raw = ocr_engine.recognize_number(image).strip()
    if raw == "":
        return 0
    if re.fullmatch(r"\d+", raw):
        return int(raw)
    return None


def _is_visually_blank_stat_cell(image: Any) -> bool:
    """Recognize PowerPro's empty light-blue stat cells before OCR.

    Borders can be interpreted as punctuation by OCR.  Inspect only the cell
    interior so an empty cell becomes the specified zero, while a genuinely
    ambiguous digit remains ``None`` for human review.
    """
    if image is None or not hasattr(image, "shape") or len(image.shape) < 2:
        return False
    height, width = image.shape[:2]
    if height < 12 or width < 12:
        return False
    cv2 = _cv2()
    vertical_margin = max(4, round(height * 0.12))
    horizontal_margin = max(4, round(width * 0.12))
    interior = image[vertical_margin:height - vertical_margin, horizontal_margin:width - horizontal_margin]
    if interior.size == 0:
        return False
    gray = cv2.cvtColor(interior, cv2.COLOR_BGR2GRAY) if len(interior.shape) == 3 else interior
    # Supplied screens use a very light blue blank background (around 250 in
    # grayscale); the dark-blue score glyphs have a substantial <170 area.
    return float((gray < 170).mean()) < 0.004


def parse_batter_screen(
    image: Any,
    candidate_names: tuple[str, ...],
    ocr_engine: OcrEngine,
    layout: BatterScreenLayout | None = None,
    aliases: Mapping[str, str] | None = None,
) -> tuple[list[RecognizedBatter], list[PlayerRowImage]]:
    """Return review records and their source-row crops for the GUI preview."""
    rows = extract_player_rows(image, layout)
    recognized: list[RecognizedBatter] = []
    for row in rows:
        ocr_name = ocr_engine.recognize_text(row.cells["name"])
        match = match_player_name(ocr_name, candidate_names, aliases)
        # The calibrated PowerPro screen currently has no 犠飛 column.  Its
        # GameJSON v1 default is explicitly 0, so set that documented default
        # rather than treating a non-visible column as an OCR failure.
        values = {
            field_name: (
                recognize_stat_number(row.cells[field_name], ocr_engine)
                if field_name in row.cells else 0
            )
            for field_name in BATTER_STAT_FIELDS
        }
        recognized.append(RecognizedBatter(
            ocr_name=ocr_name,
            matched_name=match.matched_name,
            match_score=match.score,
            match_source=match.match_source,
            second_name=match.second_name,
            second_score=match.second_score,
            requires_review=match.requires_review,
            source_row_index=row.row_index,
            ocr_stats=values.copy(),
            **values,
        ))
    return recognized, rows


def merge_batter_screens(
    images: list[Any],
    candidate_names: tuple[str, ...],
    ocr_engine: OcrEngine,
    layout: BatterScreenLayout | None = None,
    aliases: Mapping[str, str] | None = None,
) -> tuple[list[RecognizedBatter], list[PlayerRowImage]]:
    """Parse one or two scrolled screenshots as a single batting lineup.

    Consecutive captures overlap at the scroll boundary.  A formal NameList
    match is the stable deduplication key; otherwise normalized OCR text is
    used.  Empty OCR output is deliberately never deduplicated, so separate
    recognition failures remain visible for manual review.
    """
    merged_records: list[RecognizedBatter] = []
    merged_rows: list[PlayerRowImage] = []
    seen_keys: set[tuple[str, str]] = set()
    for image in images:
        records, rows = parse_batter_screen(image, candidate_names, ocr_engine, layout, aliases)
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
    return merged_records, merged_rows
