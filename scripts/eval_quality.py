from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from src.email_triage import score_triage_output  # noqa: E402
from src.eval import parse_expected_triage  # noqa: E402
from src.utils import (  # noqa: E402
    DEFAULT_BASE_MODEL,
    DEFAULT_SYSTEM_PROMPT,
    generate_response,
    load_model_and_tokenizer,
    read_jsonl,
    should_default_to_4bit,
    str_to_bool,
)

DEFAULT_CHAT_EVAL_PATH = ROOT_DIR / "data" / "eval" / "chat_quality_gold.jsonl"
DEFAULT_MAIL_EVAL_PATH = ROOT_DIR / "data" / "eval" / "mail_triage_gold.jsonl"


@dataclass
class ChatEvalCase:
    prompt: str
    expected_keywords: list[str | list[str]]
    must_not_contain: list[str]
    language: str
    category: str
    min_keyword_matches: int
    max_chars: int = 1200


@dataclass
class CaseResult:
    id: int
    category: str
    language: str
    passed: bool
    output: str
    metrics: dict[str, Any]


VI_MARKERS = {
    "anh",
    "ban",
    "bạn",
    "cach",
    "cách",
    "cho",
    "duoc",
    "được",
    "giai",
    "giải",
    "hay",
    "khong",
    "không",
    "la",
    "là",
    "minh",
    "mình",
    "noi",
    "nói",
    "the",
    "thế",
    "toi",
    "tôi",
    "trong",
    "va",
    "và",
}
VI_DIACRITIC_RE = re.compile(r"[ăâđêôơưáàảãạấầẩẫậắằẳẵặéèẻẽẹếềểễệíìỉĩịóòỏõọốồổỗộớờởỡợúùủũụứừửữựýỳỷỹỵ]", re.I)


def normalize_text(value: str) -> str:
    return " ".join(value.casefold().split())


def detect_language(text: str) -> str:
    lowered = normalize_text(text)
    if VI_DIACRITIC_RE.search(text):
        return "vi"
    tokens = set(re.findall(r"[a-zA-Z]+", lowered))
    if len(tokens & VI_MARKERS) >= 2:
        return "vi"
    return "en"


def parse_chat_case(row: dict[str, Any], *, index: int, path: Path) -> ChatEvalCase:
    prompt = row.get("prompt")
    expected_keywords = row.get("expected_keywords")
    must_not_contain = row.get("must_not_contain", [])
    language = row.get("language")
    category = row.get("category")
    if not isinstance(prompt, str) or not prompt.strip():
        raise ValueError(f"Chat eval row {index} in {path} needs a non-empty prompt.")
    if not isinstance(expected_keywords, list) or not expected_keywords:
        raise ValueError(f"Chat eval row {index} in {path} needs expected_keywords.")
    for value in expected_keywords:
        if isinstance(value, str) and value.strip():
            continue
        if isinstance(value, list) and all(isinstance(item, str) and item.strip() for item in value):
            continue
        raise ValueError(f"Chat eval row {index} in {path} has invalid expected_keywords.")
    if not isinstance(must_not_contain, list) or not all(
        isinstance(item, str) for item in must_not_contain
    ):
        raise ValueError(f"Chat eval row {index} in {path} has invalid must_not_contain.")
    if language not in {"vi", "en"}:
        raise ValueError(f"Chat eval row {index} in {path} must use language vi|en.")
    if not isinstance(category, str) or not category.strip():
        raise ValueError(f"Chat eval row {index} in {path} needs a category.")
    min_keyword_matches = row.get("min_keyword_matches", len(expected_keywords))
    if not isinstance(min_keyword_matches, int) or min_keyword_matches < 1:
        raise ValueError(f"Chat eval row {index} in {path} has invalid min_keyword_matches.")
    max_chars = row.get("max_chars", 1200)
    if not isinstance(max_chars, int) or max_chars < 1:
        raise ValueError(f"Chat eval row {index} in {path} has invalid max_chars.")
    return ChatEvalCase(
        prompt=prompt.strip(),
        expected_keywords=expected_keywords,
        must_not_contain=[item for item in must_not_contain if item],
        language=language,
        category=category.strip(),
        min_keyword_matches=min(min_keyword_matches, len(expected_keywords)),
        max_chars=max_chars,
    )


def load_chat_eval(path: Path) -> list[ChatEvalCase]:
    return [parse_chat_case(row, index=index, path=path) for index, row in enumerate(read_jsonl(path), 1)]


