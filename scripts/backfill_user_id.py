from __future__ import annotations

import argparse
import os
import sqlite3
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]


def default_db_path() -> Path:
    raw_path = os.getenv("OPEN_MODEL_DB_PATH", "outputs/app/chat.sqlite3")
    db_path = Path(raw_path).expanduser()
    if not db_path.is_absolute():
        db_path = ROOT_DIR / db_path
    return db_path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Backfill legacy conversation rows to a specific user_id."
    )
    parser.add_argument(
        "--user-id", required=True, help="User id to assign to legacy conversations."
    )
    parser.add_argument(
        "--db-path",
        type=Path,
        default=default_db_path(),
        help="SQLite chat database path. Defaults to OPEN_MODEL_DB_PATH or outputs/app/chat.sqlite3.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    user_id = args.user_id.strip()
    if not user_id:
        raise SystemExit("--user-id cannot be empty.")

    db_path = args.db_path.expanduser().resolve()
    with sqlite3.connect(db_path) as connection:
        cursor = connection.execute(
            "UPDATE conversations SET user_id = ? WHERE user_id = ?",
            (user_id, "legacy"),
        )
    print(f"Updated {cursor.rowcount} legacy conversation(s) in {db_path}.")


if __name__ == "__main__":
    main()
