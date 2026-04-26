from __future__ import annotations

from pathlib import Path

import pytest

from src.server.storage import ConversationStore, derive_conversation_title


def test_vietnamese_title_truncation_uses_utf8_ellipsis() -> None:
    title = derive_conversation_title("Xin chào " * 20)

    assert title.endswith("…")
    assert "â€¦" not in title


def test_store_lists_only_requested_user_conversations(tmp_path: Path) -> None:
    store = ConversationStore(tmp_path / "chat.sqlite3")
    user_a = store.create_conversation("user-a")
    store.create_conversation("user-b")

    conversations = store.list_conversations("user-a")

    assert [conversation.id for conversation in conversations] == [user_a.id]


def test_store_hides_cross_user_conversation_details(tmp_path: Path) -> None:
    store = ConversationStore(tmp_path / "chat.sqlite3")
    conversation = store.create_conversation("user-b")

    with pytest.raises(KeyError):
        store.get_conversation(conversation.id, "user-a")


def test_store_blocks_cross_user_message_writes(tmp_path: Path) -> None:
    store = ConversationStore(tmp_path / "chat.sqlite3")
    conversation = store.create_conversation("user-b")

    with pytest.raises(KeyError):
        store.save_user_message(conversation.id, "user-a", "Nope.")

    assert store.get_conversation(conversation.id, "user-b").messages == []
