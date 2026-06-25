#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import socket
import sqlite3
import sys
import uuid
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import instaloader
from instaloader.exceptions import InstaloaderException


ROOT = Path(__file__).resolve().parents[1]
DB_PATH = ROOT / "data" / "state.db"
RUN_LOG_DIR = ROOT / "logs" / "runs"

LOCK_NAME = "instagram_creator_scanner"
LOCK_TTL_MINUTES = 120


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

    connection.execute(
        "PRAGMA foreign_keys = ON"
    )

    connection.execute(
        "PRAGMA journal_mode = WAL"
    )

    connection.execute(
        "PRAGMA synchronous = NORMAL"
    )

    return connection


@dataclass
class CreatorResult:
    username: str
    status: str
    scanned: int = 0
    discovered: int = 0
    known: int = 0
    ignored_after_limit: int = 0
    error: str | None = None


@dataclass
class RunReport:
    run_id: str
    started_at: str
    finished_at: str | None
    status: str
    dry_run: bool
    login_user: str | None
    scan_limit: int
    creators: list[dict[str, Any]]
    creators_scanned: int
    videos_scanned: int
    videos_discovered: int
    videos_known: int
    errors: list[str]


def acquire_lock(
    connection: sqlite3.Connection,
    owner: str,
) -> None:
    now = utc_now()
    expires = now + timedelta(
        minutes=LOCK_TTL_MINUTES
    )

    connection.execute(
        "BEGIN IMMEDIATE"
    )

    existing = connection.execute(
        """
        SELECT owner, acquired_at, expires_at
        FROM pipeline_lock
        WHERE lock_name = ?
        """,
        (LOCK_NAME,),
    ).fetchone()

    if existing:
        try:
            expiry = datetime.fromisoformat(
                existing["expires_at"]
            )
        except ValueError:
            expiry = now - timedelta(seconds=1)

        if expiry > now:
            connection.rollback()

            raise RuntimeError(
                "Scanner is already running. "
                f"owner={existing['owner']} "
                f"acquired_at={existing['acquired_at']} "
                f"expires_at={existing['expires_at']}"
            )

    connection.execute(
        """
        INSERT INTO pipeline_lock (
            lock_name,
            owner,
            acquired_at,
            expires_at
        )
        VALUES (?, ?, ?, ?)
        ON CONFLICT(lock_name)
        DO UPDATE SET
            owner = excluded.owner,
            acquired_at = excluded.acquired_at,
            expires_at = excluded.expires_at
        """,
        (
            LOCK_NAME,
            owner,
            now.isoformat(timespec="seconds"),
            expires.isoformat(timespec="seconds"),
        ),
    )

    connection.commit()


def release_lock(
    connection: sqlite3.Connection,
    owner: str,
) -> None:
    connection.execute(
        """
        DELETE FROM pipeline_lock
        WHERE lock_name = ?
          AND owner = ?
        """,
        (
            LOCK_NAME,
            owner,
        ),
    )

    connection.commit()


def create_loader(
    login_user: str | None,
) -> instaloader.Instaloader:
    loader = instaloader.Instaloader(
        sleep=True,
        quiet=False,
        download_pictures=False,
        download_videos=False,
        download_video_thumbnails=False,
        download_geotags=False,
        download_comments=False,
        save_metadata=False,
        compress_json=False,
        post_metadata_txt_pattern="",
        max_connection_attempts=2,
        request_timeout=120,
    )

    if login_user:
        try:
            loader.load_session_from_file(
                login_user
            )
        except FileNotFoundError as exc:
            raise RuntimeError(
                "Instagram session file not found for "
                f"{login_user!r}. Run:\n"
                f"instaloader --login {login_user}"
            ) from exc

        print(
            f"Instagram session file loaded: "
            f"{login_user}"
        )
    else:
        print(
            "Instagram mode: anonymous"
        )

    return loader


def load_creators(
    connection: sqlite3.Connection,
    selected_creator: str | None,
) -> list[sqlite3.Row]:
    if selected_creator:
        rows = connection.execute(
            """
            SELECT *
            FROM creators
            WHERE username = ? COLLATE NOCASE
            """,
            (selected_creator.lstrip("@"),),
        ).fetchall()

        if not rows:
            raise RuntimeError(
                "Creator is not configured: "
                f"{selected_creator}"
            )

        if not rows[0]["enabled"]:
            raise RuntimeError(
                "Creator is disabled: "
                f"{rows[0]['username']}"
            )

        return rows

    return connection.execute(
        """
        SELECT *
        FROM creators
        WHERE enabled = 1
          AND scan_reels = 1
        ORDER BY username COLLATE NOCASE
        """
    ).fetchall()


def safe_caption(post) -> str:
    try:
        return post.caption or ""
    except InstaloaderException:
        return ""


