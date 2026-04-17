from __future__ import annotations

import argparse
import random
from pathlib import Path
from typing import Any

try:
    from .curate_data import CORE_CHAT_TASK_TYPES
    from .utils import (
        DEFAULT_BUILT_DATASET_PATH,
        DEFAULT_CURATED_SEED_PATH,
        DEFAULT_CURATED_TRAIN_PATH,
        DEFAULT_LOG_LEVEL,
        LOG_LEVEL_NAMES,
        configure_logging,
        get_logger,
        read_jsonl,
        write_jsonl,
    )
except ImportError:
    from curate_data import CORE_CHAT_TASK_TYPES
    from utils import (
        DEFAULT_BUILT_DATASET_PATH,
        DEFAULT_CURATED_SEED_PATH,
        DEFAULT_CURATED_TRAIN_PATH,
        DEFAULT_LOG_LEVEL,
        LOG_LEVEL_NAMES,
        configure_logging,
        get_logger,
        read_jsonl,
        write_jsonl,
    )


TARGET_PROFILES = {
    "chat_core_vi_en": {
        "vi_core": 0.50,
        "en_core": 0.30,
        "mixed_utility": 0.20,
    }
}
MIXED_UTILITY_TASK_TYPES = {"summarize", "classification", "list_extraction", "generation"}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build a balanced chatbox training dataset from curated sources."
    )
    parser.add_argument(
        "--inputs",
        nargs="+",
        type=Path,
        default=[DEFAULT_CURATED_TRAIN_PATH, DEFAULT_CURATED_SEED_PATH],
        help="Curated JSONL inputs to mix into the final training dataset.",
    )
    parser.add_argument(
        "--output_path",
        type=Path,
        default=DEFAULT_BUILT_DATASET_PATH,
        help="Path to write the built chat-core dataset.",
    )
    parser.add_argument(
        "--target_profile",
        type=str,
        choices=sorted(TARGET_PROFILES),
        default="chat_core_vi_en",
        help="Sampling profile to use when balancing the dataset.",
    )
    parser.add_argument(
        "--total_rows",
        type=int,
        default=None,
        help="Optional target row count. Defaults to the number of unique keep rows.",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=42,
        help="Seed for deterministic sampling and output ordering.",
    )
    parser.add_argument(
        "--log_level",
        type=str.upper,
        choices=LOG_LEVEL_NAMES,
        default=DEFAULT_LOG_LEVEL,
        help="Logging verbosity.",
    )
    return parser.parse_args()


def row_identity(row: dict[str, Any]) -> tuple[str, str, str]:
    return (
        str(row.get("instruction", "")),
        str(row.get("input", "")),
        str(row.get("output", "")),
    )


def dedupe_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    deduped: dict[tuple[str, str, str], dict[str, Any]] = {}
    for row in rows:
        key = row_identity(row)
        current = deduped.get(key)
        if current is None or row.get("quality_score", 0) > current.get("quality_score", 0):
            deduped[key] = row
    return list(deduped.values())


def is_keep_row(row: dict[str, Any]) -> bool:
    return row.get("action", "keep") == "keep"


def is_vi_core(row: dict[str, Any]) -> bool:
    return row.get("language") == "vi" and row.get("task_type") in CORE_CHAT_TASK_TYPES


def is_en_core(row: dict[str, Any]) -> bool:
    return row.get("language") == "en" and row.get("task_type") in CORE_CHAT_TASK_TYPES


def is_mixed_utility(row: dict[str, Any]) -> bool:
    language = row.get("language")
    task_type = row.get("task_type")
    return language == "mixed" or (task_type in MIXED_UTILITY_TASK_TYPES and language in {"vi", "en", "unknown"})


def distribute_counts(total_rows: int, profile: dict[str, float]) -> dict[str, int]:
    counts = {bucket: int(total_rows * ratio) for bucket, ratio in profile.items()}
    assigned = sum(counts.values())
    remainders = sorted(
        ((total_rows * ratio - counts[bucket], bucket) for bucket, ratio in profile.items()),
        reverse=True,
    )
    for _, bucket in remainders[: total_rows - assigned]:
        counts[bucket] += 1
    return counts


def sample_bucket_rows(
    rows: list[dict[str, Any]],
    count: int,
    *,
    seed: int,
) -> list[dict[str, Any]]:
    if count <= 0 or not rows:
        return []

    rng = random.Random(seed)
    pool = list(rows)
    rng.shuffle(pool)
    if len(pool) >= count:
        return pool[:count]

    sampled = list(pool)
    while len(sampled) < count:
        sampled.append(rng.choice(pool))
    return sampled


def annotate_rows(rows: list[dict[str, Any]], bucket_name: str, profile_name: str) -> list[dict[str, Any]]:
    annotated = []
    for row in rows:
        updated = dict(row)
        updated["dataset_profile"] = profile_name
        updated["sampling_bucket"] = bucket_name
        annotated.append(updated)
    return annotated


def build_dataset_rows(
    rows: list[dict[str, Any]],
    *,
    target_profile: str = "chat_core_vi_en",
    total_rows: int | None = None,
    seed: int = 42,
) -> list[dict[str, Any]]:
    profile = TARGET_PROFILES[target_profile]
    keep_rows = dedupe_rows([row for row in rows if is_keep_row(row)])
    if not keep_rows:
        raise ValueError("No keep rows available to build the dataset.")

    resolved_total_rows = len(keep_rows) if total_rows is None else total_rows
    if resolved_total_rows <= 0:
        raise ValueError("--total_rows must be greater than 0.")

    buckets = {
        "vi_core": [row for row in keep_rows if is_vi_core(row)],
        "en_core": [row for row in keep_rows if is_en_core(row)],
        "mixed_utility": [row for row in keep_rows if is_mixed_utility(row)],
    }
    target_counts = distribute_counts(resolved_total_rows, profile)

    sampled_rows: list[dict[str, Any]] = []
    for index, (bucket_name, target_count) in enumerate(target_counts.items(), start=1):
        bucket_rows = sample_bucket_rows(buckets[bucket_name], target_count, seed=seed + index)
        sampled_rows.extend(annotate_rows(bucket_rows, bucket_name, target_profile))

    if len(sampled_rows) < resolved_total_rows:
        fallback_rows = sample_bucket_rows(keep_rows, resolved_total_rows - len(sampled_rows), seed=seed + 99)
        sampled_rows.extend(annotate_rows(fallback_rows, "fallback", target_profile))

    rng = random.Random(seed + 1234)
    rng.shuffle(sampled_rows)
    return sampled_rows[:resolved_total_rows]


def main() -> int:
    args = parse_args()
    logger = configure_logging(args.log_level)

    try:
        input_rows: list[dict[str, Any]] = []
        for input_path in args.inputs:
            rows = read_jsonl(input_path)
            logger.info("Loaded %s rows from %s", len(rows), input_path.resolve())
            input_rows.extend(rows)

        built_rows = build_dataset_rows(
            input_rows,
            target_profile=args.target_profile,
            total_rows=args.total_rows,
            seed=args.seed,
        )
        write_jsonl(args.output_path, built_rows)

        bucket_counts: dict[str, int] = {}
        for row in built_rows:
            bucket_name = row["sampling_bucket"]
            bucket_counts[bucket_name] = bucket_counts.get(bucket_name, 0) + 1

        logger.info("Built %s rows using profile %s.", len(built_rows), args.target_profile)
        logger.info("Sampling buckets: %s", bucket_counts)
        logger.info("Saved built dataset to: %s", args.output_path.resolve())
        return 0
    except Exception as exc:
        get_logger().error("[build_dataset] Error: %s", exc)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
