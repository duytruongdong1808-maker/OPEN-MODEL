from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from scripts.eval_quality import (  # noqa: E402
    DEFAULT_CHAT_EVAL_PATH,
    DEFAULT_MAIL_EVAL_PATH,
    load_chat_eval,
)
from src.email_triage import ParsedTriage, parse_full_triage_output  # noqa: E402
from src.eval import parse_expected_triage  # noqa: E402
from src.utils import read_jsonl  # noqa: E402

MAIL_FIELDS = ("summary_match", "action_items_match", "deadlines_match", "priority_match")
BLOCKER_RE = re.compile(r"\b(blocker|blockers|slip|slips|delay|delays)\b", re.I)
CONTENT_RE = re.compile(r"[A-Za-zÀ-ỹ0-9]+")
GENERIC_SUMMARY_TOKENS = {
    "a",
    "an",
    "and",
    "for",
    "needs",
    "should",
    "the",
    "to",
    "urgent",
    "update",
}


def normalize(value: str) -> str:
    return " ".join(value.casefold().split())


def has_real_items(values: list[str]) -> bool:
    return normalize("; ".join(values)) != "none"


def parse_actual(output: str) -> ParsedTriage | None:
    try:
        return parse_full_triage_output(output)
    except ValueError:
        return None


def load_mail_gold(path: Path) -> list[dict[str, Any]]:
    rows = read_jsonl(path)
    loaded: list[dict[str, Any]] = []
    for index, row in enumerate(rows, 1):
        loaded.append(
            {
                "instruction": row.get("instruction", ""),
                "input": row.get("input", ""),
                "domain": row.get("domain", "unknown"),
                "language": row.get("language", "en"),
                "expected": parse_expected_triage(row, index=index, path=path),
            }
        )
    return loaded


def expected_anchor_tokens(expected: ParsedTriage, domain: str) -> set[str]:
    tokens = {
        token.casefold()
        for token in CONTENT_RE.findall(expected.summary)
        if len(token) >= 4 and token.casefold() not in GENERIC_SUMMARY_TOKENS
    }
    if domain and domain != "unknown":
        tokens.add(domain.casefold())
    return tokens


def summary_missing_anchor(
    actual: ParsedTriage | None, expected: ParsedTriage, domain: str
) -> bool:
    if actual is None:
        return True
    expected_tokens = expected_anchor_tokens(expected, domain)
    if not expected_tokens:
        return False
    actual_tokens = {token.casefold() for token in CONTENT_RE.findall(actual.summary)}
    return not bool(expected_tokens & actual_tokens)


def format_expected(expected: ParsedTriage) -> str:
    actions = "; ".join(expected.action_items)
    deadlines = "; ".join(expected.deadlines)
    return (
        f"Summary={expected.summary} | Priority={expected.priority} | "
        f"Actions={actions} | Deadlines={deadlines}"
    )


def format_actual(actual: ParsedTriage | None, raw_output: str) -> str:
    if actual is None:
        return raw_output.strip().replace("\n", " / ")
    actions = "; ".join(actual.action_items)
    deadlines = "; ".join(actual.deadlines)
    return (
        f"Summary={actual.summary} | Priority={actual.priority} | "
        f"Actions={actions} | Deadlines={deadlines}"
    )


def analyze_mail(report: dict[str, Any], mail_gold: list[dict[str, Any]]) -> list[str]:
    results = report.get("results", {}).get("mail", [])
    counters: Counter[str] = Counter()
    failures_by_field: dict[
        str, list[tuple[dict[str, Any], dict[str, Any], ParsedTriage | None]]
    ] = {field: [] for field in MAIL_FIELDS}

    for result in results:
        index = int(result["id"]) - 1
        gold = mail_gold[index]
        expected: ParsedTriage = gold["expected"]
        actual = parse_actual(str(result.get("output", "")))
        metrics = result.get("metrics", {})

        for field in MAIL_FIELDS:
            if metrics.get(field) is not True:
                failures_by_field[field].append((result, gold, actual))

        if actual is not None:
            if not has_real_items(actual.deadlines) and has_real_items(expected.deadlines):
                counters["actual_deadlines_none_expected_has_deadline"] += 1
            if not has_real_items(actual.action_items) and has_real_items(expected.action_items):
                counters["actual_action_none_expected_has_action"] += 1
            actual_has_blocker = any(BLOCKER_RE.search(item) for item in actual.action_items)
            expected_has_blocker = any(BLOCKER_RE.search(item) for item in expected.action_items)
            if actual_has_blocker and not expected_has_blocker:
                counters["actual_added_blocker_action"] += 1
            if expected_has_blocker and not actual_has_blocker:
                counters["actual_missing_blocker_action"] += 1
        if summary_missing_anchor(actual, expected, str(gold.get("domain", "unknown"))):
            counters["summary_missing_customer_domain_or_entity"] += 1

    lines = ["## Mail Failures", ""]
    lines.extend(["### Pattern Counts", ""])
    if counters:
        for name, count in counters.most_common():
            lines.append(f"- {name}: {count}")
    else:
        lines.append("- No mail failure patterns counted.")

    for field, failures in failures_by_field.items():
        lines.extend(["", f"### {field}", "", f"- Failed cases: {len(failures)}", ""])
        for result, gold, actual in failures[:10]:
            expected: ParsedTriage = gold["expected"]
            lines.append(f"#### Case {result['id']} ({gold.get('domain')}, {gold.get('language')})")
            lines.append(f"- Expected: {format_expected(expected)}")
            lines.append(f"- Actual: {format_actual(actual, str(result.get('output', '')))}")
            lines.append(f"- Input: {str(gold.get('input', '')).replace(chr(10), ' ')[:500]}")
            lines.append("")
    return lines


