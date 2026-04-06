from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from PySide6.QtCore import Property, QEasingCurve, QPropertyAnimation, QPoint, QRect, QRectF, QSize, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QCursor, QFont, QGuiApplication, QKeyEvent, QMouseEvent, QPainter, QPainterPath, QPalette, QPen, QResizeEvent
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QPlainTextEdit, QPushButton, QVBoxLayout, QWidget

from screen_qa_assistant.capture.geometry import (
    calculate_intro_anchor,
    calculate_prompt_rect,
    normalize_drag_rect,
    pick_active_screen_rect,
    union_screen_rect,
)
from screen_qa_assistant.capture.screenshot import ScreenshotService
from screen_qa_assistant.ui.theme import (
    ACCENT,
    ACCENT_SOFT,
    BODY_FONT,
    DISPLAY_FONT,
    ERROR,
    LIGHT_ACCENT,
    LIGHT_LINE,
    LIGHT_LINE_STRONG,
    LIGHT_PANEL,
    LIGHT_PANEL_ALT,
    LIGHT_SOFT_ACCENT,
    LIGHT_TEXT,
    PANEL_BG,
    PANEL_SOFT,
    TEXT,
    button_stylesheet,
    clean_button_stylesheet,
    fade_widget,
    fade_window,
    keep_animation,
)


def _clamp(value: float, low: float = 0.0, high: float = 1.0) -> float:
    return max(low, min(high, value))


def _segment(progress: float, start: float, end: float) -> float:
    if end <= start:
        return 1.0
    return _clamp((progress - start) / (end - start))


def _ease_out(progress: float) -> float:
    t = _clamp(progress)
    return 1.0 - (1.0 - t) ** 3


def _lerp(start: float, end: float, progress: float) -> float:
    return start + (end - start) * _clamp(progress)


@dataclass(frozen=True)
class IntroVisualState:
    width: float
    height: float
    radius: float
    outer_alpha: int
    dot_alpha: int
    dot_size: float
    label_alpha: int


def _build_intro_visual_state(progress: float, label_opacity: float, label_width: float) -> IntroVisualState:
    progress = _clamp(progress)
    label_opacity = _clamp(label_opacity)

    # 开场只允许白点淡入，整体胶囊和文字都必须保持隐藏。
    dot_fade_in = _ease_out(_segment(progress, 0.0, 0.16))
    square_t = _ease_out(_segment(progress, 0.20, 0.44))
    stretch_t = _ease_out(_segment(progress, 0.44, 0.84))
    settle_t = _ease_out(_segment(progress, 0.84, 1.0))

    width = _lerp(0.0, 110.0, square_t)
    width = _lerp(width, label_width, stretch_t)

    height = _lerp(0.0, 110.0, square_t)
    height = _lerp(height, 86.0, stretch_t)
    height = _lerp(height, 82.0, settle_t)

    if height > 0:
        radius = _lerp(22.0, height / 2.0, stretch_t)
    else:
        radius = 22.0

    outer_alpha = int(255 * _ease_out(_segment(progress, 0.24, 0.42)))

    dot_hold = 1.0 - _ease_out(_segment(progress, 0.42, 0.90))
    dot_alpha = int(255 * dot_fade_in * max(0.0, dot_hold))
    dot_size = _lerp(16.0, 28.0, dot_fade_in)
    dot_size = _lerp(dot_size, 14.0, _ease_out(_segment(progress, 0.44, 0.84)))

    label_gate = _ease_out(_segment(progress, 0.82, 1.0))
    label_alpha = int(255 * label_opacity * label_gate)

    return IntroVisualState(
        width=width,
        height=height,
        radius=radius,
        outer_alpha=outer_alpha,
        dot_alpha=dot_alpha,
        dot_size=dot_size,
        label_alpha=label_alpha,
    )


