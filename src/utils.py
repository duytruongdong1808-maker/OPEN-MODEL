from __future__ import annotations

import json
import logging
import platform
from pathlib import Path
from typing import Any


ROOT_DIR = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT_DIR / "data"
RAW_DATA_DIR = DATA_DIR / "raw"
PROCESSED_DATA_DIR = DATA_DIR / "processed"
CURATED_DATA_DIR = DATA_DIR / "curated"
DEFAULT_RAW_TRAIN_PATH = RAW_DATA_DIR / "train.jsonl"
DEFAULT_RAW_SAMPLE_PATH = RAW_DATA_DIR / "sample.jsonl"
DEFAULT_RAW_CHAT_SEED_PATH = RAW_DATA_DIR / "chat_vi_en_seed.jsonl"
DEFAULT_CURATED_TRAIN_PATH = CURATED_DATA_DIR / "train_curated.jsonl"
DEFAULT_CURATED_REVIEW_PATH = CURATED_DATA_DIR / "review_candidates.jsonl"
DEFAULT_CURATION_REPORT_PATH = CURATED_DATA_DIR / "curation_report.json"
DEFAULT_CURATED_SEED_PATH = CURATED_DATA_DIR / "chat_vi_en_seed_curated.jsonl"
DEFAULT_BUILT_DATASET_PATH = CURATED_DATA_DIR / "chat_core_vi_en_train.jsonl"
DEFAULT_BASE_MODEL = "Qwen/Qwen2.5-1.5B-Instruct"
DEFAULT_BASE_MODEL_REVISION = None
DEFAULT_SYSTEM_PROMPT = "You are a helpful, concise assistant."
DEFAULT_MAX_NEW_TOKENS = 256
DEFAULT_RUNTIME_PRESET = "rtx4060ti_8gb"
DEFAULT_LOG_LEVEL = "INFO"
LOG_LEVEL_NAMES = ("DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL")
LOGGER_NAME = "open_model"
WINDOWS_4BIT_DISABLED_MESSAGE = (
    "Running full-precision LoRA (4-bit disabled on Windows). Pass --load_in_4bit true to override."
)


def format_missing_dependency_error(exc: ModuleNotFoundError) -> str:
    dependency_name = exc.name or "a required package"
    install_hint = "Install project dependencies with `pip install -r requirements.txt`."
    if dependency_name == "torch":
        install_hint += " If you already installed them in the repo virtualenv, run the script with `.venv\\Scripts\\python.exe`."
    return f"Missing dependency: {dependency_name}. {install_hint}"


def configure_logging(log_level: str = DEFAULT_LOG_LEVEL) -> logging.Logger:
    normalized_level = log_level.upper()
    if normalized_level not in LOG_LEVEL_NAMES:
        raise ValueError(f"Unsupported log level: {log_level}")

    logging.basicConfig(
        level=getattr(logging, normalized_level),
        format="%(levelname)s | %(message)s",
        force=True,
    )
    logger = logging.getLogger(LOGGER_NAME)
    logger.setLevel(getattr(logging, normalized_level))
    return logger


def get_logger() -> logging.Logger:
    return logging.getLogger(LOGGER_NAME)


def should_show_windows_4bit_disabled_banner(
    load_in_4bit: bool,
    load_in_4bit_was_set: bool,
    system_name: str | None = None,
) -> bool:
    resolved_system_name = platform.system() if system_name is None else system_name
    return resolved_system_name == "Windows" and not load_in_4bit and not load_in_4bit_was_set


def log_runtime_mode(logger: logging.Logger, load_in_4bit: bool, load_in_4bit_was_set: bool) -> None:
    if should_show_windows_4bit_disabled_banner(load_in_4bit, load_in_4bit_was_set):
        logger.warning(WINDOWS_4BIT_DISABLED_MESSAGE)

    mode_name = "4-bit QLoRA" if load_in_4bit else "full-precision LoRA"
    logger.info("Runtime mode: %s", mode_name)


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


