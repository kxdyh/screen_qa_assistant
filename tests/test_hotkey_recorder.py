from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QEvent, QPoint, QPointF, Qt
from PySide6.QtGui import QKeyEvent, QWheelEvent
from PySide6.QtCore import QRect
from PySide6.QtWidgets import QApplication, QLabel, QScrollArea

from screen_qa_assistant.desktop.hotkey import probe_hotkey_registration
from screen_qa_assistant.models import AppSettings, ProviderProfile
from screen_qa_assistant.ui.hotkey_recorder import HotkeyRecorder
from screen_qa_assistant.ui.settings_window import SettingsWindow, compute_settings_window_rect
from screen_qa_assistant.ui.theme import clean_dialog_stylesheet


def ensure_app() -> QApplication:
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def press_key(widget, key: int, modifiers: Qt.KeyboardModifier = Qt.KeyboardModifier.NoModifier) -> None:
    event = QKeyEvent(QEvent.Type.KeyPress, key, modifiers)
    widget.keyPressEvent(event)


def spin_wheel(widget) -> None:
    event = QWheelEvent(
        QPointF(12, 12),
        QPointF(12, 12),
        QPoint(0, 0),
        QPoint(0, 120),
        Qt.MouseButton.NoButton,
        Qt.KeyboardModifier.NoModifier,
        Qt.ScrollPhase.ScrollUpdate,
        False,
    )
    widget.wheelEvent(event)


class FakeCredentialStore:
    def get(self, key: str) -> str | None:
        return None


def build_provider(provider_id: str, name: str, model: str) -> ProviderProfile:
    return ProviderProfile(
        id=provider_id,
        name=name,
        base_url="http://127.0.0.1:11434/v1",
        api_key_ref=f"provider-{provider_id}",
        model=model,
        supports_vision=True,
        enable_reasoning=False,
        timeout_seconds=60,
        temperature=0.2,
        max_tokens=2048,
    )


def test_hotkey_recorder_builds_sequence_from_pressed_keys() -> None:
    ensure_app()
    recorder = HotkeyRecorder()

    press_key(recorder, Qt.Key.Key_Control, Qt.KeyboardModifier.ControlModifier)
    assert recorder.sequence() == "Ctrl"

    press_key(recorder, Qt.Key.Key_Q, Qt.KeyboardModifier.ControlModifier)
    assert recorder.sequence() == "Ctrl+Q"


def test_hotkey_recorder_keeps_modifier_after_it_is_pressed_first() -> None:
    ensure_app()
    recorder = HotkeyRecorder()

    press_key(recorder, Qt.Key.Key_Control, Qt.KeyboardModifier.ControlModifier)
    press_key(recorder, Qt.Key.Key_Q, Qt.KeyboardModifier.NoModifier)

    assert recorder.sequence() == "Ctrl+Q"


def test_hotkey_recorder_can_promote_single_key_into_combo() -> None:
    ensure_app()
    recorder = HotkeyRecorder()

    press_key(recorder, Qt.Key.Key_E, Qt.KeyboardModifier.NoModifier)
    press_key(recorder, Qt.Key.Key_Control, Qt.KeyboardModifier.ControlModifier)

    assert recorder.sequence() == "Ctrl+E"


def test_hotkey_recorder_backspace_removes_whole_segment() -> None:
    ensure_app()
    recorder = HotkeyRecorder()
    recorder.set_sequence("Ctrl+Shift+A")

    press_key(recorder, Qt.Key.Key_Backspace)
    assert recorder.sequence() == "Ctrl+Shift"

    press_key(recorder, Qt.Key.Key_Backspace)
    assert recorder.sequence() == "Ctrl"

    press_key(recorder, Qt.Key.Key_Backspace)
    assert recorder.sequence() == ""


def test_hotkey_recorder_disables_native_input_panel() -> None:
    ensure_app()
    recorder = HotkeyRecorder()

    assert recorder.testAttribute(Qt.WidgetAttribute.WA_InputMethodEnabled) is False
    assert recorder.contextMenuPolicy() == Qt.ContextMenuPolicy.NoContextMenu


def test_settings_window_blocks_save_when_hotkey_is_invalid() -> None:
    ensure_app()
    window = SettingsWindow()
    saved: list[object] = []
    window.settings_saved.connect(lambda settings, keys: saved.append(settings))
    window.set_hotkey_validator(lambda sequence: "快捷键已被其他程序占用" if sequence == "Ctrl+Q" else None)
    window.hotkey_recorder.set_sequence("Ctrl+Q")

    window._save()

    assert saved == []
    assert "占用" in window.hotkey_feedback_label.text()


def test_settings_window_prompts_for_next_hotkey_key() -> None:
    ensure_app()
    window = SettingsWindow()

    press_key(window.hotkey_recorder, Qt.Key.Key_Control, Qt.KeyboardModifier.ControlModifier)

    assert "继续" in window.hotkey_feedback_label.text()


def test_settings_window_opens_with_roomier_default_size() -> None:
    ensure_app()
    window = SettingsWindow()

    assert window.width() >= 1120
    assert window.height() >= 800


