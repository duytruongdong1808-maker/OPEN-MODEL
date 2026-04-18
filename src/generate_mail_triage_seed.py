from __future__ import annotations

import argparse
import unicodedata
from pathlib import Path

try:
    from .utils import DEFAULT_RAW_MAIL_TRIAGE_SEED_PATH, write_jsonl
except ImportError:
    from utils import DEFAULT_RAW_MAIL_TRIAGE_SEED_PATH, write_jsonl


ROWS_PER_CASE = 8
DEFAULT_TOTAL_ROWS = 1000
MAX_CASE_COUNT = 125

VI_SUMMARY = "Tóm tắt email sau trong một câu ngắn."
EN_SUMMARY = "Summarize this email in one short sentence."
VI_PRIORITY = "Cho biết mức ưu tiên của email này: cao, trung bình, hay thấp."
EN_PRIORITY = "Classify the priority of this email as high, medium, or low."
VI_ACTION = "Trích xuất việc cần làm và hạn chót từ email sau dưới dạng danh sách gạch đầu dòng ngắn."
EN_ACTION = "Extract the action items and deadlines from this email as a short bullet list."
VI_TRIAGE = "Đọc email sau và trả về bản triage gồm Tóm tắt, Ưu tiên, Việc cần làm, Hạn chót."
EN_TRIAGE = "Read this email and return a triage block with Summary, Priority, Action items, and Deadlines."

INTERNAL_ITEMS = [
    {
        "subject_vi": "Chốt checklist phát hành",
        "subject_en": "Final release checklist",
        "deliverable_vi": "checklist phát hành",
        "deliverable_en": "release checklist",
        "owner": "Lan",
        "reviewer": "Huy",
        "review_task_vi": "xác nhận rollback plan",
        "review_task_en": "confirm the rollback plan",
        "channel_vi": "kênh release",
        "channel_en": "release channel",
    },
    {
        "subject_vi": "Rà soát ghi chú bàn giao",
        "subject_en": "Review the handoff notes",
        "deliverable_vi": "ghi chú bàn giao",
        "deliverable_en": "handoff notes",
        "owner": "Minh",
        "reviewer": "Trang",
        "review_task_vi": "kiểm tra danh sách rủi ro còn mở",
        "review_task_en": "check the list of open risks",
        "channel_vi": "nhóm vận hành",
        "channel_en": "operations group",
    },
    {
        "subject_vi": "Hoàn tất bảng xác nhận staging",
        "subject_en": "Complete the staging validation sheet",
        "deliverable_vi": "bảng xác nhận staging",
        "deliverable_en": "staging validation sheet",
        "owner": "An",
        "reviewer": "Bảo",
        "review_task_vi": "xác nhận trạng thái dependency cuối cùng",
        "review_task_en": "confirm the final dependency status",
        "channel_vi": "kênh staging",
        "channel_en": "staging channel",
    },
    {
        "subject_vi": "Cập nhật danh sách quyền truy cập",
        "subject_en": "Update the access list",
        "deliverable_vi": "danh sách quyền truy cập",
        "deliverable_en": "access list",
        "owner": "Vy",
        "reviewer": "Quân",
        "review_task_vi": "kiểm tra danh sách tài khoản đặc biệt",
        "review_task_en": "review the list of privileged accounts",
        "channel_vi": "kênh bảo mật",
        "channel_en": "security channel",
    },
    {
        "subject_vi": "Chốt slide readout nội bộ",
        "subject_en": "Finalize the internal readout deck",
        "deliverable_vi": "slide readout nội bộ",
        "deliverable_en": "internal readout deck",
        "owner": "Linh",
        "reviewer": "Khôi",
        "review_task_vi": "xác nhận số liệu cuối cùng",
        "review_task_en": "confirm the final metrics",
        "channel_vi": "nhóm dự án",
        "channel_en": "project thread",
    },
]

