from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter, field_validator, model_validator


class ChatMessage(BaseModel):
    role: Literal["system", "user", "assistant"]
    content: str = Field(min_length=1)


class ProviderProfile(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    id: str = Field(min_length=1)
    name: str = Field(min_length=1)
    base_url: str
    api_key_ref: str | None = None
    model: str = Field(min_length=1)
    supports_vision: bool = True
    enable_reasoning: bool = False
    timeout_seconds: int = Field(default=60, gt=0)
    temperature: float = Field(default=0.2, ge=0, le=2)
    max_tokens: int = Field(default=2048, gt=0)

    @field_validator("base_url", mode="before")
    @classmethod
    def normalize_base_url(cls, value: str) -> str:
        normalized = TypeAdapter(str).validate_python(value).strip()
        if not normalized:
            raise ValueError("base_url 不能为空")
        if not normalized.startswith(("http://", "https://")):
            raise ValueError("base_url 必须以 http:// 或 https:// 开头")
        return normalized.rstrip("/")


class AppSettings(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    default_provider_id: str | None = None
    hotkey: str = Field(default="Ctrl+Shift+A", min_length=1)
    save_enabled: bool = False
    save_dir: str | None = None
    cleanup_policy_days: int | None = Field(default=14, gt=0)
    window_prefs: dict[str, Any] = Field(default_factory=dict)
    providers: list[ProviderProfile] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_default_provider(self) -> "AppSettings":
        if self.providers:
            provider_ids = {provider.id for provider in self.providers}
            if self.default_provider_id is None:
                self.default_provider_id = self.providers[0].id
            if self.default_provider_id not in provider_ids:
                raise ValueError("default_provider_id 必须存在于 providers 列表中")
        return self

    @classmethod
    def default(cls, save_dir: str | None = None) -> "AppSettings":
        return cls(
            default_provider_id=None,
            hotkey="Ctrl+Shift+A",
            save_enabled=False,
            save_dir=save_dir,
            cleanup_policy_days=14,
            window_prefs={"answer_window": {"width": 420, "height": 520}},
            providers=[],
        )


class ChatSession(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    session_id: str
    screenshot_path_or_memory_ref: bytes | str | None = None
    messages: list[ChatMessage] = Field(default_factory=list)
    provider_id: str
    input_mode: Literal["vision", "text"] = "vision"
    status: Literal["idle", "streaming", "completed", "error", "cancelled"] = "idle"


class VisionRequest(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    image_bytes_or_path: bytes | str | None = None
    question: str = Field(min_length=1)
    followup_messages: list[ChatMessage] = Field(default_factory=list)
    input_mode: Literal["vision", "text"] = "vision"
