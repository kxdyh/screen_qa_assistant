from __future__ import annotations

from collections.abc import Callable

from PySide6.QtCore import QEasingCurve, QPropertyAnimation
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QComboBox,
    QGraphicsDropShadowEffect,
    QGraphicsOpacityEffect,
    QListView,
    QWidget,
)


DISPLAY_FONT = "Bahnschrift"
BODY_FONT = "Microsoft YaHei UI"
PANEL_BG = "#08131C"
PANEL_ALT = "#0B1B26"
PANEL_SOFT = "#102430"
TEXT = "#E9FDFF"
MUTED = "#95C9D2"
ACCENT = "#8AF6FF"
ACCENT_SOFT = "#204554"
SUCCESS = "#7AF0B3"
ERROR = "#FF7F91"

LIGHT_BG = "#F7F4EE"
LIGHT_PANEL = "#FFFEFB"
LIGHT_PANEL_ALT = "#F4F0E8"
LIGHT_LINE = "#D8D1C5"
LIGHT_LINE_STRONG = "#BFB5A6"
LIGHT_TEXT = "#111111"
LIGHT_MUTED = "#6E665C"
LIGHT_ACCENT = "#111111"
LIGHT_SOFT_ACCENT = "#ECE7DE"


def keep_animation(widget: QWidget, animation: QPropertyAnimation) -> None:
    animations = getattr(widget, "_qa_animations", None)
    if animations is None:
        animations = []
        setattr(widget, "_qa_animations", animations)
    animations.append(animation)

    def _cleanup() -> None:
        if animation in animations:
            animations.remove(animation)

    animation.finished.connect(_cleanup)


def fade_widget(
    widget: QWidget,
    start: float = 0.0,
    end: float = 1.0,
    duration: int = 160,
    on_finished: Callable[[], None] | None = None,
) -> QPropertyAnimation:
    effect = widget.graphicsEffect()
    if not isinstance(effect, QGraphicsOpacityEffect):
        effect = QGraphicsOpacityEffect(widget)
        widget.setGraphicsEffect(effect)
    effect.setOpacity(start)
    animation = QPropertyAnimation(effect, b"opacity", widget)
    animation.setDuration(duration)
    animation.setStartValue(start)
    animation.setEndValue(end)
    animation.setEasingCurve(QEasingCurve.Type.OutCubic)
    if on_finished is not None:
        animation.finished.connect(on_finished)
    keep_animation(widget, animation)
    animation.start()
    return animation


def fade_window(
    widget: QWidget,
    start: float = 0.0,
    end: float = 1.0,
    duration: int = 160,
    on_finished: Callable[[], None] | None = None,
) -> QPropertyAnimation:
    widget.setWindowOpacity(start)
    animation = QPropertyAnimation(widget, b"windowOpacity", widget)
    animation.setDuration(duration)
    animation.setStartValue(start)
    animation.setEndValue(end)
    animation.setEasingCurve(QEasingCurve.Type.OutCubic)
    if on_finished is not None:
        animation.finished.connect(on_finished)
    keep_animation(widget, animation)
    animation.start()
    return animation


def apply_shadow(widget: QWidget, color: str = ACCENT, blur: int = 34, alpha: int = 90) -> None:
    shadow = QGraphicsDropShadowEffect(widget)
    qcolor = QColor(color)
    qcolor.setAlpha(alpha)
    shadow.setColor(qcolor)
    shadow.setBlurRadius(blur)
    shadow.setOffset(0, 0)
    widget.setGraphicsEffect(shadow)


def button_stylesheet(accent: str = ACCENT, hover_fill: str = PANEL_SOFT) -> str:
    return f"""
    QPushButton {{
        color: {TEXT};
        background: {PANEL_ALT};
        border: 3px solid {accent};
        border-radius: 18px;
        padding: 8px 14px;
        font-family: "{BODY_FONT}";
        font-size: 12px;
        font-weight: 700;
    }}
    QPushButton:hover {{
        background: {hover_fill};
    }}
    QPushButton:pressed {{
        background: {accent};
        color: {PANEL_BG};
    }}
    QPushButton:disabled {{
        color: {MUTED};
        border-color: {ACCENT_SOFT};
    }}
    """


def input_stylesheet() -> str:
    return f"""
    QLineEdit, QPlainTextEdit {{
        background: transparent;
        color: {TEXT};
        border: none;
        selection-background-color: {ACCENT};
        font-family: "{BODY_FONT}";
        font-size: 13px;
    }}
    """


