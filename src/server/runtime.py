from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from threading import Event, Lock, Thread
from typing import Callable, Iterator, Protocol

from transformers import TextIteratorStreamer
from transformers.generation.stopping_criteria import StoppingCriteria, StoppingCriteriaList

from ..utils import (
    DEFAULT_BASE_MODEL,
    DEFAULT_MAX_NEW_TOKENS,
    DEFAULT_SYSTEM_PROMPT,
    ROOT_DIR,
    format_user_message,
    get_model_input_device,
    load_model_and_tokenizer,
)


LOGGER = logging.getLogger("open_model.server")


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


class StopOnCancel(StoppingCriteria):
    def __init__(self, cancel_event: Event) -> None:
        self.cancel_event = cancel_event

    def __call__(self, input_ids, scores, **kwargs):
        import torch

        return torch.tensor([self.cancel_event.is_set()], device=input_ids.device)


class LocalModelChatService:
    def __init__(
        self,
        *,
        base_model: str = DEFAULT_BASE_MODEL,
        adapter_path: str | Path | None = None,
        model_revision: str | None = None,
        load_in_4bit: bool | None = None,
        max_new_tokens: int = DEFAULT_MAX_NEW_TOKENS,
        temperature: float = 0.2,
        top_p: float = 0.9,
    ) -> None:
        self.base_model = base_model
        self.adapter_path = self._resolve_adapter_path(adapter_path)
        self.model_revision = model_revision
        self.load_in_4bit = load_in_4bit
        self.max_new_tokens = max_new_tokens
        self.temperature = temperature
        self.top_p = top_p
        self._model = None
        self._tokenizer = None
        self._load_lock = Lock()

    def _resolve_adapter_path(self, adapter_path: str | Path | None) -> str | None:
        if adapter_path is None:
            default_adapter = ROOT_DIR / "outputs" / "qwen2.5_1.5b_lora" / "final_adapter"
            if default_adapter.exists():
                return str(default_adapter)
            LOGGER.warning("Adapter path not found; the API will fall back to the base model only.")
            return None
        return str(Path(adapter_path).expanduser().resolve())

    def _ensure_loaded(self) -> tuple[object, object]:
        if self._model is not None and self._tokenizer is not None:
            return self._model, self._tokenizer

        with self._load_lock:
            if self._model is None or self._tokenizer is None:
                self._model, self._tokenizer = load_model_and_tokenizer(
                    base_model=self.base_model,
                    model_revision=self.model_revision,
                    adapter_path=self.adapter_path,
                    load_in_4bit=self.load_in_4bit,
                )
        return self._model, self._tokenizer

    @property
    def is_loaded(self) -> bool:
        return self._model is not None and self._tokenizer is not None

    def stream_reply(
        self,
        *,
        messages: list[dict[str, str]],
        system_prompt: str = DEFAULT_SYSTEM_PROMPT,
        mode: str = "chat",
    ) -> GenerationStream:
        del mode
        model, tokenizer = self._ensure_loaded()
        prompt_messages = [{"role": "system", "content": system_prompt.strip()}]
        for message in messages:
            if message["role"] == "user":
                prompt_messages.append({"role": "user", "content": format_user_message(message["content"])})
            else:
                prompt_messages.append({"role": "assistant", "content": message["content"]})

        prompt = tokenizer.apply_chat_template(
            prompt_messages,
            tokenize=False,
            add_generation_prompt=True,
        )
        inputs = tokenizer(prompt, return_tensors="pt")
        device = get_model_input_device(model)
        inputs = {key: value.to(device) for key, value in inputs.items()}
        cancel_event = Event()
        error_holder: list[Exception] = []
        streamer = TextIteratorStreamer(
            tokenizer,
            skip_prompt=True,
            skip_special_tokens=True,
            clean_up_tokenization_spaces=False,
        )
        do_sample = self.temperature > 0

        def run_generation() -> None:
            import torch

            generate_kwargs = {
                **inputs,
                "streamer": streamer,
                "max_new_tokens": self.max_new_tokens,
                "do_sample": do_sample,
                "pad_token_id": tokenizer.pad_token_id,
                "eos_token_id": tokenizer.eos_token_id,
                "stopping_criteria": StoppingCriteriaList([StopOnCancel(cancel_event)]),
            }
            if do_sample:
                generate_kwargs["temperature"] = self.temperature
                generate_kwargs["top_p"] = self.top_p

            try:
                with torch.inference_mode():
                    model.generate(**generate_kwargs)
            except Exception as exc:  # pragma: no cover - exercised through API tests
                error_holder.append(exc)
                streamer.end()

        worker = Thread(target=run_generation, daemon=True)
        worker.start()

        def iter_chunks() -> Iterator[str]:
            try:
                for text in streamer:
                    if text:
                        yield text
            finally:
                worker.join(timeout=0.2)
            if error_holder:
                raise error_holder[0]

        return GenerationStream(chunks=iter_chunks(), cancel=cancel_event.set)
