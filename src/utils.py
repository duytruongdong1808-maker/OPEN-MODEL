from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import torch
from peft import PeftModel
from transformers import AutoModelForCausalLM, AutoTokenizer, BitsAndBytesConfig


ROOT_DIR = Path(__file__).resolve().parents[1]
DEFAULT_BASE_MODEL = "HuggingFaceTB/SmolLM2-1.7B-Instruct"
DEFAULT_SYSTEM_PROMPT = "You are a helpful, concise assistant."
DEFAULT_MAX_NEW_TOKENS = 256


def str_to_bool(value: str | bool) -> bool:
    if isinstance(value, bool):
        return value

    lowered = value.strip().lower()
    if lowered in {"1", "true", "yes", "y"}:
        return True
    if lowered in {"0", "false", "no", "n"}:
        return False
    raise ValueError(f"Could not parse boolean value: {value}")


def ensure_parent_dir(path: str | Path) -> None:
    Path(path).expanduser().resolve().parent.mkdir(parents=True, exist_ok=True)


def read_jsonl(path: str | Path) -> list[dict[str, Any]]:
    path = Path(path).expanduser().resolve()
    if not path.exists():
        raise FileNotFoundError(f"JSONL file not found: {path}")

    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line_number, raw_line in enumerate(handle, start=1):
            line = raw_line.strip()
            if not line:
                continue

            try:
                row = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(f"Invalid JSON on line {line_number} in {path}") from exc

            if not isinstance(row, dict):
                raise ValueError(f"Expected a JSON object on line {line_number} in {path}")

            rows.append(row)

    if not rows:
        raise ValueError(f"No rows found in JSONL file: {path}")

    return rows


def write_jsonl(path: str | Path, rows: list[dict[str, Any]]) -> None:
    ensure_parent_dir(path)
    output_path = Path(path).expanduser().resolve()

    with output_path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")


def format_user_message(instruction: str, input_text: str = "") -> str:
    instruction = instruction.strip()
    input_text = input_text.strip()

    if not instruction:
        raise ValueError("Instruction cannot be empty.")

    sections = [f"Instruction:\n{instruction}"]
    if input_text:
        sections.append(f"Input:\n{input_text}")

    return "\n\n".join(sections)


def build_messages(
    instruction: str,
    input_text: str = "",
    system_prompt: str = DEFAULT_SYSTEM_PROMPT,
) -> list[dict[str, str]]:
    return [
        {"role": "system", "content": system_prompt.strip()},
        {"role": "user", "content": format_user_message(instruction, input_text)},
    ]


def load_tokenizer(model_name: str = DEFAULT_BASE_MODEL):
    tokenizer = AutoTokenizer.from_pretrained(model_name, use_fast=True)
    if tokenizer.pad_token is None and tokenizer.eos_token is not None:
        tokenizer.pad_token = tokenizer.eos_token
    return tokenizer


def render_training_record(
    tokenizer,
    row: dict[str, Any],
    system_prompt: str = DEFAULT_SYSTEM_PROMPT,
) -> dict[str, str]:
    instruction = str(row.get("instruction", "")).strip()
    input_text = str(row.get("input", "")).strip()
    output_text = str(row.get("output", "")).strip()

    if not instruction:
        raise ValueError("Each row must contain a non-empty 'instruction'.")
    if not output_text:
        raise ValueError("Each row must contain a non-empty 'output'.")

    messages = build_messages(
        instruction=instruction,
        input_text=input_text,
        system_prompt=system_prompt,
    )
    prompt = tokenizer.apply_chat_template(
        messages,
        tokenize=False,
        add_generation_prompt=True,
    )
    completion = output_text + (tokenizer.eos_token or "")

    return {
        "instruction": instruction,
        "input": input_text,
        "output": output_text,
        "prompt": prompt,
        "completion": completion,
        "text": prompt + completion,
    }


def get_compute_dtype() -> torch.dtype:
    if not torch.cuda.is_available():
        return torch.float32

    if torch.cuda.is_bf16_supported():
        return torch.bfloat16

    return torch.float16


def get_model_input_device(model) -> torch.device:
    return next(model.parameters()).device


def load_model_and_tokenizer(
    base_model: str = DEFAULT_BASE_MODEL,
    adapter_path: str | None = None,
    load_in_4bit: bool = True,
):
    tokenizer = load_tokenizer(base_model)
    model_kwargs: dict[str, Any] = {"trust_remote_code": False}
    compute_dtype = get_compute_dtype()

    if torch.cuda.is_available():
        if load_in_4bit:
            model_kwargs["quantization_config"] = BitsAndBytesConfig(
                load_in_4bit=True,
                bnb_4bit_quant_type="nf4",
                bnb_4bit_compute_dtype=compute_dtype,
                bnb_4bit_use_double_quant=True,
            )
        else:
            model_kwargs["torch_dtype"] = compute_dtype

        model_kwargs["device_map"] = "auto"
    else:
        model_kwargs["torch_dtype"] = torch.float32

    model = AutoModelForCausalLM.from_pretrained(base_model, **model_kwargs)

    if adapter_path:
        adapter_dir = Path(adapter_path).expanduser().resolve()
        if not adapter_dir.exists():
            raise FileNotFoundError(f"Adapter directory not found: {adapter_dir}")
        model = PeftModel.from_pretrained(model, str(adapter_dir))

    model.eval()
    return model, tokenizer


@torch.inference_mode()
def generate_response(
    model,
    tokenizer,
    instruction: str,
    input_text: str = "",
    system_prompt: str = DEFAULT_SYSTEM_PROMPT,
    max_new_tokens: int = DEFAULT_MAX_NEW_TOKENS,
    temperature: float = 0.2,
    top_p: float = 0.9,
) -> str:
    messages = build_messages(
        instruction=instruction,
        input_text=input_text,
        system_prompt=system_prompt,
    )
    prompt = tokenizer.apply_chat_template(
        messages,
        tokenize=False,
        add_generation_prompt=True,
    )
    inputs = tokenizer(prompt, return_tensors="pt")
    device = get_model_input_device(model)
    inputs = {key: value.to(device) for key, value in inputs.items()}

    generated = model.generate(
        **inputs,
        max_new_tokens=max_new_tokens,
        do_sample=temperature > 0,
        temperature=temperature,
        top_p=top_p,
        pad_token_id=tokenizer.pad_token_id,
        eos_token_id=tokenizer.eos_token_id,
    )

    prompt_length = inputs["input_ids"].shape[-1]
    new_tokens = generated[0][prompt_length:]
    return tokenizer.decode(new_tokens, skip_special_tokens=True).strip()