INTERNAL_VARIANTS = [
    {
        "priority_vi": "cao",
        "priority_en": "high",
        "first_vi": "trước 15h hôm nay",
        "first_en": "by 3 PM today",
        "second_vi": "trước 16h hôm nay",
        "second_en": "by 4 PM today",
        "event_vi": "đợt phát hành lúc 18h hôm nay",
        "event_en": "today's 6 PM release",
    },
    {
        "priority_vi": "trung bình",
        "priority_en": "medium",
        "first_vi": "trước 11h ngày mai",
        "first_en": "by 11 AM tomorrow",
        "second_vi": "trước 13h ngày mai",
        "second_en": "by 1 PM tomorrow",
        "event_vi": "buổi tổng rà soát ngày mai",
        "event_en": "tomorrow's review session",
    },
    {
        "priority_vi": "cao",
        "priority_en": "high",
        "first_vi": "trong 2 giờ tới",
        "first_en": "within the next 2 hours",
        "second_vi": "trước 17h hôm nay",
        "second_en": "by 5 PM today",
        "event_vi": "mốc bàn giao cuối ngày",
        "event_en": "today's end-of-day handoff",
    },
    {
        "priority_vi": "trung bình",
        "priority_en": "medium",
        "first_vi": "trước trưa thứ Năm",
        "first_en": "before Thursday noon",
        "second_vi": "trước 15h thứ Năm",
        "second_en": "by 3 PM Thursday",
        "event_vi": "buổi demo thứ Năm",
        "event_en": "Thursday's demo",
    },
    {
        "priority_vi": "thấp",
        "priority_en": "low",
        "first_vi": "trước cuối tuần",
        "first_en": "before the end of the week",
        "second_vi": "trước thứ Hai tuần sau",
        "second_en": "by next Monday",
        "event_vi": "buổi planning đầu tuần sau",
        "event_en": "next week's planning session",
    },
]

SCHEDULING_ITEMS = [
    {
        "subject_vi": "Dời lịch họp triển khai",
        "subject_en": "Rescheduled implementation meeting",
        "meeting_vi": "họp triển khai",
        "meeting_en": "implementation meeting",
        "reason_vi": "khách hàng chưa chốt xong dữ liệu đầu vào",
        "reason_en": "the client has not finalized the input data",
        "coord": "Lan",
        "support": "Minh",
        "support_task_vi": "xác nhận phòng họp",
        "support_task_en": "confirm the meeting room",
    },
    {
        "subject_vi": "Dời lịch buổi kickoff",
        "subject_en": "Kickoff meeting moved",
        "meeting_vi": "buổi kickoff",
        "meeting_en": "kickoff meeting",
        "reason_vi": "đầu mối phía đối tác bị trùng lịch đột xuất",
        "reason_en": "the partner lead had an unexpected conflict",
        "coord": "Trang",
        "support": "An",
        "support_task_vi": "gửi lại meeting link",
        "support_task_en": "resend the meeting link",
    },
    {
        "subject_vi": "Cập nhật lịch workshop",
        "subject_en": "Workshop schedule update",
        "meeting_vi": "workshop nội bộ",
        "meeting_en": "internal workshop",
        "reason_vi": "diễn giả cần thêm thời gian chuẩn bị",
        "reason_en": "the speaker needs more prep time",
        "coord": "Bảo",
        "support": "Vy",
        "support_task_vi": "cập nhật lịch trên calendar",
        "support_task_en": "update the calendar entry",
    },
    {
        "subject_vi": "Dời lịch demo khách hàng",
        "subject_en": "Customer demo rescheduled",
        "meeting_vi": "demo khách hàng",
        "meeting_en": "customer demo",
        "reason_vi": "khách hàng muốn thêm người tham gia",
        "reason_en": "the customer wants additional attendees",
        "coord": "Khôi",
        "support": "Linh",
        "support_task_vi": "xác nhận lại danh sách tham gia",
        "support_task_en": "confirm the attendee list again",
    },
    {
        "subject_vi": "Điều chỉnh lịch review định kỳ",
        "subject_en": "Recurring review time change",
        "meeting_vi": "review định kỳ",
        "meeting_en": "recurring review",
        "reason_vi": "lịch ban điều hành thay đổi",
        "reason_en": "the leadership schedule changed",
        "coord": "Quân",
        "support": "Mai",
        "support_task_vi": "cập nhật phòng họp và agenda",
        "support_task_en": "update the room booking and agenda",
    },
]

SCHEDULING_VARIANTS = [
    {
        "priority_vi": "cao",
        "priority_en": "high",
        "day_vi": "chiều nay",
        "day_en": "this afternoon",
        "old_vi": "13h",
        "old_en": "1 PM",
        "new_vi": "16h",
        "new_en": "4 PM",
        "confirm_vi": "trước 12h hôm nay",
        "confirm_en": "by noon today",
    },
    {
        "priority_vi": "trung bình",
        "priority_en": "medium",
        "day_vi": "ngày mai",
        "day_en": "tomorrow",
        "old_vi": "9h",
        "old_en": "9 AM",
        "new_vi": "14h",
        "new_en": "2 PM",
        "confirm_vi": "trước 11h ngày hôm nay",
        "confirm_en": "by 11 AM today",
    },
    {
        "priority_vi": "trung bình",
        "priority_en": "medium",
        "day_vi": "thứ Năm",
        "day_en": "Thursday",
        "old_vi": "10h",
        "old_en": "10 AM",
        "new_vi": "15h",
        "new_en": "3 PM",
        "confirm_vi": "trước 17h hôm nay",
        "confirm_en": "by 5 PM today",
    },
    {
        "priority_vi": "cao",
        "priority_en": "high",
        "day_vi": "sáng mai",
        "day_en": "tomorrow morning",
        "old_vi": "8h30",
        "old_en": "8:30 AM",
        "new_vi": "11h",
        "new_en": "11 AM",
        "confirm_vi": "trong vòng 1 giờ",
        "confirm_en": "within the next hour",
    },
    {
        "priority_vi": "thấp",
        "priority_en": "low",
        "day_vi": "tuần sau",
        "day_en": "next week",
        "old_vi": "thứ Ba 14h",
        "old_en": "Tuesday 2 PM",
        "new_vi": "thứ Tư 10h",
        "new_en": "Wednesday 10 AM",
        "confirm_vi": "trước cuối tuần",
        "confirm_en": "before the end of the week",
    },
]

