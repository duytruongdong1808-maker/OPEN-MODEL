from __future__ import annotations

import argparse
import json
import re
from collections import Counter
from pathlib import Path
from typing import Any

try:
    from langdetect import LangDetectException, detect_langs
except ImportError:  # pragma: no cover - optional dev dependency
    LangDetectException = Exception
    detect_langs = None

try:
    from .email_triage import (
        MAIL_DOMAINS,
        ParsedTriage,
        canonical_priority,
        contains_bad_mail_pattern,
        count_summary_sentences,
        output_tokens_supported_by_input,
        parse_action_extraction_output,
        parse_full_triage_output,
        validate_parsed_triage,
    )
    from .utils import (
        DEFAULT_CURATION_REPORT_PATH,
        DEFAULT_CURATED_REVIEW_PATH,
        DEFAULT_CURATED_TRAIN_PATH,
        DEFAULT_LOG_LEVEL,
        DEFAULT_RAW_TRAIN_PATH,
        LOG_LEVEL_NAMES,
        configure_logging,
        coerce_optional_text,
        coerce_required_text,
        ensure_parent_dir,
        get_logger,
        read_jsonl,
        write_jsonl,
    )
except ImportError:
    from email_triage import (
        MAIL_DOMAINS,
        ParsedTriage,
        canonical_priority,
        contains_bad_mail_pattern,
        count_summary_sentences,
        output_tokens_supported_by_input,
        parse_action_extraction_output,
        parse_full_triage_output,
        validate_parsed_triage,
    )
    from utils import (
        DEFAULT_CURATION_REPORT_PATH,
        DEFAULT_CURATED_REVIEW_PATH,
        DEFAULT_CURATED_TRAIN_PATH,
        DEFAULT_LOG_LEVEL,
        DEFAULT_RAW_TRAIN_PATH,
        LOG_LEVEL_NAMES,
        configure_logging,
        coerce_optional_text,
        coerce_required_text,
        ensure_parent_dir,
        get_logger,
        read_jsonl,
        write_jsonl,
    )


