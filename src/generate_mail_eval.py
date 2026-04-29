from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

try:
    from .utils import ROOT_DIR, write_jsonl
except ImportError:
    from utils import ROOT_DIR, write_jsonl

DEFAULT_OUTPUT_PATH = ROOT_DIR / "data" / "eval" / "mail_triage_gold.jsonl"
STRICT_TRIAGE_INSTRUCTION_EN = (
    "Read the email below and return only this exact schema:\n"
    "Summary: ...\n"
    "Priority: high|medium|low\n"
    "Action items:\n"
    "- ...\n"
    "Deadlines: ...\n"
    "Do not add Subject, Date, or extra sections."
)
STRICT_TRIAGE_INSTRUCTION_VI = (
    "Đọc email dưới đây và trả về đúng schema tiếng Anh này:\n"
    "Summary: ...\n"
    "Priority: high|medium|low\n"
    "Action items:\n"
    "- ...\n"
    "Deadlines: ...\n"
    "Không thêm Subject, Date hoặc mục khác."
)

DOMAIN_COUNTS = {
    "ops": 18,
    "support": 18,
    "sales": 18,
    "internal": 18,
    "admin": 18,
    "billing": 15,
    "product": 15,
}
LANGUAGE_PLAN = ("en", "en", "en", "en", "en", "vi", "vi", "vi", "mixed", "mixed")
CUSTOMERS = ("GreenLeaf", "BlueOcean", "Northstar", "Acme", "Lotus", "RiverBank")
OWNERS = ("Lan", "Minh", "Vy", "Quan", "Maya", "Duy")
HOURS = ("10:30 AM", "2 PM", "4 PM", "Friday noon", "tomorrow 9 AM", "end of day")


def priority_from_scenario(scenario: int) -> str:
    return ("high", "medium", "low", "low")[scenario]


def deadline_phrase(scenario: int, hour: str, *, language: str) -> str:
    if scenario in {0, 1}:
        return f"before {hour}" if language == "vi" else f"by {hour}"
    return "None"


def domain_payload(
    domain: str, customer: str, owner: str, hour: str, scenario: int, *, language: str
) -> dict[str, Any]:
    priority = priority_from_scenario(scenario)
    deadline = deadline_phrase(scenario, hour, language=language)
    vi = language == "vi"

    domain_terms = {
        "ops": ("deploy checkpoint", "rollback owner", "deployment room"),
        "support": ("support incident", "customer update", "incident channel"),
        "sales": ("renewal quote", "discount approval", "finance thread"),
        "internal": ("team review notes", "action owner list", "team channel"),
        "admin": ("invoice receipt", "records folder", "admin queue"),
        "billing": ("payment confirmation", "service continuity", "billing queue"),
        "product": ("feature request", "product board", "roadmap note"),
    }
    subject_term, action_term, channel_term = domain_terms[domain]

    if scenario == 0:
        urgency_en = "This is urgent and is blocking work."
        urgency_vi = "Viec nay khan cap va dang chan tien do."
        action_en = f"{owner} must confirm the {action_term} by {hour}"
        action_vi = f"{owner} can xac nhan {action_term} before {hour}"
        summary_en = f"{domain} needs an urgent {customer} {subject_term} follow-up."
        summary_vi = f"{domain} can xu ly gap viec {subject_term} cho {customer}."
        actions_en = [action_en, f"Post blockers in the {channel_term}"]
        actions_vi = [action_vi, f"Bao blocker trong {channel_term}"]
        deadlines = [deadline]
    elif scenario == 1:
        urgency_en = "This is a normal follow-up with a clear deadline."
        urgency_vi = "Day la viec theo doi binh thuong co han ro rang."
        action_en = f"{owner} should send the {action_term} update by {hour}"
        action_vi = f"{owner} nen gui cap nhat {action_term} before {hour}"
        summary_en = f"{domain} needs a scheduled {customer} {subject_term} update."
        summary_vi = f"{domain} can cap nhat theo lich ve {subject_term} cua {customer}."
        actions_en = [action_en]
        actions_vi = [action_vi]
        deadlines = [deadline]
    elif scenario == 2:
        urgency_en = "FYI only. No reply or deadline is needed."
        urgency_vi = "Chi de nam thong tin. Khong can phan hoi va khong co han chot."
        summary_en = f"{domain} shared FYI context for the {customer} {subject_term}."
        summary_vi = f"{domain} chia se thong tin FYI ve {subject_term} cua {customer}."
        actions_en = ["None"]
        actions_vi = ["None"]
        deadlines = ["None"]
    else:
        urgency_en = "No hard deadline. Log it when convenient."
        urgency_vi = "Khong co han cung. Ghi nhan khi thuan tien."
        summary_en = f"{domain} should log a low-priority {customer} {subject_term} note."
        summary_vi = f"{domain} nen ghi nhan note uu tien thap ve {subject_term} cua {customer}."
        actions_en = [f"Log the {subject_term} note when convenient"]
        actions_vi = [f"Ghi nhan note {subject_term} khi thuan tien"]
        deadlines = ["None"]

    if vi:
        subject = f"{domain.upper()}: {subject_term} cho {customer}"
        body = (
            f"Chao team,\n\n{urgency_vi} {actions_vi[0] if actions_vi != ['None'] else 'Khong co viec can lam.'} "
            f"Neu co blocker thi bao trong {channel_term}.\n\nCam on."
        )
        return {
            "subject": subject,
            "body": body,
            "summary": summary_vi,
            "priority": priority,
            "actions": actions_vi,
            "deadlines": deadlines,
        }

    subject = f"{domain.upper()}: {subject_term} for {customer}"
    body = (
        f"Hi team,\n\n{urgency_en} {actions_en[0] if actions_en != ['None'] else 'There is no action item.'} "
        f"If anything slips, note it in the {channel_term}.\n\nThanks."
    )
    return {
        "subject": subject,
        "body": body,
        "summary": summary_en,
        "priority": priority,
        "actions": actions_en,
        "deadlines": deadlines,
    }


