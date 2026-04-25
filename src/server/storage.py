from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from .schemas import ChatMessage, ConversationDetail, ConversationSummary, SourceItem


DEFAULT_CONVERSATION_TITLE = "New chat"
TITLE_MAX_LENGTH = 56


def utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def derive_conversation_title(message: str) -> str:
    normalized = " ".join(message.strip().split())
    if not normalized:
        return DEFAULT_CONVERSATION_TITLE
    if len(normalized) <= TITLE_MAX_LENGTH:
        return normalized
    return normalized[: TITLE_MAX_LENGTH - 1].rstrip() + "…"


@dataclass
class ConversationStore:
    db_path: Path

    def __post_init__(self) -> None:
        self.db_path = Path(self.db_path).expanduser().resolve()
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.db_path)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        return connection

    def _initialize(self) -> None:
        with self._connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS conversations (
                    id TEXT PRIMARY KEY,
                    title TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS messages (
                    id TEXT PRIMARY KEY,
                    conversation_id TEXT NOT NULL,
                    role TEXT NOT NULL CHECK(role IN ('user', 'assistant')),
                    content TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY(conversation_id) REFERENCES conversations(id) ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS message_sources (
                    id TEXT PRIMARY KEY,
                    message_id TEXT NOT NULL,
                    title TEXT NOT NULL,
                    source TEXT NOT NULL,
                    published_at TEXT,
                    url TEXT NOT NULL,
                    position INTEGER NOT NULL,
                    FOREIGN KEY(message_id) REFERENCES messages(id) ON DELETE CASCADE
                );

                CREATE INDEX IF NOT EXISTS idx_conversations_updated_at ON conversations(updated_at DESC);
                CREATE INDEX IF NOT EXISTS idx_messages_conversation_id ON messages(conversation_id, created_at);
                CREATE INDEX IF NOT EXISTS idx_message_sources_message_id ON message_sources(message_id, position);
                """
            )

    def create_conversation(self, title: str = DEFAULT_CONVERSATION_TITLE) -> ConversationSummary:
        conversation_id = str(uuid4())
        timestamp = utcnow_iso()
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO conversations (id, title, created_at, updated_at)
                VALUES (?, ?, ?, ?)
                """,
                (conversation_id, title, timestamp, timestamp),
            )
        return self.get_conversation_summary(conversation_id)

    def conversation_exists(self, conversation_id: str) -> bool:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT 1 FROM conversations WHERE id = ?",
                (conversation_id,),
            ).fetchone()
        return row is not None

    def ping(self) -> None:
        with self._connect() as connection:
            connection.execute("SELECT 1").fetchone()

    def delete_conversation(self, conversation_id: str) -> bool:
        with self._connect() as connection:
            cursor = connection.execute(
                "DELETE FROM conversations WHERE id = ?",
                (conversation_id,),
            )
        return cursor.rowcount > 0

    def list_conversations(self) -> list[ConversationSummary]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT
                    c.id,
                    c.title,
                    c.created_at,
                    c.updated_at,
                    (
                        SELECT m.content
                        FROM messages AS m
                        WHERE m.conversation_id = c.id
                        ORDER BY m.rowid DESC
                        LIMIT 1
                    ) AS last_message_preview
                FROM conversations AS c
                ORDER BY c.updated_at DESC, c.created_at DESC
                """
            ).fetchall()
        return [ConversationSummary(**dict(row)) for row in rows]

    def get_conversation_summary(self, conversation_id: str) -> ConversationSummary:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT
                    c.id,
                    c.title,
                    c.created_at,
                    c.updated_at,
                    (
                        SELECT m.content
                        FROM messages AS m
                        WHERE m.conversation_id = c.id
                        ORDER BY m.rowid DESC
                        LIMIT 1
                    ) AS last_message_preview
                FROM conversations AS c
                WHERE c.id = ?
                """,
                (conversation_id,),
            ).fetchone()
        if row is None:
            raise KeyError(conversation_id)
        return ConversationSummary(**dict(row))

    def get_conversation(self, conversation_id: str) -> ConversationDetail:
        summary = self.get_conversation_summary(conversation_id)
        with self._connect() as connection:
            message_rows = connection.execute(
                """
                SELECT id, role, content, created_at
                FROM messages
                WHERE conversation_id = ?
                ORDER BY rowid ASC
                """,
                (conversation_id,),
            ).fetchall()
            source_rows = connection.execute(
                """
                SELECT
                    ms.message_id,
                    ms.title,
                    ms.source,
                    ms.published_at,
                    ms.url
                FROM message_sources AS ms
                INNER JOIN messages AS m ON m.id = ms.message_id
                WHERE m.conversation_id = ?
                ORDER BY ms.position ASC, ms.id ASC
                """,
                (conversation_id,),
            ).fetchall()

        sources_by_message: dict[str, list[SourceItem]] = {}
        for row in source_rows:
            source = SourceItem(
                title=row["title"],
                source=row["source"],
                published_at=row["published_at"],
                url=row["url"],
            )
            sources_by_message.setdefault(row["message_id"], []).append(source)

        messages = [
            ChatMessage(
                id=row["id"],
                role=row["role"],
                content=row["content"],
                created_at=row["created_at"],
                sources=sources_by_message.get(row["id"], []),
            )
            for row in message_rows
        ]
        return ConversationDetail(**summary.model_dump(), messages=messages)

    def save_user_message(self, conversation_id: str, content: str) -> ChatMessage:
        return self._save_message(conversation_id, role="user", content=content, sources=[])

    def save_assistant_message(
        self,
        conversation_id: str,
        content: str,
        sources: list[SourceItem],
    ) -> ChatMessage:
        return self._save_message(conversation_id, role="assistant", content=content, sources=sources)

    def _save_message(
        self,
        conversation_id: str,
        *,
        role: str,
        content: str,
        sources: list[SourceItem],
    ) -> ChatMessage:
        message_id = str(uuid4())
        timestamp = utcnow_iso()
        normalized_content = content.strip()
        if not normalized_content:
            raise ValueError("Message content cannot be empty.")

        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO messages (id, conversation_id, role, content, created_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (message_id, conversation_id, role, normalized_content, timestamp),
            )
            connection.execute(
                "UPDATE conversations SET updated_at = ? WHERE id = ?",
                (timestamp, conversation_id),
            )
            if role == "user":
                current_title = connection.execute(
                    "SELECT title FROM conversations WHERE id = ?",
                    (conversation_id,),
                ).fetchone()
                if current_title is not None and current_title["title"] == DEFAULT_CONVERSATION_TITLE:
                    connection.execute(
                        "UPDATE conversations SET title = ? WHERE id = ?",
                        (derive_conversation_title(normalized_content), conversation_id),
                    )

            for index, source in enumerate(sources):
                connection.execute(
                    """
                    INSERT INTO message_sources (
                        id,
                        message_id,
                        title,
                        source,
                        published_at,
                        url,
                        position
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        str(uuid4()),
                        message_id,
                        source.title,
                        source.source,
                        source.published_at,
                        source.url,
                        index,
                    ),
                )

        return ChatMessage(
            id=message_id,
            role=role,  # type: ignore[arg-type]
            content=normalized_content,
            created_at=timestamp,
            sources=sources,
        )
