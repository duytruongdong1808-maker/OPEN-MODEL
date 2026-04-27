from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from sqlalchemy import delete, insert, select, update

from .db import (
    conversations,
    default_database_url,
    get_session,
    initialize_schema,
    message_sources,
    messages,
    sqlite_url_from_path,
)
from .schemas import ChatMessage, ConversationDetail, ConversationSummary, SourceItem

DEFAULT_CONVERSATION_TITLE = "New chat"
TITLE_MAX_LENGTH = 56


def utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="microseconds").replace("+00:00", "Z")


def derive_conversation_title(message: str) -> str:
    normalized = " ".join(message.strip().split())
    if not normalized:
        return DEFAULT_CONVERSATION_TITLE
    if len(normalized) <= TITLE_MAX_LENGTH:
        return normalized
    return normalized[: TITLE_MAX_LENGTH - 1].rstrip() + "\u2026"


@dataclass
class ConversationStore:
    db_path: Path | None = None
    database_url: str | None = None
    _initialized: bool = field(default=False, init=False)
    _initialize_lock: asyncio.Lock = field(default_factory=asyncio.Lock, init=False)

    def __post_init__(self) -> None:
        if self.database_url is None:
            self.database_url = (
                sqlite_url_from_path(self.db_path)
                if self.db_path is not None
                else default_database_url()
            )
        if self.db_path is not None:
            self.db_path = Path(self.db_path).expanduser().resolve()
            self.db_path.parent.mkdir(parents=True, exist_ok=True)

    async def initialize(self) -> None:
        if self._initialized:
            return
        async with self._initialize_lock:
            if not self._initialized:
                await initialize_schema(self.database_url)
                self._initialized = True

    async def _ensure_initialized(self) -> None:
        await self.initialize()

    async def create_conversation(
        self, user_id: str, title: str = DEFAULT_CONVERSATION_TITLE
    ) -> ConversationSummary:
        await self._ensure_initialized()
        conversation_id = str(uuid4())
        timestamp = utcnow_iso()
        async with get_session(self.database_url) as session:
            async with session.begin():
                await session.execute(
                    insert(conversations).values(
                        id=conversation_id,
                        user_id=user_id,
                        title=title,
                        created_at=timestamp,
                        updated_at=timestamp,
                    )
                )
        return await self.get_conversation_summary(conversation_id, user_id)

    async def conversation_exists(self, conversation_id: str, user_id: str) -> bool:
        await self._ensure_initialized()
        async with get_session(self.database_url) as session:
            row = (
                await session.execute(
                    select(conversations.c.id).where(
                        conversations.c.id == conversation_id,
                        conversations.c.user_id == user_id,
                    )
                )
            ).first()
        return row is not None

    async def ping(self) -> None:
        await self._ensure_initialized()
        async with get_session(self.database_url) as session:
            await session.execute(select(1))

    async def delete_conversation(self, conversation_id: str, user_id: str) -> bool:
        await self._ensure_initialized()
        async with get_session(self.database_url) as session:
            async with session.begin():
                result = await session.execute(
                    delete(conversations).where(
                        conversations.c.id == conversation_id,
                        conversations.c.user_id == user_id,
                    )
                )
        return (result.rowcount or 0) > 0

    async def list_conversations(self, user_id: str) -> list[ConversationSummary]:
        await self._ensure_initialized()
        last_message_preview = (
            select(messages.c.content)
            .where(messages.c.conversation_id == conversations.c.id)
            .order_by(messages.c.created_at.desc(), messages.c.id.desc())
            .limit(1)
            .scalar_subquery()
        )
        stmt = (
            select(
                conversations.c.id,
                conversations.c.title,
                conversations.c.created_at,
                conversations.c.updated_at,
                last_message_preview.label("last_message_preview"),
            )
            .where(conversations.c.user_id == user_id)
            .order_by(conversations.c.updated_at.desc(), conversations.c.created_at.desc())
        )
        async with get_session(self.database_url) as session:
            rows = (await session.execute(stmt)).mappings().all()
        return [ConversationSummary(**dict(row)) for row in rows]

    async def get_conversation_summary(
        self, conversation_id: str, user_id: str
    ) -> ConversationSummary:
        await self._ensure_initialized()
        last_message_preview = (
            select(messages.c.content)
            .where(messages.c.conversation_id == conversations.c.id)
            .order_by(messages.c.created_at.desc(), messages.c.id.desc())
            .limit(1)
            .scalar_subquery()
        )
        stmt = (
            select(
                conversations.c.id,
                conversations.c.title,
                conversations.c.created_at,
                conversations.c.updated_at,
                last_message_preview.label("last_message_preview"),
            )
            .where(conversations.c.id == conversation_id, conversations.c.user_id == user_id)
            .limit(1)
        )
        async with get_session(self.database_url) as session:
            row = (await session.execute(stmt)).mappings().first()
        if row is None:
            raise KeyError(conversation_id)
        return ConversationSummary(**dict(row))

    async def get_conversation(self, conversation_id: str, user_id: str) -> ConversationDetail:
        summary = await self.get_conversation_summary(conversation_id, user_id)
        await self._ensure_initialized()
        message_stmt = (
            select(messages.c.id, messages.c.role, messages.c.content, messages.c.created_at)
            .select_from(
                messages.join(conversations, conversations.c.id == messages.c.conversation_id)
            )
            .where(
                messages.c.conversation_id == conversation_id, conversations.c.user_id == user_id
            )
            .order_by(messages.c.created_at.asc(), messages.c.id.asc())
        )
        source_stmt = (
            select(
                message_sources.c.message_id,
                message_sources.c.title,
                message_sources.c.source,
                message_sources.c.published_at,
                message_sources.c.url,
            )
            .select_from(
                message_sources.join(messages, messages.c.id == message_sources.c.message_id).join(
                    conversations, conversations.c.id == messages.c.conversation_id
                )
            )
            .where(
                messages.c.conversation_id == conversation_id, conversations.c.user_id == user_id
            )
            .order_by(message_sources.c.position.asc(), message_sources.c.id.asc())
        )
        async with get_session(self.database_url) as session:
            message_rows = (await session.execute(message_stmt)).mappings().all()
            source_rows = (await session.execute(source_stmt)).mappings().all()

        sources_by_message: dict[str, list[SourceItem]] = {}
        for row in source_rows:
            source = SourceItem(
                title=row["title"],
                source=row["source"],
                published_at=row["published_at"],
                url=row["url"],
            )
            sources_by_message.setdefault(row["message_id"], []).append(source)

        chat_messages = [
            ChatMessage(
                id=row["id"],
                role=row["role"],
                content=row["content"],
                created_at=row["created_at"],
                sources=sources_by_message.get(row["id"], []),
            )
            for row in message_rows
        ]
        return ConversationDetail(**summary.model_dump(), messages=chat_messages)

    async def save_user_message(
        self, conversation_id: str, user_id: str, content: str
    ) -> ChatMessage:
        return await self._save_message(
            conversation_id, user_id, role="user", content=content, sources=[]
        )

    async def save_assistant_message(
        self,
        conversation_id: str,
        user_id: str,
        content: str,
        sources: list[SourceItem],
    ) -> ChatMessage:
        return await self._save_message(
            conversation_id, user_id, role="assistant", content=content, sources=sources
        )

    async def _save_message(
        self,
        conversation_id: str,
        user_id: str,
        *,
        role: str,
        content: str,
        sources: list[SourceItem],
    ) -> ChatMessage:
        await self._ensure_initialized()
        message_id = str(uuid4())
        timestamp = utcnow_iso()
        normalized_content = content.strip()
        if not normalized_content:
            raise ValueError("Message content cannot be empty.")

        async with get_session(self.database_url) as session:
            async with session.begin():
                conversation = (
                    (
                        await session.execute(
                            select(conversations.c.title).where(
                                conversations.c.id == conversation_id,
                                conversations.c.user_id == user_id,
                            )
                        )
                    )
                    .mappings()
                    .first()
                )
                if conversation is None:
                    raise KeyError(conversation_id)

                await session.execute(
                    insert(messages).values(
                        id=message_id,
                        conversation_id=conversation_id,
                        role=role,
                        content=normalized_content,
                        created_at=timestamp,
                    )
                )
                await session.execute(
                    update(conversations)
                    .where(
                        conversations.c.id == conversation_id, conversations.c.user_id == user_id
                    )
                    .values(updated_at=timestamp)
                )
                if role == "user" and conversation["title"] == DEFAULT_CONVERSATION_TITLE:
                    await session.execute(
                        update(conversations)
                        .where(
                            conversations.c.id == conversation_id,
                            conversations.c.user_id == user_id,
                        )
                        .values(title=derive_conversation_title(normalized_content))
                    )

                for index, source in enumerate(sources):
                    await session.execute(
                        insert(message_sources).values(
                            id=str(uuid4()),
                            message_id=message_id,
                            title=source.title,
                            source=source.source,
                            published_at=source.published_at,
                            url=source.url,
                            position=index,
                        )
                    )

        return ChatMessage(
            id=message_id,
            role=role,  # type: ignore[arg-type]
            content=normalized_content,
            created_at=timestamp,
            sources=sources,
        )
