from __future__ import annotations

from contextlib import asynccontextmanager
import os
from pathlib import Path
from typing import AsyncIterator

from sqlalchemy import (
    CheckConstraint,
    Column,
    ForeignKey,
    Index,
    Integer,
    LargeBinary,
    MetaData,
    Table,
    Text,
    event,
)
from sqlalchemy.dialects import postgresql
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.engine import make_url

from ..utils import ROOT_DIR
from .observability.tracing import instrument_sqlalchemy_engine
from .settings import OpenModelSettings, get_open_model_settings

metadata = MetaData()

json_detail_type = Text().with_variant(postgresql.JSONB(astext_type=Text()), "postgresql")

conversations = Table(
    "conversations",
    metadata,
    Column("id", Text, primary_key=True),
    Column("user_id", Text, nullable=False, server_default="legacy"),
    Column("title", Text, nullable=False),
    Column("created_at", Text, nullable=False),
    Column("updated_at", Text, nullable=False),
    Index("idx_conversations_updated_at", "updated_at"),
    Index("idx_conversations_user_updated", "user_id", "updated_at"),
)

messages = Table(
    "messages",
    metadata,
    Column("id", Text, primary_key=True),
    Column(
        "conversation_id",
        Text,
        ForeignKey("conversations.id", ondelete="CASCADE"),
        nullable=False,
    ),
    Column("role", Text, nullable=False),
    Column("content", Text, nullable=False),
    Column("created_at", Text, nullable=False),
    CheckConstraint("role IN ('user', 'assistant')", name="ck_messages_role"),
    Index("idx_messages_conversation_id", "conversation_id", "created_at"),
)

message_sources = Table(
    "message_sources",
    metadata,
    Column("id", Text, primary_key=True),
    Column("message_id", Text, ForeignKey("messages.id", ondelete="CASCADE"), nullable=False),
    Column("title", Text, nullable=False),
    Column("source", Text, nullable=False),
    Column("published_at", Text),
    Column("url", Text, nullable=False),
    Column("position", Integer, nullable=False),
    Index("idx_message_sources_message_id", "message_id", "position"),
)

gmail_credentials = Table(
    "gmail_credentials",
    metadata,
    Column("user_id", Text, primary_key=True),
    Column("encrypted_token", LargeBinary, nullable=False),
    Column("email", Text),
    Column("scopes", Text),
    Column("connected_at", Text, nullable=False),
    Column("updated_at", Text, nullable=False),
)

audit_log = Table(
    "audit_log",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("ts", Text, nullable=False),
    Column("user_id", Text, nullable=False),
    Column("action", Text, nullable=False),
    Column("target", Text),
    Column("ip", Text),
    Column("user_agent", Text),
    Column("result", Text, nullable=False),
    Column("detail_json", json_detail_type),
    CheckConstraint("result IN ('success','denied','error')", name="ck_audit_log_result"),
    Index("idx_audit_log_user_ts", "user_id", "ts"),
    Index("idx_audit_log_action_ts", "action", "ts"),
)

send_ledger = Table(
    "send_ledger",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("sent_at", Text, nullable=False),
    Column("subject", Text, nullable=False),
    Column("first_recipient", Text, nullable=False),
    Column("status", Text, nullable=False),
    Index("idx_send_ledger_sent_at", "sent_at"),
)

send_approvals = Table(
    "send_approvals",
    metadata,
    Column("id", Text, primary_key=True),
    Column("created_at", Text, nullable=False),
    Column("payload_json", Text, nullable=False),
    Column("status", Text, nullable=False, server_default="pending"),
    Column("decided_at", Text),
    Column("decided_by", Text),
    Index("idx_send_approvals_status", "status"),
)

_engines: dict[str, AsyncEngine] = {}
_sessionmakers: dict[str, async_sessionmaker[AsyncSession]] = {}


def sqlite_url_from_path(path: Path) -> str:
    db_path = Path(path).expanduser()
    if not db_path.is_absolute():
        db_path = ROOT_DIR / db_path
    return f"sqlite+aiosqlite:///{db_path.resolve().as_posix()}"


