from __future__ import annotations

import base64
import os
from datetime import UTC, datetime
from email.header import decode_header, make_header
from email.utils import getaddresses, parsedate_to_datetime
from typing import Any

import bleach
from googleapiclient.discovery import build

from .email_client import _collapse_snippet, _sanitize_html
from .gmail_auth import load_authorized_credentials
from .schemas import BODY_CHAR_CAP, AttachmentMeta, EmailMessage, EmailSummary


SUMMARY_HEADERS = ["From", "To", "Subject", "Date"]


def _max_fetch_batch() -> int:
    raw_value = os.getenv("AGENT_MAX_FETCH_BATCH", "50")
    try:
        return max(1, min(int(raw_value), 500))
    except ValueError:
        return 50


def _decode_header(value: str | None) -> str:
    if not value:
        return ""
    try:
        return str(make_header(decode_header(value)))
    except Exception:
        return value


def _header_map(payload: dict[str, Any]) -> dict[str, str]:
    headers = payload.get("headers") or []
    return {
        str(item.get("name", "")): _decode_header(item.get("value"))
        for item in headers
        if item.get("name")
    }


def _header(headers: dict[str, str], name: str) -> str:
    lowered = name.lower()
    return next((value for key, value in headers.items() if key.lower() == lowered), "")


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
            pass
    return datetime.now(UTC)


def _decode_body(data: str | None) -> str:
    if not data:
        return ""
    padded = data + "=" * (-len(data) % 4)
    return base64.urlsafe_b64decode(padded.encode("ascii")).decode("utf-8", errors="replace")


def _walk_parts(payload: dict[str, Any]) -> list[dict[str, Any]]:
    children = payload.get("parts") or []
    if not children:
        return [payload]
    parts: list[dict[str, Any]] = []
    for child in children:
        parts.extend(_walk_parts(child))
    return parts


def _attachment_meta(part: dict[str, Any]) -> AttachmentMeta | None:
    filename = part.get("filename") or None
    body = part.get("body") or {}
    attachment_id = body.get("attachmentId")
    headers = _header_map(part)
    disposition = _header(headers, "Content-Disposition") or None
    if not filename and not attachment_id and not (disposition and "attachment" in disposition.lower()):
        return None
    return AttachmentMeta(
        filename=filename,
        content_type=part.get("mimeType") or "application/octet-stream",
        size_bytes=int(body.get("size") or 0),
        content_id=_header(headers, "Content-ID") or None,
        disposition=disposition,
    )


def _summary_from_message(message: dict[str, Any]) -> EmailSummary:
    payload = message.get("payload") or {}
    headers = _header_map(payload)
    label_ids = set(message.get("labelIds") or [])
    snippet = _collapse_snippet(str(message.get("snippet") or ""))
    parts = _walk_parts(payload)
    return EmailSummary(
        uid=str(message["id"]),
        **{"from": _first_address(_header(headers, "From"))},
        to=_addresses(_header(headers, "To")),
        subject=_header(headers, "Subject"),
        date=_date(_header(headers, "Date")),
        snippet=snippet,
        unread="UNREAD" in label_ids,
        has_attachments=any(_attachment_meta(part) is not None for part in parts),
    )


def _message_from_full(message: dict[str, Any]) -> EmailMessage:
    payload = message.get("payload") or {}
    headers = _header_map(payload)
    parts = _walk_parts(payload)
    body_text = ""
    body_html: str | None = None
    attachments: list[AttachmentMeta] = []

    for part in parts:
        attachment = _attachment_meta(part)
        if attachment is not None:
            attachments.append(attachment)
            continue
        mime_type = part.get("mimeType")
        text = _decode_body((part.get("body") or {}).get("data"))
        if mime_type == "text/plain" and not body_text:
            body_text = text
        elif mime_type == "text/html" and body_html is None:
            body_html = _sanitize_html(text)

    truncated = False
    if len(body_text) > BODY_CHAR_CAP:
        body_text = body_text[:BODY_CHAR_CAP]
        truncated = True
    if body_html is not None and len(body_html) > BODY_CHAR_CAP:
        body_html = body_html[:BODY_CHAR_CAP]
        truncated = True

    if not body_text and body_html:
        body_text = bleach.clean(body_html, tags=[], strip=True)

    summary = _summary_from_message(
        {
            **message,
            "snippet": message.get("snippet") or body_text,
        }
    )
    return EmailMessage(
        **summary.model_dump(by_alias=True),
        body_text=body_text,
        body_html=body_html,
        headers=headers,
        message_id=_header(headers, "Message-ID"),
        in_reply_to=_header(headers, "In-Reply-To") or None,
        references=_header(headers, "References").split(),
        attachments=attachments,
        truncated=truncated,
    )


class GmailReader:
    def __init__(self, service: Any | None = None, *, user_key: str | None = None):
        self._service = service
        self._user_key = user_key

    @property
    def service(self) -> Any:
        if self._service is None:
            credentials = load_authorized_credentials(user_key=self._user_key)
            self._service = build("gmail", "v1", credentials=credentials, cache_discovery=False)
        return self._service

    def list_inbox(self, limit: int = 20, unread_only: bool = True) -> list[EmailSummary]:
        capped_limit = max(1, min(limit, _max_fetch_batch()))
        list_params: dict[str, Any] = {
            "userId": "me",
            "labelIds": ["INBOX"],
            "maxResults": capped_limit,
        }
        if unread_only:
            list_params["q"] = "is:unread"
        list_request = self.service.users().messages().list(**list_params)
        listed = list_request.execute()
        messages = listed.get("messages") or []
        summaries: list[EmailSummary] = []
        for item in messages[:capped_limit]:
            fetched = (
                self.service.users()
                .messages()
                .get(
                    userId="me",
                    id=item["id"],
                    format="metadata",
                    metadataHeaders=SUMMARY_HEADERS,
                )
                .execute()
            )
            summaries.append(_summary_from_message(fetched))
        return summaries

    def get_email(self, uid: str) -> EmailMessage:
        message = (
            self.service.users()
            .messages()
            .get(userId="me", id=str(uid), format="full")
            .execute()
        )
        return _message_from_full(message)
