from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Iterable, Sequence

CANONICAL_PRIORITIES = ("high", "medium", "low")
MAIL_DOMAINS = ("ops", "support", "billing", "product", "sales", "internal", "admin")
BAD_MAIL_OUTPUT_PATTERNS = (
    "before none",
    "trước không có",
    "they the",
    "review task completed",
    "summary: none",
    "tóm tắt: none",
)
SUMMARY_LABELS = {"en": "Summary", "vi": "Tóm tắt"}
PRIORITY_LABELS = {"en": "Priority", "vi": "Ưu tiên"}
ACTION_LABELS = {"en": "Action items", "vi": "Việc cần làm"}
DEADLINE_LABELS = {"en": "Deadlines", "vi": "Hạn chót"}
NONE_VALUES = {"none", "không có"}
PRIORITY_ALIASES = {
    "high": "high",
    "medium": "medium",
    "low": "low",
    "cao": "high",
    "trung bình": "medium",
    "trung binh": "medium",
    "thấp": "low",
    "thap": "low",
}
SUMMARY_GENERIC_PATTERNS = (
    "this email is about",
    "email này nói về",
    "the message asks for help",
    "email này cần xử lý",
)
CONTENT_WORDS = re.compile(r"[A-Za-zÀ-ỹ0-9]+")


@dataclass(frozen=True)
class ParsedTriage:
    summary: str
    priority: str
    action_items: list[str]
    deadlines: list[str]
    language: str


@dataclass(frozen=True)
class TriageScore:
    parse_success: bool
    summary_match: bool
    priority_match: bool
    action_items_match: bool
    deadlines_match: bool
    actual: ParsedTriage | None


def normalize_space(text: str) -> str:
    return re.sub(r"\s+", " ", text.strip())


def canonical_priority(value: str) -> str | None:
    normalized = normalize_space(value).lower()
    return PRIORITY_ALIASES.get(normalized)


def is_none_value(value: str) -> bool:
    return normalize_space(value).lower() in NONE_VALUES


def dedupe_preserve_order(values: Iterable[str]) -> list[str]:
    deduped: list[str] = []
    seen: set[str] = set()
    for value in values:
        normalized = normalize_space(value)
        if not normalized:
            continue
        key = normalized.casefold()
        if key in seen:
            continue
        seen.add(key)
        deduped.append(normalized)
    return deduped


def sanitize_action_items(action_items: Sequence[str]) -> list[str]:
    normalized = dedupe_preserve_order(action_items)
    if not normalized:
        return ["None"]
    if len(normalized) == 1 and is_none_value(normalized[0]):
        return ["None"]
    return normalized[:4]


def sanitize_deadlines(deadlines: Sequence[str]) -> list[str]:
    normalized = dedupe_preserve_order(deadlines)
    if not normalized:
        return ["None"]
    if len(normalized) == 1 and is_none_value(normalized[0]):
        return ["None"]
    return normalized


def format_deadlines(deadlines: Sequence[str]) -> str:
    sanitized = sanitize_deadlines(deadlines)
    if sanitized == ["None"]:
        return "None"
    return "; ".join(sanitized)


def format_action_extraction(
    action_items: Sequence[str],
    deadlines: Sequence[str],
    *,
    language: str,
) -> str:
    sanitized_actions = sanitize_action_items(action_items)
    deadline_label = DEADLINE_LABELS[language]
    lines = [f"- {item}" for item in sanitized_actions]
    lines.append(f"- {deadline_label}: {format_deadlines(deadlines)}")
    return "\n".join(lines)


def format_full_triage(
    summary: str,
    priority: str,
    action_items: Sequence[str],
    deadlines: Sequence[str],
    *,
    language: str,
) -> str:
    resolved_priority = canonical_priority(priority)
    if resolved_priority is None:
        raise ValueError(f"Unsupported priority: {priority}")

    sanitized_summary = normalize_space(summary)
    sanitized_actions = sanitize_action_items(action_items)
    deadline_value = format_deadlines(deadlines)
    return (
        f"{SUMMARY_LABELS[language]}: {sanitized_summary}\n"
        f"{PRIORITY_LABELS[language]}: {resolved_priority}\n"
        f"{ACTION_LABELS[language]}:\n"
        f"{chr(10).join(f'- {item}' for item in sanitized_actions)}\n"
        f"{DEADLINE_LABELS[language]}: {deadline_value}"
    )