def load_mail_eval(path: Path) -> list[dict[str, Any]]:
    rows = read_jsonl(path)
    cases: list[dict[str, Any]] = []
    for index, row in enumerate(rows, 1):
        instruction = row.get("instruction")
        input_text = row.get("input", "")
        if not isinstance(instruction, str) or not instruction.strip():
            raise ValueError(f"Mail eval row {index} in {path} needs instruction.")
        if not isinstance(input_text, str):
            raise ValueError(f"Mail eval row {index} in {path} has non-string input.")
        cases.append(
            {
                "instruction": instruction.strip(),
                "input": input_text,
                "expected": parse_expected_triage(row, index=index, path=path),
                "domain": row.get("domain") or "unknown",
                "language": row.get("language") or "en",
            }
        )
    return cases


def keyword_matches(output: str, expected_keywords: list[str | list[str]]) -> tuple[int, list[str]]:
    haystack = normalize_text(output)
    matched: list[str] = []
    for value in expected_keywords:
        if isinstance(value, str):
            if normalize_text(value) in haystack:
                matched.append(value)
            continue
        winner = next((item for item in value if normalize_text(item) in haystack), None)
        if winner is not None:
            matched.append(winner)
    return len(matched), matched


def score_chat_output(case: ChatEvalCase, output: str, *, index: int) -> CaseResult:
    keyword_count, matched = keyword_matches(output, case.expected_keywords)
    normalized_output = normalize_text(output)
    forbidden = [
        value for value in case.must_not_contain if normalize_text(value) in normalized_output
    ]
    language = detect_language(output)
    length_ok = 1 <= len(output.strip()) <= case.max_chars
    passed = (
        keyword_count >= case.min_keyword_matches
        and not forbidden
        and language == case.language
        and length_ok
    )
    return CaseResult(
        id=index,
        category=case.category,
        language=case.language,
        passed=passed,
        output=output,
        metrics={
            "keyword_matches": keyword_count,
            "min_keyword_matches": case.min_keyword_matches,
            "matched_keywords": matched,
            "forbidden_hits": forbidden,
            "detected_language": language,
            "length_chars": len(output),
            "length_ok": length_ok,
        },
    )


def summarize_case_results(results: list[CaseResult]) -> dict[str, Any]:
    total = len(results)
    passed = sum(1 for result in results if result.passed)
    by_category: dict[str, dict[str, int | float]] = {}
    for result in results:
        bucket = by_category.setdefault(result.category, {"total": 0, "passed": 0, "score": 0.0})
        bucket["total"] = int(bucket["total"]) + 1
        bucket["passed"] = int(bucket["passed"]) + int(result.passed)
    for bucket in by_category.values():
        bucket["score"] = round(int(bucket["passed"]) / max(int(bucket["total"]), 1), 4)
    return {
        "total": total,
        "passed": passed,
        "score": round(passed / max(total, 1), 4),
        "by_category": by_category,
    }


def summarize_mail_results(results: list[CaseResult]) -> dict[str, Any]:
    total = len(results)
    fields = ["parse_success", "summary_match", "priority_match", "action_items_match", "deadlines_match"]
    aggregate = {"total": total}
    for field in fields:
        count = sum(1 for result in results if result.metrics.get(field) is True)
        aggregate[field] = {"count": count, "score": round(count / max(total, 1), 4)}
    passed = sum(1 for result in results if result.passed)
    aggregate["exact_field_pass"] = {"count": passed, "score": round(passed / max(total, 1), 4)}
    return aggregate


def run_chat_eval(cases: list[ChatEvalCase], infer) -> list[CaseResult]:
    return [
        score_chat_output(case, infer(case.prompt, ""), index=index)
        for index, case in enumerate(cases, 1)
    ]


def run_mail_eval(cases: list[dict[str, Any]], infer) -> list[CaseResult]:
    results: list[CaseResult] = []
    for index, case in enumerate(cases, 1):
        output = infer(case["instruction"], case["input"])
        score = score_triage_output(expected=case["expected"], actual_text=output)
        metrics = {
            "parse_success": score.parse_success,
            "summary_match": score.summary_match,
            "priority_match": score.priority_match,
            "action_items_match": score.action_items_match,
            "deadlines_match": score.deadlines_match,
        }
        passed = all(metrics.values())
        results.append(
            CaseResult(
                id=index,
                category=str(case["domain"]),
                language=str(case["language"]),
                passed=passed,
                output=output,
                metrics=metrics,
            )
        )
    return results