class AutoGrowQuestionEdit(QPlainTextEdit):
    submit_requested = Signal()
    cancel_requested = Signal()

    def __init__(self) -> None:
        super().__init__()
        self.setPlaceholderText("输入你的问题")
        self._min_visible_lines = 1
        self._max_visible_lines = 6
        self.setStyleSheet(
            f"""
            QPlainTextEdit {{
                background: rgba(255, 255, 255, 0.96);
                color: {LIGHT_TEXT};
                border: 1px solid {LIGHT_LINE};
                border-radius: 18px;
                padding: 10px 12px;
                selection-background-color: {LIGHT_SOFT_ACCENT};
                font-family: "{BODY_FONT}";
                font-size: 13px;
            }}
            QPlainTextEdit:focus {{
                border-color: {LIGHT_LINE_STRONG};
            }}
            """
        )
        palette = self.palette()
        palette.setColor(QPalette.ColorRole.Text, QColor(LIGHT_TEXT))
        palette.setColor(QPalette.ColorRole.Base, QColor(LIGHT_PANEL))
        palette.setColor(QPalette.ColorRole.Highlight, QColor(LIGHT_SOFT_ACCENT))
        palette.setColor(QPalette.ColorRole.HighlightedText, QColor(LIGHT_TEXT))
        palette.setColor(QPalette.ColorRole.PlaceholderText, QColor(LIGHT_LINE_STRONG))
        self.setPalette(palette)
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.textChanged.connect(self.adjust_to_content)
        self.adjust_to_content()

    def adjust_to_content(self) -> None:
        total_lines = self._visual_line_count()
        visible_lines = max(self._min_visible_lines, min(self._max_visible_lines, total_lines))
        height = max(48, 30 + visible_lines * self.fontMetrics().lineSpacing())
        self.setFixedHeight(height)
        self.setVerticalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
            if total_lines <= self._max_visible_lines
            else Qt.ScrollBarPolicy.ScrollBarAsNeeded
        )

    def resizeEvent(self, event: QResizeEvent) -> None:  # type: ignore[override]
        super().resizeEvent(event)
        self.adjust_to_content()

    def _visual_line_count(self) -> int:
        count = 0
        block = self.document().firstBlock()
        while block.isValid():
            layout = block.layout()
            count += max(1, layout.lineCount() if layout is not None else 1)
            block = block.next()
        return max(1, count)

    def keyPressEvent(self, event: QKeyEvent) -> None:  # type: ignore[override]
        if event.key() == Qt.Key.Key_Escape:
            self.cancel_requested.emit()
            event.accept()
            return
        if event.key() in {Qt.Key.Key_Return, Qt.Key.Key_Enter} and not (
            event.modifiers() & Qt.KeyboardModifier.ShiftModifier
        ):
            self.submit_requested.emit()
            event.accept()
            return
        super().keyPressEvent(event)


class QuestionComposer(QFrame):
    def __init__(self, submit: Callable[[str], None], cancel: Callable[[], None]) -> None:
        super().__init__(None)
        self._submit = submit
        self._cancel = cancel
        self._selection_rect = QRect()
        self._overlay_rect = QRect()
        self._anchor_point = QPoint()
        self._text_only_mode = False

        self.setObjectName("QuestionComposer")
        self.setStyleSheet(
            f"""
            QFrame#QuestionComposer {{
                background: rgba(255, 254, 251, 248);
                border: 1px solid {LIGHT_LINE};
                border-radius: 28px;
            }}
            """
        )
        self.hide()

        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 18, 18, 18)
        layout.setSpacing(12)

        self.title_label = QLabel("输入问题")
        self.title_label.setStyleSheet(
            f'color: {LIGHT_TEXT}; font-family: "{DISPLAY_FONT}"; font-size: 14px; font-weight: 700; border: none;'
        )
        layout.addWidget(self.title_label)

        self.editor = AutoGrowQuestionEdit()
        self.editor.submit_requested.connect(self._emit_submit)
        self.editor.cancel_requested.connect(self._cancel)
        self.editor.textChanged.connect(self._resize_to_content)
        layout.addWidget(self.editor)

        footer = QHBoxLayout()
        footer.setSpacing(10)
        layout.addLayout(footer)

        self.error_label = QLabel("")
        self.error_label.setStyleSheet(
            f'color: {ERROR}; font-family: "{BODY_FONT}"; font-size: 11px; border: none;'
        )
        footer.addWidget(self.error_label, 1)

        self.cancel_button = QPushButton("取消")
        self.cancel_button.setStyleSheet(
            clean_button_stylesheet(
                fill=LIGHT_PANEL_ALT,
                text=LIGHT_TEXT,
                border=LIGHT_LINE,
                hover_fill="#FFFFFF",
            )
        )
        self.cancel_button.clicked.connect(self._cancel)
        footer.addWidget(self.cancel_button)

        self.submit_button = QPushButton("完成")
        self.submit_button.setStyleSheet(
            clean_button_stylesheet(
                fill=LIGHT_ACCENT,
                text=LIGHT_PANEL,
                border=LIGHT_ACCENT,
                hover_fill="#2A2A2A",
                pressed_fill="#000000",
            )
        )
        self.submit_button.clicked.connect(self._emit_submit)
        footer.addWidget(self.submit_button)

    def present(
        self,
        selection_rect: QRect,
        overlay_rect: QRect,
        *,
        text_only: bool = False,
        anchor_point: QPoint | None = None,
    ) -> None:
        self._selection_rect = QRect(selection_rect)
        self._overlay_rect = QRect(overlay_rect)
        self._anchor_point = QPoint(anchor_point) if anchor_point is not None else QPoint()
        self._text_only_mode = text_only
        self.title_label.setText(
            "直接输入问题"
            if text_only
            else "写下你想问的问题"
        )
        self.editor.setPlaceholderText("输入你的问题")
        self.editor.clear()
        self.error_label.clear()
        self._resize_to_content()
        self.show()
        self.raise_()
        fade_widget(self, 0.0, 1.0, 90)
        self.editor.setFocus()

    def show_error(self, message: str) -> None:
        self.error_label.setText(message)

    def _emit_submit(self) -> None:
        text = self.editor.toPlainText().strip()
        if not text:
            self.show_error("先输入一个问题再提交")
            return
        self._submit(text)

    def _resize_to_content(self) -> None:
        if self._overlay_rect.isNull():
            return
        if self._text_only_mode:
            width = 560
            anchor = self._anchor_point if not self._anchor_point.isNull() else self._overlay_rect.center()
            selection_rect = QRect(anchor.x() - 120, anchor.y() + 26, 240, 52)
        else:
            width = min(max(self._selection_rect.width() + 80, 380), 560)
            selection_rect = self._selection_rect
        desired = QSize(width, self.sizeHint().height() + 8)
        rect = calculate_prompt_rect(selection_rect, self._overlay_rect, desired)
        self.setGeometry(rect)