def _parse_deadline_value(value: str) -> list[str]:
    normalized = normalize_space(value)
    if is_none_value(normalized):
        return ["None"]
    parts = [normalize_space(part) for part in normalized.split(";")]
    cleaned = [part for part in parts if part]
    return sanitize_deadlines(cleaned)


def _extract_label_value(line: str, allowed_labels: dict[str, str]) -> tuple[str, str] | None:
    for language, label in allowed_labels.items():
        prefix = f"{label}:"
        if line.startswith(prefix):
            return language, line[len(prefix) :].strip()
    return None


def parse_action_extraction_output(text: str) -> ParsedTriage:
    lines = [
        line.strip()
        for line in text.replace("\r\n", "\n").replace("\r", "\n").strip().split("\n")
        if line.strip()
    ]
    if len(lines) < 2:
        raise ValueError("Action extraction output must contain action items and a deadlines line.")

    deadline_language: str | None = None
    deadline_value: str | None = None
    action_items: list[str] = []
    for line in lines:
        if not line.startswith("- "):
            raise ValueError("Action extraction lines must start with '- '.")
        bullet_value = line[2:].strip()
        deadline_match = _extract_label_value(bullet_value, DEADLINE_LABELS)
        if deadline_match is not None:
            deadline_language, deadline_value = deadline_match
            continue
        action_items.append(bullet_value)

    if deadline_language is None or deadline_value is None:
        raise ValueError("Action extraction output is missing the deadlines bullet.")

    if not action_items:
        raise ValueError("Action extraction output must contain at least one action bullet.")

    return ParsedTriage(
        summary="",
        priority="",
        action_items=sanitize_action_items(action_items),
        deadlines=_parse_deadline_value(deadline_value),
        language=deadline_language,
    )


def parse_full_triage_output(text: str) -> ParsedTriage:
    lines = [
        line.rstrip()
        for line in text.replace("\r\n", "\n").replace("\r", "\n").strip().split("\n")
        if line.strip()
    ]
    if len(lines) < 4:
        raise ValueError("Full triage output must contain four sections.")

    summary_match = _extract_label_value(lines[0], SUMMARY_LABELS)
    priority_match = _extract_label_value(lines[1], PRIORITY_LABELS)
    action_match = _extract_label_value(lines[2], ACTION_LABELS)
    deadline_match = _extract_label_value(lines[-1], DEADLINE_LABELS)

    if (
        summary_match is None
        or priority_match is None
        or action_match is None
        or deadline_match is None
    ):
        raise ValueError("Full triage output is missing one or more required labels.")

    language = summary_match[0]
    if len({language, priority_match[0], action_match[0], deadline_match[0]}) != 1:
        raise ValueError("Full triage output must use a single label language.")

    summary = normalize_space(summary_match[1])
    if not summary:
        raise ValueError("Summary cannot be empty.")

    priority = canonical_priority(priority_match[1])
    if priority is None:
        raise ValueError("Priority must be one of high, medium, or low.")

    if action_match[1]:
        raise ValueError("Action items header cannot contain inline content.")

    action_lines = [line.strip() for line in lines[3:-1]]
    if not action_lines:
        raise ValueError("Action items section cannot be empty.")
    if any(not line.startswith("- ") for line in action_lines):
        raise ValueError("Action item lines must start with '- '.")

    action_items = sanitize_action_items([line[2:].strip() for line in action_lines])
    deadlines = _parse_deadline_value(deadline_match[1])
    return ParsedTriage(
        summary=summary,
        priority=priority,
        action_items=action_items,
        deadlines=deadlines,
        language=language,
    )


def contains_bad_mail_pattern(*parts: str) -> bool:
    haystack = " ".join(normalize_space(part).lower() for part in parts if part)
    return any(pattern in haystack for pattern in BAD_MAIL_OUTPUT_PATTERNS)


def count_summary_sentences(summary: str) -> int:
    fragments = [fragment for fragment in re.split(r"[.!?]+", summary.strip()) if fragment.strip()]
    return len(fragments) or 1


