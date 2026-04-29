from __future__ import annotations

from scripts.compare_eval import collect_metrics, render_diff
from scripts.eval_quality import (
    ChatEvalCase,
    detect_language,
    load_chat_eval,
    render_markdown_summary,
    score_chat_output,
)


def test_chat_quality_eval_set_loads_expected_categories() -> None:
    cases = load_chat_eval("data/eval/chat_quality_gold.jsonl")

    assert len(cases) == 80
    assert {case.category for case in cases} == {
        "bilingual",
        "code",
        "context",
        "factual_en",
        "factual_vi",
        "refuse",
    }


def test_score_chat_output_uses_keywords_language_and_forbidden_terms() -> None:
    case = ChatEvalCase(
        prompt="LoRA là gì?",
        expected_keywords=["adapter", ["ít tham số", "parameter-efficient"]],
        must_not_contain=["huấn luyện lại toàn bộ"],
        language="vi",
        category="factual_vi",
        min_keyword_matches=2,
    )

    result = score_chat_output(
        case,
        "LoRA là một adapter giúp fine-tune model với ít tham số hơn.",
        index=1,
    )

    assert result.passed is True
    assert result.metrics["keyword_matches"] == 2
    assert result.metrics["detected_language"] == "vi"


def test_detect_language_handles_english_and_vietnamese() -> None:
    assert detect_language("Mình không chắc, cần kiểm tra thêm.") == "vi"
    assert detect_language("I am not sure and would need to check.") == "en"


def test_compare_eval_collects_and_renders_metric_deltas() -> None:
    base = {
        "metrics": {
            "chat": {"score": 0.5, "by_category": {"factual_vi": {"score": 0.4}}},
            "mail": {"exact_field_pass": {"score": 0.6}, "parse_success": {"score": 0.8}},
        }
    }
    new = {
        "metrics": {
            "chat": {"score": 0.7, "by_category": {"factual_vi": {"score": 0.5}}},
            "mail": {"exact_field_pass": {"score": 0.54}, "parse_success": {"score": 0.9}},
        }
    }

    rendered = render_diff(collect_metrics(base), collect_metrics(new), threshold=0.05)

    assert "chat.score" in rendered
    assert "+20.00%" in rendered
    assert "mail.exact_field_pass" in rendered
    assert "Regressions:" in rendered


def test_markdown_summary_includes_validated_case_counts_when_unscored() -> None:
    markdown = render_markdown_summary(
        {
            "eval_set": "both",
            "base_model": "base",
            "adapter_path": None,
            "generated_at": "now",
            "case_counts": {"chat": 80, "mail": 12, "chat_scored": 0, "mail_scored": 0},
            "metrics": {"chat": {"total": 0, "score": 0.0}},
        }
    )

    assert "Validated cases" in markdown
    assert "chat=80" in markdown