TASK_TYPE_QA = "qa"
TASK_TYPE_REWRITE = "rewrite"
TASK_TYPE_SUMMARIZE = "summarize"
TASK_TYPE_CLASSIFICATION = "classification"
TASK_TYPE_GENERATION = "generation"
TASK_TYPE_LIST_EXTRACTION = "list_extraction"
TASK_TYPE_OTHER = "other"
CORE_CHAT_TASK_TYPES = {
    TASK_TYPE_QA,
    TASK_TYPE_REWRITE,
    TASK_TYPE_SUMMARIZE,
    TASK_TYPE_CLASSIFICATION,
    TASK_TYPE_GENERATION,
    TASK_TYPE_LIST_EXTRACTION,
}
MIN_OUTPUT_CHARS = 10
MAX_OUTPUT_CHARS = 2000
NEAR_DUPLICATE_JACCARD_THRESHOLD = 0.90
MAX_TASK_TYPE_SHARE = 0.40
MOJIBAKE_MARKERS = ("â€™", "â€˜", "â€œ", "â€", "â€“", "â€”", "Â", "Ã", "Ù", "Ø", "Ë", "áº")
MOJIBAKE_REPLACEMENTS = {
    "â€™": "'",
    "â€˜": "'",
    "â€œ": '"',
    "â€": '"',
    "â€“": "-",
    "â€”": "-",
    "â€¦": "...",
    "Â ": " ",
    "Â": "",
    "Ã©": "é",
    "Ã¨": "è",
    "Ã¡": "á",
    "Ã¢": "â",
    "Ã£": "ã",
    "Ã¤": "ä",
    "Ãª": "ê",
    "Ãí": "í",
    "Ã³": "ó",
    "Ã´": "ô",
    "Ã¶": "ö",
    "Ãº": "ú",
    "Ã¼": "ü",
    "Ã±": "ñ",
    "Ã§": "ç",
    "MÃ¶mpelgard": "Mömpelgard",
    "FrÃ©dÃ©ric": "Frédéric",
    "MontbÃ©liard": "Montbéliard",
    "DÃ¢r": "Dâr",
    "HuracÃ¡n": "Huracán",
    "EspaÃ±a": "España",
    "Champs-Ã‰lysÃ©es": "Champs-Élysées",
    "pÃ¢tÃ©": "pâté",
    "cháº£ lá»¥a": "chả lụa",
    "xÃ­u máº¡i": "xíu mại",
}
VIETNAMESE_CHARACTERS = set("ăâđêôơưáàảãạấầẩẫậắằẳẵặéèẻẽẹếềểễệíìỉĩịóòỏõọốồổỗộớờởỡợúùủũụứừửữựýỳỷỹỵ")
VIETNAMESE_HINTS = {
    "xin",
    "chào",
    "giúp",
    "giải",
    "thích",
    "viết",
    "lịch",
    "sự",
    "tóm",
    "tắt",
    "ngắn",
    "gọn",
    "bạn",
    "mình",
    "không",
    "được",
    "danh",
    "sách",
    "trả",
    "lời",
}
ENGLISH_HINTS = {
    "the",
    "and",
    "please",
    "rewrite",
    "summarize",
    "answer",
    "list",
    "extract",
    "question",
    "professional",
    "friendly",
    "brief",
}
WEAK_OUTPUT_PATTERNS = (
    "there are many things",
    "we are always engaged one phone",
    "not good.",
    "fantastic movies",
)
QUESTION_WORDS = (
    "who",
    "what",
    "when",
    "where",
    "why",
    "how",
    "which",
    "is ",
    "are ",
    "can ",
    "do ",
    "does ",
)
EMAIL_TRIAGE_GENERATION_MARKERS = (
    "email triage",
    "triage this email",
    "triage the email",
    "triage this message",
    "triage the message",
    "return only these exact labels",
    "return only this exact schema",
    "exact triage block schema",
    "triage block schema",
    "trả về đúng schema",
    "trả về đúng các nhãn",
    "trả về triage email đúng schema",
    "read this email and return a triage block",
    "read the email and return a triage block",
    "đọc email sau và trả về bản triage",
    "đọc email sau và tạo bản triage",
    "đọc email sau và đưa ra bản triage",
    "triage email này",
)
EMAIL_SUMMARIZE_MARKERS = (
    "summarize this email",
    "summarize the email",
    "summarize the following email",
    "tóm tắt email",
    "tóm tắt nội dung email",
)
EMAIL_PRIORITY_MARKERS = (
    "priority of this email",
    "priority of the email",
    "classify the priority",
    "needs a reply",
    "reply required",
    "mức ưu tiên",
    "độ ưu tiên",
    "cần phản hồi",
)
EMAIL_ACTION_MARKERS = (
    "action items",
    "action item",
    "deadlines",
    "deadline",
    "next steps",
    "việc cần làm",
    "hạn chót",
    "hạn cuối",
)
EMAIL_DEADLINE_ONLY_MARKERS = (
    "find only the deadlines",
    "only the deadlines",
    "chỉ tìm các hạn chót",
)


def get_language_override(row: dict[str, Any]) -> str | None:
    raw_language = row.get("language")
    if not isinstance(raw_language, str):
        return None
    normalized = raw_language.strip().lower()
    if normalized in {"vi", "en", "mixed", "unknown"}:
        return normalized
    return None


def get_domain_override(row: dict[str, Any]) -> str | None:
    raw_domain = row.get("domain")
    if not isinstance(raw_domain, str):
        return None
    normalized = raw_domain.strip().lower()
    if normalized in MAIL_DOMAINS:
        return normalized
    return None


