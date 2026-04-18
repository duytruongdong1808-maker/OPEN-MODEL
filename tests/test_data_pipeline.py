from __future__ import annotations

import json
import sys
from collections import Counter

import pytest

from src import build_dataset as build_dataset_module
from src.build_dataset import build_dataset_rows
from src.curate_data import (
    TASK_TYPE_CLASSIFICATION,
    TASK_TYPE_GENERATION,
    TASK_TYPE_QA,
    TASK_TYPE_REWRITE,
    TASK_TYPE_SUMMARIZE,
    classify_task_type,
    curate_row,
    detect_language,
    normalize_text,
)
from src.generate_mail_triage_seed import DEFAULT_TOTAL_ROWS, build_rows as build_mail_triage_seed_rows
from src.utils import (
    DEFAULT_CURATED_MAIL_TRIAGE_SEED_PATH,
    DEFAULT_RAW_MAIL_TRIAGE_SEED_PATH,
    read_jsonl,
    render_training_record,
)


class FakeTokenizer:
    eos_token = "<eos>"

    @staticmethod
    def apply_chat_template(messages, tokenize=False, add_generation_prompt=True):
        assert tokenize is False
        assert add_generation_prompt is True
        return json.dumps(messages, ensure_ascii=False)


def test_normalize_text_fixes_common_mojibake_and_whitespace() -> None:
    assert normalize_text("Helloâ€™s\r\n\r\n  world  ") == "Hello's\n\nworld"


def test_classify_task_type_handles_core_chat_variants() -> None:
    assert classify_task_type("Viết lại tin nhắn cho lịch sự hơn.", "", "x") == TASK_TYPE_REWRITE
    assert classify_task_type("Summarize the note in one sentence.", "", "x") == TASK_TYPE_SUMMARIZE
    assert classify_task_type("Phân loại các mục thành hai nhóm.", "", "x") == TASK_TYPE_CLASSIFICATION
    assert classify_task_type("Trả lời ngắn gọn và rõ ràng.", "LoRA là gì?", "x") == TASK_TYPE_QA


def test_detect_language_distinguishes_vi_en_and_mixed() -> None:
    assert detect_language("Viết lại email này cho lịch sự hơn.") == "vi"
    assert detect_language("Rewrite this email to sound more professional.") == "en"
    assert detect_language("Please reply in English, cảm ơn bạn.") == "mixed"


def test_detect_language_handles_email_triage_prompts() -> None:
    assert detect_language("Tóm tắt email này và cho biết mức ưu tiên.") == "vi"
    assert detect_language("Triage this email and extract action items.") == "en"


def test_classify_task_type_handles_email_triage_variants() -> None:
    assert classify_task_type("Tóm tắt email sau trong một câu.", "", "x") == TASK_TYPE_SUMMARIZE
    assert classify_task_type("Classify the priority of this email as high, medium, or low.", "", "x") == TASK_TYPE_CLASSIFICATION
    assert classify_task_type("Extract the action items and deadlines from this email.", "", "- Call the client") == "list_extraction"
    assert (
        classify_task_type(
            "Đọc email sau và trả về bản triage gồm Tóm tắt, Ưu tiên, Việc cần làm, Hạn chót.",
            "",
            "x",
        )
        == TASK_TYPE_GENERATION
    )


def test_curate_row_drops_missing_output() -> None:
    curated = curate_row({"instruction": "Answer clearly.", "input": "", "output": ""}, source="test")

    assert curated["action"] == "drop"
    assert "missing_output" in curated["flags"]


def test_curate_row_drops_unresolved_mojibake() -> None:
    curated = curate_row(
        {"instruction": "Answer clearly.", "input": "", "output": "This response contains Ã unresolved text."},
        source="test",
    )

    assert curated["action"] == "drop"
    assert "unresolved_mojibake" in curated["flags"]


