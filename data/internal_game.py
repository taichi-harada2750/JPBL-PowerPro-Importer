"""Compatibility import for the internal game model."""

from app.models import BatterStats, InternalGame, PitcherStats, PlayerRecord, RecognitionInfo

__all__ = [
    "BatterStats",
    "InternalGame",
    "PitcherStats",
    "PlayerRecord",
    "RecognitionInfo",
]
