from __future__ import annotations

import argparse
import os
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[1]


def default_db_path() -> Path:
    raw_path = os.getenv("OPEN_MODEL_DB_PATH", "outputs/app/chat.sqlite3")
    db_path = Path(raw_path).expanduser()
    if not db_path.is_absolute():
        db_path = ROOT_DIR / db_path
    return db_path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Purge audit_log rows older than N days.")
    parser.add_argument("--days", type=int, default=90, help="Retention window in days.")
    parser.add_argument(
        "--db-path",
        type=Path,
        default=default_db_path(),
        help="SQLite chat database path. Defaults to OPEN_MODEL_DB_PATH or outputs/app/chat.sqlite3.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if args.days < 0:
        raise SystemExit("--days must be >= 0.")

    db_path = args.db_path.expanduser().resolve()
    with sqlite3.connect(db_path) as connection:
        if args.days == 0:
            cursor = connection.execute("DELETE FROM audit_log")
        else:
            cutoff = (
                datetime.now(timezone.utc) - timedelta(days=args.days)
            ).isoformat(timespec="seconds").replace("+00:00", "Z")
            cursor = connection.execute("DELETE FROM audit_log WHERE ts < ?", (cutoff,))

    # Production deployments should schedule this script via cron or a Kubernetes CronJob.
    print(f"Purged {cursor.rowcount} audit row(s) from {db_path}.")


if __name__ == "__main__":
    main()
