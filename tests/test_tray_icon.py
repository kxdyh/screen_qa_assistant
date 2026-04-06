from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from screen_qa_assistant.ui.tray_icon import build_tray_icon


def ensure_app() -> QApplication:
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def test_build_tray_icon_returns_multi_size_icon() -> None:
    ensure_app()
    icon = build_tray_icon()

    assert icon.isNull() is False
    sizes = {(size.width(), size.height()) for size in icon.availableSizes()}
    assert (16, 16) in sizes
    assert (24, 24) in sizes
    assert (32, 32) in sizes


def test_build_tray_icon_is_cached() -> None:
    ensure_app()

    first = build_tray_icon()
    second = build_tray_icon()

    assert first.cacheKey() == second.cacheKey()
