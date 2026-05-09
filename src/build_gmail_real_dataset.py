from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

try:
    from .email_triage import format_action_extraction, format_full_triage
    from .utils import (
        DEFAULT_CURATED_GMAIL_REAL_PATH,
        DEFAULT_GMAIL_REAL_EVAL_PATH,
        DEFAULT_LABELED_GMAIL_PATH,
        DEFAULT_LOG_LEVEL,
        LOG_LEVEL_NAMES,
        configure_logging,
        get_logger,
        read_jsonl,
        write_jsonl,
    )
except ImportError:
    from email_triage import format_action_extraction, format_full_triage
    from utils import (
        DEFAULT_CURATED_GMAIL_REAL_PATH,
        DEFAULT_GMAIL_REAL_EVAL_PATH,
        DEFAULT_LABELED_GMAIL_PATH,
        DEFAULT_LOG_LEVEL,
        LOG_LEVEL_NAMES,
        configure_logging,
        get_logger,
        read_jsonl,
        write_jsonl,
    )


GMAIL_REAL_SOURCE = "gmail_real_labeled"
VALID_CATEGORIES = {
    "personal",
    "work",
    "order/shipping",
    "bill/payment",
    "account/security",
    "newsletter",
    "calendar/booking",
    "government/official",
    "education",
    "other",
}
VALID_PRIORITIES = {"high", "medium", "low"}
VALID_LANGUAGES = {"vi", "en", "vi+en", "mixed"}

FULL_TRIAGE_INSTRUCTION = (
    "Read this real Gmail message and return only these exact labels: Summary, Priority, "
    "Action items, Deadlines. Do not add Category or extra sections."
)
SUMMARY_INSTRUCTION = "Summarize this real Gmail message in one short sentence."
PRIORITY_INSTRUCTION = "Classify the priority of this real Gmail message as high, medium, or low."
ACTION_INSTRUCTION = (
    "Extract the action items and deadlines from this real Gmail message as a short bullet list."
)
CATEGORY_INSTRUCTION = (
    "Classify this real Gmail message into exactly one category: personal, work, "
    "order/shipping, bill/payment, account/security, newsletter, calendar/booking, "
    "government/official, education, or other."
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Convert manually labeled real Gmail records into train and eval JSONL."
    )
    parser.add_argument(
        "--input",
        "--input_path",
        dest="input_path",
        type=Path,
        default=DEFAULT_LABELED_GMAIL_PATH,
        help="Labeled Gmail JSONL produced by the manual labeling task.",
    )
    parser.add_argument(
        "--output",
        "--output_path",
        dest="output_path",
        type=Path,
        default=DEFAULT_CURATED_GMAIL_REAL_PATH,
        help="Curated training JSONL output.",
    )
    parser.add_argument(
        "--eval-output",
        "--eval_output_path",
        dest="eval_output_path",
        type=Path,
        default=DEFAULT_GMAIL_REAL_EVAL_PATH,
        help="Gold eval JSONL output.",
    )
    parser.add_argument(
        "--log_level",
        type=str.upper,
        choices=LOG_LEVEL_NAMES,
        default=DEFAULT_LOG_LEVEL,
        help="Logging verbosity.",
    )
    return parser.parse_args()


def normalize_language(value: str) -> str:
    normalized = value.strip().lower()
    if normalized == "vi+en":
        return "mixed"
    return normalized


def none_if_empty(values: list[str]) -> list[str]:
    cleaned = [value.strip() for value in values if isinstance(value, str) and value.strip()]
    return cleaned or ["None"]


def require_str(value: Any, field_name: str, uid: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"uid={uid} has invalid {field_name}.")
    return value.strip()


def validate_labeled_record(record: dict[str, Any]) -> tuple[str, dict[str, Any], dict[str, Any]]:
    uid = require_str(record.get("uid"), "uid", "<missing>")
    input_value = record.get("input")
    output = record.get("output")
    if not isinstance(input_value, dict):
        raise ValueError(f"uid={uid} has invalid input.")
    if not isinstance(output, dict):
        raise ValueError(f"uid={uid} has invalid output.")

    for key in ("from", "subject", "body_text", "date"):
        if not isinstance(input_value.get(key), str):
            raise ValueError(f"uid={uid} input.{key} must be a string.")

    category = require_str(output.get("category"), "output.category", uid)
    priority = require_str(output.get("priority"), "output.priority", uid)
    summary = require_str(output.get("summary"), "output.summary", uid)
    language = require_str(output.get("language"), "output.language", uid)
    if category not in VALID_CATEGORIES:
        raise ValueError(f"uid={uid} has invalid category: {category}")
    if priority not in VALID_PRIORITIES:
        raise ValueError(f"uid={uid} has invalid priority: {priority}")
    if normalize_language(language) not in VALID_LANGUAGES:
        raise ValueError(f"uid={uid} has invalid language: {language}")
    if not isinstance(output.get("action_items"), list):
        raise ValueError(f"uid={uid} output.action_items must be a list.")
    if not isinstance(output.get("deadlines"), list):
        raise ValueError(f"uid={uid} output.deadlines must be a list.")

    # Store normalized values back into a shallow copy so downstream row builders
    # can depend on list defaults and canonical language names.
    normalized_output = dict(output)
    normalized_output["category"] = category
    normalized_output["priority"] = priority
    normalized_output["summary"] = summary
    normalized_output["language"] = normalize_language(language)
    normalized_output["action_items"] = none_if_empty(output["action_items"])
    normalized_output["deadlines"] = none_if_empty(output["deadlines"])
    return uid, input_value, normalized_output


