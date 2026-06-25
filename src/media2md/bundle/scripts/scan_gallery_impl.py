#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import shutil
import socket
import sqlite3
import subprocess
import sys
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DB_PATH = ROOT / "data" / "state.db"
RUN_LOG_DIR = ROOT / "logs" / "runs"
DEFAULT_COOKIE_FILE = ROOT / "data" / "secrets" / "instagram-cookies.txt"

LOCK_NAME = "instagram_gallery_scanner"
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
                "Gallery scanner is already running. "
                f"owner={existing['owner']} "
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


def load_creators(
    connection: sqlite3.Connection,
    selected_creator: str | None,
) -> list[sqlite3.Row]:
    if selected_creator:
        username = selected_creator.strip().lstrip("@")

        rows = connection.execute(
            """
            SELECT *
            FROM creators
            WHERE username = ? COLLATE NOCASE
            """,
            (username,),
        ).fetchall()

        if not rows:
            raise RuntimeError(
                f"Creator is not configured: {username}"
            )

        if not rows[0]["enabled"]:
            raise RuntimeError(
                f"Creator is disabled: {username}"
            )

        if not rows[0]["scan_reels"]:
            raise RuntimeError(
                f"Reels scanning is disabled: {username}"
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


def normalize_date(value: Any) -> str | None:
    if value is None:
        return None

    text = str(value).strip()

    if not text:
        return None

    formats = (
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%dT%H:%M:%S",
    )

    for date_format in formats:
        try:
            parsed = datetime.strptime(
                text,
                date_format,
            )

            parsed = parsed.replace(
                tzinfo=timezone.utc
            )

            return parsed.isoformat(
                timespec="seconds"
            )

        except ValueError:
            pass

    try:
        parsed = datetime.fromisoformat(text)

        if parsed.tzinfo is None:
            parsed = parsed.replace(
                tzinfo=timezone.utc
            )

        return parsed.astimezone(
            timezone.utc
        ).isoformat(timespec="seconds")

    except ValueError:
        return text


def parse_gallery_events(
    payload: Any,
) -> list[dict[str, Any]]:
    if not isinstance(payload, list):
        raise RuntimeError(
            "gallery-dl JSON root must be a list."
        )

    reels: list[dict[str, Any]] = []
    seen: set[str] = set()

    for event in payload:
        if not (
            isinstance(event, list)
            and len(event) >= 3
            and event[0] == 3
            and isinstance(event[2], dict)
        ):
            continue

        metadata = event[2]

        shortcode = (
            metadata.get("post_shortcode")
            or metadata.get("shortcode")
        )

        if not shortcode:
            continue

        shortcode = str(shortcode)

        if shortcode in seen:
            continue

        subcategory = metadata.get(
            "subcategory"
        )

        if (
            subcategory is not None
            and subcategory != "reels"
        ):
            continue

        extension = str(
            metadata.get("extension", "")
        ).lower()

        if extension and extension != "mp4":
            continue

        seen.add(shortcode)

        username = (
            metadata.get("username")
            or metadata.get(
                "owner",
                {},
            ).get("username")
        )

        published_at = normalize_date(
            metadata.get("post_date")
            or metadata.get("date")
        )

        reels.append(
            {
                "shortcode": shortcode,
                "username": username,
                "media_id": (
                    metadata.get("media_id")
                    or metadata.get("post_id")
                ),
                "published_at": published_at,
                "caption": str(
                    metadata.get(
                        "description",
                        "",
                    )
                    or ""
                ),
                "source_url": (
                    "https://www.instagram.com/"
                    f"reel/{shortcode}/"
                ),
                "duration_seconds": (
                    metadata.get(
                        "audio_duration"
                    )
                ),
            }
        )

    return reels



def gallery_auth_args(
    cookies_file: str | None,
    cookies_browser: str | None,
) -> list[str]:
    if cookies_browser:
        return [
            "--cookies-from-browser",
            cookies_browser,
        ]

    if not cookies_file:
        raise RuntimeError(
            "No Instagram cookie source configured."
        )

    path = Path(cookies_file).expanduser()

    if not path.is_absolute():
        path = ROOT / path

    path = path.resolve()

    if not path.is_file():
        raise RuntimeError(
            f"Instagram cookie file not found: {path}"
        )

    if path.stat().st_size == 0:
        raise RuntimeError(
            f"Instagram cookie file is empty: {path}"
        )

    return [
        "--cookies",
        str(path),
    ]


def run_gallery_dl(
    username: str,
    scan_limit: int,
    cookies_file: str | None,
    cookies_browser: str | None,
    force_ipv4: bool,
) -> list[dict[str, Any]]:
    executable = shutil.which(
        "gallery-dl"
    )

    if not executable:
        raise RuntimeError(
            "gallery-dl command was not found."
        )

    url = (
        "https://www.instagram.com/"
        f"{username}/reels/"
    )

    command = [executable]
    command.extend(
        gallery_auth_args(
            cookies_file,
            cookies_browser,
        )
    )
    command.extend([
        "--resolve-json",
        "--post-range",
        f"1-{scan_limit}",
        "--retries",
        "5",
        "--http-timeout",
        "120",
        "-o",
        (
            "extractor.instagram.max-posts="
            f"{scan_limit}"
        ),
        url,
    ])

    if force_ipv4:
        command.insert(
            1,
            "--force-ipv4",
        )

    try:
        result = subprocess.run(
            command,
            cwd=ROOT,
            capture_output=True,
            text=True,
            timeout=600,
            check=False,
        )

    except subprocess.TimeoutExpired as exc:
        raise RuntimeError(
            "gallery-dl timed out after 600 seconds."
        ) from exc

    if result.returncode != 0:
        error = result.stderr.strip()

        if len(error) > 3000:
            error = error[-3000:]

        raise RuntimeError(
            "gallery-dl failed with "
            f"exit code {result.returncode}: "
            f"{error or 'no error output'}"
        )

    if not result.stdout.strip():
        return []

    try:
        payload = json.loads(
            result.stdout
        )

    except json.JSONDecodeError as exc:
        preview = result.stdout[:1000]

        raise RuntimeError(
            "gallery-dl returned invalid JSON: "
            f"{exc}; preview={preview!r}"
        ) from exc

    return parse_gallery_events(payload)


def video_exists(
    connection: sqlite3.Connection,
    creator_id: int,
    shortcode: str,
) -> sqlite3.Row | None:
    return connection.execute(
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


def insert_pending_video(
    connection: sqlite3.Connection,
    creator_id: int,
    reel: dict[str, Any],
) -> None:
    now = iso_now()

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
        VALUES (
            ?, ?, ?, ?, ?, ?,
            'pending',
            0,
            ?, ?
        )
        """,
        (
            creator_id,
            reel["shortcode"],
            reel["source_url"],
            reel["published_at"],
            reel["caption"],
            now,
            now,
            now,
        ),
    )


def scan_creator(
    connection: sqlite3.Connection,
    creator: sqlite3.Row,
    scan_limit: int,
    cookies_file: str | None,
    cookies_browser: str | None,
    force_ipv4: bool,
    dry_run: bool,
) -> dict[str, Any]:
    username = creator["username"]
    max_new = creator["max_new_per_run"]

    result: dict[str, Any] = {
        "username": username,
        "status": "running",
        "scanned": 0,
        "queued": 0,
        "known": 0,
        "deferred": 0,
        "error": None,
    }

    print()
    print(f"Scanning creator: {username}")

    try:
        reels = run_gallery_dl(
            username=username,
            scan_limit=scan_limit,
            cookies_file=cookies_file,
            cookies_browser=cookies_browser,
            force_ipv4=force_ipv4,
        )

        result["scanned"] = len(reels)

        for reel in reels:
            shortcode = reel["shortcode"]

            existing = video_exists(
                connection,
                creator["id"],
                shortcode,
            )

            if existing:
                result["known"] += 1

                print(
                    f"  KNOWN {username}/{shortcode} "
                    f"status={existing['status']}"
                )

                continue

            if result["queued"] >= max_new:
                result["deferred"] += 1

                print(
                    f"  DEFERRED {username}/{shortcode} "
                    f"max_new_per_run={max_new}"
                )

                continue

            if dry_run:
                print(
                    f"  DRY-RUN WOULD QUEUE "
                    f"{username}/{shortcode} "
                    f"{reel['published_at'] or '-'}"
                )
            else:
                insert_pending_video(
                    connection,
                    creator["id"],
                    reel,
                )

                print(
                    f"  NEW PENDING "
                    f"{username}/{shortcode} "
                    f"{reel['published_at'] or '-'}"
                )

            result["queued"] += 1

        result["status"] = "completed"

        if not dry_run:
            now = iso_now()

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
                    now,
                    now,
                    creator["id"],
                ),
            )

            connection.commit()

    except Exception as exc:
        connection.rollback()

        result["status"] = "failed"
        result["error"] = (
            f"{type(exc).__name__}: {exc}"
        )

        if not dry_run:
            now = iso_now()

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
                    now,
                    result["error"],
                    now,
                    creator["id"],
                ),
            )

            connection.commit()

    return result


def save_report(
    report: dict[str, Any],
) -> Path:
    RUN_LOG_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    path = RUN_LOG_DIR / (
        f"{report['run_id']}.json"
    )

    temporary = path.with_suffix(
        ".json.tmp"
    )

    temporary.write_text(
        json.dumps(
            report,
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )

    os.replace(
        temporary,
        path,
    )

    return path


def create_run(
    connection: sqlite3.Connection,
    run_id: str,
    started_at: str,
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
            run_id,
            started_at,
        ),
    )

    connection.commit()


def finish_run(
    connection: sqlite3.Connection,
    report: dict[str, Any],
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
            report["finished_at"],
            report["status"],
            report["creators_scanned"],
            report["videos_queued"],
            len(report["errors"]),
            report["videos_deferred"],
            (
                json.dumps(
                    report["errors"],
                    ensure_ascii=False,
                )
                if report["errors"]
                else None
            ),
            report["run_id"],
        ),
    )

    connection.commit()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Scan Instagram Reels with gallery-dl "
            "and queue new videos in SQLite."
        )
    )

    parser.add_argument(
        "--creator",
        help="Scan one configured creator.",
    )

    parser.add_argument(
        "--scan-limit",
        type=int,
        default=50,
    )

    auth_group = parser.add_mutually_exclusive_group()

    auth_group.add_argument(
        "--cookies-file",
        default=os.environ.get(
            "INSTAGRAM_COOKIES_FILE",
            str(DEFAULT_COOKIE_FILE),
        ),
        help=(
            "Netscape-format Instagram cookie file. "
            "Used by default."
        ),
    )

    auth_group.add_argument(
        "--cookies-browser",
        default=None,
        help=(
            "Explicit browser-cookie fallback, for example "
            "chrome/instagram.com."
        ),
    )

    parser.add_argument(
        "--force-ipv4",
        action="store_true",
    )

    parser.add_argument(
        "--dry-run",
        action="store_true",
    )

    return parser


def main() -> int:
    args = build_parser().parse_args()

    if not DB_PATH.exists():
        print(
            f"ERROR: Database not found: {DB_PATH}",
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
        utc_now().strftime(
            "%Y%m%dT%H%M%SZ"
        )
        + "-"
        + uuid.uuid4().hex[:8]
    )

    owner = (
        f"{socket.gethostname()}:"
        f"{os.getpid()}:{run_id}"
    )

    report: dict[str, Any] = {
        "run_id": run_id,
        "backend": "gallery-dl",
        "started_at": iso_now(),
        "finished_at": None,
        "status": "running",
        "dry_run": args.dry_run,
        "auth_mode": (
            "browser"
            if args.cookies_browser
            else "cookie_file"
        ),
        "cookies_file": (
            None
            if args.cookies_browser
            else str(Path(args.cookies_file).expanduser())
        ),
        "cookies_browser": args.cookies_browser,
        "scan_limit": args.scan_limit,
        "creators": [],
        "creators_scanned": 0,
        "videos_scanned": 0,
        "videos_queued": 0,
        "videos_known": 0,
        "videos_deferred": 0,
        "errors": [],
    }

    connection = connect()
    lock_acquired = False

    try:
        creators = load_creators(
            connection,
            args.creator,
        )

        if not creators:
            report["status"] = "completed"
            report["finished_at"] = iso_now()

            path = save_report(report)

            print("No enabled creators to scan.")
            print(f"Report: {path}")

            return 0

        acquire_lock(
            connection,
            owner,
        )

        lock_acquired = True

        if not args.dry_run:
            create_run(
                connection,
                run_id,
                report["started_at"],
            )

        for creator in creators:
            result = scan_creator(
                connection=connection,
                creator=creator,
                scan_limit=args.scan_limit,
                cookies_file=args.cookies_file,
                cookies_browser=args.cookies_browser,
                force_ipv4=args.force_ipv4,
                dry_run=args.dry_run,
            )

            report["creators"].append(
                result
            )

            report["creators_scanned"] += 1
            report["videos_scanned"] += (
                result["scanned"]
            )
            report["videos_queued"] += (
                result["queued"]
            )
            report["videos_known"] += (
                result["known"]
            )
            report["videos_deferred"] += (
                result["deferred"]
            )

            if result["error"]:
                report["errors"].append(
                    f"{result['username']}: "
                    f"{result['error']}"
                )

        report["finished_at"] = iso_now()

        report["status"] = (
            "completed_with_errors"
            if report["errors"]
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
            f"SCAN_{report['status'].upper()}"
        )

        print(
            f"run_id={report['run_id']}"
        )

        print(
            f"videos_scanned="
            f"{report['videos_scanned']}"
        )

        print(
            f"videos_queued="
            f"{report['videos_queued']}"
        )

        print(
            f"videos_known="
            f"{report['videos_known']}"
        )

        print(
            f"videos_deferred="
            f"{report['videos_deferred']}"
        )

        print(
            f"errors={len(report['errors'])}"
        )

        print(
            f"report={report_path}"
        )

        return (
            0
            if not report["errors"]
            else 2
        )

    except Exception as exc:
        connection.rollback()

        report["status"] = "failed"
        report["finished_at"] = iso_now()

        report["errors"].append(
            f"{type(exc).__name__}: {exc}"
        )

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
                    "WARNING: Could not release lock: "
                    f"{exc}",
                    file=sys.stderr,
                )

        connection.close()


if __name__ == "__main__":
    raise SystemExit(main())