def test_curate_row_keeps_clean_chat_style_example() -> None:
    curated = curate_row(
        {
            "instruction": "Viết lại tin nhắn cho lịch sự hơn.",
            "input": "gửi mình file trước 5 giờ nhé",
            "output": "Chào bạn, bạn có thể gửi mình file trước 5 giờ chiều được không?",
        },
        source="seed",
    )

    assert curated["action"] == "keep"
    assert curated["task_type"] == TASK_TYPE_REWRITE
    assert curated["language"] == "vi"
    assert curated["quality_score"] >= 75


def test_curate_row_keeps_combined_email_triage_as_generation() -> None:
    curated = curate_row(
        {
            "instruction": "Đọc email sau và trả về bản triage gồm Tóm tắt, Ưu tiên, Việc cần làm, Hạn chót.",
            "input": (
                "Chủ đề: Hóa đơn tháng 4\n\n"
                "Chào bạn,\n\n"
                "Bên mình chưa nhận được xác nhận chuyển khoản cho hóa đơn đến hạn ngày mai. "
                "Nếu có thể, vui lòng phản hồi trước 16h hôm nay để tránh gián đoạn dịch vụ.\n\n"
                "Cảm ơn."
            ),
            "output": (
                "Tóm tắt: Khách hàng nhắc về hóa đơn đến hạn ngày mai và cần xác nhận thanh toán sớm.\n"
                "Ưu tiên: cao\n"
                "Việc cần làm:\n"
                "- Xác nhận trạng thái chuyển khoản\n"
                "- Phản hồi khách hàng trước 16h hôm nay\n"
                "Hạn chót: trước 16h hôm nay"
            ),
        },
        source="seed_mail_triage_vi_en",
    )

    assert curated["action"] == "keep"
    assert curated["task_type"] == TASK_TYPE_GENERATION


def test_build_dataset_parse_args_defaults_include_mail_seed_and_profile(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sys, "argv", ["build_dataset.py"])

    args = build_dataset_module.parse_args()

    assert args.target_profile == "chat_core_vi_en_mail"
    assert DEFAULT_CURATED_MAIL_TRIAGE_SEED_PATH in args.inputs


def test_build_dataset_rows_balances_profile_and_is_deterministic() -> None:
    rows = []
    for index in range(5):
        rows.append(
            {
                "instruction": f"vi {index}",
                "input": "",
                "output": f"Trả lời tiếng Việt số {index}.",
                "task_type": TASK_TYPE_QA,
                "language": "vi",
                "quality_score": 90,
                "flags": [],
                "source": "seed",
                "action": "keep",
            }
        )
    for index in range(3):
        rows.append(
            {
                "instruction": f"en {index}",
                "input": "",
                "output": f"English answer number {index}.",
                "task_type": TASK_TYPE_QA,
                "language": "en",
                "quality_score": 90,
                "flags": [],
                "source": "seed",
                "action": "keep",
            }
        )
    for index in range(2):
        rows.append(
            {
                "instruction": f"mixed {index}",
                "input": "",
                "output": f"I can help, cảm ơn bạn {index}.",
                "task_type": TASK_TYPE_SUMMARIZE,
                "language": "mixed",
                "quality_score": 90,
                "flags": [],
                "source": "seed",
                "action": "keep",
            }
        )

    built_once = build_dataset_rows(rows, target_profile="chat_core_vi_en", total_rows=10, seed=7)
    built_twice = build_dataset_rows(rows, target_profile="chat_core_vi_en", total_rows=10, seed=7)

    assert built_once == built_twice
    counts = Counter(row["sampling_bucket"] for row in built_once)
    assert counts["vi_core"] == 5
    assert counts["en_core"] == 3
    assert counts["mixed_utility"] == 2


