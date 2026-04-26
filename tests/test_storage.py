from __future__ import annotations

from src.server.storage import derive_conversation_title


def test_vietnamese_title_truncation_uses_utf8_ellipsis() -> None:
    title = derive_conversation_title("Xin chào " * 20)

    assert title.endswith("…")
    assert "â€¦" not in title
