from __future__ import annotations

import uuid

from screen_qa_assistant.models import ChatMessage, ChatSession, ProviderProfile, VisionRequest


class SessionManager:
    def __init__(self) -> None:
        self.current_session: ChatSession | None = None

    def start_session(
        self,
        provider: ProviderProfile,
        screenshot_ref: bytes | str,
        question: str,
    ) -> ChatSession:
        if not provider.supports_vision:
            raise ValueError("当前模型不支持视觉输入")
        session = ChatSession(
            session_id=uuid.uuid4().hex,
            screenshot_path_or_memory_ref=screenshot_ref,
            messages=[ChatMessage(role="user", content=question)],
            provider_id=provider.id,
            input_mode="vision",
            status="idle",
        )
        self.current_session = session
        return session

    def start_text_session(self, provider: ProviderProfile, question: str) -> ChatSession:
        session = ChatSession(
            session_id=uuid.uuid4().hex,
            screenshot_path_or_memory_ref=None,
            messages=[ChatMessage(role="user", content=question)],
            provider_id=provider.id,
            input_mode="text",
            status="idle",
        )
        self.current_session = session
        return session

    def build_initial_request(self) -> VisionRequest:
        session = self.require_session()
        return VisionRequest(
            image_bytes_or_path=session.screenshot_path_or_memory_ref,
            question=session.messages[0].content,
            followup_messages=[],
            input_mode=session.input_mode,
        )

    def build_followup_request(self, question: str) -> VisionRequest:
        session = self.require_session()
        return VisionRequest(
            image_bytes_or_path=session.screenshot_path_or_memory_ref,
            question=question,
            followup_messages=list(session.messages),
            input_mode=session.input_mode,
        )

    def record_user_message(self, content: str) -> None:
        session = self.require_session()
        session.messages.append(ChatMessage(role="user", content=content))

    def record_assistant_message(self, content: str) -> None:
        session = self.require_session()
        session.messages.append(ChatMessage(role="assistant", content=content))

    def mark_streaming(self) -> None:
        self.require_session().status = "streaming"

    def mark_completed(self) -> None:
        self.require_session().status = "completed"

    def mark_error(self) -> None:
        self.require_session().status = "error"

    def cancel_current_session(self) -> None:
        if self.current_session is not None:
            self.current_session.status = "cancelled"

    def clear(self) -> None:
        self.current_session = None

    def require_session(self) -> ChatSession:
        if self.current_session is None:
            raise ValueError("当前没有活跃会话")
        return self.current_session
