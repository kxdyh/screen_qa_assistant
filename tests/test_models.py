from __future__ import annotations

import pytest

from screen_qa_assistant.models import AppSettings, ProviderProfile


def build_provider() -> ProviderProfile:
    return ProviderProfile(
        id="demo-provider",
        name="Demo Provider",
        base_url="https://example.com/v1/",
        api_key_ref="cred-demo-provider",
        model="demo-model",
        supports_vision=True,
        session_only=False,
        enable_reasoning=True,
        timeout_seconds=45,
        temperature=0.2,
        max_tokens=1024,
    )


def test_provider_profile_normalizes_url_and_round_trips() -> None:
    provider = build_provider()

    assert str(provider.base_url) == "https://example.com/v1"
    assert provider.enable_reasoning is True

    cloned = ProviderProfile.model_validate_json(provider.model_dump_json())
    assert cloned == provider


def test_provider_profile_round_trip_preserves_session_only_flag() -> None:
    provider = build_provider().model_copy(update={"session_only": True})

    cloned = ProviderProfile.model_validate_json(provider.model_dump_json())

    assert cloned.session_only is True


def test_app_settings_requires_existing_default_provider() -> None:
    provider = build_provider()

    settings = AppSettings(
        default_provider_id=provider.id,
        hotkey="Ctrl+Shift+A",
        save_enabled=False,
        save_dir=None,
        cleanup_policy_days=30,
        window_prefs={"answer_window": {"width": 420}},
        providers=[provider],
    )
    assert settings.default_provider_id == provider.id

    with pytest.raises(ValueError):
        AppSettings(
            default_provider_id="missing",
            hotkey="Ctrl+Shift+A",
            save_enabled=False,
            save_dir=None,
            cleanup_policy_days=30,
            window_prefs={},
            providers=[provider],
        )