def validate_mail_output(
    instruction: str,
    input_text: str,
    output: str,
) -> tuple[list[str], list[str]]:
    instruction_lower = instruction.lower()
    review_flags: list[str] = []
    drop_flags: list[str] = []

    if contains_bad_mail_pattern(output):
        drop_flags.append("mail_placeholder_leakage")
        return review_flags, drop_flags

    if any(keyword in instruction_lower for keyword in EMAIL_TRIAGE_GENERATION_MARKERS):
        try:
            parsed = parse_full_triage_output(output)
        except ValueError:
            drop_flags.append("mail_malformed_triage_block")
            return review_flags, drop_flags

        parsed_review_flags, parsed_drop_flags = validate_parsed_triage(
            parsed, input_text=input_text
        )
        review_flags.extend(parsed_review_flags)
        drop_flags.extend(parsed_drop_flags)
        return review_flags, drop_flags

    if any(keyword in instruction_lower for keyword in EMAIL_ACTION_MARKERS):
        try:
            parsed = parse_action_extraction_output(output)
        except ValueError:
            drop_flags.append("mail_malformed_action_output")
            return review_flags, drop_flags

        proxy_triage = ParsedTriage(
            summary="mail action validation",
            priority="medium",
            action_items=parsed.action_items,
            deadlines=parsed.deadlines,
            language=parsed.language,
        )
        parsed_review_flags, parsed_drop_flags = validate_parsed_triage(
            proxy_triage, input_text=input_text
        )
        review_flags.extend(
            flag for flag in parsed_review_flags if flag not in {"mail_summary_not_single_sentence"}
        )
        drop_flags.extend(parsed_drop_flags)
        return review_flags, drop_flags

    if any(keyword in instruction_lower for keyword in EMAIL_PRIORITY_MARKERS):
        if canonical_priority(output) is None:
            drop_flags.append("mail_invalid_priority")
        return review_flags, drop_flags

    if any(keyword in instruction_lower for keyword in EMAIL_SUMMARIZE_MARKERS):
        if "\n" in output:
            review_flags.append("mail_summary_multiline")
        if count_summary_sentences(output) != 1:
            review_flags.append("mail_summary_not_single_sentence")
        if not output_tokens_supported_by_input([output], input_text):
            review_flags.append("mail_summary_not_in_input")
        return review_flags, drop_flags

    return review_flags, drop_flags


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Curate raw instruction data into keep/review sets with quality metadata."
    )
    parser.add_argument(
        "--input_path",
        type=Path,
        default=DEFAULT_RAW_TRAIN_PATH,
        help="Path to the raw JSONL file to curate.",
    )
    parser.add_argument(
        "--output_path",
        type=Path,
        default=DEFAULT_CURATED_TRAIN_PATH,
        help="Path to write curated keep rows.",
    )
    parser.add_argument(
        "--review_path",
        type=Path,
        default=DEFAULT_CURATED_REVIEW_PATH,
        help="Path to write rows that need manual review.",
    )
    parser.add_argument(
        "--report_path",
        type=Path,
        default=DEFAULT_CURATION_REPORT_PATH,
        help="Path to write the curation report JSON.",
    )
    parser.add_argument(
        "--source",
        type=str,
        default=None,
        help="Optional source label recorded on curated rows. Defaults to the input file stem.",
    )
    parser.add_argument(
        "--log_level",
        type=str.upper,
        choices=LOG_LEVEL_NAMES,
        default=DEFAULT_LOG_LEVEL,
        help="Logging verbosity.",
    )
    return parser.parse_args()


def normalize_text(text: str) -> str:
    normalized = text.replace("\r\n", "\n").replace("\r", "\n")
    for source, replacement in MOJIBAKE_REPLACEMENTS.items():
        normalized = normalized.replace(source, replacement)
    normalized = re.sub(r"[ \t]+\n", "\n", normalized)
    normalized = re.sub(r"\n[ \t]+", "\n", normalized)
    normalized = re.sub(r"\n{3,}", "\n\n", normalized)
    normalized = re.sub(r"[ \t]{2,}", " ", normalized)
    return normalized.strip()


