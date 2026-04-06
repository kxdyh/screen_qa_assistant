from __future__ import annotations

from dataclasses import dataclass
from enum import IntFlag

from PySide6.QtCore import (
    QEasingCurve,
    Property,
    QEvent,
    QPoint,
    QPointF,
    QPropertyAnimation,
    QRect,
    QSize,
    Qt,
    QTimer,
    Signal,
)
from PySide6.QtGui import (
    QColor,
    QMouseEvent,
    QPainter,
    QPainterPath,
    QPen,
    QPixmap,
    QRegion,
    QResizeEvent,
    QShowEvent,
    QTextCursor,
)
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from screen_qa_assistant.ui.theme import (
    BODY_FONT,
    DISPLAY_FONT,
    LIGHT_ACCENT,
    LIGHT_LINE,
    LIGHT_LINE_STRONG,
    LIGHT_MUTED,
    LIGHT_PANEL,
    LIGHT_PANEL_ALT,
    LIGHT_SOFT_ACCENT,
    LIGHT_TEXT,
    fade_widget,
    fade_window,
    keep_animation,
)
from screen_qa_assistant.ui.tray_icon import build_tray_icon_pixmap


class ResizeEdge(IntFlag):
    NONE = 0
    LEFT = 1
    TOP = 2
    RIGHT = 4
    BOTTOM = 8


@dataclass(frozen=True)
class FontPreset:
    title_size: int
    status_size: int
    body_size: int
    input_size: int
    button_size: int
    width_scale: float
    expanded_scale: float
    compact_scale: float


FONT_PRESETS: dict[str, FontPreset] = {
    "small": FontPreset(18, 11, 13, 12, 12, 1.0, 1.0, 1.0),
    "medium": FontPreset(20, 12, 15, 13, 13, 1.12, 1.14, 1.1),
    "large": FontPreset(22, 13, 17, 15, 14, 1.26, 1.3, 1.18),
}


def compute_resized_geometry(
    start_rect: QRect,
    edges: ResizeEdge,
    delta: QPoint,
    *,
    minimum_size: QSize,
) -> QRect:
    x = start_rect.x()
    y = start_rect.y()
    width = start_rect.width()
    height = start_rect.height()
    min_width = minimum_size.width()
    min_height = minimum_size.height()

    if edges & ResizeEdge.LEFT:
        new_x = min(x + delta.x(), x + width - min_width)
        width += x - new_x
        x = new_x
    if edges & ResizeEdge.RIGHT:
        width = max(min_width, width + delta.x())
    if edges & ResizeEdge.TOP:
        new_y = min(y + delta.y(), y + height - min_height)
        height += y - new_y
        y = new_y
    if edges & ResizeEdge.BOTTOM:
        height = max(min_height, height + delta.y())

    return QRect(x, y, width, height)


