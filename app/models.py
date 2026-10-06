"""Internal, OCR-independent game data models.

These models deliberately use English field names.  Conversion to the exact
Japanese keys required by the existing GAS happens only in gamejson_exporter.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal


Position = Literal["野手", "投手"]


@dataclass(slots=True)
class RecognitionInfo:
    """Recognition and matching metadata that must never leave as GameJSON."""

    ocr_text: str = ""
    matched_name: str | None = None
    confidence: float = 0.0
    manually_corrected: bool = False
    manually_added_name: bool = False
    second_candidate: str | None = None
    second_candidate_score: float | None = None
    match_source: str = "unresolved"


@dataclass(slots=True)
class BatterStats:
    games: int = 1
    at_bats: int = 0
    runs: int = 0
    hits: int = 0
    doubles: int = 0
    triples: int = 0
    home_runs: int = 0
    rbi: int = 0
    strikeouts: int = 0
    walks_hbp: int = 0
    sacrifices: int = 0
    steals: int = 0
    double_plays: int = 0
    errors: int = 0
    sac_flies: int = 0


@dataclass(slots=True)
class PitcherStats:
    appearances: int = 1
    starts: int = 0
    wins: int = 0
    losses: int = 0
    holds: int = 0
    saves: int = 0
    innings: int = 0
    inning_fraction: int = 0
    pitches: int = 0
    batters_faced: int = 0
    hits_allowed: int = 0
    strikeouts: int = 0
    walks_hbp: int = 0
    runs: int = 0
    earned_runs: int = 0
    wild_pitches: int = 0
    home_runs_allowed: int = 0
    # ``None`` means that an internal caller did not supply a reviewed value;
    # the exporter retains the legacy fallback calculation in that case.
    qs: int | None = None
    hqs: int | None = None
    complete_games: int = 0
    shutouts: int = 0
    no_walk_games: int = 0
    intentional_walks: int = 0


@dataclass(slots=True)
class PlayerRecord:
    """A player record awaiting review and eventual GameJSON export."""

    team: str
    position: Position
    recognition: RecognitionInfo
    stats: BatterStats | PitcherStats
    remarks: str = ""

    @property
    def name(self) -> str | None:
        return self.recognition.matched_name


@dataclass(slots=True)
class InternalGame:
    """Working game state; it can retain OCR data without exposing it."""

    game_id: str
    game_date: str
    away_team: str
    home_team: str
    players: list[PlayerRecord] = field(default_factory=list)


BATTER_STAT_FIELDS = (
    "at_bats",
    "runs",
    "hits",
    "doubles",
    "triples",
    "home_runs",
    "rbi",
    "strikeouts",
    "walks_hbp",
    "sacrifices",
    "steals",
    "double_plays",
    "errors",
    "sac_flies",
)

BATTER_STAT_LABELS = {
    "at_bats": "打数", "runs": "得点", "hits": "安打", "doubles": "二塁打",
    "triples": "三塁打", "home_runs": "本塁打", "rbi": "打点", "strikeouts": "三振",
    "walks_hbp": "四死球", "sacrifices": "犠打", "steals": "盗塁",
    "double_plays": "併殺", "errors": "失策", "sac_flies": "犠飛",
}

PITCHER_OCR_FIELDS = (
    "innings", "inning_fraction", "pitches", "batters_faced", "hits_allowed",
    "strikeouts", "walks_hbp", "runs", "earned_runs", "wild_pitches",
    "home_runs_allowed",
)
PITCHER_MANUAL_BINARY_FIELDS = (
    "qs", "hqs", "starts", "wins", "losses", "holds", "saves", "complete_games", "shutouts", "no_walk_games",
)
PITCHER_MANUAL_INTEGER_FIELDS = ("intentional_walks",)
PITCHER_STAT_LABELS = {
    "innings": "投球回", "inning_fraction": "投球回分数", "pitches": "球数",
    "batters_faced": "打者", "hits_allowed": "被安打", "strikeouts": "奪三振",
    "walks_hbp": "四死球", "runs": "失点", "earned_runs": "自責点",
    "wild_pitches": "暴投", "home_runs_allowed": "被本塁打", "qs": "QS", "hqs": "HQS", "starts": "先発",
    "wins": "勝利", "losses": "敗戦", "holds": "H", "saves": "S",
    "complete_games": "完投", "shutouts": "完封", "no_walk_games": "無四球",
    "intentional_walks": "敬遠数",
}


@dataclass(slots=True)
class RecognizedBatter:
    """OCR result plus independently editable, reviewable batter values.

    The direct stat attributes are the current user-visible values.  ``ocr_stats``
    retains the original OCR values, so a later correction never destroys OCR
    evaluation data.  ``None`` always means an unresolved recognition failure.
    """

    ocr_name: str = ""
    matched_name: str | None = None
    match_score: float = 0.0
    match_source: str = "unresolved"
    second_name: str | None = None
    second_score: float | None = None
    requires_review: bool = True
    excluded_from_export: bool = False
    manually_corrected_name: bool = False
    manually_added_name: bool = False
    at_bats: int | None = None
    runs: int | None = None
    hits: int | None = None
    doubles: int | None = None
    triples: int | None = None
    home_runs: int | None = None
    rbi: int | None = None
    strikeouts: int | None = None
    walks_hbp: int | None = None
    sacrifices: int | None = None
    steals: int | None = None
    double_plays: int | None = None
    errors: int | None = None
    sac_flies: int | None = None
    ocr_stats: dict[str, int | None] = field(default_factory=dict)
    manually_corrected_stats: set[str] = field(default_factory=set)
    source_row_index: int | None = None
    remarks: str = ""

    def __post_init__(self) -> None:
        for field_name in BATTER_STAT_FIELDS:
            self.ocr_stats.setdefault(field_name, getattr(self, field_name))

    def set_stat(self, field_name: str, value: int | None, *, manual: bool = True) -> None:
        if field_name not in BATTER_STAT_FIELDS:
            raise KeyError(f"Unknown batter stat field: {field_name}")
        if value is not None and (not isinstance(value, int) or isinstance(value, bool) or value < 0):
            raise ValueError("野手成績は0以上の整数、または未確認のNoneである必要があります")
        setattr(self, field_name, value)
        if manual:
            self.manually_corrected_stats.add(field_name)

    @property
    def missing_stat_fields(self) -> tuple[str, ...]:
        return tuple(field_name for field_name in BATTER_STAT_FIELDS if getattr(self, field_name) is None)

    @property
    def status(self) -> Literal["OK", "要確認", "エラー", "除外"]:
        if self.excluded_from_export:
            return "除外"
        if self.matched_name is None or self.missing_stat_fields:
            return "エラー"
        return "要確認" if self.requires_review else "OK"

    @property
    def review_reasons(self) -> tuple[str, ...]:
        """Human-readable reasons shown alongside the review status."""
        if self.excluded_from_export:
            return ("GameJSON出力から手動で除外",)
        reasons: list[str] = []
        if self.matched_name is None:
            reasons.append("正式名が未選択")
        elif self.match_source == "alias":
            reasons.append("Alias一致")
        elif self.requires_review:
            reasons.append(f"名前照合を確認（{self.match_score:.1f}点）")
        if self.manually_added_name and self.matched_name:
            reasons.append("NameList未登録の手動追加選手")
        if self.missing_stat_fields:
            labels = "、".join(BATTER_STAT_LABELS[field_name] for field_name in self.missing_stat_fields)
            reasons.append(f"数値が未入力: {labels}")
        return tuple(reasons)

    @property
    def review_reason_text(self) -> str:
        return " / ".join(self.review_reasons) or "確認済み"

    def to_batter_stats(self) -> BatterStats:
        if self.missing_stat_fields:
            raise ValueError("未確認の野手数値が残っているため成績へ変換できません")
        return BatterStats(
            at_bats=self.at_bats, runs=self.runs, hits=self.hits, doubles=self.doubles,
            triples=self.triples, home_runs=self.home_runs, rbi=self.rbi,
            strikeouts=self.strikeouts, walks_hbp=self.walks_hbp,
            sacrifices=self.sacrifices, steals=self.steals,
            double_plays=self.double_plays, errors=self.errors, sac_flies=self.sac_flies,
        )

    def to_serializable_dict(self) -> dict[str, object]:
        """Return a JSON-ready work-in-progress record, including OCR metadata."""
        return {
            "ocrName": self.ocr_name,
            "matchedName": self.matched_name,
            "matchScore": self.match_score,
            "matchSource": self.match_source,
            "secondName": self.second_name,
            "secondScore": self.second_score,
            "requiresReview": self.requires_review,
            "excludedFromExport": self.excluded_from_export,
            "manuallyCorrectedName": self.manually_corrected_name,
            "manuallyAddedName": self.manually_added_name,
            "stats": {field_name: getattr(self, field_name) for field_name in BATTER_STAT_FIELDS},
            "ocrStats": self.ocr_stats,
            "manuallyCorrectedStats": sorted(self.manually_corrected_stats),
            "sourceRowIndex": self.source_row_index,
            "remarks": self.remarks,
        }


@dataclass(slots=True)
class RecognizedPitcher:
    """Pitcher OCR result plus editable values, mirroring ``RecognizedBatter``."""

    ocr_name: str = ""
    matched_name: str | None = None
    match_score: float = 0.0
    match_source: str = "unresolved"
    second_name: str | None = None
    second_score: float | None = None
    requires_review: bool = True
    excluded_from_export: bool = False
    manually_corrected_name: bool = False
    manually_added_name: bool = False
    innings: int | None = None
    inning_fraction: int | None = None
    pitches: int | None = None
    batters_faced: int | None = None
    hits_allowed: int | None = None
    strikeouts: int | None = None
    walks_hbp: int | None = None
    runs: int | None = None
    earned_runs: int | None = None
    wild_pitches: int | None = None
    home_runs_allowed: int | None = None
    qs: int = 0
    hqs: int = 0
    starts: int = 0
    wins: int = 0
    losses: int = 0
    holds: int = 0
    saves: int = 0
    complete_games: int = 0
    shutouts: int = 0
    no_walk_games: int = 0
    intentional_walks: int = 0
    remarks: str = ""
    ocr_decision: str = ""
    ocr_stats: dict[str, int | None] = field(default_factory=dict)
    manually_corrected_stats: set[str] = field(default_factory=set)
    source_row_index: int | None = None

    def __post_init__(self) -> None:
        for field_name in PITCHER_OCR_FIELDS:
            self.ocr_stats.setdefault(field_name, getattr(self, field_name))

    def set_stat(self, field_name: str, value: int | None, *, manual: bool = True) -> None:
        valid_fields = PITCHER_OCR_FIELDS + PITCHER_MANUAL_BINARY_FIELDS + PITCHER_MANUAL_INTEGER_FIELDS
        if field_name not in valid_fields:
            raise KeyError(f"Unknown pitcher stat field: {field_name}")
        if value is not None and (not isinstance(value, int) or isinstance(value, bool) or value < 0):
            raise ValueError("投手成績は0以上の整数、または未確認のNoneである必要があります")
        if field_name == "inning_fraction" and value is not None and value not in (0, 1, 2):
            raise ValueError("投球回分数は0、1、2のいずれかである必要があります")
        if field_name in PITCHER_MANUAL_BINARY_FIELDS and value not in (0, 1):
            raise ValueError(f"{PITCHER_STAT_LABELS[field_name]}は0または1である必要があります")
        setattr(self, field_name, value)
        if manual:
            self.manually_corrected_stats.add(field_name)

    def refresh_automatic_fields(
        self,
        *,
        is_starting_pitcher: bool | None = None,
        only_pitcher: bool = False,
    ) -> None:
        """Set initial pitcher flags unless the reviewer has overridden them.

        When the screen contains only one pitcher, that pitcher is treated as
        having thrown a complete game regardless of innings pitched. This also
        covers an extra-inning game where the starter leaves after the ninth.
        With multiple pitchers, nine or more innings is required. A manual
        correction remains authoritative through later OCR-stat edits, which
        keeps every calculated flag editable.
        """
        if is_starting_pitcher is not None and "starts" not in self.manually_corrected_stats:
            self.starts = int(is_starting_pitcher)

        outs = None
        if self.innings is not None and self.inning_fraction in (0, 1, 2):
            outs = self.innings * 3 + self.inning_fraction
        is_complete_game = only_pitcher or (outs is not None and outs >= 27)

        qs, hqs = self.qs_hqs
        if "qs" not in self.manually_corrected_stats:
            self.qs = qs
        if "hqs" not in self.manually_corrected_stats:
            self.hqs = hqs

        if "complete_games" not in self.manually_corrected_stats:
            self.complete_games = int(is_complete_game)
        if "shutouts" not in self.manually_corrected_stats:
            self.shutouts = int(self.complete_games == 1 and self.runs == 0)
        if "no_walk_games" not in self.manually_corrected_stats:
            self.no_walk_games = int(self.shutouts == 1 and self.walks_hbp == 0)

    @property
    def missing_stat_fields(self) -> tuple[str, ...]:
        return tuple(field_name for field_name in PITCHER_OCR_FIELDS if getattr(self, field_name) is None)

    @property
    def status(self) -> Literal["OK", "要確認", "エラー", "除外"]:
        if self.excluded_from_export:
            return "除外"
        if self.matched_name is None or self.missing_stat_fields:
            return "エラー"
        return "要確認" if self.requires_review else "OK"

    @property
    def qs_hqs(self) -> tuple[int, int]:
        if self.innings is None or self.inning_fraction is None or self.earned_runs is None:
            return 0, 0
        outs = self.innings * 3 + self.inning_fraction
        qs = int(outs >= 18 and self.earned_runs <= 3)
        hqs = int(outs >= 21 and self.earned_runs <= 2)
        return qs, hqs

    @property
    def review_reasons(self) -> tuple[str, ...]:
        if self.excluded_from_export:
            return ("GameJSON出力から手動で除外",)
        reasons: list[str] = []
        if self.matched_name is None:
            reasons.append("正式名が未選択")
        elif self.match_source == "alias":
            reasons.append("Alias一致")
        elif self.requires_review:
            reasons.append(f"名前照合を確認（{self.match_score:.1f}点）")
        if self.manually_added_name and self.matched_name:
            reasons.append("NameList未登録の手動追加選手")
        if self.missing_stat_fields:
            labels = "、".join(PITCHER_STAT_LABELS[field_name] for field_name in self.missing_stat_fields)
            reasons.append(f"数値が未入力: {labels}")
        return tuple(reasons)

    @property
    def review_reason_text(self) -> str:
        return " / ".join(self.review_reasons) or "確認済み"

    def to_pitcher_stats(self) -> PitcherStats:
        if self.missing_stat_fields:
            raise ValueError("未確認の投手数値が残っているため成績へ変換できません")
        return PitcherStats(
            appearances=1, qs=self.qs, hqs=self.hqs, starts=self.starts, wins=self.wins, losses=self.losses, holds=self.holds,
            saves=self.saves, innings=self.innings, inning_fraction=self.inning_fraction,
            pitches=self.pitches, batters_faced=self.batters_faced, hits_allowed=self.hits_allowed,
            strikeouts=self.strikeouts, walks_hbp=self.walks_hbp, runs=self.runs,
            earned_runs=self.earned_runs, wild_pitches=self.wild_pitches,
            home_runs_allowed=self.home_runs_allowed, complete_games=self.complete_games,
            shutouts=self.shutouts, no_walk_games=self.no_walk_games,
            intentional_walks=self.intentional_walks,
        )

    def to_serializable_dict(self) -> dict[str, object]:
        return {
            "ocrName": self.ocr_name, "matchedName": self.matched_name,
            "matchScore": self.match_score, "matchSource": self.match_source, "secondName": self.second_name,
            "secondScore": self.second_score, "requiresReview": self.requires_review,
            "excludedFromExport": self.excluded_from_export,
            "manuallyCorrectedName": self.manually_corrected_name,
            "manuallyAddedName": self.manually_added_name,
            "stats": {name: getattr(self, name) for name in PITCHER_OCR_FIELDS + PITCHER_MANUAL_BINARY_FIELDS + PITCHER_MANUAL_INTEGER_FIELDS},
            "ocrStats": self.ocr_stats, "manuallyCorrectedStats": sorted(self.manually_corrected_stats),
            "sourceRowIndex": self.source_row_index, "ocrDecision": self.ocr_decision,
            "remarks": self.remarks,
        }
