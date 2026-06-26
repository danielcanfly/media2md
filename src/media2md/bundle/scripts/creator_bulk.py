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
import time
import uuid
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from media2md_paths import command_path

ROOT = Path(__file__).resolve().parents[1]
DB_PATH = ROOT / "data" / "state.db"
COOKIE_FILE = ROOT / "data" / "secrets" / "instagram-cookies.txt"
CATALOG_DIR = ROOT / "data" / "creator_catalogs"
RUN_DIR = ROOT / "logs" / "runs"
PIPELINE_LOCK_PATH = ROOT / "logs" / "pipeline.lock"
CONFIG_PATH = ROOT / "config" / "social2md.json"
INSTALOADER_HELPER = ROOT / "scripts" / "instagram_instaloader.py"

PROFILE_RE = re.compile(
    r"https?://(?:www\.)?instagram\.com/([A-Za-z0-9._]+)/?",
    re.IGNORECASE,
)
USERNAME_RE = re.compile(r"^[A-Za-z0-9._]+$")
SHORTCODE_RE = re.compile(r"^[A-Za-z0-9_-]+$")

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


def run_id() -> str:
    return (
        utc_now().strftime("%Y%m%dT%H%M%SZ")
        + "-"
        + uuid.uuid4().hex[:8]
    )


def normalize_creator(value: str) -> str:
    text = value.strip()
    match = PROFILE_RE.match(text)

    username = match.group(1) if match else text.lstrip("@")

    if username.lower() in {
        "reel",
        "reels",
        "p",
        "tv",
        "explore",
        "accounts",
    }:
        raise RuntimeError(
            "Expected a profile username or profile URL, not a post URL."
        )

    if not USERNAME_RE.fullmatch(username):
        raise RuntimeError(
            "Unsupported creator identifier. Use a username or profile URL."
        )

    return username


def gallery_dl_path() -> str:
    executable = command_path("gallery-dl")
    if executable:
        return executable

    raise RuntimeError("gallery-dl executable was not found.")



def instagram_backend() -> str:
    try:
        payload = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
        value = payload.get("providers", {}).get("instagram", {}).get("backend", "auto")
    except (FileNotFoundError, json.JSONDecodeError, TypeError):
        value = "auto"
    value = str(value).lower()
    return value if value in {"auto", "gallery-dl", "instaloader"} else "auto"


def fetch_page_instaloader(username: str, start: int, end: int, timeout_seconds: int) -> list[dict[str, Any]]:
    if not INSTALOADER_HELPER.is_file():
        raise RuntimeError(f"Instaloader fallback helper is missing: {INSTALOADER_HELPER}")
    try:
        result = subprocess.run(
            [sys.executable, str(INSTALOADER_HELPER), "catalog", username, "--start", str(start), "--end", str(end)],
            cwd=ROOT, capture_output=True, text=True, timeout=timeout_seconds, check=False,
        )
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError(f"Instaloader page request timed out for post range {start}-{end}.") from exc
    if result.returncode != 0:
        raise RuntimeError("Instaloader page request failed: " + (result.stderr.strip()[-3000:] or "unknown error"))
    try:
        payload = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"Instaloader returned invalid JSON: {exc}") from exc
    if not isinstance(payload, list):
        raise RuntimeError("Instaloader returned an unexpected JSON root.")
    return payload


def connect() -> sqlite3.Connection:
    connection = sqlite3.connect(DB_PATH, timeout=30)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    connection.execute("PRAGMA journal_mode = WAL")
    return connection


@contextmanager
def require_pipeline_idle():
    PIPELINE_LOCK_PATH.parent.mkdir(parents=True, exist_ok=True)
    with PIPELINE_LOCK_PATH.open("a+", encoding="utf-8") as handle:
        try:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise RuntimeError(
                "Another full pipeline or bulk process is already running."
            ) from exc

        handle.seek(0)
        handle.truncate()
        handle.write(
            json.dumps(
                {
                    "pid": os.getpid(),
                    "type": "creator_bulk",
                    "started_at": iso_now(),
                }
            )
        )
        handle.flush()

        try:
            yield
        finally:
            handle.seek(0)
            handle.truncate()
            handle.flush()
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def parse_datetime(value: Any) -> datetime:
    if not value:
        return datetime.min.replace(tzinfo=timezone.utc)

    text = str(value).strip()

    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        try:
            parsed = datetime.strptime(text, "%Y-%m-%d %H:%M:%S")
        except ValueError:
            return datetime.min.replace(tzinfo=timezone.utc)

    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)

    return parsed.astimezone(timezone.utc)


def normalize_datetime(value: Any) -> str | None:
    parsed = parse_datetime(value)
    if parsed.year == 1:
        return None
    return parsed.isoformat(timespec="seconds")


def atomic_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    os.replace(temporary, path)


def catalog_path(username: str) -> Path:
    safe = username.lower()
    return CATALOG_DIR / f"{safe}.json"


def sync_checkpoint_path(username: str) -> Path:
    safe = username.lower()
    return CATALOG_DIR / f"{safe}.sync.json"


def catalog_current_shortcodes(catalog: dict[str, Any]) -> set[str]:
    return {
        str(item.get("shortcode"))
        for item in catalog.get("items", [])
        if item.get("shortcode")
    }


def migrate_catalog(payload: dict[str, Any]) -> dict[str, Any]:
    payload.setdefault("version", 3)
    payload["version"] = max(int(payload.get("version", 1)), 3)
    payload.setdefault("current_total", len(payload.get("items", [])))
    payload.setdefault("current_total_exact", bool(payload.get("complete")))
    payload.setdefault("last_full_sync_at", None)
    payload.setdefault("last_sync_summary", None)
    payload.setdefault("historical_removed", [])
    payload.setdefault("last_quick_sync_at", None)
    payload.setdefault("last_quick_sync_summary", None)
    payload.setdefault("last_sync_mode", "full" if payload.get("last_full_sync_at") else None)
    payload.setdefault("last_exact_total", payload.get("current_total") if payload.get("current_total_exact") else None)
    payload.setdefault("last_exact_at", payload.get("last_full_sync_at"))
    payload.setdefault("quick_added_since_full", [])
    return payload



def new_catalog(username: str, page_size: int, max_reels: int) -> dict[str, Any]:
    return {
        "version": 3,
        "creator": username,
        "profile_url": f"https://www.instagram.com/{username}/reels/",
        "created_at": iso_now(),
        "updated_at": iso_now(),
        "page_size": page_size,
        "max_reels": max_reels,
        "next_start": 1,
        "pages_completed": 0,
        "complete": False,
        "capped": False,
        "last_error": None,
        "current_total": 0,
        "current_total_exact": False,
        "last_full_sync_at": None,
        "last_sync_summary": None,
        "historical_removed": [],
        "last_quick_sync_at": None,
        "last_quick_sync_summary": None,
        "last_sync_mode": None,
        "last_exact_total": None,
        "last_exact_at": None,
        "quick_added_since_full": [],
        "items": [],
    }


def load_catalog(username: str) -> dict[str, Any]:
    path = catalog_path(username)
    if not path.is_file():
        raise RuntimeError(
            f"Catalog not found: {path}. Run the sync command first."
        )

    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("creator", "").lower() != username.lower():
        raise RuntimeError("Catalog creator does not match the requested creator.")
    return migrate_catalog(payload)

