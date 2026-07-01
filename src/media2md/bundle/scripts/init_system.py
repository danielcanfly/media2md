#!/usr/bin/env python3

from __future__ import annotations

import logging
import shutil
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

import yaml
from media2md_paths import command_path


PROJECT_ROOT = Path(__file__).resolve().parents[1]

CONFIG_PATH = PROJECT_ROOT / "config" / "creators.yaml"
DB_PATH = PROJECT_ROOT / "data" / "state.db"
LOG_PATH = PROJECT_ROOT / "logs" / "pipeline.log"

REQUIRED_DIRS = [
    PROJECT_ROOT / "config",
    PROJECT_ROOT / "data",
    PROJECT_ROOT / "workspace" / "downloads",
    PROJECT_ROOT / "workspace" / "transcripts",
    PROJECT_ROOT / "workspace" / "temp",
    PROJECT_ROOT / "markdown",
    PROJECT_ROOT / "logs",
    PROJECT_ROOT / "logs" / "runs",
]

VIDEO_STATUSES = [
    "discovered",
    "pending",
    "downloading",
    "downloaded",
    "transcribing",
    "transcribed",
    "rendering",
    "validating",
    "cleaning",
    "completed",
    "retry_wait",
    "failed",
    "skipped",
]

RUN_STATUSES = [
    "running",
    "completed",
    "completed_with_errors",
    "failed",
]


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def setup_logging() -> logging.Logger:
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)

    logger = logging.getLogger("instagram_to_md")
    logger.setLevel(logging.INFO)
    logger.handlers.clear()

    formatter = logging.Formatter(
        "%(asctime)s %(levelname)s %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%S%z",
    )

    console = logging.StreamHandler()
    console.setFormatter(formatter)

    file_handler = logging.FileHandler(LOG_PATH, encoding="utf-8")
    file_handler.setFormatter(formatter)

    logger.addHandler(console)
    logger.addHandler(file_handler)

    return logger


def validate_username(value: object) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError("Creator username must be a non-empty string.")

    username = value.strip().lstrip("@")
    allowed = set(
        "abcdefghijklmnopqrstuvwxyz"
        "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
        "0123456789._"
    )

    if any(character not in allowed for character in username):
        raise ValueError(f"Invalid Instagram username: {value!r}")

    return username


def load_creators() -> list[dict]:
    if not CONFIG_PATH.exists():
        raise FileNotFoundError(f"Missing creator config: {CONFIG_PATH}")

    raw = yaml.safe_load(CONFIG_PATH.read_text(encoding="utf-8")) or {}
    creators = raw.get("creators")

    if not isinstance(creators, list):
        raise ValueError(
            "config/creators.yaml must contain a top-level creators list."
        )

    validated: list[dict] = []
    seen: set[str] = set()

    for index, creator in enumerate(creators, start=1):
        if not isinstance(creator, dict):
            raise ValueError(f"Creator entry #{index} must be an object.")

        username = validate_username(creator.get("username"))
        key = username.lower()

        if key in seen:
            raise ValueError(f"Duplicate creator username: {username}")

        seen.add(key)

        max_new = creator.get("max_new_per_run", 20)

        if not isinstance(max_new, int) or not 1 <= max_new <= 500:
            raise ValueError(
                f"{username}: max_new_per_run must be between 1 and 500."
            )

        validated.append(
            {
                "username": username,
                "enabled": bool(creator.get("enabled", True)),
                "language": str(
                    creator.get("language", "auto")
                ).strip() or "auto",
                "max_new_per_run": max_new,
                "scan_reels": bool(creator.get("scan_reels", True)),
                "note": str(creator.get("note", "") or ""),
            }
        )

    return validated


def connect() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)

    connection = sqlite3.connect(DB_PATH, timeout=30)
    connection.row_factory = sqlite3.Row

    connection.execute("PRAGMA foreign_keys = ON")
    connection.execute("PRAGMA journal_mode = WAL")
    connection.execute("PRAGMA synchronous = NORMAL")

    return connection


