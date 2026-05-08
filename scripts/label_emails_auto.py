import argparse
import json
import os
import re
import sys
import time
from pathlib import Path

import httpx


sys.stdout.reconfigure(encoding="utf-8")

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_INPUT = PROJECT_ROOT / "data" / "filtered" / "emails.jsonl"
DEFAULT_OUTPUT = PROJECT_ROOT / "data" / "labeled" / "emails_labeled.jsonl"
DEFAULT_FAILED = PROJECT_ROOT / "data" / "labeled" / "failed.jsonl"

CATEGORIES = (
    "personal",
    "work",
    "order/shipping",
    "bill/payment",
    "account/security",
    "newsletter",
    "calendar/booking",
    "government/official",
    "education",
    "other",
)
VALID_PRIORITIES = ("low", "medium", "high")

SYSTEM_PROMPT = (
    "You are an email triage assistant. Classify emails precisely. Always respond with valid "
    "JSON only — no markdown, no explanation, no code fences."
)
STRICT_PREFIX = (
    "IMPORTANT: Respond with a single raw JSON object only. No ```json fences, no explanation "
    "text.\n"
)

STUB_OUTPUT = {
    "category": "other",
    "priority": "low",
    "summary": "HTML-only email — body not available as plain text.",
    "action_items": [],
    "deadlines": [],
    "language": "unknown",
}


def parse_args():
    parser = argparse.ArgumentParser(description="Autonomously label filtered emails.")
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT, help="Input filtered JSONL.")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT, help="Output labeled JSONL.")
    parser.add_argument(
        "--dry-run",
        type=int,
        default=None,
        metavar="N",
        help="Label only the first N unlabeled emails then exit.",
    )
    return parser.parse_args()


def load_jsonl(path):
    rows = []
    if not path.exists():
        return rows
    with path.open("r", encoding="utf-8") as file:
        for line in file:
            if line.strip():
                rows.append(json.loads(line))
    return rows


def is_html_stub(body: str) -> bool:
    if not body:
        return True
    stripped = body.strip()
    lower = stripped.lower()
    if "html email" in lower and "email client" in lower:
        return True
    if len(stripped) < 50:
        return True
    return False


def extract_json(text: str) -> dict:
    text = text.strip()
    text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.IGNORECASE)
    text = re.sub(r"\s*```$", "", text)
    return json.loads(text.strip())


def validate_output(output):
    if not isinstance(output, dict):
        raise ValueError("output is not a JSON object")
    if output.get("category") not in CATEGORIES:
        raise ValueError("invalid category")
    if output.get("priority") not in VALID_PRIORITIES:
        raise ValueError("invalid priority")
    if not isinstance(output.get("summary"), str) or not output["summary"].strip():
        raise ValueError("summary must be a non-empty string")
    if not isinstance(output.get("action_items"), list):
        raise ValueError("action_items must be a list")
    if not isinstance(output.get("deadlines"), list):
        raise ValueError("deadlines must be a list")
    if not isinstance(output.get("language"), str) or not output["language"].strip():
        raise ValueError("language must be a non-empty string")


def make_record(email: dict, output: dict) -> dict:
    return {
        "uid": email.get("uid"),
        "input": {
            "from": email.get("from", ""),
            "subject": email.get("subject", ""),
            "body_text": email.get("body_text", ""),
            "date": email.get("date", ""),
        },
        "output": output,
    }


def make_user_prompt(email):
    from_field = email.get("from", "")
    subject = email.get("subject", "")
    date = email.get("date", "")
    body_preview = (email.get("body_text") or "")[:4000]
    return f"""Classify this email into exactly one category, one priority, a short summary, a list of action items, a list of deadlines, and the language.
Email:
From: {from_field}
Subject: {subject}
Date: {date}
Body:
{body_preview}
Respond with ONLY a JSON object matching this schema (no markdown fences, no extra keys):
{{
  "category": "<one of: personal | work | order/shipping | bill/payment | account/security | newsletter | calendar/booking | government/official | education | other>",
  "priority": "<one of: low | medium | high>",
  "summary": "<1-2 sentence summary in the same language as the email>",
  "action_items": ["<item>", ...],
  "deadlines": ["<deadline>", ...],
  "language": "<e.g. vi, en, vi+en>"
}}"""


