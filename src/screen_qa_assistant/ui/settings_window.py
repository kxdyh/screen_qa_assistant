from __future__ import annotations

import uuid
from pathlib import Path
from typing import Callable

from PySide6.QtCore import QRect, Qt, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDoubleSpinBox,
    QFileDialog,
    QFrame,
    QFormLayout,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from screen_qa_assistant.models import AppSettings, ProviderProfile
from screen_qa_assistant.storage.keyring_store import KeyringCredentialStore
from screen_qa_assistant.ui.hotkey_recorder import HotkeyRecorder
from screen_qa_assistant.ui.theme import (
    LIGHT_ACCENT,
    LIGHT_MUTED,
    apply_light_combo_popup,
    clean_button_stylesheet,
    clean_dialog_stylesheet,
)
from screen_qa_assistant.ui.tray_icon import build_tray_icon


def compute_settings_window_rect(
    available: QRect,
    *,
    width: int,
    height: int,
    margin: int = 18,
    upward_bias: int = 28,
) -> QRect:
    max_width = max(1, available.width() - margin * 2)
    max_height = max(1, available.height() - margin * 2)
    final_width = min(width, max_width)
    final_height = min(height, max_height)

    centered_x = available.x() + max(margin, (available.width() - final_width) // 2)
    centered_y = available.y() + max(margin, (available.height() - final_height) // 2)

    x = max(available.x() + margin, centered_x)
    y = max(available.y() + margin, centered_y - upward_bias)

    right_limit = available.right() - margin
    bottom_limit = available.bottom() - margin

    if x + final_width - 1 > right_limit:
        x = right_limit - final_width + 1
    if y + final_height - 1 > bottom_limit:
        y = bottom_limit - final_height + 1

    x = max(available.x() + margin, x)
    y = max(available.y() + margin, y)
    return QRect(x, y, final_width, final_height)


class _NoWheelSpinBox(QSpinBox):
    def wheelEvent(self, event) -> None:  # type: ignore[override]
        event.ignore()


class _NoWheelDoubleSpinBox(QDoubleSpinBox):
    def wheelEvent(self, event) -> None:  # type: ignore[override]
        event.ignore()


class SettingsWindow(QDialog):
    settings_saved = Signal(object, object)
    cleanup_requested = Signal(str, int)

    def __init__(self) -> None:
        super().__init__(None)
        self.setWindowFlags(
            Qt.WindowType.Window
            | Qt.WindowType.WindowMinimizeButtonHint
            | Qt.WindowType.WindowMaximizeButtonHint
            | Qt.WindowType.WindowCloseButtonHint
        )
        self.setWindowTitle("截图问答助手设置")
        self.resize(1160, 820)
        self.setMinimumSize(960, 720)
        self.setWindowIcon(build_tray_icon())
        self.setStyleSheet(clean_dialog_stylesheet())

        self._providers: list[ProviderProfile] = []
        self._api_keys: dict[str, str] = {}
        self._hotkey_validator: Callable[[str], str | None] = self._default_hotkey_validator
        self._active_provider_row = -1

        root = QVBoxLayout(self)
        root.setContentsMargins(24, 24, 24, 24)
        root.setSpacing(18)

        title = QLabel("模型与交互")
        title.setStyleSheet("font-size: 28px; font-weight: 700; letter-spacing: -1px;")
        root.addWidget(title)

        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setFrameShape(QFrame.Shape.NoFrame)
        self.scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.scroll_area.setStyleSheet(
            """
            QScrollArea {
                background: transparent;
                border: none;
            }
            QScrollArea > QWidget > QWidget {
                background: transparent;
            }
            """
        )
        root.addWidget(self.scroll_area, 1)

        self.content_widget = QWidget()
        self.content_widget.setObjectName("settingsScrollContent")
        self.scroll_area.setWidget(self.content_widget)

        scroll_root = QVBoxLayout(self.content_widget)
        scroll_root.setContentsMargins(0, 0, 0, 0)
        scroll_root.setSpacing(18)

        content = QHBoxLayout()
        content.setSpacing(20)
        content.setAlignment(Qt.AlignmentFlag.AlignTop)
        scroll_root.addLayout(content)

        provider_box = QGroupBox("模型配置")
        provider_layout = QVBoxLayout(provider_box)
        provider_layout.setSpacing(12)
        content.addWidget(provider_box, 1)

        self.provider_list = QListWidget()
        self.provider_list.setMinimumWidth(260)
        self.provider_list.currentRowChanged.connect(self._on_provider_selected)
        provider_layout.addWidget(self.provider_list, 1)

        provider_actions = QHBoxLayout()
        provider_actions.setSpacing(10)
        provider_layout.addLayout(provider_actions)

        self.add_provider_button = QPushButton("新增模型")
        self.add_provider_button.setStyleSheet(
            clean_button_stylesheet(
                fill=LIGHT_ACCENT,
                text="#FFFEFB",
                border=LIGHT_ACCENT,
                hover_fill="#2A2A2A",
                pressed_fill="#000000",
            )
        )
        self.add_provider_button.clicked.connect(self._add_provider)
        provider_actions.addWidget(self.add_provider_button)

        self.remove_provider_button = QPushButton("删除当前")
        self.remove_provider_button.setStyleSheet(clean_button_stylesheet())
        self.remove_provider_button.clicked.connect(self._remove_provider)
        provider_actions.addWidget(self.remove_provider_button)

        right_column = QVBoxLayout()
        right_column.setSpacing(18)
        content.addLayout(right_column, 2)

        detail_box = QGroupBox("当前模型详情")
        detail_layout = QFormLayout(detail_box)
        detail_layout.setSpacing(14)
        right_column.addWidget(detail_box)

        self.name_edit = QLineEdit()
        self.name_edit.textChanged.connect(self._update_current_item_label)
        detail_layout.addRow("显示名称", self.name_edit)

        self.base_url_edit = QLineEdit()
        detail_layout.addRow("Base URL", self.base_url_edit)

        self.model_edit = QLineEdit()
        detail_layout.addRow("模型名", self.model_edit)

        self.api_key_edit = QLineEdit()
        self.api_key_edit.setEchoMode(QLineEdit.EchoMode.Password)
        detail_layout.addRow("API Key", self.api_key_edit)

        self.supports_vision_checkbox = QCheckBox("该模型支持视觉输入")
        self.supports_vision_checkbox.setChecked(True)
        detail_layout.addRow("", self.supports_vision_checkbox)

        self.reasoning_checkbox = QCheckBox("默认开启思考模式")
        self.reasoning_checkbox.setChecked(False)
        detail_layout.addRow("", self.reasoning_checkbox)

        self.timeout_spin = _NoWheelSpinBox()
        self.timeout_spin.setRange(5, 600)
        self.timeout_spin.setValue(60)
        detail_layout.addRow("超时秒数", self.timeout_spin)

        self.temperature_spin = _NoWheelDoubleSpinBox()
        self.temperature_spin.setDecimals(2)
        self.temperature_spin.setRange(0.0, 2.0)
        self.temperature_spin.setSingleStep(0.1)
        self.temperature_spin.setValue(0.2)
        detail_layout.addRow("Temperature", self.temperature_spin)

        self.max_tokens_spin = _NoWheelSpinBox()
        self.max_tokens_spin.setRange(64, 32768)
        self.max_tokens_spin.setValue(2048)
        detail_layout.addRow("Max Tokens", self.max_tokens_spin)

        general_box = QGroupBox("通用设置")
        general_layout = QGridLayout(general_box)
        general_layout.setHorizontalSpacing(12)
        general_layout.setVerticalSpacing(14)
        general_layout.setColumnStretch(1, 1)
        right_column.addWidget(general_box)

        self.default_provider_combo = QComboBox()
        apply_light_combo_popup(self.default_provider_combo)
        general_layout.addWidget(QLabel("默认模型"), 0, 0)
        general_layout.addWidget(self.default_provider_combo, 0, 1, 1, 2)

        general_layout.addWidget(QLabel("截图快捷键"), 1, 0)
        self.hotkey_recorder = HotkeyRecorder()
        general_layout.addWidget(self.hotkey_recorder, 1, 1, 1, 2)

        self.hotkey_feedback_label = QLabel("点击右侧录制区，然后依次按下修饰键和主键。Backspace 会整段回退。")
        self.hotkey_feedback_label.setWordWrap(True)
        self.hotkey_feedback_label.setStyleSheet(
            f"color: {LIGHT_MUTED}; font-size: 11px; padding-left: 4px;"
        )
        general_layout.addWidget(self.hotkey_feedback_label, 2, 1, 1, 2)
        self.hotkey_recorder.hint_changed.connect(self._set_hotkey_hint)

        self.save_enabled_checkbox = QCheckBox("开启截图落盘")
        general_layout.addWidget(self.save_enabled_checkbox, 3, 0, 1, 3)

        self.save_dir_edit = QLineEdit()
        general_layout.addWidget(QLabel("保存路径"), 4, 0)
        general_layout.addWidget(self.save_dir_edit, 4, 1)

        self.browse_button = QPushButton("浏览")
        self.browse_button.setStyleSheet(clean_button_stylesheet())
        self.browse_button.clicked.connect(self._browse_save_dir)
        general_layout.addWidget(self.browse_button, 4, 2)

        self.cleanup_days_spin = QSpinBox()
        self.cleanup_days_spin.setRange(1, 3650)
        self.cleanup_days_spin.setValue(14)
        general_layout.addWidget(QLabel("清理周期（天）"), 5, 0)
        general_layout.addWidget(self.cleanup_days_spin, 5, 1)

        self.cleanup_button = QPushButton("立即清理")
        self.cleanup_button.setStyleSheet(clean_button_stylesheet())
        self.cleanup_button.clicked.connect(self._emit_cleanup)
        general_layout.addWidget(self.cleanup_button, 5, 2)

        right_column.addStretch(1)
        scroll_root.addStretch(1)

        footer = QHBoxLayout()
        footer.addStretch(1)
        root.addLayout(footer)

        self.cancel_button = QPushButton("取消")
        self.cancel_button.setStyleSheet(clean_button_stylesheet())
        self.cancel_button.clicked.connect(self.hide)
        footer.addWidget(self.cancel_button)

        self.save_button = QPushButton("保存设置")
        self.save_button.setStyleSheet(
            clean_button_stylesheet(
                fill=LIGHT_ACCENT,
                text="#FFFEFB",
                border=LIGHT_ACCENT,
                hover_fill="#2A2A2A",
                pressed_fill="#000000",
            )
        )
        self.save_button.clicked.connect(self._save)
        footer.addWidget(self.save_button)

        self._apply_compact_safe_metrics()

    def _apply_compact_safe_metrics(self) -> None:
        fixed_height_controls = [
            self.name_edit,
            self.base_url_edit,
            self.model_edit,
            self.api_key_edit,
            self.default_provider_combo,
            self.save_dir_edit,
            self.hotkey_recorder,
        ]
        for control in fixed_height_controls:
            control.setMinimumHeight(max(control.minimumHeight(), 44))
            control.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

        spin_controls = [
            self.timeout_spin,
            self.temperature_spin,
            self.max_tokens_spin,
            self.cleanup_days_spin,
        ]
        for control in spin_controls:
            control.setMinimumHeight(40)
            control.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

        action_buttons = [
            self.add_provider_button,
            self.remove_provider_button,
            self.browse_button,
            self.cleanup_button,
            self.cancel_button,
            self.save_button,
        ]
        for button in action_buttons:
            button.setMinimumHeight(40)
            button.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)

        self.provider_list.setMinimumWidth(260)
        self.provider_list.setMinimumHeight(460)
        self.provider_list.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.content_widget.setMinimumHeight(880)

    def set_hotkey_validator(self, validator: Callable[[str], str | None]) -> None:
        self._hotkey_validator = validator

    def load_settings(self, settings: AppSettings, credential_store: KeyringCredentialStore) -> None:
        self._providers = [provider.model_copy(deep=True) for provider in settings.providers]
        self._api_keys = {}
        self._active_provider_row = -1
        for provider in self._providers:
            if provider.api_key_ref:
                self._api_keys[provider.api_key_ref] = credential_store.get(provider.api_key_ref) or ""

        self.hotkey_recorder.set_sequence(settings.hotkey)
        self._set_hotkey_hint(self.hotkey_recorder.current_hint())
        self.save_enabled_checkbox.setChecked(settings.save_enabled)
        self.save_dir_edit.setText(settings.save_dir or "")
        self.cleanup_days_spin.setValue(settings.cleanup_policy_days or 14)
        self._refresh_provider_views(settings.default_provider_id)

    def present_on_screen(self, available: QRect) -> None:
        if self.isMaximized() or self.isFullScreen():
            return
        rect = compute_settings_window_rect(
            available,
            width=self.width(),
            height=self.height(),
        )
        self.resize(rect.size())
        self.move(rect.topLeft())

    def _refresh_provider_views(self, default_provider_id: str | None = None) -> None:
        self._active_provider_row = -1
        self.provider_list.blockSignals(True)
        self.provider_list.clear()
        for provider in self._providers:
            self.provider_list.addItem(provider.name)
        self.provider_list.blockSignals(False)

        self.default_provider_combo.clear()
        for provider in self._providers:
            self.default_provider_combo.addItem(provider.name, provider.id)

        if self._providers:
            target_id = default_provider_id or self._providers[0].id
            target_index = 0
            for idx, provider in enumerate(self._providers):
                if provider.id == target_id:
                    target_index = idx
                    break
            self.provider_list.setCurrentRow(target_index)
            self.default_provider_combo.setCurrentIndex(target_index)
        else:
            self._clear_form()

    def _clear_form(self) -> None:
        self._active_provider_row = -1
        self.name_edit.clear()
        self.base_url_edit.clear()
        self.model_edit.clear()
        self.api_key_edit.clear()
        self.supports_vision_checkbox.setChecked(True)
        self.reasoning_checkbox.setChecked(False)
        self.timeout_spin.setValue(60)
        self.temperature_spin.setValue(0.2)
        self.max_tokens_spin.setValue(2048)

    def _on_provider_selected(self, row: int) -> None:
        previous_row = self._active_provider_row
        if previous_row != row and 0 <= previous_row < len(self._providers):
            self._providers[previous_row] = self._build_provider_from_form(self._providers[previous_row])

        if row < 0 or row >= len(self._providers):
            self._clear_form()
            return
        provider = self._providers[row]
        self.name_edit.setText(provider.name)
        self.base_url_edit.setText(provider.base_url)
        self.model_edit.setText(provider.model)
        self.api_key_edit.setText(self._api_keys.get(provider.api_key_ref or "", ""))
        self.supports_vision_checkbox.setChecked(provider.supports_vision)
        self.reasoning_checkbox.setChecked(provider.enable_reasoning)
        self.timeout_spin.setValue(provider.timeout_seconds)
        self.temperature_spin.setValue(provider.temperature)
        self.max_tokens_spin.setValue(provider.max_tokens)
        self._active_provider_row = row

    def _build_provider_from_form(self, provider: ProviderProfile | None = None) -> ProviderProfile:
        existing = provider or ProviderProfile(
            id=uuid.uuid4().hex[:12],
            name="新模型",
            base_url="http://127.0.0.1:11434/v1",
            api_key_ref=None,
            model="gpt-4o-mini",
            supports_vision=True,
            enable_reasoning=False,
            timeout_seconds=60,
            temperature=0.2,
            max_tokens=2048,
        )
        api_ref = existing.api_key_ref or f"provider-{existing.id}"
        self._api_keys[api_ref] = self.api_key_edit.text().strip()
        return ProviderProfile(
            id=existing.id,
            name=self.name_edit.text().strip() or existing.name,
            base_url=self.base_url_edit.text().strip() or existing.base_url,
            api_key_ref=api_ref,
            model=self.model_edit.text().strip() or existing.model,
            supports_vision=self.supports_vision_checkbox.isChecked(),
            enable_reasoning=self.reasoning_checkbox.isChecked(),
            timeout_seconds=self.timeout_spin.value(),
            temperature=self.temperature_spin.value(),
            max_tokens=self.max_tokens_spin.value(),
        )

    def _commit_current_provider(self) -> None:
        row = self.provider_list.currentRow()
        if row < 0 or row >= len(self._providers):
            return
        self._providers[row] = self._build_provider_from_form(self._providers[row])
        self.provider_list.item(row).setText(self._providers[row].name)
        self.default_provider_combo.setItemText(row, self._providers[row].name)

    def _add_provider(self) -> None:
        if self._providers:
            self._commit_current_provider()
        provider = ProviderProfile(
            id=uuid.uuid4().hex[:12],
            name=f"新模型 {len(self._providers) + 1}",
            base_url="http://127.0.0.1:11434/v1",
            api_key_ref=None,
            model="gpt-4o-mini",
            supports_vision=True,
            enable_reasoning=False,
            timeout_seconds=60,
            temperature=0.2,
            max_tokens=2048,
        )
        self._providers.append(provider)
        self.provider_list.addItem(provider.name)
        self.default_provider_combo.addItem(provider.name, provider.id)
        self.provider_list.setCurrentRow(len(self._providers) - 1)

    def _remove_provider(self) -> None:
        row = self.provider_list.currentRow()
        if row < 0 or row >= len(self._providers):
            return
        self._active_provider_row = -1
        provider = self._providers.pop(row)
        if provider.api_key_ref:
            self._api_keys.setdefault(provider.api_key_ref, "")
        self.provider_list.takeItem(row)
        self.default_provider_combo.removeItem(row)
        if self._providers:
            self.provider_list.setCurrentRow(max(0, row - 1))
        else:
            self._clear_form()

    def _update_current_item_label(self, text: str) -> None:
        row = self.provider_list.currentRow()
        if row >= 0 and row < self.provider_list.count():
            label = text.strip() or f"模型 {row + 1}"
            self.provider_list.item(row).setText(label)
            if row < self.default_provider_combo.count():
                self.default_provider_combo.setItemText(row, label)

    def _browse_save_dir(self) -> None:
        directory = QFileDialog.getExistingDirectory(self, "选择截图保存目录", self.save_dir_edit.text() or str(Path.home()))
        if directory:
            self.save_dir_edit.setText(directory)

    def _emit_cleanup(self) -> None:
        directory = self.save_dir_edit.text().strip()
        if not directory:
            QMessageBox.warning(self, "无法清理", "请先填写截图保存目录。")
            return
        self.cleanup_requested.emit(directory, self.cleanup_days_spin.value())

    def _save(self) -> None:
        hotkey = self.hotkey_recorder.sequence().strip()
        validation_error = self._hotkey_validator(hotkey)
        if validation_error:
            self.hotkey_feedback_label.setText(validation_error)
            self.hotkey_feedback_label.setStyleSheet("color: #FF7F91; font-size: 11px; padding-left: 4px;")
            self.hotkey_recorder.setFocus()
            return

        self.hotkey_feedback_label.setText("快捷键可用。")
        self.hotkey_feedback_label.setStyleSheet("color: #2F8E63; font-size: 11px; padding-left: 4px;")

        try:
            if self._providers:
                self._commit_current_provider()
            settings = AppSettings(
                default_provider_id=self.default_provider_combo.currentData(),
                hotkey=hotkey,
                save_enabled=self.save_enabled_checkbox.isChecked(),
                save_dir=self.save_dir_edit.text().strip() or None,
                cleanup_policy_days=self.cleanup_days_spin.value(),
                window_prefs={"answer_window": {"width": 420, "height": 420}},
                providers=self._providers,
            )
        except Exception as exc:
            QMessageBox.warning(self, "保存失败", str(exc))
            return
        self.settings_saved.emit(settings, dict(self._api_keys))
        self.hide()

    def _set_hotkey_hint(self, text: str) -> None:
        self.hotkey_feedback_label.setText(text)
        self.hotkey_feedback_label.setStyleSheet(f"color: {LIGHT_MUTED}; font-size: 11px; padding-left: 4px;")

    @staticmethod
    def _default_hotkey_validator(sequence: str) -> str | None:
        if not sequence:
            return "请先点击快捷键录制区，再按下组合键。"
        return None