def initialize_schema(connection: sqlite3.Connection) -> None:
    video_statuses = ", ".join(
        f"'{status}'" for status in VIDEO_STATUSES
    )
    run_statuses = ", ".join(
        f"'{status}'" for status in RUN_STATUSES
    )

    connection.executescript(
        f"""
        CREATE TABLE IF NOT EXISTS schema_meta (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS creators (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT NOT NULL COLLATE NOCASE UNIQUE,

            enabled INTEGER NOT NULL DEFAULT 1
                CHECK (enabled IN (0, 1)),

            language TEXT NOT NULL DEFAULT 'auto',

            max_new_per_run INTEGER NOT NULL DEFAULT 20
                CHECK (max_new_per_run >= 1),

            scan_reels INTEGER NOT NULL DEFAULT 1
                CHECK (scan_reels IN (0, 1)),

            note TEXT NOT NULL DEFAULT '',

            last_scan_at TEXT,
            last_scan_status TEXT,
            last_error TEXT,

            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS runs (
            id TEXT PRIMARY KEY,

            started_at TEXT NOT NULL,
            finished_at TEXT,

            status TEXT NOT NULL
                CHECK (status IN ({run_statuses})),

            creators_scanned INTEGER NOT NULL DEFAULT 0,
            videos_discovered INTEGER NOT NULL DEFAULT 0,
            videos_completed INTEGER NOT NULL DEFAULT 0,
            videos_failed INTEGER NOT NULL DEFAULT 0,
            videos_deferred INTEGER NOT NULL DEFAULT 0,

            error_summary TEXT
        );

        CREATE TABLE IF NOT EXISTS videos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,

            creator_id INTEGER NOT NULL
                REFERENCES creators(id)
                ON DELETE CASCADE,

            shortcode TEXT NOT NULL,
            source_url TEXT NOT NULL,

            published_at TEXT,
            caption TEXT,

            discovered_at TEXT NOT NULL,

            status TEXT NOT NULL DEFAULT 'discovered'
                CHECK (status IN ({video_statuses})),

            attempt_count INTEGER NOT NULL DEFAULT 0
                CHECK (attempt_count >= 0),

            next_retry_at TEXT,
            last_error TEXT,

            markdown_path TEXT,
            markdown_sha256 TEXT,
            completed_at TEXT,
            media_type TEXT,
            processing_class TEXT,

            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,

            UNIQUE (creator_id, shortcode)
        );

        CREATE INDEX IF NOT EXISTS idx_videos_status
            ON videos(status, next_retry_at);

        CREATE INDEX IF NOT EXISTS idx_videos_creator
            ON videos(creator_id, published_at);

        CREATE TABLE IF NOT EXISTS attempts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,

            video_id INTEGER NOT NULL
                REFERENCES videos(id)
                ON DELETE CASCADE,

            run_id TEXT
                REFERENCES runs(id)
                ON DELETE SET NULL,

            stage TEXT NOT NULL,
            started_at TEXT NOT NULL,
            finished_at TEXT,

            status TEXT NOT NULL,

            error_type TEXT,
            error_message TEXT
        );

        CREATE INDEX IF NOT EXISTS idx_attempts_video
            ON attempts(video_id, started_at);

        CREATE TABLE IF NOT EXISTS pipeline_lock (
            lock_name TEXT PRIMARY KEY,
            owner TEXT NOT NULL,
            acquired_at TEXT NOT NULL,
            expires_at TEXT NOT NULL
        );
        """
    )

    connection.execute(
        """
        INSERT INTO schema_meta (key, value)
        VALUES ('schema_version', '1')
        ON CONFLICT(key)
        DO UPDATE SET value = excluded.value
        """
    )
    columns = {str(row["name"]) for row in connection.execute("PRAGMA table_info(videos)").fetchall()}
    if "media_type" not in columns:
        connection.execute("ALTER TABLE videos ADD COLUMN media_type TEXT")
    if "processing_class" not in columns:
        connection.execute("ALTER TABLE videos ADD COLUMN processing_class TEXT")