class CaptureOverlay(QWidget):
    def __init__(
        self,
        screenshot_service: ScreenshotService,
        submit_callback: Callable[[bytes | None, str, QRect], str | None],
        cancel_callback: Callable[[], None] | None = None,
    ) -> None:
        super().__init__(None)
        self.screenshot_service = screenshot_service
        self.submit_callback = submit_callback
        self.cancel_callback = cancel_callback or (lambda: None)

        self._drag_start = QPoint()
        self._drag_end = QPoint()
        self._selection_rect = QRect()
        self._selection_global_rect = QRect()
        self._captured_bytes: bytes | None = None
        self._dragging = False
        self._virtual_rect = QRect()
        self._intro_anchor = QPoint()
        self._supports_vision = True
        self._text_only_mode = False
        self._intro_message = "Enter 直接提问 / 拖拽截图"

        self._backdrop_strength = 0.0
        self._intro_morph_progress = 0.0
        self._intro_label_opacity = 0.0

        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
        )
        self.setMouseTracking(True)
        self.setCursor(Qt.CursorShape.CrossCursor)
        self.hide()

        self.composer = QuestionComposer(self._handle_submit, self.cancel_capture)
        self.composer.setParent(self)

    def _reset_intro_state(self) -> None:
        self._backdrop_strength = 0.0
        self._intro_morph_progress = 0.0
        self._intro_label_opacity = 0.0

    def set_provider_capabilities(self, supports_vision: bool) -> None:
        self._supports_vision = supports_vision
        self._intro_message = "Enter 直接输入问题" if not supports_vision else "Enter 直接提问 / 拖拽截图"
        self.setCursor(Qt.CursorShape.IBeamCursor if not supports_vision else Qt.CursorShape.CrossCursor)
        self.update()

    def begin_capture(self) -> None:
        screens = QGuiApplication.screens()
        self._virtual_rect = union_screen_rect(screens)
        self.setGeometry(self._virtual_rect)
        active_screen = pick_active_screen_rect([screen.geometry() for screen in screens], QCursor.pos())
        self._intro_anchor = calculate_intro_anchor(active_screen, self._virtual_rect)
        self._selection_rect = QRect()
        self._selection_global_rect = QRect()
        self._captured_bytes = None
        self._dragging = False
        self._text_only_mode = False
        self.composer.hide()
        self._reset_intro_state()
        self.setWindowOpacity(0.0)
        self.show()
        self.repaint()
        self.raise_()
        self.activateWindow()
        self.grabKeyboard()
        self._start_intro_animation()

    def cancel_capture(self) -> None:
        self.cancel_callback()
        self.releaseKeyboard()
        fade_window(self, self.windowOpacity(), 0.0, 90, on_finished=self._finish_hide)

    def _finish_hide(self) -> None:
        self.hide()
        self.setWindowOpacity(1.0)
        self._selection_rect = QRect()
        self._selection_global_rect = QRect()
        self._captured_bytes = None
        self._dragging = False
        self._text_only_mode = False
        self._intro_anchor = QPoint()
        self.composer.hide()
        self._reset_intro_state()

    def _handle_submit(self, question: str) -> None:
        if self._text_only_mode:
            error = self.submit_callback(None, question, QRect())
        else:
            if self._captured_bytes is None:
                self.composer.show_error("当前截图数据不可用，请重新框选")
                return
            error = self.submit_callback(self._captured_bytes, question, self._selection_global_rect)
        if error:
            self.composer.show_error(error)
            return
        self.releaseKeyboard()
        fade_window(self, self.windowOpacity(), 0.0, 110, on_finished=self._finish_hide)

    def _show_text_only_composer(self) -> None:
        self._text_only_mode = True
        self._selection_rect = QRect()
        self._selection_global_rect = QRect()
        self._captured_bytes = None
        self.releaseKeyboard()
        self.composer.present(QRect(), self.rect(), text_only=True, anchor_point=self._intro_anchor)
        QTimer.singleShot(0, self._focus_composer_editor)
        self.update()

    def _start_intro_animation(self) -> None:
        self._reset_intro_state()
        self.update()
        fade_window(self, 0.0, 1.0, 120)

        backdrop = QPropertyAnimation(self, b"backdropStrength", self)
        backdrop.setDuration(180)
        backdrop.setStartValue(0.0)
        backdrop.setEndValue(1.0)
        backdrop.setEasingCurve(QEasingCurve.Type.OutCubic)

        morph = QPropertyAnimation(self, b"introMorphProgress", self)
        morph.setDuration(520)
        morph.setStartValue(0.0)
        morph.setEndValue(1.0)
        morph.setEasingCurve(QEasingCurve.Type.OutCubic)

        label = QPropertyAnimation(self, b"introLabelOpacity", self)
        label.setDuration(180)
        label.setStartValue(0.0)
        label.setEndValue(1.0)
        label.setEasingCurve(QEasingCurve.Type.OutCubic)

        keep_animation(self, backdrop)
        keep_animation(self, morph)
        keep_animation(self, label)

        backdrop.start()
        QTimer.singleShot(50, morph.start)
        QTimer.singleShot(360, label.start)

    def getBackdropStrength(self) -> float:
        return self._backdrop_strength

    def setBackdropStrength(self, value: float) -> None:
        self._backdrop_strength = value
        self.update()

    def getIntroMorphProgress(self) -> float:
        return self._intro_morph_progress

    def setIntroMorphProgress(self, value: float) -> None:
        self._intro_morph_progress = value
        self.update()

    def getIntroLabelOpacity(self) -> float:
        return self._intro_label_opacity

    def setIntroLabelOpacity(self, value: float) -> None:
        self._intro_label_opacity = value
        self.update()

    backdropStrength = Property(float, getBackdropStrength, setBackdropStrength)
    introMorphProgress = Property(float, getIntroMorphProgress, setIntroMorphProgress)
    introLabelOpacity = Property(float, getIntroLabelOpacity, setIntroLabelOpacity)

    def mousePressEvent(self, event: QMouseEvent) -> None:  # type: ignore[override]
        if self.composer.isVisible():
            return
        if not self._supports_vision:
            return
        if event.button() == Qt.MouseButton.LeftButton:
            self._dragging = True
            self._text_only_mode = False
            self._drag_start = event.position().toPoint()
            self._drag_end = self._drag_start
            self._selection_rect = QRect()
            self.update()

    def mouseMoveEvent(self, event: QMouseEvent) -> None:  # type: ignore[override]
        if self._dragging:
            self._drag_end = event.position().toPoint()
            self._selection_rect = normalize_drag_rect(self._drag_start, self._drag_end)
            self.update()

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:  # type: ignore[override]
        if not self._dragging:
            return
        self._dragging = False
        self._drag_end = event.position().toPoint()
        self._selection_rect = normalize_drag_rect(self._drag_start, self._drag_end)
        if self._selection_rect.width() < 8 or self._selection_rect.height() < 8:
            self._selection_rect = QRect()
            self.update()
            return
        self._selection_global_rect = self._selection_rect.translated(self._virtual_rect.topLeft())
        try:
            self._captured_bytes = self.screenshot_service.grab_region(self._selection_global_rect)
        except Exception as exc:
            self.composer.show_error(f"截图失败：{exc}")
            return
        self._text_only_mode = False
        self.releaseKeyboard()
        self.composer.present(self._selection_rect, self.rect())
        QTimer.singleShot(0, self._focus_composer_editor)
        self.update()

    def keyPressEvent(self, event: QKeyEvent) -> None:  # type: ignore[override]
        if event.key() == Qt.Key.Key_Escape:
            self.cancel_capture()
            return
        if (
            event.key() in {Qt.Key.Key_Return, Qt.Key.Key_Enter}
            and not self.composer.isVisible()
            and self._selection_rect.isNull()
        ):
            self._show_text_only_composer()
            return
        super().keyPressEvent(event)

    def paintEvent(self, event) -> None:  # type: ignore[override]
        painter = QPainter(self)
        try:
            painter.setRenderHint(QPainter.RenderHint.Antialiasing)
            alpha = int(170 * self._backdrop_strength)
            painter.fillRect(self.rect(), QColor(3, 8, 12, alpha))

            if not self._selection_rect.isNull():
                path = QPainterPath()
                path.addRoundedRect(QRectF(self._selection_rect), 22, 22)
                painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_Clear)
                painter.fillPath(path, Qt.GlobalColor.transparent)
                painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceOver)

                glow_pen = QPen(QColor(138, 246, 255, 90), 8)
                painter.setPen(glow_pen)
                painter.drawRoundedRect(self._selection_rect.adjusted(-2, -2, 2, 2), 24, 24)

                border_pen = QPen(QColor(ACCENT), 3)
                painter.setPen(border_pen)
                painter.drawRoundedRect(self._selection_rect, 22, 22)

            if self._selection_rect.isNull() and not self.composer.isVisible():
                self._draw_intro(painter)

            super().paintEvent(event)
        finally:
            painter.end()

    def _draw_intro(self, painter: QPainter) -> None:
        center = self._intro_anchor if not self._intro_anchor.isNull() else self.rect().center()

        label_font = QFont(DISPLAY_FONT, 15)
        label_font.setWeight(QFont.Weight.Black)
        painter.setFont(label_font)
        label_width = max(260.0, min(420.0, float(painter.fontMetrics().horizontalAdvance(self._intro_message) + 92)))
        visual = _build_intro_visual_state(
            progress=self._intro_morph_progress,
            label_opacity=self._intro_label_opacity,
            label_width=label_width,
        )

        pill_rect = QRectF(
            center.x() - visual.width / 2.0,
            center.y() - visual.height / 2.0,
            visual.width,
            visual.height,
        )

        if visual.outer_alpha > 0 and visual.width > 1 and visual.height > 1:
            shadow_pen = QPen(QColor(0, 0, 0, min(90, visual.outer_alpha)), 3)
            painter.setPen(shadow_pen)
            painter.setBrush(QColor(255, 255, 255, visual.outer_alpha))
            painter.drawRoundedRect(pill_rect, visual.radius, visual.radius)

        if visual.dot_alpha > 0:
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor(255, 255, 255, visual.dot_alpha))
            painter.drawEllipse(
                QRectF(
                    center.x() - visual.dot_size / 2.0,
                    center.y() - visual.dot_size / 2.0,
                    visual.dot_size,
                    visual.dot_size,
                )
            )

        if visual.label_alpha > 0 and visual.width > 120:
            text_color = QColor(12, 12, 12)
            text_color.setAlpha(visual.label_alpha)
            painter.setPen(text_color)
            painter.setFont(label_font)
            painter.drawText(
                pill_rect.adjusted(24, 0, -24, 0),
                Qt.AlignmentFlag.AlignCenter,
                self._intro_message,
            )

    def _focus_composer_editor(self) -> None:
        if not self.composer.isVisible():
            return
        self.raise_()
        self.activateWindow()
        self.composer.raise_()
        self.composer.editor.setFocus(Qt.FocusReason.ActiveWindowFocusReason)
