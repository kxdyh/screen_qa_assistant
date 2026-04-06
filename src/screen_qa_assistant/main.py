from __future__ import annotations

import ctypes
import os
import sys


def _configure_windows_dpi() -> None:
    if os.name != "nt":
        return
    os.environ.setdefault("QT_ENABLE_HIGHDPI_SCALING", "0")
    try:
        ctypes.windll.user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4))
    except Exception:
        try:
            ctypes.windll.user32.SetProcessDPIAware()
        except Exception:
            return


def _configure_windows_app_identity() -> None:
    if os.name != "nt":
        return
    try:
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(
            "ScreenQAAssistant.Desktop"
        )
    except Exception:
        return


_configure_windows_dpi()
_configure_windows_app_identity()

from PySide6.QtWidgets import QApplication, QMessageBox

from screen_qa_assistant.desktop.hotkey import probe_hotkey_registration
from screen_qa_assistant.desktop.single_instance import SingleInstanceGuard
from screen_qa_assistant.paths import get_lock_path
from screen_qa_assistant.services.app_controller import AppController
from screen_qa_assistant.ui.tray_icon import build_tray_icon


def build_startup_console_message(
    hotkey: str,
    has_providers: bool,
    hotkey_error: str | None = None,
) -> str:
    suffix = "模型已配置，应用会常驻托盘。" if has_providers else "还没有模型配置，启动后会自动打开设置页。"
    if hotkey_error:
        return (
            f"截图问答助手已启动，但当前快捷键 {hotkey} 暂不可用。{hotkey_error}"
            f" 你可以先从托盘或启动面板打开设置修改快捷键。{suffix}"
        )
    return f"截图问答助手已启动。按 {hotkey} 开始截图；可从托盘打开设置。{suffix}"


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName("截图问答助手")
    app.setWindowIcon(build_tray_icon())
    app.setQuitOnLastWindowClosed(False)

    instance_guard = SingleInstanceGuard(get_lock_path())
    if not instance_guard.acquire():
        QMessageBox.information(None, "截图问答助手", "应用已经在运行。")
        return 0

    controller = AppController(app)
    _, hotkey_error = probe_hotkey_registration(controller.settings.hotkey)
    print(
        build_startup_console_message(
            controller.settings.hotkey,
            bool(controller.settings.providers),
            hotkey_error=hotkey_error,
        ),
        flush=True,
    )
    controller.start()
    exit_code = app.exec()
    controller.shutdown()
    instance_guard.release()
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
