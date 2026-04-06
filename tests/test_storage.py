from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path

from screen_qa_assistant.models import AppSettings, ProviderProfile
from screen_qa_assistant.storage.settings_store import (
    JSONSettingsStore,
    build_screenshot_path,
    cleanup_saved_screenshots,
)


def build_settings() -> AppSettings:
    provider = ProviderProfile(
        id="local",
        name="Local",
        base_url="http://127.0.0.1:11434/v1",
        api_key_ref=None,
        model="llava",
        supports_vision=True,
        enable_reasoning=True,
        timeout_seconds=60,
        temperature=0.3,
        max_tokens=2048,
    )
    return AppSettings(
        default_provider_id="local",
        hotkey="Ctrl+Shift+A",
        save_enabled=True,
        save_dir="shots",
        cleanup_policy_days=14,
        window_prefs={"answer_window": {"width": 440}},
        providers=[provider],
    )


def test_build_screenshot_path_contains_timestamp(tmp_path: Path) -> None:
    now = datetime(2026, 4, 3, 21, 15, 30)

    path = build_screenshot_path(tmp_path, now=now)

    assert path.parent == tmp_path
    assert path.name == "screen-qa-20260403-211530.png"


def test_cleanup_saved_screenshots_only_deletes_old_managed_files(tmp_path: Path) -> None:
    old_file = tmp_path / "screen-qa-20260101-000000.png"
    new_file = tmp_path / "screen-qa-20260401-120000.png"
    foreign_file = tmp_path / "notes.png"

    old_file.write_bytes(b"old")
    new_file.write_bytes(b"new")
    foreign_file.write_bytes(b"keep")

    old_time = (datetime(2026, 1, 2) - datetime(1970, 1, 1)).total_seconds()
    new_time = (datetime(2026, 4, 1, 12, 0, 0) - datetime(1970, 1, 1)).total_seconds()
    old_file.touch()
    new_file.touch()
    foreign_file.touch()
    old_file.chmod(0o666)
    new_file.chmod(0o666)
    foreign_file.chmod(0o666)
    import os

    os.utime(old_file, (old_time, old_time))
    os.utime(new_file, (new_time, new_time))

    removed = cleanup_saved_screenshots(
        tmp_path,
        older_than_days=30,
        now=datetime(2026, 4, 3),
    )

    assert removed == [old_file]
    assert not old_file.exists()
    assert new_file.exists()
    assert foreign_file.exists()


def test_json_settings_store_round_trip(tmp_path: Path) -> None:
    settings_path = tmp_path / "settings.json"
    store = JSONSettingsStore(settings_path)
    settings = build_settings()

    store.save(settings)
    loaded = store.load()

    assert loaded == settings
