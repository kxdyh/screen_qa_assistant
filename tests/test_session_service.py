from __future__ import annotations

import pytest

from screen_qa_assistant.models import ChatMessage, ProviderProfile
from screen_qa_assistant.services.session_manager import SessionManager


def test_session_manager_rejects_non_vision_provider() -> None:
    manager = SessionManager()
    provider = ProviderProfile(
        id="text-only",
        name="Text Only",
        base_url="https://example.com/v1",
        api_key_ref=None,
        model="text-only-model",
        supports_vision=False,
        timeout_seconds=30,
        temperature=0.1,
        max_tokens=512,
    )

    with pytest.raises(ValueError):
        manager.start_session(provider, b"img", "帮我看一下这个界面")


def test_session_manager_reuses_messages_for_followup() -> None:
    manager = SessionManager()
    provider = ProviderProfile(
        id="vision",
        name="Vision",
        base_url="https://example.com/v1",
        api_key_ref=None,
        model="vision-model",
        supports_vision=True,
        timeout_seconds=30,
        temperature=0.1,
        max_tokens=512,
    )

    session = manager.start_session(provider, b"img", "先总结截图内容")
    manager.record_assistant_message("第一轮回答")
    request = manager.build_followup_request("再指出一个风险点")

    assert session.messages == [
        ChatMessage(role="user", content="先总结截图内容"),
        ChatMessage(role="assistant", content="第一轮回答"),
    ]
    assert request.followup_messages == session.messages
    assert request.question == "再指出一个风险点"


def test_session_manager_supports_text_only_session() -> None:
    manager = SessionManager()
    provider = ProviderProfile(
        id="text-only",
        name="Text Only",
        base_url="https://example.com/v1",
        api_key_ref=None,
        model="text-only-model",
        supports_vision=False,
        enable_reasoning=True,
        timeout_seconds=30,
        temperature=0.1,
        max_tokens=512,
    )

    session = manager.start_text_session(provider, "直接总结今天会议")
    request = manager.build_initial_request()

    assert session.status == "idle"
    assert session.screenshot_path_or_memory_ref is None
    assert request.image_bytes_or_path is None
    assert request.question == "直接总结今天会议"
