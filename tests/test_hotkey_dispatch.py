from __future__ import annotations

import ctypes
import os

from PySide6.QtCore import QTimer
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from screen_qa_assistant.desktop.hotkey import GlobalHotkeyWidget, WM_HOTKEY


def ensure_app() -> QApplication:
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def test_global_hotkey_dispatch_emits_activated_for_matching_message() -> None:
    app = ensure_app()
    hotkey = GlobalHotkeyWidget(app)
    hits: list[str] = []
    hotkey.activated.connect(lambda: hits.append("hit"))

    ctypes.windll.user32.PostMessageW(hotkey.window_handle, WM_HOTKEY, hotkey._hotkey_id, 0)
    QTimer.singleShot(80, app.quit)
    app.exec()

    assert hits == ["hit"]
    hotkey.dispose()


def test_global_hotkey_dispatch_ignores_unrelated_message() -> None:
    app = ensure_app()
    hotkey = GlobalHotkeyWidget(app)
    hits: list[str] = []
    hotkey.activated.connect(lambda: hits.append("hit"))

    ctypes.windll.user32.PostMessageW(hotkey.window_handle, 0x1234, hotkey._hotkey_id, 0)
    QTimer.singleShot(80, app.quit)
    app.exec()

    assert hits == []
    hotkey.dispose()
