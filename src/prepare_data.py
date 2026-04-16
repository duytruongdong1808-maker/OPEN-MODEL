from __future__ import annotations

import argparse
import sys
from pathlib import Path

from utils import (
    DEFAULT_BASE_MODEL,
    DEFAULT_SYSTEM_PROMPT,
    ROOT_DIR,
    load_tokenizer,
    read_jsonl,
    render_training_record,
    write_jsonl,
)


DEFAULT_INPUT_PATH = ROOT_DIR / "data" / "raw" / "train.jsonl"
DEFAULT_OUTPUT_PATH = ROOT_DIR / "data" / "processed" / "train_sft.jsonl"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Convert raw instruction JSONL into a processed SFT dataset."
    )
    parser.add_argument(
        "--input_path",
        type=Path,
        default=DEFAULT_INPUT_PATH,
        help="Path to the raw train.jsonl file.",
    )
    parser.add_argument(
        "--output_path",
        type=Path,
        default=DEFAULT_OUTPUT_PATH,
        help="Path to write the processed JSONL file.",
    )
    parser.add_argument(
        "--base_model",
        type=str,
        default=DEFAULT_BASE_MODEL,
        help="Base model used to load the tokenizer and chat template.",
    )
    parser.add_argument(
        "--system_prompt",
        type=str,
        default=DEFAULT_SYSTEM_PROMPT,
        help="System prompt to bake into processed prompts.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    raw_rows = read_jsonl(args.input_path)
    tokenizer = load_tokenizer(args.base_model)
    processed_rows = []

    for index, row in enumerate(raw_rows, start=1):
        try:
            processed_rows.append(
                render_training_record(
                    tokenizer=tokenizer,
                    row=row,
                    system_prompt=args.system_prompt,
                )
            )
        except ValueError as exc:
            raise ValueError(f"Invalid training row at index {index}: {exc}") from exc

    write_jsonl(args.output_path, processed_rows)

    print(f"Processed {len(processed_rows)} examples.")
    print(f"Saved processed dataset to: {args.output_path.resolve()}")
    print(f"Tokenizer/model template source: {args.base_model}")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"[prepare_data] Error: {exc}", file=sys.stderr)
        sys.exit(1)
