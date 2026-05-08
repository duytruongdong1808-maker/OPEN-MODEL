import argparse
import json
import os
import sys
import textwrap
import time
from collections import Counter
from pathlib import Path


sys.stdout.reconfigure(encoding="utf-8")
sys.stdin.reconfigure(encoding="utf-8")

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_INPUT = PROJECT_ROOT / "data" / "filtered" / "emails.jsonl"
DEFAULT_OUTPUT = PROJECT_ROOT / "data" / "labeled" / "emails_labeled.jsonl"

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

PRIORITY_MAP = {
    "1": "low",
    "2": "medium",
    "3": "high",
    "low": "low",
    "medium": "medium",
    "high": "high",
}

TEMPLATES = {
    "t1": {
        "category": "bill/payment",
        "priority": "medium",
        "summary": "Thông báo giao dịch từ ngân hàng",
        "action_items": ["Kiểm tra giao dịch"],
        "deadlines": [],
    },
    "t2": {
        "category": "account/security",
        "priority": "high",
        "summary": "Cảnh báo bảo mật tài khoản",
        "action_items": ["Xác nhận hoặc đổi mật khẩu"],
        "deadlines": [],
    },
    "t3": {
        "category": "order/shipping",
        "priority": "medium",
        "summary": "Thông tin đơn hàng hoặc giao hàng",
        "action_items": ["Theo dõi đơn hàng"],
        "deadlines": [],
    },
    "t4": {
        "category": "education",
        "priority": "medium",
        "summary": "Thông báo học tập hoặc đào tạo",
        "action_items": ["Xem nội dung thông báo"],
        "deadlines": [],
    },
    "t5": {
        "category": "calendar/booking",
        "priority": "medium",
        "summary": "Thông tin lịch hẹn hoặc đặt chỗ",
        "action_items": ["Kiểm tra lịch"],
        "deadlines": [],
    },
    "t6": {
        "category": "government/official",
        "priority": "high",
        "summary": "Thông báo từ cơ quan chính thức",
        "action_items": ["Xem và xử lý nếu cần"],
        "deadlines": [],
    },
}

FIELDS = (
    ("category", "Category"),
    ("priority", "Priority (1=low, 2=medium, 3=high)"),
    ("summary", "Summary"),
    ("action_items", "Action items (semicolon-separated, or empty)"),
    ("deadlines", "Deadlines (semicolon-separated, or empty)"),
)


def parse_args():
    parser = argparse.ArgumentParser(description="Interactively label filtered emails.")
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT, help="Input filtered JSONL.")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT, help="Output labeled JSONL.")
    return parser.parse_args()


def load_jsonl(path):
    rows = []
    if not path.exists():
        return rows
    with path.open("r", encoding="utf-8") as file:
        for line in file:
            if line.strip():
                rows.append(json.loads(line))
    return rows


def sort_emails(emails):
    return sorted(
        emails,
        key=lambda email: (
            (email.get("from") or "").lower(),
            (email.get("date") or ""),
            (email.get("uid") or ""),
        ),
    )


def split_semicolon(value):
    return [item.strip() for item in value.split(";") if item.strip()]


def join_semicolon(value):
    if isinstance(value, list):
        return "; ".join(value)
    return value or ""


def priority_to_saved(value):
    return PRIORITY_MAP.get(value.strip().lower(), value.strip().lower())


def priority_to_prompt(value):
    reverse = {"low": "1", "medium": "2", "high": "3"}
    return reverse.get(value, value)


def clear_screen():
    os.system("cls" if os.name == "nt" else "clear")


def wrapped_body(body):
    body = " ".join((body or "").split())
    truncated = len(body) > 2000
    body = body[:2000]
    if truncated:
        body += "...[truncated]"
    return textwrap.fill(body, width=80)


def render_templates():
    lines = []
    for key, template in TEMPLATES.items():
        lines.append(
            f"{key}: {template['category']} | {template['priority']} | {template['summary']}"
        )
    return "\n".join(lines)


def render_email(email, position, total, total_labeled, session_labeled, started_at):
    elapsed_minutes = max((time.time() - started_at) / 60, 1 / 60)
    rate = session_labeled / elapsed_minutes
    percent = (total_labeled / total * 100) if total else 0
    from_name = email.get("from_name") or ""
    sender = email.get("from") or ""
    labels = ", ".join(email.get("labels") or [])

    clear_screen()
    print(f"Labeled {total_labeled}/{total} ({percent:.1f}%) | this session: {session_labeled} emails | rate: {rate:.1f}/min")
    print("Categories: " + ", ".join(CATEGORIES))
    print("Templates: type ?t1, ?t2, ... at any prompt")
    print(render_templates())
    print("=" * 60)
    print(f"Email {position} / {total}  |  Sender: {sender}")
    print("=" * 60)
    print(f"From:    {from_name} <{sender}>")
    print(f"Subject: {email.get('subject') or ''}")
    print(f"Date:    {email.get('date') or ''}")
    print(f"Labels:  {labels}")
    print("-" * 60)
    print(wrapped_body(email.get("body_text") or ""))
    print("=" * 60)