def analyze_chat(report: dict[str, Any], chat_path: Path) -> list[str]:
    cases = load_chat_eval(chat_path)
    results = report.get("results", {}).get("chat", [])
    grouped: dict[str, list[tuple[dict[str, Any], Any]]] = defaultdict(list)
    counters: Counter[str] = Counter()

    for result in results:
        case = cases[int(result["id"]) - 1]
        if result.get("passed") is True:
            continue
        grouped[result.get("category", "unknown")].append((result, case))
        metrics = result.get("metrics", {})
        keyword_ok = (
            int(metrics.get("keyword_matches", 0))
            >= int(metrics.get("min_keyword_matches", case.min_keyword_matches))
            or metrics.get("semantic_pass") is True
        )
        forbidden = bool(metrics.get("forbidden_hits"))
        language_ok = bool(
            metrics.get("language_ok", metrics.get("detected_language") == case.language)
        )
        length_ok = bool(metrics.get("length_ok", True))

        if not language_ok:
            counters["wrong_language"] += 1
        if not keyword_ok and not forbidden and language_ok and length_ok:
            counters["missing_keyword_only"] += 1
        if forbidden:
            counters["forbidden_hit"] += 1
        if case.category == "code" and not language_ok:
            counters["likely_correct_but_metric_failed"] += 1
        elif not keyword_ok and not forbidden and language_ok and length_ok:
            missing = case.min_keyword_matches - int(metrics.get("keyword_matches", 0))
            if missing <= 1:
                counters["likely_correct_but_metric_failed"] += 1
        if case.category.startswith("factual") and (forbidden or not keyword_ok):
            counters["likely_factual_wrong"] += 1

    lines = ["## Chat Failures", "", "### Pattern Counts", ""]
    if counters:
        for name, count in counters.most_common():
            lines.append(f"- {name}: {count}")
    else:
        lines.append("- No chat failures counted.")

    for category in sorted(grouped):
        failures = grouped[category]
        lines.extend(["", f"### {category}", "", f"- Failed cases: {len(failures)}", ""])
        for result, case in failures[:10]:
            metrics = result.get("metrics", {})
            lines.append(f"#### Case {result['id']} ({case.language})")
            lines.append(f"- Prompt: {case.prompt}")
            lines.append(f"- Expected keywords: {case.expected_keywords}")
            lines.append(
                "- Metrics: "
                f"keywords={metrics.get('keyword_matches')}/{metrics.get('min_keyword_matches')}, "
                f"semantic={metrics.get('semantic_pass')}, "
                f"language={metrics.get('detected_language')}, "
                f"forbidden={metrics.get('forbidden_hits')}"
            )
            lines.append(f"- Output: {str(result.get('output', '')).replace(chr(10), ' ')[:700]}")
            lines.append("")
    return lines


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Analyze eval failures against gold sets.")
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--chat-path", type=Path, default=DEFAULT_CHAT_EVAL_PATH)
    parser.add_argument("--mail-path", type=Path, default=DEFAULT_MAIL_EVAL_PATH)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    report = json.loads(args.report.read_text(encoding="utf-8"))
    mail_gold = load_mail_gold(args.mail_path)
    lines = [
        f"# Eval Failure Analysis: {args.report}",
        "",
        f"- Eval set: `{report.get('eval_set')}`",
        f"- Adapter: `{report.get('adapter_path')}`",
        "",
    ]
    if report.get("results", {}).get("mail") is not None:
        lines.extend(analyze_mail(report, mail_gold))
        lines.append("")
    if report.get("results", {}).get("chat") is not None:
        lines.extend(analyze_chat(report, args.chat_path))
        lines.append("")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text("\n".join(lines), encoding="utf-8")
    print(f"Wrote {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
