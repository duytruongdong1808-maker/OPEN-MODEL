from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path

try:
    from .email_triage import format_action_extraction, format_full_triage
    from .utils import DEFAULT_RAW_MAIL_TRIAGE_SEED_PATH, write_jsonl
except ImportError:
    from email_triage import format_action_extraction, format_full_triage
    from utils import DEFAULT_RAW_MAIL_TRIAGE_SEED_PATH, write_jsonl


ROWS_PER_RECORD = 4
DEFAULT_TOTAL_ROWS = 1000
DEFAULT_RECORD_COUNT = DEFAULT_TOTAL_ROWS // ROWS_PER_RECORD
MAIL_DOMAINS = ("ops", "support", "billing", "product")

SUMMARY_INSTRUCTIONS = {
    "en": "Summarize this email in one short sentence.",
    "vi": "Tóm tắt email sau trong một câu ngắn.",
}
PRIORITY_INSTRUCTIONS = {
    "en": "Classify the priority of this email as high, medium, or low.",
    "vi": "Cho biết mức ưu tiên của email này là high, medium, hay low.",
}
ACTION_INSTRUCTIONS = {
    "en": "Extract the action items and deadlines from this email as a short bullet list.",
    "vi": "Trích xuất việc cần làm và hạn chót từ email sau dưới dạng danh sách gạch đầu dòng ngắn.",
}
TRIAGE_INSTRUCTIONS = {
    "en": "Read this email and return a triage block with Summary, Priority, Action items, and Deadlines.",
    "vi": "Đọc email sau và trả về bản triage gồm Tóm tắt, Ưu tiên, Việc cần làm, Hạn chót.",
}
NAME_PAIRS = [
    ("Lan", "Huy"),
    ("Minh", "Trang"),
    ("An", "Bảo"),
    ("Vy", "Quân"),
    ("Linh", "Khôi"),
    ("Mai", "Duy"),
]
OPS_RELEASE_ITEMS = [
    {
        "subject_en": "Final release checklist",
        "subject_vi": "Chốt checklist phát hành",
        "deliverable_en": "release checklist",
        "deliverable_vi": "checklist phát hành",
        "review_en": "the rollback notes",
        "review_vi": "ghi chú rollback",
        "channel_en": "the release channel",
        "channel_vi": "kênh release",
    },
    {
        "subject_en": "Staging handoff notes",
        "subject_vi": "Chốt ghi chú bàn giao staging",
        "deliverable_en": "staging handoff notes",
        "deliverable_vi": "ghi chú bàn giao staging",
        "review_en": "the staging approvals",
        "review_vi": "phê duyệt staging",
        "channel_en": "the staging thread",
        "channel_vi": "luồng staging",
    },
    {
        "subject_en": "Cutover runbook check",
        "subject_vi": "Rà soát runbook cutover",
        "deliverable_en": "cutover runbook",
        "deliverable_vi": "runbook cutover",
        "review_en": "the fallback checklist",
        "review_vi": "checklist fallback",
        "channel_en": "the cutover room",
        "channel_vi": "phòng cutover",
    },
    {
        "subject_en": "Launch metrics handoff",
        "subject_vi": "Bàn giao số liệu launch",
        "deliverable_en": "launch metrics sheet",
        "deliverable_vi": "bảng số liệu launch",
        "review_en": "the anomaly summary",
        "review_vi": "tóm tắt bất thường",
        "channel_en": "the launch bridge",
        "channel_vi": "cầu launch",
    },
]
OPS_RELEASE_VARIANTS = [
    {
        "priority": "high",
        "event_en": "today's 6 PM release",
        "event_vi": "đợt phát hành lúc 18h hôm nay",
        "first_en": "by 2 PM today",
        "first_vi": "trước 14h hôm nay",
        "second_en": "by 3 PM today",
        "second_vi": "trước 15h hôm nay",
    },
    {
        "priority": "high",
        "event_en": "tomorrow morning's cutover",
        "event_vi": "đợt cutover sáng mai",
        "first_en": "by 5 PM today",
        "first_vi": "trước 17h hôm nay",
        "second_en": "by 6 PM today",
        "second_vi": "trước 18h hôm nay",
    },
    {
        "priority": "medium",
        "event_en": "Thursday's operations review",
        "event_vi": "buổi rà soát vận hành thứ Năm",
        "first_en": "by Thursday 10 AM",
        "first_vi": "trước 10h thứ Năm",
        "second_en": "by Thursday noon",
        "second_vi": "trước 12h trưa thứ Năm",
    },
]
OPS_SCHEDULE_ITEMS = [
    {
        "subject_en": "Implementation review moved",
        "subject_vi": "Dời lịch review triển khai",
        "meeting_en": "implementation review",
        "meeting_vi": "review triển khai",
        "reason_en": "the upstream partner needs more prep time",
        "reason_vi": "đối tác upstream cần thêm thời gian chuẩn bị",
        "support_en": "the attendee list",
        "support_vi": "danh sách người tham gia",
    },
    {
        "subject_en": "Migration dry run rescheduled",
        "subject_vi": "Dời lịch dry run migration",
        "meeting_en": "migration dry run",
        "meeting_vi": "dry run migration",
        "reason_en": "the dependency snapshot is not ready yet",
        "reason_vi": "ảnh chụp dependency chưa sẵn sàng",
        "support_en": "the runbook links",
        "support_vi": "link runbook",
    },
    {
        "subject_en": "Launch sync update",
        "subject_vi": "Cập nhật lịch launch sync",
        "meeting_en": "launch sync",
        "meeting_vi": "launch sync",
        "reason_en": "the dashboard backfill will finish later than expected",
        "reason_vi": "backfill dashboard sẽ hoàn tất muộn hơn dự kiến",
        "support_en": "the room booking",
        "support_vi": "đặt phòng họp",
    },
]
OPS_SCHEDULE_VARIANTS = [
    {
        "priority": "medium",
        "old_en": "9 AM tomorrow",
        "old_vi": "9h sáng mai",
        "new_en": "1 PM tomorrow",
        "new_vi": "13h ngày mai",
        "confirm_en": "by 11 AM today",
        "confirm_vi": "trước 11h hôm nay",
    },
    {
        "priority": "medium",
        "old_en": "Thursday 10 AM",
        "old_vi": "10h thứ Năm",
        "new_en": "Thursday 3 PM",
        "new_vi": "15h thứ Năm",
        "confirm_en": "by 5 PM today",
        "confirm_vi": "trước 17h hôm nay",
    },
    {
        "priority": "high",
        "old_en": "this afternoon at 1 PM",
        "old_vi": "13h chiều nay",
        "new_en": "this afternoon at 4 PM",
        "new_vi": "16h chiều nay",
        "confirm_en": "within the next hour",
        "confirm_vi": "trong vòng 1 giờ tới",
    },
]
OPS_FYI_ITEMS = [
    {
        "subject_en": "Postmortem packet published",
        "subject_vi": "Đã phát hành bộ tài liệu postmortem",
        "document_en": "postmortem packet",
        "document_vi": "bộ tài liệu postmortem",
        "context_en": "Friday's review",
        "context_vi": "buổi review thứ Sáu",
    },
    {
        "subject_en": "Cutover archive available",
        "subject_vi": "Đã lưu trữ tài liệu cutover",
        "document_en": "cutover archive",
        "document_vi": "tài liệu cutover đã lưu trữ",
        "context_en": "the next audit",
        "context_vi": "đợt audit tiếp theo",
    },
]
SUPPORT_INCIDENT_ITEMS = [
    {
        "subject_en": "Billing login outage",
        "subject_vi": "Sự cố đăng nhập billing",
        "issue_en": "the billing portal login is failing",
        "issue_vi": "cổng billing đang lỗi đăng nhập",
        "impact_en": "two renewals are blocked",
        "impact_vi": "hai hợp đồng gia hạn đang bị chặn",
        "workaround_en": "share the manual renewal steps",
        "workaround_vi": "gửi quy trình gia hạn thủ công",
    },
    {
        "subject_en": "Attachment download failure",
        "subject_vi": "Lỗi tải file đính kèm",
        "issue_en": "customers cannot download attachments",
        "issue_vi": "khách hàng không tải được file đính kèm",
        "impact_en": "the onboarding queue is delayed",
        "impact_vi": "hàng đợi onboarding đang bị chậm",
        "workaround_en": "send the alternate download link",
        "workaround_vi": "gửi link tải thay thế",
    },
    {
        "subject_en": "Dashboard numbers look wrong",
        "subject_vi": "Dashboard đang hiển thị sai số liệu",
        "issue_en": "the main dashboard widget shows stale metrics",
        "issue_vi": "widget chính trên dashboard đang hiển thị số liệu cũ",
        "impact_en": "the executive readout is at risk",
        "impact_vi": "buổi readout cho ban điều hành đang bị ảnh hưởng",
        "workaround_en": "point the customer to the raw report",
        "workaround_vi": "hướng dẫn khách hàng xem báo cáo gốc",
    },
]
SUPPORT_INCIDENT_VARIANTS = [
    {
        "priority": "high",
        "owner_en": "confirm who owns the investigation within 20 minutes",
        "owner_vi": "xác nhận người phụ trách điều tra trong 20 phút tới",
        "update_en": "send the next customer update within 45 minutes",
        "update_vi": "gửi cập nhật tiếp theo cho khách hàng trong 45 phút tới",
    },
    {
        "priority": "high",
        "owner_en": "confirm whether engineering is already on it within 30 minutes",
        "owner_vi": "xác nhận engineering đã nhận việc trong vòng 30 phút",
        "update_en": "share the next status note by 11 AM today",
        "update_vi": "chia sẻ bản cập nhật tiếp theo trước 11h hôm nay",
    },
    {
        "priority": "medium",
        "owner_en": "capture the current owner by 3 PM today",
        "owner_vi": "chốt người phụ trách hiện tại trước 15h hôm nay",
        "update_en": "reply with the mitigation ETA by 5 PM today",
        "update_vi": "phản hồi ETA khắc phục trước 17h hôm nay",
    },
]
SUPPORT_FOLLOWUP_ITEMS = [
    {
        "subject_en": "Need a concise RCA update",
        "subject_vi": "Cần bản cập nhật RCA ngắn gọn",
        "issue_en": "the webhook delay is still under investigation",
        "issue_vi": "độ trễ webhook vẫn đang được điều tra",
        "request_en": "send a concise root-cause update after the debug call",
        "request_vi": "gửi bản cập nhật nguyên nhân ngắn gọn sau cuộc gọi debug",
        "workaround_en": "keep the customer on the temporary polling setup",
        "workaround_vi": "giữ khách hàng ở chế độ polling tạm thời",
    },
    {
        "subject_en": "Prepare the customer-ready summary",
        "subject_vi": "Chuẩn bị bản tóm tắt gửi khách hàng",
        "issue_en": "the export bug is mitigated but not fully fixed",
        "issue_vi": "lỗi export đã được giảm thiểu nhưng chưa sửa xong",
        "request_en": "draft the customer-ready summary once the patch lands",
        "request_vi": "soạn bản tóm tắt gửi khách hàng sau khi bản vá hoàn tất",
        "workaround_en": "keep the workaround note attached to the ticket",
        "workaround_vi": "tiếp tục đính kèm ghi chú workaround vào ticket",
    },
]
SUPPORT_FYI_ITEMS = [
    {
        "subject_en": "Incident review notes posted",
        "subject_vi": "Đã đăng ghi chú review sự cố",
        "note_en": "incident review notes",
        "note_vi": "ghi chú review sự cố",
        "channel_en": "the support knowledge base",
        "channel_vi": "knowledge base của support",
    },
    {
        "subject_en": "Customer workaround approved",
        "subject_vi": "Đã duyệt workaround cho khách hàng",
        "note_en": "approved workaround details",
        "note_vi": "chi tiết workaround đã duyệt",
        "channel_en": "the escalation thread",
        "channel_vi": "luồng escalation",
    },
]
BILLING_ITEMS = [
    {
        "subject_en": "Invoice confirmation needed",
        "subject_vi": "Cần xác nhận hóa đơn",
        "request_en": "confirm the payment status for invoice INV-204",
        "request_vi": "xác nhận trạng thái thanh toán của hóa đơn INV-204",
        "secondary_en": "reply to the customer with the latest status",
        "secondary_vi": "phản hồi khách hàng với trạng thái mới nhất",
    },
    {
        "subject_en": "Renewal quote follow-up",
        "subject_vi": "Theo dõi renewal quote",
        "request_en": "send the final renewal quote to GreenLeaf",
        "request_vi": "gửi renewal quote cuối cho GreenLeaf",
        "secondary_en": "answer the discount question from finance",
        "secondary_vi": "trả lời câu hỏi về discount từ finance",
    },
    {
        "subject_en": "Refund request review",
        "subject_vi": "Rà soát yêu cầu hoàn tiền",
        "request_en": "review the refund request for the April order",
        "request_vi": "rà soát yêu cầu hoàn tiền cho đơn hàng tháng Tư",
        "secondary_en": "update the expected handling timeline",
        "secondary_vi": "cập nhật timeline xử lý dự kiến",
    },
]
BILLING_VARIANTS = [
    {
        "priority": "high",
        "deadline_en": "by 4 PM today",
        "deadline_vi": "trước 16h hôm nay",
    },
    {
        "priority": "medium",
        "deadline_en": "by 10 AM tomorrow",
        "deadline_vi": "trước 10h sáng mai",
    },
    {
        "priority": "medium",
        "deadline_en": "None",
        "deadline_vi": "None",
    },
]
PRODUCT_ITEMS = [
    {
        "subject_en": "Feature request from Orion",
        "subject_vi": "Yêu cầu tính năng từ Orion",
        "feature_en": "regional dashboard filters",
        "feature_vi": "bộ lọc dashboard theo khu vực",
        "request_en": "regional dashboard filter",
        "request_vi": "bộ lọc dashboard theo khu vực",
        "review_en": "next week's roadmap review",
        "review_vi": "buổi roadmap review tuần sau",
    },
    {
        "subject_en": "SMS notification request",
        "subject_vi": "Đề xuất thông báo qua SMS",
        "feature_en": "SMS notifications",
        "feature_vi": "thông báo qua SMS",
        "request_en": "SMS notification",
        "request_vi": "thông báo qua SMS",
        "review_en": "Friday's prioritization meeting",
        "review_vi": "buổi họp ưu tiên thứ Sáu",
    },
    {
        "subject_en": "Scheduled export request",
        "subject_vi": "Đề xuất xuất báo cáo theo lịch",
        "feature_en": "scheduled report exports",
        "feature_vi": "xuất báo cáo theo lịch",
        "request_en": "scheduled report export",
        "request_vi": "xuất báo cáo theo lịch",
        "review_en": "the monthly backlog review",
        "review_vi": "buổi rà soát backlog hàng tháng",
    },
]
PRODUCT_VARIANTS = [
    {
        "priority": "low",
        "deadline_en": "None",
        "deadline_vi": "None",
    },
    {
        "priority": "medium",
        "deadline_en": "by Friday 3 PM",
        "deadline_vi": "trước 15h thứ Sáu",
    },
]