def sync_creators(
    connection: sqlite3.Connection,
    creators: list[dict],
) -> tuple[int, int]:
    inserted = 0
    updated = 0
    now = utc_now()

    for creator in creators:
        existing = connection.execute(
            """
            SELECT id
            FROM creators
            WHERE username = ? COLLATE NOCASE
            """,
            (creator["username"],),
        ).fetchone()

        values = (
            int(creator["enabled"]),
            creator["language"],
            creator["max_new_per_run"],
            int(creator["scan_reels"]),
            creator["note"],
            now,
        )

        if existing:
            connection.execute(
                """
                UPDATE creators
                SET
                    enabled = ?,
                    language = ?,
                    max_new_per_run = ?,
                    scan_reels = ?,
                    note = ?,
                    updated_at = ?
                WHERE id = ?
                """,
                values + (existing["id"],),
            )
            updated += 1
        else:
            connection.execute(
                """
                INSERT INTO creators (
                    username,
                    enabled,
                    language,
                    max_new_per_run,
                    scan_reels,
                    note,
                    created_at,
                    updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    creator["username"],
                    int(creator["enabled"]),
                    creator["language"],
                    creator["max_new_per_run"],
                    int(creator["scan_reels"]),
                    creator["note"],
                    now,
                    now,
                ),
            )
            inserted += 1

    return inserted, updated


def healthcheck(
    connection: sqlite3.Connection,
    creator_count: int,
) -> bool:
    checks: list[tuple[bool, str, str]] = []

    checks.append(
        (
            sys.version_info >= (3, 11),
            "Python >= 3.11",
            sys.version.split()[0],
        )
    )

    for command in ["ffmpeg", "instaloader", "mlx_whisper"]:
        path = command_path(command)
        checks.append(
            (
                path is not None,
                f"Command available: {command}",
                path or "not found",
            )
        )

    for directory in REQUIRED_DIRS:
        checks.append(
            (
                directory.exists() and directory.is_dir(),
                f"Directory exists: {directory.relative_to(PROJECT_ROOT)}",
                str(directory),
            )
        )

    schema_version = connection.execute(
        """
        SELECT value
        FROM schema_meta
        WHERE key = 'schema_version'
        """
    ).fetchone()

    checks.append(
        (
            schema_version is not None,
            "SQLite schema available",
            (
                f"version={schema_version['value']}"
                if schema_version
                else "missing"
            ),
        )
    )

    checks.append(
        (
            creator_count >= 0,
            "Creator config loaded",
            f"{creator_count} creator(s)",
        )
    )

    write_test = PROJECT_ROOT / "markdown" / ".write-test"

    try:
        write_test.write_text("ok\n", encoding="utf-8")
        write_test.unlink()
        markdown_writable = True
        markdown_detail = "writable"
    except OSError as exc:
        markdown_writable = False
        markdown_detail = str(exc)

    checks.append(
        (
            markdown_writable,
            "Markdown directory",
            markdown_detail,
        )
    )

    all_passed = True

    for passed, label, detail in checks:
        optional = label.startswith("Command available:")
        status = "PASS" if passed else ("WARN" if optional else "FAIL")
        print(f"[{status}] {label} | {detail}")

        if not passed and not optional:
            all_passed = False

    return all_passed


def main() -> int:
    logger = setup_logging()

    for directory in REQUIRED_DIRS:
        directory.mkdir(parents=True, exist_ok=True)

    creators = load_creators()

    connection = connect()

    try:
        initialize_schema(connection)

        inserted, updated = sync_creators(
            connection,
            creators,
        )

        connection.commit()

        creator_count = connection.execute(
            "SELECT COUNT(*) AS count FROM creators"
        ).fetchone()["count"]

        logger.info(
            "Database initialized: %s",
            DB_PATH,
        )

        logger.info(
            "Creators synchronized: inserted=%d updated=%d",
            inserted,
            updated,
        )

        print()
        passed = healthcheck(
            connection,
            creator_count,
        )
        print()

        if not passed:
            print("PHASE1_FAILED")
            return 1

        print("PHASE1_READY")
        print(f"Database: {DB_PATH}")
        print(f"Creators: {creator_count}")
        print(f"Log: {LOG_PATH}")

        return 0

    except Exception:
        connection.rollback()
        logger.exception("Phase 1 initialization failed.")
        raise

    finally:
        connection.close()


if __name__ == "__main__":
    raise SystemExit(main())
