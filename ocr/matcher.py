"""Conservative NameList-scoped player-name matching."""

from __future__ import annotations

from dataclasses import dataclass
from difflib import SequenceMatcher
from typing import Iterable, Literal, Mapping


NAME_MATCH_AUTO_THRESHOLD = 85.0
NAME_MATCH_MARGIN_THRESHOLD = 10.0


@dataclass(frozen=True, slots=True)
class NameMatchResult:
    ocr_text: str
    matched_name: str | None
    score: float
    second_name: str | None
    second_score: float | None
    match_source: Literal["alias", "exact", "fuzzy", "unresolved"] = "unresolved"

    @property
    def requires_review(self) -> bool:
        if self.match_source == "alias":
            return False
        return self.matched_name is None or self.score < NAME_MATCH_AUTO_THRESHOLD or (
            self.second_score is not None and self.score - self.second_score < NAME_MATCH_MARGIN_THRESHOLD
        )


def _score(query: str, choice: str) -> float:
    try:
        from rapidfuzz.fuzz import ratio
    except ImportError:
        # Keeping this fallback makes model/unit tests usable before optional
        # dependencies are installed; production uses RapidFuzz.
        return SequenceMatcher(None, query, choice).ratio() * 100
    return float(ratio(query, choice))


def _normalize_for_comparison(value: str) -> str:
    """Normalize only common OCR punctuation variants, not player name content."""
    return "".join(value.split()).translate(str.maketrans({
        ".": "・",
        "·": "・",
        "・": "・",
        "-": "ー",
        "−": "ー",
        "―": "ー",
    }))


def match_player_name(
    ocr_text: str,
    candidate_names: Iterable[str],
    aliases: Mapping[str, str] | None = None,
) -> NameMatchResult:
    """Resolve aliases exactly, then rank only official NameList candidates."""
    normalized = _normalize_for_comparison(ocr_text)
    candidates = tuple(candidate_names)
    if not normalized:
        return NameMatchResult(ocr_text, None, 0.0, None, None, "unresolved")

    # Alias matching deliberately compares complete normalized strings only.
    # Aliases are never fuzzy candidates and never act as prefixes.
    for alias, official_name in (aliases or {}).items():
        if normalized == _normalize_for_comparison(alias):
            return NameMatchResult(ocr_text, official_name, 100.0, None, None, "alias")

    if not candidates:
        return NameMatchResult(ocr_text, None, 0.0, None, None, "unresolved")

    exact_names = tuple(name for name in candidates if normalized == _normalize_for_comparison(name))
    if exact_names:
        name = exact_names[0]
        remaining = tuple(candidate for candidate in candidates if candidate != name)
        ranked_remaining = sorted(
            ((_score(normalized, _normalize_for_comparison(candidate)), candidate) for candidate in remaining),
            key=lambda item: (-item[0], item[1]),
        )
        second_score, second_name = ranked_remaining[0] if ranked_remaining else (None, None)
        return NameMatchResult(ocr_text, name, 100.0, second_name, second_score, "exact")

    ranked = sorted(
        ((_score(normalized, _normalize_for_comparison(name)), name) for name in candidates),
        key=lambda item: (-item[0], item[1]),
    )
    score, name = ranked[0]
    second_score, second_name = (ranked[1] if len(ranked) > 1 else (None, None))
    return NameMatchResult(ocr_text, name, score, second_name, second_score, "fuzzy")