def defaults_from_template(template):
    return {
        "category": template["category"],
        "priority": priority_to_prompt(template["priority"]),
        "summary": template["summary"],
        "action_items": join_semicolon(template["action_items"]),
        "deadlines": join_semicolon(template["deadlines"]),
    }


def prompt_for_label(email, last_values, position, total, total_labeled, session_labeled, started_at):
    values = dict(last_values)
    index = 0

    while index < len(FIELDS):
        render_email(email, position, total, total_labeled, session_labeled, started_at)
        for prev_key, prev_label in FIELDS[:index]:
            print(f"{prev_label}: {values.get(prev_key, '')}")

        key, label = FIELDS[index]
        default = values.get(key, "")
        raw = input(f"{label} [{default}]: ").strip()
        command = raw.lower()

        if command in {"quit", "q"}:
            return "quit", None, last_values
        if command in {"skip", "s"}:
            return "skip", None, last_values
        if command in {"back", "b"}:
            return "back", None, last_values
        if command in {"edit", "e"}:
            index = max(index - 1, 0)
            continue
        if command.startswith("?"):
            template_name = command[1:]
            if template_name in TEMPLATES:
                values.update(defaults_from_template(TEMPLATES[template_name]))
                index = 0
            else:
                input(f"Unknown template {command}. Press Enter to continue.")
            continue

        values[key] = raw if raw else default
        index += 1

    saved_priority = priority_to_saved(values["priority"])
    if saved_priority not in {"low", "medium", "high"}:
        saved_priority = "medium"

    output = {
        "category": values["category"],
        "priority": saved_priority,
        "summary": values["summary"],
        "action_items": split_semicolon(values["action_items"]),
        "deadlines": split_semicolon(values["deadlines"]),
    }
    next_last_values = {
        "category": output["category"],
        "priority": priority_to_prompt(output["priority"]),
        "summary": output["summary"],
        "action_items": join_semicolon(output["action_items"]),
        "deadlines": join_semicolon(output["deadlines"]),
    }
    return "save", output, next_last_values


def make_record(email, output):
    return {
        "uid": email.get("uid"),
        "input": {
            "from": email.get("from", ""),
            "subject": email.get("subject", ""),
            "body_text": email.get("body_text", ""),
            "date": email.get("date", ""),
        },
        "output": output,
    }


def append_record(path, record):
    with path.open("a", encoding="utf-8") as file:
        file.write(json.dumps(record, ensure_ascii=False) + "\n")


def rewrite_records(path, records):
    with path.open("w", encoding="utf-8") as file:
        for record in records:
            file.write(json.dumps(record, ensure_ascii=False) + "\n")


def print_summary(records, total):
    category_counts = Counter(record["output"]["category"] for record in records)
    priority_counts = Counter(record["output"]["priority"] for record in records)
    print(f"Total labeled: {len(records)}/{total}")
    print("By category:")
    for category, count in category_counts.most_common():
        print(f"- {category}: {count}")
    print("By priority:")
    for priority in ("low", "medium", "high"):
        print(f"- {priority}: {priority_counts[priority]}")


def main():
    args = parse_args()
    emails = sort_emails(load_jsonl(args.input))
    total = len(emails)
    args.output.parent.mkdir(parents=True, exist_ok=True)

    records = load_jsonl(args.output)
    labeled_uids = {record.get("uid") for record in records}
    email_by_uid = {email.get("uid"): email for email in emails}
    session_saved = []
    started_at = time.time()
    last_values = {
        "category": "order/shipping",
        "priority": "2",
        "summary": "",
        "action_items": "",
        "deadlines": "",
    }

    print(f"Loaded {total} emails from {args.input}")
    if records:
        print(f"Resuming from email {min(len(labeled_uids) + 1, total)}/{total}")
    else:
        print(f"Resuming from email 1/{total}")

    index = 0
    while index < total:
        email = emails[index]
        uid = email.get("uid")
        if uid in labeled_uids:
            index += 1
            continue

        status, output, new_last_values = prompt_for_label(
            email,
            last_values,
            index + 1,
            total,
            len(labeled_uids),
            len(session_saved),
            started_at,
        )

        if status == "quit":
            clear_screen()
            print_summary(records, total)
            return
        if status == "skip":
            index += 1
            continue
        if status == "back":
            if not session_saved:
                input("No previous session-saved email to re-do. Press Enter to continue.")
                continue
            previous = session_saved.pop()
            previous_uid = previous.get("uid")
            records = [record for record in records if record.get("uid") != previous_uid]
            labeled_uids.discard(previous_uid)
            rewrite_records(args.output, records)
            index = emails.index(email_by_uid[previous_uid])
            continue

        record = make_record(email, output)
        append_record(args.output, record)
        records.append(record)
        labeled_uids.add(uid)
        session_saved.append(record)
        last_values = new_last_values
        index += 1

    clear_screen()
    print("All emails labeled.")
    print_summary(records, total)


if __name__ == "__main__":
    main()