def contains_mojibake(text: str) -> bool:
    return any(marker in text for marker in MOJIBAKE_MARKERS)


def detect_language_with_langdetect(text: str) -> str | None:
    if detect_langs is None or len(text.split()) < 4:
        return None
    try:
        candidates = detect_langs(text[:2000])
    except LangDetectException:
        return None
    if not candidates:
        return None
    top = candidates[0]
    if top.prob < 0.75:
        return None
    if top.lang == "vi":
        return "vi"
    if top.lang == "en":
        return "en"
    return None


def detect_language(*parts: str) -> str:
    combined = " ".join(part for part in parts if part).strip().lower()
    if not combined:
        return "unknown"

    tokens = set(re.findall(r"[a-zA-ZÀ-ỹ]+", combined))
    has_vietnamese_chars = any(char in VIETNAMESE_CHARACTERS for char in combined)
    has_vi = has_vietnamese_chars or bool(tokens & VIETNAMESE_HINTS)
    has_en = bool(tokens & ENGLISH_HINTS) or bool(
        re.search(r"\b(the|and|please|answer|rewrite)\b", combined)
    )

    if has_vi and has_en:
        return "mixed"
    if has_vi:
        return "vi"
    if has_en:
        return "en"
    langdetect_guess = detect_language_with_langdetect(combined)
    if langdetect_guess is not None:
        return langdetect_guess
    if re.search(r"[A-Za-z]", combined):
        return "en"
    return "unknown"


def classify_task_type(instruction: str, input_text: str, output: str) -> str:
    instruction_lower = instruction.strip().lower()
    input_lower = input_text.strip().lower()
    output_lower = output.strip().lower()

    if any(
        keyword in instruction_lower
        for keyword in ("rewrite", "rephrase", "sound more professional", "viết lại")
    ):
        return TASK_TYPE_REWRITE
    if any(keyword in instruction_lower for keyword in EMAIL_TRIAGE_GENERATION_MARKERS):
        return TASK_TYPE_GENERATION
    if any(keyword in instruction_lower for keyword in EMAIL_SUMMARIZE_MARKERS):
        return TASK_TYPE_SUMMARIZE
    if any(keyword in instruction_lower for keyword in EMAIL_PRIORITY_MARKERS):
        return TASK_TYPE_CLASSIFICATION
    if any(keyword in instruction_lower for keyword in EMAIL_ACTION_MARKERS):
        return TASK_TYPE_LIST_EXTRACTION
    if any(
        keyword in instruction_lower
        for keyword in ("summarize", "summary", "tóm tắt", "briefly summarize")
    ):
        return TASK_TYPE_SUMMARIZE
    if any(
        keyword in instruction_lower
        for keyword in (
            "extract",
            "list down",
            "comma separated",
            "pipe symbol",
            "separate them",
            "danh sách",
        )
    ):
        return TASK_TYPE_LIST_EXTRACTION
    if any(
        keyword in instruction_lower
        for keyword in (
            "classify",
            "identify which",
            "which of the following",
            "divisible by",
            "either a",
        )
    ):
        return TASK_TYPE_CLASSIFICATION
    if any(keyword in instruction_lower for keyword in ("phân loại",)):
        return TASK_TYPE_CLASSIFICATION
    if any(
        keyword in instruction_lower
        for keyword in (
            "write",
            "draft",
            "compose",
            "haiku",
            "story",
            "email",
            "respond",
            "acknowledgement",
            "greet",
            "clarify",
            "hỏi lại",
            "từ chối",
            "chào",
            "giữ câu trả lời",
            "trung thực",
            "tạo một câu trả lời",
        )
    ):
        return TASK_TYPE_GENERATION
    if any(
        keyword in instruction_lower for keyword in ("trả lời", "answer", "giải thích", "explain")
    ):
        return TASK_TYPE_QA
    if (
        instruction_lower.endswith("?")
        or instruction_lower.startswith(QUESTION_WORDS)
        or "question" in instruction_lower
        or input_lower.endswith("?")
    ):
        return TASK_TYPE_QA
    if output_lower.startswith(("-", "*")) or re.match(r"^\d+\.", output_lower):
        return TASK_TYPE_LIST_EXTRACTION
    return TASK_TYPE_OTHER


