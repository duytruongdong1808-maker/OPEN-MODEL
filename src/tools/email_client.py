from __future__ import annotations

import asyncio
import re
from datetime import UTC, datetime
from email import policy
from email.header import decode_header, make_header
from email.message import Message
from email.parser import BytesParser
from email.utils import getaddresses, parsedate_to_datetime
from typing import Any

import aioimaplib
import bleach
import structlog

from .config import EmailSettings
from .errors import AuthError, ToolError
from .schemas import BODY_CHAR_CAP, SNIPPET_CHAR_CAP, AttachmentMeta, EmailMessage, EmailSummary

logger = structlog.get_logger(__name__)
SAFE_TAGS = [
    "a",
    "b",
    "blockquote",
    "br",
    "code",
    "div",
    "em",
    "li",
    "ol",
    "p",
    "pre",
    "span",
    "strong",
    "ul",
]
SAFE_ATTRS = {"a": ["href", "title"], "*": ["class"]}


def redact(value: str, secrets: list[str]) -> str:
    redacted = value
    for secret in secrets:
        if secret:
            redacted = redacted.replace(secret, "[REDACTED]")
    return redacted


def _decode_header(value: str | None) -> str:
    if not value:
        return ""
    try:
        return str(make_header(decode_header(value)))
    except Exception:
        return value


def _addresses(value: str | None) -> list[str]:
    return [address for _, address in getaddresses([_decode_header(value)]) if address]


def _first_address(value: str | None) -> str:
    addresses = _addresses(value)
    return addresses[0] if addresses else "unknown@example.com"


def _date(value: str | None) -> datetime:
    if value:
        try:
            parsed = parsedate_to_datetime(value)
            return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)
        except Exception:
            logger.warning("parse_date", fallback=True)
    return datetime.now(UTC)


def _collapse_snippet(value: str) -> str:
    return " ".join(value.split())[:SNIPPET_CHAR_CAP]


def _sanitize_html(value: str | None) -> str | None:
    if value is None:
        return None
    without_active = re.sub(r"<(script|style)\b[^>]*>.*?</\1>", "", value, flags=re.I | re.S)
    without_images = re.sub(r"<img\b[^>]*>", "", without_active, flags=re.I)
    return bleach.clean(without_images, tags=SAFE_TAGS, attributes=SAFE_ATTRS, strip=True)


def _response_parts(response: Any) -> tuple[str, list[bytes]]:
    if hasattr(response, "result") and hasattr(response, "lines"):
        return str(response.result), [bytes(line) for line in response.lines]
    if isinstance(response, tuple) and len(response) >= 2:
        result, lines = response[0], response[1]
        normalized = [
            bytes(line) if isinstance(line, (bytes, bytearray)) else str(line).encode()
            for line in lines
        ]
        return str(result), normalized
    raise ToolError("Unexpected IMAP response shape.")


def _ensure_ok(response: Any, *, action: str) -> list[bytes]:
    result, lines = _response_parts(response)
    if result.upper() != "OK":
        raise ToolError(f"IMAP {action} failed.")
    return lines


def _parse_capabilities(lines: list[bytes]) -> set[str]:
    joined = b" ".join(lines).decode("utf-8", errors="replace")
    return {item.upper() for item in joined.replace("CAPABILITY", "").split()}


async def _load_capabilities(client: Any) -> set[str]:
    if hasattr(client, "capability"):
        return _parse_capabilities(_ensure_ok(await client.capability(), action="capability"))
    capabilities: set[str] = set()
    if hasattr(client, "has_capability") and client.has_capability("MOVE"):
        capabilities.add("MOVE")
    return capabilities


def _parse_summary_fetch(lines: list[bytes]) -> list[tuple[str, set[str], bytes, bytes]]:
    records: list[tuple[str, set[str], bytes, bytes]] = []
    index = 0
    current_uid = ""
    current_flags: set[str] = set()
    current_header = b""
    current_snippet = b""
    while index < len(lines):
        line = lines[index]
        if b"FETCH" in line:
            if current_uid:
                records.append((current_uid, current_flags, current_header, current_snippet))
            uid_match = re.search(rb"\bUID\s+(\d+)", line)
            flags_match = re.search(rb"FLAGS\s+\(([^)]*)\)", line)
            current_uid = uid_match.group(1).decode() if uid_match else ""
            current_flags = set(
                (flags_match.group(1).decode(errors="replace") if flags_match else "").split()
            )
            current_header = b""
            current_snippet = b""
        if b"BODY[HEADER]" in line and index + 1 < len(lines):
            current_header = lines[index + 1]
        elif (b"BODY[TEXT]" in line or b"BODY[1]" in line) and index + 1 < len(lines):
            current_snippet = lines[index + 1]
        elif line.strip() == b")" and current_uid:
            records.append((current_uid, current_flags, current_header, current_snippet))
            current_uid = ""
            current_flags = set()
            current_header = b""
            current_snippet = b""
        index += 1
    if current_uid:
        records.append((current_uid, current_flags, current_header, current_snippet))
    return records


