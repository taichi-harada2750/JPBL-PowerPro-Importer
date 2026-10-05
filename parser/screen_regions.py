"""All 1920x1080 batter-screen coordinates live in one calibratable module."""

from __future__ import annotations

import json
import statistics
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True, slots=True)
class Region:
    x: int
    y: int
    width: int
    height: int

    def crop(self, image: Any) -> Any:
        return image[self.y:self.y + self.height, self.x:self.x + self.width]


@dataclass(frozen=True, slots=True)
class BatterScreenLayout:
    columns: dict[str, Region]
    first_row_y: int
    row_height: int
    row_stride: int
    max_rows: int
    row_ink_threshold: float
    row_bounds: tuple[tuple[int, int], ...] = ()


_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_LAYOUT_PATH = _ROOT / "config" / "batter_screen_regions.json"
DEFAULT_PITCHER_LAYOUT_PATH = _ROOT / "config" / "pitcher_screen_regions.json"


def _load_layout(path: str | Path) -> BatterScreenLayout:
    """Load the only coordinate source; no parser may embed screen coordinates."""
    try:
        raw = json.loads(Path(path).read_text(encoding="utf-8"))
        columns = {
            name: Region(**values)
            for name, values in raw["columns"].items()
        }
        return BatterScreenLayout(
            columns=columns,
            first_row_y=raw["rows"]["firstRowY"],
            row_height=raw["rows"]["rowHeight"],
            row_stride=raw["rows"].get("rowStride", raw["rows"]["rowHeight"]),
            max_rows=raw["rows"]["maxRows"],
            row_ink_threshold=float(raw["rows"].get("rowInkThreshold", 0.012)),
        )
    except (OSError, KeyError, TypeError, json.JSONDecodeError) as error:
        raise ValueError(f"野手画面座標設定を読み込めません: {path}") from error


def load_batter_layout(path: str | Path = DEFAULT_LAYOUT_PATH) -> BatterScreenLayout:
    """Load batter coordinates from the central configuration file."""
    return _load_layout(path)


def load_pitcher_layout(path: str | Path = DEFAULT_PITCHER_LAYOUT_PATH) -> BatterScreenLayout:
    """Load pitcher coordinates using the same layout contract as batters."""
    try:
        return _load_layout(path)
    except ValueError as error:
        raise ValueError(f"投手画面座標設定を読み込めません: {path}") from error


BATTER_COLUMNS = load_batter_layout().columns


def _contiguous_groups(indices: Any, max_gap: int = 1) -> list[tuple[int, int]]:
    """Convert a sorted one-dimensional index array into inclusive ranges.

    A table separator can be interrupted by a couple of non-white pixels due
    to antialiasing/compression.  Callers detecting vertical grid lines may
    therefore allow a small gap without treating one physical separator as
    two distinct columns.
    """
    groups: list[tuple[int, int]] = []
    for index in indices.tolist():
        if not groups or index > groups[-1][1] + max_gap:
            groups.append((index, index))
        else:
            groups[-1] = (groups[-1][0], index)
    return groups


def _closest_group(groups: list[tuple[int, int]], target: int, tolerance: int) -> tuple[int, int] | None:
    if not groups:
        return None
    candidate = min(groups, key=lambda group: min(abs(group[0] - target), abs(group[1] - target)))
    return candidate if min(abs(candidate[0] - target), abs(candidate[1] - target)) <= tolerance else None


def _group_centers(groups: list[tuple[int, int]]) -> list[float]:
    return [(start + end) / 2 for start, end in groups]


def _longest_regular_run(
    groups: list[tuple[int, int]],
    minimum_gap: float,
    maximum_gap: float,
    relative_tolerance: float = 0.28,
) -> list[tuple[int, int]]:
    """Find the longest sequence of near-equidistant grid separators."""
    centers = _group_centers(groups)
    best: list[tuple[int, int]] = []
    for start_index in range(len(groups) - 1):
        run = [groups[start_index]]
        baseline: float | None = None
        for index in range(start_index + 1, len(groups)):
            gap = centers[index] - centers[index - 1]
            if baseline is None:
                if not minimum_gap <= gap <= maximum_gap:
                    break
                baseline = gap
            elif not baseline * (1 - relative_tolerance) <= gap <= baseline * (1 + relative_tolerance):
                break
            run.append(groups[index])
        if len(run) > len(best):
            best = run
    return best


