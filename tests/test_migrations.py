from __future__ import annotations

from pathlib import Path
import sqlite3
import subprocess
import sys

import pytest
import sqlalchemy as sa
from alembic import command
from alembic.config import Config


def alembic_config(database_url: str) -> Config:
    config = Config(str(Path("alembic.ini")))
    config.set_main_option("sqlalchemy.url", database_url)
    return config


def test_sqlite_migrations_apply_from_scratch(tmp_path: Path, monkeypatch) -> None:
    db_path = tmp_path / "migrations.sqlite3"
    monkeypatch.setenv("OPEN_MODEL_DATABASE_URL", f"sqlite:///{db_path.as_posix()}")

    command.upgrade(alembic_config(f"sqlite:///{db_path.as_posix()}"), "head")

    engine = sa.create_engine(f"sqlite:///{db_path.as_posix()}", future=True)
    inspector = sa.inspect(engine)
    assert {
        "conversations",
        "messages",
        "message_sources",
        "gmail_credentials",
        "audit_log",
        "mail_triage_feedback",
    }.issubset(set(inspector.get_table_names()))


@pytest.mark.postgres
def test_postgres_migrations_apply_from_scratch(postgres_container: str, monkeypatch) -> None:
    monkeypatch.setenv("OPEN_MODEL_DATABASE_URL", postgres_container)
    engine = sa.create_engine(postgres_container, future=True)
    with engine.begin() as connection:
        for table_name in [
            "alembic_version",
            "message_sources",
            "messages",
            "conversations",
            "gmail_credentials",
            "audit_log",
            "mail_triage_feedback",
        ]:
            connection.execute(sa.text(f'DROP TABLE IF EXISTS "{table_name}" CASCADE'))

    command.upgrade(alembic_config(postgres_container), "head")

    inspector = sa.inspect(engine)
    assert {
        "conversations",
        "messages",
        "message_sources",
        "gmail_credentials",
        "audit_log",
        "mail_triage_feedback",
    }.issubset(set(inspector.get_table_names()))
    audit_columns = {column["name"]: column for column in inspector.get_columns("audit_log")}
    assert "JSONB" in str(audit_columns["detail_json"]["type"]).upper()


@pytest.mark.postgres
def test_sqlite_to_postgres_migration_copies_rows(postgres_container: str, tmp_path: Path) -> None:
    sqlite_path = tmp_path / "source.sqlite3"
    with sqlite3.connect(sqlite_path) as connection:
        connection.execute("""
            CREATE TABLE conversations (
                id TEXT PRIMARY KEY,
                user_id TEXT NOT NULL DEFAULT 'legacy',
                title TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """)
        connection.execute(
            """
            INSERT INTO conversations (id, user_id, title, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            ("conversation-1", "user-a", "Hello", "2026-04-01T00:00:00Z", "2026-04-01T00:00:00Z"),
        )

    engine = sa.create_engine(postgres_container, future=True)
    with engine.begin() as connection:
        for table_name in [
            "message_sources",
            "messages",
            "conversations",
            "gmail_credentials",
            "audit_log",
            "send_ledger",
            "send_approvals",
        ]:
            connection.execute(sa.text(f'DROP TABLE IF EXISTS "{table_name}" CASCADE'))

    subprocess.run(
        [
            sys.executable,
            str(Path("scripts") / "migrate_sqlite_to_postgres.py"),
            "--sqlite-path",
            str(sqlite_path),
            "--postgres-url",
            postgres_container,
        ],
        check=True,
        capture_output=True,
        text=True,
    )

    with engine.connect() as connection:
        count = connection.execute(sa.text("SELECT COUNT(*) FROM conversations")).scalar_one()
    assert count == 1
