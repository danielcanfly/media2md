#!/usr/bin/env python3
from __future__ import annotations

import argparse
import fcntl
import hashlib
import json
import os
import re
import shutil
import sqlite3
import subprocess
import sys
import tempfile
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml
from media2md_paths import command_path


ROOT = Path(__file__).resolve().parents[1]
DB_PATH = ROOT / "data" / "state.db"
CONFIG_PATH = ROOT / "config" / "creators.yaml"
CONFIG_BACKUP_DIR = ROOT / "config" / "backups"
DB_BACKUP_DIR = ROOT / "data" / "backups"
COOKIE_FILE = ROOT / "data" / "secrets" / "instagram-cookies.txt"
MARKDOWN_DIR = ROOT / "markdown"
QUARANTINE_DIR = ROOT / "data" / "quarantine" / "deleted-markdown"
PIPELINE_LOCK_PATH = ROOT / "logs" / "pipeline.lock"

INSTAGRAM_URL_RE = re.compile(
    r"https?://(?:www\.)?instagram\.com/"
    r"(?:reel|reels|p|tv)/([A-Za-z0-9_-]+)",
    re.IGNORECASE,
)

ACTIVE_STATUSES = {
    "downloading",
    "downloaded",
    "transcribing",
    "transcribed",
    "rendering",
    "validating",
    "cleaning",
}


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def iso_now() -> str:
    return utc_now().isoformat(timespec="seconds")


def timestamp() -> str:
    return utc_now().strftime("%Y%m%dT%H%M%SZ")


def connect() -> sqlite3.Connection:
    connection = sqlite3.connect(DB_PATH, timeout=30)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    connection.execute("PRAGMA journal_mode = WAL")
    return connection


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def backup_database(connection: sqlite3.Connection, label: str) -> Path:
    DB_BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    destination_path = DB_BACKUP_DIR / f"state-{label}-{timestamp()}.db"
    destination = sqlite3.connect(destination_path)
    try:
        connection.backup(destination)
    finally:
        destination.close()
    return destination_path


def backup_config() -> Path:
    CONFIG_BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    destination = CONFIG_BACKUP_DIR / (
        f"creators-before-single-import-{timestamp()}.yaml"
    )
    shutil.copy2(CONFIG_PATH, destination)
    return destination


@contextmanager
def require_pipeline_idle():
    PIPELINE_LOCK_PATH.parent.mkdir(parents=True, exist_ok=True)
    with PIPELINE_LOCK_PATH.open("a+", encoding="utf-8") as handle:
        try:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise RuntimeError(
                "The full pipeline is currently running. Try again after it finishes."
            ) from exc
        try:
            yield
        finally:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def ensure_no_active_video(connection: sqlite3.Connection, video_id: int) -> None:
    row = connection.execute(
        "SELECT status FROM videos WHERE id = ?",
        (video_id,),
    ).fetchone()
    if row and row["status"] in ACTIVE_STATUSES:
        raise RuntimeError(
            f"Video is currently active: status={row['status']}"
        )


def parse_shortcode(url: str) -> str:
    match = INSTAGRAM_URL_RE.search(url)
    if not match:
        raise RuntimeError(
            "Unsupported Instagram URL. Expected /reel/<shortcode>/, "
            "/p/<shortcode>/, or /tv/<shortcode>/."
        )
    return match.group(1)


def gallery_dl_path() -> str:
    candidate = command_path("gallery-dl")
    if candidate:
        return candidate
    raise RuntimeError("gallery-dl executable was not found.")


