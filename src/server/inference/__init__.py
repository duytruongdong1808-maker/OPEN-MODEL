from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Iterator, Protocol

from ..core.sampling import SamplingOverrides


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
