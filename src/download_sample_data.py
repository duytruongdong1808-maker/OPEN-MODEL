from __future__ import annotations

import argparse
from pathlib import Path

from datasets import load_dataset

try:
    from .utils import (
        DEFAULT_LOG_LEVEL,
        LOG_LEVEL_NAMES,
        ROOT_DIR,
        configure_logging,
        get_logger,
        write_jsonl,
    )
except ImportError:
    from utils import (
        DEFAULT_LOG_LEVEL,
        LOG_LEVEL_NAMES,
        ROOT_DIR,
        configure_logging,
        get_logger,
        write_jsonl,
    )


DEFAULT_DATASET_NAME = "databricks/databricks-dolly-15k"
DEFAULT_DATASET_SPLIT = "train"
DEFAULT_MAX_ROWS = 1000
DEFAULT_OUTPUT_PATH = ROOT_DIR / "data" / "raw" / "train.jsonl"

SUPPORTED_DATASET_SCHEMAS = {
    "databricks/databricks-dolly-15k": {
        "instruction": "instruction",
        "input": "context",
        "output": "response",
    },
    "tatsu-lab/alpaca": {
        "instruction": "instruction",
        "input": "input",
        "output": "output",
    },
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Download a small openly licensed raw instruction sample into data/raw/train.jsonl."
    )
    parser.add_argument(
        "--dataset_name",
        type=str,
        default=DEFAULT_DATASET_NAME,
        choices=sorted(SUPPORTED_DATASET_SCHEMAS),
        help="Source dataset to sample from.",
    )
    parser.add_argument(
        "--dataset_split",
        type=str,
        default=DEFAULT_DATASET_SPLIT,
        help="Dataset split to read from.",
    )
    parser.add_argument(
        "--max_rows",
        type=int,
        default=DEFAULT_MAX_ROWS,
        help="Maximum number of rows to download.",
    )
    parser.add_argument(
        "--output_path",
        type=Path,
        default=DEFAULT_OUTPUT_PATH,
        help="Path to write normalized raw training data for later curation.",
    )
    parser.add_argument(
        "--cache_dir",
        type=Path,
        default=None,
        help="Optional Hugging Face cache directory for dataset downloads.",
    )
    parser.add_argument(
        "--log_level",
        type=str.upper,
        choices=LOG_LEVEL_NAMES,
        default=DEFAULT_LOG_LEVEL,
        help="Logging verbosity.",
    )
    return parser.parse_args()


def normalize_row(row: dict, dataset_name: str) -> dict[str, str] | None:
    schema = SUPPORTED_DATASET_SCHEMAS[dataset_name]
    normalized_row = {
        "instruction": str(row[schema["instruction"]]).strip(),
        "input": str(row.get(schema["input"], "") or "").strip(),
        "output": str(row[schema["output"]]).strip(),
    }
    if not normalized_row["instruction"] or not normalized_row["output"]:
        return None
    return normalized_row


def main() -> int:
    args = parse_args()
    logger = configure_logging(args.log_level)

    try:
        if args.max_rows <= 0:
            raise ValueError("--max_rows must be greater than 0.")

        load_kwargs = {}
        if args.cache_dir is not None:
            load_kwargs["cache_dir"] = str(args.cache_dir)

        sliced_split = f"{args.dataset_split}[:{args.max_rows}]"
        logger.debug("download_sample_data args: %s", vars(args))
        dataset = load_dataset(args.dataset_name, split=sliced_split, **load_kwargs)
        rows = []
        skipped_rows = 0
        for row in dataset:
            normalized_row = normalize_row(dict(row), args.dataset_name)
            if normalized_row is None:
                skipped_rows += 1
                continue
            rows.append(normalized_row)

        write_jsonl(args.output_path, rows)

        logger.info("Downloaded %s rows from %s (%s).", len(rows), args.dataset_name, sliced_split)
        if skipped_rows:
            logger.warning("Skipped %s rows with empty instruction or output.", skipped_rows)
        logger.info("Saved normalized training data to: %s", args.output_path.resolve())
        return 0
    except Exception as exc:
        get_logger().error("[download_sample_data] Error: %s", exc)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