def backend_config():
    if os.environ.get("LABEL_API_BASE"):
        base_url = os.environ["LABEL_API_BASE"]
        model = os.environ.get("LABEL_MODEL", "gpt-4o-mini")
        headers = {"Authorization": f"Bearer {os.environ['LABEL_API_KEY']}"}
    else:
        base_url = os.environ.get("OPEN_MODEL_VLLM_URL", "http://localhost:8001/v1")
        model = os.environ.get("OPEN_MODEL_VLLM_MODEL", "Qwen/Qwen2.5-7B-Instruct")
        headers = {}
        api_key = os.environ.get("OPEN_MODEL_VLLM_API_KEY")
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"
    return base_url.rstrip("/"), model, headers


def chat_completion(client, base_url, model, headers, system_prompt, user_prompt):
    response = client.post(
        f"{base_url}/chat/completions",
        headers=headers,
        json={
            "model": model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "temperature": 0,
        },
    )
    if response.status_code >= 500:
        raise httpx.HTTPStatusError(
            f"server error {response.status_code}", request=response.request, response=response
        )
    response.raise_for_status()
    data = response.json()
    return data["choices"][0]["message"]["content"]


def request_with_backoff(client, base_url, model, headers, system_prompt, user_prompt):
    waits = (2, 4, 8)
    for attempt in range(4):
        try:
            return chat_completion(client, base_url, model, headers, system_prompt, user_prompt)
        except httpx.HTTPStatusError as error:
            if error.response is not None and error.response.status_code < 500:
                raise
            if attempt == len(waits):
                raise
            time.sleep(waits[attempt])
        except (httpx.TransportError, httpx.TimeoutException):
            if attempt == len(waits):
                raise
            time.sleep(waits[attempt])


def parse_and_validate(raw_text):
    output = extract_json(raw_text)
    validate_output(output)
    return output


def label_with_llm(client, base_url, model, headers, email):
    user_prompt = make_user_prompt(email)
    raw_text = ""
    try:
        raw_text = request_with_backoff(
            client, base_url, model, headers, SYSTEM_PROMPT, user_prompt
        )
        return parse_and_validate(raw_text), raw_text, None
    except (json.JSONDecodeError, ValueError) as error:
        first_error = str(error)

    try:
        raw_text = chat_completion(
            client, base_url, model, headers, STRICT_PREFIX + SYSTEM_PROMPT, user_prompt
        )
        return parse_and_validate(raw_text), raw_text, None
    except (json.JSONDecodeError, ValueError) as error:
        return None, raw_text, f"{first_error}; retry failed: {error}"
    except (httpx.HTTPError, KeyError, IndexError) as error:
        return None, raw_text, str(error)


def append_jsonl(path, row):
    with path.open("a", encoding="utf-8") as file:
        file.write(json.dumps(row, ensure_ascii=False) + "\n")
        file.flush()


def write_failed(path, uid, error, raw_response):
    append_jsonl(path, {"uid": uid, "error": error, "raw_response": raw_response})


def main():
    args = parse_args()
    input_path = args.input.resolve()
    output_path = args.output.resolve()
    failed_path = DEFAULT_FAILED
    output_path.parent.mkdir(parents=True, exist_ok=True)
    failed_path.parent.mkdir(parents=True, exist_ok=True)

    emails = load_jsonl(input_path)
    records = load_jsonl(output_path)
    labeled_uids = {record.get("uid") for record in records}
    total = len(emails)
    skipped = 0
    labeled = 0
    failed = 0
    processed_unlabeled = 0
    base_url, model, headers = backend_config()

    with httpx.Client(timeout=120) as client:
        for index, email in enumerate(emails, start=1):
            uid = email.get("uid")
            if uid in labeled_uids:
                skipped += 1
                continue
            if args.dry_run is not None and processed_unlabeled >= args.dry_run:
                break

            processed_unlabeled += 1
            body = email.get("body_text") or ""
            if is_html_stub(body):
                output = dict(STUB_OUTPUT)
                append_jsonl(output_path, make_record(email, output))
                labeled += 1
                print(
                    f"[{index}/{total}] uid={uid} → "
                    f"{output['category']} | {output['priority']}  (stub)"
                )
                continue

            try:
                output, raw_text, error = label_with_llm(client, base_url, model, headers, email)
            except (httpx.HTTPError, KeyError, IndexError) as exception:
                output = None
                raw_text = ""
                error = str(exception)

            if output is None:
                write_failed(failed_path, uid, error, raw_text)
                failed += 1
                print(f"[{index}/{total}] uid={uid} → FAILED (saved to failed.jsonl)")
                continue

            append_jsonl(output_path, make_record(email, output))
            labeled += 1
            print(
                f"[{index}/{total}] uid={uid} → "
                f"{output['category']} | {output['priority']}"
            )

    print(f"Done. Labeled: {labeled} Skipped (already done): {skipped} Failed: {failed} Total: {total}")


if __name__ == "__main__":
    main()