SUPPORT_ITEMS = [
    {
        "subject_vi": "Sự cố đăng nhập cổng billing",
        "subject_en": "Billing portal login outage",
        "issue_vi": "không đăng nhập được vào cổng billing",
        "issue_en": "cannot log in to the billing portal",
        "group_vi": "sales team",
        "group_en": "the sales team",
        "follow_up_vi": "cập nhật trạng thái xử lý",
        "follow_up_en": "share a status update",
        "workaround_vi": "gửi tạm workaround",
        "workaround_en": "send a temporary workaround",
    },
    {
        "subject_vi": "Lỗi export CSV cho khách hàng",
        "subject_en": "CSV export issue for customer",
        "issue_vi": "file export CSV bị thiếu cột trạng thái",
        "issue_en": "the CSV export is missing the status column",
        "group_vi": "khách hàng Acorn",
        "group_en": "customer Acorn",
        "follow_up_vi": "phản hồi kết quả reproduce",
        "follow_up_en": "reply with the reproduce result",
        "workaround_vi": "gửi hướng dẫn tạm thời",
        "workaround_en": "send temporary guidance",
    },
    {
        "subject_vi": "Chậm đồng bộ webhook",
        "subject_en": "Webhook sync delay",
        "issue_vi": "webhook đồng bộ chậm hơn bình thường",
        "issue_en": "the webhook sync is slower than normal",
        "group_vi": "khách hàng Orion",
        "group_en": "customer Orion",
        "follow_up_vi": "cập nhật nguyên nhân sơ bộ",
        "follow_up_en": "share a preliminary root cause",
        "workaround_vi": "đề xuất cách theo dõi tạm thời",
        "workaround_en": "suggest a temporary monitoring workaround",
    },
    {
        "subject_vi": "Lỗi tải file đính kèm",
        "subject_en": "Attachment download error",
        "issue_vi": "người dùng tải file đính kèm thất bại",
        "issue_en": "users are failing to download attachments",
        "group_vi": "khách hàng GreenLeaf",
        "group_en": "customer GreenLeaf",
        "follow_up_vi": "cập nhật tiến độ xử lý",
        "follow_up_en": "share the handling progress",
        "workaround_vi": "gửi link tải thay thế",
        "workaround_en": "send an alternate download link",
    },
    {
        "subject_vi": "Lỗi hiển thị dashboard",
        "subject_en": "Dashboard display issue",
        "issue_vi": "dashboard hiển thị sai số liệu ở widget chính",
        "issue_en": "the dashboard shows incorrect metrics in the main widget",
        "group_vi": "khách hàng Northwind",
        "group_en": "customer Northwind",
        "follow_up_vi": "cập nhật ETA khắc phục",
        "follow_up_en": "share the mitigation ETA",
        "workaround_vi": "gửi cách xem số liệu từ báo cáo gốc",
        "workaround_en": "share how to view the raw report instead",
    },
]

SUPPORT_VARIANTS = [
    {
        "priority_vi": "cao",
        "priority_en": "high",
        "impact_vi": "đang chặn hai hợp đồng gia hạn",
        "impact_en": "is blocking two renewal deals",
        "reply_vi": "trong vòng 30 phút",
        "reply_en": "within 30 minutes",
    },
    {
        "priority_vi": "trung bình",
        "priority_en": "medium",
        "impact_vi": "ảnh hưởng đến báo cáo khách hàng tuần này",
        "impact_en": "is affecting this week's customer report",
        "reply_vi": "trong hôm nay",
        "reply_en": "today",
    },
    {
        "priority_vi": "cao",
        "priority_en": "high",
        "impact_vi": "đang làm gián đoạn buổi demo sáng mai",
        "impact_en": "is disrupting tomorrow morning's demo",
        "reply_vi": "trước 10h sáng mai",
        "reply_en": "by 10 AM tomorrow",
    },
    {
        "priority_vi": "trung bình",
        "priority_en": "medium",
        "impact_vi": "khiến khách hàng phải thao tác thủ công",
        "impact_en": "is forcing the customer to use a manual workaround",
        "reply_vi": "trước 17h hôm nay",
        "reply_en": "by 5 PM today",
    },
    {
        "priority_vi": "thấp",
        "priority_en": "low",
        "impact_vi": "được ghi nhận nhưng chưa chặn vận hành",
        "impact_en": "has been reported but is not blocking operations",
        "reply_vi": "trước cuối tuần",
        "reply_en": "before the end of the week",
    },
]

