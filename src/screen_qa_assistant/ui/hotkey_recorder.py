from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFocusEvent, QInputMethodEvent, QKeyEvent
from PySide6.QtWidgets import QLineEdit


MODIFIER_PARTS = ("Ctrl", "Shift", "Alt", "Win")


class HotkeyRecorder(QLineEdit):
    sequence_changed = Signal(str)
    hint_changed = Signal(str)

    def __init__(self) -> None:
        super().__init__()
        self._parts: list[str] = []
        self.setReadOnly(True)
        self.setAttribute(Qt.WidgetAttribute.WA_InputMethodEnabled, False)
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.NoContextMenu)
        self.setInputMethodHints(
            Qt.InputMethodHint.ImhNoPredictiveText
            | Qt.InputMethodHint.ImhNoAutoUppercase
            | Qt.InputMethodHint.ImhPreferLatin
        )
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        self.setPlaceholderText("点击这里，然后依次录入快捷键")
        self.setMinimumWidth(380)
        self.setMinimumHeight(52)
        self._apply_idle_style()

    def sequence(self) -> str:
        return "+".join(self._parts)

    def set_sequence(self, sequence: str) -> None:
        self._parts = [part.strip() for part in sequence.split("+") if part.strip()]
        self._sync_text()

    def clear_sequence(self) -> None:
        self._parts = []
        self._sync_text()

    def current_hint(self) -> str:
        return self._build_hint()

    def focusInEvent(self, event: QFocusEvent) -> None:  # type: ignore[override]
        super().focusInEvent(event)
        self.deselect()
        self._apply_active_style()

    def focusOutEvent(self, event: QFocusEvent) -> None:  # type: ignore[override]
        super().focusOutEvent(event)
        self._apply_idle_style()

    def keyPressEvent(self, event: QKeyEvent) -> None:  # type: ignore[override]
        key = event.key()

        if key in {Qt.Key.Key_Backspace, Qt.Key.Key_Delete}:
            if self._parts:
                self._parts.pop()
                self._sync_text()
            event.accept()
            return

        if key == Qt.Key.Key_Escape:
            self.clear_sequence()
            event.accept()
            return

        modifiers = self._modifier_parts(event.modifiers())
        key_name = self._key_name(key)
        if key_name is None:
            event.accept()
            return

        existing_modifiers, existing_main = self._split_parts()
        if key_name in MODIFIER_PARTS:
            merged_modifiers = self._merge_modifiers(existing_modifiers, modifiers or [key_name])
            self._parts = self._compose_parts(merged_modifiers, existing_main)
        else:
            merged_modifiers = self._merge_modifiers(existing_modifiers, modifiers)
            self._parts = self._compose_parts(merged_modifiers, key_name)

        self._sync_text()
        event.accept()

    def mousePressEvent(self, event) -> None:  # type: ignore[override]
        self.setFocus()
        event.accept()

    def mouseDoubleClickEvent(self, event) -> None:  # type: ignore[override]
        self.setFocus()
        event.accept()

    def inputMethodEvent(self, event: QInputMethodEvent) -> None:  # type: ignore[override]
        event.ignore()

    def _modifier_parts(self, modifiers: Qt.KeyboardModifier) -> list[str]:
        parts: list[str] = []
        if modifiers & Qt.KeyboardModifier.ControlModifier:
            parts.append("Ctrl")
        if modifiers & Qt.KeyboardModifier.ShiftModifier:
            parts.append("Shift")
        if modifiers & Qt.KeyboardModifier.AltModifier:
            parts.append("Alt")
        if modifiers & Qt.KeyboardModifier.MetaModifier:
            parts.append("Win")
        return parts

    def _split_parts(self) -> tuple[list[str], str | None]:
        modifiers = [part for part in self._parts if part in MODIFIER_PARTS]
        main_key = next((part for part in self._parts if part not in MODIFIER_PARTS), None)
        return modifiers, main_key

    def _merge_modifiers(self, existing: list[str], incoming: list[str]) -> list[str]:
        merged = list(existing)
        for part in incoming:
            if part in MODIFIER_PARTS and part not in merged:
                merged.append(part)
        merged.sort(key=MODIFIER_PARTS.index)
        return merged

    def _compose_parts(self, modifiers: list[str], main_key: str | None) -> list[str]:
        parts = list(modifiers)
        if main_key:
            parts.append(main_key)
        return parts

    def _key_name(self, key: int) -> str | None:
        modifier_keys = {
            Qt.Key.Key_Control: "Ctrl",
            Qt.Key.Key_Shift: "Shift",
            Qt.Key.Key_Alt: "Alt",
            Qt.Key.Key_Meta: "Win",
        }
        if key in modifier_keys:
            return modifier_keys[key]

        special = {
            Qt.Key.Key_Return: "Enter",
            Qt.Key.Key_Enter: "Enter",
            Qt.Key.Key_Tab: "Tab",
            Qt.Key.Key_Space: "Space",
            Qt.Key.Key_Escape: "Esc",
            Qt.Key.Key_Print: "PrintScreen",
            Qt.Key.Key_Insert: "Insert",
            Qt.Key.Key_Delete: "Delete",
            Qt.Key.Key_Home: "Home",
            Qt.Key.Key_End: "End",
            Qt.Key.Key_PageUp: "PageUp",
            Qt.Key.Key_PageDown: "PageDown",
            Qt.Key.Key_Left: "Left",
            Qt.Key.Key_Right: "Right",
            Qt.Key.Key_Up: "Up",
            Qt.Key.Key_Down: "Down",
        }
        if key in special:
            return special[key]

        if Qt.Key.Key_A <= key <= Qt.Key.Key_Z:
            return chr(key)
        if Qt.Key.Key_0 <= key <= Qt.Key.Key_9:
            return chr(key)
        if Qt.Key.Key_F1 <= key <= Qt.Key.Key_F24:
            return f"F{key - Qt.Key.Key_F1 + 1}"
        return None

    def _sync_text(self) -> None:
        sequence = self.sequence()
        self.setText(sequence)
        self.sequence_changed.emit(sequence)
        self.hint_changed.emit(self._build_hint())

    def _build_hint(self) -> str:
        modifiers, main_key = self._split_parts()
        if not self._parts:
            return "点击录制区，然后依次按下修饰键和主键。Backspace 会整段回退。"
        if modifiers and main_key is None:
            return f"已记录 {'+'.join(modifiers)}，请继续按下主键。"
        if main_key is not None and not modifiers:
            return f"已记录 {main_key}，如需组合键，请继续按下 Ctrl / Shift / Alt / Win。"
        return f"当前快捷键：{self.sequence()}。如需修改，可继续按键覆盖主键或按 Backspace 回退。"

    def _apply_idle_style(self) -> None:
        self.setStyleSheet(
            """
            QLineEdit {
                background: rgba(255, 255, 255, 0.98);
                border: 1px solid #D8D1C5;
                border-radius: 22px;
                color: #111111;
                padding: 10px 14px;
                font-family: "Microsoft YaHei UI";
                font-size: 13px;
                font-weight: 700;
            }
            """
        )

    def _apply_active_style(self) -> None:
        self.setStyleSheet(
            """
            QLineEdit {
                background: rgba(255, 255, 255, 1);
                border: 1px solid #111111;
                border-radius: 22px;
                color: #111111;
                padding: 10px 14px;
                font-family: "Microsoft YaHei UI";
                font-size: 13px;
                font-weight: 700;
            }
            """
        )
