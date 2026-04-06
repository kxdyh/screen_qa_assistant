from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QRect
from PySide6.QtWidgets import QApplication

from screen_qa_assistant.models import AppSettings, ProviderProfile
from screen_qa_assistant.services.app_controller import AppController


def ensure_app() -> QApplication:
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def build_provider(*, supports_vision: bool, enable_reasoning: bool = False) -> ProviderProfile:
    return ProviderProfile(
        id="provider-1",
        name="Provider One",
        base_url="https://example.com/v1",
        api_key_ref=None,
        model="demo-model",
        supports_vision=supports_vision,
        enable_reasoning=enable_reasoning,
        timeout_seconds=60,
        temperature=0.2,
        max_tokens=2048,
    )


def test_begin_capture_ignores_hotkey_while_overlay_is_active() -> None:
    app = ensure_app()
    controller = AppController(app)
    calls: list[str] = []
    controller.overlay.begin_capture = lambda: calls.append("capture")  # type: ignore[method-assign]
    controller.overlay.isVisible = lambda: True  # type: ignore[method-assign]

    controller.begin_capture()

    assert calls == []
    controller.shutdown()
    controller.hotkey_widget.dispose()


def test_handle_capture_submission_allows_text_only_for_non_vision_provider() -> None:
    app = ensure_app()
    controller = AppController(app)
    provider = build_provider(supports_vision=False)
    controller.settings = AppSettings(
        default_provider_id=provider.id,
        providers=[provider],
        hotkey="Ctrl+Shift+J",
    )
    started: list[tuple[str, object]] = []
    controller._start_request = lambda provider, request: started.append((provider.id, request.image_bytes_or_path))  # type: ignore[method-assign]
    controller.answer_window.queue_turn = lambda *args, **kwargs: None  # type: ignore[method-assign]

    error = controller._handle_capture_submission(None, "直接问个问题", QRect())

    assert error is None
    assert started == [(provider.id, None)]
    controller.shutdown()
    controller.hotkey_widget.dispose()


def test_app_controller_sets_custom_icons_for_app_and_settings_window() -> None:
    app = ensure_app()
    controller = AppController(app)

    assert app.windowIcon().isNull() is False
    assert controller.settings_window.windowIcon().isNull() is False

    controller.shutdown()
    controller.hotkey_widget.dispose()


def test_app_controller_builds_same_quick_actions_for_icon_menu() -> None:
    app = ensure_app()
    controller = AppController(app)

    menu = controller._build_quick_menu()
    labels = [action.text() for action in menu.actions() if not action.isSeparator()]

    assert labels == ["开始截图", "打开设置", "退出"]

    controller.shutdown()
    controller.hotkey_widget.dispose()


def test_app_controller_shutdown_hides_windows_and_disposes_hotkey() -> None:
    app = ensure_app()
    controller = AppController(app)
    controller.answer_window.show()
    controller.launch_panel.show()
    controller.overlay.show()
    controller.settings_window.show()

    controller.shutdown()

    assert controller.answer_window.isVisible() is False
    assert controller.launch_panel.isVisible() is False
    assert controller.overlay.isVisible() is False
    assert controller.settings_window.isVisible() is False
    assert controller.hotkey_widget.window_handle == 0
