from __future__ import annotations

import os
from logging.config import fileConfig
from pathlib import Path

from alembic import context
from sqlalchemy import engine_from_config, pool

from src.server.db import metadata, sqlite_url_from_path, sync_migration_url
from src.utils import ROOT_DIR

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = metadata


def database_url() -> str:
    configured_url = os.getenv("OPEN_MODEL_DATABASE_URL")
    if configured_url:
        return configured_url

    raw_path = os.getenv("OPEN_MODEL_DB_PATH", "outputs/app/chat.sqlite3")
    db_path = Path(raw_path).expanduser()
    if not db_path.is_absolute():
        db_path = ROOT_DIR / db_path
    return sqlite_url_from_path(db_path)


def run_migrations_offline() -> None:
    context.configure(
        url=sync_migration_url(database_url()),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    configuration = config.get_section(config.config_ini_section, {})
    configuration["sqlalchemy.url"] = sync_migration_url(database_url())
    connectable = engine_from_config(
        configuration,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
