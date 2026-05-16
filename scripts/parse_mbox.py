import argparse
import json
import mailbox
import re
from email.header import decode_header
from email.utils import getaddresses, parseaddr
from html import unescape
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_INPUT = PROJECT_ROOT / "data" / "takeout_extracted" / "Takeout" / "Mail" / "all_mail.mbox"
DEFAULT_OUTPUT = PROJECT_ROOT / "data" / "raw" / "emails.jsonl"


def decode_mime_header(value):
    if not value:
        return ""

    pieces = []
    for part, charset in decode_header(value):
        if isinstance(part, bytes):
            try:
                pieces.append(part.decode(charset or "utf-8", errors="ignore"))
            except LookupError:
                pieces.append(part.decode("utf-8", errors="ignore"))
        else:
            pieces.append(part)
    return "".join(pieces).strip()


def payload_to_text(part):
    payload = part.get_payload(decode=True)
    if payload is None:
        raw_payload = part.get_payload()
        if isinstance(raw_payload, str):
            return raw_payload
        return ""
    return payload.decode("utf-8", errors="ignore")


def strip_html(value):
    value = re.sub(r"(?is)<(script|style).*?>.*?</\1>", " ", value)
    value = re.sub(r"(?s)<[^>]+>", " ", value)
    value = unescape(value)
    return re.sub(r"\s+", " ", value).strip()


def is_attachment(part):
    disposition = part.get("Content-Disposition", "")
    return disposition.lower().startswith("attachment")


def extract_body_text(message):
    plain_parts = []
    html_parts = []

    if message.is_multipart():
        parts = message.walk()
    else:
        parts = [message]

    for part in parts:
        if part.is_multipart() or is_attachment(part):
            continue

        content_type = part.get_content_type()
        if content_type == "text/plain":
            text = payload_to_text(part).strip()
            if text:
                plain_parts.append(text)
        elif content_type == "text/html":
            text = strip_html(payload_to_text(part))
            if text:
                html_parts.append(text)

    if plain_parts:
        return "\n\n".join(plain_parts).strip()
    return "\n\n".join(html_parts).strip()


def has_attachments(message):
    parts = message.walk() if message.is_multipart() else [message]
    return any(is_attachment(part) for part in parts)


def parse_labels(value):
    if not value:
        return []
    decoded = decode_mime_header(value)
    return [label.strip().lower() for label in decoded.split(",") if label.strip()]


def parse_message(index, message):
    from_name, from_address = parseaddr(message.get("From", ""))
    to_addresses = [address for _, address in getaddresses(message.get_all("To", [])) if address]
    body_text = extract_body_text(message)

    if not body_text.strip():
        return None

    return {
        "uid": str(index),
        "from": from_address,
        "from_name": decode_mime_header(from_name),
        "to": to_addresses,
        "subject": decode_mime_header(message.get("Subject", "")),
        "date": message.get("Date", ""),
        "body_text": body_text,
        "list_unsubscribe": message.get("List-Unsubscribe") is not None,
        "labels": parse_labels(message.get("X-Gmail-Labels", "")),
        "has_attachments": has_attachments(message),
    }


def parse_args():
    parser = argparse.ArgumentParser(description="Parse a Gmail Takeout MBOX into JSONL.")
    parser.add_argument(
        "--input", type=Path, default=DEFAULT_INPUT, help="Path to input MBOX file."
    )
    parser.add_argument(
        "--output", type=Path, default=DEFAULT_OUTPUT, help="Path to output JSONL file."
    )
    return parser.parse_args()


def main():
    args = parse_args()
    output_path = args.output
    output_path.parent.mkdir(parents=True, exist_ok=True)

    print(f"Parsing MBOX: {args.input}")
    print(f"Writing JSONL: {output_path}")

    parsed_count = 0
    mbox_file = mailbox.mbox(args.input, create=False)
    try:
        with output_path.open("w", encoding="utf-8") as output_file:
            for index, message in enumerate(mbox_file):
                record = parse_message(index, message)
                if record is not None:
                    output_file.write(json.dumps(record, ensure_ascii=False) + "\n")
                    parsed_count += 1

                if (index + 1) % 1000 == 0:
                    print(f"Processed {index + 1} messages, parsed {parsed_count} emails...")
    finally:
        mbox_file.close()

    relative_output = (
        output_path.relative_to(PROJECT_ROOT)
        if output_path.is_relative_to(PROJECT_ROOT)
        else output_path
    )
    print(f"Parsed {parsed_count} emails to {relative_output}")


if __name__ == "__main__":
    main()
