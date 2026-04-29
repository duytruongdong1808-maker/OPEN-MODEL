from __future__ import annotations

from dataclasses import dataclass, replace


@dataclass(frozen=True)
class SamplingOverrides:
    profile: str
    temperature: float | None = None
    top_p: float | None = None
    max_new_tokens: int | None = None
    repetition_penalty: float | None = None


SAMPLING_PROFILES: dict[str, SamplingOverrides] = {
    "chat": SamplingOverrides(
        profile="chat",
        temperature=0.7,
        top_p=0.92,
        max_new_tokens=512,
        repetition_penalty=1.05,
    ),
    "agent_json": SamplingOverrides(
        profile="agent_json",
        temperature=0.0,
        top_p=1.0,
        max_new_tokens=384,
        repetition_penalty=1.05,
    ),
    "mail_summary": SamplingOverrides(
        profile="mail_summary",
        temperature=0.3,
        top_p=0.9,
        max_new_tokens=512,
        repetition_penalty=1.05,
    ),
    "news": SamplingOverrides(
        profile="news",
        temperature=0.5,
        top_p=0.9,
        max_new_tokens=768,
        repetition_penalty=1.05,
    ),
}

MODE_TO_PROFILE = {
    "agent": "agent_json",
    "agent_json": "agent_json",
    "chat": "chat",
    "mail_summary": "mail_summary",
    "news": "news",
}


def resolve_sampling(
    *,
    mode: str = "chat",
    fallback_max_new_tokens: int,
    fallback_temperature: float,
    fallback_top_p: float,
    fallback_repetition_penalty: float,
    sampling_overrides: SamplingOverrides | None = None,
) -> SamplingOverrides:
    profile_name = MODE_TO_PROFILE.get(mode, "chat")
    profile = SAMPLING_PROFILES[profile_name]
    if sampling_overrides is not None:
        profile = replace(
            profile,
            profile=sampling_overrides.profile or profile.profile,
            temperature=(
                sampling_overrides.temperature
                if sampling_overrides.temperature is not None
                else profile.temperature
            ),
            top_p=sampling_overrides.top_p
            if sampling_overrides.top_p is not None
            else profile.top_p,
            max_new_tokens=(
                sampling_overrides.max_new_tokens
                if sampling_overrides.max_new_tokens is not None
                else profile.max_new_tokens
            ),
            repetition_penalty=(
                sampling_overrides.repetition_penalty
                if sampling_overrides.repetition_penalty is not None
                else profile.repetition_penalty
            ),
        )
    return SamplingOverrides(
        profile=profile.profile,
        temperature=profile.temperature
        if profile.temperature is not None
        else fallback_temperature,
        top_p=profile.top_p if profile.top_p is not None else fallback_top_p,
        max_new_tokens=(
            profile.max_new_tokens
            if profile.max_new_tokens is not None
            else fallback_max_new_tokens
        ),
        repetition_penalty=(
            profile.repetition_penalty
            if profile.repetition_penalty is not None
            else fallback_repetition_penalty
        ),
    )
