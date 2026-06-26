#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import sqlite3
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from media2md_paths import command_path
ROOT = Path(__file__).resolve().parents[1]
DB_PATH = ROOT / "data" / "state.db"
COOKIE_FILE = ROOT / "data" / "secrets" / "instagram-cookies.txt"

PROFILE_RE = re.compile(
    r"https?://(?:www\.)?instagram\.com/([A-Za-z0-9._]+)/?",
    re.IGNORECASE,
)
USERNAME_RE = re.compile(r"^[A-Za-z0-9._]+$")


def normalize_creator(value: str) -> str:
    text = value.strip()
    match = PROFILE_RE.match(text)

    if match:
        username = match.group(1)
    else:
        username = text.lstrip("@")

    if username.lower() in {
        "reel",
        "reels",
        "p",
        "tv",
        "explore",
        "accounts",
    }:
        raise RuntimeError(
            "A profile username or profile URL is required, not a post URL."
        )

    if not USERNAME_RE.fullmatch(username):
        raise RuntimeError(
            "Unsupported creator identifier. Use a username such as "
            "'heyenzo.exe' or a profile URL."
        )

    return username


def gallery_dl_path() -> str:
    executable = command_path("gallery-dl")
    if executable:
        return executable

    raise RuntimeError("gallery-dl executable was not found.")


def parse_date(value: Any) -> datetime:
    if not value:
        return datetime.min.replace(tzinfo=timezone.utc)

    text = str(value).strip()

    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        try:
            parsed = datetime.strptime(
                text,
                "%Y-%m-%d %H:%M:%S",
            )
        except ValueError:
            return datetime.min.replace(tzinfo=timezone.utc)

    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)

    return parsed.astimezone(timezone.utc)


def normalize_date(value: Any) -> str | None:
    parsed = parse_date(value)
    if parsed.year == 1:
        return None
    return parsed.isoformat(timespec="seconds")


def fetch_reels(
    username: str,
    cookies_file: Path,
    max_reels: int,
) -> list[dict[str, Any]]:
    if not cookies_file.is_file():
        raise RuntimeError(f"Cookie file not found: {cookies_file}")

    command = [
        gallery_dl_path(),
        "--cookies",
        str(cookies_file),
        "--resolve-json",
        "--post-range",
        f"1-{max_reels}",
        "-o",
        f"extractor.instagram.max-posts={max_reels}",
        f"https://www.instagram.com/{username}/reels/",
    ]

    result = subprocess.run(
        command,
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=1800,
        check=False,
    )

    if result.returncode != 0:
        raise RuntimeError(
            "gallery-dl profile inventory failed: "
            f"{result.stderr.strip()[-3000:] or 'unknown error'}"
        )

    try:
        payload = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise RuntimeError(
            f"gallery-dl returned invalid JSON: {exc}"
        ) from exc

    reels: dict[str, dict[str, Any]] = {}

    if not isinstance(payload, list):
        raise RuntimeError("gallery-dl returned an unexpected JSON root.")

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
        if not shortcode:
            continue

        owner = (
            metadata.get("username")
            or (metadata.get("owner") or {}).get("username")
            or (metadata.get("user") or {}).get("username")
        )

        if owner and str(owner).lower() != username.lower():
            continue

        reel = {
            "shortcode": str(shortcode),
            "published_at": normalize_date(
                metadata.get("post_date")
                or metadata.get("date")
            ),
            "source_url": (
                f"https://www.instagram.com/reel/{shortcode}/"
            ),
            "caption": str(
                metadata.get("description") or ""
            ),
        }

        existing = reels.get(str(shortcode))
        if (
            existing is None
            or parse_date(reel["published_at"])
            > parse_date(existing["published_at"])
        ):
            reels[str(shortcode)] = reel

    return sorted(
        reels.values(),
        key=lambda item: (
            parse_date(item["published_at"]),
            item["shortcode"],
        ),
        reverse=True,
    )


def markdown_state(relative: str | None, expected_hash: str | None) -> dict[str, Any]:
    if not relative:
        return {
            "exists": False,
            "hash_matches": None,
        }

    path = (ROOT / relative).resolve()
    exists = path.is_file()

    if not exists:
        return {
            "exists": False,
            "hash_matches": False,
        }

    digest = hashlib.sha256(path.read_bytes()).hexdigest()

    return {
        "exists": True,
        "hash_matches": digest == (expected_hash or ""),
    }


