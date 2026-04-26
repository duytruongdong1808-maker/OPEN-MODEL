from __future__ import annotations

from src.email_triage import (
    ParsedTriage,
    parse_action_extraction_output,
    parse_full_triage_output,
    score_triage_output,
)
from src.eval import load_eval_prompts


def test_parse_full_triage_output_handles_english_and_none_values() -> None:
    parsed = parse_full_triage_output(
        "Summary: Incident notes are available for reference.\n"
        "Priority: low\n"
        "Action items:\n"
        "- None\n"
        "Deadlines: None"
    )

    assert parsed.language == "en"
    assert parsed.priority == "low"
    assert parsed.action_items == ["None"]
    assert parsed.deadlines == ["None"]


def test_parse_full_triage_output_handles_vietnamese_labels() -> None:
    parsed = parse_full_triage_output(
        "Tóm tắt: Team vận hành cần cập nhật calendar và xác nhận phòng họp.\n"
        "Ưu tiên: medium\n"
        "Việc cần làm:\n"
        "- Cập nhật calendar\n"
        "- Xác nhận phòng họp trước 14h30\n"
        "Hạn chót: trước 14h30; 16h chiều nay"
    )

    assert parsed.language == "vi"
    assert parsed.priority == "medium"
    assert parsed.action_items == ["Cập nhật calendar", "Xác nhận phòng họp trước 14h30"]
    assert parsed.deadlines == ["trước 14h30", "16h chiều nay"]


def test_parse_action_extraction_output_requires_deadline_bullet() -> None:
    parsed = parse_action_extraction_output(
        "- Draft the response\n- Attach the workaround note\n- Deadlines: by 4 PM today"
    )

    assert parsed.action_items == ["Draft the response", "Attach the workaround note"]
    assert parsed.deadlines == ["by 4 PM today"]


def test_score_triage_output_matches_normalized_fields() -> None:
    expected = ParsedTriage(
        summary="Support needs to respond because the billing workspace outage is blocking two renewals.",
        priority="high",
        action_items=[
            "Confirm the incident owner within 15 minutes",
            "Send the next customer update by 10:30 AM",
        ],
        deadlines=["within 15 minutes", "by 10:30 AM"],
        language="en",
    )

    actual = (
        "Summary: Support needs to respond because the billing workspace outage is blocking two renewals.\n"
        "Priority: high\n"
        "Action items:\n"
        "- Confirm the incident owner within 15 minutes.\n"
        "- Send the next customer update by 10:30 AM\n"
        "Deadlines: within 15 minutes; by 10:30 AM"
    )

    score = score_triage_output(expected=expected, actual_text=actual)

    assert score.parse_success is True
    assert score.summary_match is True
    assert score.priority_match is True
    assert score.action_items_match is True
    assert score.deadlines_match is True


def test_score_triage_output_reports_parse_failure() -> None:
    expected = ParsedTriage(
        summary="Product should log the request.",
        priority="low",
        action_items=["Log the request"],
        deadlines=["None"],
        language="en",
    )

    score = score_triage_output(expected=expected, actual_text="This is not a triage block.")

    assert score.parse_success is False
    assert score.actual is None


def test_score_triage_output_handles_semantic_summary_and_deadline_normalization() -> None:
    expected = ParsedTriage(
        summary="Support needs to respond because the billing workspace outage is blocking two renewals.",
        priority="high",
        action_items=[
            "Confirm the incident owner within 15 minutes",
            "Send the next customer update by 10:30 AM",
            "Attach the manual renewal workaround if the fix is still pending",
        ],
        deadlines=["within 15 minutes", "by 10:30 AM"],
        language="en",
    )

    actual = (
        "Summary: Support needs to handle an incident because sales cannot access the billing workspace and two renewals are blocked.\n"
        "Priority: high\n"
        "Action items:\n"
        "- Confirm the incident owner within 15 minutes\n"
        "- Send the next customer update by 10:30 AM\n"
        "- Attach the manual renewal workaround if the fix is still pending\n"
        "Deadlines: 15 minutes; 10:30 AM"
    )

    score = score_triage_output(expected=expected, actual_text=actual)

    assert score.parse_success is True
    assert score.summary_match is True
    assert score.priority_match is True
    assert score.action_items_match is True
    assert score.deadlines_match is True


def test_score_triage_output_treats_action_deadline_as_deadline_field_not_action_mismatch() -> None:
    expected = ParsedTriage(
        summary="Team finance needs to send the renewal quote and answer the discount question before tomorrow morning.",
        priority="medium",
        action_items=[
            "Send the final renewal quote to GreenLeaf",
            "Answer the discount question from finance before 10 AM tomorrow",
        ],
        deadlines=["before 10 AM tomorrow"],
        language="en",
    )

    actual = (
        "Summary: Team finance needs to send the final renewal quote to GreenLeaf and answer the discount question from finance before tomorrow morning.\n"
        "Priority: medium\n"
        "Action items:\n"
        "- Send the final renewal quote to GreenLeaf\n"
        "- Answer the discount question from finance\n"
        "Deadlines: 10 AM tomorrow"
    )

    score = score_triage_output(expected=expected, actual_text=actual)

    assert score.parse_success is True
    assert score.summary_match is True
    assert score.priority_match is True
    assert score.action_items_match is True
    assert score.deadlines_match is True


def test_score_triage_output_keeps_vague_action_item_as_mismatch() -> None:
    expected = ParsedTriage(
        summary="Product should log the scheduled export request for the next roadmap review.",
        priority="low",
        action_items=["Log the scheduled report export request"],
        deadlines=["None"],
        language="en",
    )

    actual = (
        "Summary: Product should capture the feature request for scheduled report exports in the next week's roadmap.\n"
        "Priority: low\n"
        "Action items:\n"
        "- Log the request for next week's roadmap review\n"
        "Deadlines: None"
    )

    score = score_triage_output(expected=expected, actual_text=actual)

    assert score.parse_success is True
    assert score.summary_match is False
    assert score.priority_match is True
    assert score.action_items_match is False
    assert score.deadlines_match is True


def test_load_eval_prompts_parses_gold_eval_rows() -> None:
    prompts = load_eval_prompts("data/eval/mail_triage_gold.jsonl")

    assert prompts
    first = prompts[0]
    assert isinstance(first["expected"], ParsedTriage)
    assert first["domain"] == "support"
