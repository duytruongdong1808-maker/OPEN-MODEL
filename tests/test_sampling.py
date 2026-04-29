from __future__ import annotations

from src.server.core.sampling import SamplingOverrides, resolve_sampling
from src.server.inference.vllm import VLLMChatService


def test_resolve_sampling_maps_modes_to_profiles() -> None:
    chat = resolve_sampling(
        mode="chat",
        fallback_max_new_tokens=256,
        fallback_temperature=0.2,
        fallback_top_p=0.9,
        fallback_repetition_penalty=1.0,
    )
    agent = resolve_sampling(
        mode="agent",
        fallback_max_new_tokens=256,
        fallback_temperature=0.2,
        fallback_top_p=0.9,
        fallback_repetition_penalty=1.0,
    )
    mail = resolve_sampling(
        mode="mail_summary",
        fallback_max_new_tokens=256,
        fallback_temperature=0.2,
        fallback_top_p=0.9,
        fallback_repetition_penalty=1.0,
    )

    assert chat.profile == "chat"
    assert chat.temperature == 0.7
    assert chat.max_new_tokens == 512
    assert agent.profile == "agent_json"
    assert agent.temperature == 0.0
    assert agent.max_new_tokens == 384
    assert mail.profile == "mail_summary"
    assert mail.temperature == 0.3
    assert mail.max_new_tokens == 512


def test_sampling_overrides_win_over_profile_values() -> None:
    sampling = resolve_sampling(
        mode="chat",
        fallback_max_new_tokens=256,
        fallback_temperature=0.2,
        fallback_top_p=0.9,
        fallback_repetition_penalty=1.0,
        sampling_overrides=SamplingOverrides(profile="test", temperature=0.1),
    )

    assert sampling.profile == "test"
    assert sampling.temperature == 0.1
    assert sampling.max_new_tokens == 512


def test_vllm_payload_uses_mode_specific_sampling() -> None:
    service = VLLMChatService(
        base_url="http://test/v1",
        model="adapter",
        max_new_tokens=256,
        temperature=0.2,
        top_p=0.9,
        repetition_penalty=1.0,
    )

    payload = service._build_payload(
        messages=[{"role": "user", "content": "hello"}],
        system_prompt="system",
        mode="news",
    )

    assert payload["max_tokens"] == 768
    assert payload["temperature"] == 0.5
    assert payload["top_p"] == 0.9
    assert payload["repetition_penalty"] == 1.05
    assert payload["sampling_profile"] == "news"