def read_yaml_dict(path: str | Path) -> dict[str, Any]:
    import yaml

    resolved_path = Path(path).expanduser().resolve()
    if not resolved_path.exists():
        raise FileNotFoundError(f"YAML file not found: {resolved_path}")

    with resolved_path.open("r", encoding="utf-8") as handle:
        data = yaml.safe_load(handle)

    if data is None:
        return {}
    if not isinstance(data, dict):
        raise ValueError(f"Expected a YAML mapping in: {resolved_path}")
    return data


def collect_cli_option_names(argv: list[str]) -> set[str]:
    option_names = set()
    for token in argv:
        if not token.startswith("--") or token == "--":
            continue
        option_names.add(token[2:].split("=", 1)[0].replace("-", "_"))
    return option_names


def coerce_required_text(value: Any, field_name: str) -> str:
    if not isinstance(value, str):
        raise ValueError(f"Each row must contain a string '{field_name}'.")

    text = value.strip()
    if not text:
        raise ValueError(f"Each row must contain a non-empty '{field_name}'.")

    return text


def coerce_optional_text(value: Any, field_name: str) -> str:
    if value is None:
        return ""
    if not isinstance(value, str):
        raise ValueError(f"Each row must contain a string '{field_name}'.")

    return value.strip()


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


def trim_chat_messages(messages: list[dict[str, str]], max_history_turns: int) -> list[dict[str, str]]:
    if max_history_turns <= 0:
        raise ValueError("max_history_turns must be greater than 0.")

    system_message = messages[0] if messages and messages[0].get("role") == "system" else None
    conversation_messages = messages[1:] if system_message else messages
    max_conversation_messages = max_history_turns * 2
    trimmed_conversation = conversation_messages[-max_conversation_messages:]
    if system_message:
        return [system_message, *trimmed_conversation]
    return trimmed_conversation


def resolve_model_revision(
    model_name: str = DEFAULT_BASE_MODEL,
    model_revision: str | None = None,
) -> str | None:
    if model_revision is not None:
        return model_revision
    if model_name == DEFAULT_BASE_MODEL:
        return DEFAULT_BASE_MODEL_REVISION
    return None


def load_tokenizer(
    model_name: str = DEFAULT_BASE_MODEL,
    model_revision: str | None = None,
):
    from transformers import AutoTokenizer

    tokenizer = AutoTokenizer.from_pretrained(
        model_name,
        revision=resolve_model_revision(model_name, model_revision),
        use_fast=True,
    )
    tokenizer.padding_side = "right"
    added_pad_token_count = 0
    if tokenizer.pad_token is None:
        added_pad_token_count = tokenizer.add_special_tokens({"pad_token": "<|pad|>"})
    tokenizer._open_model_added_pad_token_count = added_pad_token_count
    return tokenizer


def sync_model_tokenizer_padding(model, tokenizer) -> None:
    added_pad_token_count = getattr(tokenizer, "_open_model_added_pad_token_count", 0)
    if added_pad_token_count:
        model.resize_token_embeddings(len(tokenizer))
    if tokenizer.pad_token_id is not None:
        model.config.pad_token_id = tokenizer.pad_token_id
        if getattr(model, "generation_config", None) is not None:
            model.generation_config.pad_token_id = tokenizer.pad_token_id


def render_training_record(
    tokenizer,
    row: dict[str, Any],
    system_prompt: str = DEFAULT_SYSTEM_PROMPT,
) -> dict[str, str]:
    instruction = coerce_required_text(row.get("instruction"), "instruction")
    input_text = coerce_optional_text(row.get("input", ""), "input")
    output_text = coerce_required_text(row.get("output"), "output")

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

    # TRL's SFTTrainer prefers the prompt-completion path whenever both columns
    # are present. We intentionally omit a redundant `text` column so
    # completion-only loss is unambiguous and the trainer always builds a
    # completion mask for the answer tokens.
    return {
        "instruction": instruction,
        "input": input_text,
        "output": output_text,
        "prompt": prompt,
        "completion": completion,
    }


def get_compute_dtype():
    import torch

    if not torch.cuda.is_available():
        return torch.float32

    if torch.cuda.is_bf16_supported():
        return torch.bfloat16

    return torch.float16


