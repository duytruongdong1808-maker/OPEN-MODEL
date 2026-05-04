from __future__ import annotations

from src.server.inference.local import LocalModelChatService
from src.server.inference.vllm import VLLMChatService
from src.server.runtime import StubChatService, build_chat_service
from src.server.settings import OpenModelSettings


def test_build_chat_service_returns_stub_when_model_load_is_skipped() -> None:
    service = build_chat_service(OpenModelSettings(open_model_skip_model_load=True))

    assert isinstance(service, StubChatService)


def test_build_chat_service_returns_local_backend() -> None:
    service = build_chat_service(
        OpenModelSettings(open_model_inference_backend="local", open_model_skip_model_load=False)
    )

    assert isinstance(service, LocalModelChatService)


def test_build_chat_service_returns_vllm_backend() -> None:
    service = build_chat_service(
        OpenModelSettings(
            open_model_inference_backend="vllm",
            open_model_skip_model_load=False,
            open_model_vllm_url="http://vllm.test/v1",
            open_model_vllm_model="adapter",
            open_model_vllm_context_window=1536,
            open_model_frequency_penalty=0.4,
            open_model_repetition_penalty=1.08,
        )
    )

    assert isinstance(service, VLLMChatService)
    assert service.base_url == "http://vllm.test/v1"
    assert service.model == "adapter"
    assert service.context_window == 1536
    assert service.frequency_penalty == 0.4
    assert service.repetition_penalty == 1.08