@dataclass(frozen=True)
class GoldTriageRecord:
    domain: str
    language: str
    email: str
    summary: str
    priority: str
    action_items: list[str]
    deadlines: list[str]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate a clean email-triage seed dataset.")
    parser.add_argument(
        "--output_path",
        type=Path,
        default=DEFAULT_RAW_MAIL_TRIAGE_SEED_PATH,
        help="Path to write the generated raw JSONL dataset.",
    )
    parser.add_argument(
        "--total_rows",
        type=int,
        default=DEFAULT_TOTAL_ROWS,
        help="Total number of rows to generate. Must be a positive multiple of 4.",
    )
    return parser.parse_args()


def _pair(index: int) -> tuple[str, str]:
    return NAME_PAIRS[index % len(NAME_PAIRS)]


def _record_priority(index: int, variants: list[dict[str, str]]) -> dict[str, str]:
    return variants[(index // 3) % len(variants)]


def add_reference(email: str, *, language: str, domain: str, index: int) -> str:
    reference = f"{domain.upper()}-{index + 1:03d}"
    if language == "en":
        return email.replace("\n\nThanks.", f"\n\nReference: {reference}.\n\nThanks.")
    return email.replace("\n\nCảm ơn.", f"\n\nMã theo dõi: {reference}.\n\nCảm ơn.")


def extract_deadline_phrase(text: str) -> str:
    for marker in (" within ", " by ", " before ", " trong vòng ", " trước "):
        if marker in text:
            return marker.strip() + " " + text.split(marker, 1)[1].strip()
    return text.strip()


def build_ops_release_record(language: str, index: int) -> GoldTriageRecord:
    item = OPS_RELEASE_ITEMS[index % len(OPS_RELEASE_ITEMS)]
    variant = _record_priority(index, OPS_RELEASE_VARIANTS)
    owner, reviewer = _pair(index)
    blocker_action_en = f"Share any blocker in {item['channel_en']} before {variant['event_en']}"
    blocker_action_vi = f"Báo blocker trên {item['channel_vi']} trước {variant['event_vi']}"
    unconditional_blocker = (index // 4) % 2 == 0

    if language == "en":
        if unconditional_blocker:
            blocker_clause_en = (
                f", and share any blocker in {item['channel_en']} before {variant['event_en']}."
            )
        else:
            blocker_clause_en = (
                f". If anything slips, post it in {item['channel_en']} immediately."
            )
        email = (
            f"Subject: {item['subject_en']}\n\n"
            f"Hi ops team,\n\n"
            f"Before {variant['event_en']}, please have {owner} update the {item['deliverable_en']} "
            f"{variant['first_en']} and {reviewer} verify {item['review_en']} {variant['second_en']}"
            f"{blocker_clause_en}\n\n"
            "Thanks."
        )
        summary = (
            f"Ops needs the {item['deliverable_en']} and {item['review_en']} finished "
            f"before {variant['event_en']}."
        )
        actions = [
            f"{owner} updates the {item['deliverable_en']} {variant['first_en']}",
            f"{reviewer} verifies {item['review_en']} {variant['second_en']}",
        ]
        if unconditional_blocker:
            actions.append(blocker_action_en)
            deadlines = [variant["first_en"], variant["second_en"], variant["event_en"]]
        else:
            deadlines = [variant["first_en"], variant["second_en"]]
    else:
        if unconditional_blocker:
            blocker_clause_vi = (
                f", và báo blocker trên {item['channel_vi']} trước {variant['event_vi']}."
            )
        else:
            blocker_clause_vi = (
                f". Nếu phát sinh vấn đề, vui lòng thông báo trên {item['channel_vi']} ngay lập tức."
            )
        email = (
            f"Chủ đề: {item['subject_vi']}\n\n"
            f"Chào team ops,\n\n"
            f"Trước {variant['event_vi']}, nhờ {owner} cập nhật {item['deliverable_vi']} "
            f"{variant['first_vi']} và {reviewer} rà soát {item['review_vi']} {variant['second_vi']}"
            f"{blocker_clause_vi}\n\n"
            "Cảm ơn."
        )
        summary = (
            f"Team ops cần hoàn tất {item['deliverable_vi']} và {item['review_vi']} "
            f"trước {variant['event_vi']}."
        )
        actions = [
            f"{owner} cập nhật {item['deliverable_vi']} {variant['first_vi']}",
            f"{reviewer} rà soát {item['review_vi']} {variant['second_vi']}",
        ]
        if unconditional_blocker:
            actions.append(blocker_action_vi)
            deadlines = [variant["first_vi"], variant["second_vi"], variant["event_vi"]]
        else:
            deadlines = [variant["first_vi"], variant["second_vi"]]

    return GoldTriageRecord(
        domain="ops",
        language=language,
        email=add_reference(email, language=language, domain="ops", index=index),
        summary=summary,
        priority=variant["priority"],
        action_items=actions,
        deadlines=deadlines,
    )


def build_ops_schedule_record(language: str, index: int) -> GoldTriageRecord:
    item = OPS_SCHEDULE_ITEMS[index % len(OPS_SCHEDULE_ITEMS)]
    variant = _record_priority(index, OPS_SCHEDULE_VARIANTS)
    owner, reviewer = _pair(index + 1)

    if language == "en":
        confirm_phrase_en = variant["confirm_en"]
        if item["meeting_en"] == "launch sync" and variant["priority"] == "high":
            confirm_phrase_en = "by 2:30 PM today"
        email = (
            f"Subject: {item['subject_en']}\n\n"
            f"Hi operations,\n\n"
            f"Because {item['reason_en']}, the {item['meeting_en']} scheduled for {variant['old_en']} "
            f"needs to move to {variant['new_en']}. Please have {owner} update the calendar and "
            f"{reviewer} confirm {item['support_en']} {confirm_phrase_en}.\n\n"
            "Thanks."
        )
        if variant["priority"] == "high":
            summary = (
                f"The {item['meeting_en']} moved to {variant['new_en']}, and ops needs the schedule updated "
                "this afternoon."
            )
        else:
            summary = (
                f"The {item['meeting_en']} moved to {variant['new_en']}, and ops needs the schedule updated "
                f"{confirm_phrase_en}."
            )
        actions = [
            "Update the calendar",
            f"{reviewer} confirms {item['support_en']} {confirm_phrase_en}",
        ]
        deadlines = [confirm_phrase_en, variant["new_en"]]
    else:
        confirm_phrase_vi = variant["confirm_vi"]
        if item["meeting_vi"] == "launch sync" and variant["priority"] == "high":
            confirm_phrase_vi = "trước 14h30"
        email = (
            f"Chủ đề: {item['subject_vi']}\n\n"
            f"Chào team vận hành,\n\n"
            f"Vì {item['reason_vi']} nên {item['meeting_vi']} dự kiến vào {variant['old_vi']} "
            f"cần dời sang {variant['new_vi']}. Nhờ {owner} cập nhật lại lịch trên calendar và "
            f"{reviewer} xác nhận {item['support_vi']} {confirm_phrase_vi}.\n\n"
            "Cảm ơn."
        )
        if variant["priority"] == "high":
            summary = (
                f"{item['meeting_vi'].capitalize()} đã được dời sang {variant['new_vi']}, và team vận hành cần "
                "cập nhật lịch ngay chiều nay."
            )
        else:
            summary = (
                f"{item['meeting_vi'].capitalize()} đã được dời sang {variant['new_vi']}, và team vận hành cần "
                f"cập nhật lịch {confirm_phrase_vi}."
            )
        actions = [
            "Cập nhật calendar",
            f"{reviewer} xác nhận {item['support_vi']} {confirm_phrase_vi}",
        ]
        deadlines = [confirm_phrase_vi, variant["new_vi"]]

    return GoldTriageRecord(
        domain="ops",
        language=language,
        email=add_reference(email, language=language, domain="ops", index=100 + index),
        summary=summary,
        priority=variant["priority"],
        action_items=actions,
        deadlines=deadlines,
    )


def build_ops_fyi_record(language: str, index: int) -> GoldTriageRecord:
    item = OPS_FYI_ITEMS[index % len(OPS_FYI_ITEMS)]

    if language == "en":
        email = (
            f"Subject: {item['subject_en']}\n\n"
            "Hi team,\n\n"
            f"The {item['document_en']} for {item['context_en']} is now published in the operations wiki. "
            "No response is needed unless you spot a factual error.\n\n"
            "Thanks."
        )
        summary = f"The {item['document_en']} is available for reference, and no immediate action is required."
    else:
        email = (
            f"Chủ đề: {item['subject_vi']}\n\n"
            "Chào cả nhóm,\n\n"
            f"{item['document_vi'].capitalize()} phục vụ {item['context_vi']} đã được đăng trên wiki vận hành. "
            "Không cần phản hồi ngay trừ khi mọi người phát hiện lỗi thực tế.\n\n"
            "Cảm ơn."
        )
        summary = f"{item['document_vi'].capitalize()} đã sẵn sàng để tham khảo và chưa cần hành động ngay."

    return GoldTriageRecord(
        domain="ops",
        language=language,
        email=add_reference(email, language=language, domain="ops", index=200 + index),
        summary=summary,
        priority="low",
        action_items=["None"],
        deadlines=["None"],
    )


def build_support_incident_record(language: str, index: int) -> GoldTriageRecord:
    item = SUPPORT_INCIDENT_ITEMS[index % len(SUPPORT_INCIDENT_ITEMS)]
    variant = _record_priority(index, SUPPORT_INCIDENT_VARIANTS)

    if language == "en":
        email = (
            f"Subject: {item['subject_en']}\n\n"
            "Hi support,\n\n"
            f"We need help because {item['issue_en']}, and {item['impact_en']}. Please {variant['owner_en']} "
            f"and {variant['update_en']}. If engineering is not ready, please {item['workaround_en']}.\n\n"
            "Thanks."
        )
        summary = (
            f"Support needs to respond because {item['issue_en']} and {item['impact_en']}."
        )
        actions = [
            variant["owner_en"].replace("confirm ", "Confirm ").replace("capture ", "Capture "),
            variant["update_en"].replace("send ", "Send ").replace("share ", "Share ").replace("reply ", "Reply "),
            item["workaround_en"].capitalize(),
        ]
        deadlines = [
            extract_deadline_phrase(variant["owner_en"]),
            extract_deadline_phrase(variant["update_en"]),
        ]
    else:
        email = (
            f"Chủ đề: {item['subject_vi']}\n\n"
            "Chào team support,\n\n"
            f"Hiện tại {item['issue_vi']} và {item['impact_vi']}. Nhờ team {variant['owner_vi']} "
            f"và {variant['update_vi']}. Nếu engineering chưa sẵn sàng, vui lòng {item['workaround_vi']}.\n\n"
            "Cảm ơn."
        )
        summary = f"Team support cần phản hồi vì {item['issue_vi']} và {item['impact_vi']}."
        actions = [
            variant["owner_vi"].capitalize(),
            variant["update_vi"].capitalize(),
            item["workaround_vi"].capitalize(),
        ]
        deadlines = [
            extract_deadline_phrase(variant["owner_vi"]),
            extract_deadline_phrase(variant["update_vi"]),
        ]

    return GoldTriageRecord(
        domain="support",
        language=language,
        email=add_reference(email, language=language, domain="support", index=index),
        summary=summary,
        priority=variant["priority"],
        action_items=actions,
        deadlines=deadlines,
    )


def build_support_followup_record(language: str, index: int) -> GoldTriageRecord:
    item = SUPPORT_FOLLOWUP_ITEMS[index % len(SUPPORT_FOLLOWUP_ITEMS)]

    if language == "en":
        email = (
            f"Subject: {item['subject_en']}\n\n"
            "Hi support leads,\n\n"
            f"{item['issue_en'].capitalize()}. Please {item['request_en']}. Until then, {item['workaround_en']}.\n\n"
            "Thanks."
        )
        summary = f"Support needs a concise follow-up while {item['issue_en']}."
        actions = [
            item["request_en"].capitalize(),
            item["workaround_en"].capitalize(),
        ]
    else:
        email = (
            f"Chủ đề: {item['subject_vi']}\n\n"
            "Chào các lead support,\n\n"
            f"{item['issue_vi'].capitalize()}. Nhờ team {item['request_vi']}. Trong lúc chờ, vui lòng "
            f"{item['workaround_vi']}.\n\n"
            "Cảm ơn."
        )
        summary = f"Team support cần một bản follow-up ngắn gọn trong khi {item['issue_vi']}."
        actions = [
            item["request_vi"].capitalize(),
            item["workaround_vi"].capitalize(),
        ]

    return GoldTriageRecord(
        domain="support",
        language=language,
        email=add_reference(email, language=language, domain="support", index=100 + index),
        summary=summary,
        priority="medium",
        action_items=actions,
        deadlines=["None"],
    )


def build_support_fyi_record(language: str, index: int) -> GoldTriageRecord:
    item = SUPPORT_FYI_ITEMS[index % len(SUPPORT_FYI_ITEMS)]

    if language == "en":
        email = (
            f"Subject: {item['subject_en']}\n\n"
            "Hi support team,\n\n"
            f"The {item['note_en']} are now posted in {item['channel_en']}. No response is required unless "
            "someone finds an inaccurate detail.\n\n"
            "Thanks."
        )
        summary = "The support notes are available for reference and do not require immediate action."
    else:
        email = (
            f"Chủ đề: {item['subject_vi']}\n\n"
            "Chào team support,\n\n"
            f"{item['note_vi'].capitalize()} đã được đăng trong {item['channel_vi']}. Hiện chưa cần phản hồi "
            "trừ khi có chi tiết chưa chính xác.\n\n"
            "Cảm ơn."
        )
        summary = "Ghi chú support đã sẵn sàng để tham khảo và chưa cần hành động ngay."

    return GoldTriageRecord(
        domain="support",
        language=language,
        email=add_reference(email, language=language, domain="support", index=200 + index),
        summary=summary,
        priority="low",
        action_items=["None"],
        deadlines=["None"],
    )


def build_billing_record(language: str, index: int) -> GoldTriageRecord:
    item = BILLING_ITEMS[index % len(BILLING_ITEMS)]
    variant = _record_priority(index, BILLING_VARIANTS)

    if language == "en":
        email = (
            f"Subject: {item['subject_en']}\n\n"
            "Hi finance,\n\n"
            f"Please {item['request_en']}. Also {item['secondary_en']}."
        )
        if variant["deadline_en"] != "None":
            email += f" We need this done {variant['deadline_en']}.\n\nThanks."
            deadlines = [variant["deadline_en"]]
            second_action = f"{item['secondary_en'].capitalize()} {variant['deadline_en']}"
        else:
            email += " There is no hard deadline yet, but it should stay visible in the queue.\n\nThanks."
            deadlines = ["None"]
            second_action = item["secondary_en"].capitalize()
        summary = f"Finance needs to {item['request_en']} and keep the customer updated."
        actions = [
            item["request_en"].capitalize(),
            second_action,
        ]
    else:
        email = (
            f"Chủ đề: {item['subject_vi']}\n\n"
            "Chào team finance,\n\n"
            f"Nhờ team {item['request_vi']} và {item['secondary_vi']}."
        )
        if variant["deadline_vi"] != "None":
            email += f" Việc này cần hoàn tất {variant['deadline_vi']}.\n\nCảm ơn."
            deadlines = [variant["deadline_vi"]]
            second_action = f"{item['secondary_vi'].capitalize()} {variant['deadline_vi']}"
        else:
            email += " Hiện chưa có hạn chót cứng nhưng cần giữ đầu việc trong hàng chờ.\n\nCảm ơn."
            deadlines = ["None"]
            second_action = item["secondary_vi"].capitalize()
        summary = f"Team finance cần {item['request_vi']} và cập nhật lại cho khách hàng."
        actions = [
            item["request_vi"].capitalize(),
            second_action,
        ]

    return GoldTriageRecord(
        domain="billing",
        language=language,
        email=add_reference(email, language=language, domain="billing", index=index),
        summary=summary,
        priority=variant["priority"],
        action_items=actions,
        deadlines=deadlines,
    )


def build_product_record(language: str, index: int) -> GoldTriageRecord:
    item = PRODUCT_ITEMS[index % len(PRODUCT_ITEMS)]
    variant = _record_priority(index, PRODUCT_VARIANTS)

    if language == "en":
        email = (
            f"Subject: {item['subject_en']}\n\n"
            "Hi product,\n\n"
            f"A customer asked about {item['feature_en']}. Please log the {item['request_en']} request so it can be reviewed in "
            f"{item['review_en']}."
        )
        if variant["deadline_en"] != "None":
            email += f" If possible, share a quick status note {variant['deadline_en']}.\n\nThanks."
            deadlines = [variant["deadline_en"]]
            actions = [
                f"Log the {item['request_en']} request",
                f"Share a quick status note {variant['deadline_en']}",
            ]
        else:
            email += " No immediate reply is required.\n\nThanks."
            deadlines = ["None"]
            actions = [
                f"Log the {item['request_en']} request",
            ]
        summary = f"Product should log the {item['request_en']} request for {item['review_en']}."
    else:
        email = (
            f"Chủ đề: {item['subject_vi']}\n\n"
            "Chào team sản phẩm,\n\n"
            f"Khách hàng vừa hỏi về {item['feature_vi']}. Nhờ team ghi nhận yêu cầu {item['request_vi']} để đưa vào "
            f"{item['review_vi']}."
        )
        if variant["deadline_vi"] != "None":
            email += f" Nếu thuận tiện, vui lòng cập nhật trạng thái {variant['deadline_vi']}.\n\nCảm ơn."
            deadlines = [variant["deadline_vi"]]
            actions = [
                f"Ghi nhận yêu cầu {item['request_vi']}",
                f"Cập nhật trạng thái {variant['deadline_vi']}",
            ]
        else:
            email += " Hiện chưa cần phản hồi gấp.\n\nCảm ơn."
            deadlines = ["None"]
            actions = [
                f"Ghi nhận yêu cầu {item['request_vi']}",
            ]
        summary = f"Team sản phẩm nên ghi nhận yêu cầu {item['request_vi']} cho {item['review_vi']}."

    return GoldTriageRecord(
        domain="product",
        language=language,
        email=add_reference(email, language=language, domain="product", index=index),
        summary=summary,
        priority=variant["priority"],
        action_items=actions,
        deadlines=deadlines,
    )


def build_domain_records(language: str, count: int, builders: list) -> list[GoldTriageRecord]:
    records: list[GoldTriageRecord] = []
    local_index = 0
    while len(records) < count:
        builder = builders[local_index % len(builders)]
        records.append(builder(language, local_index))
        local_index += 1
    return records


def build_record_catalog() -> list[GoldTriageRecord]:
    records: list[GoldTriageRecord] = []
    records.extend(
        build_domain_records(
            "en",
            80,
            [build_ops_release_record, build_ops_schedule_record, build_ops_schedule_record, build_ops_fyi_record],
        )
    )
    records.extend(
        build_domain_records(
            "en",
            60,
            [build_support_incident_record, build_support_followup_record, build_support_fyi_record],
        )
    )
    records.extend(
        build_domain_records(
            "vi",
            35,
            [build_ops_release_record, build_ops_schedule_record, build_ops_schedule_record, build_ops_fyi_record],
        )
    )
    records.extend(build_domain_records("vi", 20, [build_support_incident_record, build_support_followup_record, build_support_fyi_record]))
    records.extend(build_domain_records("en", 20, [build_billing_record]))
    records.extend(build_domain_records("en", 10, [build_product_record]))
    records.extend(build_domain_records("vi", 15, [build_billing_record]))
    records.extend(build_domain_records("vi", 10, [build_product_record]))
    return records


def rows_from_record(record: GoldTriageRecord) -> list[dict[str, str]]:
    language = record.language
    return [
        {
            "instruction": SUMMARY_INSTRUCTIONS[language],
            "input": record.email,
            "output": record.summary,
            "domain": record.domain,
            "language": record.language,
        },
        {
            "instruction": PRIORITY_INSTRUCTIONS[language],
            "input": record.email,
            "output": record.priority,
            "domain": record.domain,
            "language": record.language,
        },
        {
            "instruction": ACTION_INSTRUCTIONS[language],
            "input": record.email,
            "output": format_action_extraction(
                record.action_items,
                record.deadlines,
                language=language,
            ),
            "domain": record.domain,
            "language": record.language,
        },
        {
            "instruction": TRIAGE_INSTRUCTIONS[language],
            "input": record.email,
            "output": format_full_triage(
                record.summary,
                record.priority,
                record.action_items,
                record.deadlines,
                language=language,
            ),
            "domain": record.domain,
            "language": record.language,
        },
    ]


def build_rows(total_rows: int = DEFAULT_TOTAL_ROWS) -> list[dict[str, str]]:
    if total_rows <= 0 or total_rows % ROWS_PER_RECORD != 0:
        raise ValueError("total_rows must be a positive multiple of 4.")

    records = build_record_catalog()
    max_rows = len(records) * ROWS_PER_RECORD
    if total_rows > max_rows:
        raise ValueError(f"total_rows cannot exceed {max_rows}.")

    selected_record_count = total_rows // ROWS_PER_RECORD
    rows: list[dict[str, str]] = []
    for record in records[:selected_record_count]:
        rows.extend(rows_from_record(record))
    return rows


def main() -> None:
    args = parse_args()
    rows = build_rows(args.total_rows)
    write_jsonl(args.output_path, rows)
    print(f"Wrote {len(rows)} rows to {Path(args.output_path).expanduser().resolve()}")


if __name__ == "__main__":
    main()
