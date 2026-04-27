from __future__ import annotations

from .inference import GenerationStream as GenerationStream
from .inference import SupportsStreamingReply as SupportsStreamingReply
from .settings import OpenModelSettings


def build_chat_service(settings: OpenModelSettings) -> SupportsStreamingReply:
    if settings.open_model_inference_backend == "vllm":
        from .inference.vllm import VLLMChatService

        return VLLMChatService(
            base_url=settings.open_model_vllm_url,
            model=settings.open_model_vllm_model,
            max_new_tokens=settings.open_model_max_new_tokens,
            temperature=settings.open_model_temperature,
            top_p=settings.open_model_top_p,
            timeout=settings.open_model_vllm_timeout_s,
        )
    from .inference.local import LocalModelChatService

    return LocalModelChatService(
        base_model=settings.open_model_base_model,
        adapter_path=settings.open_model_adapter_path,
        model_revision=settings.open_model_model_revision,
        load_in_4bit=settings.open_model_load_in_4bit,
        max_new_tokens=settings.open_model_max_new_tokens,
        temperature=settings.open_model_temperature,
        top_p=settings.open_model_top_p,
    )