def parse_gallery_payload(
    payload: Any,
    username: str,
) -> list[dict[str, Any]]:
    if not isinstance(payload, list):
        raise RuntimeError("gallery-dl returned an unexpected JSON root.")

    items: dict[str, dict[str, Any]] = {}

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
        if not shortcode or not SHORTCODE_RE.fullmatch(str(shortcode)):
            continue

        owner = (
            metadata.get("username")
            or (metadata.get("owner") or {}).get("username")
            or (metadata.get("user") or {}).get("username")
        )
        if owner and str(owner).lower() != username.lower():
            continue

        item = {
            "shortcode": str(shortcode),
            "published_at": normalize_datetime(
                metadata.get("post_date")
                or metadata.get("date")
            ),
            "source_url": (
                f"https://www.instagram.com/reel/{shortcode}/"
            ),
            "caption": str(metadata.get("description") or ""),
            "media_id": str(
                metadata.get("media_id")
                or metadata.get("post_id")
                or ""
            ),
        }

        existing = items.get(item["shortcode"])
        if (
            existing is None
            or parse_datetime(item["published_at"])
            > parse_datetime(existing["published_at"])
        ):
            items[item["shortcode"]] = item

    return sorted(
        items.values(),
        key=lambda item: (
            parse_datetime(item["published_at"]),
            item["shortcode"],
        ),
        reverse=True,
    )


def fetch_page(
    username: str,
    cookies_file: Path,
    start: int,
    end: int,
    timeout_seconds: int,
    force_ipv4: bool,
) -> list[dict[str, Any]]:
    backend = instagram_backend()
    gallery_error: Exception | None = None
    if backend in {"auto", "gallery-dl"}:
        try:
            command = [
                gallery_dl_path(),
                "--cookies", str(cookies_file),
                "--resolve-json",
                "--post-range", f"{start}-{end}",
                "-o", f"extractor.instagram.max-posts={end}",
                "--retries", "5",
                "--http-timeout", "60",
                "--sleep-request", "0.5",
                "--sleep-retries", "10",
                "--sleep-429", "120",
            ]
            if force_ipv4:
                command.append("--force-ipv4")
            command.append(f"https://www.instagram.com/{username}/reels/")
            result = subprocess.run(command, cwd=ROOT, capture_output=True, text=True, timeout=timeout_seconds, check=False)
            if result.returncode != 0:
                raise RuntimeError("gallery-dl page request failed: " + (result.stderr.strip()[-3000:] or "unknown error"))
            payload = json.loads(result.stdout)
            print(f"INSTAGRAM_BACKEND_SELECTED creator={username} backend=gallery-dl", file=sys.stderr, flush=True)
            return parse_gallery_payload(payload, username)
        except (subprocess.TimeoutExpired, json.JSONDecodeError, RuntimeError) as exc:
            gallery_error = exc
            if backend == "gallery-dl":
                raise RuntimeError(str(exc)) from exc
            print(
                "INSTAGRAM_BACKEND_FALLBACK "
                f"creator={username} from=gallery-dl to=instaloader "
                f"reason={type(exc).__name__}",
                file=sys.stderr, flush=True,
            )
    if backend in {"auto", "instaloader"}:
        try:
            items = fetch_page_instaloader(username, start, end, timeout_seconds)
            print(f"INSTAGRAM_BACKEND_SELECTED creator={username} backend=instaloader", file=sys.stderr, flush=True)
            return items
        except Exception as instaloader_error:
            if gallery_error is not None:
                raise RuntimeError(
                    f"Both Instagram backends failed. gallery-dl={gallery_error}; "
                    f"instaloader={instaloader_error}"
                ) from instaloader_error
            raise
    raise RuntimeError(f"Unsupported Instagram backend: {backend}")


def emit_agent_progress(
    *,
    phase: str,
    current: int | None,
    total: int | None,
    percent: float | None,
    creator: str,
    **extra: Any,
) -> None:
    payload = {
        "event": "progress",
        "phase": phase,
        "creator": creator,
        "current": current,
        "total": total,
        "percent": percent,
        "timestamp": iso_now(),
        **extra,
    }
    print(
        "AGENT_PROGRESS "
        + json.dumps(payload, ensure_ascii=False, sort_keys=True),
        flush=True,
    )



def catalog_age_minutes(catalog: dict[str, Any]) -> float | None:
    value = catalog.get("last_full_sync_at")
    if not value:
        return None
    parsed = parse_datetime(value)
    if parsed.year == 1:
        return None
    return max(0.0, (utc_now() - parsed).total_seconds() / 60.0)


def new_sync_checkpoint(
    username: str,
    page_size: int,
    max_reels: int,
) -> dict[str, Any]:
    return {
        "version": 3,
        "type": "creator_full_sync_checkpoint",
        "creator": username,
        "profile_url": f"https://www.instagram.com/{username}/reels/",
        "started_at": iso_now(),
        "updated_at": iso_now(),
        "page_size": page_size,
        "max_reels": max_reels,
        "next_start": 1,
        "pages_completed": 0,
        "complete": False,
        "capped": False,
        "last_error": None,
        "items": [],
    }


def promote_completed_sync(
    *,
    username: str,
    checkpoint: dict[str, Any],
    catalog_file: Path,
    checkpoint_file: Path,
    show_ids: bool,
) -> dict[str, Any]:
    old_catalog: dict[str, Any] | None = None
    if catalog_file.is_file():
        old_catalog = load_catalog(username)

    old_items = {
        item["shortcode"]: item
        for item in (old_catalog or {}).get("items", [])
    }
    new_items = {
        item["shortcode"]: item
        for item in checkpoint.get("items", [])
    }

    added_ids = sorted(
        set(new_items) - set(old_items),
        key=lambda shortcode: (
            parse_datetime(new_items[shortcode].get("published_at")),
            shortcode,
        ),
        reverse=True,
    )
    removed_ids = sorted(
        set(old_items) - set(new_items),
        key=lambda shortcode: (
            parse_datetime(old_items[shortcode].get("published_at")),
            shortcode,
        ),
        reverse=True,
    )

    removed_history = list(
        (old_catalog or {}).get("historical_removed", [])
    )
    known_removed = {
        item.get("shortcode") for item in removed_history
    }
    removed_at = iso_now()

    for shortcode in removed_ids:
        if shortcode in known_removed:
            continue
        removed_history.append(
            {
                **old_items[shortcode],
                "removed_from_current_at": removed_at,
            }
        )

    ordered = sorted(
        new_items.values(),
        key=lambda item: (
            parse_datetime(item.get("published_at")),
            item.get("shortcode", ""),
        ),
        reverse=True,
    )

    previous_total = (
        len(old_items)
        if old_catalog and old_catalog.get("current_total_exact")
        else None
    )
    current_total = len(ordered)
    completed_at = iso_now()

    final_catalog = {
        "version": 3,
        "creator": username,
        "profile_url": f"https://www.instagram.com/{username}/reels/",
        "created_at": (
            (old_catalog or {}).get("created_at")
            or checkpoint.get("started_at")
            or completed_at
        ),
        "updated_at": completed_at,
        "page_size": checkpoint.get("page_size"),
        "max_reels": checkpoint.get("max_reels"),
        "next_start": checkpoint.get("next_start"),
        "pages_completed": checkpoint.get("pages_completed"),
        "complete": True,
        "capped": False,
        "last_error": None,
        "current_total": current_total,
        "current_total_exact": True,
        "last_full_sync_at": completed_at,
        "last_sync_summary": {
            "previous_total": previous_total,
            "current_total": current_total,
            "new_since_last_sync": len(added_ids),
            "removed_since_last_sync": len(removed_ids),
            "added_ids": added_ids,
            "removed_ids": removed_ids,
            "started_at": checkpoint.get("started_at"),
            "completed_at": completed_at,
        },
        "historical_removed": removed_history,
        "last_quick_sync_at": None,
        "last_quick_sync_summary": None,
        "last_sync_mode": "full",
        "last_exact_total": current_total,
        "last_exact_at": completed_at,
        "quick_added_since_full": [],
        "items": ordered,
    }

    atomic_json(catalog_file, final_catalog)
    checkpoint_file.unlink(missing_ok=True)

    newest = ordered[0].get("published_at") if ordered else None
    oldest = ordered[-1].get("published_at") if ordered else None

    print()
    print("CREATOR_SYNC_RESULT")
    print(f"creator={username}")
    print(
        f"previous_current_total="
        f"{previous_total if previous_total is not None else '-'}"
    )
    print(f"current_accessible_total={current_total}")
    print("current_total_is_exact=true")
    print(f"new_since_last_sync={len(added_ids)}")
    print(f"removed_since_last_sync={len(removed_ids)}")
    print(f"current_newest={newest or '-'}")
    print(f"current_oldest={oldest or '-'}")
    print(f"catalog={catalog_file}")

    emit_agent_progress(
        phase="sync_complete",
        current=current_total,
        total=current_total,
        percent=100.0,
        creator=username,
        previous_total=previous_total,
        current_total=current_total,
        new_since_last_sync=len(added_ids),
        removed_since_last_sync=len(removed_ids),
        exact=True,
    )

    if show_ids:
        print("\nADDED_IDS")
        for shortcode in added_ids:
            item = new_items[shortcode]
            print(
                f"{item.get('published_at') or '-'} | "
                f"{shortcode}"
            )

        print("\nREMOVED_IDS")
        for shortcode in removed_ids:
            item = old_items[shortcode]
            print(
                f"{item.get('published_at') or '-'} | "
                f"{shortcode}"
            )

    return final_catalog