def normalize_text_match(value: str) -> str:
    normalized = normalize_space(value).lower()
    normalized = re.sub(r"[“”\"'`]", "", normalized)
    normalized = re.sub(r"[,:;.!?]+$", "", normalized)
    return normalized


DEADLINE_PREFIXES = (
    "by ",
    "within ",
    "before ",
    "until ",
    "trong vong ",
    "truoc ",
    "trước ",
)
ACTION_DEADLINE_MARKERS = (
    " by ",
    " within ",
    " before ",
    " until ",
    " trong vong ",
    " trong vòng ",
    " truoc ",
    " trước ",
)
TOKEN_REPLACEMENTS = {
    "customer-ready": "customer ready",
    "follow-up": "follow up",
    "root-cause": "root cause",
}
TOKEN_LEMMAS = {
    "answered": "answer",
    "answers": "answer",
    "attached": "attach",
    "attaches": "attach",
    "blocked": "block",
    "blocking": "block",
    "confirmed": "confirm",
    "confirms": "confirm",
    "customers": "customer",
    "delays": "delay",
    "exports": "export",
    "finished": "finish",
    "handled": "handle",
    "handles": "handle",
    "kept": "keep",
    "keeps": "keep",
    "metrics": "metric",
    "moved": "move",
    "moves": "move",
    "notes": "note",
    "renewals": "renewal",
    "replied": "reply",
    "replies": "reply",
    "required": "require",
    "requires": "require",
    "resent": "resend",
    "resends": "resend",
    "responded": "respond",
    "responds": "respond",
    "reviewed": "review",
    "reviews": "review",
    "scheduled": "schedule",
    "sheets": "sheet",
    "updated": "update",
    "updates": "update",
    "verified": "verify",
    "verifies": "verify",
    "workarounds": "workaround",
}
STOPWORDS = {
    "a",
    "an",
    "and",
    "are",
    "at",
    "after",
    "because",
    "can",
    "cho",
    "cua",
    "của",
    "da",
    "do",
    "for",
    "from",
    "has",
    "have",
    "is",
    "its",
    "need",
    "needs",
    "next",
    "ngay",
    "of",
    "on",
    "please",
    "should",
    "still",
    "team",
    "that",
    "the",
    "their",
    "this",
    "to",
    "va",
    "và",
    "while",
    "with",
}


def _strip_deadline_prefix(value: str) -> str:
    normalized = normalize_text_match(value)
    for prefix in DEADLINE_PREFIXES:
        if normalized.startswith(prefix):
            return normalize_space(normalized[len(prefix) :])
    return normalized


def _strip_action_deadline_phrase(value: str) -> str:
    normalized = normalize_space(value)
    lowered = f" {normalized.casefold()} "
    split_index: int | None = None
    for marker in ACTION_DEADLINE_MARKERS:
        found = lowered.find(marker)
        if found == -1:
            continue
        candidate_index = max(found - 1, 0)
        if split_index is None or candidate_index < split_index:
            split_index = candidate_index
    if split_index is None:
        return normalized
    return normalize_space(normalized[:split_index])


def _semantic_tokens(value: str, *, strip_action_deadline: bool = False) -> list[str]:
    normalized = normalize_space(value).casefold()
    if strip_action_deadline:
        normalized = _strip_action_deadline_phrase(normalized)
    for source, target in TOKEN_REPLACEMENTS.items():
        normalized = normalized.replace(source, target)

    tokens: list[str] = []
    for token in CONTENT_WORDS.findall(normalized):
        canonical = TOKEN_LEMMAS.get(token.casefold(), token.casefold())
        if canonical in STOPWORDS:
            continue
        tokens.append(canonical)
    return tokens


def _semantic_similarity(
    actual: str, expected: str, *, strip_action_deadline: bool = False
) -> float:
    actual_tokens = set(_semantic_tokens(actual, strip_action_deadline=strip_action_deadline))
    expected_tokens = set(_semantic_tokens(expected, strip_action_deadline=strip_action_deadline))
    if not actual_tokens and not expected_tokens:
        return 1.0
    if not actual_tokens or not expected_tokens:
        return 0.0
    overlap = len(actual_tokens & expected_tokens)
    precision = overlap / len(actual_tokens)
    recall = overlap / len(expected_tokens)
    if precision + recall == 0:
        return 0.0
    return 2 * precision * recall / (precision + recall)


