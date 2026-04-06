from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QObject, QTimer
from PySide6.QtGui import QAction, QCursor
from PySide6.QtWidgets import QApplication, QMenu, QMessageBox, QSystemTrayIcon

from screen_qa_assistant.capture.overlay import CaptureOverlay
from screen_qa_assistant.capture.screenshot import ScreenshotService
from screen_qa_assistant.desktop.hotkey import GlobalHotkeyWidget, probe_hotkey_registration
from screen_qa_assistant.models import ProviderProfile, VisionRequest
from screen_qa_assistant.paths import get_default_capture_dir, get_settings_path
from screen_qa_assistant.providers.openai_compatible import OpenAICompatibleClient
from screen_qa_assistant.services.session_manager import SessionManager
from screen_qa_assistant.services.stream_worker import StreamWorker
from screen_qa_assistant.storage.keyring_store import KeyringCredentialStore
from screen_qa_assistant.storage.settings_store import JSONSettingsStore, build_screenshot_path, cleanup_saved_screenshots
from screen_qa_assistant.ui.answer_window import AnswerWindow
from screen_qa_assistant.ui.launch_panel import LaunchPanel
from screen_qa_assistant.ui.settings_window import SettingsWindow
from screen_qa_assistant.ui.theme import clean_menu_stylesheet
from screen_qa_assistant.ui.tray_icon import build_tray_icon