BILLING_ITEMS = [
    {
        "subject_vi": "Hóa đơn đến hạn ngày mai",
        "subject_en": "Invoice due tomorrow",
        "request_vi": "xác nhận thanh toán hóa đơn INV-204",
        "request_en": "confirm payment for invoice INV-204",
        "secondary_vi": "phản hồi cho khách hàng",
        "secondary_en": "reply to the customer",
        "customer_vi": "khách hàng Orion",
        "customer_en": "customer Orion",
    },
    {
        "subject_vi": "Gửi renewal quote bản cuối",
        "subject_en": "Send the final renewal quote",
        "request_vi": "gửi renewal quote cuối cho GreenLeaf",
        "request_en": "send the final renewal quote to GreenLeaf",
        "secondary_vi": "trả lời câu hỏi về mức discount cũ",
        "secondary_en": "answer the question about the previous discount level",
        "customer_vi": "khách hàng GreenLeaf",
        "customer_en": "customer GreenLeaf",
    },
    {
        "subject_vi": "Rà soát yêu cầu hoàn tiền",
        "subject_en": "Review the refund request",
        "request_vi": "xác minh yêu cầu hoàn tiền cho đơn hàng tháng 4",
        "request_en": "verify the refund request for the April order",
        "secondary_vi": "cập nhật lại timeline xử lý",
        "secondary_en": "update the expected handling timeline",
        "customer_vi": "khách hàng Acorn",
        "customer_en": "customer Acorn",
    },
    {
        "subject_vi": "Phát hành credit note",
        "subject_en": "Issue the credit note",
        "request_vi": "phát hành credit note cho invoice điều chỉnh",
        "request_en": "issue the credit note for the adjusted invoice",
        "secondary_vi": "gửi bản PDF cho khách hàng",
        "secondary_en": "send the PDF copy to the customer",
        "customer_vi": "khách hàng Northwind",
        "customer_en": "customer Northwind",
    },
    {
        "subject_vi": "Xác nhận PO trước khi xuất hóa đơn",
        "subject_en": "Confirm the PO before invoicing",
        "request_vi": "xác nhận mã PO trước khi xuất hóa đơn",
        "request_en": "confirm the PO number before issuing the invoice",
        "secondary_vi": "đồng bộ lại với đội sales",
        "secondary_en": "sync again with the sales team",
        "customer_vi": "khách hàng BrightPath",
        "customer_en": "customer BrightPath",
    },
]

BILLING_VARIANTS = [
    {
        "priority_vi": "cao",
        "priority_en": "high",
        "deadline_vi": "trước 16h hôm nay",
        "deadline_en": "by 4 PM today",
        "context_vi": "để tránh gián đoạn dịch vụ",
        "context_en": "to avoid service interruption",
    },
    {
        "priority_vi": "trung bình",
        "priority_en": "medium",
        "deadline_vi": "trước 12h trưa thứ Năm",
        "deadline_en": "by Thursday noon",
        "context_vi": "để sales kịp follow-up",
        "context_en": "so sales can follow up in time",
    },
    {
        "priority_vi": "cao",
        "priority_en": "high",
        "deadline_vi": "trong hôm nay",
        "deadline_en": "today",
        "context_vi": "vì khách hàng đang chờ xác nhận cuối cùng",
        "context_en": "because the customer is waiting for the final confirmation",
    },
    {
        "priority_vi": "trung bình",
        "priority_en": "medium",
        "deadline_vi": "trước 10h sáng mai",
        "deadline_en": "by 10 AM tomorrow",
        "context_vi": "để finance chốt batch thanh toán tiếp theo",
        "context_en": "so finance can close the next payment batch",
    },
    {
        "priority_vi": "thấp",
        "priority_en": "low",
        "deadline_vi": "Không có",
        "deadline_en": "None",
        "context_vi": "khi có thời gian trong tuần này",
        "context_en": "when the team has time later this week",
    },
]