def _summary_match(actual: str, expected: str) -> bool:
    if normalize_text_match(actual) == normalize_text_match(expected):
        return True
    return _semantic_similarity(actual, expected) >= 0.6


def _normalize_action_match(value: str) -> str:
    normalized = normalize_text_match(_strip_action_deadline_phrase(value))
    return re.sub(r"\s+", " ", normalized)


def _action_match(actual: str, expected: str) -> bool:
    if _normalize_action_match(actual) == _normalize_action_match(expected):
        return True
    return _semantic_similarity(actual, expected, strip_action_deadline=True) >= 0.7


def _list_match(actual_values: Sequence[str], expected_values: Sequence[str], *, matcher) -> bool:
    if len(actual_values) != len(expected_values):
        return False
    remaining = list(expected_values)
    for actual in actual_values:
        matched_index: int | None = None
        for index, expected in enumerate(remaining):
            if matcher(actual, expected):
                matched_index = index
                break
        if matched_index is None:
            return False
        remaining.pop(matched_index)
    return not remaining


def normalize_list_match(values: Sequence[str]) -> list[str]:
    return [normalize_text_match(value) for value in values]


def score_triage_output(
    *,
    expected: ParsedTriage,
    actual_text: str,
) -> TriageScore:
    try:
        actual = parse_full_triage_output(actual_text)
    except ValueError:
        return TriageScore(
            parse_success=False,
            summary_match=False,
            priority_match=False,
            action_items_match=False,
            deadlines_match=False,
            actual=None,
        )

    return TriageScore(
        parse_success=True,
        summary_match=_summary_match(actual.summary, expected.summary),
        priority_match=actual.priority == expected.priority,
        action_items_match=_list_match(
            actual.action_items, expected.action_items, matcher=_action_match
        ),
        deadlines_match=sorted(_strip_deadline_prefix(value) for value in actual.deadlines)
        == sorted(_strip_deadline_prefix(value) for value in expected.deadlines),
        actual=actual,
    )


def output_tokens_supported_by_input(output_parts: Sequence[str], input_text: str) -> bool:
    input_tokens = {token.lower() for token in CONTENT_WORDS.findall(input_text)}
    if not input_tokens:
        return True

    for part in output_parts:
        candidate_tokens = [
            token.lower() for token in CONTENT_WORDS.findall(part) if len(token) > 2
        ]
        if not candidate_tokens:
            continue
        if any(token in input_tokens for token in candidate_tokens):
            continue
        return False
    return True


def validate_parsed_triage(
    parsed: ParsedTriage, *, input_text: str = ""
) -> tuple[list[str], list[str]]:
    review_flags: list[str] = []
    drop_flags: list[str] = []

    if count_summary_sentences(parsed.summary) != 1:
        review_flags.append("mail_summary_not_single_sentence")

    if normalize_text_match(parsed.summary) in SUMMARY_GENERIC_PATTERNS:
        review_flags.append("mail_summary_too_generic")

    if contains_bad_mail_pattern(
        parsed.summary,
        " ".join(parsed.action_items),
        " ".join(parsed.deadlines),
    ):
        drop_flags.append("mail_placeholder_leakage")

    if len(parsed.action_items) > 4:
        drop_flags.append("mail_too_many_action_items")

    normalized_actions = normalize_list_match(parsed.action_items)
    if len(set(normalized_actions)) != len(normalized_actions):
        drop_flags.append("mail_duplicate_action_items")

    normalized_deadlines = normalize_list_match(parsed.deadlines)
    if len(set(normalized_deadlines)) != len(normalized_deadlines):
        drop_flags.append("mail_duplicate_deadlines")

    if parsed.action_items == ["None"] and parsed.deadlines != ["None"]:
        drop_flags.append("mail_none_action_with_deadline")

    if (
        input_text
        and parsed.deadlines != ["None"]
        and not output_tokens_supported_by_input(parsed.deadlines, input_text)
    ):
        review_flags.append("mail_deadline_not_in_input")

    if (
        input_text
        and parsed.action_items != ["None"]
        and not output_tokens_supported_by_input(parsed.action_items, input_text)
    ):
        review_flags.append("mail_action_not_in_input")

    return review_flags, drop_flags
