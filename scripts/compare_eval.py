from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


def load_report(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def metric_value(report: dict[str, Any], path: list[str]) -> float | None:
    value: Any = report.get("metrics", {})
    for key in path:
        if not isinstance(value, dict) or key not in value:
            return None
        value = value[key]
    if isinstance(value, int | float):
        return float(value)
    return None


def collect_metrics(report: dict[str, Any]) -> dict[str, float]:
    metrics: dict[str, float] = {}
    chat_score = metric_value(report, ["chat", "score"])
    if chat_score is not None:
        metrics["chat.score"] = chat_score
    chat_categories = report.get("metrics", {}).get("chat", {}).get("by_category", {})
    if isinstance(chat_categories, dict):
        for category, payload in chat_categories.items():
            if isinstance(payload, dict) and isinstance(payload.get("score"), int | float):
                metrics[f"chat.{category}"] = float(payload["score"])

    mail = report.get("metrics", {}).get("mail", {})
    if isinstance(mail, dict):
        exact = mail.get("exact_field_pass")
        if isinstance(exact, dict) and isinstance(exact.get("score"), int | float):
            metrics["mail.exact_field_pass"] = float(exact["score"])
        for field in [
            "parse_success",
            "summary_match",
            "priority_match",
            "action_items_match",
            "deadlines_match",
        ]:
            payload = mail.get(field)
            if isinstance(payload, dict) and isinstance(payload.get("score"), int | float):
                metrics[f"mail.{field}"] = float(payload["score"])
    return metrics


def render_diff(base: dict[str, float], new: dict[str, float], threshold: float) -> str:
    names = sorted(set(base) | set(new))
    lines = [
        "| Metric | Base | New | Delta |",
        "|---|---:|---:|---:|",
    ]
    regressions: list[str] = []
    improvements: list[str] = []
    for name in names:
        before = base.get(name)
        after = new.get(name)
        if before is None or after is None:
            continue
        delta = after - before
        lines.append(f"| {name} | {before:.2%} | {after:.2%} | {delta:+.2%} |")
        if delta <= -threshold:
            regressions.append(f"{name} {delta:+.2%}")
        elif delta >= threshold:
            improvements.append(f"{name} {delta:+.2%}")

    if improvements:
        lines.extend(["", "Improvements:", *[f"- {item}" for item in improvements]])
    if regressions:
        lines.extend(["", "Regressions:", *[f"- {item}" for item in regressions]])
    if not improvements and not regressions:
        lines.extend(["", f"No metric changed by at least {threshold:.0%}."])
    return "\n".join(lines)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Compare two eval_quality JSON reports.")
    parser.add_argument("base_report", type=Path)
    parser.add_argument("new_report", type=Path)
    parser.add_argument("--threshold", type=float, default=0.05)
    parser.add_argument("--output", type=Path, default=None)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    base_metrics = collect_metrics(load_report(args.base_report))
    new_metrics = collect_metrics(load_report(args.new_report))
    rendered = render_diff(base_metrics, new_metrics, args.threshold)
    if args.output is not None:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered + "\n", encoding="utf-8")
    print(rendered)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
