from __future__ import annotations

import json
from collections import Counter

from src.build_dataset import build_dataset_rows
from src.curate_data import (
    TASK_TYPE_CLASSIFICATION,
    TASK_TYPE_QA,
    TASK_TYPE_REWRITE,
    TASK_TYPE_SUMMARIZE,
    classify_task_type,
    curate_row,
    detect_language,
    normalize_text,
)
from src.utils import render_training_record


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

    built_once = build_dataset_rows(rows, total_rows=10, seed=7)
    built_twice = build_dataset_rows(rows, total_rows=10, seed=7)

    assert built_once == built_twice
    counts = Counter(row["sampling_bucket"] for row in built_once)
    assert counts["vi_core"] == 5
    assert counts["en_core"] == 3
    assert counts["mixed_utility"] == 2


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
