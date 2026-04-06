from __future__ import annotations

from PySide6.QtCore import QRect, Qt, QTimer
from PySide6.QtGui import QColor, QPainter, QPainterPath, QPen, QRegion
from PySide6.QtWidgets import QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget

from screen_qa_assistant.ui.theme import (
    BODY_FONT,
    DISPLAY_FONT,
    ERROR,
    LIGHT_ACCENT,
    LIGHT_LINE,
    LIGHT_LINE_STRONG,
    LIGHT_MUTED,
    LIGHT_PANEL,
    LIGHT_PANEL_ALT,
    LIGHT_TEXT,
    clean_button_stylesheet,
    fade_window,
)


class LaunchPanel(QWidget):
    def __init__(self) -> None:
        super().__init__(None)
        self._auto_hide_timer = QTimer(self)
        self._auto_hide_timer.setSingleShot(True)
        self._auto_hide_timer.timeout.connect(self.hide_with_fade)

        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground, True)
        self.setWindowFlags(
            Qt.WindowType.Tool
            | Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
        )
        self.resize(420, 164)

        root = QVBoxLayout(self)
        root.setContentsMargins(18, 18, 18, 18)
        root.setSpacing(12)

        self.top_line = QWidget()
        self.top_line.setFixedHeight(3)
        self.top_line.setStyleSheet("background: #111111; border-radius: 2px;")
        root.addWidget(self.top_line)

        self.title_label = QLabel("截图问答助手已启动")
        self.title_label.setStyleSheet(
            f'color: {LIGHT_TEXT}; font-family: "{DISPLAY_FONT}"; font-size: 22px; font-weight: 700;'
        )
        root.addWidget(self.title_label)

        self.summary_label = QLabel("")
        self.summary_label.setWordWrap(True)
        self.summary_label.setStyleSheet(
            f'color: {LIGHT_MUTED}; font-family: "{BODY_FONT}"; font-size: 12px; line-height: 1.6;'
        )
        root.addWidget(self.summary_label)

        self.hint_label = QLabel("")
        self.hint_label.setVisible(False)
        root.addWidget(self.hint_label)

        buttons = QHBoxLayout()
        buttons.setSpacing(10)
        root.addLayout(buttons)

        self.capture_button = QPushButton("立即截图")
        self.capture_button.setStyleSheet(
            clean_button_stylesheet(
                fill=LIGHT_ACCENT,
                text=LIGHT_PANEL,
                border=LIGHT_ACCENT,
                hover_fill="#2A2A2A",
                pressed_fill="#000000",
            )
        )
        buttons.addWidget(self.capture_button)

        self.settings_button = QPushButton("打开设置")
        self.settings_button.setStyleSheet(
            clean_button_stylesheet(
                fill=LIGHT_PANEL,
                text=LIGHT_TEXT,
                border=LIGHT_LINE_STRONG,
                hover_fill="#FFFFFF",
            )
        )
        buttons.addWidget(self.settings_button)

        self.dismiss_button = QPushButton("知道了")
        self.dismiss_button.setStyleSheet(
            clean_button_stylesheet(
                fill=LIGHT_PANEL_ALT,
                text=LIGHT_TEXT,
                border=LIGHT_LINE,
                hover_fill="#FFFFFF",
            )
        )
        self.dismiss_button.clicked.connect(self.hide_with_fade)
        buttons.addWidget(self.dismiss_button)

        self._sync_rounded_mask()

    def present(self, hotkey: str, has_models: bool, auto_hide_ms: int = 4200) -> None:
        self._show_panel(
            title="截图问答助手已启动",
            summary=(
                f"按 {hotkey} 就能开始截图。"
                + (" 当前模型已就绪。" if has_models else " 当前还没有可用模型。")
            ),
            title_color=LIGHT_TEXT,
            auto_hide_ms=auto_hide_ms,
            capture_enabled=True,
        )

    def present_hotkey_error(self, hotkey: str, message: str, auto_hide_ms: int = 0) -> None:
        self._show_panel(
            title="快捷键暂时不可用",
            summary=f"{hotkey} 当前无法生效。{message}",
            title_color=ERROR,
            auto_hide_ms=auto_hide_ms,
            capture_enabled=True,
        )

    def summary_text(self) -> str:
        return self.summary_label.text()

    def hide_with_fade(self) -> None:
        self._auto_hide_timer.stop()
        if not self.isVisible():
            return

        def _hide() -> None:
            self.hide()
            self.setWindowOpacity(1.0)

        fade_window(self, self.windowOpacity(), 0.0, 110, on_finished=_hide)

    def _show_panel(
        self,
        *,
        title: str,
        summary: str,
        title_color: str,
        auto_hide_ms: int,
        capture_enabled: bool,
    ) -> None:
        self._auto_hide_timer.stop()
        self.title_label.setText(title)
        self.title_label.setStyleSheet(
            f'color: {title_color}; font-family: "{DISPLAY_FONT}"; font-size: 22px; font-weight: 700;'
        )
        self.summary_label.setText(summary)
        self.hint_label.hide()
        self.capture_button.setEnabled(capture_enabled)
        self._place_top_right()
        if not self.isVisible():
            self.show()
            fade_window(self, 0.0, 1.0, 140)
        else:
            self.raise_()
            self.activateWindow()
        if auto_hide_ms > 0:
            self._auto_hide_timer.start(auto_hide_ms)

    def _place_top_right(self) -> None:
        screen = self.screen()
        if screen is None and self.windowHandle() is not None:
            screen = self.windowHandle().screen()
        if screen is None:
            from PySide6.QtGui import QGuiApplication

            screen = QGuiApplication.primaryScreen()
        available = screen.availableGeometry() if screen is not None else QRect(0, 0, 1600, 900)
        margin = 26
        self.move(available.right() - self.width() - margin, available.top() + margin)

    def _sync_rounded_mask(self) -> None:
        path = QPainterPath()
        path.addRoundedRect(self.rect().adjusted(1, 1, -1, -1), 26, 26)
        self.setMask(QRegion(path.toFillPolygon().toPolygon()))

    def resizeEvent(self, event) -> None:  # type: ignore[override]
        self._sync_rounded_mask()
        super().resizeEvent(event)

    def paintEvent(self, event) -> None:  # type: ignore[override]
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_Source)
        painter.fillRect(self.rect(), Qt.GlobalColor.transparent)
        painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceOver)
        rect = self.rect().adjusted(2, 2, -2, -2)

        shadow = QColor("#000000")
        shadow.setAlpha(20)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(shadow)
        painter.drawRoundedRect(rect.adjusted(0, 6, 0, 6), 26, 26)

        painter.setBrush(QColor(LIGHT_PANEL))
        painter.setPen(QPen(QColor(LIGHT_LINE), 1))
        painter.drawRoundedRect(rect, 26, 26)

        painter.setPen(QPen(QColor(255, 255, 255, 150), 1))
        painter.drawRoundedRect(rect.adjusted(1, 1, -1, -1), 25, 25)
