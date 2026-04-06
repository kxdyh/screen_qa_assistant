from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from screen_qa_assistant.main import build_startup_console_message
from screen_qa_assistant.ui.launch_panel import LaunchPanel


def ensure_app() -> QApplication:
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def test_build_startup_console_message_mentions_hotkey() -> None:
    message = build_startup_console_message("Ctrl+Q", True)

    assert "Ctrl+Q" in message
    assert "托盘" in message
    assert "截图" in message


def test_build_startup_console_message_mentions_hotkey_conflict() -> None:
    message = build_startup_console_message(
        "Ctrl+J",
        True,
        hotkey_error="这个快捷键已经被其他程序占用了，请换一个组合键。",
    )

    assert "Ctrl+J" in message
    assert "占用" in message
    assert "设置" in message


def test_launch_panel_present_makes_feedback_visible() -> None:
    ensure_app()
    panel = LaunchPanel()

    panel.present("Ctrl+Q", has_models=True)

    assert panel.isVisible() is True
    assert "Ctrl+Q" in panel.summary_text()


def test_launch_panel_can_switch_to_hotkey_error_state() -> None:
    ensure_app()
    panel = LaunchPanel()

    panel.present_hotkey_error("Ctrl+Q", "这个快捷键已经被其他程序占用了，请换一个组合键。")

    assert "占用" in panel.summary_text()


def test_launch_panel_hides_background_hint_copy_in_formal_ui() -> None:
    ensure_app()
    panel = LaunchPanel()

    panel.present("Ctrl+Q", has_models=True)

    assert panel.hint_label.isHidden() is True


def test_launch_panel_uses_light_button_theme() -> None:
    ensure_app()
    panel = LaunchPanel()

    assert "#111111" in panel.capture_button.styleSheet()
