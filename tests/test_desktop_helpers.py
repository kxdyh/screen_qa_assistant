from __future__ import annotations

from PySide6.QtCore import QPoint, QRect, QSize

from screen_qa_assistant.capture.geometry import (
    calculate_intro_anchor,
    calculate_prompt_rect,
    normalize_drag_rect,
    pick_active_screen_rect,
)
from screen_qa_assistant.desktop.hotkey import parse_hotkey


def test_normalize_drag_rect_orders_points() -> None:
    rect = normalize_drag_rect(QPoint(220, 180), QPoint(40, 60))

    assert rect == QRect(40, 60, 180, 120)


def test_calculate_prompt_rect_prefers_below_selection() -> None:
    overlay = QRect(0, 0, 1600, 900)
    selection = QRect(200, 200, 360, 180)

    rect = calculate_prompt_rect(selection, overlay, QSize(420, 120))

    assert rect.top() > selection.bottom()
    assert rect.left() >= 24


def test_calculate_prompt_rect_moves_above_when_needed() -> None:
    overlay = QRect(0, 0, 1600, 900)
    selection = QRect(300, 820, 360, 80)

    rect = calculate_prompt_rect(selection, overlay, QSize(420, 120))

    assert rect.bottom() < selection.top()


def test_pick_active_screen_rect_prefers_cursor_screen() -> None:
    screens = [
        QRect(0, 0, 1920, 1080),
        QRect(1920, 0, 2560, 1440),
    ]

    rect = pick_active_screen_rect(screens, QPoint(2200, 400))

    assert rect == QRect(1920, 0, 2560, 1440)


def test_calculate_intro_anchor_uses_top_band_of_active_screen() -> None:
    overlay = QRect(0, 0, 4480, 1440)
    active_screen = QRect(1920, 0, 2560, 1440)

    anchor = calculate_intro_anchor(active_screen, overlay)

    assert anchor.x() == active_screen.center().x()
    assert 72 <= anchor.y() <= 220


def test_parse_hotkey_parses_common_sequence() -> None:
    modifiers, key_code = parse_hotkey("Ctrl+Shift+A")

    assert modifiers == 0x0002 | 0x0004
    assert key_code == ord("A")
