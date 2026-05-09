from __future__ import annotations

import json
import sys
from collections import Counter

import pytest

from src import build_dataset as build_dataset_module
from src.build_dataset import GMAIL_REAL_SOURCE, build_dataset_rows
from src.build_gmail_real_dataset import (
    VALID_CATEGORIES,
    build_eval_rows,
    build_train_rows,
)
from src.curate_data import (
    TASK_TYPE_CLASSIFICATION,
    TASK_TYPE_GENERATION,
    TASK_TYPE_QA,
    TASK_TYPE_REFUSAL,
    TASK_TYPE_REWRITE,
    TASK_TYPE_SUMMARIZE,
    classify_task_type,
    curate_row,
    detect_language,
    normalize_text,
)
from src.email_triage import parse_action_extraction_output, parse_full_triage_output
from src.generate_chat_seed import build_chat_seed_rows
from src.prepare_data import parse_args as parse_prepare_data_args
from src.utils import (
    DEFAULT_CURATED_GMAIL_REAL_PATH,
    read_jsonl,
    render_training_record,
    write_jsonl,
)


class FakeTokenizer:
    eos_token = "<eos>"

    @staticmethod
    def apply_chat_template(messages, tokenize=False, add_generation_prompt=True):
        assert tokenize is False
        assert add_generation_prompt is True
        return json.dumps(messages, ensure_ascii=False)


def make_labeled_email(
    uid: str,
    *,
    category: str = "account/security",
    priority: str = "high",
    action_items: list[str] | None = None,
    deadlines: list[str] | None = None,
    language: str = "en",
) -> dict[str, object]:
    return {
        "uid": uid,
        "input": {
            "from": "security@example.com",
            "subject": "New login detected",
            "body_text": "A new login was detected. Review the activity by 09:00 today.",
            "date": "Sat, 09 May 2026 08:00:00 +0700",
        },
        "output": {
            "category": category,
            "priority": priority,
            "summary": "The message alerts the user about a new account login.",
            "action_items": action_items if action_items is not None else ["Review account activity"],
            "deadlines": deadlines if deadlines is not None else ["09:00 today"],
            "language": language,
        },
    }


def test_normalize_text_fixes_common_mojibake_and_whitespace() -> None:
    assert normalize_text("Helloâ€™s\r\n\r\n  world  ") == "Hello's\n\nworld"


def test_classify_task_type_handles_core_chat_variants() -> None:
    assert classify_task_type("Rewrite this note to sound more professional.", "", "x") == TASK_TYPE_REWRITE
    assert classify_task_type("Summarize the note in one sentence.", "", "x") == TASK_TYPE_SUMMARIZE
    assert classify_task_type("Classify these items into two groups.", "", "x") == TASK_TYPE_CLASSIFICATION
    assert classify_task_type("Answer briefly and clearly.", "What is LoRA?", "x") == TASK_TYPE_QA


def test_classify_task_type_handles_refusal_prompts() -> None:
    assert (
        classify_task_type("Refuse the unsafe request and offer a safe alternative.", "", "x")
        == TASK_TYPE_REFUSAL
    )


def test_detect_language_distinguishes_vi_en_and_mixed() -> None:
    assert detect_language("xin giup minh tra loi ngan gon") == "vi"
    assert detect_language("Rewrite this email to sound more professional.") == "en"
    assert detect_language("Please reply in English, xin cam on.") == "mixed"


def test_classify_task_type_handles_email_triage_variants() -> None:
    assert classify_task_type("Summarize this email in one sentence.", "", "x") == TASK_TYPE_SUMMARIZE
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
            "Read this email and return a triage block with Summary, Priority, Action items, and Deadlines.",
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
            "output": "This response contains Ãƒ unresolved text.",
        },
        source="test",
    )

    assert curated["action"] == "drop"
    assert "unresolved_mojibake" in curated["flags"]


def test_curate_row_keeps_clean_chat_style_example() -> None:
    curated = curate_row(
        {
            "instruction": "Rewrite this note to sound more professional.",
            "input": "send me the file before 5",
            "output": "Could you please send me the file before 5 PM?",
        },
        source="seed",
    )

    assert curated["action"] == "keep"
    assert curated["task_type"] == TASK_TYPE_REWRITE
    assert curated["language"] == "en"
    assert curated["quality_score"] >= 75


def test_build_gmail_real_train_rows_create_five_tasks_per_email_and_parse_cleanly() -> None:
    rows = build_train_rows(
        [
            make_labeled_email("gmail-1"),
            make_labeled_email(
                "gmail-2",
                category="newsletter",
                priority="low",
                action_items=[],
                deadlines=[],
                language="vi+en",
            ),
        ]
    )

    assert len(rows) == 10
    assert {row["source"] for row in rows} == {GMAIL_REAL_SOURCE}
    assert {row["uid"] for row in rows} == {"gmail-1", "gmail-2"}
    assert Counter(row["task_variant"] for row in rows) == {
        "real_full_triage": 2,
        "real_summary": 2,
        "real_priority": 2,
        "real_actions_deadlines": 2,
        "real_category": 2,
    }

    full_triage_rows = [row for row in rows if row["task_variant"] == "real_full_triage"]
    for row in full_triage_rows:
        parsed = parse_full_triage_output(row["output"])
        assert parsed.priority in {"high", "medium", "low"}

    action_rows = [row for row in rows if row["task_variant"] == "real_actions_deadlines"]
    for row in action_rows:
        parsed = parse_action_extraction_output(row["output"])
        assert parsed.action_items
        assert parsed.deadlines

    category_rows = [row for row in rows if row["task_variant"] == "real_category"]
    assert all(row["output"] in VALID_CATEGORIES for row in category_rows)
    assert any(row["language"] == "mixed" for row in rows)


