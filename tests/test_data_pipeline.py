from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path

import pytest

from src import build_dataset as build_dataset_module
from src.build_dataset import build_dataset_rows
from src.email_triage import parse_action_extraction_output, parse_full_triage_output
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
from src.prepare_data import parse_args as parse_prepare_data_args
from src.generate_chat_seed import build_chat_seed_rows
from src.generate_mail_eval import build_mail_eval_rows
from src.generate_mail_triage_seed import (
    DEFAULT_TOTAL_ROWS,
    build_rows as build_mail_triage_seed_rows,
)
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
    assert (
        classify_task_type("Phân loại các mục thành hai nhóm.", "", "x") == TASK_TYPE_CLASSIFICATION
    )
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
    assert (
        classify_task_type("Classify the priority of this email as high, medium, or low.", "", "x")
        == TASK_TYPE_CLASSIFICATION
    )
    assert (
        classify_task_type(
            "Extract the action items and deadlines from this email.", "", "- Call the client"
        )
        == "list_extraction"
    )
    assert (
        classify_task_type(
            "Đọc email sau và trả về bản triage gồm Tóm tắt, Ưu tiên, Việc cần làm, Hạn chót.",
            "",
            "x",
        )
        == TASK_TYPE_GENERATION
    )


def test_curate_row_drops_missing_output() -> None:
    curated = curate_row(
        {"instruction": "Answer clearly.", "input": "", "output": ""}, source="test"
    )

    assert curated["action"] == "drop"
    assert "missing_output" in curated["flags"]


def test_curate_row_drops_unresolved_mojibake() -> None:
    curated = curate_row(
        {
            "instruction": "Answer clearly.",
            "input": "",
            "output": "This response contains Ã unresolved text.",
        },
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
                "Ưu tiên: high\n"
                "Việc cần làm:\n"
                "- Xác nhận trạng thái chuyển khoản\n"
                "- Phản hồi khách hàng trước 16h hôm nay\n"
                "Hạn chót: trước 16h hôm nay"
            ),
            "domain": "billing",
            "language": "vi",
        },
        source="seed_mail_triage_vi_en",
    )

    assert curated["action"] == "keep"
    assert curated["task_type"] == TASK_TYPE_GENERATION
    assert curated["language"] == "vi"
    assert curated["domain"] == "billing"


def test_build_dataset_parse_args_defaults_include_mail_seed_and_profile(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(sys, "argv", ["build_dataset.py"])

    args = build_dataset_module.parse_args()

    assert args.target_profile == "chat_balanced_with_mail"
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
                "instruction": f"triage en {index}",
                "input": "",
                "output": f"Summary: Billing follow-up {index}.\nPriority: high\nAction items:\n- Reply to the customer\nDeadlines: None",
                "task_type": TASK_TYPE_GENERATION,
                "language": "en",
                "quality_score": 95,
                "flags": [],
                "source": "seed_mail_triage_vi_en",
                "action": "keep",
                "domain": "support",
            }
        )
    for index in range(3):
        rows.append(
            {
                "instruction": f"triage vi {index}",
                "input": "",
                "output": f"Tóm tắt: Theo dõi vận hành {index}.\nƯu tiên: medium\nViệc cần làm:\n- Cập nhật tiến độ\nHạn chót: None",
                "task_type": TASK_TYPE_GENERATION,
                "language": "vi",
                "quality_score": 95,
                "flags": [],
                "source": "seed_mail_triage_vi_en",
                "action": "keep",
                "domain": "ops",
            }
        )
    for index in range(2):
        rows.append(
            {
                "instruction": f"triage other {index}",
                "input": "",
                "output": f"Summary: Product request {index}.\nPriority: low\nAction items:\n- Log the request\nDeadlines: None",
                "task_type": TASK_TYPE_GENERATION,
                "language": "en",
                "quality_score": 95,
                "flags": [],
                "source": "seed_mail_triage_vi_en",
                "action": "keep",
                "domain": "product",
            }
        )
    for index in range(2):
        rows.append(
            {
                "instruction": f"rewrite {index}",
                "input": "please rewrite this note",
                "output": "Please rewrite this note in a calmer tone.",
                "task_type": "rewrite",
                "language": "en",
                "quality_score": 90,
                "flags": [],
                "source": "seed",
                "action": "keep",
            }
        )

    built_once = build_dataset_rows(
        rows, target_profile="mail_triage_en_ops_support", total_rows=20, seed=11
    )
    built_twice = build_dataset_rows(
        rows, target_profile="mail_triage_en_ops_support", total_rows=20, seed=11
    )

    assert built_once == built_twice
    counts = Counter(row["sampling_bucket"] for row in built_once)
    assert counts["mail_en_ops_support"] == 10
    assert counts["mail_vi_ops_support"] == 4
    assert counts["mail_other"] == 2
    assert counts["general_concise"] == 2
    assert counts["mixed_utility"] == 2
    assert all(
        row["source"] == "seed_mail_triage_vi_en"
        for row in built_once
        if row["sampling_bucket"].startswith("mail_")
    )
    assert all(
        row["domain"] in {"ops", "support"}
        for row in built_once
        if row["sampling_bucket"] in {"mail_en_ops_support", "mail_vi_ops_support"}
    )