def write_report(report: dict[str, Any], output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    markdown_path = output_path.with_suffix(".md")
    markdown_path.write_text(render_markdown_summary(report), encoding="utf-8")


def render_markdown_summary(report: dict[str, Any]) -> str:
    lines = [
        f"# Eval Report: {report['eval_set']}",
        "",
        f"- Base model: `{report['base_model']}`",
        f"- Adapter: `{report['adapter_path'] or 'none'}`",
        f"- Generated at: `{report['generated_at']}`",
    ]
    case_counts = report.get("case_counts", {})
    if isinstance(case_counts, dict):
        lines.append(
            "- Validated cases: "
            f"chat={case_counts.get('chat', 0)}, mail={case_counts.get('mail', 0)}, "
            f"chat_scored={case_counts.get('chat_scored', 0)}, "
            f"mail_scored={case_counts.get('mail_scored', 0)}"
        )
    lines.extend(["", "| Section | Total | Score |", "|---|---:|---:|"])
    if "chat" in report["metrics"]:
        chat = report["metrics"]["chat"]
        lines.append(f"| Chat | {chat['total']} | {chat['score']:.2%} |")
    if "mail" in report["metrics"]:
        mail = report["metrics"]["mail"]
        lines.append(
            f"| Mail exact-field pass | {mail['total']} | {mail['exact_field_pass']['score']:.2%} |"
        )
        for field in [
            "parse_success",
            "summary_match",
            "priority_match",
            "action_items_match",
            "deadlines_match",
        ]:
            metric = mail[field]
            lines.append(f"| Mail {field} | {mail['total']} | {metric['score']:.2%} |")
    lines.append("")
    return "\n".join(lines)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Evaluate chat and mail quality.")
    parser.add_argument("--adapter", "--adapter_path", dest="adapter_path", type=Path, default=None)
    parser.add_argument("--base", "--base_model", dest="base_model", default=DEFAULT_BASE_MODEL)
    parser.add_argument("--eval-set", choices=["chat", "mail", "both"], default="both")
    parser.add_argument("--chat-path", type=Path, default=DEFAULT_CHAT_EVAL_PATH)
    parser.add_argument("--mail-path", type=Path, default=DEFAULT_MAIL_EVAL_PATH)
    parser.add_argument("--output", type=Path, default=ROOT_DIR / "outputs" / "eval_report.json")
    parser.add_argument("--max-new-tokens", type=int, default=512)
    parser.add_argument("--temperature", type=float, default=0.2)
    parser.add_argument("--top-p", type=float, default=0.9)
    parser.add_argument("--load-in-4bit", type=str_to_bool, default=None)
    parser.add_argument("--no-adapter", action="store_true")
    parser.add_argument(
        "--no-inference",
        action="store_true",
        help="Validate eval files and emit an empty report without loading a model.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    chat_cases = load_chat_eval(args.chat_path) if args.eval_set in {"chat", "both"} else []
    mail_cases = load_mail_eval(args.mail_path) if args.eval_set in {"mail", "both"} else []

    chat_results: list[CaseResult] = []
    mail_results: list[CaseResult] = []

    if not args.no_inference:
        load_in_4bit = should_default_to_4bit() if args.load_in_4bit is None else args.load_in_4bit
        adapter_path = None if args.no_adapter else args.adapter_path
        if adapter_path is not None and not adapter_path.exists():
            raise FileNotFoundError(f"Adapter path not found: {adapter_path}")
        model, tokenizer = load_model_and_tokenizer(
            base_model=args.base_model,
            adapter_path=str(adapter_path) if adapter_path is not None else None,
            load_in_4bit=load_in_4bit,
        )

        def infer(instruction: str, input_text: str) -> str:
            return generate_response(
                model=model,
                tokenizer=tokenizer,
                instruction=instruction,
                input_text=input_text,
                system_prompt=DEFAULT_SYSTEM_PROMPT,
                max_new_tokens=args.max_new_tokens,
                temperature=args.temperature,
                top_p=args.top_p,
            )

        chat_results = run_chat_eval(chat_cases, infer) if chat_cases else []
        mail_results = run_mail_eval(mail_cases, infer) if mail_cases else []

    report: dict[str, Any] = {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "eval_set": args.eval_set,
        "base_model": args.base_model,
        "adapter_path": None if args.no_adapter or args.adapter_path is None else str(args.adapter_path),
        "case_counts": {
            "chat": len(chat_cases),
            "mail": len(mail_cases),
            "chat_scored": len(chat_results),
            "mail_scored": len(mail_results),
        },
        "metrics": {},
        "results": {},
    }
    if args.eval_set in {"chat", "both"}:
        report["metrics"]["chat"] = summarize_case_results(chat_results)
        report["results"]["chat"] = [asdict(result) for result in chat_results]
    if args.eval_set in {"mail", "both"}:
        report["metrics"]["mail"] = summarize_mail_results(mail_results)
        report["results"]["mail"] = [asdict(result) for result in mail_results]
    write_report(report, args.output)
    print(f"Wrote {args.output}")
    print(f"Wrote {args.output.with_suffix('.md')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
