from __future__ import annotations

import argparse
from pathlib import Path

from transformers import set_seed

try:
    from .email_triage import ParsedTriage, score_triage_output
    from .utils import (
        DEFAULT_BASE_MODEL,
        DEFAULT_LOG_LEVEL,
        DEFAULT_RUNTIME_PRESET,
        LOG_LEVEL_NAMES,
        ROOT_DIR,
        configure_logging,
        format_missing_dependency_error,
        get_default_adapter_path,
        generate_response,
        get_logger,
        get_runtime_preset_names,
        load_model_and_tokenizer,
        log_runtime_mode,
        read_jsonl,
        resolve_runtime_preset,
        should_default_to_4bit,
        str_to_bool,
    )
except ImportError:
    from email_triage import ParsedTriage, score_triage_output
    from utils import (
        DEFAULT_BASE_MODEL,
        DEFAULT_LOG_LEVEL,
        DEFAULT_RUNTIME_PRESET,
        LOG_LEVEL_NAMES,
        ROOT_DIR,
        configure_logging,
        format_missing_dependency_error,
        get_default_adapter_path,
        generate_response,
        get_logger,
        get_runtime_preset_names,
        load_model_and_tokenizer,
        log_runtime_mode,
        read_jsonl,
        resolve_runtime_preset,
        should_default_to_4bit,
        str_to_bool,
    )


DEFAULT_EVAL_PATH = ROOT_DIR / "data" / "eval" / "smoke.jsonl"


def parse_expected_triage(row: dict[str, object], *, index: int, path: Path) -> ParsedTriage:
    expected = row.get("expected")
    if not isinstance(expected, dict):
        raise ValueError(f"Eval row {index} in {path} must include an object 'expected'.")

    summary = expected.get("summary")
    priority = expected.get("priority")
    action_items = expected.get("action_items")
    deadlines = expected.get("deadlines")
    language = row.get("language", "en")

    if not isinstance(summary, str) or not summary.strip():
        raise ValueError(f"Eval row {index} in {path} has an invalid expected.summary.")
    if not isinstance(priority, str) or not priority.strip():
        raise ValueError(f"Eval row {index} in {path} has an invalid expected.priority.")
    if not isinstance(action_items, list) or not all(isinstance(item, str) and item.strip() for item in action_items):
        raise ValueError(f"Eval row {index} in {path} has an invalid expected.action_items.")
    if not isinstance(deadlines, list) or not all(isinstance(item, str) and item.strip() for item in deadlines):
        raise ValueError(f"Eval row {index} in {path} has an invalid expected.deadlines.")
    if not isinstance(language, str) or not language.strip():
        raise ValueError(f"Eval row {index} in {path} has an invalid language.")

    return ParsedTriage(
        summary=summary.strip(),
        priority=priority.strip(),
        action_items=[item.strip() for item in action_items],
        deadlines=[item.strip() for item in deadlines],
        language=language.strip(),
    )


def load_eval_prompts(path: Path) -> list[dict[str, object]]:
    rows = read_jsonl(path)
    prompts: list[dict[str, object]] = []
    for index, row in enumerate(rows, start=1):
        instruction = row.get("instruction")
        if not isinstance(instruction, str) or not instruction.strip():
            raise ValueError(f"Eval row {index} in {path} is missing a non-empty 'instruction'.")
        input_text = row.get("input", "") or ""
        if not isinstance(input_text, str):
            raise ValueError(f"Eval row {index} in {path} has a non-string 'input'.")
        prompt: dict[str, object] = {"instruction": instruction, "input": input_text}
        if "expected" in row:
            prompt["expected"] = parse_expected_triage(row, index=index, path=path)
            prompt["domain"] = row.get("domain")
            prompt["language"] = row.get("language")
        prompts.append(prompt)
    return prompts


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
    parser.add_argument("--adapter_path", type=Path, default=None)
    parser.add_argument(
        "--eval_path",
        type=Path,
        default=DEFAULT_EVAL_PATH,
        help="JSONL file with {instruction, input} rows to evaluate.",
    )
    parser.add_argument(
        "--no_adapter",
        action="store_true",
        help="Run the base model only, without loading the LoRA adapter.",
    )
    parser.add_argument(
        "--compare_base",
        action="store_true",
        help="For each prompt, print base-model and adapter outputs side by side.",
    )
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
    if args.adapter_path is None:
        args.adapter_path = get_default_adapter_path(args.base_model)
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

        if args.no_adapter and args.compare_base:
            raise ValueError("--no_adapter and --compare_base cannot be used together.")

        prompts = load_eval_prompts(args.eval_path)
        logger.info("Loaded %s eval prompts from %s.", len(prompts), args.eval_path)

        load_adapter = not args.no_adapter
        if load_adapter and not args.adapter_path.exists():
            raise FileNotFoundError(
                f"Adapter path not found: {args.adapter_path}. Train the model first, pass --adapter_path, or use --no_adapter."
            )

        model, tokenizer = load_model_and_tokenizer(
            base_model=args.base_model,
            model_revision=args.model_revision,
            adapter_path=str(args.adapter_path) if load_adapter else None,
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

        def run_prompt(sample: dict[str, str]) -> str:
            return generate_response(
                model=model,
                tokenizer=tokenizer,
                instruction=sample["instruction"],
                input_text=sample["input"],
                max_new_tokens=args.max_new_tokens,
                temperature=args.temperature,
                top_p=args.top_p,
            )

        triage_scores = []
        for index, sample in enumerate(prompts, start=1):
            logger.info("=== Sample %s ===", index)
            logger.info("Instruction: %s", sample["instruction"])
            if sample["input"]:
                logger.info("Input: %s", sample["input"])

            if args.compare_base:
                with model.disable_adapter():
                    base_response = run_prompt(sample)
                adapter_response = run_prompt(sample)
                logger.info("[base]    %s", base_response)
                logger.info("[adapter] %s", adapter_response)
            else:
                label = "base" if args.no_adapter else "adapter"
                response = run_prompt(sample)
                logger.info("[%s] %s", label, response)
                expected = sample.get("expected")
                if isinstance(expected, ParsedTriage):
                    score = score_triage_output(expected=expected, actual_text=response)
                    triage_scores.append(score)
                    logger.info(
                        "[triage-score] parse=%s summary=%s priority=%s actions=%s deadlines=%s",
                        score.parse_success,
                        score.summary_match,
                        score.priority_match,
                        score.action_items_match,
                        score.deadlines_match,
                    )

        if triage_scores:
            total = len(triage_scores)
            parse_successes = sum(1 for score in triage_scores if score.parse_success)
            summary_matches = sum(1 for score in triage_scores if score.summary_match)
            priority_matches = sum(1 for score in triage_scores if score.priority_match)
            action_matches = sum(1 for score in triage_scores if score.action_items_match)
            deadline_matches = sum(1 for score in triage_scores if score.deadlines_match)
            logger.info("=== Aggregate triage metrics ===")
            logger.info("Parse success: %s/%s", parse_successes, total)
            logger.info("Summary match: %s/%s", summary_matches, total)
            logger.info("Priority match: %s/%s", priority_matches, total)
            logger.info("Action items match: %s/%s", action_matches, total)
            logger.info("Deadlines match: %s/%s", deadline_matches, total)
        return 0
    except ModuleNotFoundError as exc:
        get_logger().error("[eval] Error: %s", format_missing_dependency_error(exc))
        return 1
    except Exception as exc:
        get_logger().error("[eval] Error: %s", exc)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