class AppController(QObject):
    def __init__(self, app: QApplication) -> None:
        super().__init__(app)
        self.app = app
        self._is_shutting_down = False
        self._app_icon = build_tray_icon()
        self.app.setWindowIcon(self._app_icon)
        self.settings_store = JSONSettingsStore(
            get_settings_path(),
            default_save_dir=str(get_default_capture_dir()),
        )
        self.credential_store = KeyringCredentialStore()
        self.settings = self.settings_store.load()
        self.client = OpenAICompatibleClient()
        self.session_manager = SessionManager()
        self.screenshot_service = ScreenshotService()

        self.answer_window = AnswerWindow(self.settings.window_prefs.get("answer_window", {}))
        self.launch_panel = LaunchPanel()
        self.overlay = CaptureOverlay(
            self.screenshot_service,
            submit_callback=self._handle_capture_submission,
            cancel_callback=self._handle_capture_cancelled,
        )
        self.hotkey_widget = GlobalHotkeyWidget(app)
        self.hotkey_widget.activated.connect(self.begin_capture)
        self.hotkey_widget.registration_failed.connect(self._show_hotkey_error)

        self.settings_window = SettingsWindow()
        self.settings_window.set_hotkey_validator(self._validate_hotkey)
        self.settings_window.settings_saved.connect(self._save_settings)
        self.settings_window.cleanup_requested.connect(self._run_cleanup)

        for window in (
            self.answer_window,
            self.launch_panel,
            self.overlay,
            self.settings_window,
        ):
            window.setWindowIcon(self._app_icon)

        self.answer_window.followup_submitted.connect(self._handle_followup_submitted)
        self.answer_window.retry_requested.connect(self._retry_last_request)
        self.answer_window.stop_requested.connect(self._stop_current_request)
        self.answer_window.closed_manually.connect(self._handle_answer_window_closed)
        self.answer_window.icon_menu_requested.connect(self._show_answer_window_icon_menu)

        self._active_worker: StreamWorker | None = None
        self._last_request: VisionRequest | None = None
        self._last_provider_id: str | None = None
        self._pending_followup_question: str | None = None
        self._current_response_buffer = ""
        self._answer_window_menu: QMenu | None = None

        self._tray = self._create_tray()

    def start(self) -> None:
        tray_available = QSystemTrayIcon.isSystemTrayAvailable()
        if tray_available:
            self._tray.show()
        self.launch_panel.capture_button.clicked.connect(self.begin_capture)
        self.launch_panel.settings_button.clicked.connect(self.show_settings)
        hotkey_registered = self.hotkey_widget.register_hotkey(self.settings.hotkey)
        if hotkey_registered:
            self.launch_panel.present(self.settings.hotkey, has_models=bool(self.settings.providers))
        else:
            QTimer.singleShot(200, self.show_settings)
        if tray_available:
            self._tray.showMessage(
                "截图问答助手",
                (
                    f"应用已启动，按 {self.settings.hotkey} 开始截图。"
                    if hotkey_registered
                    else f"应用已启动，但 {self.settings.hotkey} 当前不可用，请打开设置更换快捷键。"
                ),
            )
        if not self.settings.providers:
            QTimer.singleShot(200, self.show_settings)

    def shutdown(self) -> None:
        if self._is_shutting_down:
            return
        self._is_shutting_down = True
        self._cancel_active_request(reset_session=True)
        for window in (
            self.answer_window,
            self.launch_panel,
            self.overlay,
            self.settings_window,
        ):
            window.hide()
        self.hotkey_widget.dispose()
        self.launch_panel.hide()
        self._tray.setContextMenu(None)
        self._tray.hide()

    def _create_tray(self) -> QSystemTrayIcon:
        tray = QSystemTrayIcon(self._app_icon, self.app)
        tray.setToolTip("截图问答助手")
        menu = self._build_quick_menu()
        tray.setContextMenu(menu)
        tray.activated.connect(
            lambda reason: self.begin_capture()
            if reason == QSystemTrayIcon.ActivationReason.Trigger
            else None
        )
        return tray

    def _build_quick_menu(self, parent=None) -> QMenu:
        menu = QMenu(parent)
        menu.setStyleSheet(clean_menu_stylesheet())

        capture_action = QAction("开始截图", menu)
        capture_action.triggered.connect(self.begin_capture)
        menu.addAction(capture_action)

        settings_action = QAction("打开设置", menu)
        settings_action.triggered.connect(self.show_settings)
        menu.addAction(settings_action)

        menu.addSeparator()

        quit_action = QAction("退出", menu)
        quit_action.triggered.connect(self._quit)
        menu.addAction(quit_action)
        return menu

    def _show_answer_window_icon_menu(self, global_pos) -> None:
        if not self.answer_window.is_iconified:
            return
        menu = self._build_quick_menu(self.answer_window)
        self._answer_window_menu = menu
        menu.aboutToHide.connect(menu.deleteLater)
        menu.aboutToHide.connect(lambda: setattr(self, "_answer_window_menu", None))
        menu.popup(global_pos)

    def _quit(self) -> None:
        self.shutdown()
        self.app.closeAllWindows()
        self.app.exit(0)

    def show_settings(self) -> None:
        self.settings_window.load_settings(self.settings, self.credential_store)
        screen = QApplication.screenAt(QCursor.pos()) or self.app.primaryScreen()
        if screen is not None:
            self.settings_window.present_on_screen(screen.availableGeometry())
        self.settings_window.show()
        self.settings_window.raise_()
        self.settings_window.activateWindow()

    def begin_capture(self) -> None:
        if self.overlay.isVisible():
            return
        provider = self._current_provider()
        self.overlay.set_provider_capabilities(provider.supports_vision if provider is not None else True)
        had_session = self.session_manager.current_session is not None or self.answer_window.isVisible()
        self._cancel_active_request(reset_session=True)
        if had_session and self.answer_window.isVisible():
            self.answer_window.append_system_message("已切换到新的截图会话")
        self.overlay.begin_capture()

    def _handle_capture_cancelled(self) -> None:
        return

    def _provider_by_id(self, provider_id: str | None) -> ProviderProfile | None:
        for provider in self.settings.providers:
            if provider.id == provider_id:
                return provider
        return None

    def _current_provider(self) -> ProviderProfile | None:
        provider = self._provider_by_id(self.settings.default_provider_id)
        if provider is not None:
            return provider
        return self.settings.providers[0] if self.settings.providers else None

    def _handle_capture_submission(self, png_bytes: bytes | None, question: str, rect) -> str | None:
        provider = self._current_provider()
        if provider is None:
            return "请先在设置里添加一个模型。"
        if png_bytes is None:
            self.session_manager.start_text_session(provider, question)
        else:
            if not provider.supports_vision:
                return "当前模型不支持截图，请直接按 Enter 文本提问。"
            screenshot_ref = self._persist_capture(png_bytes)
            self.session_manager.start_session(provider, screenshot_ref, question)
        request = self.session_manager.build_initial_request()
        self._last_request = request
        self._last_provider_id = provider.id
        self._pending_followup_question = None
        self.answer_window.queue_turn(
            provider.name,
            question,
            collapse=True,
            reset=True,
            input_mode=request.input_mode,
        )
        self._start_request(provider, request)
        return None

    def _persist_capture(self, png_bytes: bytes) -> bytes | str:
        if not self.settings.save_enabled:
            return png_bytes
        save_dir = self.settings.save_dir or str(get_default_capture_dir())
        path = build_screenshot_path(Path(save_dir))
        self.screenshot_service.save_png(png_bytes, path)
        return str(path)

    def _start_request(self, provider: ProviderProfile, request: VisionRequest) -> None:
        api_key = self.credential_store.get(provider.api_key_ref) if provider.api_key_ref else None
        self._current_response_buffer = ""
        self.session_manager.mark_streaming()
        worker = StreamWorker(self.client, provider, request, api_key)
        worker.signals.chunk.connect(lambda chunk, current=worker: self._on_worker_chunk(current, chunk))
        worker.signals.error.connect(lambda message, current=worker: self._on_worker_error(current, message))
        worker.signals.finished.connect(lambda status, current=worker: self._on_worker_finished(current, status))
        self._active_worker = worker
        worker.start()

    def _on_worker_chunk(self, worker: StreamWorker, chunk: str) -> None:
        if worker is not self._active_worker:
            return
        self._current_response_buffer += chunk
        self.answer_window.append_chunk(chunk)

    def _on_worker_error(self, worker: StreamWorker, message: str) -> None:
        if worker is not self._active_worker:
            return
        self.session_manager.mark_error()
        self.answer_window.append_error(message)

    def _on_worker_finished(self, worker: StreamWorker, status: str) -> None:
        if worker is not self._active_worker:
            return

        if status == "completed":
            if self._pending_followup_question is not None:
                self.session_manager.record_user_message(self._pending_followup_question)
                self._pending_followup_question = None
            if self._current_response_buffer.strip():
                self.session_manager.record_assistant_message(self._current_response_buffer)
            self.session_manager.mark_completed()
            self.answer_window.finish_turn("已完成")
        elif status == "cancelled":
            self.session_manager.cancel_current_session()
            self.answer_window.finish_turn("已停止")
        else:
            self.answer_window.finish_turn("请求失败")

        self._current_response_buffer = ""
        self._active_worker = None

    def _handle_followup_submitted(self, question: str) -> None:
        if self._active_worker is not None:
            self.answer_window.append_system_message("请等待当前回答结束后再继续追问。")
            return
        session = self.session_manager.current_session
        if session is None:
            self.answer_window.append_system_message("当前没有可追问的截图会话。")
            return
        provider = self._provider_by_id(session.provider_id)
        if provider is None:
            self.answer_window.append_system_message("当前会话模型不存在，请重新截图。")
            return

        request = self.session_manager.build_followup_request(question)
        self._pending_followup_question = question
        self._last_request = request
        self._last_provider_id = provider.id
        self.answer_window.queue_turn(
            provider.name,
            question,
            collapse=False,
            reset=False,
            input_mode=session.input_mode,
        )
        self._start_request(provider, request)

    def _retry_last_request(self) -> None:
        if self._active_worker is not None or self._last_request is None or self._last_provider_id is None:
            return
        provider = self._provider_by_id(self._last_provider_id)
        if provider is None:
            self.answer_window.append_system_message("重试失败：当前模型配置不存在。")
            return
        self.answer_window.queue_turn(
            provider.name,
            self._last_request.question,
            collapse=False,
            reset=False,
            input_mode=self._last_request.input_mode,
        )
        self._start_request(provider, self._last_request)

    def _stop_current_request(self) -> None:
        if self._active_worker is None:
            return
        self._cancel_active_request(reset_session=False)
        self.answer_window.append_system_message("当前回答已手动停止。")
        self.answer_window.finish_turn("已停止")

    def _cancel_active_request(self, reset_session: bool) -> None:
        worker = self._active_worker
        self._active_worker = None
        if worker is not None:
            worker.stop()
        self._current_response_buffer = ""
        if reset_session:
            self._pending_followup_question = None
            self.session_manager.clear()

    def _handle_answer_window_closed(self) -> None:
        self._cancel_active_request(reset_session=True)

    def _save_settings(self, settings, api_keys: dict[str, str]) -> None:
        previous_hotkey = self.settings.hotkey
        if not self.hotkey_widget.register_hotkey(settings.hotkey):
            self.hotkey_widget.register_hotkey(previous_hotkey)
            QMessageBox.warning(
                self.settings_window,
                "快捷键不可用",
                "新的快捷键注册失败，请更换一个没有冲突的组合键。",
            )
            return

        self.settings = settings
        for provider in settings.providers:
            if provider.api_key_ref:
                secret = api_keys.get(provider.api_key_ref, "").strip()
                if secret:
                    self.credential_store.set(provider.api_key_ref, secret)
                else:
                    self.credential_store.delete(provider.api_key_ref)
        self.settings_store.save(settings)
        self.answer_window.hide()
        self.answer_window = AnswerWindow(self.settings.window_prefs.get("answer_window", {}))
        self.answer_window.setWindowIcon(self._app_icon)
        self.answer_window.followup_submitted.connect(self._handle_followup_submitted)
        self.answer_window.retry_requested.connect(self._retry_last_request)
        self.answer_window.stop_requested.connect(self._stop_current_request)
        self.answer_window.closed_manually.connect(self._handle_answer_window_closed)
        self.answer_window.icon_menu_requested.connect(self._show_answer_window_icon_menu)
        self._tray.showMessage("截图问答助手", "设置已保存。")

    def _run_cleanup(self, directory: str, days: int) -> None:
        removed = cleanup_saved_screenshots(Path(directory), older_than_days=days)
        QMessageBox.information(
            self.settings_window,
            "清理完成",
            f"已清理 {len(removed)} 个过期截图文件。",
        )

    def _show_hotkey_error(self, message: str) -> None:
        self.launch_panel.present_hotkey_error(self.settings.hotkey, message)
        if QSystemTrayIcon.isSystemTrayAvailable():
            self._tray.showMessage("截图问答助手", message)

    def _validate_hotkey(self, sequence: str) -> str | None:
        if not sequence:
            return "请先点击快捷键录制区，再按下组合键。"
        if sequence == self.settings.hotkey:
            return None
        ok, message = probe_hotkey_registration(sequence)
        if ok:
            return None
        return message
