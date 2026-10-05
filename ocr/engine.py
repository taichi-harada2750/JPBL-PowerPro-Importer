"""Replaceable OCR interface.

The parser only knows this interface and therefore remains independent of a
specific OCR package or cloud service.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class OcrEngine(ABC):
    @abstractmethod
    def recognize_text(self, image: Any) -> str:
        """Recognize a player-name cell. Return an empty string for no text."""

    @abstractmethod
    def recognize_number(self, image: Any) -> str:
        """Recognize a numeric cell. Return an empty string for an empty cell."""


class OcrEngineUnavailableError(RuntimeError):
    """The selected OCR backend is installed incorrectly or cannot be run."""
