#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DB_PATH = ROOT / "data" / "state.db"
BACKUP_DIR = ROOT / "data" / "backups"

WORKER_LOCK_NAME = "instagram_video_worker"


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def iso_now() -> str:
    return utc_now().isoformat(timespec="seconds")


def connect() -> sqlite3.Connection:
    connection = sqlite3.connect(
        DB_PATH,
        timeout=30,
    )
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    connection.execute("PRAGMA journal_mode = WAL")
    return connection


def ensure_worker_not_running(
    connection: sqlite3.Connection,
) -> None:
    row = connection.execute(
        """
        SELECT owner, acquired_at, expires_at
        FROM pipeline_lock
        WHERE lock_name = ?
        """,
        (WORKER_LOCK_NAME,),
    ).fetchone()

    if not row:
        return

    try:
        expires_at = datetime.fromisoformat(
            row["expires_at"]
        )
    except ValueError:
        return

    if expires_at > utc_now():
        raise RuntimeError(
            "Worker is currently running. "
            f"owner={row['owner']} "
            f"acquired_at={row['acquired_at']} "
            f"expires_at={row['expires_at']}"
        )


def backup_database(
    connection: sqlite3.Connection,
) -> Path:
    BACKUP_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    stamp = utc_now().strftime(
        "%Y%m%dT%H%M%SZ"
    )

    destination_path = (
        BACKUP_DIR /
        f"state-before-queue-change-{stamp}.db"
    )

    destination = sqlite3.connect(
        destination_path
    )

    try:
        connection.backup(destination)
    finally:
        destination.close()

    return destination_path


def find_video(
    connection: sqlite3.Connection,
    shortcode: str,
) -> sqlite3.Row:
    rows = connection.execute(
        """
        SELECT
            v.*,
            c.username
        FROM videos AS v
        JOIN creators AS c
          ON c.id = v.creator_id
        WHERE v.shortcode = ?
        """,
        (shortcode,),
    ).fetchall()

    if not rows:
        raise RuntimeError(
            f"Video not found: {shortcode}"
        )

    if len(rows) > 1:
        raise RuntimeError(
            "Multiple videos share this shortcode. "
            "Manual inspection is required."
        )

    return rows[0]


def print_video(row: sqlite3.Row) -> None:
    print(f"creator={row['username']}")
    print(f"shortcode={row['shortcode']}")
    print(f"status={row['status']}")
    print(f"attempt_count={row['attempt_count']}")
    print(
        f"next_retry_at="
        f"{row['next_retry_at'] or '-'}"
    )
    print(
        f"markdown_path="
        f"{row['markdown_path'] or '-'}"
    )
    print(
        f"last_error="
        f"{row['last_error'] or '-'}"
    )


def command_show(args) -> int:
    connection = connect()

    try:
        row = find_video(
            connection,
            args.shortcode,
        )
        print_video(row)
        return 0
    finally:
        connection.close()


def command_retry_now(args) -> int:
    connection = connect()

    try:
        ensure_worker_not_running(
            connection
        )

        row = find_video(
            connection,
            args.shortcode,
        )

        allowed = {
            "retry_wait",
            "failed",
        }

        if row["status"] not in allowed:
            raise RuntimeError(
                "retry-now only accepts retry_wait "
                f"or failed items. Current status: "
                f"{row['status']}"
            )

        backup_path = backup_database(
            connection
        )

        connection.execute(
            "BEGIN IMMEDIATE"
        )

        connection.execute(
            """
            UPDATE videos
            SET
                status = 'pending',
                next_retry_at = NULL,
                last_error = NULL,
                updated_at = ?
            WHERE id = ?
            """,
            (
                iso_now(),
                row["id"],
            ),
        )

        connection.commit()

        updated = find_video(
            connection,
            args.shortcode,
        )

        print("QUEUE_RETRY_READY")
        print(
            f"backup={backup_path.relative_to(ROOT)}"
        )
        print(
            f"reason={args.reason or '-'}"
        )
        print_video(updated)

        return 0

    except Exception:
        connection.rollback()
        raise

    finally:
        connection.close()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Safely inspect and reset "
            "Instagram processing queue items."
        )
    )

    commands = parser.add_subparsers(
        dest="command",
        required=True,
    )

    command = commands.add_parser(
        "show",
        help="Show one video state.",
    )
    command.add_argument(
        "--shortcode",
        required=True,
    )
    command.set_defaults(
        function=command_show,
    )

    command = commands.add_parser(
        "retry-now",
        help=(
            "Reset one retry_wait or failed "
            "video back to pending."
        ),
    )
    command.add_argument(
        "--shortcode",
        required=True,
    )
    command.add_argument(
        "--reason",
        default="",
    )
    command.set_defaults(
        function=command_retry_now,
    )

    return parser


def main() -> int:
    if not DB_PATH.exists():
        print(
            f"ERROR: Database not found: {DB_PATH}",
            file=sys.stderr,
        )
        return 1

    args = build_parser().parse_args()

    try:
        return args.function(args)
    except (
        RuntimeError,
        sqlite3.Error,
        OSError,
    ) as exc:
        print(
            f"ERROR: {exc}",
            file=sys.stderr,
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