def _auto_align_batter_table(image: Any, layout: BatterScreenLayout) -> BatterScreenLayout | None:
    """Locate the table from its repeated grid, independent of screenshot edges.

    This works when desktop capture includes a taskbar/black bars or when a user
    manually crops away the decorative PowerPro background.  It intentionally
    needs the actual table, not any fixed screen corner or title artwork.
    """
    try:
        import numpy as np
    except ImportError:
        return None
    if image is None or len(image.shape) != 3:
        return None
    height, width = image.shape[:2]
    white = np.all(image > 235, axis=2)
    # A 25% full-image support threshold excludes decorative background lines
    # while retaining every separator in both full-screen and cropped captures.
    # Some captures split a single bright vertical separator by 1-3 pixels.
    # Merge those fragments before looking for the regular stats-column grid.
    vertical_groups = _contiguous_groups(np.flatnonzero(white.mean(axis=0) > 0.25), max_gap=4)
    stat_separators = _longest_regular_run(vertical_groups, width * 0.025, width * 0.10)
    stat_names = [name for name in layout.columns if name != "name"]
    if len(stat_separators) < len(stat_names) + 1:
        return None
    stat_separators = stat_separators[:len(stat_names) + 1]
    first_separator = stat_separators[0]
    name_separator_candidates = [group for group in vertical_groups if group[1] < first_separator[0]]
    if not name_separator_candidates:
        return None
    name_left = name_separator_candidates[-1]
    columns: dict[str, Region] = {
        "name": Region(
            name_left[1] + 1,
            0,
            first_separator[0] - name_left[1] - 1,
            layout.columns["name"].height,
        )
    }
    for index, name in enumerate(stat_names):
        left, right = stat_separators[index], stat_separators[index + 1]
        columns[name] = Region(
            left[1] + 1,
            0,
            right[0] - left[1] - 1,
            layout.columns[name].height,
        )

    x_start = stat_separators[0][1] + 1
    x_end = stat_separators[-1][0]
    if x_end <= x_start:
        return None
    horizontal_groups = _contiguous_groups(np.flatnonzero(white[:, x_start:x_end].mean(axis=1) > 0.75))
    row_separators = _longest_regular_run(horizontal_groups, height * 0.035, height * 0.11)
    if len(row_separators) < 3:
        return None
    row_bounds = tuple(
        (left[1] + 1, right[0] - left[1] - 1)
        for left, right in zip(row_separators, row_separators[1:])
        if right[0] - left[1] - 1 > 8
    )[:layout.max_rows]
    if not row_bounds:
        return None
    strides = [right[0] - left[0] for left, right in zip(row_bounds, row_bounds[1:])]
    row_height = int(round(statistics.median(row_height for _start, row_height in row_bounds)))
    row_stride = int(round(statistics.median(strides))) if strides else layout.row_stride
    return BatterScreenLayout(
        columns=columns,
        first_row_y=row_bounds[0][0],
        row_height=row_height,
        row_stride=row_stride,
        max_rows=layout.max_rows,
        row_ink_threshold=layout.row_ink_threshold,
        row_bounds=row_bounds,
    )


