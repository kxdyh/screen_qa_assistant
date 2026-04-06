from __future__ import annotations

import os
from pathlib import Path


APP_DIR_NAME = "ScreenQAAssistant"


def get_app_data_dir() -> Path:
    root = os.getenv("LOCALAPPDATA")
    if root:
        path = Path(root) / APP_DIR_NAME
    else:
        path = Path.home() / f".{APP_DIR_NAME.lower()}"
    path.mkdir(parents=True, exist_ok=True)
    return path


def get_settings_path() -> Path:
    return get_app_data_dir() / "settings.json"


def get_lock_path() -> Path:
    return get_app_data_dir() / "app.lock"


def get_default_capture_dir() -> Path:
    path = get_app_data_dir() / "captures"
    path.mkdir(parents=True, exist_ok=True)
    return path
