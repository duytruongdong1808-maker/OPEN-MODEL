from __future__ import annotations

import logging
import os

import pytest

from src.tools.config import get_email_settings
from src.tools.email_client import IMAPReader
from src.tools.errors import AuthError
from src.tools.schemas import BODY_CHAR_CAP, SNIPPET_CHAR_CAP


async def connected_reader(email_settings) -> IMAPReader:
    reader = IMAPReader(email_settings)
    await reader.connect()
    return reader


async def test_connect_calls_login_and_select(email_settings, fake_imap):
    reader = await connected_reader(email_settings)

    assert fake_imap.logged_in is True
    assert fake_imap.selected == "INBOX"
    assert fake_imap.login_args == ("reader@example.com", "s3cr3t-not-in-logs")

    await reader.close()


async def test_list_inbox_unread_only_filters(email_settings, fake_imap):
    reader = await connected_reader(email_settings)
    items = await reader.list_inbox(limit=10, unread_only=True)

    assert [item.uid for item in items] == ["1", "3", "4", "5", "6", "7"]
    assert ("uid_search", ("UNSEEN",)) in fake_imap.calls


async def test_list_inbox_returns_summaries_with_snippets(email_settings, fake_imap):
    before_flags = fake_imap.flags_for(1)
    reader = await connected_reader(email_settings)

    items = await reader.list_inbox(limit=3, unread_only=False)

    assert items
    assert all(len(item.snippet) <= SNIPPET_CHAR_CAP for item in items)
    assert fake_imap.flags_for(1) == before_flags
    fetch_calls = [call for call in fake_imap.calls if call[0] == "uid" and call[1][0] == "FETCH"]
    assert any("BODY.PEEK[HEADER]" in str(call[1]) for call in fetch_calls)


async def test_list_inbox_respects_limit(email_settings):
    reader = await connected_reader(email_settings)

    items = await reader.list_inbox(limit=2, unread_only=True)

    assert len(items) == 2


async def test_get_email_plain_text(email_settings):
    reader = await connected_reader(email_settings)

    message = await reader.get_email("1")

    assert "plain text message" in message.body_text
    assert message.body_html is None


async def test_get_email_multipart_alternative(email_settings):
    reader = await connected_reader(email_settings)

    message = await reader.get_email("2")

    assert "Plain body" in message.body_text
    assert message.body_html is not None
    assert "HTML body" in message.body_html
    assert "<script" not in message.body_html
    assert "<img" not in message.body_html


async def test_get_email_utf8_vietnamese_subject(email_settings):
    reader = await connected_reader(email_settings)

    message = await reader.get_email("3")

    assert message.subject == "Báo cáo tuần"


async def test_get_email_latin1_body_decodes_cleanly(email_settings):
    reader = await connected_reader(email_settings)

    message = await reader.get_email("4")

    assert "Café crème déjà vu" in message.body_text
    assert "Plain ASCII remains readable" in message.body_text


async def test_get_email_attachments_metadata_only(email_settings):
    reader = await connected_reader(email_settings)

    message = await reader.get_email("5")

    assert len(message.attachments) == 2
    assert message.attachments[0].filename == "brief.pdf"
    assert message.attachments[0].size_bytes > 0
    assert "%PDF-1.4" not in message.model_dump_json()


async def test_list_inbox_documents_header_only_attachment_limitation(email_settings):
    reader = await connected_reader(email_settings)

    summaries = await reader.list_inbox(limit=10, unread_only=False)
    full_message = await reader.get_email("5")

    summary = next(item for item in summaries if item.uid == "5")
    assert summary.has_attachments is False
    assert full_message.has_attachments is True


async def test_get_email_threading_headers(email_settings):
    reader = await connected_reader(email_settings)

    message = await reader.get_email("6")

    assert message.in_reply_to == "<original@example.com>"
    assert message.references == ["<root@example.com>", "<original@example.com>"]


async def test_get_email_truncates_large_body(email_settings):
    reader = await connected_reader(email_settings)

    message = await reader.get_email("7")

    assert message.truncated is True
    assert len(message.body_text) == BODY_CHAR_CAP


async def test_get_email_does_not_mark_seen(email_settings, fake_imap):
    before_flags = fake_imap.flags_for(1)
    reader = await connected_reader(email_settings)

    await reader.get_email("1")

    assert fake_imap.flags_for(1) == before_flags
    fetch_calls = [call for call in fake_imap.calls if call[0] == "uid" and call[1][0] == "FETCH"]
    assert any("BODY.PEEK[]" in str(call[1]) for call in fetch_calls)
    assert not any("(RFC822)" in str(call[1]) for call in fetch_calls)


async def test_mark_read_adds_seen_flag(email_settings, fake_imap):
    reader = await connected_reader(email_settings)

    await reader.mark_read("1")

    assert "\\Seen" in fake_imap.flags_for(1)
    assert ("uid", ("STORE", "1", "+FLAGS", "(\\Seen)")) in fake_imap.calls


async def test_archive_uses_move_when_capable(email_settings, fake_imap):
    reader = await connected_reader(email_settings)

    await reader.archive("1")

    assert ("uid", ("MOVE", "1", "Archive")) in fake_imap.calls


async def test_archive_uses_configured_mailbox(email_settings, fake_imap):
    settings = email_settings.model_copy(update={"archive_mailbox": "[Gmail]/All Mail"})
    reader = await connected_reader(settings)

    await reader.archive("1")

    assert ("uid", ("MOVE", "1", "[Gmail]/All Mail")) in fake_imap.calls


async def test_archive_falls_back_to_copy_expunge(email_settings, fake_imap):
    fake_imap.capabilities = {b"IMAP4rev1"}
    reader = await connected_reader(email_settings)

    await reader.archive("1")

    assert ("uid", ("COPY", "1", "Archive")) in fake_imap.calls
    assert ("uid", ("STORE", "1", "+FLAGS", "(\\Deleted)")) in fake_imap.calls
    assert ("expunge", ()) in fake_imap.calls


async def test_auth_failure_raises_auth_error(email_settings, fake_imap):
    fake_imap.fail_login = True
    reader = IMAPReader(email_settings)

    with pytest.raises(AuthError) as exc_info:
        await reader.connect()

    assert "s3cr3t-not-in-logs" not in str(exc_info.value)


async def test_context_manager_closes_on_exit(email_settings, fake_imap):
    with pytest.raises(RuntimeError):
        async with IMAPReader(email_settings):
            raise RuntimeError("boom")

    assert fake_imap.logged_in is False
    assert ("logout", ()) in fake_imap.calls


async def test_no_secrets_in_logs(caplog, email_settings):
    caplog.set_level(logging.DEBUG)

    async with IMAPReader(email_settings) as reader:
        await reader.list_inbox(limit=2, unread_only=False)
        await reader.get_email("1")

    assert "s3cr3t-not-in-logs" not in caplog.text


@pytest.mark.integration
@pytest.mark.skipif(not os.getenv("AGENT_IMAP_HOST"), reason="no real inbox")
async def test_real_inbox_smoke():
    async with IMAPReader(get_email_settings()) as reader:
        items = await reader.list_inbox(limit=3, unread_only=False)

    assert isinstance(items, list)