def perform_full_sync(
    *,
    username: str,
    cookies_file: Path,
    page_size: int,
    pages_per_run: int,
    max_reels: int,
    page_timeout: int,
    force_ipv4: bool,
    show_ids: bool,
    restart: bool,
    skip_if_fresh_minutes: float = 0.0,
) -> int:
    if not cookies_file.is_file():
        raise RuntimeError(f"Cookie file not found: {cookies_file}")

    CATALOG_DIR.mkdir(parents=True, exist_ok=True)
    catalog_file = catalog_path(username)
    checkpoint_file = sync_checkpoint_path(username)

    if (
        skip_if_fresh_minutes > 0
        and catalog_file.is_file()
        and not checkpoint_file.exists()
    ):
        catalog = load_catalog(username)
        age = catalog_age_minutes(catalog)
        if (
            catalog.get("current_total_exact")
            and age is not None
            and age <= skip_if_fresh_minutes
        ):
            print("CREATOR_AUTO_SYNC_SKIPPED_FRESH")
            print(f"creator={username}")
            print(f"catalog_age_minutes={age:.1f}")
            print(
                f"current_accessible_total="
                f"{len(catalog.get('items', []))}"
            )
            return 0

    if restart:
        checkpoint_file.unlink(missing_ok=True)

    if checkpoint_file.is_file():
        checkpoint = json.loads(
            checkpoint_file.read_text(encoding="utf-8")
        )
        if checkpoint.get("creator", "").lower() != username.lower():
            raise RuntimeError(
                "Sync checkpoint creator does not match the requested creator."
            )
        print("CREATOR_SYNC_RESUMED")
        print(f"creator={username}")
        print(f"cataloged={len(checkpoint.get('items', []))}")
        print(f"next_start={checkpoint.get('next_start', 1)}")
    else:
        checkpoint = new_sync_checkpoint(
            username,
            page_size,
            max_reels,
        )
        atomic_json(checkpoint_file, checkpoint)
        print("CREATOR_SYNC_STARTED")
        print(f"creator={username}")
        print(f"page_size={page_size}")

    existing = {
        item["shortcode"]: item
        for item in checkpoint.get("items", [])
    }
    pages_this_run = 0

    while not checkpoint.get("complete"):
        start = int(checkpoint.get("next_start", 1))

        if start > max_reels:
            checkpoint["capped"] = True
            checkpoint["complete"] = False
            checkpoint["updated_at"] = iso_now()
            atomic_json(checkpoint_file, checkpoint)
            print("CREATOR_SYNC_CAP_REACHED")
            print(f"current_discovered={len(existing)}")
            print("current_total_is_exact=false")
            print(f"checkpoint={checkpoint_file}")
            return 2

        end = min(start + page_size - 1, max_reels)
        page_number = int(checkpoint.get("pages_completed", 0)) + 1

        print(
            f"SYNC_PAGE_START page={page_number} "
            f"range={start}-{end} discovered={len(existing)}",
            flush=True,
        )
        emit_agent_progress(
            phase="sync",
            current=len(existing),
            total=None,
            percent=None,
            creator=username,
            page=page_number,
            range_start=start,
            range_end=end,
            exact=False,
        )

        try:
            page_items = fetch_page(
                username,
                cookies_file,
                start,
                end,
                page_timeout,
                force_ipv4,
            )
        except Exception as exc:
            checkpoint["last_error"] = f"{type(exc).__name__}: {exc}"
            checkpoint["updated_at"] = iso_now()
            atomic_json(checkpoint_file, checkpoint)
            print(f"CREATOR_SYNC_PAGE_FAILED error={exc}", file=sys.stderr)
            print(f"checkpoint={checkpoint_file}")
            return 2

        before_count = len(existing)
        for item in page_items:
            existing[item["shortcode"]] = item

        ordered = sorted(
            existing.values(),
            key=lambda item: (
                parse_datetime(item.get("published_at")),
                item.get("shortcode", ""),
            ),
            reverse=True,
        )

        checkpoint["items"] = ordered
        checkpoint["pages_completed"] = page_number
        checkpoint["next_start"] = end + 1
        checkpoint["last_error"] = None
        checkpoint["updated_at"] = iso_now()

        raw_count = len(page_items)
        new_count = len(existing) - before_count

        if raw_count < page_size:
            checkpoint["complete"] = True
        elif end >= max_reels:
            checkpoint["capped"] = True
            checkpoint["complete"] = False

        atomic_json(checkpoint_file, checkpoint)
        pages_this_run += 1

        newest = page_items[0].get("published_at") if page_items else None
        oldest = page_items[-1].get("published_at") if page_items else None

        print(
            f"SYNC_PAGE_DONE page={page_number} "
            f"fetched={raw_count} new_unique={new_count} "
            f"discovered={len(ordered)} "
            f"newest={newest or '-'} oldest={oldest or '-'}",
            flush=True,
        )
        emit_agent_progress(
            phase="sync",
            current=len(ordered),
            total=(len(ordered) if checkpoint["complete"] else None),
            percent=(100.0 if checkpoint["complete"] else None),
            creator=username,
            page=page_number,
            fetched=raw_count,
            new_unique=new_count,
            complete=bool(checkpoint["complete"]),
            exact=bool(checkpoint["complete"]),
        )

        if checkpoint.get("complete"):
            break
        if checkpoint.get("capped"):
            print("CREATOR_SYNC_CAP_REACHED")
            print(f"current_discovered={len(ordered)}")
            print("current_total_is_exact=false")
            print(f"checkpoint={checkpoint_file}")
            return 2
        if pages_per_run and pages_this_run >= pages_per_run:
            print()
            print("CREATOR_SYNC_CHECKPOINT")
            print(f"creator={username}")
            print(f"current_discovered={len(ordered)}")
            print("current_total_is_exact=false")
            print(f"next_start={checkpoint.get('next_start')}")
            print(f"checkpoint={checkpoint_file}")
            return 0

    promote_completed_sync(
        username=username,
        checkpoint=checkpoint,
        catalog_file=catalog_file,
        checkpoint_file=checkpoint_file,
        show_ids=show_ids,
    )
    return 0



def full_sync_due(
    catalog: dict[str, Any] | None,
    interval_minutes: float,
) -> tuple[bool, str, float | None]:
    if catalog is None:
        return True, "no_catalog", None

    last_full = catalog.get("last_full_sync_at")
    if not last_full:
        return True, "no_full_sync_baseline", None

    age = catalog_age_minutes(catalog)
    if age is None:
        return True, "invalid_full_sync_timestamp", None

    if interval_minutes <= 0:
        return True, "interval_zero", age

    if age >= interval_minutes:
        return True, "full_sync_ttl_expired", age

    return False, "full_sync_snapshot_fresh", age


