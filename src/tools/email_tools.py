from __future__ import annotations

import asyncio

from .config import get_email_settings
from .email_client import IMAPReader
from .gmail_auth import has_gmail_credentials
from .gmail_reader import GmailReader
from .ledger import SendLedger
from .safety import SafetyPipeline
from .schemas import EmailMessage, EmailSummary, SendRequest, SendResult
from .smtp_sender import SMTPSender
from .registry import tool


@tool(name="read_inbox", description="List recent email summaries from the configured inbox.")
async def read_inbox(user_id: str, limit: int = 20, unread_only: bool = True) -> list[EmailSummary]:
    """List recent email summaries."""
    if has_gmail_credentials(user_id):
        return await asyncio.to_thread(GmailReader(user_id).list_inbox, limit, unread_only)
    async with IMAPReader(get_email_settings()) as reader:
        return await reader.list_inbox(limit=limit, unread_only=unread_only)


@tool(name="get_email", description="Read a full email by IMAP UID.")
async def get_email(user_id: str, uid: str) -> EmailMessage:
    """Read a full email by IMAP UID."""
    if has_gmail_credentials(user_id):
        return await asyncio.to_thread(GmailReader(user_id).get_email, uid)
    async with IMAPReader(get_email_settings()) as reader:
        return await reader.get_email(uid)


@tool(
    name="send_email", description="Send an email after safety checks, dry-run, and approval gates."
)
async def send_email(
    to: list[str],
    subject: str,
    body_text: str,
    body_html: str | None = None,
    cc: list[str] | None = None,
    bcc: list[str] | None = None,
    in_reply_to: str | None = None,
    references: list[str] | None = None,
) -> SendResult:
    """Send an email through SMTPSender."""
    req = SendRequest(
        to=to,
        cc=cc or [],
        bcc=bcc or [],
        subject=subject,
        body_text=body_text,
        body_html=body_html,
        in_reply_to=in_reply_to,
        references=references or [],
    )
    return await send_request(req)


async def send_request(req: SendRequest) -> SendResult:
    """Send a validated request through the safety pipeline and SMTP sender."""
    settings = get_email_settings()
    safety = SafetyPipeline(settings, SendLedger())
    sender = SMTPSender(settings, safety)
    try:
        return await sender.send(req)
    finally:
        await sender.close()


@tool(name="reply_email", description="Reply to an existing email by UID with threading headers.")
async def reply_email(
    user_id: str,
    uid: str,
    body_text: str,
    body_html: str | None = None,
    quote_original: bool = True,
) -> SendResult:
    """Reply to an existing email by UID."""
    original = await get_email(user_id, uid)
    subject = (
        original.subject
        if original.subject.lower().startswith("re:")
        else f"Re: {original.subject}"
    )
    reply_text = body_text
    reply_html = body_html
    if quote_original:
        quoted = "\n".join(f"> {line}" for line in original.body_text.splitlines())
        reply_text = (
            f"{body_text}\n\nOn {original.date.isoformat()}, {original.from_} wrote:\n{quoted}"
        )
        if body_html is not None and original.body_html is not None:
            reply_html = f"{body_html}<blockquote>{original.body_html}</blockquote>"
    references = [*original.references]
    if original.message_id and original.message_id not in references:
        references.append(original.message_id)
    return await send_email(
        to=[str(original.from_)],
        subject=subject,
        body_text=reply_text,
        body_html=reply_html,
        in_reply_to=original.message_id or None,
        references=references,
    )


@tool(name="mark_read", description="Mark an email read by IMAP UID.")
async def mark_read(uid: str) -> None:
    """Mark an email read by IMAP UID."""
    async with IMAPReader(get_email_settings()) as reader:
        await reader.mark_read(uid)


@tool(name="archive", description="Archive an email by IMAP UID.")
async def archive(uid: str) -> None:
    """Archive an email by IMAP UID."""
    async with IMAPReader(get_email_settings()) as reader:
        await reader.archive(uid)