def test_build_dataset_rows_balances_mail_profile_and_email_bucket() -> None:
    rows = []
    for index in range(7):
        rows.append(
            {
                "instruction": f"vi {index}",
                "input": "",
                "output": f"Trả lời tiếng Việt số {index}.",
                "task_type": TASK_TYPE_QA,
                "language": "vi",
                "quality_score": 90,
                "flags": [],
                "source": "seed",
                "action": "keep",
            }
        )
    for index in range(4):
        rows.append(
            {
                "instruction": f"en {index}",
                "input": "",
                "output": f"English answer number {index}.",
                "task_type": TASK_TYPE_QA,
                "language": "en",
                "quality_score": 90,
                "flags": [],
                "source": "seed",
                "action": "keep",
            }
        )
    for index in range(3):
        rows.append(
            {
                "instruction": f"mixed {index}",
                "input": "",
                "output": f"I can help, cảm ơn bạn {index}.",
                "task_type": TASK_TYPE_SUMMARIZE,
                "language": "mixed",
                "quality_score": 90,
                "flags": [],
                "source": "seed",
                "action": "keep",
            }
        )
    for index in range(6):
        rows.append(
            {
                "instruction": f"triage {index}",
                "input": "",
                "output": f"Summary: Billing follow-up {index}.\nPriority: high\nAction items:\n- Reply\nDeadlines: None",
                "task_type": TASK_TYPE_GENERATION,
                "language": "en",
                "quality_score": 95,
                "flags": [],
                "source": "seed_mail_triage_vi_en",
                "action": "keep",
            }
        )

    built_once = build_dataset_rows(rows, target_profile="chat_core_vi_en_mail", total_rows=20, seed=11)
    built_twice = build_dataset_rows(rows, target_profile="chat_core_vi_en_mail", total_rows=20, seed=11)

    assert built_once == built_twice
    counts = Counter(row["sampling_bucket"] for row in built_once)
    assert counts["vi_core"] == 7
    assert counts["en_core"] == 4
    assert counts["mixed_utility"] == 3
    assert counts["email_triage"] == 6
    assert all(row["source"] == "seed_mail_triage_vi_en" for row in built_once if row["sampling_bucket"] == "email_triage")


def test_generate_mail_triage_seed_rows_are_balanced_and_unique() -> None:
    rows = build_mail_triage_seed_rows(DEFAULT_TOTAL_ROWS)

    assert len(rows) == DEFAULT_TOTAL_ROWS
    assert len({(row["instruction"], row["input"], row["output"]) for row in rows}) == DEFAULT_TOTAL_ROWS

    instruction_counts = Counter(row["instruction"] for row in rows)
    assert instruction_counts["Tóm tắt email sau trong một câu ngắn."] == 125
    assert instruction_counts["Summarize this email in one short sentence."] == 125
    assert instruction_counts["Cho biết mức ưu tiên của email này: cao, trung bình, hay thấp."] == 125
    assert instruction_counts["Classify the priority of this email as high, medium, or low."] == 125
    assert instruction_counts["Trích xuất việc cần làm và hạn chót từ email sau dưới dạng danh sách gạch đầu dòng ngắn."] == 125
    assert instruction_counts["Extract the action items and deadlines from this email as a short bullet list."] == 125
    assert instruction_counts["Đọc email sau và trả về bản triage gồm Tóm tắt, Ưu tiên, Việc cần làm, Hạn chót."] == 125
    assert instruction_counts["Read this email and return a triage block with Summary, Priority, Action items, and Deadlines."] == 125


def test_generated_mail_triage_seed_matches_committed_raw_file() -> None:
    assert read_jsonl(DEFAULT_RAW_MAIL_TRIAGE_SEED_PATH) == build_mail_triage_seed_rows(DEFAULT_TOTAL_ROWS)


def test_render_training_record_accepts_curated_metadata_fields() -> None:
    rendered = render_training_record(
        FakeTokenizer(),
        {
            "instruction": "Summarize briefly.",
            "input": "Open-source models give teams more control over deployment and cost.",
            "output": "Open-source models help teams keep more control over deployment and cost.",
            "task_type": TASK_TYPE_SUMMARIZE,
            "language": "en",
            "quality_score": 90,
            "flags": [],
            "source": "seed",
            "action": "keep",
        },
        system_prompt="You are concise.",
    )

    assert rendered["completion"].endswith("<eos>")
    assert "prompt" in rendered