def _parse_rfc822_fetch(lines: list[bytes]) -> bytes:
    for index, line in enumerate(lines):
        if (
            b"FETCH" in line
            and (b"RFC822" in line or b"BODY.PEEK[]" in line or b"BODY[]" in line)
            and index + 1 < len(lines)
        ):
            return lines[index + 1]
    raise ToolError("IMAP RFC822 fetch returned no message literal.")


def _leaf_parts(message: Message) -> list[Message]:
    if not message.is_multipart():
        return [message]
    return [part for part in message.walk() if not part.is_multipart()]


def _part_text(part: Message) -> str:
    try:
        content = part.get_content()
        return content if isinstance(content, str) else str(content)
    except Exception:
        payload = part.get_payload(decode=True) or b""
        charset = part.get_content_charset() or "utf-8"
        return payload.decode(charset, errors="replace")


def _attachment_meta(part: Message) -> AttachmentMeta | None:
    filename = part.get_filename()
    disposition = part.get_content_disposition()
    if disposition != "attachment" and not filename:
        return None
    raw_payload = part.get_payload(decode=False) or ""
    transfer_encoding = (part.get("Content-Transfer-Encoding") or "").lower()
    if isinstance(raw_payload, bytes):
        raw_size = len(raw_payload)
    elif isinstance(raw_payload, str):
        raw_size = len(raw_payload.encode("utf-8"))
    else:
        raw_size = 0
    size_bytes = raw_size * 3 // 4 if transfer_encoding == "base64" else raw_size
    return AttachmentMeta(
        filename=_decode_header(filename),
        content_type=part.get_content_type(),
        size_bytes=size_bytes,
        content_id=part.get("Content-ID"),
        disposition=disposition,
    )


def _extract_message(uid: str, raw: bytes, flags: set[str]) -> EmailMessage:
    parsed = BytesParser(policy=policy.default).parsebytes(raw)
    body_text = ""
    body_html: str | None = None
    attachments: list[AttachmentMeta] = []

    for part in _leaf_parts(parsed):
        attachment = _attachment_meta(part)
        if attachment is not None:
            attachments.append(attachment)
            continue
        content_type = part.get_content_type()
        if content_type == "text/plain" and not body_text:
            body_text = _part_text(part)
        elif content_type == "text/html" and body_html is None:
            body_html = _sanitize_html(_part_text(part))

    truncated = False
    if len(body_text) > BODY_CHAR_CAP:
        body_text = body_text[:BODY_CHAR_CAP]
        truncated = True
    if body_html is not None and len(body_html) > BODY_CHAR_CAP:
        body_html = body_html[:BODY_CHAR_CAP]
        truncated = True

    references = _decode_header(parsed.get("References")).split()
    summary = _summary_from_headers(
        uid, parsed, flags, body_text or bleach.clean(body_html or "", tags=[], strip=True)
    )
    return EmailMessage(
        **summary.model_dump(by_alias=True),
        body_text=body_text,
        body_html=body_html,
        headers={key: _decode_header(value) for key, value in parsed.items()},
        message_id=_decode_header(parsed.get("Message-ID")),
        in_reply_to=_decode_header(parsed.get("In-Reply-To")) or None,
        references=references,
        attachments=attachments,
        truncated=truncated,
    )


def _summary_from_headers(
    uid: str, message: Message, flags: set[str], snippet_source: str
) -> EmailSummary:
    return EmailSummary(
        uid=str(uid),
        **{"from": _first_address(message.get("From"))},
        to=_addresses(message.get("To")),
        subject=_decode_header(message.get("Subject")),
        date=_date(message.get("Date")),
        snippet=_collapse_snippet(snippet_source),
        unread="\\Seen" not in flags,
        has_attachments=any(_attachment_meta(part) is not None for part in _leaf_parts(message)),
    )