def dialog_stylesheet() -> str:
    return f"""
    QDialog {{
        background: {PANEL_BG};
        color: {TEXT};
        font-family: "{BODY_FONT}";
    }}
    QLabel {{
        color: {TEXT};
    }}
    QListWidget, QLineEdit, QPlainTextEdit, QSpinBox, QDoubleSpinBox, QComboBox {{
        background: {PANEL_ALT};
        border: 3px solid {ACCENT_SOFT};
        border-radius: 18px;
        color: {TEXT};
        padding: 8px 10px;
        selection-background-color: {ACCENT_SOFT};
    }}
    QListWidget::item:selected {{
        background: {PANEL_SOFT};
        border-radius: 12px;
    }}
    QCheckBox {{
        spacing: 8px;
    }}
    QCheckBox::indicator {{
        width: 18px;
        height: 18px;
        border-radius: 9px;
        border: 3px solid {ACCENT_SOFT};
        background: {PANEL_ALT};
    }}
    QCheckBox::indicator:checked {{
        background: {ACCENT};
        border-color: {ACCENT};
    }}
    QGroupBox {{
        border: 3px solid {ACCENT_SOFT};
        border-radius: 24px;
        margin-top: 18px;
        padding: 18px;
        font-family: "{DISPLAY_FONT}";
        font-size: 14px;
    }}
    QGroupBox::title {{
        subcontrol-origin: margin;
        left: 18px;
        padding: 0 8px;
        color: {ACCENT};
    }}
    {button_stylesheet()}
    """


def clean_button_stylesheet(
    *,
    fill: str = LIGHT_PANEL,
    text: str = LIGHT_TEXT,
    border: str = LIGHT_LINE,
    hover_fill: str = "#FFFFFF",
    pressed_fill: str = LIGHT_ACCENT,
    pressed_text: str = LIGHT_PANEL,
) -> str:
    return f"""
    QPushButton {{
        color: {text};
        background: {fill};
        border: 1px solid {border};
        border-radius: 20px;
        padding: 9px 16px;
        font-family: "{BODY_FONT}";
        font-size: 12px;
        font-weight: 700;
    }}
    QPushButton:hover {{
        background: {hover_fill};
        border-color: {LIGHT_LINE_STRONG};
    }}
    QPushButton:pressed {{
        background: {pressed_fill};
        color: {pressed_text};
        border-color: {pressed_fill};
    }}
    QPushButton:disabled {{
        color: {LIGHT_MUTED};
        border-color: {LIGHT_LINE};
        background: {LIGHT_PANEL_ALT};
    }}
    """


def clean_popup_view_stylesheet() -> str:
    return f"""
    QAbstractItemView {{
        background: {LIGHT_PANEL};
        color: {LIGHT_TEXT};
        border: 1px solid {LIGHT_LINE};
        border-radius: 18px;
        outline: none;
        padding: 8px;
        selection-background-color: {LIGHT_SOFT_ACCENT};
        selection-color: {LIGHT_TEXT};
        alternate-background-color: {LIGHT_PANEL_ALT};
    }}
    QAbstractItemView::item {{
        min-height: 22px;
        margin: 4px 0;
        padding: 12px 14px;
        border-radius: 14px;
        color: {LIGHT_TEXT};
        background: transparent;
    }}
    QAbstractItemView::item:selected {{
        background: {LIGHT_SOFT_ACCENT};
        color: {LIGHT_TEXT};
        border: 1px solid {LIGHT_LINE};
    }}
    QAbstractItemView::item:hover {{
        background: {LIGHT_PANEL_ALT};
        color: {LIGHT_TEXT};
    }}
    """


def clean_menu_stylesheet() -> str:
    return f"""
    QMenu {{
        background: {LIGHT_PANEL};
        color: {LIGHT_TEXT};
        border: 1px solid {LIGHT_LINE};
        border-radius: 16px;
        padding: 8px;
    }}
    QMenu::item {{
        padding: 10px 14px;
        border-radius: 12px;
        background: transparent;
    }}
    QMenu::item:selected {{
        background: {LIGHT_SOFT_ACCENT};
        color: {LIGHT_TEXT};
    }}
    QMenu::separator {{
        height: 1px;
        margin: 6px 8px;
        background: {LIGHT_LINE};
    }}
    """


