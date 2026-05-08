import argparse
import json
import sys
from pathlib import Path


sys.stdout.reconfigure(encoding="utf-8")

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_INPUT = PROJECT_ROOT / "data" / "labeled" / "emails_labeled.jsonl"

CATEGORIES = (
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
)
VALID_PRIORITIES = ("low", "medium", "high")
INPUT_KEYS = ("from", "subject", "body_text", "date")


def parse_args():
    parser = argparse.ArgumentParser(description="Validate labeled email JSONL output.")
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT, help="Input labeled JSONL.")
    return parser.parse_args()


def load_jsonl(path):
    rows = []
    if not path.exists():
        return rows
    with path.open("r", encoding="utf-8") as file:
        for line_number, line in enumerate(file, start=1):
            if line.strip():
                try:
                    rows.append(json.loads(line))
                except json.JSONDecodeError as error:
                    rows.append({"uid": f"line-{line_number}", "_json_error": str(error)})
    return rows


def add_error(errors, uid, field, reason):
    errors.append((uid, field, reason))
    print(f"ERROR uid={uid}: {field} — {reason}")


def validate_record(record, errors, category_counts, priority_counts):
    uid = record.get("uid")
    uid_for_error = uid if uid else "<missing>"

    if record.get("_json_error"):
        add_error(errors, uid_for_error, "json", record["_json_error"])
        return False
    if not uid:
        add_error(errors, uid_for_error, "uid", "must be present and non-empty")

    input_value = record.get("input")
    if not isinstance(input_value, dict):
        add_error(errors, uid_for_error, "input", "must be a dict")
    else:
        for key in INPUT_KEYS:
            if key not in input_value:
                add_error(errors, uid_for_error, f"input.{key}", "missing key")

    output = record.get("output")
    if not isinstance(output, dict):
        add_error(errors, uid_for_error, "output", "must be a dict")
        return False

    category = output.get("category")
    priority = output.get("priority")
    if category not in CATEGORIES:
        add_error(errors, uid_for_error, "output.category", "invalid category")
    else:
        category_counts[category] += 1
    if priority not in VALID_PRIORITIES:
        add_error(errors, uid_for_error, "output.priority", "invalid priority")
    else:
        priority_counts[priority] += 1
    if not isinstance(output.get("summary"), str) or not output["summary"].strip():
        add_error(errors, uid_for_error, "output.summary", "must be a non-empty string")
    if not isinstance(output.get("action_items"), list):
        add_error(errors, uid_for_error, "output.action_items", "must be a list")
    if not isinstance(output.get("deadlines"), list):
        add_error(errors, uid_for_error, "output.deadlines", "must be a list")
    if not isinstance(output.get("language"), str) or not output["language"].strip():
        add_error(errors, uid_for_error, "output.language", "must be a non-empty string")

    return True


def main():
    args = parse_args()
    errors = []
    valid = 0
    category_counts = {category: 0 for category in CATEGORIES}
    priority_counts = {priority: 0 for priority in VALID_PRIORITIES}
    if not args.input.exists():
        add_error(errors, "<missing>", "input", "file does not exist")
        records = []
    else:
        records = load_jsonl(args.input)

    for record in records:
        error_count = len(errors)
        validate_record(record, errors, category_counts, priority_counts)
        if len(errors) == error_count:
            valid += 1

    print("--- Validation summary ---")
    print(f"Total records: {len(records)}")
    print(f"Valid: {valid}")
    print(f"Errors: {len(errors)}")
    print("Category breakdown:")
    for category in CATEGORIES:
        print(f"  {category}: {category_counts[category]}")
    print("Priority breakdown:")
    for priority in VALID_PRIORITIES:
        print(f"  {priority}: {priority_counts[priority]}")

    if errors:
        sys.exit(1)


if __name__ == "__main__":
    main()
