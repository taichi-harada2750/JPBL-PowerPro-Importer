"""QSettings-backed settings whose values are safe to restore automatically."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QSettings

from app.app_info import APP_NAME, ORG_NAME

WINDOW_GEOMETRY = "window/geometry"
WINDOW_STATE = "window/state"
NAMELIST_LAST_PATH = "namelist/last_path"
IMAGE_LAST_DIRECTORY = "image/last_directory"
UI_THEME = "ui/theme"
USER_NAME = "game/user_name"
GAME_ID_SERIALS = "game/next_id_serials"

RESETTABLE_KEYS = (WINDOW_GEOMETRY, WINDOW_STATE, NAMELIST_LAST_PATH, IMAGE_LAST_DIRECTORY, UI_THEME)
VALID_THEMES = ("dark", "light", "system")


def get_settings(settings_path: Path | None = None) -> QSettings:
    """Use the Windows app store normally; a file-backed store is useful in tests."""
    if settings_path is not None:
        return QSettings(str(settings_path), QSettings.Format.IniFormat)
    return QSettings(ORG_NAME, APP_NAME)


def theme(settings: QSettings | None = None) -> str:
    value = (settings if settings is not None else get_settings()).value(UI_THEME, "dark", type=str)
    return value if value in VALID_THEMES else "dark"


def set_theme(value: str, settings: QSettings | None = None) -> None:
    store = settings if settings is not None else get_settings()
    store.setValue(UI_THEME, value if value in VALID_THEMES else "dark")
    store.sync()


def last_namelist_path(settings: QSettings | None = None) -> Path | None:
    value = (settings if settings is not None else get_settings()).value(NAMELIST_LAST_PATH, "", type=str)
    return Path(value) if value else None


def set_last_namelist_path(path: Path, settings: QSettings | None = None) -> None:
    store = settings if settings is not None else get_settings()
    store.setValue(NAMELIST_LAST_PATH, str(path))
    store.sync()


def image_last_directory(settings: QSettings | None = None) -> str:
    return (settings if settings is not None else get_settings()).value(IMAGE_LAST_DIRECTORY, "", type=str)


def set_image_last_directory(path: Path, settings: QSettings | None = None) -> None:
    store = settings if settings is not None else get_settings()
    store.setValue(IMAGE_LAST_DIRECTORY, str(path))
    store.sync()


def reset_user_preferences(settings: QSettings | None = None) -> None:
    store = settings if settings is not None else get_settings()
    for key in RESETTABLE_KEYS:
        store.remove(key)
    store.sync()