def next_full_sync_due_at(
    catalog: dict[str, Any],
    interval_minutes: float,
) -> str | None:
    value = catalog.get("last_full_sync_at")
    if not value or interval_minutes <= 0:
        return None
    parsed = parse_datetime(value)
    if parsed.year == 1:
        return None
    return (parsed + timedelta(minutes=interval_minutes)).isoformat(
        timespec="seconds"
    )


def perform_quick_sync(
    *,
    username: str,
    cookies_file: Path,
    quick_size: int,
    page_timeout: int,
    force_ipv4: bool,
    show_ids: bool,
) -> int:
    if not cookies_file.is_file():
        raise RuntimeError(f"Cookie file not found: {cookies_file}")

    catalog_file = catalog_path(username)
    if not catalog_file.is_file():
        raise RuntimeError(
            "Quick sync requires an existing full catalog. "
            "Run the sync command first."
        )

    old_catalog = load_catalog(username)
    old_items = {
        item["shortcode"]: item
        for item in old_catalog.get("items", [])
    }

    # Fetch one extra item. If fewer than quick_size + 1 are returned,
    # the quick request reached the end and is also a complete full snapshot.
    probe_end = quick_size + 1

    print("CREATOR_QUICK_SYNC_STARTED")
    print(f"creator={username}")
    print(f"quick_window={quick_size}")
    print(f"probe_limit={probe_end}")
    print(f"previous_known_total={len(old_items)}")

    emit_agent_progress(
        phase="quick_sync",
        current=0,
        total=1,
        percent=0.0,
        creator=username,
        quick_window=quick_size,
    )

    page_items = fetch_page(
        username,
        cookies_file,
        1,
        probe_end,
        page_timeout,
        force_ipv4,
    )

    # Small accounts are fully covered by this request. Promote the result
    # through the same exact full-sync path so additions and deletions are
    # both reconciled immediately.
    if len(page_items) < probe_end:
        print("QUICK_SYNC_REACHED_ACCOUNT_END")
        print("promoted_to_full_sync=true")
        checkpoint = new_sync_checkpoint(
            username,
            quick_size,
            max(quick_size, len(page_items)),
        )
        checkpoint.update(
            {
                "complete": True,
                "capped": False,
                "pages_completed": 1,
                "next_start": len(page_items) + 1,
                "updated_at": iso_now(),
                "items": page_items,
            }
        )
        return_code_catalog = promote_completed_sync(
            username=username,
            checkpoint=checkpoint,
            catalog_file=catalog_file,
            checkpoint_file=sync_checkpoint_path(username),
            show_ids=show_ids,
        )
        return 0

    quick_items = page_items[:quick_size]
    merged = dict(old_items)
    for item in quick_items:
        merged[item["shortcode"]] = item

    quick_shortcodes = {item["shortcode"] for item in quick_items}
    added_ids = sorted(
        quick_shortcodes - set(old_items),
        key=lambda shortcode: (
            parse_datetime(merged[shortcode].get("published_at")),
            shortcode,
        ),
        reverse=True,
    )

    ordered = sorted(
        merged.values(),
        key=lambda item: (
            parse_datetime(item.get("published_at")),
            item.get("shortcode", ""),
        ),
        reverse=True,
    )

    previous_quick_added = set(
        old_catalog.get("quick_added_since_full", [])
    )
    cumulative_quick_added = sorted(
        previous_quick_added | set(added_ids),
        key=lambda shortcode: (
            parse_datetime(merged[shortcode].get("published_at")),
            shortcode,
        ),
        reverse=True,
    )

    completed_at = iso_now()
    updated = {
        **old_catalog,
        "version": 3,
        "updated_at": completed_at,
        "current_total": len(ordered),
        # Quick sync cannot detect arbitrary old deletions on large accounts.
        "current_total_exact": False,
        "last_quick_sync_at": completed_at,
        "last_quick_sync_summary": {
            "quick_window": quick_size,
            "fetched": len(quick_items),
            "new_since_quick_sync": len(added_ids),
            "added_ids": added_ids,
            "completed_at": completed_at,
        },
        "last_sync_mode": "quick",
        "last_exact_total": (
            old_catalog.get("last_exact_total")
            if old_catalog.get("last_exact_total") is not None
            else (
                old_catalog.get("current_total")
                if old_catalog.get("current_total_exact")
                else None
            )
        ),
        "last_exact_at": (
            old_catalog.get("last_exact_at")
            or old_catalog.get("last_full_sync_at")
        ),
        "quick_added_since_full": cumulative_quick_added,
        "items": ordered,
    }
    atomic_json(catalog_file, updated)

    newest = quick_items[0].get("published_at") if quick_items else None
    oldest = quick_items[-1].get("published_at") if quick_items else None

    print("CREATOR_QUICK_SYNC_RESULT")
    print(f"creator={username}")
    print(f"quick_items_checked={len(quick_items)}")
    print(f"new_since_quick_sync={len(added_ids)}")
    print(f"current_known_total={len(ordered)}")
    print("current_total_is_exact=false")
    print(f"last_exact_total={updated.get('last_exact_total') or '-'}")
    print(f"last_exact_at={updated.get('last_exact_at') or '-'}")
    print(f"quick_newest={newest or '-'}")
    print(f"quick_oldest={oldest or '-'}")
    print("old_deletions_checked=false")
    print(f"catalog={catalog_file}")

    emit_agent_progress(
        phase="quick_sync",
        current=1,
        total=1,
        percent=100.0,
        creator=username,
        quick_window=quick_size,
        quick_items_checked=len(quick_items),
        new_since_quick_sync=len(added_ids),
        current_known_total=len(ordered),
        exact=False,
    )

    if show_ids:
        print("\nQUICK_SYNC_ADDED_IDS")
        for shortcode in added_ids:
            item = merged[shortcode]
            print(
                f"{item.get('published_at') or '-'} | "
                f"{shortcode}"
            )

    return 0


def auto_sync_catalog(
    *,
    username: str,
    cookies_file: Path,
    quick_sync_size: int,
    full_sync_interval_minutes: float,
    full_page_size: int,
    full_max_reels: int,
    page_timeout: int,
    force_ipv4: bool,
    force_full_sync: bool,
    restart_sync: bool,
) -> int:
    catalog: dict[str, Any] | None = None
    catalog_file = catalog_path(username)
    checkpoint_file = sync_checkpoint_path(username)

    if catalog_file.is_file():
        catalog = load_catalog(username)

    due, reason, age = full_sync_due(
        catalog,
        full_sync_interval_minutes,
    )

    if checkpoint_file.is_file():
        due = True
        reason = "resume_incomplete_full_sync"

    if force_full_sync:
        due = True
        reason = "force_full_sync"

    if due:
        print("AUTO_SYNC_DECISION mode=full")
        print(f"reason={reason}")
        print(
            f"last_full_sync_age_minutes="
            f"{f'{age:.1f}' if age is not None else '-'}"
        )
        return perform_full_sync(
            username=username,
            cookies_file=cookies_file,
            page_size=full_page_size,
            pages_per_run=0,
            max_reels=full_max_reels,
            page_timeout=page_timeout,
            force_ipv4=force_ipv4,
            show_ids=False,
            restart=restart_sync,
            skip_if_fresh_minutes=0.0,
        )

    if quick_sync_size > 0:
        print("AUTO_SYNC_DECISION mode=quick")
        print(f"reason={reason}")
        print(f"last_full_sync_age_minutes={age:.1f}")
        print(
            f"next_full_sync_due_at="
            f"{next_full_sync_due_at(catalog or {}, full_sync_interval_minutes) or '-'}"
        )
        return perform_quick_sync(
            username=username,
            cookies_file=cookies_file,
            quick_size=quick_sync_size,
            page_timeout=page_timeout,
            force_ipv4=force_ipv4,
            show_ids=False,
        )

    print("AUTO_SYNC_DECISION mode=local")
    print("reason=quick_sync_disabled_and_full_snapshot_fresh")
    return 0


