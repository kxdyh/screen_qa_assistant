from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from screen_qa_assistant.models import AppSettings, ProviderProfile
from screen_qa_assistant.storage.keyring_store import KeyringCredentialStore
from screen_qa_assistant.ui.settings_window import SettingsWindow


def ensure_app() -> QApplication:
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def build_provider(*, session_only: bool) -> ProviderProfile:
    return ProviderProfile(
        id="provider-1",
        name="Provider One",
        base_url="https://example.com/v1",
        api_key_ref="provider-provider-1",
        model="demo-model",
        supports_vision=True,
        session_only=session_only,
        enable_reasoning=False,
        timeout_seconds=60,
        temperature=0.2,
        max_tokens=2048,
    )


def test_settings_window_updates_security_hint_for_session_only_mode() -> None:
    ensure_app()
    window = SettingsWindow()

    window.session_only_checkbox.setChecked(False)
    persistent_text = window.api_key_security_label.text()
    window.session_only_checkbox.setChecked(True)
    session_text = window.api_key_security_label.text()

    assert "Windows Credential Manager" in persistent_text
    assert "当前会话" in session_text
    assert "不写入项目目录" in session_text


def test_settings_window_loads_session_only_provider_state() -> None:
    ensure_app()
    window = SettingsWindow()
    provider = build_provider(session_only=True)
    settings = AppSettings(
        default_provider_id=provider.id,
        hotkey="Ctrl+Q",
        save_enabled=False,
        save_dir=None,
        cleanup_policy_days=14,
        window_prefs={},
        providers=[provider],
    )
    store = KeyringCredentialStore()

    window.load_settings(settings, store)

    assert window.session_only_checkbox.isChecked() is True
    assert "当前会话" in window.api_key_security_label.text()