PRODUCT_ITEMS = [
    {
        "subject_vi": "Ghi nhận đề xuất dark mode",
        "subject_en": "Log the dark mode request",
        "feature_vi": "dark mode",
        "feature_en": "dark mode",
        "customer_vi": "khách hàng enterprise Orion",
        "customer_en": "enterprise customer Orion",
    },
    {
        "subject_vi": "Đề xuất xuất báo cáo theo lịch",
        "subject_en": "Scheduled report export request",
        "feature_vi": "xuất báo cáo theo lịch",
        "feature_en": "scheduled report export",
        "customer_vi": "khách hàng GreenLeaf",
        "customer_en": "customer GreenLeaf",
    },
    {
        "subject_vi": "Yêu cầu hỗ trợ nhiều phê duyệt viên",
        "subject_en": "Multi-approver workflow request",
        "feature_vi": "workflow nhiều phê duyệt viên",
        "feature_en": "multi-approver workflow",
        "customer_vi": "khách hàng Northwind",
        "customer_en": "customer Northwind",
    },
    {
        "subject_vi": "Đề xuất bộ lọc dashboard mới",
        "subject_en": "New dashboard filter request",
        "feature_vi": "bộ lọc dashboard theo khu vực",
        "feature_en": "regional dashboard filter",
        "customer_vi": "khách hàng BrightPath",
        "customer_en": "customer BrightPath",
    },
    {
        "subject_vi": "Đề xuất thông báo qua SMS",
        "subject_en": "SMS notification request",
        "feature_vi": "thông báo qua SMS",
        "feature_en": "SMS notifications",
        "customer_vi": "khách hàng Acorn",
        "customer_en": "customer Acorn",
    },
]

PRODUCT_VARIANTS = [
    {
        "priority_vi": "thấp",
        "priority_en": "low",
        "deadline_vi": "Không có",
        "deadline_en": "None",
        "review_vi": "roadmap review tuần sau",
        "review_en": "next week's roadmap review",
    },
    {
        "priority_vi": "trung bình",
        "priority_en": "medium",
        "deadline_vi": "trước cuối tuần",
        "deadline_en": "before the end of the week",
        "review_vi": "buổi grooming cuối tuần này",
        "review_en": "this week's backlog grooming",
    },
    {
        "priority_vi": "thấp",
        "priority_en": "low",
        "deadline_vi": "trước thứ Hai tuần sau",
        "deadline_en": "by next Monday",
        "review_vi": "planning đầu tuần sau",
        "review_en": "next week's planning session",
    },
    {
        "priority_vi": "trung bình",
        "priority_en": "medium",
        "deadline_vi": "trước 15h thứ Sáu",
        "deadline_en": "by 3 PM Friday",
        "review_vi": "cuộc họp ưu tiên tính năng thứ Sáu",
        "review_en": "Friday's feature prioritization meeting",
    },
    {
        "priority_vi": "thấp",
        "priority_en": "low",
        "deadline_vi": "Không có",
        "deadline_en": "None",
        "review_vi": "đợt rà soát backlog tháng này",
        "review_en": "this month's backlog review",
    },
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate a bilingual email-triage seed dataset."
    )
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
        help="Total number of rows to generate. Must be a multiple of 8.",
    )
    return parser.parse_args()


def triage_output(
    summary: str,
    priority: str,
    actions: list[str],
    deadlines: str,
    *,
    vi: bool,
) -> str:
    if vi:
        return (
            f"Tóm tắt: {summary}\n"
            f"Ưu tiên: {priority}\n"
            f"Việc cần làm:\n{chr(10).join(actions)}\n"
            f"Hạn chót: {deadlines}"
        )
    return (
        f"Summary: {summary}\n"
        f"Priority: {priority}\n"
        f"Action items:\n{chr(10).join(actions)}\n"
        f"Deadlines: {deadlines}"
    )


def ascii_name(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value)
    return "".join(char for char in normalized if not unicodedata.combining(char))