def command_quick_sync(args: argparse.Namespace) -> int:
    username = normalize_creator(args.creator)
    cookies_file = args.cookies_file.expanduser().resolve()

    with require_pipeline_idle():
        return perform_quick_sync(
            username=username,
            cookies_file=cookies_file,
            quick_size=args.quick_sync_size,
            page_timeout=args.page_timeout,
            force_ipv4=args.force_ipv4,
            show_ids=args.show_ids,
        )

def command_catalog(args: argparse.Namespace) -> int:
    username = normalize_creator(args.creator)
    cookies_file = args.cookies_file.expanduser().resolve()

    with require_pipeline_idle():
        return perform_full_sync(
            username=username,
            cookies_file=cookies_file,
            page_size=args.page_size,
            pages_per_run=args.pages_per_run,
            max_reels=args.max_reels,
            page_timeout=args.page_timeout,
            force_ipv4=args.force_ipv4,
            show_ids=args.show_ids,
            restart=args.refresh,
            skip_if_fresh_minutes=0.0,
        )

def creator_row(connection: sqlite3.Connection, username: str) -> sqlite3.Row:
    row = connection.execute(
        """
        SELECT id, username, enabled
        FROM creators
        WHERE username = ? COLLATE NOCASE
        """,
        (username,),
    ).fetchone()

    if not row:
        raise RuntimeError(
            f"Creator @{username} is not configured. "
            f"Add it with: python scripts/manage_creators.py add {username}"
        )

    if not bool(row["enabled"]):
        raise RuntimeError(
            f"Creator @{username} is disabled. "
            f"Enable it with: python scripts/manage_creators.py enable {username}"
        )

    return row


def load_video_rows(
    connection: sqlite3.Connection,
    creator_id: int,
) -> dict[str, sqlite3.Row]:
    rows = connection.execute(
        """
        SELECT *
        FROM videos
        WHERE creator_id = ?
        """,
        (creator_id,),
    ).fetchall()
    return {row["shortcode"]: row for row in rows}


def markdown_valid(row: sqlite3.Row) -> bool:
    relative = row["markdown_path"]
    expected = row["markdown_sha256"]

    if not relative or not expected:
        return False

    path = (ROOT / relative).resolve()

    try:
        path.relative_to((ROOT / "markdown").resolve())
    except ValueError:
        return False

    if not path.is_file():
        return False

    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    return digest == expected


