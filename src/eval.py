from __future__ import annotations

import argparse
from pathlib import Path

from transformers import set_seed

try:
    from .utils import (
        DEFAULT_BASE_MODEL,
        DEFAULT_LOG_LEVEL,
        DEFAULT_RUNTIME_PRESET,
        LOG_LEVEL_NAMES,
        ROOT_DIR,
        configure_logging,
        format_missing_dependency_error,
        generate_response,
        get_logger,
        get_runtime_preset_names,
        load_model_and_tokenizer,
        log_runtime_mode,
        resolve_runtime_preset,
        should_default_to_4bit,
        str_to_bool,
    )
except ImportError:
    from utils import (
        DEFAULT_BASE_MODEL,
        DEFAULT_LOG_LEVEL,
        DEFAULT_RUNTIME_PRESET,
        LOG_LEVEL_NAMES,
        ROOT_DIR,
        configure_logging,
        format_missing_dependency_error,
        generate_response,
        get_logger,
        get_runtime_preset_names,
        load_model_and_tokenizer,
        log_runtime_mode,
        resolve_runtime_preset,
        should_default_to_4bit,
        str_to_bool,
    )


DEFAULT_ADAPTER_PATH = ROOT_DIR / "outputs" / "qwen2.5_1.5b_lora" / "final_adapter"
DEFAULT_SAMPLE_PROMPTS = [
    {
        "instruction": "Summarize the value of LoRA in one sentence.",
        "input": "",
    },
    {
        "instruction": "Rewrite the message to sound more professional.",
        "input": "can you send me the report today? i need it before lunch",
    },
    {
        "instruction": "Explain QLoRA simply.",
        "input": "",
    },
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run a quick local inference check with the fine-tuned adapter.")
    parser.add_argument(
        "--preset",
        type=str,
        choices=get_runtime_preset_names(),
        default=None,
        help=f"Optional hardware preset, for example {DEFAULT_RUNTIME_PRESET}.",
    )
    parser.add_argument("--base_model", type=str, default=DEFAULT_BASE_MODEL)
    parser.add_argument("--adapter_path", type=Path, default=DEFAULT_ADAPTER_PATH)
    parser.add_argument("--max_new_tokens", type=int, default=None)
    parser.add_argument("--temperature", type=float, default=0.2)
    parser.add_argument("--top_p", type=float, default=0.9)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument(
        "--model_revision",
        type=str,
        default=None,
        help="Optional Hugging Face revision override for the base model.",
    )
    parser.add_argument(
        "--load_in_4bit",
        type=str_to_bool,
        default=None,
        help="Load the base model in 4-bit when CUDA is available.",
    )
    parser.add_argument(
        "--log_level",
        type=str.upper,
        choices=LOG_LEVEL_NAMES,
        default=DEFAULT_LOG_LEVEL,
        help="Logging verbosity.",
    )
    args = parser.parse_args()
    args.load_in_4bit_was_set = args.load_in_4bit is not None
    preset_defaults = resolve_runtime_preset(
        preset_name=args.preset,
        scope="eval",
        fallback_defaults={
            "max_new_tokens": 200,
            "load_in_4bit": should_default_to_4bit(),
        },
    )
    for field_name, field_value in preset_defaults.items():
        if getattr(args, field_name) is None:
            setattr(args, field_name, field_value)
    return args


def main() -> int:
    logger = configure_logging()

    try:
        args = parse_args()
        logger = configure_logging(args.log_level)
        set_seed(args.seed)
        if args.preset:
            logger.info("Using preset: %s", args.preset)
        log_runtime_mode(logger, args.load_in_4bit, args.load_in_4bit_was_set)

        if not args.adapter_path.exists():
            raise FileNotFoundError(
                f"Adapter path not found: {args.adapter_path}. Train the model first or pass --adapter_path."
            )

        model, tokenizer = load_model_and_tokenizer(
            base_model=args.base_model,
            model_revision=args.model_revision,
            adapter_path=str(args.adapter_path),
            load_in_4bit=args.load_in_4bit,
        )
        logger.debug("eval args: %s", vars(args))
        logger.debug(
            "Tokenizer config: %s",
            {
                "pad_token": tokenizer.pad_token,
                "pad_token_id": tokenizer.pad_token_id,
                "padding_side": tokenizer.padding_side,
                "model_revision": args.model_revision,
            },
        )
        logger.debug(
            "Model config: %s",
            {
                "model_type": getattr(model.config, "model_type", None),
                "pad_token_id": getattr(model.config, "pad_token_id", None),
                "vocab_size": getattr(model.config, "vocab_size", None),
            },
        )

        for index, sample in enumerate(DEFAULT_SAMPLE_PROMPTS, start=1):
            response = generate_response(
                model=model,
                tokenizer=tokenizer,
                instruction=sample["instruction"],
                input_text=sample["input"],
                max_new_tokens=args.max_new_tokens,
                temperature=args.temperature,
                top_p=args.top_p,
            )
            logger.info("=== Sample %s ===", index)
            logger.info("Instruction: %s", sample["instruction"])
            if sample["input"]:
                logger.info("Input: %s", sample["input"])
            logger.info("Response: %s", response)
        return 0
    except ModuleNotFoundError as exc:
        get_logger().error("[eval] Error: %s", format_missing_dependency_error(exc))
        return 1
    except Exception as exc:
        get_logger().error("[eval] Error: %s", exc)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