def score_row_quality(
    instruction: str,
    input_text: str,
    output: str,
    task_type: str,
    unresolved_mojibake: bool,
) -> tuple[int, list[str], list[str]]:
    score = 100
    review_flags: list[str] = []
    drop_flags: list[str] = []

    output_word_count = len(output.split())
    output_length = len(output)
    input_length = len(input_text)
    bullet_count = len(re.findall(r"(^|\n)(-|\*|\d+\.)\s", output))

    if unresolved_mojibake:
        score -= 80
        drop_flags.append("unresolved_mojibake")

    if any(phrase in output.lower() for phrase in WEAK_OUTPUT_PATTERNS):
        score -= 50
        drop_flags.append("weak_output_phrase")

    if output_length < MIN_OUTPUT_CHARS and task_type != TASK_TYPE_CLASSIFICATION:
        score -= 50
        drop_flags.append("short_output")

    if output_length > MAX_OUTPUT_CHARS:
        score -= 60
        drop_flags.append("oversized_output")

    if (
        task_type in {TASK_TYPE_REWRITE, TASK_TYPE_SUMMARIZE, TASK_TYPE_GENERATION}
        and output_word_count < 5
    ):
        score -= 40
        drop_flags.append("underspecified_output")

    if task_type == TASK_TYPE_OTHER:
        score -= 20
        review_flags.append("task_other")

    if output_length > 900:
        score -= 35
        review_flags.append("very_long_output")
    elif output_length > 500:
        score -= 15
        review_flags.append("long_output")

    if input_length > 1500:
        score -= 10
        review_flags.append("long_input")

    if bullet_count >= 8:
        score -= 10
        review_flags.append("long_list_output")

    if task_type == TASK_TYPE_LIST_EXTRACTION and output_length > 350:
        score -= 15
        review_flags.append("list_format_drift")

    if task_type == TASK_TYPE_QA and input_length == 0 and output_length > 350:
        score -= 15
        review_flags.append("possible_factual_drift")

    if re.search(r"[?]{2,}|[!]{3,}", output):
        score -= 5
        review_flags.append("noisy_punctuation")

    if score < 0:
        score = 0
    return score, review_flags, drop_flags


