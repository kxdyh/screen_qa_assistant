from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QEvent, QPoint, QPointF, QRect, QSize, Qt
from PySide6.QtGui import QMouseEvent
from PySide6.QtWidgets import QApplication

from screen_qa_assistant.ui.answer_window import (
    AnswerWindow,
    ResizeEdge,
    compute_resized_geometry,
)


def ensure_app() -> QApplication:
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def test_answer_window_expands_after_first_chunk() -> None:
    ensure_app()
    window = AnswerWindow({"width": 420, "height": 420})

    window.queue_turn("Demo", "请描述截图内容", collapse=True, reset=True)
    assert window.is_expanded is False

    window.append_chunk("第一段结果")

    assert window.is_expanded is True
    assert "第一段结果" in window.transcript_text()


def test_answer_window_applies_true_rounded_mask() -> None:
    ensure_app()
    window = AnswerWindow({"width": 420, "height": 420})
    window.resize(420, 220)
    window.show()
    QApplication.processEvents()

    mask = window.mask()

    assert mask.contains(window.rect().center()) is True
    assert mask.contains(window.rect().topLeft()) is False


def test_answer_window_can_be_dragged_from_header() -> None:
    ensure_app()
    window = AnswerWindow({"width": 420, "height": 420})
    window.move(100, 100)
    window.show()
    QApplication.processEvents()

    press_event = QMouseEvent(
        QEvent.Type.MouseButtonPress,
        QPointF(60, 26),
        QPointF(60, 26),
        QPointF(160, 126),
        Qt.MouseButton.LeftButton,
        Qt.MouseButton.LeftButton,
        Qt.KeyboardModifier.NoModifier,
    )
    move_event = QMouseEvent(
        QEvent.Type.MouseMove,
        QPointF(90, 38),
        QPointF(90, 38),
        QPointF(220, 168),
        Qt.MouseButton.NoButton,
        Qt.MouseButton.LeftButton,
        Qt.KeyboardModifier.NoModifier,
    )
    release_event = QMouseEvent(
        QEvent.Type.MouseButtonRelease,
        QPointF(90, 38),
        QPointF(90, 38),
        QPointF(220, 168),
        Qt.MouseButton.LeftButton,
        Qt.MouseButton.NoButton,
        Qt.KeyboardModifier.NoModifier,
    )

    start_pos = window.pos()
    window.mousePressEvent(press_event)
    window.mouseMoveEvent(move_event)
    window.mouseReleaseEvent(release_event)

    assert window.pos() != start_pos


def test_answer_window_dragging_title_label_does_not_trigger_resize() -> None:
    ensure_app()
    window = AnswerWindow({"width": 420, "height": 420})
    window.move(100, 100)
    window.show()
    QApplication.processEvents()

    start_size = window.size()
    start_pos = window.pos()
    press_event = QMouseEvent(
        QEvent.Type.MouseButtonPress,
        QPointF(18, 16),
        QPointF(18, 16),
        QPointF(140, 120),
        Qt.MouseButton.LeftButton,
        Qt.MouseButton.LeftButton,
        Qt.KeyboardModifier.NoModifier,
    )
    move_event = QMouseEvent(
        QEvent.Type.MouseMove,
        QPointF(32, 22),
        QPointF(32, 22),
        QPointF(186, 142),
        Qt.MouseButton.NoButton,
        Qt.MouseButton.LeftButton,
        Qt.KeyboardModifier.NoModifier,
    )
    release_event = QMouseEvent(
        QEvent.Type.MouseButtonRelease,
        QPointF(32, 22),
        QPointF(32, 22),
        QPointF(186, 142),
        Qt.MouseButton.LeftButton,
        Qt.MouseButton.NoButton,
        Qt.KeyboardModifier.NoModifier,
    )

    window.eventFilter(window.provider_label, press_event)
    window.eventFilter(window.provider_label, move_event)
    window.eventFilter(window.provider_label, release_event)

    assert window.size() == start_size
    assert window.pos() != start_pos


def test_answer_window_loading_line_offset_advances() -> None:
    ensure_app()
    window = AnswerWindow({"width": 420, "height": 420})
    window.queue_turn("Demo", "加载测试", collapse=True, reset=True)

    start_offset = window._line_offset
    window._advance_loading_line()

    assert window._line_offset != start_offset


def test_answer_window_can_enter_iconified_mode_and_restore() -> None:
    ensure_app()
    window = AnswerWindow({"width": 420, "height": 420})
    window._line_timer.stop()

    window.set_iconified(True, animate=False)
    assert window.is_iconified is True
    assert window.content_frame.isHidden() is True

    window.set_iconified(False, animate=False)
    assert window.is_iconified is False


def test_answer_window_iconified_right_click_requests_context_menu() -> None:
    ensure_app()
    window = AnswerWindow({"width": 420, "height": 420})
    window.set_iconified(True, animate=False)
    requested: list[QPoint] = []
    window.icon_menu_requested.connect(requested.append)

    press_event = QMouseEvent(
        QEvent.Type.MouseButtonPress,
        QPointF(24, 24),
        QPointF(24, 24),
        QPointF(180, 180),
        Qt.MouseButton.RightButton,
        Qt.MouseButton.RightButton,
        Qt.KeyboardModifier.NoModifier,
    )

    window.mousePressEvent(press_event)

    assert requested == [QPoint(180, 180)]


def test_answer_window_font_scale_updates_window_metrics() -> None:
    ensure_app()
    window = AnswerWindow({"width": 420, "height": 420})

    base_width = window._preferred_width
    base_height = window._expanded_height
    window.set_font_scale("large", animate=False)

    assert window.current_font_scale == "large"
    assert window._preferred_width > base_width
    assert window._expanded_height > base_height


def test_compute_resized_geometry_supports_corner_resize() -> None:
    start = QRect(100, 100, 420, 420)
    target = compute_resized_geometry(
        start,
        ResizeEdge.RIGHT | ResizeEdge.BOTTOM,
        QPoint(80, 60),
        minimum_size=QSize(320, 220),
    )

    assert target.width() == 500
    assert target.height() == 480


def test_answer_window_corner_resize_zone_is_larger_than_plain_edge_zone() -> None:
    ensure_app()
    window = AnswerWindow({"width": 420, "height": 420})
    window.resize(420, 320)

    assert window._hit_resize_edges(QPointF(14, 14)) == (ResizeEdge.LEFT | ResizeEdge.TOP)
    assert window._hit_resize_edges(QPointF(24, 14)) == ResizeEdge.NONE
