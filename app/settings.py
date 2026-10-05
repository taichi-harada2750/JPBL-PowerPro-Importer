"""Small UTF-8 application settings store for user convenience."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


SETTINGS_PATH = Path(__file__).resolve().parents[1] / "config" / "settings.json"


def _load_settings(settings_path: Path) -> dict[str, Any]:
    try:
        document: Any = json.loads(settings_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return document if isinstance(document, dict) else {}


def _save_settings(document: dict[str, Any], settings_path: Path) -> None:
    settings_path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = settings_path.with_suffix(".tmp")
    temporary_path.write_text(json.dumps(document, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary_path.replace(settings_path)


def load_last_namelist_path(settings_path: Path = SETTINGS_PATH) -> Path | None:
    value = _load_settings(settings_path).get("lastNameListPath")
    return Path(value) if isinstance(value, str) and value else None


def save_last_namelist_path(path: Path, settings_path: Path = SETTINGS_PATH) -> None:
    document = _load_settings(settings_path)
    document["lastNameListPath"] = str(path)
    _save_settings(document, settings_path)


def load_user_name(settings_path: Path = SETTINGS_PATH) -> str:
    value = _load_settings(settings_path).get("userName")
    return value if isinstance(value, str) else ""


def save_user_name(user_name: str, settings_path: Path = SETTINGS_PATH) -> None:
    document = _load_settings(settings_path)
    document["userName"] = user_name
    _save_settings(document, settings_path)


def load_next_game_id_serial(prefix: str, settings_path: Path = SETTINGS_PATH) -> int:
    """Return the next persistent serial for one Game ID prefix."""
    values = _load_settings(settings_path).get("nextGameIdSerials")
    value = values.get(prefix) if isinstance(values, dict) else None
    return value if isinstance(value, int) and not isinstance(value, bool) and value > 0 else 1


def save_next_game_id_serial(prefix: str, serial: int, settings_path: Path = SETTINGS_PATH) -> None:
    """Persist the next serial without allowing an older value to overwrite it."""
    if serial < 1:
        raise ValueError("Game IDの通し番号は1以上である必要があります")
    document = _load_settings(settings_path)
    values = document.get("nextGameIdSerials")
    serials = values.copy() if isinstance(values, dict) else {}
    existing = serials.get(prefix)
    serials[prefix] = max(serial, existing) if isinstance(existing, int) and not isinstance(existing, bool) else serial
    document["nextGameIdSerials"] = serials
    _save_settings(document, settings_path)