def curate_row(row: dict[str, Any], source: str) -> dict[str, Any]:
    flags: list[str] = []
    domain_override = get_domain_override(row)
    language_override = get_language_override(row)

    try:
        instruction = coerce_required_text(row.get("instruction"), "instruction")
    except ValueError:
        curated_row = {
            "instruction": normalize_text(str(row.get("instruction", "") or "")),
            "input": normalize_text(str(row.get("input", "") or "")),
            "output": normalize_text(str(row.get("output", "") or "")),
            "task_type": TASK_TYPE_OTHER,
            "language": language_override or "unknown",
            "quality_score": 0,
            "flags": ["missing_instruction"],
            "source": source,
            "action": "drop",
        }
        if domain_override:
            curated_row["domain"] = domain_override
        return curated_row

    try:
        output = coerce_required_text(row.get("output"), "output")
    except ValueError:
        curated_row = {
            "instruction": normalize_text(instruction),
            "input": normalize_text(str(row.get("input", "") or "")),
            "output": normalize_text(str(row.get("output", "") or "")),
            "task_type": classify_task_type(instruction, "", ""),
            "language": language_override or detect_language(instruction),
            "quality_score": 0,
            "flags": ["missing_output"],
            "source": source,
            "action": "drop",
        }
        if domain_override:
            curated_row["domain"] = domain_override
        return curated_row

    input_text = coerce_optional_text(row.get("input", ""), "input")
    instruction = normalize_text(instruction)
    input_text = normalize_text(input_text)
    output = normalize_text(output)

    had_mojibake_before = any(
        contains_mojibake(str(row.get(field, "") or ""))
        for field in ("instruction", "input", "output")
    )
    unresolved_mojibake = any(contains_mojibake(text) for text in (instruction, input_text, output))
    if had_mojibake_before:
        flags.append("mojibake_normalized")
    if unresolved_mojibake:
        flags.append("mojibake_detected")

    task_type = classify_task_type(instruction, input_text, output)
    language = language_override or detect_language(instruction, input_text, output)
    detected_language = detect_language(instruction, input_text, output)
    quality_score, review_flags, drop_flags = score_row_quality(
        instruction=instruction,
        input_text=input_text,
        output=output,
        task_type=task_type,
        unresolved_mojibake=unresolved_mojibake,
    )
    if language_override in {"vi", "en"} and detected_language not in {
        language_override,
        "mixed",
        "unknown",
    }:
        quality_score = max(0, quality_score - 60)
        drop_flags.append("language_mismatch")
    flags.extend(review_flags)
    flags.extend(drop_flags)

    mail_review_flags, mail_drop_flags = validate_mail_output(
        instruction=instruction,
        input_text=input_text,
        output=output,
    )
    flags.extend(mail_review_flags)
    flags.extend(mail_drop_flags)

    if drop_flags or mail_drop_flags or quality_score < 45:
        action = "drop"
    elif review_flags or mail_review_flags or quality_score < 75:
        action = "review"
    else:
        action = "keep"

    curated_row = {
        "instruction": instruction,
        "input": input_text,
        "output": output,
        "task_type": task_type,
        "language": language,
        "quality_score": quality_score,
        "flags": sorted(set(flags)),
        "source": source,
        "action": action,
    }
    if domain_override:
        curated_row["domain"] = domain_override
    return curated_row


def _token_ngrams(text: str, n: int = 5) -> set[tuple[str, ...]]:
    tokens = re.findall(r"[a-zA-ZÀ-ỹ0-9]+", text.lower())
    if len(tokens) < n:
        return {tuple(tokens)} if tokens else set()
    return {tuple(tokens[index : index + n]) for index in range(len(tokens) - n + 1)}


def _jaccard(left: set[tuple[str, ...]], right: set[tuple[str, ...]]) -> float:
    if not left or not right:
        return 0.0
    return len(left & right) / len(left | right)


def mark_near_duplicates(
    curated_rows: list[dict[str, Any]],
    *,
    threshold: float = NEAR_DUPLICATE_JACCARD_THRESHOLD,
) -> list[dict[str, Any]]:
    seen_by_bucket: dict[tuple[str, str], list[set[tuple[str, ...]]]] = {}
    updated_rows: list[dict[str, Any]] = []
    for row in curated_rows:
        updated = dict(row)
        flags = list(updated.get("flags", []))
        if updated.get("action") == "keep":
            combined = " ".join(
                str(updated.get(field, "")) for field in ("instruction", "input", "output")
            )
            if len(combined.split()) < 40:
                updated_rows.append(updated)
                continue
            ngrams = _token_ngrams(combined)
            bucket = (str(updated.get("task_type", "")), str(updated.get("language", "")))
            seen_ngrams = seen_by_bucket.setdefault(bucket, [])
            if any(_jaccard(ngrams, previous) > threshold for previous in seen_ngrams):
                flags.append("near_duplicate")
                updated["action"] = "drop"
                updated["quality_score"] = min(int(updated.get("quality_score", 0)), 40)
            else:
                seen_ngrams.append(ngrams)
        updated["flags"] = sorted(set(flags))
        updated_rows.append(updated)
    return updated_rows


