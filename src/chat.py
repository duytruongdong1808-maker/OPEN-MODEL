from __future__ import annotations

import argparse
from pathlib import Path

try:
    from .utils import (
        DEFAULT_BASE_MODEL,
        DEFAULT_LOG_LEVEL,
        DEFAULT_RUNTIME_PRESET,
        DEFAULT_SYSTEM_PROMPT,
        LOG_LEVEL_NAMES,
        configure_logging,
        format_user_message,
        format_missing_dependency_error,
        get_default_adapter_path,
        generate_response_from_messages,
        get_logger,
        get_runtime_preset_names,
        load_model_and_tokenizer,
        log_runtime_mode,
        resolve_runtime_preset,
        trim_chat_messages,
        should_default_to_4bit,
        str_to_bool,
    )
except ImportError:
    from utils import (
        DEFAULT_BASE_MODEL,
        DEFAULT_LOG_LEVEL,
        DEFAULT_RUNTIME_PRESET,
        DEFAULT_SYSTEM_PROMPT,
        LOG_LEVEL_NAMES,
        configure_logging,
        format_user_message,
        format_missing_dependency_error,
        get_default_adapter_path,
        generate_response_from_messages,
        get_logger,
        get_runtime_preset_names,
        load_model_and_tokenizer,
        log_runtime_mode,
        resolve_runtime_preset,
        trim_chat_messages,
        should_default_to_4bit,
        str_to_bool,
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Start a basic local chat loop with the fine-tuned model."
    )
    parser.add_argument(
        "--preset",
        type=str,
        choices=get_runtime_preset_names(),
        default=None,
        help=f"Optional hardware preset, for example {DEFAULT_RUNTIME_PRESET}.",
    )
    parser.add_argument("--base_model", type=str, default=DEFAULT_BASE_MODEL)
    parser.add_argument("--adapter_path", type=Path, default=None)
    parser.add_argument("--max_new_tokens", type=int, default=None)
    parser.add_argument("--temperature", type=float, default=0.2)
    parser.add_argument("--top_p", type=float, default=0.9)
    parser.add_argument("--system_prompt", type=str, default=DEFAULT_SYSTEM_PROMPT)
    parser.add_argument("--max_history_turns", type=int, default=6)
    parser.add_argument("--model_revision", type=str, default=None)
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
        scope="chat",
        fallback_defaults={
            "max_new_tokens": 256,
            "load_in_4bit": should_default_to_4bit(),
        },
    )
    for field_name, field_value in preset_defaults.items():
        if getattr(args, field_name) is None:
            setattr(args, field_name, field_value)
    if args.adapter_path is None:
        args.adapter_path = get_default_adapter_path(args.base_model)
    return args


def main() -> int:
    logger = configure_logging()

    try:
        args = parse_args()
        logger = configure_logging(args.log_level)
        if args.preset:
            logger.info("Using preset: %s", args.preset)
        log_runtime_mode(logger, args.load_in_4bit, args.load_in_4bit_was_set)
        if args.max_history_turns <= 0:
            raise ValueError("--max_history_turns must be greater than 0.")

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
        logger.debug("chat args: %s", vars(args))
        logger.debug(
            "Tokenizer config: %s",
            {
                "pad_token": tokenizer.pad_token,
                "pad_token_id": tokenizer.pad_token_id,
                "padding_side": tokenizer.padding_side,
            },
        )
        logger.debug(
            "Model config: %s",
            {
                "model_type": getattr(model.config, "model_type", None),
                "pad_token_id": getattr(model.config, "pad_token_id", None),
            },
        )

        logger.info("Local chat is ready.")
        logger.info("Commands: /reset, /system <prompt>, exit, quit")

        current_system_prompt = args.system_prompt.strip()
        messages = [{"role": "system", "content": current_system_prompt}]
        while True:
            user_text = input("You: ").strip()
            if not user_text:
                continue
            if user_text.lower() in {"exit", "quit"}:
                break
            if user_text == "/reset":
                messages = [{"role": "system", "content": current_system_prompt}]
                logger.info("Conversation reset.")
                continue
            if user_text == "/system" or user_text.startswith("/system "):
                new_system_prompt = user_text[len("/system") :].strip()
                if not new_system_prompt:
                    logger.warning("Usage: /system <prompt>")
                    continue
                current_system_prompt = new_system_prompt
                messages = [{"role": "system", "content": current_system_prompt}]
                logger.info("System prompt updated and conversation reset.")
                continue

            messages.append({"role": "user", "content": format_user_message(user_text)})
            response = generate_response_from_messages(
                model=model,
                tokenizer=tokenizer,
                messages=messages,
                max_new_tokens=args.max_new_tokens,
                temperature=args.temperature,
                top_p=args.top_p,
            )
            messages.append({"role": "assistant", "content": response})
            messages = trim_chat_messages(messages, args.max_history_turns)
            logger.info("Assistant: %s", response)
        return 0
    except KeyboardInterrupt:
        get_logger().info("[chat] Stopped by user.")
        return 0
    except ModuleNotFoundError as exc:
        get_logger().error("[chat] Error: %s", format_missing_dependency_error(exc))
        return 1
    except Exception as exc:
        get_logger().error("[chat] Error: %s", exc)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
