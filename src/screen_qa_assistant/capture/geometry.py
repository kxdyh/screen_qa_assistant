from __future__ import annotations

from PySide6.QtCore import QPoint, QRect, QSize
from PySide6.QtGui import QScreen


def normalize_drag_rect(start: QPoint, end: QPoint) -> QRect:
    left = min(start.x(), end.x())
    top = min(start.y(), end.y())
    right = max(start.x(), end.x())
    bottom = max(start.y(), end.y())
    return QRect(left, top, right - left, bottom - top)


def calculate_prompt_rect(selection_rect: QRect, overlay_rect: QRect, preferred_size: QSize) -> QRect:
    margin = 24
    gap = 16
    width = min(max(preferred_size.width(), 360), max(360, overlay_rect.width() - margin * 2))
    height = preferred_size.height()

    x = selection_rect.center().x() - width // 2
    x = max(margin, min(x, overlay_rect.width() - width - margin))

    below_y = selection_rect.bottom() + gap
    if below_y + height <= overlay_rect.height() - margin:
        return QRect(x, below_y, width, height)

    above_y = selection_rect.top() - gap - height
    if above_y >= margin:
        return QRect(x, above_y, width, height)

    clamped_y = max(margin, min(below_y, overlay_rect.height() - height - margin))
    return QRect(x, clamped_y, width, height)


def pick_active_screen_rect(screen_rects: list[QRect], cursor_pos: QPoint) -> QRect:
    if not screen_rects:
        return QRect(0, 0, 1280, 720)
    for rect in screen_rects:
        if rect.contains(cursor_pos):
            return QRect(rect)
    return min(
        (QRect(rect) for rect in screen_rects),
        key=lambda rect: abs(rect.center().x() - cursor_pos.x()) + abs(rect.center().y() - cursor_pos.y()),
    )


def calculate_intro_anchor(active_screen_rect: QRect, overlay_rect: QRect) -> QPoint:
    offset_y = max(72, min(180, active_screen_rect.height() // 8))
    x = active_screen_rect.center().x() - overlay_rect.left()
    y = active_screen_rect.top() + offset_y - overlay_rect.top()
    return QPoint(x, y)


def union_screen_rect(screens: list[QScreen]) -> QRect:
    if not screens:
        return QRect(0, 0, 1280, 720)
    rect = QRect(screens[0].geometry())
    for screen in screens[1:]:
        rect = rect.united(screen.geometry())
    return rect
