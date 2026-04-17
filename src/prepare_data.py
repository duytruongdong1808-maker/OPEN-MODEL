from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

try:
    from .utils import (
        DEFAULT_BUILT_DATASET_PATH,
        DEFAULT_BASE_MODEL,
        DEFAULT_LOG_LEVEL,
        DEFAULT_SYSTEM_PROMPT,
        LOG_LEVEL_NAMES,
        ROOT_DIR,
        configure_logging,
        get_logger,
        load_tokenizer,
        read_jsonl,
        render_training_record,
        write_jsonl,
    )
except ImportError:
    from utils import (
        DEFAULT_BUILT_DATASET_PATH,
        DEFAULT_BASE_MODEL,
        DEFAULT_LOG_LEVEL,
        DEFAULT_SYSTEM_PROMPT,
        LOG_LEVEL_NAMES,
        ROOT_DIR,
        configure_logging,
        get_logger,
        load_tokenizer,
        read_jsonl,
        render_training_record,
        write_jsonl,
    )


DEFAULT_INPUT_PATH = DEFAULT_BUILT_DATASET_PATH
DEFAULT_OUTPUT_PATH = ROOT_DIR / "data" / "processed" / "train_sft.jsonl"
DEFAULT_VAL_OUTPUT_PATH = ROOT_DIR / "data" / "processed" / "val_sft.jsonl"


def validate_val_ratio(value: str) -> float:
    ratio = float(value)
    if not 0.0 <= ratio < 1.0:
        raise argparse.ArgumentTypeError("--val_ratio must be in the range [0.0, 1.0).")
    return ratio


def should_use_validation_split(row: dict[str, str], seed: int, val_ratio: float) -> bool:
    if val_ratio <= 0:
        return False

    split_key = json.dumps(
        {
            "instruction": row["instruction"],
            "input": row["input"],
            "output": row["output"],
        },
        ensure_ascii=False,
        sort_keys=True,
    )
    digest = hashlib.sha256(f"{seed}:{split_key}".encode("utf-8")).digest()
    bucket = int.from_bytes(digest[:8], byteorder="big") / float(1 << 64)
    return bucket < val_ratio


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Convert raw instruction JSONL into a processed SFT dataset."
    )
    parser.add_argument(
        "--input_path",
        type=Path,
        default=DEFAULT_INPUT_PATH,
        help="Path to the curated or raw JSONL file used for SFT preparation.",
    )
    parser.add_argument(
        "--output_path",
        type=Path,
        default=DEFAULT_OUTPUT_PATH,
        help="Path to write the processed training JSONL file.",
    )
    parser.add_argument(
        "--val_output_path",
        type=Path,
        default=DEFAULT_VAL_OUTPUT_PATH,
        help="Path to write the processed validation JSONL file.",
    )
    parser.add_argument(
        "--base_model",
        type=str,
        default=DEFAULT_BASE_MODEL,
        help="Base model used to load the tokenizer and chat template.",
    )
    parser.add_argument(
        "--model_revision",
        type=str,
        default=None,
        help="Optional Hugging Face revision override for the base model/tokenizer.",
    )
    parser.add_argument(
        "--system_prompt",
        type=str,
        default=DEFAULT_SYSTEM_PROMPT,
        help="System prompt to bake into processed prompts.",
    )
    parser.add_argument(
        "--val_ratio",
        type=validate_val_ratio,
        default=0.05,
        help="Deterministic validation split ratio. Use 0 for train-only smoke tests.",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=42,
        help="Seed used for deterministic train/validation assignment.",
    )
    parser.add_argument(
        "--log_level",
        type=str.upper,
        choices=LOG_LEVEL_NAMES,
        default=DEFAULT_LOG_LEVEL,
        help="Logging verbosity.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    logger = configure_logging(args.log_level)

    try:
        raw_rows = read_jsonl(args.input_path)
        tokenizer = load_tokenizer(args.base_model, model_revision=args.model_revision)
        logger.debug("prepare_data args: %s", vars(args))
        logger.debug(
            "Tokenizer config: %s",
            {
                "base_model": args.base_model,
                "model_revision": args.model_revision,
                "pad_token": tokenizer.pad_token,
                "pad_token_id": tokenizer.pad_token_id,
                "padding_side": tokenizer.padding_side,
            },
        )
        train_rows = []
        val_rows = []

        for index, row in enumerate(raw_rows, start=1):
            try:
                processed_row = render_training_record(
                    tokenizer=tokenizer,
                    row=row,
                    system_prompt=args.system_prompt,
                )
            except ValueError as exc:
                raise ValueError(f"Invalid training row at index {index}: {exc}") from exc
            if should_use_validation_split(processed_row, seed=args.seed, val_ratio=args.val_ratio):
                val_rows.append(processed_row)
            else:
                train_rows.append(processed_row)

        write_jsonl(args.output_path, train_rows)
        write_jsonl(args.val_output_path, val_rows)

        logger.info("Processed %s examples.", len(raw_rows))
        logger.info("Training rows: %s", len(train_rows))
        logger.info("Validation rows: %s", len(val_rows))
        logger.info("Saved processed train dataset to: %s", args.output_path.resolve())
        logger.info("Saved processed validation dataset to: %s", args.val_output_path.resolve())
        logger.info("Tokenizer/model template source: %s", args.base_model)
        if args.model_revision:
            logger.info("Tokenizer/model revision override: %s", args.model_revision)
        return 0
    except Exception as exc:
        get_logger().error("[prepare_data] Error: %s", exc)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
