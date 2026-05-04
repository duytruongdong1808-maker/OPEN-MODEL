from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Iterator, Protocol

from .config import OpenModelSettings
from .sampling import SamplingOverrides


class SupportsStreamingReply(Protocol):
    supports_constrained_decoding: bool

    def stream_reply(
        self,
        *,
        messages: list[dict[str, str]],
        system_prompt: str,
        mode: str = "chat",
        sampling_overrides: SamplingOverrides | None = None,
        response_format: dict[str, Any] | None = None,
        guided_json: dict[str, Any] | None = None,
    ) -> "GenerationStream": ...


@dataclass
class GenerationStream:
    chunks: Iterator[str]
    cancel: Callable[[], None]


class StubChatService:
    supports_constrained_decoding = False
    is_loaded = True

    def stream_reply(
        self,
        *,
        messages: list[dict[str, str]],
        system_prompt: str,
        mode: str = "chat",
        sampling_overrides: SamplingOverrides | None = None,
        response_format: dict[str, Any] | None = None,
        guided_json: dict[str, Any] | None = None,
    ) -> GenerationStream:
        del system_prompt, mode, sampling_overrides, response_format, guided_json
        last_user_message = next(
            (message["content"] for message in reversed(messages) if message["role"] == "user"),
            "",
        )
        text = (
            "Development inference is running without a loaded model. "
            f"I received: {last_user_message}"
        )
        return GenerationStream(chunks=iter([text]), cancel=lambda: None)


def build_chat_service(settings: OpenModelSettings) -> SupportsStreamingReply:
    if settings.open_model_skip_model_load:
        return StubChatService()
    if settings.open_model_inference_backend == "vllm":
        from ..inference.vllm import VLLMChatService

        return VLLMChatService(
            base_url=settings.open_model_vllm_url,
            model=settings.open_model_vllm_model,
            max_new_tokens=settings.open_model_max_new_tokens,
            temperature=settings.open_model_temperature,
            top_p=settings.open_model_top_p,
            frequency_penalty=settings.open_model_frequency_penalty,
            repetition_penalty=settings.open_model_repetition_penalty,
            timeout=settings.open_model_vllm_timeout_s,
            context_window=settings.open_model_vllm_context_window,
        )
    from ..inference.local import LocalModelChatService

    return LocalModelChatService(
        base_model=settings.open_model_base_model,
        adapter_path=settings.open_model_adapter_path,
        model_revision=settings.open_model_model_revision,
        load_in_4bit=settings.open_model_load_in_4bit,
        max_new_tokens=settings.open_model_max_new_tokens,
        temperature=settings.open_model_temperature,
        top_p=settings.open_model_top_p,
        repetition_penalty=settings.open_model_repetition_penalty,
    )