def default_database_url(settings: OpenModelSettings | None = None) -> str:
    settings = settings or get_open_model_settings()
    if settings.open_model_database_url:
        return _url_with_password_file(settings.open_model_database_url)
    return sqlite_url_from_path(settings.open_model_db_path)


def default_ledger_database_url(settings: OpenModelSettings | None = None) -> str:
    settings = settings or get_open_model_settings()
    if settings.open_model_ledger_database_url:
        return _url_with_password_file(settings.open_model_ledger_database_url)
    if settings.open_model_database_url:
        return _url_with_password_file(settings.open_model_database_url)
    return sqlite_url_from_path(settings.open_model_ledger_db_path)


def _url_with_password_file(url: str) -> str:
    password_file = os.getenv("OPEN_MODEL_DATABASE_PASSWORD_FILE")
    if not password_file or not url.startswith("postgresql"):
        return url
    parsed = make_url(url)
    if parsed.password:
        return url
    password = Path(password_file).read_text(encoding="utf-8").strip()
    return parsed.set(password=password).render_as_string(hide_password=False)


def redact_url(url: str) -> str:
    if "@" not in url or "://" not in url:
        return url
    scheme, rest = url.split("://", 1)
    userinfo, host = rest.split("@", 1)
    if ":" not in userinfo:
        return url
    user, _password = userinfo.split(":", 1)
    return f"{scheme}://{user}:***@{host}"


def redact_url_in_message(message: str, url: str | None) -> str:
    if not url:
        return message
    return message.replace(url, redact_url(url))


def get_engine(database_url: str | None = None) -> AsyncEngine:
    url = database_url or default_database_url()
    engine = _engines.get(url)
    if engine is not None:
        return engine

    kwargs: dict[str, object] = {"future": True}
    if url.startswith("postgresql"):
        kwargs.update(
            {
                "pool_size": 10,
                "max_overflow": 20,
                "pool_pre_ping": True,
                "pool_recycle": 1800,
            }
        )
    engine = create_async_engine(url, **kwargs)
    if url.startswith("sqlite"):
        event.listen(engine.sync_engine, "connect", _enable_sqlite_foreign_keys)
    instrument_sqlalchemy_engine(engine.sync_engine)
    _engines[url] = engine
    return engine


def _enable_sqlite_foreign_keys(dbapi_connection, _connection_record) -> None:
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()


def get_sessionmaker(database_url: str | None = None) -> async_sessionmaker[AsyncSession]:
    url = database_url or default_database_url()
    maker = _sessionmakers.get(url)
    if maker is None:
        maker = async_sessionmaker(get_engine(url), expire_on_commit=False)
        _sessionmakers[url] = maker
    return maker


@asynccontextmanager
async def get_session(database_url: str | None = None) -> AsyncIterator[AsyncSession]:
    maker = get_sessionmaker(database_url)
    async with maker() as session:
        yield session


async def initialize_schema(database_url: str | None = None) -> None:
    engine = get_engine(database_url)
    async with engine.begin() as connection:
        await connection.run_sync(metadata.create_all)


async def dispose_engine(database_url: str | None = None) -> None:
    if database_url is None:
        urls = list(_engines)
    else:
        urls = [database_url]
    for url in urls:
        engine = _engines.pop(url, None)
        _sessionmakers.pop(url, None)
        if engine is not None:
            await engine.dispose()


def sync_migration_url(url: str) -> str:
    if url.startswith("sqlite+aiosqlite:"):
        return url.replace("sqlite+aiosqlite:", "sqlite:", 1)
    return url


__all__ = [
    "audit_log",
    "conversations",
    "default_database_url",
    "default_ledger_database_url",
    "dispose_engine",
    "get_engine",
    "get_session",
    "gmail_credentials",
    "initialize_schema",
    "message_sources",
    "messages",
    "metadata",
    "redact_url",
    "redact_url_in_message",
    "send_approvals",
    "send_ledger",
    "sqlite_url_from_path",
    "sync_migration_url",
]