def queue_item(
    connection: sqlite3.Connection,
    creator_id: int,
    item: dict[str, Any],
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
        VALUES (?, ?, ?, ?, ?, ?, 'pending', 0, ?, ?)
        """,
        (
            creator_id,
            item["shortcode"],
            item["source_url"],
            item["published_at"],
            item.get("caption", ""),
            now,
            now,
            now,
        ),
    )
    connection.commit()



def status_summary(
    catalog_items: list[dict[str, Any]],
    rows: dict[str, sqlite3.Row],
) -> dict[str, Any]:
    completed = 0
    skipped = 0
    pending = 0
    retry_wait = 0
    failed = 0
    active = 0
    untracked = 0
    invalid_completed = 0

    current_shortcodes = {
        item["shortcode"] for item in catalog_items
    }

    for item in catalog_items:
        row = rows.get(item["shortcode"])
        if row is None:
            untracked += 1
            continue

        status = row["status"]

        if status == "completed":
            if markdown_valid(row):
                completed += 1
            else:
                invalid_completed += 1
        elif status == "skipped":
            skipped += 1
        elif status == "pending":
            pending += 1
        elif status == "retry_wait":
            retry_wait += 1
        elif status == "failed":
            failed += 1
        elif status in ACTIVE_STATUSES:
            active += 1
        else:
            failed += 1

    tracked_not_current = sum(
        1 for shortcode in rows
        if shortcode not in current_shortcodes
    )

    remaining = (
        untracked
        + pending
        + retry_wait
        + failed
        + active
        + invalid_completed
    )

    return {
        "catalog_total": len(catalog_items),
        "completed": completed,
        "skipped": skipped,
        "untracked": untracked,
        "pending": pending,
        "retry_wait": retry_wait,
        "failed": failed,
        "active": active,
        "invalid_completed": invalid_completed,
        "remaining": remaining,
        "tracked_not_current": tracked_not_current,
        "historical_tracked": len(rows),
    }

def candidate_items(
    catalog_items: list[dict[str, Any]],
    rows: dict[str, sqlite3.Row],
    *,
    retry_failed: bool,
    oldest_first: bool,
    since: str | None = None,
    until: str | None = None,
    rank_from: int | None = None,
    rank_to: int | None = None,
) -> list[dict[str, Any]]:
    ordered = sorted(
        catalog_items,
        key=lambda item: (
            parse_datetime(item["published_at"]),
            item["shortcode"],
        ),
        reverse=not oldest_first,
    )

    since_dt = parse_datetime(since) if since else None
    until_dt = parse_datetime(until) if until else None

    filtered: list[dict[str, Any]] = []
    for item in ordered:
        published = parse_datetime(item.get("published_at"))
        if since_dt and published < since_dt:
            continue
        if until_dt and published > until_dt:
            continue
        filtered.append(item)

    start = (rank_from - 1) if rank_from else 0
    stop = rank_to if rank_to else None
    ranked = filtered[start:stop]

    candidates: list[dict[str, Any]] = []

    for item in ranked:
        row = rows.get(item["shortcode"])

        if row is None:
            candidates.append(item)
            continue

        status = row["status"]

        if status == "pending":
            candidates.append(item)
        elif status in {"retry_wait", "failed"} and retry_failed:
            candidates.append(item)
        elif status == "completed" and not markdown_valid(row):
            candidates.append(item)

    return candidates


def set_pending_for_retry(
    connection: sqlite3.Connection,
    video_id: int,
) -> None:
    connection.execute(
        """
        UPDATE videos
        SET status = 'pending',
            next_retry_at = NULL,
            last_error = NULL,
            markdown_path = NULL,
            markdown_sha256 = NULL,
            completed_at = NULL,
            updated_at = ?
        WHERE id = ?
        """,
        (iso_now(), video_id),
    )
    connection.commit()


def worker_command(
    shortcode: str,
    cookies_file: Path | None,
    force_ipv4: bool,
) -> list[str]:
    """Build the Instagram worker command without changing the proven default path.

    Media2MD v0.6.x let the worker resolve the managed cookie file itself. Later
    callers always injected ``--cookies-file`` and created a brittle cross-script
    contract. Keep explicit overrides supported, but omit the flag by default so
    the worker follows its long-standing managed-file -> browser fallback order.
    """
    command = [
        sys.executable,
        str(ROOT / "scripts" / "process_worker.py"),
        "--shortcode",
        shortcode,
        "--limit",
        "1",
    ]

    if cookies_file is not None:
        command += ["--cookies-file", str(cookies_file)]
    if force_ipv4:
        command.append("--force-ipv4")

    return command



def command_run(args: argparse.Namespace) -> int:
    username = normalize_creator(args.creator)
    explicit_cookies_file = (
        args.cookies_file.expanduser().resolve() if args.cookies_file is not None else None
    )
    catalog_cookies_file = explicit_cookies_file or COOKIE_FILE

    if not args.no_auto_sync:
        with require_pipeline_idle():
            sync_code = auto_sync_catalog(
                username=username,
                cookies_file=catalog_cookies_file,
                quick_sync_size=(
                    0 if args.no_quick_sync else args.quick_sync_size
                ),
                full_sync_interval_minutes=(
                    args.full_sync_interval_minutes
                ),
                full_page_size=args.sync_page_size,
                full_max_reels=args.sync_max_reels,
                page_timeout=args.sync_page_timeout,
                force_ipv4=args.force_ipv4,
                force_full_sync=args.force_full_sync,
                restart_sync=args.restart_sync,
            )
        if sync_code != 0:
            print(
                "BATCH_NOT_STARTED reason=creator_sync_incomplete_or_failed",
                file=sys.stderr,
            )
            return sync_code

    catalog = load_catalog(username)
    catalog_items = list(catalog.get("items", []))

    if not catalog_items:
        raise RuntimeError("Catalog is empty.")

    if (
        not catalog.get("current_total_exact")
        and not catalog.get("last_full_sync_at")
        and not args.allow_partial_catalog
    ):
        raise RuntimeError(
            "Catalog has no completed full-sync baseline. Complete synchronization "
            "first, or use --allow-partial-catalog when a lower-bound count is acceptable."
        )

    batch_run_id = run_id()
    report_path = RUN_DIR / f"{batch_run_id}-creator-batch.json"
    report: dict[str, Any] = {
        "run_id": batch_run_id,
        "type": "creator_batch",
        "creator": username,
        "started_at": iso_now(),
        "finished_at": None,
        "status": "running",
        "order": "oldest_first" if args.oldest_first else "newest_first",
        "catalog_complete": bool(catalog.get("current_total_exact")),
        "catalog_capped": bool(catalog.get("capped")),
        "catalog_last_full_sync_at": catalog.get("last_full_sync_at"),
        "batch_size_requested": args.batch_size,
        "filters": {
            "since": args.since,
            "until": args.until,
            "rank_from": args.rank_from,
            "rank_to": args.rank_to,
        },
        "selected_count": 0,
        "selected_newest": None,
        "selected_oldest": None,
        "items": [],
        "completed": 0,
        "failed": 0,
        "remaining_after": None,
        "remaining_is_exact": bool(catalog.get("current_total_exact")),
        "last_sync_mode": catalog.get("last_sync_mode"),
        "last_full_sync_at": catalog.get("last_full_sync_at"),
        "last_quick_sync_at": catalog.get("last_quick_sync_at"),
        "errors": [],
    }

    RUN_DIR.mkdir(parents=True, exist_ok=True)

    with require_pipeline_idle():
        connection = connect()
        try:
            creator = creator_row(connection, username)
            rows = load_video_rows(connection, creator["id"])

            candidates = candidate_items(
                catalog_items,
                rows,
                retry_failed=args.retry_failed,
                oldest_first=args.oldest_first,
                since=args.since,
                until=args.until,
                rank_from=args.rank_from,
                rank_to=args.rank_to,
            )
            selected = candidates[: args.batch_size]

            report["selected_count"] = len(selected)

            if selected:
                dates = [
                    parse_datetime(item["published_at"])
                    for item in selected
                ]
                report["selected_newest"] = max(dates).isoformat(
                    timespec="seconds"
                )
                report["selected_oldest"] = min(dates).isoformat(
                    timespec="seconds"
                )

            atomic_json(report_path, report)

            total = len(selected)
            initial_summary = status_summary(catalog_items, rows)

            print("CREATOR_BATCH_START")
            print(f"creator={username}")
            print(
                f"order={'oldest_first' if args.oldest_first else 'newest_first'}"
            )
            print(f"filter_since={args.since or '-'}")
            print(f"filter_until={args.until or '-'}")
            print(f"rank_from={args.rank_from or '-'}")
            print(f"rank_to={args.rank_to or '-'}")
            print(f"selected={total}")
            print(f"batch_size_requested={args.batch_size}")
            print(
                f"selected_newest={report['selected_newest'] or '-'}"
            )
            print(
                f"selected_oldest={report['selected_oldest'] or '-'}"
            )
            print(
                f"current_accessible_total="
                f"{initial_summary['catalog_total']}"
            )
            print(
                f"current_known_total="
                f"{initial_summary['catalog_total']}"
            )
            print(
                f"total_basis="
                f"{'exact_full_sync' if catalog.get('current_total_exact') else 'quick_sync_lower_bound'}"
            )
            print(
                f"current_total_is_exact="
                f"{str(bool(catalog.get('current_total_exact'))).lower()}"
            )
            print(f"last_sync_mode={catalog.get('last_sync_mode') or '-'}")
            print(f"last_full_sync_at={catalog.get('last_full_sync_at') or '-'}")
            print(f"last_quick_sync_at={catalog.get('last_quick_sync_at') or '-'}")
            print(
                f"account_completed_before="
                f"{initial_summary['completed']}"
            )
            print(
                f"account_remaining_before="
                f"{initial_summary['remaining']}"
            )
            print(
                f"tracked_not_current="
                f"{initial_summary['tracked_not_current']}"
            )
            print(f"report={report_path}")

            print(
                f"PROGRESS 0/{total} 0.0% "
                f"completed=0 failed=0",
                flush=True,
            )
            emit_agent_progress(
                phase="process",
                current=0,
                total=total,
                percent=0.0,
                creator=username,
                completed=0,
                failed=0,
                account_completed=initial_summary["completed"],
                account_total=initial_summary["catalog_total"],
                account_percent=(
                    round(
                        initial_summary["completed"]
                        / initial_summary["catalog_total"]
                        * 100,
                        1,
                    )
                    if initial_summary["catalog_total"]
                    else 100.0
                ),
            )

            for index, item in enumerate(selected, start=1):
                shortcode = item["shortcode"]
                rows = load_video_rows(connection, creator["id"])
                row = rows.get(shortcode)

                if row is None:
                    queue_item(
                        connection,
                        creator["id"],
                        item,
                    )
                elif row["status"] in {"retry_wait", "failed"}:
                    if args.retry_failed:
                        set_pending_for_retry(
                            connection,
                            row["id"],
                        )
                elif row["status"] == "completed" and not markdown_valid(row):
                    set_pending_for_retry(
                        connection,
                        row["id"],
                    )

                print(
                    f"\nITEM_START {index}/{total} "
                    f"shortcode={shortcode} "
                    f"published_at={item['published_at'] or '-'}",
                    flush=True,
                )

                started = iso_now()
                worker = subprocess.run(
                    worker_command(
                        shortcode,
                        explicit_cookies_file,
                        args.force_ipv4,
                    ),
                    cwd=ROOT,
                    capture_output=True,
                    text=True,
                    check=False,
                )

                rows = load_video_rows(connection, creator["id"])
                current_row = rows.get(shortcode)
                final_status = (
                    current_row["status"]
                    if current_row
                    else "missing"
                )
                success = bool(
                    current_row
                    and current_row["status"] == "completed"
                    and markdown_valid(current_row)
                )
                error_text = ""

                if success:
                    report["completed"] += 1
                else:
                    report["failed"] += 1
                    error_text = (
                        (current_row["last_error"] if current_row and current_row["last_error"] else "")
                        or worker.stderr.strip()
                        or worker.stdout.strip()
                        or f"final_status={final_status}"
                    )
                    report["errors"].append(
                        f"{shortcode}: {error_text[-2000:]}"
                    )

                item_result = {
                    "index": index,
                    "shortcode": shortcode,
                    "published_at": item["published_at"],
                    "started_at": started,
                    "finished_at": iso_now(),
                    "worker_return_code": worker.returncode,
                    "status": final_status,
                    "success": success,
                    "error": error_text[-2000:] if error_text else None,
                    "worker_output_tail": (
                        (worker.stdout + "\n" + worker.stderr)[-6000:]
                    ),
                }
                report["items"].append(item_result)
                atomic_json(report_path, report)

                percent = round(index / total * 100, 1) if total else 100.0
                current_summary = status_summary(catalog_items, rows)
                account_total = current_summary["catalog_total"]
                account_completed = current_summary["completed"]
                account_percent = (
                    round(account_completed / account_total * 100, 1)
                    if account_total
                    else 100.0
                )

                print(
                    f"PROGRESS {index}/{total} {percent:.1f}% "
                    f"completed={report['completed']} "
                    f"failed={report['failed']} "
                    f"shortcode={shortcode} "
                    f"status={final_status}",
                    flush=True,
                )
                print(
                    f"ACCOUNT_PROGRESS "
                    f"{account_completed}/{account_total} "
                    f"{account_percent:.1f}% "
                    f"remaining={current_summary['remaining']} "
                    f"exact={str(bool(catalog.get('current_total_exact'))).lower()}",
                    flush=True,
                )
                emit_agent_progress(
                    phase="process",
                    current=index,
                    total=total,
                    percent=percent,
                    creator=username,
                    completed=report["completed"],
                    failed=report["failed"],
                    shortcode=shortcode,
                    status=final_status,
                    error=error_text[-500:] if error_text else None,
                    account_completed=account_completed,
                    account_total=account_total,
                    account_percent=account_percent,
                    account_remaining=current_summary["remaining"],
                    account_total_exact=bool(catalog.get("current_total_exact")),
                )

                if not success:
                    print(
                        f"ITEM_FAILED shortcode={shortcode} status={final_status} "
                        f"error={error_text.replace(chr(10), ' ')[-800:]}",
                        file=sys.stderr,
                        flush=True,
                    )
                if args.max_failures > 0 and report["failed"] >= args.max_failures:
                    print(
                        f"BATCH_ABORTED reason=max_failures threshold={args.max_failures} "
                        f"processed={len(report['items'])} completed={report['completed']} failed={report['failed']}",
                        file=sys.stderr,
                        flush=True,
                    )
                    break
                if args.pause_seconds > 0 and index < total:
                    time.sleep(args.pause_seconds)

            rows = load_video_rows(connection, creator["id"])
            summary = status_summary(catalog_items, rows)
            report["remaining_after"] = summary["remaining"]
            report["summary_after"] = summary
            report["finished_at"] = iso_now()
            report["status"] = (
                "completed_with_errors"
                if report["failed"]
                else "completed"
            )
            atomic_json(report_path, report)

            print()
            print("CREATOR_BATCH_RESULT")
            print(f"creator={username}")
            print(f"status={report['status']}")
            print(f"processed={len(report['items'])}")
            print(f"completed={report['completed']}")
            print(f"failed={report['failed']}")
            print(
                f"date_newest={report['selected_newest'] or '-'}"
            )
            print(
                f"date_oldest={report['selected_oldest'] or '-'}"
            )
            print(
                f"current_accessible_total="
                f"{summary['catalog_total']}"
            )
            print(f"current_known_total={summary['catalog_total']}")
            print(
                f"total_basis="
                f"{'exact_full_sync' if catalog.get('current_total_exact') else 'quick_sync_lower_bound'}"
            )
            print(
                f"account_completed={summary['completed']}"
            )
            print(
                f"remaining={report['remaining_after']}"
            )
            print(
                f"tracked_not_current="
                f"{summary['tracked_not_current']}"
            )
            print(
                f"remaining_is_exact="
                f"{str(report['remaining_is_exact']).lower()}"
            )
            print(f"report={report_path}")

            if args.show_ids:
                print("\nSELECTED_IDS")
                for item in selected:
                    print(
                        f"{item['published_at'] or '-'} | "
                        f"{item['shortcode']}"
                    )

                print("\nRESULT_IDS")
                for item in report["items"]:
                    print(
                        f"{item['shortcode']} | "
                        f"{item['status']} | "
                        f"success={str(item['success']).lower()}"
                    )

            return 0 if not report["failed"] else 2
        finally:
            connection.close()


def command_status(args: argparse.Namespace) -> int:
    username = normalize_creator(args.creator)

    if not args.no_sync:
        cookies_file = args.cookies_file.expanduser().resolve()
        with require_pipeline_idle():
            sync_code = auto_sync_catalog(
                username=username,
                cookies_file=cookies_file,
                quick_sync_size=(
                    0 if args.no_quick_sync else args.quick_sync_size
                ),
                full_sync_interval_minutes=(
                    args.full_sync_interval_minutes
                ),
                full_page_size=args.sync_page_size,
                full_max_reels=args.sync_max_reels,
                page_timeout=args.sync_page_timeout,
                force_ipv4=args.force_ipv4,
                force_full_sync=args.force_full_sync,
                restart_sync=args.restart_sync,
            )
        if sync_code != 0:
            return sync_code

    catalog = load_catalog(username)
    items = list(catalog.get("items", []))

    connection = connect()
    try:
        creator = connection.execute(
            """
            SELECT id, username, enabled
            FROM creators
            WHERE username = ? COLLATE NOCASE
            """,
            (username,),
        ).fetchone()

        rows = (
            load_video_rows(connection, creator["id"])
            if creator
            else {}
        )
    finally:
        connection.close()

    summary = status_summary(items, rows)
    sync_summary = catalog.get("last_sync_summary") or {}
    quick_summary = catalog.get("last_quick_sync_summary") or {}

    print("CREATOR_BULK_STATUS")
    print(f"creator={username}")
    print(f"current_accessible_total={summary['catalog_total']}")
    print(f"current_known_total={summary['catalog_total']}")
    print(
        f"total_basis="
        f"{'exact_full_sync' if catalog.get('current_total_exact') else 'quick_sync_lower_bound'}"
    )
    print(
        f"current_total_is_exact="
        f"{str(bool(catalog.get('current_total_exact'))).lower()}"
    )
    print(f"last_full_sync_at={catalog.get('last_full_sync_at') or '-'}")
    print(f"last_quick_sync_at={catalog.get('last_quick_sync_at') or '-'}")
    print(f"last_sync_mode={catalog.get('last_sync_mode') or '-'}")
    print(f"last_exact_total={catalog.get('last_exact_total') if catalog.get('last_exact_total') is not None else '-'}")
    print(f"last_exact_at={catalog.get('last_exact_at') or '-'}")
    print(
        f"next_full_sync_due_at="
        f"{next_full_sync_due_at(catalog, args.full_sync_interval_minutes) or '-'}"
    )
    print(
        f"quick_added_since_full="
        f"{len(catalog.get('quick_added_since_full', []))}"
    )
    print(
        f"previous_current_total="
        f"{sync_summary.get('previous_total', '-')}"
    )
    print(
        f"new_since_last_sync="
        f"{sync_summary.get('new_since_last_sync', 0)}"
    )
    print(
        f"removed_since_last_full_sync="
        f"{sync_summary.get('removed_since_last_sync', 0)}"
    )
    print(
        f"new_since_last_quick_sync="
        f"{quick_summary.get('new_since_quick_sync', 0)}"
    )
    print(f"completed={summary['completed']}")
    print(f"skipped={summary['skipped']}")
    print(f"untracked={summary['untracked']}")
    print(f"pending={summary['pending']}")
    print(f"retry_wait={summary['retry_wait']}")
    print(f"failed={summary['failed']}")
    print(f"active={summary['active']}")
    print(f"invalid_completed={summary['invalid_completed']}")
    print(f"remaining={summary['remaining']}")
    print(f"historical_tracked={summary['historical_tracked']}")
    print(f"tracked_not_current={summary['tracked_not_current']}")
    print(
        f"remaining_is_exact="
        f"{str(bool(catalog.get('current_total_exact'))).lower()}"
    )

    if items:
        print(f"current_newest={items[0]['published_at'] or '-'}")
        print(f"current_oldest={items[-1]['published_at'] or '-'}")

    if args.show_ids:
        print("\nREMAINING_IDS")
        for item in items:
            row = rows.get(item["shortcode"])
            done = bool(
                row
                and row["status"] == "completed"
                and markdown_valid(row)
            )
            skipped = bool(row and row["status"] == "skipped")
            if done or skipped:
                continue
            status = row["status"] if row else "untracked"
            print(
                f"{item['published_at'] or '-'} | "
                f"{item['shortcode']} | {status}"
            )

        current_shortcodes = {
            item["shortcode"] for item in items
        }
        print("\nTRACKED_NOT_CURRENT_IDS")
        for shortcode, row in sorted(rows.items()):
            if shortcode in current_shortcodes:
                continue
            print(
                f"{row['published_at'] or '-'} | "
                f"{shortcode} | {row['status']}"
            )

        print("\nLAST_SYNC_ADDED_IDS")
        for shortcode in sync_summary.get("added_ids", []):
            print(shortcode)

        print("\nLAST_SYNC_REMOVED_IDS")
        for shortcode in sync_summary.get("removed_ids", []):
            print(shortcode)

    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Hybrid quick/full synchronized creator catalog and 100-video processing batches."
        )
    )
    commands = parser.add_subparsers(dest="command", required=True)

    for command_name in ("sync", "catalog"):
        command = commands.add_parser(
            command_name,
            help=(
                "Build, resume, or refresh an exact current creator snapshot."
            ),
        )
        command.add_argument("creator")
        command.add_argument(
            "--page-size",
            type=int,
            default=100,
        )
        command.add_argument(
            "--pages-per-run",
            type=int,
            default=0,
            help="0 means continue until complete or until an error/cap.",
        )
        command.add_argument(
            "--max-reels",
            type=int,
            default=50000,
        )
        command.add_argument(
            "--page-timeout",
            type=int,
            default=900,
        )
        command.add_argument(
            "--cookies-file",
            type=Path,
            default=COOKIE_FILE,
        )
        command.add_argument(
            "--refresh",
            action="store_true",
            help="Discard an incomplete sync checkpoint and start over.",
        )
        command.add_argument("--force-ipv4", action="store_true")
        command.add_argument("--show-ids", action="store_true")
        command.set_defaults(function=command_catalog)

    command = commands.add_parser(
        "quick-sync",
        help="Check the latest window without traversing all historical Reels.",
    )
    command.add_argument("creator")
    command.add_argument(
        "--quick-sync-size",
        type=int,
        default=100,
    )
    command.add_argument(
        "--page-timeout",
        type=int,
        default=900,
    )
    command.add_argument(
        "--cookies-file",
        type=Path,
        default=COOKIE_FILE,
    )
    command.add_argument("--force-ipv4", action="store_true")
    command.add_argument("--show-ids", action="store_true")
    command.set_defaults(function=command_quick_sync)

    command = commands.add_parser(
        "run",
        help=(
            "Synchronize the current creator snapshot, then process the next batch."
        ),
    )
    command.add_argument("creator")
    command.add_argument(
        "--batch-size",
        type=int,
        default=100,
    )
    command.add_argument("--oldest-first", action="store_true")
    command.add_argument(
        "--since",
        help="Inclusive UTC ISO-8601 lower publication boundary.",
    )
    command.add_argument(
        "--until",
        help="Inclusive UTC ISO-8601 upper publication boundary.",
    )
    command.add_argument(
        "--rank-from",
        type=int,
        help="1-based inclusive rank after ordering and date filtering.",
    )
    command.add_argument(
        "--rank-to",
        type=int,
        help="1-based inclusive rank after ordering and date filtering.",
    )
    command.add_argument("--retry-failed", action="store_true")
    command.add_argument("--allow-partial-catalog", action="store_true")
    command.add_argument(
        "--pause-seconds",
        type=float,
        default=1.0,
    )
    command.add_argument(
        "--max-failures",
        type=int,
        default=10,
        help="Stop the current batch after this many failed items. Use 0 for unlimited.",
    )
    command.add_argument(
        "--cookies-file",
        type=Path,
        default=None,
        help="Optional explicit cookie-file override. By default the worker uses the managed cookie file, then browser cookies.",
    )
    command.add_argument("--force-ipv4", action="store_true")
    command.add_argument("--show-ids", action="store_true")
    command.add_argument(
        "--no-auto-sync",
        action="store_true",
        help="Use the existing snapshot without checking Instagram first.",
    )
    command.add_argument(
        "--full-sync-interval-minutes",
        "--sync-max-age-minutes",
        dest="full_sync_interval_minutes",
        type=float,
        default=1440.0,
        help=(
            "Run a full historical sync when the last full sync is older "
            "than this interval. Default: 1440 minutes (24 hours)."
        ),
    )
    command.add_argument(
        "--quick-sync-size",
        type=int,
        default=100,
        help="Latest Reels checked before each fresh-snapshot batch.",
    )
    command.add_argument(
        "--no-quick-sync",
        action="store_true",
        help="Reuse a fresh full snapshot without checking the latest window.",
    )
    command.add_argument(
        "--force-full-sync",
        action="store_true",
        help="Ignore the TTL and run a complete historical sync now.",
    )
    command.add_argument(
        "--sync-page-size",
        type=int,
        default=100,
    )
    command.add_argument(
        "--sync-max-reels",
        type=int,
        default=50000,
    )
    command.add_argument(
        "--sync-page-timeout",
        type=int,
        default=900,
    )
    command.add_argument(
        "--restart-sync",
        action="store_true",
        help="Discard any incomplete sync checkpoint before auto-sync.",
    )
    command.set_defaults(function=command_run)

    command = commands.add_parser(
        "status",
        help="Show current snapshot, changes, and processing coverage.",
    )
    command.add_argument("creator")
    command.add_argument("--show-ids", action="store_true")
    command.add_argument(
        "--no-sync",
        action="store_true",
        help="Report the saved snapshot without checking Instagram first.",
    )
    command.add_argument(
        "--cookies-file",
        type=Path,
        default=COOKIE_FILE,
    )
    command.add_argument("--force-ipv4", action="store_true")
    command.add_argument(
        "--full-sync-interval-minutes",
        "--sync-max-age-minutes",
        dest="full_sync_interval_minutes",
        type=float,
        default=1440.0,
    )
    command.add_argument(
        "--quick-sync-size",
        type=int,
        default=100,
    )
    command.add_argument("--no-quick-sync", action="store_true")
    command.add_argument("--force-full-sync", action="store_true")
    command.add_argument(
        "--sync-page-size",
        type=int,
        default=100,
    )
    command.add_argument(
        "--sync-max-reels",
        type=int,
        default=50000,
    )
    command.add_argument(
        "--sync-page-timeout",
        type=int,
        default=900,
    )
    command.add_argument("--restart-sync", action="store_true")
    command.set_defaults(function=command_status)

    return parser


def main() -> int:
    args = build_parser().parse_args()

    if not DB_PATH.is_file():
        raise RuntimeError(f"Database not found: {DB_PATH}")

    for field in ("page_size", "sync_page_size", "quick_sync_size"):
        if hasattr(args, field):
            value = getattr(args, field)
            if not 1 <= value <= 500:
                raise RuntimeError(f"--{field.replace('_', '-')} must be between 1 and 500.")

    if hasattr(args, "pages_per_run") and args.pages_per_run < 0:
        raise RuntimeError("--pages-per-run must be 0 or greater.")

    for field in ("max_reels", "sync_max_reels"):
        if hasattr(args, field):
            value = getattr(args, field)
            if not 1 <= value <= 50000:
                raise RuntimeError(
                    f"--{field.replace('_', '-')} must be between 1 and 50000."
                )

    if hasattr(args, "batch_size") and not 1 <= args.batch_size <= 500:
        raise RuntimeError("--batch-size must be between 1 and 500.")

    if hasattr(args, "rank_from") and args.rank_from is not None and args.rank_from < 1:
        raise RuntimeError("--rank-from must be 1 or greater.")
    if hasattr(args, "rank_to") and args.rank_to is not None and args.rank_to < 1:
        raise RuntimeError("--rank-to must be 1 or greater.")
    if (
        hasattr(args, "rank_from")
        and hasattr(args, "rank_to")
        and args.rank_from is not None
        and args.rank_to is not None
        and args.rank_from > args.rank_to
    ):
        raise RuntimeError("--rank-from cannot exceed --rank-to.")

    if (
        hasattr(args, "full_sync_interval_minutes")
        and args.full_sync_interval_minutes < 0
    ):
        raise RuntimeError(
            "--full-sync-interval-minutes must be 0 or greater."
        )

    return args.function(args)

if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (
        RuntimeError,
        sqlite3.Error,
        OSError,
        subprocess.SubprocessError,
        json.JSONDecodeError,
    ) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise SystemExit(1)