def save_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    os.replace(temporary, path)


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Fetch a creator's currently accessible Reels and compare them "
            "with SQLite and Markdown storage."
        )
    )
    parser.add_argument(
        "creator",
        help="Instagram username or profile URL.",
    )
    parser.add_argument(
        "--cookies-file",
        type=Path,
        default=COOKIE_FILE,
    )
    parser.add_argument(
        "--max-reels",
        type=int,
        default=500,
        help=(
            "Maximum number of accessible Reels to inspect. "
            "If this limit is reached, the account total is a lower bound."
        ),
    )
    parser.add_argument(
        "--show-items",
        action="store_true",
    )
    parser.add_argument(
        "--json-output",
        type=Path,
    )
    args = parser.parse_args()

    if not 1 <= args.max_reels <= 5000:
        raise RuntimeError("--max-reels must be between 1 and 5000.")

    username = normalize_creator(args.creator)
    cookies_file = args.cookies_file.expanduser().resolve()
    reels = fetch_reels(username, cookies_file, args.max_reels)
    accessible_by_shortcode = {
        item["shortcode"]: item for item in reels
    }

    connection = sqlite3.connect(DB_PATH, timeout=30)
    connection.row_factory = sqlite3.Row

    try:
        creator_row = connection.execute(
            """
            SELECT id, username, enabled
            FROM creators
            WHERE username = ? COLLATE NOCASE
            """,
            (username,),
        ).fetchone()

        db_rows = []
        if creator_row:
            db_rows = connection.execute(
                """
                SELECT
                    shortcode,
                    status,
                    attempt_count,
                    markdown_path,
                    markdown_sha256,
                    published_at,
                    last_error
                FROM videos
                WHERE creator_id = ?
                ORDER BY published_at DESC, id DESC
                """,
                (creator_row["id"],),
            ).fetchall()
    finally:
        connection.close()

    tracked = {
        row["shortcode"]: row for row in db_rows
    }

    accessible_shortcodes = set(accessible_by_shortcode)
    tracked_shortcodes = set(tracked)

    missing_from_system = sorted(
        accessible_shortcodes - tracked_shortcodes,
        key=lambda shortcode: parse_date(
            accessible_by_shortcode[shortcode]["published_at"]
        ),
        reverse=True,
    )

    accessible_tracked = accessible_shortcodes & tracked_shortcodes
    status_counts: dict[str, int] = {}
    completed_with_file = 0
    completed_missing_file = 0

    for shortcode in accessible_tracked:
        row = tracked[shortcode]
        status = row["status"]
        status_counts[status] = status_counts.get(status, 0) + 1

        if status == "completed":
            state = markdown_state(
                row["markdown_path"],
                row["markdown_sha256"],
            )
            if state["exists"] and state["hash_matches"]:
                completed_with_file += 1
            else:
                completed_missing_file += 1

    tracked_not_in_current_fetch = sorted(
        tracked_shortcodes - accessible_shortcodes
    )

    limit_reached = len(reels) >= args.max_reels

    report = {
        "type": "creator_inventory",
        "creator": username,
        "profile_url": f"https://www.instagram.com/{username}/",
        "generated_at": datetime.now(timezone.utc).isoformat(
            timespec="seconds"
        ),
        "max_reels": args.max_reels,
        "limit_reached": limit_reached,
        "account_total_is_exact": not limit_reached,
        "creator_configured": bool(creator_row),
        "creator_enabled": (
            bool(creator_row["enabled"])
            if creator_row
            else None
        ),
        "counts": {
            "accessible_reels": len(reels),
            "tracked_accessible": len(accessible_tracked),
            "not_tracked": len(missing_from_system),
            "completed_with_markdown": completed_with_file,
            "completed_but_markdown_missing_or_changed": (
                completed_missing_file
            ),
            "pending_or_retry_or_other": (
                len(accessible_tracked)
                - completed_with_file
                - completed_missing_file
            ),
            "tracked_not_in_current_fetch": (
                len(tracked_not_in_current_fetch)
            ),
            "all_sqlite_rows_for_creator": len(db_rows),
        },
        "status_counts_for_accessible_tracked": status_counts,
        "missing_from_system": [
            accessible_by_shortcode[shortcode]
            for shortcode in missing_from_system
        ],
        "tracked_not_in_current_fetch": (
            tracked_not_in_current_fetch
        ),
    }

    print("CREATOR_INVENTORY")
    print(f"creator={username}")
    print(f"profile_url={report['profile_url']}")
    print(f"creator_configured={str(report['creator_configured']).lower()}")
    print(f"creator_enabled={report['creator_enabled']}")
    print(f"accessible_reels={len(reels)}")
    print(f"account_total_is_exact={str(not limit_reached).lower()}")
    if limit_reached:
        print(
            f"accessible_total_note=at_least_{len(reels)}"
        )
    print(f"tracked_accessible={len(accessible_tracked)}")
    print(f"not_tracked={len(missing_from_system)}")
    print(f"completed_with_markdown={completed_with_file}")
    print(
        "completed_but_markdown_missing_or_changed="
        f"{completed_missing_file}"
    )
    print(
        "pending_or_retry_or_other="
        f"{report['counts']['pending_or_retry_or_other']}"
    )
    print(
        "all_sqlite_rows_for_creator="
        f"{len(db_rows)}"
    )
    print(
        "tracked_not_in_current_fetch="
        f"{len(tracked_not_in_current_fetch)}"
    )

    if args.show_items:
        print("\nNOT_TRACKED")
        for item in report["missing_from_system"]:
            print(
                f"{item['published_at'] or '-'} | "
                f"{item['shortcode']} | {item['source_url']}"
            )

        print("\nTRACKED_ACCESSIBLE")
        for reel in reels:
            shortcode = reel["shortcode"]
            if shortcode not in tracked:
                continue
            row = tracked[shortcode]
            print(
                f"{reel['published_at'] or '-'} | "
                f"{shortcode} | {row['status']} | "
                f"{row['markdown_path'] or '-'}"
            )

        print("\nTRACKED_NOT_IN_CURRENT_FETCH")
        for shortcode in tracked_not_in_current_fetch:
            row = tracked[shortcode]
            print(
                f"{row['published_at'] or '-'} | "
                f"{shortcode} | {row['status']}"
            )

    if args.json_output:
        output = args.json_output
        if not output.is_absolute():
            output = ROOT / output
        save_json(output, report)
        print(f"\nreport={output}")

    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (
        RuntimeError,
        sqlite3.Error,
        OSError,
        subprocess.SubprocessError,
    ) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise SystemExit(1)