def register_video(
    connection: sqlite3.Connection,
    creator_id: int,
    username: str,
    post,
    dry_run: bool,
) -> bool:
    shortcode = post.shortcode

    existing = connection.execute(
        """
        SELECT id, status
        FROM videos
        WHERE creator_id = ?
          AND shortcode = ?
        """,
        (
            creator_id,
            shortcode,
        ),
    ).fetchone()

    if existing:
        return False

    published_at = (
        post.date_utc
        .astimezone(timezone.utc)
        .isoformat(timespec="seconds")
    )

    source_url = (
        "https://www.instagram.com/"
        f"reel/{shortcode}/"
    )

    caption = safe_caption(post)
    now = iso_now()

    if dry_run:
        print(
            "  DRY-RUN NEW "
            f"{username}/{shortcode} "
            f"{published_at}"
        )

        return True

    connection.execute(
        """
        INSERT INTO videos (
            creator_id,
            shortcode,
            source_url,
            published_at,
            caption,
            discovered_at,
            status,
            attempt_count,
            created_at,
            updated_at
        )
        VALUES (?, ?, ?, ?, ?, ?, 'pending', 0, ?, ?)
        """,
        (
            creator_id,
            shortcode,
            source_url,
            published_at,
            caption,
            now,
            now,
            now,
        ),
    )

    connection.commit()

    print(
        "  NEW PENDING "
        f"{username}/{shortcode} "
        f"{published_at}"
    )

    return True


def scan_creator(
    connection: sqlite3.Connection,
    loader: instaloader.Instaloader,
    creator: sqlite3.Row,
    scan_limit: int,
    dry_run: bool,
) -> CreatorResult:
    username = creator["username"]

    result = CreatorResult(
        username=username,
        status="running",
    )

    print()
    print(
        f"Scanning creator: {username}"
    )

    try:
        profile = (
            instaloader.Profile.from_username(
                loader.context,
                username,
            )
        )

        max_new = creator["max_new_per_run"]
        iterator = profile.get_reels()

        for post in iterator:
            if result.scanned >= scan_limit:
                break

            result.scanned += 1

            is_new = register_video(
                connection=connection,
                creator_id=creator["id"],
                username=username,
                post=post,
                dry_run=dry_run,
            )

            if is_new:
                if result.discovered >= max_new:
                    result.ignored_after_limit += 1

                    print(
                        "  NEW BUT DEFERRED "
                        f"{username}/{post.shortcode} "
                        f"max_new_per_run={max_new}"
                    )

                    continue

                result.discovered += 1
            else:
                result.known += 1

                print(
                    "  KNOWN "
                    f"{username}/{post.shortcode}"
                )

        result.status = "completed"

        if not dry_run:
            connection.execute(
                """
                UPDATE creators
                SET
                    last_scan_at = ?,
                    last_scan_status = 'completed',
                    last_error = NULL,
                    updated_at = ?
                WHERE id = ?
                """,
                (
                    iso_now(),
                    iso_now(),
                    creator["id"],
                ),
            )

            connection.commit()

    except Exception as exc:
        result.status = "failed"
        result.error = (
            f"{type(exc).__name__}: {exc}"
        )

        if not dry_run:
            connection.execute(
                """
                UPDATE creators
                SET
                    last_scan_at = ?,
                    last_scan_status = 'failed',
                    last_error = ?,
                    updated_at = ?
                WHERE id = ?
                """,
                (
                    iso_now(),
                    result.error,
                    iso_now(),
                    creator["id"],
                ),
            )

            connection.commit()

    return result


def save_report(
    report: RunReport,
) -> Path:
    RUN_LOG_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    path = RUN_LOG_DIR / (
        f"{report.run_id}.json"
    )

    temp_path = path.with_suffix(
        ".json.tmp"
    )

    temp_path.write_text(
        json.dumps(
            asdict(report),
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )

    os.replace(
        temp_path,
        path,
    )

    return path


def insert_run(
    connection: sqlite3.Connection,
    report: RunReport,
) -> None:
    connection.execute(
        """
        INSERT INTO runs (
            id,
            started_at,
            status
        )
        VALUES (?, ?, 'running')
        """,
        (
            report.run_id,
            report.started_at,
        ),
    )

    connection.commit()


def finish_run(
    connection: sqlite3.Connection,
    report: RunReport,
) -> None:
    connection.execute(
        """
        UPDATE runs
        SET
            finished_at = ?,
            status = ?,
            creators_scanned = ?,
            videos_discovered = ?,
            videos_completed = 0,
            videos_failed = ?,
            videos_deferred = ?,
            error_summary = ?
        WHERE id = ?
        """,
        (
            report.finished_at,
            report.status,
            report.creators_scanned,
            report.videos_discovered,
            len(report.errors),
            sum(
                creator.get(
                    "ignored_after_limit",
                    0,
                )
                for creator in report.creators
            ),
            (
                json.dumps(
                    report.errors,
                    ensure_ascii=False,
                )
                if report.errors
                else None
            ),
            report.run_id,
        ),
    )

    connection.commit()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Scan configured Instagram creators "
            "and register new Reels as pending."
        )
    )

    parser.add_argument(
        "--creator",
        help=(
            "Scan one configured and enabled "
            "creator only."
        ),
    )

    parser.add_argument(
        "--scan-limit",
        type=int,
        default=50,
        help=(
            "Maximum Reels inspected per creator. "
            "Default: 50."
        ),
    )

    parser.add_argument(
        "--login-user",
        default=os.environ.get(
            "INSTAGRAM_LOGIN_USER"
        ),
        help=(
            "Load an Instaloader session for this "
            "Instagram username."
        ),
    )

    parser.add_argument(
        "--dry-run",
        action="store_true",
        help=(
            "Scan Instagram but do not insert "
            "videos or update creator state."
        ),
    )

    return parser