def test_generate_mail_triage_seed_rows_are_balanced_and_unique() -> None:
    rows = build_mail_triage_seed_rows(DEFAULT_TOTAL_ROWS)

    assert len(rows) == DEFAULT_TOTAL_ROWS
    assert (
        len({(row["instruction"], row["input"], row["output"]) for row in rows})
        == DEFAULT_TOTAL_ROWS
    )

    assert Counter(row["task_variant"] for row in rows) == {
        "summarize_email": 375,
        "classify_only": 375,
        "extract_actions_and_deadlines": 375,
        "extract_only": 375,
        "find_deadline": 375,
        "draft_reply": 375,
        "summarize_thread": 375,
        "full_triage": 375,
    }

    domain_counts = Counter(row["domain"] for row in rows)
    assert domain_counts["ops"] == 1240
    assert domain_counts["support"] == 960
    assert domain_counts["billing"] == 480
    assert domain_counts["product"] == 320
    assert Counter(row["language"] for row in rows) == {"en": 1920, "vi": 1080}
    assert not any("before None" in row["output"] or "they the" in row["output"] for row in rows)


def test_generate_chat_seed_expands_bilingual_coverage() -> None:
    rows = build_chat_seed_rows()

    assert len(rows) == 250
    assert Counter(row["category"] for row in rows) == {
        "smalltalk": 40,
        "factual_qa": 50,
        "code_math": 30,
        "summarize_rewrite": 30,
        "refusal": 30,
        "multi_turn": 30,
        "bilingual_switch": 20,
        "technical_explain": 20,
    }
    assert Counter(row["language"] for row in rows)["vi"] > Counter(row["language"] for row in rows)["en"]


def test_generate_mail_eval_extends_to_120_balanced_gold_rows() -> None:
    rows = build_mail_eval_rows(total_rows=120)

    assert len(rows) == 120
    assert Counter(row["domain"] for row in rows) == {
        "ops": 30,
        "sales": 30,
        "internal": 30,
        "admin": 30,
    }
    assert Counter(row["language"] for row in rows) == {"en": 60, "vi": 36, "mixed": 24}
    assert all("expected" in row and row["expected"]["priority"] in {"high", "medium", "low"} for row in rows)


def test_generated_mail_triage_seed_matches_committed_raw_file() -> None:
    assert read_jsonl(DEFAULT_RAW_MAIL_TRIAGE_SEED_PATH) == build_mail_triage_seed_rows(
        DEFAULT_TOTAL_ROWS
    )


def test_generated_mail_triage_seed_rows_parse_cleanly() -> None:
    rows = build_mail_triage_seed_rows(DEFAULT_TOTAL_ROWS)

    triage_rows = [
        row
        for row in rows
        if "triage block" in row["instruction"].lower()
        or "bản triage" in row["instruction"].lower()
    ]
    action_rows = [
        row
        for row in rows
        if "extract the action items and deadlines" in row["instruction"].lower()
        or "trích xuất việc cần làm và hạn chót" in row["instruction"].lower()
    ]

    for row in triage_rows[:20]:
        parsed = parse_full_triage_output(row["output"])
        assert parsed.priority in {"high", "medium", "low"}

    for row in action_rows[:20]:
        parsed = parse_action_extraction_output(row["output"])
        assert parsed.action_items


