"""Image normalization and OCR-specific preprocessing."""

from __future__ import annotations

from typing import Any


BASE_SCREEN_SIZE = (1920, 1080)


def _cv2() -> Any:
    try:
        import cv2
    except ImportError as error:
        raise RuntimeError("OpenCVがありません。`python -m pip install -r requirements.txt` を実行してください") from error
    return cv2


def _edge_bar_width(dark: Any, *, from_left: bool) -> int:
    """Return the width of a near-black side bar, if one occupies the edge."""
    import numpy as np

    # Window title bars and taskbars can overlap the side-bar columns.  A real
    # letterbox bar still remains dark for the overwhelming majority of rows.
    dark_columns = dark.mean(axis=0) >= 0.75
    ordered = dark_columns if from_left else dark_columns[::-1]
    non_dark = np.flatnonzero(~ordered)
    return int(non_dark[0]) if non_dark.size else len(ordered)


def _crop_letterboxed_game_viewport(image: Any) -> Any:
    """Remove desktop/window chrome around a 16:9 PowerPro render when found.

    OBS/window captures can have a title bar and taskbar but retain black bars
    to the left and right of the game.  Scaling the *whole* capture changes the
    table's aspect ratio and invalidates every calibrated cell coordinate.  We
    only crop when matching bars provide strong evidence of a centered 16:9
    game viewport; ordinary screenshots and manual table crops remain intact.
    """
    try:
        import numpy as np
    except ImportError:
        return image
    cv2 = _cv2()
    if image is None or not hasattr(image, "shape") or len(image.shape) < 2:
        return image
    height, width = image.shape[:2]
    if len(image.shape) == 2:
        gray = image
    elif image.shape[2] == 4:
        gray = cv2.cvtColor(image, cv2.COLOR_BGRA2GRAY)
    else:
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    dark = gray < 16
    left_bar = _edge_bar_width(dark, from_left=True)
    right_bar = _edge_bar_width(dark, from_left=False)
    minimum_bar = max(12, round(width * 0.015))
    if left_bar < minimum_bar or right_bar < minimum_bar:
        return image

    viewport_width = width - left_bar - right_bar
    viewport_height = round(viewport_width * 9 / 16)
    if viewport_width <= 0 or viewport_height <= 0 or viewport_height > height:
        return image

    # Locate the vertical interval where both side bars are present.  This
    # distinguishes the game viewport from the desktop chrome above/below it.
    left_dark = dark[:, :left_bar].mean(axis=1) >= 0.75
    right_dark = dark[:, width - right_bar:].mean(axis=1) >= 0.75
    side_bar_rows = left_dark & right_dark
    groups: list[tuple[int, int]] = []
    for row in np.flatnonzero(side_bar_rows).tolist():
        if not groups or row > groups[-1][1] + 1:
            groups.append((row, row))
        else:
            groups[-1] = (groups[-1][0], row)
    candidates = [group for group in groups if group[1] - group[0] + 1 >= viewport_height]
    if not candidates:
        return image
    top, bottom = max(candidates, key=lambda group: group[1] - group[0])
    # Anchor at the top of the black-bar run.  In the supplied window captures
    # this is immediately below the title bar; centering would accidentally
    # include taskbar pixels when the run is a couple of pixels taller.
    del bottom
    return image[top:top + viewport_height, left_bar:width - right_bar]


def normalize_screen(image: Any) -> Any:
    """Normalize a game viewport to the parser's 1920x1080 coordinate space."""
    if image is None or not hasattr(image, "shape") or len(image.shape) < 2:
        raise ValueError("有効な画像を指定してください")
    cv2 = _cv2()
    # A native game screenshot can itself contain the game's pillarbox bars.
    # Its complete black top/bottom frame distinguishes it from a desktop
    # capture with a title bar and taskbar.  It is already in parser space, so
    # treating its bars as window chrome would crop and distort it.
    if (image.shape[1], image.shape[0]) == BASE_SCREEN_SIZE:
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY) if len(image.shape) == 3 else image
        edge_height = max(1, round(image.shape[0] * 0.02))
        if (gray[:edge_height] < 16).mean() >= 0.95 and (gray[-edge_height:] < 16).mean() >= 0.95:
            return image.copy()
    image = _crop_letterboxed_game_viewport(image)
    source_height, source_width = image.shape[:2]
    if (source_width, source_height) == BASE_SCREEN_SIZE:
        return image.copy()
    interpolation = cv2.INTER_AREA if source_width > BASE_SCREEN_SIZE[0] else cv2.INTER_CUBIC
    return cv2.resize(image, BASE_SCREEN_SIZE, interpolation=interpolation)


def preprocess_name_cell(image: Any) -> Any:
    """Upscale and binarize a name cell while preserving Japanese glyph detail."""
    cv2 = _cv2()
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY) if len(image.shape) == 3 else image
    enlarged = cv2.resize(gray, None, fx=3, fy=3, interpolation=cv2.INTER_CUBIC)
    return cv2.threshold(enlarged, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)[1]


def preprocess_number_cell(image: Any) -> Any:
    """Prepare a numeric cell separately from text OCR."""
    cv2 = _cv2()
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY) if len(image.shape) == 3 else image
    enlarged = cv2.resize(gray, None, fx=4, fy=4, interpolation=cv2.INTER_CUBIC)
    return cv2.threshold(enlarged, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)[1]
