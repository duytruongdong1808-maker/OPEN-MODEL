from __future__ import annotations

import asyncio
import contextvars
import json
import queue
import threading
import time
from dataclasses import dataclass
from typing import Any, AsyncIterator, Iterator

import httpx

from ...tools.errors import ToolError
from ...utils import DEFAULT_SYSTEM_PROMPT
from ..core.sampling import SamplingOverrides, resolve_sampling
from ..observability.metrics import (
    INFERENCE_FIRST_TOKEN_SECONDS,
    INFERENCE_REQUEST_DURATION_SECONDS,
    INFERENCE_TOKENS_TOTAL,
)
from . import GenerationStream


@dataclass
class VLLMRequestMetrics:
    first_token_latency_ms: float | None = None
    total_tokens: int = 0
    request_duration_ms: float | None = None
    sampling_profile: str = "chat"


current_vllm_metrics: contextvars.ContextVar[VLLMRequestMetrics | None] = contextvars.ContextVar(
    "current_vllm_metrics", default=None
)


_SENTINEL = object()


class VLLMChatService:
    supports_constrained_decoding = True

    def __init__(
        self,
        *,
        base_url: str,
        model: str,
        max_new_tokens: int,
        temperature: float,
        top_p: float,
        frequency_penalty: float = 0.0,
        repetition_penalty: float = 1.05,
        timeout: float = 120.0,
        context_window: int = 1536,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.max_new_tokens = max_new_tokens
        self.temperature = temperature
        self.top_p = top_p
        self.frequency_penalty = frequency_penalty
        self.repetition_penalty = repetition_penalty
        self.timeout = timeout
        self.context_window = context_window
        self._limits = httpx.Limits(max_connections=50, max_keepalive_connections=20)

    async def check_ready(self) -> bool:
        try:
            async with httpx.AsyncClient(
                limits=self._limits,
                timeout=httpx.Timeout(self.timeout),
            ) as client:
                response = await client.get(f"{self.base_url}/models")
            return response.status_code == 200
        except httpx.HTTPError:
            return False

    def stream_reply(
        self,
        *,
        messages: list[dict[str, str]],
        system_prompt: str = DEFAULT_SYSTEM_PROMPT,
        mode: str = "chat",
        sampling_overrides: SamplingOverrides | None = None,
        response_format: dict[str, Any] | None = None,
        guided_json: dict[str, Any] | None = None,
    ) -> GenerationStream:
        payload = self._build_payload(
            messages=messages,
            system_prompt=system_prompt,
            mode=mode,
            sampling_overrides=sampling_overrides,
            response_format=response_format,
            guided_json=guided_json,
        )
        output: queue.Queue[str | BaseException | object] = queue.Queue()
        cancel_event = threading.Event()
        response_holder: dict[str, httpx.Response] = {}
        loop_holder: dict[str, asyncio.AbstractEventLoop] = {}
        metrics = VLLMRequestMetrics()
        metrics.sampling_profile = str(payload.get("sampling_profile") or mode)
        payload.pop("sampling_profile", None)
        current_vllm_metrics.set(metrics)

        async def run_stream() -> None:
            loop_holder["loop"] = asyncio.get_running_loop()
            started_at = time.perf_counter()
            try:
                async with httpx.AsyncClient(
                    limits=self._limits,
                    timeout=httpx.Timeout(self.timeout),
                ) as client:
                    async with client.stream(
                        "POST",
                        f"{self.base_url}/chat/completions",
                        json=payload,
                    ) as response:
                        response_holder["response"] = response
                        await self._raise_for_status(response)
                        async for text in self._iter_sse_text(
                            response, cancel_event, started_at, metrics
                        ):
                            output.put(text)
            except ValueError as exc:
                output.put(exc)
            except ToolError as exc:
                output.put(exc)
            except (httpx.TimeoutException, httpx.RequestError) as exc:
                output.put(ToolError(f"vLLM inference request failed: {exc}"))
            except Exception as exc:  # pragma: no cover - defensive guard for stream internals
                output.put(ToolError(f"vLLM inference stream failed: {exc}"))
            finally:
                metrics.request_duration_ms = (time.perf_counter() - started_at) * 1000
                if metrics.first_token_latency_ms is not None:
                    INFERENCE_FIRST_TOKEN_SECONDS.labels(backend="vllm", model=self.model).observe(
                        metrics.first_token_latency_ms / 1000
                    )
                if metrics.total_tokens:
                    INFERENCE_TOKENS_TOTAL.labels(backend="vllm", model=self.model).inc(
                        metrics.total_tokens
                    )
                INFERENCE_REQUEST_DURATION_SECONDS.labels(backend="vllm", model=self.model).observe(
                    metrics.request_duration_ms / 1000
                )
                output.put(_SENTINEL)

        worker = threading.Thread(target=lambda: asyncio.run(run_stream()), daemon=True)
        worker.start()

        def cancel() -> None:
            cancel_event.set()
            response = response_holder.get("response")
            loop = loop_holder.get("loop")
            if response is not None and loop is not None and loop.is_running():
                asyncio.run_coroutine_threadsafe(response.aclose(), loop)

        def iter_chunks() -> Iterator[str]:
            try:
                while True:
                    item = output.get()
                    if item is _SENTINEL:
                        break
                    if isinstance(item, BaseException):
                        raise item
                    yield str(item)
            finally:
                if worker.is_alive():
                    cancel()
                    worker.join(timeout=0.5)

        return GenerationStream(chunks=iter_chunks(), cancel=cancel)

    def _build_payload(
        self,
        *,
        messages: list[dict[str, str]],
        system_prompt: str,
        mode: str = "chat",
        sampling_overrides: SamplingOverrides | None = None,
        response_format: dict[str, Any] | None = None,
        guided_json: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        sampling = resolve_sampling(
            mode=mode,
            fallback_max_new_tokens=self.max_new_tokens,
            fallback_temperature=self.temperature,
            fallback_top_p=self.top_p,
            fallback_repetition_penalty=self.repetition_penalty,
            sampling_overrides=sampling_overrides,
        )
        chat_messages: list[dict[str, str]] = []
        stripped_system_prompt = system_prompt.strip()
        if stripped_system_prompt:
            chat_messages.append({"role": "system", "content": stripped_system_prompt})
        chat_messages.extend(
            {"role": message["role"], "content": message["content"]} for message in messages
        )
        chat_messages = self._fit_messages_to_context(chat_messages)
        prompt_tokens = self._estimate_messages_tokens(chat_messages)
        available_completion_tokens = max(32, self.context_window - prompt_tokens - 32)
        max_tokens = min(
            sampling.max_new_tokens,
            max(self.max_new_tokens, self.context_window // 2),
            available_completion_tokens,
        )
        payload: dict[str, Any] = {
            "model": self.model,
            "messages": chat_messages,
            "max_tokens": max_tokens,
            "repetition_penalty": sampling.repetition_penalty,
            "sampling_profile": sampling.profile,
            "stream": True,
        }
        if self.frequency_penalty:
            payload["frequency_penalty"] = self.frequency_penalty
        if (sampling.temperature or 0) > 0:
            payload["temperature"] = sampling.temperature
            payload["top_p"] = sampling.top_p
        else:
            payload["temperature"] = 0
        if guided_json is not None:
            payload["guided_json"] = guided_json
        if response_format is not None:
            payload["response_format"] = response_format
        return payload

    def _fit_messages_to_context(self, messages: list[dict[str, str]]) -> list[dict[str, str]]:
        if not messages:
            return messages
        reserved_completion_tokens = min(self.max_new_tokens, max(64, self.context_window // 4))
        prompt_budget = max(64, self.context_window - reserved_completion_tokens - 128)
        system_messages = [message for message in messages if message["role"] == "system"]
        non_system_messages = [message for message in messages if message["role"] != "system"]
        if not non_system_messages:
            return messages

        kept: list[dict[str, str]] = [non_system_messages[-1]]
        for message in reversed(non_system_messages[:-1]):
            candidate = system_messages + [message] + list(reversed(kept))
            if self._estimate_messages_tokens(candidate) > prompt_budget:
                continue
            kept.append(message)

        fitted = system_messages + list(reversed(kept))
        if self._estimate_messages_tokens(fitted) <= self.context_window - 64:
            return fitted

        # The latest user message alone is too large for this GPU profile. Keep the end of it,
        # where users usually place their concrete question, and leave room for a short answer.
        last = dict(non_system_messages[-1])
        system_tokens = self._estimate_messages_tokens(system_messages)
        available_tokens = max(
            64, self.context_window - system_tokens - reserved_completion_tokens - 128
        )
        available_chars = max(256, available_tokens)
        if len(last["content"]) > available_chars:
            last["content"] = (
                "[Earlier content truncated to fit the local model context.]\n"
                + last["content"][-available_chars:]
            )
        return system_messages + [last]

    @staticmethod
    def _estimate_messages_tokens(messages: list[dict[str, str]]) -> int:
        return sum(len(message.get("content", "")) + 8 for message in messages) + 4

    async def _raise_for_status(self, response: httpx.Response) -> None:
        if response.status_code < 400:
            return
        body = await response.aread()
        detail = body.decode("utf-8", errors="replace").strip() or response.reason_phrase
        if 400 <= response.status_code < 500:
            raise ValueError(f"vLLM rejected the inference request: {detail}")
        raise ToolError(f"vLLM inference service error ({response.status_code}): {detail}")

    async def _iter_sse_text(
        self,
        response: httpx.Response,
        cancel_event: threading.Event,
        started_at: float,
        metrics: VLLMRequestMetrics,
    ) -> AsyncIterator[str]:
        saw_usage = False
        async for line in response.aiter_lines():
            if cancel_event.is_set():
                await response.aclose()
                break
            stripped = line.strip()
            if not stripped or stripped.startswith(":") or not stripped.startswith("data:"):
                continue
            data = stripped.removeprefix("data:").strip()
            if data == "[DONE]":
                break
            try:
                payload = json.loads(data)
            except json.JSONDecodeError:
                continue
            usage = payload.get("usage")
            if isinstance(usage, dict) and usage.get("completion_tokens") is not None:
                saw_usage = True
                metrics.total_tokens = int(usage["completion_tokens"])
            for choice in payload.get("choices") or []:
                delta = choice.get("delta") if isinstance(choice, dict) else None
                content = delta.get("content") if isinstance(delta, dict) else None
                if content:
                    if metrics.first_token_latency_ms is None:
                        metrics.first_token_latency_ms = (time.perf_counter() - started_at) * 1000
                    if not saw_usage:
                        metrics.total_tokens += 1
                    yield str(content)