def test_build_gmail_real_eval_rows_keep_uid_schema_and_none_defaults() -> None:
    eval_rows = build_eval_rows(
        [
            make_labeled_email(
                "gmail-empty",
                category="other",
                priority="low",
                action_items=[],
                deadlines=[],
                language="vi",
            )
        ]
    )

    assert len(eval_rows) == 1
    row = eval_rows[0]
    assert row["uid"] == "gmail-empty"
    assert row["source"] == GMAIL_REAL_SOURCE
    assert row["domain"] == "other"
    assert row["expected"]["action_items"] == ["None"]
    assert row["expected"]["deadlines"] == ["None"]


def test_build_gmail_real_dataset_script_writes_expected_counts(tmp_path) -> None:
    input_path = tmp_path / "emails_labeled.jsonl"
    output_path = tmp_path / "gmail_real_labeled_curated.jsonl"
    eval_path = tmp_path / "gmail_real_gold.jsonl"
    write_jsonl(input_path, [make_labeled_email("gmail-1"), make_labeled_email("gmail-2")])

    from src import build_gmail_real_dataset as module

    monkeypatch_argv = [
        "build_gmail_real_dataset.py",
        "--input_path",
        str(input_path),
        "--output_path",
        str(output_path),
        "--eval_output_path",
        str(eval_path),
    ]
    original_argv = sys.argv
    try:
        sys.argv = monkeypatch_argv
        assert module.main() == 0
    finally:
        sys.argv = original_argv

    assert len(read_jsonl(output_path)) == 10
    assert len(read_jsonl(eval_path)) == 2


def test_build_dataset_parse_args_defaults_include_gmail_real_source_and_profile(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(sys, "argv", ["build_dataset.py"])

    args = build_dataset_module.parse_args()

    assert args.target_profile == "gmail_real_v1"
    assert DEFAULT_CURATED_GMAIL_REAL_PATH in args.inputs


def test_build_dataset_rows_balances_profile_and_is_deterministic() -> None:
    rows = []
    for index in range(5):
        rows.append(
            {
                "instruction": f"vi {index}",
                "input": "",
                "output": f"Cau tra loi tieng Viet so {index}.",
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
                "output": f"I can help, cam on ban {index}.",
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


def test_build_dataset_rows_balances_gmail_real_profile() -> None:
    rows = []
    for index in range(5):
        rows.append(
            {
                "instruction": f"gmail {index}",
                "input": f"Subject: Login {index}",
                "output": "Summary: Login alert.\nPriority: high\nAction items:\n- Review login\nDeadlines: None",
                "task_type": TASK_TYPE_GENERATION,
                "language": "en",
                "quality_score": 100,
                "flags": [],
                "source": GMAIL_REAL_SOURCE,
                "action": "keep",
                "task_variant": "real_full_triage",
            }
        )
    for index, category in enumerate(["bilingual_switch", "refusal", "code_math"]):
        rows.append(
            {
                "instruction": f"chat {category}",
                "input": "",
                "output": f"Useful general answer {index}.",
                "task_type": TASK_TYPE_QA if category != "refusal" else TASK_TYPE_REFUSAL,
                "language": "en",
                "quality_score": 90,
                "flags": [],
                "source": "seed",
                "action": "keep",
                "category": category,
            }
        )

    built = build_dataset_rows(rows, target_profile="gmail_real_v1", total_rows=20, seed=11)

    counts = Counter(row["sampling_bucket"] for row in built)
    assert counts["gmail_real"] == 17
    assert counts["general_safety"] == 3
    assert all(
        row["source"] == GMAIL_REAL_SOURCE
        for row in built
        if row["sampling_bucket"] == "gmail_real"
    )
    assert all(
        row["source"] != GMAIL_REAL_SOURCE
        for row in built
        if row["sampling_bucket"] == "general_safety"
    )


def test_generate_chat_seed_expands_bilingual_coverage() -> None:
    rows = build_chat_seed_rows()

    assert len(rows) == 410
    assert Counter(row["category"] for row in rows) == {
        "smalltalk": 40,
        "factual_qa": 94,
        "code_math": 46,
        "summarize_rewrite": 30,
        "refusal": 80,
        "multi_turn": 30,
        "bilingual_switch": 70,
        "technical_explain": 20,
    }
    assert (
        Counter(row["language"] for row in rows)["vi"]
        > Counter(row["language"] for row in rows)["en"]
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


def test_curate_row_drops_malformed_mail_triage_block() -> None:
    curated = curate_row(
        {
            "instruction": "Read this email and return a triage block with Summary, Priority, Action items, and Deadlines.",
            "input": "Subject: Incident follow-up\n\nPlease reply to the customer by noon.",
            "output": "Summary only without the required sections.",
            "language": "en",
        },
        source=GMAIL_REAL_SOURCE,
    )

    assert curated["action"] == "drop"
    assert "mail_malformed_triage_block" in curated["flags"]


def test_curate_row_reviews_deadlines_missing_from_email_input() -> None:
    curated = curate_row(
        {
            "instruction": "Extract the action items and deadlines from this email as a short bullet list.",
            "input": "Subject: Customer follow-up\n\nPlease draft the response and attach the note.",
            "output": "- Draft the response\n- Attach the note\n- Deadlines: by 4 PM today",
            "language": "en",
        },
        source=GMAIL_REAL_SOURCE,
    )

    assert curated["action"] == "review"
    assert "mail_deadline_not_in_input" in curated["flags"]