class IMAPReader:
    def __init__(self, settings: EmailSettings):
        self.settings = settings
        self._client: Any | None = None
        self._capabilities: set[str] = set()

    async def __aenter__(self) -> "IMAPReader":
        await self.connect()
        return self

    async def __aexit__(self, exc_type: object, exc: object, tb: object) -> None:
        await self.close()

    async def connect(self) -> None:
        secret = self.settings.imap_pass.get_secret_value()
        last_error: Exception | None = None
        for attempt in range(3):
            try:
                client_cls = (
                    aioimaplib.IMAP4_SSL if self.settings.imap_use_ssl else aioimaplib.IMAP4
                )
                self._client = client_cls(
                    host=self.settings.imap_host, port=self.settings.imap_port
                )
                await self._client.wait_hello_from_server()
                login_response = await self._client.login(self.settings.imap_user, secret)
                result, _ = _response_parts(login_response)
                if result.upper() != "OK":
                    raise AuthError("IMAP authentication failed.")
                _ensure_ok(await self._client.select(self.settings.imap_mailbox), action="select")
                self._capabilities = await _load_capabilities(self._client)
                logger.info("imap_connect", mailbox=self.settings.imap_mailbox)
                return
            except AuthError:
                raise
            except Exception as exc:
                last_error = exc
                if attempt < 2:
                    await asyncio.sleep(0.1 * (attempt + 1))
        raise ToolError(redact(f"IMAP connect failed: {last_error}", [secret]))

    async def list_inbox(self, limit: int = 20, unread_only: bool = True) -> list[EmailSummary]:
        client = self._require_client()
        capped_limit = max(1, min(limit, self.settings.max_fetch_batch))
        criterion = "UNSEEN" if unread_only else "ALL"
        search_lines = _ensure_ok(await client.uid_search(criterion), action="uid_search")
        uids = [
            part
            for line in search_lines
            for part in line.decode(errors="replace").split()
            if part.isdigit()
        ]
        selected_uids = list(reversed(uids[-capped_limit:]))
        if not selected_uids:
            return []
        uid_set = ",".join(selected_uids)
        fetch_items = "(UID FLAGS ENVELOPE RFC822.SIZE BODY.PEEK[HEADER] BODY.PEEK[1]<0.200>)"
        records = _parse_summary_fetch(
            _ensure_ok(await client.uid("FETCH", uid_set, fetch_items), action="fetch")
        )
        summaries = []
        for uid, flags, header, snippet_bytes in records:
            parsed = BytesParser(policy=policy.default).parsebytes(header)
            snippet = snippet_bytes.decode(
                parsed.get_content_charset() or "utf-8", errors="replace"
            )
            summary = _summary_from_headers(uid, parsed, flags, snippet)
            # Header-only fetches cannot authoritatively detect attachments; get_email has the full MIME tree.
            summaries.append(summary.model_copy(update={"has_attachments": False}))
        logger.info("list_inbox", count=len(summaries), unread_only=unread_only)
        return summaries

    async def get_email(self, uid: str) -> EmailMessage:
        client = self._require_client()
        raw = _parse_rfc822_fetch(
            _ensure_ok(await client.uid("FETCH", str(uid), "(BODY.PEEK[])"), action="fetch")
        )
        message = _extract_message(str(uid), raw, set())
        logger.info(
            "get_email",
            uid=str(uid),
            subject_len=len(message.subject),
            body_len=len(message.body_text),
        )
        return message

    async def mark_read(self, uid: str) -> None:
        client = self._require_client()
        _ensure_ok(await client.uid("STORE", str(uid), "+FLAGS", "(\\Seen)"), action="store")
        logger.info("mark_read", uid=str(uid))

    async def archive(self, uid: str) -> None:
        client = self._require_client()
        if "MOVE" in self._capabilities:
            _ensure_ok(
                await client.uid("MOVE", str(uid), self.settings.archive_mailbox), action="move"
            )
            return
        _ensure_ok(await client.uid("COPY", str(uid), self.settings.archive_mailbox), action="copy")
        _ensure_ok(
            await client.uid("STORE", str(uid), "+FLAGS", "(\\Deleted)"), action="store_deleted"
        )
        if hasattr(client, "expunge"):
            _ensure_ok(await client.expunge(), action="expunge")
        else:
            _ensure_ok(await client.uid("EXPUNGE"), action="expunge")

    async def close(self) -> None:
        if self._client is None:
            return
        await self._client.logout()
        self._client = None
        logger.info("imap_close")

    def _require_client(self) -> Any:
        if self._client is None:
            raise ToolError("IMAP client is not connected.")
        return self._client


# TODO: OAuth2 support for Gmail/Outlook is planned for Phase 5. Phase 2 uses app passwords.
