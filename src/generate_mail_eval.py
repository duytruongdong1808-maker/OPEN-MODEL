from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

try:
    from .utils import ROOT_DIR, write_jsonl
except ImportError:
    from utils import ROOT_DIR, write_jsonl

DEFAULT_OUTPUT_PATH = ROOT_DIR / "data" / "eval" / "mail_triage_gold.jsonl"


DOMAINS = ("ops", "sales", "internal", "admin")
LANGUAGES = ("en", "vi", "mixed")


def make_case(index: int, domain: str, language: str) -> dict[str, Any]:
    customer = ["GreenLeaf", "BlueOcean", "Northstar", "Acme", "Lotus"][index % 5]
    owner = ["Lan", "Minh", "Vy", "Quân", "Maya"][index % 5]
    hour = ["10:30 AM", "2 PM", "4 PM", "Friday noon", "tomorrow 9 AM"][index % 5]
    priority = "high" if index % 7 in {0, 1} else "medium" if index % 7 in {2, 3, 4} else "low"
    if domain == "ops":
        subject_en = f"Deploy checkpoint for {customer}"
        body_en = f"Hi ops,\n\nPlease have {owner} confirm the rollback owner by {hour} and post any blocker in the deploy room. If everything is green, no extra customer note is needed.\n\nThanks."
        summary_en = f"Ops needs rollback ownership confirmed for the {customer} deployment checkpoint."
        actions_en = [f"{owner} confirms the rollback owner by {hour}", "Post any blocker in the deploy room"]
        deadlines_en = [f"by {hour}"]
        subject_vi = f"Chốt checkpoint deploy cho {customer}"
        body_vi = f"Chào team vận hành,\n\nNhờ {owner} xác nhận người phụ trách rollback trước {hour} và báo blocker trong phòng deploy. Nếu mọi thứ xanh thì chưa cần gửi note khách hàng.\n\nCảm ơn."
        summary_vi = f"Team vận hành cần xác nhận owner rollback cho checkpoint deploy của {customer}."
        actions_vi = [f"{owner} xác nhận người phụ trách rollback trước {hour}", "Báo blocker trong phòng deploy"]
        deadlines_vi = [f"trước {hour}"]
    elif domain == "sales":
        subject_en = f"Renewal quote follow-up for {customer}"
        body_en = f"Hi sales,\n\nThe {customer} renewal quote is waiting on discount approval. Please send the final quote by {hour} and flag finance if approval slips.\n\nThanks."
        summary_en = f"Sales needs to finish the {customer} renewal quote after discount approval."
        actions_en = [f"Send the final quote by {hour}", "Flag finance if approval slips"]
        deadlines_en = [f"by {hour}"]
        subject_vi = f"Theo dõi renewal quote cho {customer}"
        body_vi = f"Chào team sales,\n\nRenewal quote của {customer} đang chờ duyệt discount. Nhờ gửi quote cuối trước {hour} và báo finance nếu duyệt bị trễ.\n\nCảm ơn."
        summary_vi = f"Team sales cần hoàn tất renewal quote cho {customer} sau khi duyệt discount."
        actions_vi = [f"Gửi quote cuối trước {hour}", "Báo finance nếu duyệt bị trễ"]
        deadlines_vi = [f"trước {hour}"]
    elif domain == "internal":
        subject_en = f"Team notes for {customer} incident review"
        body_en = f"Hi team,\n\nThe incident review notes are ready. Please review the action owner list by {hour}. No broad announcement is required unless you find a factual error.\n\nThanks."
        summary_en = "The team needs to review incident notes, but no broad announcement is required."
        actions_en = [f"Review the action owner list by {hour}"]
        deadlines_en = [f"by {hour}"]
        subject_vi = f"Ghi chú review sự cố {customer}"
        body_vi = f"Chào team,\n\nGhi chú review sự cố đã sẵn sàng. Nhờ xem lại danh sách owner hành động trước {hour}. Chưa cần thông báo rộng trừ khi phát hiện sai thông tin.\n\nCảm ơn."
        summary_vi = "Team cần review ghi chú sự cố, nhưng chưa cần thông báo rộng."
        actions_vi = [f"Xem lại danh sách owner hành động trước {hour}"]
        deadlines_vi = [f"trước {hour}"]
    else:
        subject_en = f"Admin reminder for {customer} invoice"
        body_en = f"Hi admin,\n\nPlease upload the {customer} invoice receipt by {hour}. This is only for records, so no customer reply is needed.\n\nThanks."
        summary_en = f"Admin needs to upload the {customer} invoice receipt for records."
        actions_en = [f"Upload the {customer} invoice receipt by {hour}"]
        deadlines_en = [f"by {hour}"]
        subject_vi = f"Nhắc admin về hóa đơn {customer}"
        body_vi = f"Chào admin,\n\nNhờ upload biên nhận hóa đơn của {customer} trước {hour}. Việc này chỉ để lưu hồ sơ nên chưa cần phản hồi khách hàng.\n\nCảm ơn."
        summary_vi = f"Admin cần upload biên nhận hóa đơn của {customer} để lưu hồ sơ."
        actions_vi = [f"Upload biên nhận hóa đơn của {customer} trước {hour}"]
        deadlines_vi = [f"trước {hour}"]

    if priority == "low":
        actions_en = ["None"] if index % 2 == 0 else actions_en[:1]
        actions_vi = ["None"] if index % 2 == 0 else actions_vi[:1]
        deadlines_en = ["None"] if actions_en == ["None"] else deadlines_en
        deadlines_vi = ["None"] if actions_vi == ["None"] else deadlines_vi

    if language == "vi":
        return {
            "instruction": "Đọc email dưới đây và trả về các mục Tóm tắt, Ưu tiên, Việc cần làm, Hạn chót.",
            "input": f"Chủ đề: {subject_vi}\n\n{body_vi}\n\nMã eval: {domain.upper()}-{index + 1:03d}",
            "expected": {"summary": summary_vi, "priority": priority, "action_items": actions_vi, "deadlines": deadlines_vi},
            "domain": domain,
            "language": "vi",
        }
    if language == "mixed":
        return {
            "instruction": "Read the mixed-language email below and return Summary, Priority, Action items, and Deadlines.",
            "input": f"Subject: {subject_en}\n\n{body_vi}\n\nNote: customer name is {customer}. Eval ID: {domain.upper()}-{index + 1:03d}.",
            "expected": {"summary": summary_en, "priority": priority, "action_items": actions_en, "deadlines": deadlines_en},
            "domain": domain,
            "language": "mixed",
        }
    return {
        "instruction": "Read the email below and return Summary, Priority, Action items, and Deadlines.",
        "input": f"Subject: {subject_en}\n\n{body_en}\n\nEval ID: {domain.upper()}-{index + 1:03d}",
        "expected": {"summary": summary_en, "priority": priority, "action_items": actions_en, "deadlines": deadlines_en},
        "domain": domain,
        "language": "en",
    }