def apply_light_combo_popup(combo: QComboBox) -> None:
    view = combo.view()
    if view is None:
        view = QListView(combo)
        combo.setView(view)
    view.setStyleSheet(clean_popup_view_stylesheet())
    view.setAlternatingRowColors(False)


def clean_dialog_stylesheet() -> str:
    return f"""
    QDialog {{
        background: {LIGHT_BG};
        color: {LIGHT_TEXT};
        font-family: "{BODY_FONT}";
    }}
    QLabel {{
        color: {LIGHT_TEXT};
        background: transparent;
    }}
    QGroupBox {{
        background: {LIGHT_PANEL};
        border: 1px solid {LIGHT_LINE};
        border-radius: 26px;
        margin-top: 18px;
        padding: 20px;
        font-family: "{DISPLAY_FONT}";
        font-size: 13px;
        font-weight: 700;
        color: {LIGHT_TEXT};
    }}
    QGroupBox::title {{
        subcontrol-origin: margin;
        left: 18px;
        padding: 0 8px;
        color: {LIGHT_MUTED};
    }}
    QListWidget,
    QLineEdit,
    QPlainTextEdit,
    QSpinBox,
    QDoubleSpinBox,
    QComboBox {{
        background: {LIGHT_PANEL};
        border: 1px solid {LIGHT_LINE};
        border-radius: 18px;
        color: {LIGHT_TEXT};
        padding: 8px 12px;
        selection-background-color: {LIGHT_SOFT_ACCENT};
        selection-color: {LIGHT_TEXT};
    }}
    QListWidget {{
        outline: none;
        padding: 8px;
    }}
    QListWidget::item {{
        margin: 4px 0;
        padding: 12px 14px;
        border-radius: 16px;
    }}
    QListWidget::item:selected {{
        background: {LIGHT_SOFT_ACCENT};
        border: 1px solid {LIGHT_LINE};
    }}
    QComboBox::drop-down {{
        border: none;
        width: 26px;
    }}
    QComboBox QAbstractItemView {{
        background: {LIGHT_PANEL};
        color: {LIGHT_TEXT};
        border: 1px solid {LIGHT_LINE};
        border-radius: 18px;
        padding: 8px;
        selection-background-color: {LIGHT_SOFT_ACCENT};
        selection-color: {LIGHT_TEXT};
    }}
    QAbstractItemView {{
        background: {LIGHT_PANEL};
        color: {LIGHT_TEXT};
        border: 1px solid {LIGHT_LINE};
        border-radius: 18px;
        outline: none;
        padding: 8px;
        selection-background-color: {LIGHT_SOFT_ACCENT};
        selection-color: {LIGHT_TEXT};
        alternate-background-color: {LIGHT_PANEL_ALT};
    }}
    QAbstractItemView::item {{
        min-height: 22px;
        margin: 4px 0;
        padding: 12px 14px;
        border-radius: 14px;
        color: {LIGHT_TEXT};
        background: transparent;
    }}
    QAbstractItemView::item:selected {{
        background: {LIGHT_SOFT_ACCENT};
        color: {LIGHT_TEXT};
        border: 1px solid {LIGHT_LINE};
    }}
    QAbstractItemView::item:hover {{
        background: {LIGHT_PANEL_ALT};
        color: {LIGHT_TEXT};
    }}
    QMenu {{
        background: {LIGHT_PANEL};
        color: {LIGHT_TEXT};
        border: 1px solid {LIGHT_LINE};
        border-radius: 16px;
        padding: 8px;
    }}
    QMenu::item {{
        padding: 10px 14px;
        border-radius: 12px;
        background: transparent;
    }}
    QMenu::item:selected {{
        background: {LIGHT_SOFT_ACCENT};
        color: {LIGHT_TEXT};
    }}
    QMenu::separator {{
        height: 1px;
        margin: 6px 8px;
        background: {LIGHT_LINE};
    }}
    QCheckBox {{
        spacing: 8px;
        color: {LIGHT_TEXT};
    }}
    QCheckBox::indicator {{
        width: 18px;
        height: 18px;
        border-radius: 9px;
        border: 1px solid {LIGHT_LINE_STRONG};
        background: {LIGHT_PANEL};
    }}
    QCheckBox::indicator:checked {{
        background: {LIGHT_ACCENT};
        border-color: {LIGHT_ACCENT};
    }}
    {clean_button_stylesheet()}
    """