def test_settings_window_has_standard_caption_buttons() -> None:
    ensure_app()
    window = SettingsWindow()

    flags = window.windowFlags()
    assert bool(flags & Qt.WindowType.WindowMinimizeButtonHint)
    assert bool(flags & Qt.WindowType.WindowMaximizeButtonHint)
    assert bool(flags & Qt.WindowType.WindowCloseButtonHint)


def test_settings_window_uses_scroll_area_for_main_content() -> None:
    ensure_app()
    window = SettingsWindow()

    scroll_areas = window.findChildren(QScrollArea)

    assert len(scroll_areas) >= 1


def test_settings_window_applies_visible_styles_to_combo_popup() -> None:
    ensure_app()
    window = SettingsWindow()

    popup_sheet = window.default_provider_combo.view().styleSheet()

    assert "QAbstractItemView" in popup_sheet
    assert "#FFFEFB" in popup_sheet
    assert "#111111" in popup_sheet


def test_settings_window_does_not_render_intro_marketing_copy() -> None:
    ensure_app()
    window = SettingsWindow()
    labels = [label.text() for label in window.findChildren(QLabel)]

    assert "管理多个兼容端点、默认模型、截图快捷键和保存策略。" not in labels
    assert "模型与交互" in labels


def test_clean_dialog_stylesheet_styles_popup_views_and_menus() -> None:
    stylesheet = clean_dialog_stylesheet()

    assert "QComboBox QAbstractItemView" in stylesheet
    assert "QAbstractItemView::item:selected" in stylesheet
    assert "QMenu {" in stylesheet


def test_compute_settings_window_rect_keeps_bottom_buttons_visible() -> None:
    available = QRect(0, 0, 1440, 1000)

    rect = compute_settings_window_rect(available, width=1160, height=820)

    centered_y = available.y() + max(18, (available.height() - rect.height()) // 2)
    assert rect.bottom() <= available.bottom() - 18
    assert rect.y() < centered_y


def test_settings_window_keeps_key_editors_readable_at_compact_size() -> None:
    app = ensure_app()
    window = SettingsWindow()
    settings = AppSettings(
        default_provider_id="p1",
        hotkey="Ctrl+Shift+A",
        providers=[
            build_provider("p1", "模型一", "gpt-4o"),
            build_provider("p2", "模型二", "gpt-4.1"),
        ],
    )
    window.load_settings(settings, FakeCredentialStore())
    window.resize(960, 720)
    window.show()
    app.processEvents()

    assert window.name_edit.height() >= 40
    assert window.base_url_edit.height() >= 40
    assert window.default_provider_combo.height() >= 40
    assert window.timeout_spin.height() >= 40
    assert window.save_dir_edit.height() >= 40


def test_settings_window_disables_wheel_changes_for_core_generation_fields() -> None:
    ensure_app()
    window = SettingsWindow()

    timeout_before = window.timeout_spin.value()
    temperature_before = window.temperature_spin.value()
    max_tokens_before = window.max_tokens_spin.value()
    cleanup_before = window.cleanup_days_spin.value()

    spin_wheel(window.timeout_spin)
    spin_wheel(window.temperature_spin)
    spin_wheel(window.max_tokens_spin)
    spin_wheel(window.cleanup_days_spin)

    assert window.timeout_spin.value() == timeout_before
    assert window.temperature_spin.value() == temperature_before
    assert window.max_tokens_spin.value() == max_tokens_before
    assert window.cleanup_days_spin.value() != cleanup_before


def test_settings_window_keeps_provider_edits_when_switching_rows() -> None:
    ensure_app()
    window = SettingsWindow()
    settings = AppSettings(
        default_provider_id="p1",
        hotkey="Ctrl+Shift+A",
        providers=[
            build_provider("p1", "模型一", "gpt-4o"),
            build_provider("p2", "模型二", "gpt-4.1"),
        ],
    )
    window.load_settings(settings, FakeCredentialStore())

    window.provider_list.setCurrentRow(1)
    window.name_edit.setText("模型二-已修改")
    window.model_edit.setText("gpt-4.1-mini")
    window.provider_list.setCurrentRow(0)
    window.provider_list.setCurrentRow(1)

    assert window.name_edit.text() == "模型二-已修改"
    assert window.model_edit.text() == "gpt-4.1-mini"


def test_settings_window_loads_reasoning_checkbox_from_provider() -> None:
    ensure_app()
    window = SettingsWindow()
    settings = AppSettings(
        default_provider_id="p1",
        hotkey="Ctrl+Shift+A",
        providers=[build_provider("p1", "模型一", "gpt-4o").model_copy(update={"enable_reasoning": True})],
    )
    window.load_settings(settings, FakeCredentialStore())

    assert window.reasoning_checkbox.isChecked() is True


def test_probe_hotkey_registration_returns_conflict_message() -> None:
    class FakeUser32:
        def RegisterHotKey(self, hwnd, hotkey_id, modifiers, key_code):  # noqa: N802
            return 0

        def UnregisterHotKey(self, hwnd, hotkey_id):  # noqa: N802
            return 1

    ok, message = probe_hotkey_registration(
        "Ctrl+Q",
        user32=FakeUser32(),
        error_getter=lambda: 1409,
    )

    assert ok is False
    assert "占用" in message
