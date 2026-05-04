from __future__ import annotations

import asyncio
import json
import threading

import httpx
import pytest
import respx

from src.server.inference.vllm import VLLMChatService, current_vllm_metrics
from src.tools.errors import ToolError


def make_service() -> VLLMChatService:
    return VLLMChatService(
        base_url="http://vllm.test/v1",
        model="adapter",
        max_new_tokens=32,
        temperature=0.2,
        top_p=0.9,
        timeout=1.0,
    )


class BlockingSSEStream(httpx.AsyncByteStream):
    def __init__(self) -> None:
        self.closed = threading.Event()
        self.first_sent = threading.Event()

    async def __aiter__(self):
        yield b'data: {"choices":[{"delta":{"content":"first"}}]}\n\n'
        self.first_sent.set()
        while not self.closed.is_set():
            await asyncio.sleep(0.01)

    async def aclose(self) -> None:
        self.closed.set()


def test_stream_reply_parses_sse_text_chunks() -> None:
    with respx.mock(assert_all_called=True) as router:
        router.post("http://vllm.test/v1/chat/completions").mock(
            return_value=httpx.Response(
                200,
                content=(
                    b'data: {"choices":[{"delta":{"content":"Hello"}}]}\n\n'
                    b'data: {"choices":[{"delta":{"content":" world"}}]}\n\n'
                    b"data: [DONE]\n\n"
                ),
                headers={"content-type": "text/event-stream"},
            )
        )

        generation = make_service().stream_reply(
            messages=[{"role": "user", "content": "Say hi"}],
            system_prompt="You are concise.",
        )

        assert list(generation.chunks) == ["Hello", " world"]
        metrics = current_vllm_metrics.get()
        assert metrics is not None
        assert metrics.first_token_latency_ms is not None
        assert metrics.total_tokens == 2
        assert metrics.request_duration_ms is not None


def test_vllm_payload_includes_guided_json_when_provided() -> None:
    schema = {"type": "object", "properties": {"final": {"type": "string"}}}
    with respx.mock(assert_all_called=True) as router:
        route = router.post("http://vllm.test/v1/chat/completions").mock(
            return_value=httpx.Response(
                200,
                content=b"data: [DONE]\n\n",
                headers={"content-type": "text/event-stream"},
            )
        )

        generation = make_service().stream_reply(
            messages=[{"role": "user", "content": "Say hi"}],
            system_prompt="You are concise.",
            guided_json=schema,
        )

        assert list(generation.chunks) == []
        body = json.loads(route.calls.last.request.content)
        assert body["guided_json"] == schema


def test_vllm_payload_omits_guided_json_when_none() -> None:
    with respx.mock(assert_all_called=True) as router:
        route = router.post("http://vllm.test/v1/chat/completions").mock(
            return_value=httpx.Response(
                200,
                content=b"data: [DONE]\n\n",
                headers={"content-type": "text/event-stream"},
            )
        )

        generation = make_service().stream_reply(
            messages=[{"role": "user", "content": "Say hi"}],
            system_prompt="You are concise.",
            guided_json=None,
        )

        assert list(generation.chunks) == []
        body = json.loads(route.calls.last.request.content)
        assert "guided_json" not in body


def test_vllm_payload_trims_old_messages_to_fit_context() -> None:
    service = VLLMChatService(
        base_url="http://vllm.test/v1",
        model="adapter",
        max_new_tokens=128,
        temperature=0.2,
        top_p=0.9,
        timeout=1.0,
        context_window=256,
    )
    messages = [
        {"role": "user", "content": "old " * 400},
        {"role": "assistant", "content": "older answer " * 200},
        {"role": "user", "content": "latest question"},
    ]
    with respx.mock(assert_all_called=True) as router:
        route = router.post("http://vllm.test/v1/chat/completions").mock(
            return_value=httpx.Response(
                200,
                content=b"data: [DONE]\n\n",
                headers={"content-type": "text/event-stream"},
            )
        )

        generation = service.stream_reply(messages=messages, system_prompt="You are concise.")

        assert list(generation.chunks) == []
        body = json.loads(route.calls.last.request.content)
        sent_content = "\n".join(message["content"] for message in body["messages"])
        assert "latest question" in sent_content
        assert "old old old" not in sent_content
        assert body["max_tokens"] <= 128


def test_stream_reply_cancel_closes_response_stream() -> None:
    stream = BlockingSSEStream()
    with respx.mock(assert_all_called=True) as router:
        router.post("http://vllm.test/v1/chat/completions").mock(
            return_value=httpx.Response(
                200,
                stream=stream,
                headers={"content-type": "text/event-stream"},
            )
        )

        generation = make_service().stream_reply(
            messages=[{"role": "user", "content": "Keep going"}],
            system_prompt="You are concise.",
        )
        chunks = iter(generation.chunks)

        assert next(chunks) == "first"
        assert stream.first_sent.wait(timeout=1.0)
        generation.cancel()

        with pytest.raises(StopIteration):
            next(chunks)
        assert stream.closed.wait(timeout=1.0)


def test_stream_reply_maps_5xx_to_tool_error() -> None:
    with respx.mock(assert_all_called=True) as router:
        router.post("http://vllm.test/v1/chat/completions").mock(
            return_value=httpx.Response(503, content=b"loading")
        )

        generation = make_service().stream_reply(
            messages=[{"role": "user", "content": "Hello"}],
            system_prompt="You are concise.",
        )

        with pytest.raises(ToolError, match="503"):
            list(generation.chunks)


def test_stream_reply_maps_timeout_to_tool_error() -> None:
    with respx.mock(assert_all_called=True) as router:
        router.post("http://vllm.test/v1/chat/completions").mock(
            side_effect=httpx.ReadTimeout("timed out")
        )

        generation = make_service().stream_reply(
            messages=[{"role": "user", "content": "Hello"}],
            system_prompt="You are concise.",
        )

        with pytest.raises(ToolError, match="timed out"):
            list(generation.chunks)


def test_stream_reply_maps_4xx_to_value_error() -> None:
    with respx.mock(assert_all_called=True) as router:
        router.post("http://vllm.test/v1/chat/completions").mock(
            return_value=httpx.Response(400, content=b"bad model")
        )

        generation = make_service().stream_reply(
            messages=[{"role": "user", "content": "Hello"}],
            system_prompt="You are concise.",
        )

        with pytest.raises(ValueError, match="bad model"):
            list(generation.chunks)
