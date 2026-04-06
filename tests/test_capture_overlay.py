from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QEvent, QPoint, QPointF, QRect, Qt
from PySide6.QtGui import QImage, QKeyEvent, QMouseEvent, QPainter
from PySide6.QtWidgets import QApplication

from screen_qa_assistant.capture.overlay import AutoGrowQuestionEdit, CaptureOverlay, _build_intro_visual_state


def ensure_app() -> QApplication:
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


class FakeScreenshotService:
    def grab_region(self, rect: QRect) -> bytes:
        return b"fake-png"


def test_capture_overlay_releases_keyboard_before_showing_question_composer() -> None:
    ensure_app()
    overlay = CaptureOverlay(FakeScreenshotService(), submit_callback=lambda *_: None)
    overlay._virtual_rect = QRect(0, 0, 1600, 900)
    overlay.setGeometry(overlay._virtual_rect)
    overlay._dragging = True
    overlay._drag_start = QPoint(80, 120)

    calls: list[str] = []
    overlay.releaseKeyboard = lambda: calls.append("release")  # type: ignore[method-assign]
    overlay.composer.present = lambda selection_rect, overlay_rect: calls.append("present")  # type: ignore[method-assign]

    event = QMouseEvent(
        QEvent.Type.MouseButtonRelease,
        QPointF(320, 300),
        QPointF(320, 300),
        Qt.MouseButton.LeftButton,
        Qt.MouseButton.LeftButton,
        Qt.KeyboardModifier.NoModifier,
    )

    overlay.mouseReleaseEvent(event)

    assert calls == ["release", "present"]


def test_capture_overlay_enter_without_selection_opens_text_only_composer() -> None:
    ensure_app()
    overlay = CaptureOverlay(FakeScreenshotService(), submit_callback=lambda *_: None)
    overlay._virtual_rect = QRect(0, 0, 1600, 900)
    overlay.setGeometry(overlay._virtual_rect)
    overlay._intro_anchor = QPoint(640, 120)

    calls: list[str] = []
    overlay.releaseKeyboard = lambda: calls.append("release")  # type: ignore[method-assign]
    overlay.composer.present = lambda *args, **kwargs: calls.append(f"text_only={kwargs.get('text_only')}")  # type: ignore[method-assign]

    event = QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_Return, Qt.KeyboardModifier.NoModifier)
    overlay.keyPressEvent(event)

    assert calls == ["release", "text_only=True"]


def test_capture_overlay_intro_draw_does_not_raise() -> None:
    ensure_app()
    overlay = CaptureOverlay(FakeScreenshotService(), submit_callback=lambda *_: None)
    overlay.resize(1600, 900)
    overlay._intro_anchor = QPoint(800, 140)
    overlay._intro_morph_progress = 1.0
    overlay._intro_label_opacity = 1.0

    image = QImage(1600, 900, QImage.Format.Format_ARGB32_Premultiplied)
    painter = QPainter(image)
    try:
        overlay._draw_intro(painter)
    finally:
        painter.end()


def test_intro_visual_state_starts_with_only_small_dot() -> None:
    state = _build_intro_visual_state(progress=0.08, label_opacity=1.0, label_width=320.0)

    assert state.width == 0.0
    assert state.height == 0.0
    assert state.outer_alpha == 0
    assert state.label_alpha == 0
    assert state.dot_alpha > 0


def test_begin_capture_resets_intro_state_before_first_show() -> None:
    ensure_app()
    overlay = CaptureOverlay(FakeScreenshotService(), submit_callback=lambda *_: None)
    overlay._backdrop_strength = 1.0
    overlay._intro_morph_progress = 1.0
    overlay._intro_label_opacity = 1.0

    seen: list[tuple[float, float, float]] = []
    overlay.show = lambda: seen.append(  # type: ignore[method-assign]
        (overlay._backdrop_strength, overlay._intro_morph_progress, overlay._intro_label_opacity)
    )
    overlay.raise_ = lambda: None  # type: ignore[method-assign]
    overlay.activateWindow = lambda: None  # type: ignore[method-assign]
    overlay.grabKeyboard = lambda: None  # type: ignore[method-assign]

    overlay.begin_capture()

    assert seen == [(0.0, 0.0, 0.0)]


def test_begin_capture_keeps_overlay_invisible_until_first_frame_is_ready() -> None:
    ensure_app()
    overlay = CaptureOverlay(FakeScreenshotService(), submit_callback=lambda *_: None)

    state = {"opacity": None}
    seen: list[float | None] = []
    overlay.setWindowOpacity = lambda value: state.__setitem__("opacity", value)  # type: ignore[method-assign]
    overlay.show = lambda: seen.append(state["opacity"])  # type: ignore[method-assign]
    overlay.raise_ = lambda: None  # type: ignore[method-assign]
    overlay.activateWindow = lambda: None  # type: ignore[method-assign]
    overlay.grabKeyboard = lambda: None  # type: ignore[method-assign]
    overlay._start_intro_animation = lambda: None  # type: ignore[method-assign]

    overlay.begin_capture()

    assert seen == [0.0]


def test_question_composer_uses_light_surface_style() -> None:
    ensure_app()
    overlay = CaptureOverlay(FakeScreenshotService(), submit_callback=lambda *_: None)

    assert "255, 254, 251" in overlay.composer.styleSheet()
    assert "rgba(8, 19, 28, 245)" not in overlay.composer.styleSheet()


def test_question_composer_uses_short_placeholder_in_text_mode() -> None:
    ensure_app()
    overlay = CaptureOverlay(FakeScreenshotService(), submit_callback=lambda *_: None)
    overlay._virtual_rect = QRect(0, 0, 1600, 900)
    overlay.setGeometry(overlay._virtual_rect)
    overlay._intro_anchor = QPoint(640, 120)

    overlay._show_text_only_composer()

    assert overlay.composer.editor.placeholderText() == "输入你的问题"


def test_auto_grow_question_edit_expands_for_wrapped_lines() -> None:
    app = ensure_app()
    editor = AutoGrowQuestionEdit()
    editor.resize(140, editor.height())
    editor.show()
    app.processEvents()

    start_height = editor.height()
    editor.setPlainText("这是一段很长很长的测试文本，用来验证自动换行后输入框会继续增高。" * 6)
    app.processEvents()

    assert editor.height() >= start_height + 24