def parse_gallery_metadata(payload: Any, expected_shortcode: str) -> dict[str, Any]:
    if not isinstance(payload, list):
        raise RuntimeError("gallery-dl returned an unexpected JSON root.")

    candidates: list[dict[str, Any]] = []
    for event in payload:
        if not (
            isinstance(event, list)
            and len(event) >= 3
            and isinstance(event[2], dict)
        ):
            continue
        metadata = event[2]
        shortcode = (
            metadata.get("post_shortcode")
            or metadata.get("shortcode")
        )
        if shortcode == expected_shortcode:
            candidates.append(metadata)

    if not candidates:
        raise RuntimeError(
            f"No metadata event was found for shortcode {expected_shortcode}."
        )

    metadata = max(
        candidates,
        key=lambda item: (
            bool(item.get("description")),
            bool(item.get("username")),
            len(item),
        ),
    )

    username = (
        metadata.get("username")
        or (metadata.get("owner") or {}).get("username")
        or (metadata.get("user") or {}).get("username")
    )
    if not username:
        raise RuntimeError("Creator username is missing from Instagram metadata.")

    published_at = metadata.get("post_date") or metadata.get("date")
    if published_at:
        published_at = str(published_at).strip()
        if "T" not in published_at and len(published_at) >= 19:
            published_at = published_at.replace(" ", "T", 1) + "+00:00"

    return {
        "creator": str(username).lstrip("@"),
        "shortcode": expected_shortcode,
        "source_url": (
            f"https://www.instagram.com/reel/{expected_shortcode}/"
        ),
        "published_at": published_at,
        "caption": str(metadata.get("description") or ""),
        "media_id": str(
            metadata.get("media_id")
            or metadata.get("post_id")
            or ""
        ),
    }


def fetch_single_metadata(url: str, cookies_file: Path) -> dict[str, Any]:
    shortcode = parse_shortcode(url)

    if not cookies_file.is_file():
        raise RuntimeError(f"Cookie file not found: {cookies_file}")

    command = [
        gallery_dl_path(),
        "--cookies",
        str(cookies_file),
        "--resolve-json",
        url,
    ]
    result = subprocess.run(
        command,
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=300,
        check=False,
    )

    if result.returncode != 0:
        error = result.stderr.strip()[-3000:]
        raise RuntimeError(
            "gallery-dl could not read the Instagram post: "
            f"{error or 'unknown error'}"
        )

    try:
        payload = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise RuntimeError(
            f"gallery-dl returned invalid JSON: {exc}"
        ) from exc

    return parse_gallery_metadata(payload, shortcode)


def load_creator_config() -> tuple[Any, list[dict[str, Any]]]:
    data = yaml.safe_load(CONFIG_PATH.read_text(encoding="utf-8"))

    if isinstance(data, dict) and isinstance(data.get("creators"), list):
        return data, data["creators"]

    if isinstance(data, list):
        return data, data

    raise RuntimeError(
        "Unsupported creators.yaml structure. Expected a list or "
        "a mapping with a 'creators' list."
    )


def write_yaml_atomic(data: Any) -> None:
    CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary_name = tempfile.mkstemp(
        prefix="creators.",
        suffix=".yaml.tmp",
        dir=CONFIG_PATH.parent,
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            yaml.safe_dump(
                data,
                handle,
                allow_unicode=True,
                sort_keys=False,
            )
        os.replace(temporary, CONFIG_PATH)
    finally:
        temporary.unlink(missing_ok=True)


def ensure_creator_configured(
    connection: sqlite3.Connection,
    username: str,
    auto_add: bool,
) -> sqlite3.Row:
    row = connection.execute(
        """
        SELECT *
        FROM creators
        WHERE username = ? COLLATE NOCASE
        """,
        (username,),
    ).fetchone()
    if row:
        return row

    if not auto_add:
        raise RuntimeError(
            f"Creator @{username} is not configured. "
            "Use --auto-add-creator or add it with manage_creators.py."
        )

    data, creators = load_creator_config()
    for item in creators:
        if (
            isinstance(item, dict)
            and str(item.get("username", "")).lower() == username.lower()
        ):
            break
    else:
        backup = backup_config()
        creators.append(
            {
                "username": username,
                "enabled": False,
                "scan_reels": False,
                "language": "auto",
                "max_new_per_run": 10,
                "notes": "Auto-added for a single-video import.",
            }
        )
        write_yaml_atomic(data)
        print(f"CREATOR_CONFIG_BACKUP={backup.relative_to(ROOT)}")
        print(f"CREATOR_AUTO_ADDED=@{username}")

    sync = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "init_system.py")],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    if sync.returncode != 0:
        raise RuntimeError(
            "Creator config was updated, but init_system.py could not sync it: "
            f"{(sync.stdout + sync.stderr)[-3000:]}"
        )

    row = connection.execute(
        """
        SELECT *
        FROM creators
        WHERE username = ? COLLATE NOCASE
        """,
        (username,),
    ).fetchone()
    if not row:
        raise RuntimeError(
            f"Creator @{username} was not created in SQLite after config sync."
        )
    return row


