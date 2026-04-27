from __future__ import annotations

from src.server.inference.local import LocalModelChatService
from src.server.inference.vllm import VLLMChatService
from src.server.runtime import build_chat_service
from src.server.settings import OpenModelSettings


def test_build_chat_service_returns_local_backend() -> None:
    service = build_chat_service(OpenModelSettings(open_model_inference_backend="local"))

    assert isinstance(service, LocalModelChatService)


def test_build_chat_service_returns_vllm_backend() -> None:
    service = build_chat_service(
        OpenModelSettings(
            open_model_inference_backend="vllm",
            open_model_vllm_url="http://vllm.test/v1",
            open_model_vllm_model="adapter",
        )
    )

    assert isinstance(service, VLLMChatService)
    assert service.base_url == "http://vllm.test/v1"
    assert service.model == "adapter"