def format_email_input(input_value: dict[str, Any]) -> str:
    sender = input_value.get("from", "")
    subject = input_value.get("subject", "")
    date = input_value.get("date", "")
    body = input_value.get("body_text", "")
    return f"From: {sender}\nDate: {date}\nSubject: {subject}\n\n{body}".strip()


def make_train_row(
    *,
    uid: str,
    instruction: str,
    input_text: str,
    output_text: str,
    task_type: str,
    language: str,
    category: str,
    task_variant: str,
) -> dict[str, Any]:
    return {
        "instruction": instruction,
        "input": input_text,
        "output": output_text,
        "task_type": task_type,
        "language": language,
        "quality_score": 100,
        "flags": [],
        "source": GMAIL_REAL_SOURCE,
        "action": "keep",
        "uid": uid,
        "category": category,
        "mail_category": category,
        "task_variant": task_variant,
    }


def build_train_rows(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for record in records:
        uid, input_value, output = validate_labeled_record(record)
        input_text = format_email_input(input_value)
        language = output["language"]
        category = output["category"]
        action_items = output["action_items"]
        deadlines = output["deadlines"]
        full_triage = format_full_triage(
            output["summary"],
            output["priority"],
            action_items,
            deadlines,
            language="en",
        )
        action_block = format_action_extraction(action_items, deadlines, language="en")

        rows.extend(
            [
                make_train_row(
                    uid=uid,
                    instruction=FULL_TRIAGE_INSTRUCTION,
                    input_text=input_text,
                    output_text=full_triage,
                    task_type="generation",
                    language=language,
                    category=category,
                    task_variant="real_full_triage",
                ),
                make_train_row(
                    uid=uid,
                    instruction=SUMMARY_INSTRUCTION,
                    input_text=input_text,
                    output_text=output["summary"],
                    task_type="summarize",
                    language=language,
                    category=category,
                    task_variant="real_summary",
                ),
                make_train_row(
                    uid=uid,
                    instruction=PRIORITY_INSTRUCTION,
                    input_text=input_text,
                    output_text=output["priority"],
                    task_type="classification",
                    language=language,
                    category=category,
                    task_variant="real_priority",
                ),
                make_train_row(
                    uid=uid,
                    instruction=ACTION_INSTRUCTION,
                    input_text=input_text,
                    output_text=action_block,
                    task_type="list_extraction",
                    language=language,
                    category=category,
                    task_variant="real_actions_deadlines",
                ),
                make_train_row(
                    uid=uid,
                    instruction=CATEGORY_INSTRUCTION,
                    input_text=input_text,
                    output_text=category,
                    task_type="classification",
                    language=language,
                    category=category,
                    task_variant="real_category",
                ),
            ]
        )
    return rows


def build_eval_rows(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for record in records:
        uid, input_value, output = validate_labeled_record(record)
        rows.append(
            {
                "uid": uid,
                "instruction": FULL_TRIAGE_INSTRUCTION,
                "input": format_email_input(input_value),
                "expected": {
                    "summary": output["summary"],
                    "priority": output["priority"],
                    "action_items": output["action_items"],
                    "deadlines": output["deadlines"],
                },
                "source": GMAIL_REAL_SOURCE,
                "domain": output["category"],
                "category": output["category"],
                "language": output["language"],
            }
        )
    return rows


def main() -> int:
    args = parse_args()
    logger = configure_logging(args.log_level)

    try:
        records = read_jsonl(args.input_path)
        train_rows = build_train_rows(records)
        eval_rows = build_eval_rows(records)
        write_jsonl(args.output_path, train_rows)
        write_jsonl(args.eval_output_path, eval_rows)
        logger.info("Loaded %s labeled Gmail records.", len(records))
        logger.info("Wrote %s Gmail training rows to %s.", len(train_rows), args.output_path)
        logger.info("Wrote %s Gmail eval rows to %s.", len(eval_rows), args.eval_output_path)
        return 0
    except Exception as exc:
        get_logger().error("[build_gmail_real_dataset] Error: %s", exc)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
