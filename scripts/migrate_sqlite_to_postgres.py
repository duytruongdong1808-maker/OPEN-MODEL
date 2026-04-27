from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from collections.abc import Iterable
from pathlib import Path
from typing import Any

from sqlalchemy import create_engine, func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from src.server.db import (  # noqa: E402
    audit_log,
    conversations,
    gmail_credentials,
    message_sources,
    messages,
    metadata,
    send_approvals,
    send_ledger,
)

BATCH_SIZE = 500
TABLES = [
    conversations,
    messages,
    message_sources,
    gmail_credentials,
    audit_log,
    send_ledger,
    send_approvals,
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Migrate Open Model SQLite data to Postgres.")
    parser.add_argument("--sqlite-path", type=Path, required=True)
    parser.add_argument("--postgres-url", required=True)
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args()


def batched(rows: list[dict[str, Any]], size: int) -> Iterable[list[dict[str, Any]]]:
    for index in range(0, len(rows), size):
        yield rows[index : index + size]


def table_exists(connection: sqlite3.Connection, table_name: str) -> bool:
    row = connection.execute(
        "SELECT 1 FROM sqlite_master WHERE type = ? AND name = ?",
        ("table", table_name),
    ).fetchone()
    return row is not None


def read_rows(connection: sqlite3.Connection, table_name: str) -> list[dict[str, Any]]:
    if table_name not in {table.name for table in TABLES}:
        raise ValueError(f"Unsupported table: {table_name}")
    return [dict(row) for row in connection.execute(f"SELECT * FROM {table_name}").fetchall()]


def normalize_row(table_name: str, row: dict[str, Any]) -> dict[str, Any]:
    if table_name == "audit_log" and row.get("detail_json"):
        try:
            row["detail_json"] = json.loads(row["detail_json"])
        except json.JSONDecodeError:
            row["detail_json"] = {"legacy_text": row["detail_json"]}
    return row


def primary_key_columns(table) -> list[str]:
    return [column.name for column in table.primary_key.columns]


def destination_count(connection, table) -> int:
    return int(connection.execute(select(func.count()).select_from(table)).scalar_one())


def main() -> None:
    args = parse_args()
    sqlite_path = args.sqlite_path.expanduser().resolve()
    if not sqlite_path.exists():
        raise SystemExit(f"SQLite database does not exist: {sqlite_path}")

    engine = create_engine(args.postgres_url, future=True)
    metadata.create_all(engine)

    with sqlite3.connect(sqlite_path) as sqlite_connection:
        sqlite_connection.row_factory = sqlite3.Row
        source_rows: dict[str, list[dict[str, Any]]] = {}
        for table in TABLES:
            if not table_exists(sqlite_connection, table.name):
                source_rows[table.name] = []
                continue
            source_rows[table.name] = [
                normalize_row(table.name, row) for row in read_rows(sqlite_connection, table.name)
            ]

    if args.dry_run:
        for table in TABLES:
            print(f"{table.name}: would copy {len(source_rows[table.name])} row(s)")
        return

    with engine.begin() as postgres_connection:
        for table in TABLES:
            rows = source_rows[table.name]
            if not rows:
                continue
            conflict_columns = primary_key_columns(table)
            for batch in batched(rows, BATCH_SIZE):
                statement = pg_insert(table).values(batch)
                statement = statement.on_conflict_do_nothing(index_elements=conflict_columns)
                postgres_connection.execute(statement)

        mismatches: list[str] = []
        for table in TABLES:
            source_count = len(source_rows[table.name])
            dest_count = destination_count(postgres_connection, table)
            if source_count != dest_count:
                mismatches.append(f"{table.name}: source={source_count}, postgres={dest_count}")

    if mismatches:
        raise SystemExit("Row count verification failed:\n" + "\n".join(mismatches))

    print("SQLite to Postgres migration completed successfully.")


if __name__ == "__main__":
    main()
