from __future__ import annotations

import base64
from email.utils import format_datetime
from datetime import datetime, timezone

from src.tools.gmail_reader import GmailReader


def encode_body(value: str) -> str:
    return base64.urlsafe_b64encode(value.encode("utf-8")).decode("ascii").rstrip("=")


def header(name: str, value: str) -> dict[str, str]:
    return {"name": name, "value": value}


MESSAGE_DATE = format_datetime(datetime(2026, 4, 25, 12, 0, tzinfo=timezone.utc))


FAKE_MESSAGES = {
    "msg-1": {
        "id": "msg-1",
        "labelIds": ["INBOX", "UNREAD"],
        "snippet": "Please review the launch checklist today.",
        "payload": {
            "mimeType": "multipart/mixed",
            "headers": [
                header("From", "Alice <alice@example.com>"),
                header("To", "reader@example.com"),
                header("Subject", "Launch checklist"),
                header("Date", MESSAGE_DATE),
                header("Message-ID", "<msg-1@example.com>"),
                header("References", "<root@example.com>"),
            ],
            "parts": [
                {
                    "mimeType": "text/plain",
                    "body": {"data": encode_body("Please review the launch checklist today.")},
                    "headers": [],
                },
                {
                    "filename": "brief.pdf",
                    "mimeType": "application/pdf",
                    "body": {"attachmentId": "att-1", "size": 512},
                    "headers": [header("Content-Disposition", "attachment; filename=brief.pdf")],
                },
            ],
        },
    },
    "msg-2": {
        "id": "msg-2",
        "labelIds": ["INBOX"],
        "snippet": "HTML only",
        "payload": {
            "mimeType": "text/html",
            "headers": [
                header("From", "Bob <bob@example.com>"),
                header("To", "reader@example.com"),
                header("Subject", "HTML note"),
                header("Date", MESSAGE_DATE),
            ],
            "body": {"data": encode_body("<p>Hello <strong>there</strong></p><script>x()</script>")},
        },
    },
}


class FakeRequest:
    def __init__(self, payload):
        self.payload = payload

    def execute(self):
        return self.payload


class FakeMessages:
    def __init__(self):
        self.list_calls = []
        self.get_calls = []

    def list(self, **kwargs):
        self.list_calls.append(kwargs)
        return FakeRequest({"messages": [{"id": "msg-1"}, {"id": "msg-2"}]})

    def get(self, **kwargs):
        self.get_calls.append(kwargs)
        return FakeRequest(FAKE_MESSAGES[kwargs["id"]])


class FakeService:
    def __init__(self):
        self.messages_api = FakeMessages()

    def users(self):
        return self

    def messages(self):
        return self.messages_api


def test_gmail_reader_lists_unread_inbox_summaries():
    service = FakeService()
    reader = GmailReader(service=service)

    items = reader.list_inbox(limit=2, unread_only=True)

    assert [item.uid for item in items] == ["msg-1", "msg-2"]
    assert items[0].subject == "Launch checklist"
    assert items[0].unread is True
    assert items[0].has_attachments is True
    assert service.messages_api.list_calls[0] == {
        "userId": "me",
        "labelIds": ["INBOX"],
        "maxResults": 2,
        "q": "is:unread",
    }
    assert service.messages_api.get_calls[0]["format"] == "metadata"


def test_gmail_reader_gets_full_message():
    service = FakeService()
    reader = GmailReader(service=service)

    message = reader.get_email("msg-1")

    assert message.uid == "msg-1"
    assert message.from_ == "alice@example.com"
    assert message.body_text == "Please review the launch checklist today."
    assert message.message_id == "<msg-1@example.com>"
    assert message.references == ["<root@example.com>"]
    assert message.attachments[0].filename == "brief.pdf"
    assert service.messages_api.get_calls[0] == {
        "userId": "me",
        "id": "msg-1",
        "format": "full",
    }


def test_gmail_reader_omits_query_when_listing_all_inbox():
    service = FakeService()
    reader = GmailReader(service=service)

    reader.list_inbox(limit=1, unread_only=False)

    assert service.messages_api.list_calls[0] == {
        "userId": "me",
        "labelIds": ["INBOX"],
        "maxResults": 1,
    }


def test_gmail_reader_sanitizes_html_body():
    reader = GmailReader(service=FakeService())

    message = reader.get_email("msg-2")

    assert "Hello" in message.body_text
    assert message.body_html == "<p>Hello <strong>there</strong></p>"
    assert "<script" not in message.body_html