def find_video(
    connection: sqlite3.Connection,
    shortcode: str,
    creator: str | None = None,
) -> sqlite3.Row:
    parameters: list[Any] = [shortcode]
    creator_filter = ""
    if creator:
        creator_filter = "AND c.username = ? COLLATE NOCASE"
        parameters.append(creator.lstrip("@"))

    rows = connection.execute(
        f"""
        SELECT v.*, c.username
        FROM videos AS v
        JOIN creators AS c
          ON c.id = v.creator_id
        WHERE v.shortcode = ?
        {creator_filter}
        """,
        parameters,
    ).fetchall()

    if not rows:
        raise RuntimeError(f"Video not found: {shortcode}")
    if len(rows) > 1:
        raise RuntimeError(
            "Multiple records matched. Supply --creator to disambiguate."
        )
    return rows[0]


def safe_markdown_path(relative: str | None) -> Path | None:
    if not relative:
        return None
    path = (ROOT / relative).resolve()
    try:
        path.relative_to(MARKDOWN_DIR.resolve())
    except ValueError as exc:
        raise RuntimeError(
            f"Refusing to delete a path outside markdown/: {path}"
        ) from exc
    return path


def command_add(args: argparse.Namespace) -> int:
    cookies_file = args.cookies_file.expanduser().resolve()
    metadata = fetch_single_metadata(args.url, cookies_file)

    with require_pipeline_idle():
        connection = connect()
        try:
            creator = ensure_creator_configured(
                connection,
                metadata["creator"],
                args.auto_add_creator,
            )

            existing = connection.execute(
                """
                SELECT v.*, c.username
                FROM videos AS v
                JOIN creators AS c
                  ON c.id = v.creator_id
                WHERE v.creator_id = ?
                  AND v.shortcode = ?
                """,
                (creator["id"], metadata["shortcode"]),
            ).fetchone()

            if existing:
                print("VIDEO_ALREADY_TRACKED")
                print(f"creator={existing['username']}")
                print(f"shortcode={existing['shortcode']}")
                print(f"status={existing['status']}")
                print(f"markdown_path={existing['markdown_path'] or '-'}")

                if args.process_now and existing["status"] in {
                    "retry_wait",
                    "failed",
                }:
                    connection.execute(
                        """
                        UPDATE videos
                        SET status = 'pending',
                            next_retry_at = NULL,
                            last_error = NULL,
                            updated_at = ?
                        WHERE id = ?
                        """,
                        (iso_now(), existing["id"]),
                    )
                    connection.commit()
                elif args.process_now and existing["status"] == "skipped":
                    raise RuntimeError(
                        "This video is intentionally skipped. "
                        "Use the restore command before processing it again."
                    )
                elif args.process_now and existing["status"] == "completed":
                    print("PROCESS_SKIPPED_ALREADY_COMPLETED")
                    return 0
            else:
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
                    VALUES (?, ?, ?, ?, ?, ?, 'pending', 0, ?, ?)
                    """,
                    (
                        creator["id"],
                        metadata["shortcode"],
                        metadata["source_url"],
                        metadata["published_at"],
                        metadata["caption"],
                        now,
                        now,
                        now,
                    ),
                )
                connection.commit()
                print("VIDEO_ENQUEUED")
                print(f"creator={metadata['creator']}")
                print(f"shortcode={metadata['shortcode']}")
                print("status=pending")
        finally:
            connection.close()

    if args.process_now:
        command = [
            sys.executable,
            str(ROOT / "scripts" / "process_worker.py"),
            "--shortcode",
            metadata["shortcode"],
            "--limit",
            "1",
            "--cookies-file",
            str(cookies_file),
        ]
        result = subprocess.run(command, cwd=ROOT, check=False)
        return result.returncode

    return 0


def command_show(args: argparse.Namespace) -> int:
    connection = connect()
    try:
        row = find_video(connection, args.shortcode, args.creator)
        path = safe_markdown_path(row["markdown_path"])
        exists = bool(path and path.is_file())
        actual_hash = sha256_file(path) if exists and path else None

        print(f"creator={row['username']}")
        print(f"shortcode={row['shortcode']}")
        print(f"status={row['status']}")
        print(f"attempt_count={row['attempt_count']}")
        print(f"markdown_path={row['markdown_path'] or '-'}")
        print(f"markdown_exists={str(exists).lower()}")
        print(
            "hash_matches="
            + (
                str(actual_hash == row["markdown_sha256"]).lower()
                if actual_hash
                else "-"
            )
        )
        print(f"last_error={row['last_error'] or '-'}")
        return 0
    finally:
        connection.close()


def command_list(args: argparse.Namespace) -> int:
    connection = connect()
    try:
        filters: list[str] = []
        parameters: list[Any] = []
        if args.status:
            filters.append("v.status = ?")
            parameters.append(args.status)
        if args.creator:
            filters.append("c.username = ? COLLATE NOCASE")
            parameters.append(args.creator.lstrip("@"))

        where = f"WHERE {' AND '.join(filters)}" if filters else ""
        rows = connection.execute(
            f"""
            SELECT
                c.username,
                v.shortcode,
                v.published_at,
                v.status,
                v.attempt_count,
                v.markdown_path
            FROM videos AS v
            JOIN creators AS c
              ON c.id = v.creator_id
            {where}
            ORDER BY v.published_at DESC, v.id DESC
            """,
            parameters,
        ).fetchall()

        print(
            "CREATOR | SHORTCODE | STATUS | ATTEMPTS | "
            "MARKDOWN_EXISTS | MARKDOWN_PATH"
        )
        print("-" * 140)
        for row in rows:
            path = safe_markdown_path(row["markdown_path"])
            exists = bool(path and path.is_file())
            print(
                f"{row['username']} | {row['shortcode']} | "
                f"{row['status']} | {row['attempt_count']} | "
                f"{str(exists).lower()} | {row['markdown_path'] or '-'}"
            )
        print(f"\nTOTAL={len(rows)}")
        return 0
    finally:
        connection.close()


def move_to_quarantine(path: Path, shortcode: str) -> Path:
    destination_dir = QUARANTINE_DIR / timestamp()
    destination_dir.mkdir(parents=True, exist_ok=True)
    destination = destination_dir / f"{shortcode}.md"
    os.replace(path, destination)
    return destination


def command_delete(args: argparse.Namespace) -> int:
    with require_pipeline_idle():
        connection = connect()
        quarantined: Path | None = None
        original_path: Path | None = None

        try:
            row = find_video(connection, args.shortcode, args.creator)
            ensure_no_active_video(connection, row["id"])

            if args.mode == "purge" and not args.yes:
                raise RuntimeError(
                    "Purge permanently removes the SQLite record. "
                    "Run again with --yes."
                )

            backup = backup_database(connection, "before-video-delete")
            original_path = safe_markdown_path(row["markdown_path"])

            if original_path and original_path.is_file():
                quarantined = move_to_quarantine(
                    original_path,
                    row["shortcode"],
                )

            connection.execute("BEGIN IMMEDIATE")
            now = iso_now()
            reason = args.reason.strip() or "No reason supplied"

            if args.mode == "keep-record":
                connection.execute(
                    """
                    UPDATE videos
                    SET status = 'skipped',
                        markdown_path = NULL,
                        markdown_sha256 = NULL,
                        completed_at = NULL,
                        next_retry_at = NULL,
                        last_error = ?,
                        updated_at = ?
                    WHERE id = ?
                    """,
                    (
                        f"Artifact intentionally deleted at {now}. "
                        f"Reason: {reason}",
                        now,
                        row["id"],
                    ),
                )

            elif args.mode == "requeue":
                connection.execute(
                    """
                    UPDATE videos
                    SET status = 'pending',
                        markdown_path = NULL,
                        markdown_sha256 = NULL,
                        completed_at = NULL,
                        next_retry_at = NULL,
                        last_error = NULL,
                        updated_at = ?
                    WHERE id = ?
                    """,
                    (now, row["id"]),
                )

            elif args.mode == "purge":
                connection.execute(
                    "DELETE FROM attempts WHERE video_id = ?",
                    (row["id"],),
                )
                connection.execute(
                    "DELETE FROM videos WHERE id = ?",
                    (row["id"],),
                )

            connection.commit()

            if quarantined:
                quarantined.unlink(missing_ok=True)
                try:
                    quarantined.parent.rmdir()
                except OSError:
                    pass

            if original_path:
                try:
                    original_path.parent.rmdir()
                except OSError:
                    pass

            print("VIDEO_DELETE_COMPLETED")
            print(f"creator={row['username']}")
            print(f"shortcode={row['shortcode']}")
            print(f"mode={args.mode}")
            print(f"database_backup={backup.relative_to(ROOT)}")
            print(
                f"artifact_removed="
                f"{str(bool(original_path and not original_path.exists())).lower()}"
            )
            if args.mode == "keep-record":
                print("new_status=skipped")
            elif args.mode == "requeue":
                print("new_status=pending")
            else:
                print("sqlite_record=purged")
            return 0

        except Exception:
            connection.rollback()
            if quarantined and quarantined.exists() and original_path:
                original_path.parent.mkdir(parents=True, exist_ok=True)
                os.replace(quarantined, original_path)
            raise
        finally:
            connection.close()


def command_restore(args: argparse.Namespace) -> int:
    with require_pipeline_idle():
        connection = connect()
        try:
            row = find_video(connection, args.shortcode, args.creator)
            ensure_no_active_video(connection, row["id"])
            if row["status"] != "skipped":
                raise RuntimeError(
                    f"Only skipped videos can be restored. "
                    f"Current status={row['status']}"
                )

            backup = backup_database(connection, "before-video-restore")
            connection.execute(
                """
                UPDATE videos
                SET status = 'pending',
                    next_retry_at = NULL,
                    last_error = NULL,
                    updated_at = ?
                WHERE id = ?
                """,
                (iso_now(), row["id"]),
            )
            connection.commit()

            print("VIDEO_RESTORED")
            print(f"creator={row['username']}")
            print(f"shortcode={row['shortcode']}")
            print("status=pending")
            print(f"database_backup={backup.relative_to(ROOT)}")
            return 0
        finally:
            connection.close()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Add, inspect, delete, requeue, and restore Instagram videos."
        )
    )
    commands = parser.add_subparsers(dest="command", required=True)

    command = commands.add_parser(
        "add",
        help="Add one Instagram Reel/post URL to SQLite.",
    )
    command.add_argument("--url", required=True)
    command.add_argument(
        "--cookies-file",
        type=Path,
        default=COOKIE_FILE,
    )
    command.add_argument(
        "--auto-add-creator",
        action=argparse.BooleanOptionalAction,
        default=True,
    )
    command.add_argument("--process-now", action="store_true")
    command.set_defaults(function=command_add)

    command = commands.add_parser("show")
    command.add_argument("--shortcode", required=True)
    command.add_argument("--creator")
    command.set_defaults(function=command_show)

    command = commands.add_parser("list")
    command.add_argument("--creator")
    command.add_argument("--status")
    command.set_defaults(function=command_list)

    command = commands.add_parser(
        "delete",
        help=(
            "Delete a Markdown artifact and synchronize SQLite. "
            "Default mode keeps a skipped dedupe record."
        ),
    )
    command.add_argument("--shortcode", required=True)
    command.add_argument("--creator")
    command.add_argument(
        "--mode",
        choices=("keep-record", "requeue", "purge"),
        default="keep-record",
    )
    command.add_argument("--reason", default="")
    command.add_argument("--yes", action="store_true")
    command.set_defaults(function=command_delete)

    command = commands.add_parser(
        "restore",
        help="Restore an intentionally skipped video to pending.",
    )
    command.add_argument("--shortcode", required=True)
    command.add_argument("--creator")
    command.set_defaults(function=command_restore)

    return parser


def main() -> int:
    if not DB_PATH.is_file():
        print(f"ERROR: Database not found: {DB_PATH}", file=sys.stderr)
        return 1

    args = build_parser().parse_args()

    try:
        return args.function(args)
    except (
        RuntimeError,
        sqlite3.Error,
        OSError,
        subprocess.SubprocessError,
        yaml.YAMLError,
    ) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
