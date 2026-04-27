from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Iterator, Protocol


class SupportsStreamingReply(Protocol):
    def stream_reply(
        self,
        *,
        messages: list[dict[str, str]],
        system_prompt: str,
        mode: str = "chat",
    ) -> "GenerationStream": ...


@dataclass
class GenerationStream:
    chunks: Iterator[str]
    cancel: Callable[[], None]
