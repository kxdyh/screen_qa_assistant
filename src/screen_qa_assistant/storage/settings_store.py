from __future__ import annotations

import json
import re
from datetime import datetime, timedelta
from pathlib import Path

from screen_qa_assistant.models import AppSettings


SCREENSHOT_PATTERN = re.compile(r"^screen-qa-\d{8}-\d{6}\.png$")


def build_screenshot_path(directory: Path, now: datetime | None = None) -> Path:
    current = now or datetime.now()
    directory.mkdir(parents=True, exist_ok=True)
    filename = current.strftime("screen-qa-%Y%m%d-%H%M%S.png")
    return directory / filename


def cleanup_saved_screenshots(
    directory: Path,
    older_than_days: int,
    now: datetime | None = None,
) -> list[Path]:
    if not directory.exists():
        return []

    current = now or datetime.now()
    cutoff = current - timedelta(days=older_than_days)
    removed: list[Path] = []
    for path in directory.iterdir():
        if not path.is_file() or not SCREENSHOT_PATTERN.match(path.name):
            continue
        modified = datetime.fromtimestamp(path.stat().st_mtime)
        if modified <= cutoff:
            path.unlink(missing_ok=True)
            removed.append(path)
    return removed


class JSONSettingsStore:
    def __init__(self, path: Path, default_save_dir: str | None = None) -> None:
        self.path = path
        self.default_save_dir = default_save_dir

    def load(self) -> AppSettings:
        if not self.path.exists():
            return AppSettings.default(save_dir=self.default_save_dir)
        payload = json.loads(self.path.read_text(encoding="utf-8"))
        return AppSettings.model_validate(payload)

    def save(self, settings: AppSettings) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(
            settings.model_dump_json(indent=2),
            encoding="utf-8",
        )
