"""Compatibility APIs for persistent Game ID data, backed by QSettings."""

from __future__ import annotations

from pathlib import Path
from app.app_settings import GAME_ID_SERIALS, USER_NAME, get_settings, last_namelist_path, set_last_namelist_path


SETTINGS_PATH = Path(__file__).resolve().parents[1] / "config" / "settings.ini"


def load_last_namelist_path(settings_path: Path | None = None) -> Path | None:
    return last_namelist_path(get_settings(settings_path))


def save_last_namelist_path(path: Path, settings_path: Path | None = None) -> None:
    set_last_namelist_path(path, get_settings(settings_path))


def load_user_name(settings_path: Path | None = None) -> str:
    return get_settings(settings_path).value(USER_NAME, "", type=str)


def save_user_name(user_name: str, settings_path: Path | None = None) -> None:
    store = get_settings(settings_path)
    store.setValue(USER_NAME, user_name)
    store.sync()


def load_next_game_id_serial(prefix: str, settings_path: Path | None = None) -> int:
    """Return the next persistent serial for one Game ID prefix."""
    values = get_settings(settings_path).value(GAME_ID_SERIALS, {})
    value = values.get(prefix) if isinstance(values, dict) else None
    return value if isinstance(value, int) and not isinstance(value, bool) and value > 0 else 1


def save_next_game_id_serial(prefix: str, serial: int, settings_path: Path | None = None) -> None:
    """Persist the next serial without allowing an older value to overwrite it."""
    if serial < 1:
        raise ValueError("Game IDの通し番号は1以上である必要があります")
    store = get_settings(settings_path)
    values = store.value(GAME_ID_SERIALS, {})
    serials = values.copy() if isinstance(values, dict) else {}
    existing = serials.get(prefix)
    serials[prefix] = max(serial, existing) if isinstance(existing, int) and not isinstance(existing, bool) else serial
    store.setValue(GAME_ID_SERIALS, serials)
    store.sync()
