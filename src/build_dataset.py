from __future__ import annotations

import argparse
import random
from pathlib import Path
from typing import Any

try:
    from .curate_data import CORE_CHAT_TASK_TYPES
    from .utils import (
        DEFAULT_BUILT_DATASET_PATH,
        DEFAULT_CURATED_MAIL_TRIAGE_SEED_PATH,
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
        DEFAULT_CURATED_MAIL_TRIAGE_SEED_PATH,
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
    },
    "chat_core_vi_en_mail": {
        "vi_core": 0.35,
        "en_core": 0.20,
        "mixed_utility": 0.15,
        "email_triage": 0.30,
    },
    "mail_triage_en_ops_support": {
        "mail_en_ops_support": 0.50,
        "mail_vi_ops_support": 0.20,
        "mail_other": 0.10,
        "general_concise": 0.10,
        "mixed_utility": 0.10,
    },
    "chat_balanced_with_mail": {
        "chat_vi_general": 0.25,
        "chat_en_general": 0.20,
        "mail_en_all_domains": 0.25,
        "mail_vi": 0.10,
        "mail_mixed": 0.10,
        "mixed_utility": 0.10,
    },
    "chat_mail_triage_v51": {
        "mail_strict_triage": 0.20,
        "mail_summary_anchor": 0.10,
        "mail_priority_calibration": 0.08,
        "mail_blocker_rules": 0.08,
        "mail_deadline_repair": 0.09,
        "chat_vi_general": 0.18,
        "chat_en_general": 0.17,
        "mixed_utility": 0.10,
    },
    "chat_mail_summary_v52": {
        "mail_summary_focus": 0.18,
        "mail_strict_triage": 0.10,
        "mail_action_deadline": 0.08,
        "mail_priority_deadline": 0.05,
        "mail_blocker_rules": 0.04,
        "chat_bilingual": 0.12,
        "chat_refusal": 0.10,
        "chat_code_factual": 0.12,
        "chat_vi_general": 0.11,
        "chat_en_general": 0.06,
        "mixed_utility": 0.04,
    },
}
MIXED_UTILITY_TASK_TYPES = {"summarize", "classification", "list_extraction", "generation"}
EMAIL_TRIAGE_SOURCE = "seed_mail_triage_vi_en"
PRIORITY_MAIL_DOMAINS = {"ops", "support"}
GENERAL_CONCISE_TASK_TYPES = {"qa", "rewrite"}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build a balanced chatbox training dataset from curated sources."
    )
    parser.add_argument(
        "--inputs",
        nargs="+",
        type=Path,
        default=[
            DEFAULT_CURATED_TRAIN_PATH,
            DEFAULT_CURATED_SEED_PATH,
            DEFAULT_CURATED_MAIL_TRIAGE_SEED_PATH,
        ],
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
        default="chat_mail_summary_v52",
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
    return language == "mixed" or (
        task_type in MIXED_UTILITY_TASK_TYPES and language in {"vi", "en", "unknown"}
    )


def is_email_triage(row: dict[str, Any]) -> bool:
    return row.get("source") == EMAIL_TRIAGE_SOURCE


def is_chat_vi_general(row: dict[str, Any]) -> bool:
    return (
        not is_email_triage(row)
        and row.get("language") == "vi"
        and row.get("task_type") in CORE_CHAT_TASK_TYPES
    )


def is_chat_en_general(row: dict[str, Any]) -> bool:
    return (
        not is_email_triage(row)
        and row.get("language") == "en"
        and row.get("task_type") in CORE_CHAT_TASK_TYPES
    )


def is_chat_category(row: dict[str, Any], categories: set[str]) -> bool:
    return not is_email_triage(row) and row.get("category") in categories


def is_chat_bilingual(row: dict[str, Any]) -> bool:
    return is_chat_category(row, {"bilingual_switch"})


def is_chat_refusal(row: dict[str, Any]) -> bool:
    return is_chat_category(row, {"refusal"}) or (
        not is_email_triage(row) and row.get("task_type") == "safety_refusal"
    )


def is_chat_code_factual(row: dict[str, Any]) -> bool:
    return is_chat_category(row, {"code_math", "factual_qa", "technical_explain"})


def is_mail_en_all_domains(row: dict[str, Any]) -> bool:
    return is_email_triage(row) and row.get("language") == "en"


def is_mail_vi(row: dict[str, Any]) -> bool:
    return is_email_triage(row) and row.get("language") == "vi"


def is_mail_mixed(row: dict[str, Any]) -> bool:
    return is_email_triage(row) and row.get("language") == "mixed"


def is_general_concise(row: dict[str, Any]) -> bool:
    if is_email_triage(row):
        return False
    if row.get("task_type") not in GENERAL_CONCISE_TASK_TYPES:
        return False
    output_word_count = len(str(row.get("output", "")).split())
    input_length = len(str(row.get("input", "")))
    return output_word_count <= 80 and input_length <= 700


def is_mail_en_ops_support(row: dict[str, Any]) -> bool:
    return (
        is_email_triage(row)
        and row.get("language") == "en"
        and row.get("domain") in PRIORITY_MAIL_DOMAINS
    )


def is_mail_vi_ops_support(row: dict[str, Any]) -> bool:
    return (
        is_email_triage(row)
        and row.get("language") == "vi"
        and row.get("domain") in PRIORITY_MAIL_DOMAINS
    )


def is_mail_other(row: dict[str, Any]) -> bool:
    return is_email_triage(row) and row.get("domain") not in PRIORITY_MAIL_DOMAINS


def has_task_variant(row: dict[str, Any], variants: set[str]) -> bool:
    return is_email_triage(row) and row.get("task_variant") in variants


def is_mail_strict_triage(row: dict[str, Any]) -> bool:
    return has_task_variant(
        row,
        {
            "full_triage",
            "full_triage_strict_schema",
            "json_to_full_triage_schema",
        },
    )


def is_mail_summary_focus(row: dict[str, Any]) -> bool:
    return has_task_variant(
        row,
        {
            "summarize_email",
            "anchored_summary_schema",
            "summary_contract_schema",
            "repair_generic_summary_schema",
        },
    )


def is_mail_summary_anchor(row: dict[str, Any]) -> bool:
    return has_task_variant(row, {"anchored_summary_schema", "summary_contract_schema"})


def is_mail_priority_calibration(row: dict[str, Any]) -> bool:
    return has_task_variant(row, {"classify_only", "priority_calibration_schema"})


def is_mail_blocker_rule(row: dict[str, Any]) -> bool:
    return has_task_variant(row, {"conditional_blocker_schema", "required_blocker_schema"})


def is_mail_deadline_repair(row: dict[str, Any]) -> bool:
    return has_task_variant(
        row,
        {
            "deadline_carryover_schema",
            "repair_deadline_bullet_schema",
            "repair_missing_actions_deadlines_schema",
        },
    )


def is_mail_action_deadline(row: dict[str, Any]) -> bool:
    return has_task_variant(
        row,
        {
            "extract_actions_and_deadlines",
            "canonicalize_action_schema",
            "repair_missing_actions_deadlines_schema",
        },
    )


def is_mail_priority_deadline(row: dict[str, Any]) -> bool:
    return has_task_variant(
        row,
        {
            "classify_only",
            "deadline_carryover_schema",
            "repair_deadline_bullet_schema",
            "find_deadline",
        },
    )


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


def annotate_rows(
    rows: list[dict[str, Any]], bucket_name: str, profile_name: str
) -> list[dict[str, Any]]:
    annotated = []
    for row in rows:
        updated = dict(row)
        updated["dataset_profile"] = profile_name
        updated["sampling_bucket"] = bucket_name
        annotated.append(updated)
    return annotated


def build_profile_buckets(
    keep_rows: list[dict[str, Any]],
    *,
    target_profile: str,
) -> dict[str, list[dict[str, Any]]]:
    if target_profile == "mail_triage_en_ops_support":
        ordered_buckets = [
            ("mail_en_ops_support", is_mail_en_ops_support),
            ("mail_vi_ops_support", is_mail_vi_ops_support),
            ("mail_other", is_mail_other),
            ("general_concise", is_general_concise),
            ("mixed_utility", lambda row: not is_email_triage(row) and is_mixed_utility(row)),
        ]
        buckets = {bucket_name: [] for bucket_name, _ in ordered_buckets}
        for row in keep_rows:
            for bucket_name, predicate in ordered_buckets:
                if predicate(row):
                    buckets[bucket_name].append(row)
                    break
        return buckets

    if target_profile == "chat_balanced_with_mail":
        ordered_buckets = [
            ("chat_vi_general", is_chat_vi_general),
            ("chat_en_general", is_chat_en_general),
            ("mail_en_all_domains", is_mail_en_all_domains),
            ("mail_vi", is_mail_vi),
            ("mail_mixed", is_mail_mixed),
            ("mixed_utility", lambda row: not is_email_triage(row) and is_mixed_utility(row)),
        ]
        buckets = {bucket_name: [] for bucket_name, _ in ordered_buckets}
        for row in keep_rows:
            for bucket_name, predicate in ordered_buckets:
                if predicate(row):
                    buckets[bucket_name].append(row)
                    break
        return buckets

    if target_profile == "chat_mail_triage_v51":
        ordered_buckets = [
            ("mail_strict_triage", is_mail_strict_triage),
            ("mail_summary_anchor", is_mail_summary_anchor),
            ("mail_priority_calibration", is_mail_priority_calibration),
            ("mail_blocker_rules", is_mail_blocker_rule),
            ("mail_deadline_repair", is_mail_deadline_repair),
            ("chat_vi_general", is_chat_vi_general),
            ("chat_en_general", is_chat_en_general),
            ("mixed_utility", lambda row: not is_email_triage(row) and is_mixed_utility(row)),
        ]
        buckets = {bucket_name: [] for bucket_name, _ in ordered_buckets}
        for row in keep_rows:
            for bucket_name, predicate in ordered_buckets:
                if predicate(row):
                    buckets[bucket_name].append(row)
                    break
        return buckets

    if target_profile == "chat_mail_summary_v52":
        ordered_buckets = [
            ("mail_summary_focus", is_mail_summary_focus),
            ("mail_strict_triage", is_mail_strict_triage),
            ("mail_action_deadline", is_mail_action_deadline),
            ("mail_priority_deadline", is_mail_priority_deadline),
            ("mail_blocker_rules", is_mail_blocker_rule),
            ("chat_bilingual", is_chat_bilingual),
            ("chat_refusal", is_chat_refusal),
            ("chat_code_factual", is_chat_code_factual),
            ("chat_vi_general", is_chat_vi_general),
            ("chat_en_general", is_chat_en_general),
            ("mixed_utility", lambda row: not is_email_triage(row) and is_mixed_utility(row)),
        ]
        buckets = {bucket_name: [] for bucket_name, _ in ordered_buckets}
        for row in keep_rows:
            for bucket_name, predicate in ordered_buckets:
                if predicate(row):
                    buckets[bucket_name].append(row)
                    break
        return buckets

    return {
        "vi_core": [row for row in keep_rows if is_vi_core(row)],
        "en_core": [row for row in keep_rows if is_en_core(row)],
        "mixed_utility": [row for row in keep_rows if is_mixed_utility(row)],
        "email_triage": [row for row in keep_rows if is_email_triage(row)],
    }


def build_dataset_rows(
    rows: list[dict[str, Any]],
    *,
    target_profile: str = "mail_triage_en_ops_support",
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

    buckets = build_profile_buckets(keep_rows, target_profile=target_profile)
    target_counts = distribute_counts(resolved_total_rows, profile)

    sampled_rows: list[dict[str, Any]] = []
    for index, (bucket_name, target_count) in enumerate(target_counts.items(), start=1):
        bucket_rows = sample_bucket_rows(buckets[bucket_name], target_count, seed=seed + index)
        sampled_rows.extend(annotate_rows(bucket_rows, bucket_name, target_profile))

    if len(sampled_rows) < resolved_total_rows:
        fallback_rows = sample_bucket_rows(
            keep_rows, resolved_total_rows - len(sampled_rows), seed=seed + 99
        )
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