def main() -> int:
    args = build_parser().parse_args()

    if not DB_PATH.exists():
        print(
            f"ERROR: Database not found: "
            f"{DB_PATH}",
            file=sys.stderr,
        )

        return 1

    if not 1 <= args.scan_limit <= 500:
        print(
            "ERROR: --scan-limit must be "
            "between 1 and 500.",
            file=sys.stderr,
        )

        return 1

    run_id = (
        utc_now().strftime("%Y%m%dT%H%M%SZ")
        + "-"
        + uuid.uuid4().hex[:8]
    )

    owner = (
        f"{socket.gethostname()}:"
        f"{os.getpid()}:{run_id}"
    )

    report = RunReport(
        run_id=run_id,
        started_at=iso_now(),
        finished_at=None,
        status="running",
        dry_run=args.dry_run,
        login_user=args.login_user,
        scan_limit=args.scan_limit,
        creators=[],
        creators_scanned=0,
        videos_scanned=0,
        videos_discovered=0,
        videos_known=0,
        errors=[],
    )

    connection = connect()
    lock_acquired = False

    try:
        creators = load_creators(
            connection,
            args.creator,
        )

        if not creators:
            print(
                "No enabled creators to scan."
            )

            report.status = "completed"
            report.finished_at = iso_now()

            path = save_report(report)

            print(
                f"Report: {path}"
            )

            return 0

        if not args.dry_run:
            acquire_lock(
                connection,
                owner,
            )

            lock_acquired = True

            insert_run(
                connection,
                report,
            )

        loader = create_loader(
            args.login_user
        )

        for creator in creators:
            result = scan_creator(
                connection=connection,
                loader=loader,
                creator=creator,
                scan_limit=args.scan_limit,
                dry_run=args.dry_run,
            )

            result_dict = asdict(result)

            report.creators.append(
                result_dict
            )

            report.creators_scanned += 1
            report.videos_scanned += (
                result.scanned
            )
            report.videos_discovered += (
                result.discovered
            )
            report.videos_known += (
                result.known
            )

            if result.error:
                report.errors.append(
                    f"{result.username}: "
                    f"{result.error}"
                )

        report.finished_at = iso_now()

        report.status = (
            "completed_with_errors"
            if report.errors
            else "completed"
        )

        if not args.dry_run:
            finish_run(
                connection,
                report,
            )

        report_path = save_report(
            report
        )

        print()
        print(
            f"SCAN_{report.status.upper()}"
        )

        print(
            f"run_id={report.run_id}"
        )

        print(
            f"creators_scanned="
            f"{report.creators_scanned}"
        )

        print(
            f"videos_scanned="
            f"{report.videos_scanned}"
        )

        print(
            f"videos_discovered="
            f"{report.videos_discovered}"
        )

        print(
            f"videos_known="
            f"{report.videos_known}"
        )

        print(
            f"errors={len(report.errors)}"
        )

        print(
            f"report={report_path}"
        )

        return (
            0
            if not report.errors
            else 2
        )

    except Exception as exc:
        report.status = "failed"
        report.finished_at = iso_now()

        report.errors.append(
            f"{type(exc).__name__}: {exc}"
        )

        if not args.dry_run:
            try:
                existing = connection.execute(
                    """
                    SELECT id
                    FROM runs
                    WHERE id = ?
                    """,
                    (report.run_id,),
                ).fetchone()

                if existing:
                    finish_run(
                        connection,
                        report,
                    )
            except sqlite3.Error:
                pass

        report_path = save_report(
            report
        )

        print(
            f"ERROR: {exc}",
            file=sys.stderr,
        )

        print(
            f"report={report_path}",
            file=sys.stderr,
        )

        return 1

    finally:
        if lock_acquired:
            try:
                release_lock(
                    connection,
                    owner,
                )
            except sqlite3.Error as exc:
                print(
                    "WARNING: Could not release "
                    f"scanner lock: {exc}",
                    file=sys.stderr,
                )

        connection.close()


if __name__ == "__main__":
    raise SystemExit(main())