def build_internal_case(local_index: int) -> dict[str, object]:
    item = INTERNAL_ITEMS[local_index % len(INTERNAL_ITEMS)]
    variant = INTERNAL_VARIANTS[local_index // len(INTERNAL_ITEMS)]
    owner_en = ascii_name(str(item["owner"]))
    reviewer_en = ascii_name(str(item["reviewer"]))
    return {
        "vi_email": (
            f"Chủ đề: {item['subject_vi']}\n\n"
            f"Chào cả nhóm,\n\n"
            f"Trước {variant['event_vi']}, nhờ {item['owner']} cập nhật "
            f"{item['deliverable_vi']} {variant['first_vi']} và {item['reviewer']} "
            f"{item['review_task_vi']} {variant['second_vi']}. Nếu có blocker mới, "
            f"báo lại ngay trên {item['channel_vi']}.\n\n"
            "Cảm ơn."
        ),
        "en_email": (
            f"Subject: {item['subject_en']}\n\n"
            f"Hi team,\n\n"
            f"Before {variant['event_en']}, please have {owner_en} update the "
            f"{item['deliverable_en']} {variant['first_en']} and {reviewer_en} "
            f"{item['review_task_en']} {variant['second_en']}. If any new blocker appears, "
            f"post it in the {item['channel_en']} immediately.\n\n"
            "Thanks."
        ),
        "vi_summary": (
            f"Nhóm cần hoàn tất {item['deliverable_vi']} và {item['review_task_vi']} "
            f"trước {variant['event_vi']}."
        ),
        "en_summary": (
            f"The team needs the {item['deliverable_en']} updated and the review task "
            f"completed before {variant['event_en']}."
        ),
        "vi_priority": variant["priority_vi"],
        "en_priority": variant["priority_en"],
        "vi_actions": [
            f"- {item['owner']} cập nhật {item['deliverable_vi']} {variant['first_vi']}",
            f"- {item['reviewer']} {item['review_task_vi']} {variant['second_vi']}",
            "- Báo ngay nếu phát sinh blocker mới",
        ],
        "en_actions": [
            f"- {owner_en} updates the {item['deliverable_en']} {variant['first_en']}",
            f"- {reviewer_en} {item['review_task_en']} {variant['second_en']}",
            "- Report any new blocker immediately",
        ],
        "vi_deadlines": (
            f"{variant['first_vi']}; {variant['second_vi']}; {variant['event_vi']}"
        ),
        "en_deadlines": (
            f"{variant['first_en']}; {variant['second_en']}; {variant['event_en']}"
        ),
    }


def build_scheduling_case(local_index: int) -> dict[str, object]:
    item = SCHEDULING_ITEMS[local_index % len(SCHEDULING_ITEMS)]
    variant = SCHEDULING_VARIANTS[local_index // len(SCHEDULING_ITEMS)]
    coord_en = ascii_name(str(item["coord"]))
    support_en = ascii_name(str(item["support"]))
    return {
        "vi_email": (
            f"Chủ đề: {item['subject_vi']}\n\n"
            f"Chào cả nhóm,\n\n"
            f"Vì {item['reason_vi']} nên {item['meeting_vi']} vào {variant['day_vi']} lúc "
            f"{variant['old_vi']} cần dời sang {variant['new_vi']}. Nhờ {item['coord']} cập nhật "
            f"lại lịch trên calendar và {item['support']} {item['support_task_vi']} "
            f"{variant['confirm_vi']}.\n\n"
            "Cảm ơn."
        ),
        "en_email": (
            f"Subject: {item['subject_en']}\n\n"
            f"Hi team,\n\n"
            f"Because {item['reason_en']}, the {item['meeting_en']} on {variant['day_en']} at "
            f"{variant['old_en']} needs to move to {variant['new_en']}. Please have {coord_en} "
            f"update the calendar and {support_en} {item['support_task_en']} "
            f"{variant['confirm_en']}.\n\n"
            "Thanks."
        ),
        "vi_summary": (
            f"{item['meeting_vi'].capitalize()} vào {variant['day_vi']} được dời từ "
            f"{variant['old_vi']} sang {variant['new_vi']} và nhóm cần cập nhật lịch "
            f"{variant['confirm_vi']}."
        ),
        "en_summary": (
            f"The {item['meeting_en']} on {variant['day_en']} moved from {variant['old_en']} "
            f"to {variant['new_en']}, and the schedule must be updated {variant['confirm_en']}."
        ),
        "vi_priority": variant["priority_vi"],
        "en_priority": variant["priority_en"],
        "vi_actions": [
            f"- {item['coord']} cập nhật lại lịch trên calendar {variant['confirm_vi']}",
            f"- {item['support']} {item['support_task_vi']} {variant['confirm_vi']}",
        ],
        "en_actions": [
            f"- {coord_en} updates the calendar {variant['confirm_en']}",
            f"- {support_en} {item['support_task_en']} {variant['confirm_en']}",
        ],
        "vi_deadlines": (
            f"{variant['confirm_vi']}; lịch mới {variant['day_vi']} lúc {variant['new_vi']}"
        ),
        "en_deadlines": (
            f"{variant['confirm_en']}; new meeting time {variant['day_en']} at {variant['new_en']}"
        ),
    }


def build_support_case(local_index: int) -> dict[str, object]:
    item = SUPPORT_ITEMS[local_index % len(SUPPORT_ITEMS)]
    variant = SUPPORT_VARIANTS[local_index // len(SUPPORT_ITEMS)]
    return {
        "vi_email": (
            f"Chủ đề: {item['subject_vi']}\n\n"
            f"Chào team support,\n\n"
            f"{item['group_vi'].capitalize()} báo rằng họ {item['issue_vi']} và việc này "
            f"{variant['impact_vi']}. Nhờ team kiểm tra giúp và {item['follow_up_vi']} "
            f"{variant['reply_vi']}. Nếu chưa fix kịp, vui lòng {item['workaround_vi']}.\n\n"
            "Cảm ơn."
        ),
        "en_email": (
            f"Subject: {item['subject_en']}\n\n"
            f"Hi support team,\n\n"
            f"{item['group_en'].capitalize()} reported that they {item['issue_en']}, and this "
            f"{variant['impact_en']}. Please investigate and {item['follow_up_en']} "
            f"{variant['reply_en']}. If the fix is not ready yet, please {item['workaround_en']}.\n\n"
            "Thanks."
        ),
        "vi_summary": (
            f"Team support cần xử lý việc {item['issue_vi']} vì sự cố này {variant['impact_vi']}."
        ),
        "en_summary": (
            f"Support needs to address the fact that {item['group_en']} {item['issue_en']}, "
            f"because it {variant['impact_en']}."
        ),
        "vi_priority": variant["priority_vi"],
        "en_priority": variant["priority_en"],
        "vi_actions": [
            f"- Kiểm tra sự cố {item['issue_vi']}",
            f"- {item['follow_up_vi'].capitalize()} {variant['reply_vi']}",
            f"- {item['workaround_vi'].capitalize()} nếu chưa fix kịp",
        ],
        "en_actions": [
            f"- Investigate why {item['group_en']} {item['issue_en']}",
            f"- {item['follow_up_en'].capitalize()} {variant['reply_en']}",
            f"- {item['workaround_en'].capitalize()} if the fix is not ready",
        ],
        "vi_deadlines": variant["reply_vi"],
        "en_deadlines": variant["reply_en"],
    }


def build_billing_case(local_index: int) -> dict[str, object]:
    item = BILLING_ITEMS[local_index % len(BILLING_ITEMS)]
    variant = BILLING_VARIANTS[local_index // len(BILLING_ITEMS)]
    when_vi = (
        variant["deadline_vi"].lower()
        if variant["deadline_vi"] != "Không có"
        else "khi có thời gian"
    )
    when_en = (
        variant["deadline_en"]
        if variant["deadline_en"] != "None"
        else "when the team has time"
    )
    return {
        "vi_email": (
            f"Chủ đề: {item['subject_vi']}\n\n"
            f"Chào team finance,\n\n"
            f"{item['customer_vi'].capitalize()} đang cần bên mình {item['request_vi']}. "
            f"Nhờ team {item['request_vi']} {when_vi} và {item['secondary_vi']} "
            f"{variant['context_vi']}.\n\n"
            "Cảm ơn."
        ),
        "en_email": (
            f"Subject: {item['subject_en']}\n\n"
            f"Hi finance team,\n\n"
            f"{item['customer_en'].capitalize()} needs us to {item['request_en']}. "
            f"Please {item['request_en']} {when_en} and {item['secondary_en']} "
            f"{variant['context_en']}.\n\n"
            "Thanks."
        ),
        "vi_summary": (
            f"Team finance được nhờ {item['request_vi']} và {item['secondary_vi']} "
            f"{variant['context_vi']}."
        ),
        "en_summary": (
            f"Finance is asked to {item['request_en']} and {item['secondary_en']} "
            f"{variant['context_en']}."
        ),
        "vi_priority": variant["priority_vi"],
        "en_priority": variant["priority_en"],
        "vi_actions": [
            f"- {item['request_vi'].capitalize()}",
            f"- {item['secondary_vi'].capitalize()}",
        ],
        "en_actions": [
            f"- {item['request_en'].capitalize()}",
            f"- {item['secondary_en'].capitalize()}",
        ],
        "vi_deadlines": variant["deadline_vi"],
        "en_deadlines": variant["deadline_en"],
    }


def build_product_case(local_index: int) -> dict[str, object]:
    item = PRODUCT_ITEMS[local_index % len(PRODUCT_ITEMS)]
    variant = PRODUCT_VARIANTS[local_index // len(PRODUCT_ITEMS)]
    return {
        "vi_email": (
            f"Chủ đề: {item['subject_vi']}\n\n"
            f"Chào team sản phẩm,\n\n"
            f"{item['customer_vi'].capitalize()} vừa hỏi liệu bên mình có kế hoạch hỗ trợ "
            f"{item['feature_vi']} hay không. Chưa cần phản hồi gấp, nhưng nhờ team ghi nhận "
            f"lại để bổ sung vào {variant['review_vi']}. Nếu có thể, cập nhật trạng thái trước "
            f"{variant['deadline_vi']}.\n\n"
            "Cảm ơn."
        ),
        "en_email": (
            f"Subject: {item['subject_en']}\n\n"
            f"Hi product team,\n\n"
            f"{item['customer_en'].capitalize()} asked whether we plan to support "
            f"{item['feature_en']}. There is no urgent reply needed, but please log the request "
            f"so it can be included in {variant['review_en']}. If possible, share a status note "
            f"before {variant['deadline_en']}.\n\n"
            "Thanks."
        ),
        "vi_summary": (
            f"Team sản phẩm được nhờ ghi nhận đề xuất {item['feature_vi']} vào "
            f"{variant['review_vi']}."
        ),
        "en_summary": (
            f"The product team should log the {item['feature_en']} request for "
            f"{variant['review_en']}."
        ),
        "vi_priority": variant["priority_vi"],
        "en_priority": variant["priority_en"],
        "vi_actions": [
            f"- Ghi nhận đề xuất {item['feature_vi']} vào backlog",
            f"- Đưa mục này vào {variant['review_vi']}",
        ],
        "en_actions": [
            f"- Log the {item['feature_en']} request in the backlog",
            f"- Include it in {variant['review_en']}",
        ],
        "vi_deadlines": variant["deadline_vi"],
        "en_deadlines": variant["deadline_en"],
    }


def build_case_catalog() -> list[dict[str, object]]:
    builders = [
        build_internal_case,
        build_scheduling_case,
        build_support_case,
        build_billing_case,
        build_product_case,
    ]
    cases: list[dict[str, object]] = []
    cases_per_builder = MAX_CASE_COUNT // len(builders)

    for local_index in range(cases_per_builder):
        for builder in builders:
            cases.append(builder(local_index))

    return cases


def rows_from_case(case: dict[str, object]) -> list[dict[str, str]]:
    vi_actions = list(case["vi_actions"])
    en_actions = list(case["en_actions"])

    vi_action_output = "\n".join([*vi_actions, f"- Hạn chót: {case['vi_deadlines']}"])
    en_action_output = "\n".join([*en_actions, f"- Deadlines: {case['en_deadlines']}"])

    return [
        {
            "instruction": VI_SUMMARY,
            "input": str(case["vi_email"]),
            "output": str(case["vi_summary"]),
        },
        {
            "instruction": EN_SUMMARY,
            "input": str(case["en_email"]),
            "output": str(case["en_summary"]),
        },
        {
            "instruction": VI_PRIORITY,
            "input": str(case["vi_email"]),
            "output": str(case["vi_priority"]),
        },
        {
            "instruction": EN_PRIORITY,
            "input": str(case["en_email"]),
            "output": str(case["en_priority"]),
        },
        {
            "instruction": VI_ACTION,
            "input": str(case["vi_email"]),
            "output": vi_action_output,
        },
        {
            "instruction": EN_ACTION,
            "input": str(case["en_email"]),
            "output": en_action_output,
        },
        {
            "instruction": VI_TRIAGE,
            "input": str(case["vi_email"]),
            "output": triage_output(
                str(case["vi_summary"]),
                str(case["vi_priority"]),
                vi_actions,
                str(case["vi_deadlines"]),
                vi=True,
            ),
        },
        {
            "instruction": EN_TRIAGE,
            "input": str(case["en_email"]),
            "output": triage_output(
                str(case["en_summary"]),
                str(case["en_priority"]),
                en_actions,
                str(case["en_deadlines"]),
                vi=False,
            ),
        },
    ]


def build_rows(total_rows: int = DEFAULT_TOTAL_ROWS) -> list[dict[str, str]]:
    if total_rows <= 0 or total_rows % ROWS_PER_CASE != 0:
        raise ValueError("total_rows must be a positive multiple of 8.")

    case_catalog = build_case_catalog()
    max_rows = len(case_catalog) * ROWS_PER_CASE
    if total_rows > max_rows:
        raise ValueError(f"total_rows cannot exceed {max_rows}.")

    selected_case_count = total_rows // ROWS_PER_CASE
    rows: list[dict[str, str]] = []
    for case in case_catalog[:selected_case_count]:
        rows.extend(rows_from_case(case))
    return rows


def main() -> None:
    args = parse_args()
    rows = build_rows(args.total_rows)
    write_jsonl(args.output_path, rows)
    print(f"Wrote {len(rows)} rows to {Path(args.output_path).expanduser().resolve()}")


if __name__ == "__main__":
    main()