def align_batter_layout(image: Any, layout: BatterScreenLayout) -> BatterScreenLayout:
    """Refine configured regions from bright PowerPro table-grid separators.

    Fixed coordinates remain the safe fallback.  When a capture is shifted a few
    pixels after normalization, the long horizontal/vertical white separator
    lines re-anchor the cells without scattering layout logic into the parser.
    """
    automatic = _auto_align_batter_table(image, layout)
    if automatic is not None:
        return automatic
    try:
        import numpy as np
    except ImportError:
        return layout
    if image is None or len(image.shape) < 2:
        return layout
    height, width = image.shape[:2]
    if len(image.shape) != 3:
        return layout
    white = np.all(image > 235, axis=2)
    y_start = max(0, layout.first_row_y - layout.row_height)
    y_end = min(height, layout.first_row_y + layout.max_rows * layout.row_stride + layout.row_height)
    vertical_groups = _contiguous_groups(
        np.flatnonzero(white[y_start:y_end].mean(axis=0) > 0.60), max_gap=4
    )
    if len(vertical_groups) < 8:
        return layout

    columns: dict[str, Region] = {}
    for name, region in layout.columns.items():
        left = _closest_group(vertical_groups, region.x - 3, 56)
        right = _closest_group(vertical_groups, region.x + region.width, 56)
        if left is None or right is None or left[1] >= right[0] - 1:
            columns[name] = region
            continue
        columns[name] = Region(left[1] + 1, region.y, right[0] - left[1] - 1, region.height)

    stats_columns = [region for name, region in columns.items() if name not in ("name", "decision")]
    if not stats_columns:
        return layout
    x_start = max(0, min(region.x for region in stats_columns))
    x_end = min(width, max(region.x + region.width for region in stats_columns))
    horizontal_groups = _contiguous_groups(np.flatnonzero(white[:, x_start:x_end].mean(axis=1) > 0.80))
    row_starts = [end + 1 for _start, end in horizontal_groups]
    predicted_starts = [layout.first_row_y + index * layout.row_stride for index in range(layout.max_rows)]
    matched_starts = [
        candidate for expected in predicted_starts
        if (candidate := min(row_starts, key=lambda start: abs(start - expected), default=None)) is not None
        and abs(candidate - expected) <= 12
    ]
    if not matched_starts:
        return BatterScreenLayout(
            columns, layout.first_row_y, layout.row_height, layout.row_stride,
            layout.max_rows, layout.row_ink_threshold, layout.row_bounds,
        )

    first_row_y = matched_starts[0]
    stride = int(round(statistics.median(
        right - left for left, right in zip(matched_starts, matched_starts[1:])
    ))) if len(matched_starts) > 1 else layout.row_stride
    row_heights = []
    for start in matched_starts:
        next_separator = next((group_start for group_start, _group_end in horizontal_groups if group_start > start), None)
        if next_separator is not None:
            row_heights.append(next_separator - start)
    candidate_row_height = int(round(statistics.median(row_heights))) if row_heights else layout.row_height
    # Header glyphs and antialiased grid edges can form tiny bright horizontal
    # groups.  They are not player-row separators; accepting them here would
    # collapse a 56px row to 1-2px and make every valid row look empty.
    row_height = candidate_row_height if layout.row_height * 0.55 <= candidate_row_height <= layout.row_height * 1.50 else layout.row_height
    return BatterScreenLayout(
        columns, first_row_y, row_height, stride, layout.max_rows,
        layout.row_ink_threshold, layout.row_bounds,
    )


def align_pitcher_layout(image: Any, layout: BatterScreenLayout) -> BatterScreenLayout:
    """Align pitcher columns to nearby grid lines without using ERA as data.

    Pitcher columns have intentionally uneven widths, so the batter-specific
    equal-spacing detector is not applicable.  The shared configured geometry
    remains the anchor and is refined by bright separator lines when present.
    """
    try:
        import numpy as np
    except ImportError:
        return layout
    if image is None or len(image.shape) != 3:
        return layout
    height, width = image.shape[:2]
    white = np.all(image > 235, axis=2)
    y_start = max(0, layout.first_row_y - layout.row_height)
    y_end = min(height, layout.first_row_y + layout.max_rows * layout.row_stride + layout.row_height)
    vertical_groups = _contiguous_groups(
        np.flatnonzero(white[y_start:y_end].mean(axis=0) > 0.60), max_gap=4
    )
    if len(vertical_groups) < 4:
        return layout
    columns: dict[str, Region] = {}
    for name, region in layout.columns.items():
        left = _closest_group(vertical_groups, region.x - 3, 56)
        right = _closest_group(vertical_groups, region.x + region.width, 56)
        if left is None or right is None or left[1] >= right[0] - 1:
            columns[name] = region
            continue
        columns[name] = Region(left[1] + 1, region.y, right[0] - left[1] - 1, region.height)

    stats_columns = [region for name, region in columns.items() if name != "name"]
    if not stats_columns:
        return BatterScreenLayout(columns, layout.first_row_y, layout.row_height, layout.row_stride,
                                  layout.max_rows, layout.row_ink_threshold, layout.row_bounds)
    x_start = max(0, min(region.x for region in stats_columns))
    x_end = min(width, max(region.x + region.width for region in stats_columns))
    horizontal_groups = _contiguous_groups(np.flatnonzero(white[:, x_start:x_end].mean(axis=1) > 0.80))
    row_bounds = tuple(
        (left[1] + 1, right[0] - left[1] - 1)
        for left, right in zip(horizontal_groups, horizontal_groups[1:])
        if layout.first_row_y - 12 <= left[1] + 1 and right[0] - left[1] - 1 > 8
    )[:layout.max_rows]
    if row_bounds:
        return BatterScreenLayout(
            columns, row_bounds[0][0], int(round(statistics.median(height for _y, height in row_bounds))),
            layout.row_stride, layout.max_rows, layout.row_ink_threshold, row_bounds,
        )
    return BatterScreenLayout(columns, layout.first_row_y, layout.row_height, layout.row_stride,
                              layout.max_rows, layout.row_ink_threshold, layout.row_bounds)