def make_case(index: int, domain: str, language: str) -> dict[str, Any]:
    customer = CUSTOMERS[index % len(CUSTOMERS)]
    owner = OWNERS[index % len(OWNERS)]
    hour = HOURS[index % len(HOURS)]
    scenario = index % 4
    label_language = "vi" if language == "vi" else "en"
    payload = domain_payload(domain, customer, owner, hour, scenario, language=label_language)

    if language == "vi":
        return {
            "instruction": STRICT_TRIAGE_INSTRUCTION_VI,
            "input": f"Chu de: {payload['subject']}\n\n{payload['body']}\n\nMa eval: {domain.upper()}-{index + 1:03d}",
            "expected": {
                "summary": payload["summary"],
                "priority": payload["priority"],
                "action_items": payload["actions"],
                "deadlines": payload["deadlines"],
            },
            "domain": domain,
            "language": "vi",
        }

    if language == "mixed":
        mixed_payload = domain_payload(domain, customer, owner, hour, scenario, language="vi")
        return {
            "instruction": STRICT_TRIAGE_INSTRUCTION_EN,
            "input": (
                f"Subject: {payload['subject']}\n\n{mixed_payload['body']}\n\n"
                f"Note: customer name is {customer}. Deadline in English: "
                f"{payload['deadlines'][0] if payload['deadlines'] != ['None'] else 'None'}. "
                f"Eval ID: {domain.upper()}-{index + 1:03d}."
            ),
            "expected": {
                "summary": payload["summary"],
                "priority": payload["priority"],
                "action_items": payload["actions"],
                "deadlines": payload["deadlines"],
            },
            "domain": domain,
            "language": "mixed",
        }

    return {
        "instruction": STRICT_TRIAGE_INSTRUCTION_EN,
        "input": f"Subject: {payload['subject']}\n\n{payload['body']}\n\nEval ID: {domain.upper()}-{index + 1:03d}",
        "expected": {
            "summary": payload["summary"],
            "priority": payload["priority"],
            "action_items": payload["actions"],
            "deadlines": payload["deadlines"],
        },
        "domain": domain,
        "language": "en",
    }


def build_mail_eval_rows(
    existing_rows: list[dict[str, Any]] | None = None, total_rows: int = 120
) -> list[dict[str, Any]]:
    del existing_rows
    rows: list[dict[str, Any]] = []
    index = 0
    for domain, domain_count in DOMAIN_COUNTS.items():
        for _ in range(domain_count):
            language = LANGUAGE_PLAN[index % len(LANGUAGE_PLAN)]
            rows.append(make_case(index, domain, language))
            index += 1
    return rows[:total_rows]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate mail triage gold eval rows.")
    parser.add_argument("--output-path", type=Path, default=DEFAULT_OUTPUT_PATH)
    parser.add_argument("--total-rows", type=int, default=120)
    parser.add_argument(
        "--preserve-existing",
        action="store_true",
        help="Accepted for compatibility; V2 eval generation always rewrites deterministic rows.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    rows = build_mail_eval_rows(total_rows=args.total_rows)
    write_jsonl(args.output_path, rows)
    print(f"Wrote {len(rows)} rows to {args.output_path.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