class _LoadingLine(QWidget):
    def __init__(self, owner: "AnswerWindow") -> None:
        super().__init__(owner)
        self._owner = owner
        self.setFixedHeight(12)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)

    def paintEvent(self, event) -> None:  # type: ignore[override]
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        line_rect = self.rect().adjusted(6, 4, -6, -4)
        center_y = line_rect.center().y()

        base_pen = QPen(QColor(LIGHT_LINE), 2)
        base_pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        painter.setPen(base_pen)
        painter.drawLine(line_rect.left(), center_y, line_rect.right(), center_y)

        if not self._owner._working:
            return

        segment_width = min(120, max(72, self.width() // 4))
        segment_height = 3
        left = int(self._owner._line_offset)
        highlight_rect = QRect(left, center_y - 1, segment_width, segment_height)

        for alpha, inset in ((180, 0), (110, 14), (60, 28)):
            glow = highlight_rect.adjusted(inset, 0, -inset, 0)
            if glow.width() <= 0:
                continue
            painter.setPen(Qt.PenStyle.NoPen)
            color = QColor(LIGHT_ACCENT)
            color.setAlpha(alpha)
            painter.setBrush(color)
            painter.drawRoundedRect(glow, 2, 2)


class AnswerWindow(QWidget):
    stop_requested = Signal()
    retry_requested = Signal()
    followup_submitted = Signal(str)
    closed_manually = Signal()
    icon_menu_requested = Signal(QPoint)

    def __init__(self, window_prefs: dict | None = None) -> None:
        super().__init__(None)
        prefs = window_prefs or {}
        self._base_width = int(prefs.get("width", 420))
        self._base_expanded_height = int(prefs.get("height", 420))
        self._base_compact_height = 112
        self._preferred_width = self._base_width
        self._expanded_height = self._base_expanded_height
        self._compact_height = self._base_compact_height
        self._icon_size = 92
        self._is_expanded = False
        self._is_iconified = False
        self._last_non_icon_mode = "expanded"
        self._working = False
        self._pending_question: str | None = None
        self._turn_open = False
        self._header_drag_height = 68
        self._drag_active = False
        self._drag_offset = QPoint()
        self._drag_start_global = QPoint()
        self._icon_click_pending = False
        self._font_scale = "small"
        self._line_offset = -120.0
        self._edge_resize_margin = 5
        self._corner_resize_margin = 18
        self._active_resize_edges = ResizeEdge.NONE
        self._resize_start_rect = QRect()
        self._resize_start_global = QPoint()
        self._icon_glyph_opacity = 0.0
        self._icon_pixmap = QPixmap()

        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground, True)
        self.setWindowFlags(
            Qt.WindowType.Tool
            | Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
        )
        self.setMouseTracking(True)
        self.resize(self._preferred_width, self._compact_height)

        self._line_timer = QTimer(self)
        self._line_timer.setInterval(26)
        self._line_timer.timeout.connect(self._advance_loading_line)

        root = QVBoxLayout(self)
        root.setContentsMargins(16, 16, 16, 16)
        root.setSpacing(12)

        self.header_frame = QFrame()
        self.header_frame.setObjectName("answerHeader")
        header = QHBoxLayout(self.header_frame)
        header.setContentsMargins(0, 0, 0, 0)
        header.setSpacing(10)
        root.addWidget(self.header_frame)

        title_box = QVBoxLayout()
        title_box.setSpacing(2)
        header.addLayout(title_box, 1)

        self.provider_label = QLabel("Assistant")
        self.provider_label.setStyleSheet(
            f'color: {LIGHT_TEXT}; font-family: "{DISPLAY_FONT}"; font-size: 18px; font-weight: 700;'
        )
        title_box.addWidget(self.provider_label)

        self.status_label = QLabel("已完成")
        self.status_label.setStyleSheet(
            f'color: {LIGHT_MUTED}; font-family: "{BODY_FONT}"; font-size: 11px;'
        )
        title_box.addWidget(self.status_label)

        self.stop_button = QPushButton("停止")
        self.stop_button.clicked.connect(self.stop_requested.emit)
        header.addWidget(self.stop_button)

        self.retry_button = QPushButton("重试")
        self.retry_button.clicked.connect(self.retry_requested.emit)
        header.addWidget(self.retry_button)

        font_box = QHBoxLayout()
        font_box.setSpacing(6)
        header.addLayout(font_box)

        self.font_small_button = QPushButton("小")
        self.font_small_button.clicked.connect(lambda: self.set_font_scale("small"))
        font_box.addWidget(self.font_small_button)

        self.font_medium_button = QPushButton("中")
        self.font_medium_button.clicked.connect(lambda: self.set_font_scale("medium"))
        font_box.addWidget(self.font_medium_button)

        self.font_large_button = QPushButton("大")
        self.font_large_button.clicked.connect(lambda: self.set_font_scale("large"))
        font_box.addWidget(self.font_large_button)

        self.close_button = QPushButton("收起")
        self.close_button.clicked.connect(lambda: self.set_iconified(True))
        header.addWidget(self.close_button)

        self.loading_line = _LoadingLine(self)
        root.addWidget(self.loading_line)

        self.content_frame = QFrame()
        self.content_frame.setStyleSheet("background: transparent; border: none;")
        content_layout = QVBoxLayout(self.content_frame)
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(12)
        root.addWidget(self.content_frame, 1)

        self.transcript_edit = QPlainTextEdit()
        self.transcript_edit.setReadOnly(True)
        self.transcript_edit.setStyleSheet(
            f"""
            QPlainTextEdit {{
                background: rgba(255, 255, 255, 0.92);
                border: 1px solid {LIGHT_LINE};
                border-radius: 22px;
                color: {LIGHT_TEXT};
                padding: 16px;
                font-family: "{BODY_FONT}";
                font-size: 13px;
                line-height: 1.7;
                selection-background-color: {LIGHT_SOFT_ACCENT};
            }}
            """
        )
        content_layout.addWidget(self.transcript_edit, 1)

        followup_row = QHBoxLayout()
        followup_row.setSpacing(10)
        content_layout.addLayout(followup_row)

        self.followup_input = QLineEdit()
        self.followup_input.setPlaceholderText("继续围绕当前截图追问")
        self.followup_input.setStyleSheet(
            f"""
            QLineEdit {{
                background: rgba(255, 255, 255, 0.98);
                border: 2px solid {LIGHT_LINE};
                border-radius: 20px;
                color: {LIGHT_TEXT};
                padding: 10px 14px;
                font-family: "{BODY_FONT}";
                font-size: 12px;
            }}
            QLineEdit:focus {{
                border-color: {LIGHT_LINE_STRONG};
            }}
            """
        )
        self.followup_input.returnPressed.connect(self._submit_followup)
        followup_row.addWidget(self.followup_input, 1)

        self.followup_button = QPushButton("发送")
        self.followup_button.clicked.connect(self._submit_followup)
        followup_row.addWidget(self.followup_button)

        self.stop_button.setEnabled(False)
        self.content_frame.hide()
        self.header_frame.installEventFilter(self)
        self.provider_label.installEventFilter(self)
        self.status_label.installEventFilter(self)
        self._apply_font_scale_metrics(animate=False)
        self._apply_icon_glyph_opacity(0.0)
        self._sync_rounded_mask()

    @property
    def is_expanded(self) -> bool:
        return self._is_expanded

    @property
    def is_iconified(self) -> bool:
        return self._is_iconified

    @property
    def current_font_scale(self) -> str:
        return self._font_scale

    def transcript_text(self) -> str:
        return self.transcript_edit.toPlainText()

    def set_font_scale(self, scale: str, *, animate: bool = True) -> None:
        if scale not in FONT_PRESETS or scale == self._font_scale:
            return

        previous_scale = self._font_scale
        old_width, old_expanded, old_compact = self._scaled_base_dimensions(previous_scale)
        width_ratio = self._preferred_width / max(1, old_width)
        expanded_ratio = self._expanded_height / max(1, old_expanded)
        compact_ratio = self._compact_height / max(1, old_compact)

        self._font_scale = scale
        new_width, new_expanded, new_compact = self._scaled_base_dimensions(scale)
        self._preferred_width = max(self._minimum_window_size("expanded").width(), int(new_width * max(1.0, width_ratio)))
        self._expanded_height = max(
            self._minimum_window_size("expanded").height(),
            int(new_expanded * max(1.0, expanded_ratio)),
        )
        self._compact_height = max(
            self._minimum_window_size("compact").height(),
            int(new_compact * max(1.0, compact_ratio)),
        )
        self._apply_font_scale_metrics(animate=animate)

    def set_iconified(self, enabled: bool, *, animate: bool = True) -> None:
        if enabled == self._is_iconified:
            return
        if enabled:
            self._last_non_icon_mode = "expanded" if self._is_expanded else "compact"
            self._enter_iconified_mode(animate=animate)
        else:
            self._exit_iconified_mode(animate=animate)

    def queue_turn(
        self,
        provider_name: str,
        question: str,
        collapse: bool = False,
        reset: bool = False,
        input_mode: str = "vision",
    ) -> None:
        self.provider_label.setText(provider_name)
        self.status_label.setText("处理中")
        self.followup_input.setPlaceholderText(
            "继续围绕当前截图追问" if input_mode == "vision" else "继续围绕当前问题追问"
        )
        self._pending_question = question
        self._turn_open = False
        self._working = True
        self._line_offset = -120.0
        self.stop_button.setEnabled(True)
        self.retry_button.setEnabled(True)
        self._line_timer.start()
        self.loading_line.update()
        if self._is_iconified:
            self.set_iconified(False, animate=False)
        if reset:
            self.transcript_edit.clear()
        if collapse:
            self._collapse()
        else:
            self._expand()
        self._show_window()

    def _button_style(
        self,
        *,
        fill: str,
        border: str,
        text: str,
        hover_fill: str,
        pressed_fill: str,
        font_size: int,
    ) -> str:
        return f"""
        QPushButton {{
            color: {text};
            background: {fill};
            border: 1px solid {border};
            border-radius: 16px;
            padding: 8px 12px;
            font-family: "{BODY_FONT}";
            font-size: {font_size}px;
            font-weight: 700;
        }}
        QPushButton:hover {{
            background: {hover_fill};
            border-color: {border};
        }}
        QPushButton:pressed {{
            background: {pressed_fill};
            color: {LIGHT_PANEL};
            border-color: {pressed_fill};
        }}
        """

    def _scaled_base_dimensions(self, scale: str) -> tuple[int, int, int]:
        profile = FONT_PRESETS[scale]
        return (
            int(self._base_width * profile.width_scale),
            int(self._base_expanded_height * profile.expanded_scale),
            int(self._base_compact_height * profile.compact_scale),
        )

    def _minimum_window_size(self, mode: str) -> QSize:
        base_width, base_expanded, base_compact = self._scaled_base_dimensions(self._font_scale)
        if mode == "icon":
            return QSize(self._icon_size, self._icon_size)
        if mode == "compact":
            return QSize(max(300, int(base_width * 0.72)), max(108, int(base_compact * 0.96)))
        return QSize(max(320, int(base_width * 0.76)), max(220, int(base_expanded * 0.56)))

    def _apply_font_scale_metrics(self, *, animate: bool) -> None:
        profile = FONT_PRESETS[self._font_scale]

        self.provider_label.setStyleSheet(
            f'color: {LIGHT_TEXT}; font-family: "{DISPLAY_FONT}"; font-size: {profile.title_size}px; font-weight: 700;'
        )
        self.status_label.setStyleSheet(
            f'color: {LIGHT_MUTED}; font-family: "{BODY_FONT}"; font-size: {profile.status_size}px;'
        )
        self.transcript_edit.setStyleSheet(
            f"""
            QPlainTextEdit {{
                background: rgba(255, 255, 255, 0.92);
                border: 1px solid {LIGHT_LINE};
                border-radius: 22px;
                color: {LIGHT_TEXT};
                padding: 16px;
                font-family: "{BODY_FONT}";
                font-size: {profile.body_size}px;
                selection-background-color: {LIGHT_SOFT_ACCENT};
            }}
            """
        )
        self.followup_input.setStyleSheet(
            f"""
            QLineEdit {{
                background: rgba(255, 255, 255, 0.98);
                border: 2px solid {LIGHT_LINE};
                border-radius: 20px;
                color: {LIGHT_TEXT};
                padding: 10px 14px;
                font-family: "{BODY_FONT}";
                font-size: {profile.input_size}px;
            }}
            QLineEdit:focus {{
                border-color: {LIGHT_LINE_STRONG};
            }}
            """
        )

        neutral_button_style = self._button_style(
            fill=LIGHT_PANEL_ALT,
            border=LIGHT_LINE,
            text=LIGHT_TEXT,
            hover_fill="#FFFFFF",
            pressed_fill=LIGHT_ACCENT,
            font_size=profile.button_size,
        )
        accent_button_style = self._button_style(
            fill=LIGHT_PANEL,
            border=LIGHT_LINE_STRONG,
            text=LIGHT_TEXT,
            hover_fill="#FFFFFF",
            pressed_fill=LIGHT_ACCENT,
            font_size=profile.button_size,
        )
        send_button_style = self._button_style(
            fill=LIGHT_ACCENT,
            border=LIGHT_ACCENT,
            text=LIGHT_PANEL,
            hover_fill="#2A2A2A",
            pressed_fill="#000000",
            font_size=profile.button_size,
        )

        self.stop_button.setStyleSheet(neutral_button_style)
        self.retry_button.setStyleSheet(accent_button_style)
        self.close_button.setStyleSheet(neutral_button_style)
        self.followup_button.setStyleSheet(send_button_style)

        for key, button in {
            "small": self.font_small_button,
            "medium": self.font_medium_button,
            "large": self.font_large_button,
        }.items():
            button.setFixedWidth(42)
            if key == self._font_scale:
                button.setStyleSheet(send_button_style)
            else:
                button.setStyleSheet(neutral_button_style)

        self.followup_input.setMinimumHeight(max(42, 36 + profile.input_size // 2))
        for button in (
            self.stop_button,
            self.retry_button,
            self.close_button,
            self.followup_button,
            self.font_small_button,
            self.font_medium_button,
            self.font_large_button,
        ):
            button.setMinimumHeight(max(38, 30 + profile.button_size // 2))

        if self._is_iconified:
            return

        target_mode = "expanded" if self._is_expanded else "compact"
        target_rect = self._target_mode_rect(target_mode)
        if animate and self.isVisible():
            fade_widget(self.header_frame, 0.65, 1.0, 120)
            if self.content_frame.isVisible():
                fade_widget(self.content_frame, 0.45, 1.0, 150)
            self._animate_geometry(target_rect)
        elif self.isVisible():
            self.setGeometry(target_rect)
            self._sync_rounded_mask()

    def getIconGlyphOpacity(self) -> float:
        return self._icon_glyph_opacity

    def setIconGlyphOpacity(self, value: float) -> None:
        self._apply_icon_glyph_opacity(float(value))

    iconGlyphOpacity = Property(float, getIconGlyphOpacity, setIconGlyphOpacity)

    def _apply_icon_glyph_opacity(self, value: float) -> None:
        self._icon_glyph_opacity = max(0.0, min(1.0, float(value)))
        self.update()

    def _set_chrome_visible(self, visible: bool) -> None:
        self.header_frame.setVisible(visible)
        self.loading_line.setVisible(visible)
        self.content_frame.setVisible(visible and self._is_expanded)

    def _animate_icon_glyph(self, start: float, end: float, duration: int) -> None:
        animation = QPropertyAnimation(self, b"iconGlyphOpacity", self)
        animation.setDuration(duration)
        animation.setStartValue(start)
        animation.setEndValue(end)
        animation.setEasingCurve(QEasingCurve.Type.OutCubic)
        keep_animation(self, animation)
        animation.start()

    def _animate_chrome_fade(self, start: float, end: float, duration: int) -> None:
        fade_widget(self.header_frame, start, end, duration)
        fade_widget(self.loading_line, start, end, duration)
        if self._is_expanded or end > 0:
            self.content_frame.show()
            fade_widget(self.content_frame, start, end, duration)

    def _enter_iconified_mode(self, *, animate: bool) -> None:
        self._is_iconified = True
        self._drag_active = False
        self._active_resize_edges = ResizeEdge.NONE
        target = self._icon_target_rect()
        if not animate or not self.isVisible():
            self._set_chrome_visible(False)
            self.setGeometry(target)
            self._apply_icon_glyph_opacity(1.0)
            self.show()
            self.raise_()
            self.activateWindow()
            return

        self._animate_chrome_fade(1.0, 0.0, 120)
        self._animate_geometry(target, duration=180)
        QTimer.singleShot(115, lambda: self._set_chrome_visible(False))
        QTimer.singleShot(120, lambda: self._animate_icon_glyph(0.0, 1.0, 110))

    def _exit_iconified_mode(self, *, animate: bool) -> None:
        self._is_iconified = False
        target = self._target_mode_rect(self._last_non_icon_mode)
        self._set_chrome_visible(True)
        if not self._is_expanded:
            self.content_frame.hide()
        if not animate or not self.isVisible():
            self._apply_icon_glyph_opacity(0.0)
            self.setGeometry(target)
            self._sync_rounded_mask()
            return

        self._animate_icon_glyph(1.0, 0.0, 90)
        self._animate_geometry(target, duration=180)
        self._animate_chrome_fade(0.0, 1.0, 150)

    def append_chunk(self, text: str) -> None:
        self._ensure_turn_started()
        cursor = self.transcript_edit.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)
        cursor.insertText(text)
        self.transcript_edit.setTextCursor(cursor)

    def append_error(self, message: str) -> None:
        self._ensure_turn_started()
        cursor = self.transcript_edit.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)
        cursor.insertText(f"\n[错误] {message}")
        self.transcript_edit.setTextCursor(cursor)
        self.status_label.setText("请求失败")
        self._working = False
        self._line_timer.stop()
        self.loading_line.update()

    def append_system_message(self, message: str) -> None:
        cursor = self.transcript_edit.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)
        if self.transcript_edit.toPlainText():
            cursor.insertText("\n")
        cursor.insertText(f"[系统] {message}\n")
        self.transcript_edit.setTextCursor(cursor)
        self._expand()

    def finish_turn(self, status_text: str) -> None:
        if self._turn_open:
            cursor = self.transcript_edit.textCursor()
            cursor.movePosition(QTextCursor.MoveOperation.End)
            cursor.insertText("\n\n")
            self.transcript_edit.setTextCursor(cursor)
        self._turn_open = False
        self._working = False
        self.status_label.setText(status_text)
        self._line_timer.stop()
        self.stop_button.setEnabled(False)
        self.loading_line.update()

    def eventFilter(self, watched, event) -> bool:  # type: ignore[override]
        drag_widgets = {
            getattr(self, "header_frame", None),
            getattr(self, "provider_label", None),
            getattr(self, "status_label", None),
        }
        if watched in drag_widgets and isinstance(event, QMouseEvent):
            if event.type() == QEvent.Type.MouseButtonPress:
                self._try_begin_header_drag(event)
                return event.isAccepted()
            if event.type() == QEvent.Type.MouseMove:
                self._move_drag(event)
                return event.isAccepted()
            if event.type() == QEvent.Type.MouseButtonRelease:
                self._end_drag(event)
                return event.isAccepted()
        return super().eventFilter(watched, event)

    def mousePressEvent(self, event: QMouseEvent) -> None:  # type: ignore[override]
        if self._is_iconified and event.button() == Qt.MouseButton.RightButton:
            self.icon_menu_requested.emit(event.globalPosition().toPoint())
            event.accept()
            return
        self._try_begin_drag(event)
        if not event.isAccepted():
            super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QMouseEvent) -> None:  # type: ignore[override]
        self._move_drag(event)
        if not event.isAccepted():
            super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:  # type: ignore[override]
        self._end_drag(event)
        if not event.isAccepted():
            super().mouseReleaseEvent(event)

    def _submit_followup(self) -> None:
        text = self.followup_input.text().strip()
        if not text:
            return
        self.followup_input.clear()
        self.followup_submitted.emit(text)

    def _show_window(self) -> None:
        target = self._target_mode_rect("expanded" if self._is_expanded else "compact")
        if not self.isVisible():
            self.setGeometry(target)
            self.show()
            fade_window(self, 0.0, 1.0, 140)
        else:
            self.raise_()
            self.activateWindow()
            self._animate_geometry(target, duration=150)

    def _collapse(self) -> None:
        self._is_expanded = False
        self._last_non_icon_mode = "compact"
        if self._is_iconified:
            return
        if self.content_frame.isVisible():
            fade_widget(self.content_frame, 1.0, 0.0, 90, on_finished=self.content_frame.hide)
        else:
            self.content_frame.hide()
        self._animate_geometry(self._target_mode_rect("compact"))

    def _expand(self) -> None:
        self._is_expanded = True
        self._last_non_icon_mode = "expanded"
        if self._is_iconified:
            return
        self.content_frame.show()
        fade_widget(self.content_frame, 0.0, 1.0, 140)
        self._animate_geometry(self._target_mode_rect("expanded"))

    def _ensure_turn_started(self) -> None:
        if not self._is_expanded:
            self._expand()
        if self._pending_question is None:
            return
        cursor = self.transcript_edit.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)
        if self.transcript_edit.toPlainText():
            cursor.insertText("\n")
        cursor.insertText(f"你：{self._pending_question}\nAI：")
        self.transcript_edit.setTextCursor(cursor)
        self._pending_question = None
        self._turn_open = True

    def _screen_available_geometry(self) -> QRect:
        screen = self.screen()
        if screen is None and self.windowHandle() is not None:
            screen = self.windowHandle().screen()
        if screen is None:
            from PySide6.QtGui import QGuiApplication

            screen = QGuiApplication.primaryScreen()
        return screen.availableGeometry() if screen is not None else QRect(0, 0, 1600, 900)

    def _anchor_rect(self, size: QSize) -> QRect:
        available = self._screen_available_geometry()
        margin = 24
        x = available.right() - size.width() - margin
        y = available.top() + margin
        return QRect(x, y, size.width(), size.height())

    def _clamp_rect_to_screen(self, rect: QRect) -> QRect:
        available = self._screen_available_geometry()
        x = min(max(rect.x(), available.left()), available.right() - rect.width())
        y = min(max(rect.y(), available.top()), available.bottom() - rect.height())
        return QRect(x, y, rect.width(), rect.height())

    def _target_mode_rect(self, mode: str) -> QRect:
        if mode == "icon":
            return self._icon_target_rect()
        height = self._expanded_height if mode == "expanded" else self._compact_height
        width = self._preferred_width
        size = QSize(width, height)
        if not self.isVisible():
            return self._anchor_rect(size)

        current = self.geometry()
        if self._is_iconified:
            rect = QRect(0, 0, size.width(), size.height())
            rect.moveCenter(current.center())
            return self._clamp_rect_to_screen(rect)
        return self._clamp_rect_to_screen(QRect(current.x(), current.y(), size.width(), size.height()))

    def _icon_target_rect(self) -> QRect:
        size = QSize(self._icon_size, self._icon_size)
        if not self.isVisible():
            return self._anchor_rect(size)
        rect = QRect(0, 0, size.width(), size.height())
        rect.moveCenter(self.geometry().center())
        return self._clamp_rect_to_screen(rect)

    def _animate_geometry(self, target: QRect, *, duration: int = 180) -> None:
        animation = QPropertyAnimation(self, b"geometry", self)
        animation.setDuration(duration)
        animation.setStartValue(self.geometry() if self.isVisible() else target)
        animation.setEndValue(target)
        animation.setEasingCurve(QEasingCurve.Type.OutCubic)
        keep_animation(self, animation)
        animation.start()

    def _advance_loading_line(self) -> None:
        self._line_offset += 16
        cycle_width = self.loading_line.width() + 120
        if self._line_offset > cycle_width:
            self._line_offset = -120.0
        self.loading_line.update()

    def _hit_resize_edges(self, position: QPointF) -> ResizeEdge:
        if self._is_iconified:
            return ResizeEdge.NONE
        x = position.x()
        y = position.y()
        width = self.width()
        height = self.height()
        edge_margin = self._edge_resize_margin
        corner_margin = self._corner_resize_margin

        in_left_corner = x <= corner_margin
        in_right_corner = x >= width - corner_margin
        in_top_corner = y <= corner_margin
        in_bottom_corner = y >= height - corner_margin

        if in_left_corner and in_top_corner:
            return ResizeEdge.LEFT | ResizeEdge.TOP
        if in_right_corner and in_top_corner:
            return ResizeEdge.RIGHT | ResizeEdge.TOP
        if in_left_corner and in_bottom_corner:
            return ResizeEdge.LEFT | ResizeEdge.BOTTOM
        if in_right_corner and in_bottom_corner:
            return ResizeEdge.RIGHT | ResizeEdge.BOTTOM

        if x <= edge_margin:
            return ResizeEdge.LEFT
        if x >= width - edge_margin:
            return ResizeEdge.RIGHT
        if y >= height - edge_margin:
            return ResizeEdge.BOTTOM
        return ResizeEdge.NONE

    def _cursor_for_edges(self, edges: ResizeEdge):
        if edges in (ResizeEdge.LEFT, ResizeEdge.RIGHT):
            return Qt.CursorShape.SizeHorCursor
        if edges in (ResizeEdge.TOP, ResizeEdge.BOTTOM):
            return Qt.CursorShape.SizeVerCursor
        if edges in (ResizeEdge.LEFT | ResizeEdge.TOP, ResizeEdge.RIGHT | ResizeEdge.BOTTOM):
            return Qt.CursorShape.SizeFDiagCursor
        if edges in (ResizeEdge.RIGHT | ResizeEdge.TOP, ResizeEdge.LEFT | ResizeEdge.BOTTOM):
            return Qt.CursorShape.SizeBDiagCursor
        return Qt.CursorShape.ArrowCursor

    def _begin_resize(self, event: QMouseEvent, edges: ResizeEdge) -> None:
        self._active_resize_edges = edges
        self._resize_start_rect = self.geometry()
        self._resize_start_global = event.globalPosition().toPoint()
        self.setCursor(self._cursor_for_edges(edges))
        event.accept()

    def _start_window_drag(self, global_pos: QPoint, *, icon_click: bool = False) -> None:
        self._drag_active = True
        self._drag_offset = global_pos - self.frameGeometry().topLeft()
        self._drag_start_global = global_pos
        self._icon_click_pending = icon_click

    def _try_begin_header_drag(self, event: QMouseEvent) -> None:
        if event.button() != Qt.MouseButton.LeftButton:
            return
        self._start_window_drag(event.globalPosition().toPoint(), icon_click=self._is_iconified)
        event.accept()

    def _perform_resize(self, event: QMouseEvent) -> None:
        if self._active_resize_edges == ResizeEdge.NONE:
            return
        mode = "expanded" if self._is_expanded else "compact"
        delta = event.globalPosition().toPoint() - self._resize_start_global
        target = compute_resized_geometry(
            self._resize_start_rect,
            self._active_resize_edges,
            delta,
            minimum_size=self._minimum_window_size(mode),
        )
        self.setGeometry(self._clamp_rect_to_screen(target))
        event.accept()

    def _end_resize(self, event: QMouseEvent) -> None:
        if self._active_resize_edges == ResizeEdge.NONE:
            return
        self._preferred_width = self.width()
        if self._is_expanded:
            self._expanded_height = self.height()
        else:
            self._compact_height = self.height()
        self._active_resize_edges = ResizeEdge.NONE
        self.setCursor(Qt.CursorShape.ArrowCursor)
        event.accept()

    def _try_begin_drag(self, event: QMouseEvent) -> None:
        if event.button() != Qt.MouseButton.LeftButton:
            return

        if self._is_iconified:
            self._start_window_drag(event.globalPosition().toPoint(), icon_click=True)
            event.accept()
            return

        edges = self._hit_resize_edges(event.position())
        if edges != ResizeEdge.NONE:
            self._begin_resize(event, edges)
            return

        if event.position().y() > self._header_drag_height:
            return
        self._start_window_drag(event.globalPosition().toPoint())
        event.accept()

    def _move_drag(self, event: QMouseEvent) -> None:
        if self._active_resize_edges != ResizeEdge.NONE:
            self._perform_resize(event)
            return

        if self._drag_active:
            self.move(event.globalPosition().toPoint() - self._drag_offset)
            if self._is_iconified and (
                event.globalPosition().toPoint() - self._drag_start_global
            ).manhattanLength() > 6:
                self._icon_click_pending = False
            event.accept()
            return

        if self._is_iconified:
            self.setCursor(Qt.CursorShape.OpenHandCursor)
            return

        edges = self._hit_resize_edges(event.position())
        self.setCursor(self._cursor_for_edges(edges))
        if edges != ResizeEdge.NONE:
            event.accept()

    def _end_drag(self, event: QMouseEvent) -> None:
        if self._active_resize_edges != ResizeEdge.NONE:
            self._end_resize(event)
            return

        if not self._drag_active:
            if not self._is_iconified:
                self.setCursor(Qt.CursorShape.ArrowCursor)
            return
        self._drag_active = False
        self.move(self._clamp_rect_to_screen(QRect(self.pos(), self.size())).topLeft())
        if self._is_iconified:
            self.setCursor(Qt.CursorShape.OpenHandCursor)
            should_restore = self._icon_click_pending and (
                event.globalPosition().toPoint() - self._drag_start_global
            ).manhattanLength() <= 6
            self._icon_click_pending = False
            if should_restore:
                self.set_iconified(False)
        else:
            self.setCursor(Qt.CursorShape.ArrowCursor)
        event.accept()

    def _sync_rounded_mask(self) -> None:
        path = QPainterPath()
        rounded_rect = self.rect().adjusted(1, 1, -1, -1)
        radius = 26 if self._is_iconified else 28
        path.addRoundedRect(rounded_rect, radius, radius)
        self.setMask(QRegion(path.toFillPolygon().toPolygon()))

    def resizeEvent(self, event: QResizeEvent) -> None:  # type: ignore[override]
        self._sync_rounded_mask()
        super().resizeEvent(event)

    def showEvent(self, event: QShowEvent) -> None:  # type: ignore[override]
        self._sync_rounded_mask()
        super().showEvent(event)

    def paintEvent(self, event) -> None:  # type: ignore[override]
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_Source)
        painter.fillRect(self.rect(), Qt.GlobalColor.transparent)
        painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceOver)
        rect = self.rect().adjusted(2, 2, -2, -2)
        radius = 26 if self._is_iconified else 28

        if not self._is_iconified:
            shadow_color = QColor("#000000")
            shadow_color.setAlpha(22)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(shadow_color)
            painter.drawRoundedRect(rect.adjusted(0, 6, 0, 6), radius, radius)

        painter.setBrush(QColor(LIGHT_PANEL))
        painter.setPen(QPen(QColor(LIGHT_LINE), 1))
        painter.drawRoundedRect(rect, radius, radius)

        painter.setPen(QPen(QColor(255, 255, 255, 140), 1))
        painter.drawRoundedRect(rect.adjusted(1, 1, -1, -1), max(0, radius - 1), max(0, radius - 1))

        if self._icon_glyph_opacity > 0.0:
            painter.save()
            painter.setOpacity(self._icon_glyph_opacity)
            if self._icon_pixmap.isNull():
                self._icon_pixmap = build_tray_icon_pixmap(52)
            target_size = min(56, min(self.width(), self.height()) - 22)
            pixmap = self._icon_pixmap.scaled(
                target_size,
                target_size,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
            x = (self.width() - pixmap.width()) // 2
            y = (self.height() - pixmap.height()) // 2
            painter.drawPixmap(x, y, pixmap)
            painter.restore()

    def closeEvent(self, event) -> None:  # type: ignore[override]
        event.ignore()

        def _hide() -> None:
            self.hide()
            self._working = False
            self._line_timer.stop()
            self.loading_line.update()
            self.closed_manually.emit()
            self.setWindowOpacity(1.0)

        fade_window(self, self.windowOpacity(), 0.0, 110, on_finished=_hide)