def test_generated_mail_triage_seed_keeps_launch_blocker_and_product_request_patterns() -> None:
    rows = build_mail_triage_seed_rows(DEFAULT_TOTAL_ROWS)
    outputs = [row["output"] for row in rows]
    inputs = [row["input"] for row in rows]

    assert any("Share any blocker in" in output and "before" in output for output in outputs)
    assert any("Log the scheduled report export request" in output for output in outputs)
    assert any(
        "launch sync" in input.lower() and "high" in output.lower()
        for input, output in zip(inputs, outputs)
    )


def test_committed_mail_triage_report_tracks_en_first_distribution() -> None:
    report = json.loads(
        Path("data/curated/mail_triage_vi_en_seed_report.json").read_text(encoding="utf-8")
    )

    assert report["action_counts"] == {"keep": 2695, "drop": 289, "review": 16}
    assert report["language_distribution"] == {"en": 1800, "vi": 895}
    assert report["domain_distribution"] == {
        "ops": 1123,
        "support": 824,
        "billing": 463,
        "product": 285,
    }


def test_committed_built_dataset_keeps_mail_focus_and_clean_phrasing() -> None:
    rows = read_jsonl("data/curated/chat_core_vi_en_train.jsonl")

    assert Counter(row["sampling_bucket"] for row in rows) == {
        "chat_vi_general": 993,
        "mail_en_all_domains": 828,
        "chat_en_general": 827,
        "mail_vi": 331,
        "mixed_utility": 331,
    }
    assert Counter(row["language"] for row in rows) == {"en": 1655, "vi": 1324, "mixed": 331}
    assert sum(1 for row in rows if row["source"] == "seed_mail_triage_vi_en") == 1159
    assert not any(
        pattern in row.get("input", "") or pattern in row.get("output", "")
        for row in rows
        for pattern in ("before None", "they the", "review task completed", "trước Không có")
    )


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


def test_prepare_data_accepts_val_split_and_val_ratio_aliases(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        sys,
        "argv",
        ["prepare_data.py", "--val_split", "0.2"],
    )
    args = parse_prepare_data_args()
    assert args.val_split == 0.2

    monkeypatch.setattr(
        sys,
        "argv",
        ["prepare_data.py", "--val_ratio", "0.3"],
    )
    args = parse_prepare_data_args()
    assert args.val_split == 0.3


def test_curate_row_keeps_mail_priority_with_language_override() -> None:
    curated = curate_row(
        {
            "instruction": "Cho biết mức ưu tiên của email này là high, medium, hay low.",
            "input": "Chủ đề: Sự cố dashboard\n\nChào team support,\n\nDashboard đang lỗi và buổi readout đang bị ảnh hưởng.",
            "output": "high",
            "domain": "support",
            "language": "vi",
        },
        source="seed_mail_triage_vi_en",
    )

    assert curated["action"] == "keep"
    assert curated["language"] == "vi"
    assert curated["domain"] == "support"


def test_curate_row_drops_malformed_mail_triage_block() -> None:
    curated = curate_row(
        {
            "instruction": "Read this email and return a triage block with Summary, Priority, Action items, and Deadlines.",
            "input": "Subject: Incident follow-up\n\nHi support,\n\nPlease reply to the customer by noon.",
            "output": "Summary only without the required sections.",
            "domain": "support",
            "language": "en",
        },
        source="seed_mail_triage_vi_en",
    )

    assert curated["action"] == "drop"
    assert "mail_malformed_triage_block" in curated["flags"]


def test_curate_row_reviews_deadlines_missing_from_email_input() -> None:
    curated = curate_row(
        {
            "instruction": "Extract the action items and deadlines from this email as a short bullet list.",
            "input": "Subject: Customer follow-up\n\nHi support,\n\nPlease draft the response and attach the workaround note.",
            "output": "- Draft the response\n- Attach the workaround note\n- Deadlines: by 4 PM today",
            "domain": "support",
            "language": "en",
        },
        source="seed_mail_triage_vi_en",
    )

    assert curated["action"] == "review"
    assert "mail_deadline_not_in_input" in curated["flags"]