def get_model_input_device(model):
    return next(model.parameters()).device


def should_default_to_4bit() -> bool:
    try:
        import torch
    except ModuleNotFoundError:
        return False

    return torch.cuda.is_available() and platform.system() != "Windows"


def get_runtime_preset_names() -> list[str]:
    return [DEFAULT_RUNTIME_PRESET]


def resolve_runtime_preset(
    preset_name: str | None,
    scope: str,
    fallback_defaults: dict[str, Any],
) -> dict[str, Any]:
    preset_defaults: dict[str, dict[str, Any]] = {
        DEFAULT_RUNTIME_PRESET: {
            "train": {
                "max_length": 512,
                "per_device_train_batch_size": 1,
                "gradient_accumulation_steps": 8,
                "load_in_4bit": should_default_to_4bit(),
            },
            "eval": {
                "max_new_tokens": 160,
                "load_in_4bit": should_default_to_4bit(),
            },
            "chat": {
                "max_new_tokens": 192,
                "load_in_4bit": should_default_to_4bit(),
            },
        }
    }

    resolved = dict(fallback_defaults)
    if not preset_name:
        return resolved

    if preset_name not in preset_defaults:
        raise ValueError(f"Unknown preset: {preset_name}")

    resolved.update(preset_defaults[preset_name].get(scope, {}))
    return resolved


def load_model_and_tokenizer(
    base_model: str = DEFAULT_BASE_MODEL,
    model_revision: str | None = None,
    adapter_path: str | None = None,
    load_in_4bit: bool | None = None,
):
    import torch
    from peft import PeftModel
    from transformers import AutoModelForCausalLM, BitsAndBytesConfig

    resolved_revision = resolve_model_revision(base_model, model_revision)
    tokenizer = load_tokenizer(base_model, model_revision=resolved_revision)
    model_kwargs: dict[str, Any] = {"trust_remote_code": False}
    compute_dtype = get_compute_dtype()
    use_4bit = should_default_to_4bit() if load_in_4bit is None else load_in_4bit

    if torch.cuda.is_available():
        if use_4bit:
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

    model = AutoModelForCausalLM.from_pretrained(
        base_model,
        revision=resolved_revision,
        **model_kwargs,
    )
    sync_model_tokenizer_padding(model, tokenizer)

    if adapter_path:
        adapter_dir = Path(adapter_path).expanduser().resolve()
        if not adapter_dir.exists():
            raise FileNotFoundError(f"Adapter directory not found: {adapter_dir}")
        model = PeftModel.from_pretrained(model, str(adapter_dir))

    model.eval()
    return model, tokenizer


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
    return generate_response_from_messages(
        model=model,
        tokenizer=tokenizer,
        messages=messages,
        max_new_tokens=max_new_tokens,
        temperature=temperature,
        top_p=top_p,
    )


def generate_response_from_messages(
    model,
    tokenizer,
    messages: list[dict[str, str]],
    max_new_tokens: int = DEFAULT_MAX_NEW_TOKENS,
    temperature: float = 0.2,
    top_p: float = 0.9,
) -> str:
    import torch

    with torch.inference_mode():
        prompt = tokenizer.apply_chat_template(
            messages,
            tokenize=False,
            add_generation_prompt=True,
        )
        inputs = tokenizer(prompt, return_tensors="pt")
        device = get_model_input_device(model)
        inputs = {key: value.to(device) for key, value in inputs.items()}
        do_sample = temperature > 0
        generate_kwargs = {
            **inputs,
            "max_new_tokens": max_new_tokens,
            "do_sample": do_sample,
            "pad_token_id": tokenizer.pad_token_id,
            "eos_token_id": tokenizer.eos_token_id,
        }
        if do_sample:
            generate_kwargs["temperature"] = temperature
            generate_kwargs["top_p"] = top_p

        generated = model.generate(**generate_kwargs)

        prompt_length = inputs["input_ids"].shape[-1]
        new_tokens = generated[0][prompt_length:]
        return tokenizer.decode(new_tokens, skip_special_tokens=True).strip()
