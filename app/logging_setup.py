"""Application logging in the user's LocalAppData directory."""

from __future__ import annotations

import logging
import os
from logging.handlers import RotatingFileHandler
from pathlib import Path

from app.app_info import APP_NAME, ORG_NAME


def log_directory() -> Path:
    local_app_data = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
    return local_app_data / ORG_NAME / APP_NAME / "logs"


def configure_logging() -> logging.Logger:
    logger = logging.getLogger("jpbl_powerpro_importer")
    logger.setLevel(logging.INFO)
    if logger.handlers:
        return logger
    try:
        directory = log_directory()
        directory.mkdir(parents=True, exist_ok=True)
        handler = RotatingFileHandler(directory / "app.log", encoding="utf-8", maxBytes=1_000_000, backupCount=2)
        handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
        logger.addHandler(handler)
    except OSError:
        logger.addHandler(logging.NullHandler())
    return logger