def build_mail_eval_rows(existing_rows: list[dict[str, Any]] | None = None, total_rows: int = 120) -> list[dict[str, Any]]:
    rows = list(existing_rows or [])
    index = 0
    while len(rows) < total_rows:
        if index % 10 < 5:
            language = "en"
        elif index % 10 < 8:
            language = "vi"
        else:
            language = "mixed"
        domain = DOMAINS[index % len(DOMAINS)]
        candidate = make_case(index, domain, language)
        identity = (candidate["instruction"], candidate["input"])
        if all((row.get("instruction"), row.get("input")) != identity for row in rows):
            rows.append(candidate)
        index += 1
    return rows[:total_rows]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate mail triage gold eval rows.")
    parser.add_argument("--output-path", type=Path, default=DEFAULT_OUTPUT_PATH)
    parser.add_argument("--total-rows", type=int, default=120)
    parser.add_argument("--preserve-existing", action="store_true", default=True)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    existing_rows: list[dict[str, Any]] = []
    if args.preserve_existing and args.output_path.exists():
        existing_rows = [
            json.loads(line)
            for line in args.output_path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
    rows = build_mail_eval_rows(existing_rows, total_rows=args.total_rows)
    write_jsonl(args.output_path, rows)
    print(f"Wrote {len(rows)} rows to {args.output_path.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