def enforce_task_type_ratio(
    curated_rows: list[dict[str, Any]],
    *,
    max_share: float = MAX_TASK_TYPE_SHARE,
) -> list[dict[str, Any]]:
    keep_indexes = [index for index, row in enumerate(curated_rows) if row["action"] == "keep"]
    if not keep_indexes:
        return curated_rows

    max_count = max(1, int(len(keep_indexes) * max_share))
    task_to_indexes: dict[str, list[int]] = {}
    for index in keep_indexes:
        task_to_indexes.setdefault(str(curated_rows[index]["task_type"]), []).append(index)

    updated_rows = [dict(row) for row in curated_rows]
    for indexes in task_to_indexes.values():
        if len(indexes) <= max_count:
            continue
        for index in indexes[max_count:]:
            updated = dict(updated_rows[index])
            flags = list(updated.get("flags", []))
            flags.append("task_ratio_downsampled")
            updated["flags"] = sorted(set(flags))
            updated["action"] = "review"
            updated_rows[index] = updated
    return updated_rows


def build_report(curated_rows: list[dict[str, Any]]) -> dict[str, Any]:
    action_counts = Counter(row["action"] for row in curated_rows)
    task_counts = Counter(row["task_type"] for row in curated_rows if row["action"] == "keep")
    language_counts = Counter(row["language"] for row in curated_rows if row["action"] == "keep")
    domain_counts = Counter(
        row["domain"] for row in curated_rows if row["action"] == "keep" and row.get("domain")
    )
    mojibake_rows = sum(
        1 for row in curated_rows if any("mojibake" in flag for flag in row["flags"])
    )
    review_reason_counts = Counter(
        flag
        for row in curated_rows
        if row["action"] == "review"
        for flag in row["flags"]
        if "mojibake_normalized" not in flag
    )
    drop_reason_counts = Counter(
        flag for row in curated_rows if row["action"] == "drop" for flag in row["flags"]
    )

    return {
        "total_rows": len(curated_rows),
        "action_counts": dict(action_counts),
        "mojibake_rows": mojibake_rows,
        "task_type_distribution": dict(task_counts),
        "language_distribution": dict(language_counts),
        "domain_distribution": dict(domain_counts),
        "top_review_reasons": review_reason_counts.most_common(10),
        "top_drop_reasons": drop_reason_counts.most_common(10),
    }


def write_report(path: Path, report: dict[str, Any]) -> None:
    ensure_parent_dir(path)
    resolved_path = path.expanduser().resolve()
    with resolved_path.open("w", encoding="utf-8") as handle:
        json.dump(report, handle, ensure_ascii=False, indent=2)
        handle.write("\n")


def main() -> int:
    args = parse_args()
    logger = configure_logging(args.log_level)

    try:
        source = args.source or args.input_path.stem
        raw_rows = read_jsonl(args.input_path)
        curated_rows = [curate_row(row, source=source) for row in raw_rows]
        curated_rows = mark_near_duplicates(curated_rows)
        curated_rows = enforce_task_type_ratio(curated_rows)
        kept_rows = [row for row in curated_rows if row["action"] == "keep"]
        review_rows = [row for row in curated_rows if row["action"] == "review"]
        report = build_report(curated_rows)

        write_jsonl(args.output_path, kept_rows)
        write_jsonl(args.review_path, review_rows)
        write_report(args.report_path, report)

        logger.info("Curated %s rows from %s.", len(raw_rows), args.input_path.resolve())
        logger.info("Kept rows: %s", len(kept_rows))
        logger.info("Review rows: %s", len(review_rows))
        logger.info("Dropped rows: %s", report["action_counts"].get("drop", 0))
        logger.info("Saved curated keep rows to: %s", args.output_path.resolve())
        logger.info("Saved review candidates to: %s", args.review_path.resolve())
        logger.info("Saved curation report to: %s", args.report_path.resolve())
        return 0
    except Exception as exc:
        get_logger().error("[curate_data] Error: %s", exc)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
