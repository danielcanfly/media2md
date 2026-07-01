#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import os
import random
import re
import string
import urllib.parse
import shutil
import signal
import sqlite3
import subprocess
import sys
import time
import statistics
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
if sys.path and sys.path[0] == _SCRIPT_DIR:
    sys.path.append(sys.path.pop(0))

try:
    from media2md.cli_result_types import cli_result
    from media2md.required_actions import validate_required_action
except ModuleNotFoundError:
    from media2md_contract_compat import cli_result, validate_required_action

from media2md_paths import require_command
from media2md_runtime import operation_lock, safe_artifact_stem
from media2md_types import (
    DEFAULT_BATCH_SIZES, infer_media_type, media_type_for_youtube_surface,
    merge_catalog_items, normalize_batch_sizes, processing_class,
    youtube_surface_from_url, youtube_surface_urls,
)
from media2md_urls import normalize_creator as normalize_creator_target, normalize_media as normalize_media_target
from media2md_ytdlp import impersonation_args, impersonation_targets, youtube_runtime_args
from media2md_youtube_session import youtube_auth_args, verify_youtube_session

from media2md_auth_shared import refresh_if_configured

ROOT = Path(__file__).resolve().parents[1]
DB = ROOT / "data" / "media2md.db"
LEGACY_INSTAGRAM_DB = ROOT / "data" / "state.db"
LEGACY_GENERIC_DB = ROOT / "data" / "social2md_media.db"
LEGACY_INSTAGRAM_CATALOG_DIR = ROOT / "data" / "creator_catalogs"
POLICIES = ROOT / "config" / "provider_policies.json"
CONFIG = ROOT / "config" / "social2md.json"
AUTH_PROFILES = ROOT / "config" / "auth_profiles.json"
RUN_DIR = ROOT / "logs" / "runs"
QUARANTINE = ROOT / "data" / "quarantine"
CHECKPOINT_DIR = ROOT / "data" / "provider_catalog_checkpoints"
TIKTOK_CURSOR_STATE = CHECKPOINT_DIR / "tiktok-cursor-state.json"
SUPPORTED = ("instagram", "youtube", "tiktok")


def iso_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def safe_name(value: str) -> str:
    clean = re.sub(r"[^A-Za-z0-9._-]+", "_", value.strip().lstrip("@"))
    return clean[:150] or "unknown"


def atomic_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.replace(tmp, path)


def load_json(path: Path, default: Any) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return json.loads(json.dumps(default))


def emit_cli_event(*, event: str, section: str, status: str, message: str, data: dict[str, Any]) -> None:
    print(
        json.dumps(
            cli_result(
                event=event,
                section=section,
                status=status,
                message=message,
                data=data,
            ),
            ensure_ascii=False,
        ),
        flush=True,
    )


def creator_run_event_status(status: str) -> str:
    if status == "completed":
        return "ok"
    if status == "paused_runtime_limit":
        return "timeout"
    if status == "stopped_max_failures":
        return "error"
    return "warn"


def _load_tiktok_cursor_state(handle: str) -> dict[str, Any]:
    payload = load_json(TIKTOK_CURSOR_STATE, {"schema_version": 1, "creators": {}})
    item = (payload.get("creators") or {}).get(handle)
    return dict(item) if isinstance(item, dict) else {}


def _save_tiktok_cursor_state(handle: str, *, device_id: str, authenticated: bool) -> None:
    with operation_lock(
        "state-write",
        "tiktok-cursor-state",
        metadata={"provider": "tiktok", "creator": handle},
        wait_seconds=10,
    ):
        payload = load_json(TIKTOK_CURSOR_STATE, {"schema_version": 1, "creators": {}})
        payload.setdefault("schema_version", 1)
        creators = payload.setdefault("creators", {})
        creators[handle] = {
            "device_id": str(device_id),
            "authenticated": bool(authenticated),
            "updated_at": iso_now(),
        }
        atomic_json(TIKTOK_CURSOR_STATE, payload)


def youtube_long_threshold_seconds() -> int:
    config = load_json(CONFIG, {})
    try:
        return max(60, int(config.get("providers", {}).get("youtube", {}).get("long_video_threshold_seconds", 2700)))
    except (TypeError, ValueError):
        return 2700


def youtube_catalog_surfaces() -> tuple[str, ...]:
    config = load_json(CONFIG, {})
    raw = config.get("providers", {}).get("youtube", {}).get("catalog_surfaces", ["videos", "shorts"])
    surfaces = tuple(item for item in raw if item in {"videos", "shorts", "streams"})
    return surfaces or ("videos", "shorts")


def _type_counts(conn: sqlite3.Connection, creator_id: int) -> dict[str, int]:
    rows = conn.execute(
        "SELECT COALESCE(media_type,'unknown') media_type,COUNT(*) total FROM media "
        "WHERE creator_id=? AND is_current=1 GROUP BY COALESCE(media_type,'unknown')",
        (creator_id,),
    ).fetchall()
    return {str(row["media_type"]): int(row["total"]) for row in rows}


def refresh_creator_type_totals(
    conn: sqlite3.Connection,
    creator_id: int,
    *,
    exact_by_type: dict[str, bool] | None = None,
    combined_exact: bool | None = None,
) -> dict[str, int]:
    counts = _type_counts(conn, creator_id)
    exact_by_type = exact_by_type or {}
    total = sum(counts.values())
    if combined_exact is None:
        combined_exact = False
    conn.execute(
        """UPDATE creators SET current_total=?,current_total_exact=?,
        youtube_video_total=?,youtube_video_total_exact=?,
        youtube_shorts_total=?,youtube_shorts_total_exact=?,
        youtube_streams_total=?,youtube_streams_total_exact=?,updated_at=? WHERE id=?""",
        (
            total, int(bool(combined_exact)),
            counts.get("youtube_video", 0), int(bool(exact_by_type.get("youtube_video", False))),
            counts.get("youtube_short", 0), int(bool(exact_by_type.get("youtube_short", False))),
            counts.get("youtube_stream", 0), int(bool(exact_by_type.get("youtube_stream", False))),
            iso_now(), creator_id,
        ),
    )
    return counts


def connect() -> sqlite3.Connection:
    DB.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB, timeout=60)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=60000")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS creators (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            provider TEXT NOT NULL,
            external_id TEXT NOT NULL,
            handle TEXT NOT NULL,
            display_name TEXT,
            source_url TEXT NOT NULL,
            enabled INTEGER NOT NULL DEFAULT 1,
            current_total INTEGER,
            current_total_exact INTEGER NOT NULL DEFAULT 0,
            youtube_video_total INTEGER,
            youtube_video_total_exact INTEGER NOT NULL DEFAULT 0,
            youtube_shorts_total INTEGER,
            youtube_shorts_total_exact INTEGER NOT NULL DEFAULT 0,
            youtube_streams_total INTEGER,
            youtube_streams_total_exact INTEGER NOT NULL DEFAULT 0,
            last_sync_mode TEXT,
            last_sync_at TEXT,
            last_full_sync_at TEXT,
            last_full_exact_total INTEGER,
            last_full_exact_at TEXT,
            last_full_youtube_video_total INTEGER,
            last_full_youtube_shorts_total INTEGER,
            last_full_youtube_streams_total INTEGER,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            UNIQUE(provider, external_id),
            UNIQUE(provider, handle)
        );
        CREATE TABLE IF NOT EXISTS media (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            provider TEXT NOT NULL,
            creator_id INTEGER NOT NULL REFERENCES creators(id) ON DELETE CASCADE,
            external_id TEXT NOT NULL,
            title TEXT,
            description TEXT,
            source_url TEXT NOT NULL,
            published_at TEXT,
            duration_seconds REAL,
            media_type TEXT,
            processing_class TEXT,
            rank_newest INTEGER,
            is_current INTEGER NOT NULL DEFAULT 1,
            status TEXT NOT NULL DEFAULT 'pending',
            markdown_path TEXT,
            markdown_sha256 TEXT,
            last_error TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            completed_at TEXT,
            UNIQUE(provider, external_id)
        );
        CREATE INDEX IF NOT EXISTS idx_media_creator_status ON media(creator_id, status);
        CREATE INDEX IF NOT EXISTS idx_media_creator_current ON media(creator_id, is_current, published_at DESC);
        CREATE TABLE IF NOT EXISTS creator_aliases (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            creator_id INTEGER NOT NULL REFERENCES creators(id) ON DELETE CASCADE,
            provider TEXT NOT NULL,
            alias TEXT NOT NULL,
            first_seen_at TEXT NOT NULL,
            last_seen_at TEXT NOT NULL,
            UNIQUE(provider, alias)
        );
        CREATE INDEX IF NOT EXISTS idx_creator_aliases_creator ON creator_aliases(creator_id);
        CREATE TABLE IF NOT EXISTS creator_identifiers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            creator_id INTEGER NOT NULL REFERENCES creators(id) ON DELETE CASCADE,
            provider TEXT NOT NULL,
            identifier_type TEXT NOT NULL,
            identifier_value TEXT NOT NULL,
            first_seen_at TEXT NOT NULL,
            last_seen_at TEXT NOT NULL,
            UNIQUE(provider, identifier_type, identifier_value)
        );
        CREATE INDEX IF NOT EXISTS idx_creator_identifiers_creator ON creator_identifiers(creator_id);
        CREATE TABLE IF NOT EXISTS migrations (
            name TEXT PRIMARY KEY,
            applied_at TEXT NOT NULL,
            details TEXT
        );
        """
    )
    # Forward-compatible in-place schema migration for v0.7.1.
    creator_columns = {row[1] for row in conn.execute("PRAGMA table_info(creators)")}
    for name, definition in (
        ("youtube_video_total", "INTEGER"),
        ("youtube_video_total_exact", "INTEGER NOT NULL DEFAULT 0"),
        ("youtube_shorts_total", "INTEGER"),
        ("youtube_shorts_total_exact", "INTEGER NOT NULL DEFAULT 0"),
        ("youtube_streams_total", "INTEGER"),
        ("youtube_streams_total_exact", "INTEGER NOT NULL DEFAULT 0"),
        ("last_full_exact_total", "INTEGER"),
        ("last_full_exact_at", "TEXT"),
        ("last_full_youtube_video_total", "INTEGER"),
        ("last_full_youtube_shorts_total", "INTEGER"),
        ("last_full_youtube_streams_total", "INTEGER"),
    ):
        if name not in creator_columns:
            conn.execute(f"ALTER TABLE creators ADD COLUMN {name} {definition}")
    media_columns = {row[1] for row in conn.execute("PRAGMA table_info(media)")}
    for name, definition in (("media_type", "TEXT"), ("processing_class", "TEXT")):
        if name not in media_columns:
            conn.execute(f"ALTER TABLE media ADD COLUMN {name} {definition}")
    threshold = youtube_long_threshold_seconds()
    conn.execute("UPDATE media SET media_type='instagram_reel' WHERE provider='instagram' AND (media_type IS NULL OR media_type='')")
    conn.execute("UPDATE media SET media_type='tiktok_video' WHERE provider='tiktok' AND (media_type IS NULL OR media_type='')")
    conn.execute("UPDATE media SET media_type='youtube_video' WHERE provider='youtube' AND (media_type IS NULL OR media_type='')")
    conn.execute(
        "UPDATE media SET processing_class=CASE WHEN provider='youtube' AND media_type='youtube_video' "
        "AND COALESCE(duration_seconds,0)>=? THEN 'youtube_long' ELSE media_type END "
        "WHERE processing_class IS NULL OR processing_class=''",
        (threshold,),
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_media_creator_type_status ON media(creator_id,processing_class,status)")
    conn.commit()
    return conn


def provider_from_url(value: str) -> str | None:
    lower = value.lower()
    if "instagram.com" in lower:
        return "instagram"
    if "youtube.com" in lower or "youtu.be" in lower:
        return "youtube"
    if "tiktok.com" in lower:
        return "tiktok"
    return None


def normalize_creator(provider: str, value: str) -> tuple[str, str]:
    target = normalize_creator_target(provider, value)
    return str(target.creator), target.canonical_url


def _is_tiktok_opaque_identifier(value: str | None) -> bool:
    text = str(value or "").strip().lstrip("@")
    return bool(text) and (text.isdigit() or text.startswith("MS4wLjAB") or len(text) > 40)


def _is_human_tiktok_handle(value: str | None) -> bool:
    text = str(value or "").strip().lstrip("@")
    return bool(text) and not _is_tiktok_opaque_identifier(text) and bool(re.fullmatch(r"[A-Za-z0-9._-]+", text))


def _tiktok_handle_from_url(value: str | None) -> str | None:
    match = re.search(r"tiktok\.com/@([A-Za-z0-9._-]+)(?:/|$)", str(value or ""), re.I)
    if not match:
        return None
    handle = match.group(1)
    return handle if _is_human_tiktok_handle(handle) else None


def _merge_creator_rows(conn: sqlite3.Connection, primary_id: int, duplicate_id: int) -> int:
    if primary_id == duplicate_id:
        return primary_id
    now = iso_now()
    duplicate = conn.execute("SELECT * FROM creators WHERE id=?", (duplicate_id,)).fetchone()
    if not duplicate:
        return primary_id
    conn.execute("UPDATE OR IGNORE media SET creator_id=? WHERE creator_id=?", (primary_id, duplicate_id))
    conn.execute(
        "INSERT OR IGNORE INTO creator_aliases(creator_id,provider,alias,first_seen_at,last_seen_at) VALUES(?,?,?,?,?)",
        (primary_id, duplicate["provider"], duplicate["handle"], now, now),
    )
    aliases = conn.execute("SELECT provider,alias,first_seen_at,last_seen_at FROM creator_aliases WHERE creator_id=?", (duplicate_id,)).fetchall()
    for alias in aliases:
        conn.execute(
            "INSERT INTO creator_aliases(creator_id,provider,alias,first_seen_at,last_seen_at) VALUES(?,?,?,?,?) "
            "ON CONFLICT(provider,alias) DO UPDATE SET creator_id=excluded.creator_id,last_seen_at=excluded.last_seen_at",
            (primary_id, alias["provider"], alias["alias"], alias["first_seen_at"], now),
        )
    identifiers = conn.execute("SELECT provider,identifier_type,identifier_value,first_seen_at FROM creator_identifiers WHERE creator_id=?", (duplicate_id,)).fetchall()
    for identifier in identifiers:
        conn.execute(
            "INSERT INTO creator_identifiers(creator_id,provider,identifier_type,identifier_value,first_seen_at,last_seen_at) VALUES(?,?,?,?,?,?) "
            "ON CONFLICT(provider,identifier_type,identifier_value) DO UPDATE SET creator_id=excluded.creator_id,last_seen_at=excluded.last_seen_at",
            (primary_id, identifier["provider"], identifier["identifier_type"], identifier["identifier_value"], identifier["first_seen_at"], now),
        )
    conn.execute("DELETE FROM creators WHERE id=?", (duplicate_id,))
    return primary_id


def _identity_rows(conn: sqlite3.Connection, provider: str, external_id: str, handle: str, identifiers: dict[str, str] | None = None) -> list[sqlite3.Row]:
    found: dict[int, sqlite3.Row] = {}
    if external_id:
        row = conn.execute("SELECT * FROM creators WHERE provider=? AND external_id=?", (provider, external_id)).fetchone()
        if row: found[int(row["id"])] = row
    if handle:
        row = conn.execute("SELECT * FROM creators WHERE provider=? AND handle=? COLLATE NOCASE", (provider, handle)).fetchone()
        if row: found[int(row["id"])] = row
        row = conn.execute(
            "SELECT c.* FROM creator_aliases a JOIN creators c ON c.id=a.creator_id WHERE a.provider=? AND a.alias=? COLLATE NOCASE",
            (provider, handle),
        ).fetchone()
        if row: found[int(row["id"])] = row
    for identifier_type, identifier_value in (identifiers or {}).items():
        if not identifier_value:
            continue
        row = conn.execute(
            "SELECT c.* FROM creator_identifiers i JOIN creators c ON c.id=i.creator_id "
            "WHERE i.provider=? AND i.identifier_type=? AND i.identifier_value=?",
            (provider, identifier_type, str(identifier_value)),
        ).fetchone()
        if row: found[int(row["id"])] = row
    return list(found.values())


def _creator_by_identity(conn: sqlite3.Connection, provider: str, external_id: str, handle: str, identifiers: dict[str, str] | None = None) -> sqlite3.Row | None:
    rows = _identity_rows(conn, provider, external_id, handle, identifiers)
    if not rows:
        return None
    # Prefer a human-readable handle over numeric/secUid placeholders, then the oldest row.
    rows.sort(key=lambda row: (_is_tiktok_opaque_identifier(str(row["handle"])) if provider == "tiktok" else False, int(row["id"])))
    primary_id = int(rows[0]["id"])
    for duplicate in rows[1:]:
        _merge_creator_rows(conn, primary_id, int(duplicate["id"]))
    return conn.execute("SELECT * FROM creators WHERE id=?", (primary_id,)).fetchone()


def upsert_creator_identity(
    conn: sqlite3.Connection, provider: str, external_id: str, handle: str, display_name: str, source_url: str,
    identifiers: dict[str, str] | None = None,
) -> sqlite3.Row:
    now = iso_now()
    identifiers = {str(k): str(v) for k, v in (identifiers or {}).items() if v}
    external_id = external_id or identifiers.get("sec_uid") or identifiers.get("channel_id") or handle
    handle = handle.lstrip("@") or external_id
    incoming_handle = handle
    creator = _creator_by_identity(conn, provider, external_id, handle, identifiers)
    if provider == "tiktok" and creator:
        existing_handle = str(creator["handle"] or "")
        if _is_tiktok_opaque_identifier(incoming_handle) and _is_human_tiktok_handle(existing_handle):
            identifiers.setdefault("sec_uid", incoming_handle if incoming_handle.startswith("MS4wLjAB") else "")
            identifiers = {k: v for k, v in identifiers.items() if v}
            handle = existing_handle
        elif _is_human_tiktok_handle(incoming_handle) and _is_tiktok_opaque_identifier(existing_handle):
            handle = incoming_handle
    if creator:
        existing_external = str(creator["external_id"] or "")
        # Legacy refreshes may only know a handle or numeric TikTok user id. Never
        # overwrite a previously learned secUid/channel id with a weaker identifier.
        if provider == "tiktok" and existing_external and existing_external.lower() != str(creator["handle"]).lower():
            incoming_is_weak = (external_id.lower() == handle.lower()) or external_id.isdigit()
            existing_is_strong = not existing_external.isdigit()
            if incoming_is_weak and existing_is_strong:
                external_id = existing_external
        if provider == "youtube" and existing_external.startswith("UC") and not external_id.startswith("UC"):
            external_id = existing_external
        old_handle = str(creator["handle"])
        if old_handle.lower() != handle.lower():
            conn.execute(
                "INSERT OR IGNORE INTO creator_aliases(creator_id,provider,alias,first_seen_at,last_seen_at) VALUES(?,?,?,?,?)",
                (creator["id"], provider, old_handle, now, now),
            )
        if provider == "tiktok" and _is_tiktok_opaque_identifier(incoming_handle):
            identifier_type = "sec_uid" if incoming_handle.startswith("MS4wLjAB") else "user_id"
            identifiers.setdefault(identifier_type, incoming_handle)
        conn.execute(
            "UPDATE creators SET external_id=?, handle=?, display_name=?, source_url=?, updated_at=? WHERE id=?",
            (external_id, handle, display_name or handle, source_url, now, creator["id"]),
        )
        creator_id = int(creator["id"])
    else:
        cursor = conn.execute(
            "INSERT INTO creators(provider,external_id,handle,display_name,source_url,created_at,updated_at) VALUES(?,?,?,?,?,?,?)",
            (provider, external_id, handle, display_name or handle, source_url, now, now),
        )
        creator_id = int(cursor.lastrowid)
    conn.execute(
        "INSERT INTO creator_aliases(creator_id,provider,alias,first_seen_at,last_seen_at) VALUES(?,?,?,?,?) "
        "ON CONFLICT(provider,alias) DO UPDATE SET creator_id=excluded.creator_id,last_seen_at=excluded.last_seen_at",
        (creator_id, provider, handle, now, now),
    )
    identifiers.setdefault("primary", external_id)
    for identifier_type, identifier_value in identifiers.items():
        conn.execute(
            "INSERT INTO creator_identifiers(creator_id,provider,identifier_type,identifier_value,first_seen_at,last_seen_at) VALUES(?,?,?,?,?,?) "
            "ON CONFLICT(provider,identifier_type,identifier_value) DO UPDATE SET creator_id=excluded.creator_id,last_seen_at=excluded.last_seen_at",
            (creator_id, provider, identifier_type, identifier_value, now, now),
        )
    return conn.execute("SELECT * FROM creators WHERE id=?", (creator_id,)).fetchone()

def auth_args(provider: str) -> list[str]:
    if provider == "youtube":
        return youtube_auth_args()
    try:
        refresh_if_configured(provider)
    except Exception:
        pass
    profiles = load_json(AUTH_PROFILES, {"providers": {}}).get("providers", {}) if "load_json" in globals() else json.loads(AUTH_PROFILES.read_text(encoding="utf-8")).get("providers", {})
    profile = profiles.get(provider, {})
    cookie = profile.get("cookie_file")
    if cookie and Path(cookie).expanduser().is_file():
        return ["--cookies", str(Path(cookie).expanduser())]
    return []


def command(name: str) -> str:
    return require_command(name)


def _transient_error_text(text: str) -> bool:
    lowered = text.lower()
    return any(token in lowered for token in (
        "read timed out", "timed out", "timeout", "connection reset", "connection aborted",
        "temporarily unavailable", "remote disconnected", "http error 429", "too many requests",
        "http error 500", "http error 502", "http error 503", "http error 504",
        "status code 429", "status code 500", "status code 502", "status code 503", "status code 504",
        "curl: (35)", "curl error 35", "tls connect error", "tls handshake", "sslerror",
        "openssl_internal", "ssl connect error", "connection closed during tls",
    ))


def _stop_process_group(process: subprocess.Popen[str], *, interrupt: bool = False) -> None:
    """Stop an extractor and its complete process tree."""
    sequence = (
        (signal.SIGINT, 4) if interrupt else (signal.SIGTERM, 4),
        (signal.SIGTERM, 4),
        (signal.SIGKILL, 2),
    )
    for sig, wait_seconds in sequence:
        if process.poll() is not None:
            return
        try:
            os.killpg(process.pid, sig)
        except (ProcessLookupError, PermissionError):
            return
        try:
            process.wait(timeout=wait_seconds)
            return
        except subprocess.TimeoutExpired:
            continue


def _capture_process(
    command_line: list[str],
    timeout: int,
    *,
    heartbeat_context: str | None = None,
    heartbeat_interval: float = 30.0,
    env: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    process = subprocess.Popen(
        command_line,
        cwd=ROOT,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        start_new_session=True,
        env=env,
    )
    started = time.monotonic()
    next_heartbeat = started + max(1.0, heartbeat_interval)
    try:
        while True:
            elapsed = time.monotonic() - started
            remaining = timeout - elapsed
            if remaining <= 0:
                _stop_process_group(process)
                stdout, stderr = process.communicate()
                raise subprocess.TimeoutExpired(command_line, timeout, output=stdout, stderr=stderr)
            try:
                stdout, stderr = process.communicate(timeout=min(1.0, remaining))
                return subprocess.CompletedProcess(command_line, process.returncode, stdout, stderr)
            except subprocess.TimeoutExpired:
                now = time.monotonic()
                if heartbeat_context and now >= next_heartbeat:
                    print(
                        f"SYNC_WAITING {heartbeat_context} elapsed_seconds={int(now-started)} "
                        f"pid={process.pid} timeout_seconds={timeout}",
                        file=sys.stderr,
                        flush=True,
                    )
                    next_heartbeat = now + max(1.0, heartbeat_interval)
    except KeyboardInterrupt:
        _stop_process_group(process, interrupt=True)
        print(
            f"SYNC_INTERRUPTED {heartbeat_context or 'extractor'} exit_code=130",
            file=sys.stderr,
            flush=True,
        )
        raise


def run_json(
    command_line: list[str],
    timeout: int = 1800,
    *,
    delays: list[int] | None = None,
    strategy: str | None = None,
    heartbeat_context: str | None = None,
    heartbeat_interval: float = 30.0,
    env: dict[str, str] | None = None,
) -> dict[str, Any]:
    delays = delays or [0, 10, 30, 90]
    scale = max(0.0, float(os.getenv("MEDIA2MD_RETRY_SCALE", "1")))
    last_error = "command failed"
    for attempt, delay in enumerate(delays, 1):
        if delay:
            actual_delay = delay * scale
            print(
                f"SYNC_RETRY attempt={attempt}/{len(delays)} delay_seconds={actual_delay:g} "
                f"reason=transient_error strategy={strategy or 'default'}",
                file=sys.stderr,
                flush=True,
            )
            if actual_delay:
                time.sleep(actual_delay)
        try:
            result = _capture_process(
                command_line,
                timeout,
                heartbeat_context=heartbeat_context,
                heartbeat_interval=heartbeat_interval,
                env=env,
            )
            if result.returncode == 0:
                try:
                    return json.loads(result.stdout)
                except json.JSONDecodeError as exc:
                    raise RuntimeError(f"Invalid JSON from extractor: {exc}") from exc
            last_error = (result.stderr or result.stdout or "command failed")[-4000:]
        except subprocess.TimeoutExpired as exc:
            last_error = f"Extractor timed out after {timeout} seconds: {exc}"
        if not _transient_error_text(last_error) or attempt == len(delays):
            raise RuntimeError(last_error)
    raise RuntimeError(last_error)


def parse_timestamp(item: dict[str, Any]) -> str | None:
    timestamp = item.get("timestamp") or item.get("release_timestamp")
    if timestamp:
        try:
            return datetime.fromtimestamp(float(timestamp), tz=timezone.utc).isoformat(timespec="seconds")
        except (ValueError, TypeError, OSError):
            pass
    upload = str(item.get("upload_date") or item.get("release_date") or "")
    if re.fullmatch(r"\d{8}", upload):
        return datetime.strptime(upload, "%Y%m%d").replace(tzinfo=timezone.utc).isoformat(timespec="seconds")
    return None


def _profile_meta(
    provider: str,
    payload: dict[str, Any],
    requested_url: str,
    *,
    handle_hint: str | None = None,
) -> dict[str, Any]:
    identifiers: dict[str, str] = {}
    if provider == "youtube":
        channel_id = str(payload.get("channel_id") or "").strip()
        uploader_id = str(payload.get("uploader_id") or "").strip()
        if channel_id: identifiers["channel_id"] = channel_id
        if uploader_id: identifiers["uploader_id"] = uploader_id
        external_id = channel_id or uploader_id or str(payload.get("id") or safe_name(requested_url))
        raw_handle = str(payload.get("uploader_id") or payload.get("channel") or payload.get("uploader") or external_id)
        handle = raw_handle.lstrip("@")
    else:
        sec_uid = str(payload.get("channel_id") or "").strip()
        user_id = str(payload.get("uploader_id") or payload.get("creator_id") or "").strip()
        if sec_uid: identifiers["sec_uid"] = sec_uid
        if user_id and user_id != sec_uid: identifiers["user_id"] = user_id
        external_id = sec_uid or user_id or str(payload.get("id") or safe_name(requested_url))
        requested_handle = (handle_hint or _tiktok_handle_from_url(requested_url) or "").lstrip("@")
        candidates = [requested_handle, payload.get("uploader"), payload.get("channel"), payload.get("uploader_id")]
        handle = next((str(value).lstrip("@") for value in candidates if _is_human_tiktok_handle(value)), None)
        if not handle:
            raise RuntimeError("TikTok catalog metadata did not contain a human-readable creator handle.")
    return {
        "external_id": external_id,
        "identifiers": identifiers,
        "handle": handle,
        "display_name": str(payload.get("channel") or payload.get("uploader") or payload.get("title") or handle),
        "source_url": requested_url,
    }


def _target_version_key(value: str) -> tuple[int, ...]:
    numbers = tuple(int(part) for part in re.findall(r"\d+", value))
    return numbers or (0,)


def _latest_impersonation_target(targets: list[str], family: str) -> str | None:
    matching = [item for item in targets if item.lower().startswith(family.lower() + "-")]
    return max(matching, key=_target_version_key) if matching else None


def _proxy_environment() -> tuple[dict[str, str], list[str]]:
    env = os.environ.copy()
    removed: list[str] = []
    for key in (
        "HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "NO_PROXY",
        "http_proxy", "https_proxy", "all_proxy", "no_proxy",
    ):
        if key in env:
            removed.append(key)
            env.pop(key, None)
    return env, removed


def _macos_system_proxy_kinds() -> list[str]:
    """Return enabled macOS proxy classes without exposing hosts or credentials."""
    if sys.platform != "darwin" or not shutil.which("scutil"):
        return []
    try:
        result = subprocess.run(
            ["scutil", "--proxy"], capture_output=True, text=True, timeout=10, check=False
        )
    except (OSError, subprocess.SubprocessError):
        return []
    if result.returncode != 0:
        return []
    enabled: list[str] = []
    mapping = {
        "HTTPEnable": "http",
        "HTTPSEnable": "https",
        "SOCKSEnable": "socks",
        "FTPEnable": "ftp",
        "RTSPEnable": "rtsp",
    }
    for key, label in mapping.items():
        if re.search(rf"(?m)^\s*{re.escape(key)}\s*:\s*1\s*$", result.stdout):
            enabled.append(label)
    return enabled


def _yt_dlp_proxy_config_files() -> list[str]:
    candidates = (
        Path.home() / ".config" / "yt-dlp" / "config",
        Path.home() / "Library" / "Application Support" / "yt-dlp" / "config",
        Path.home() / ".yt-dlp" / "config",
        Path.home() / "yt-dlp.conf",
    )
    found: list[str] = []
    for path in candidates:
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        if re.search(r"(?im)^\s*--proxy(?:\s|=)", text):
            found.append(str(path))
    return found


def _tiktok_transport_error_text(text: str) -> bool:
    lowered = text.lower()
    return any(token in lowered for token in (
        "curl: (35)", "curl: (56)", "tls connect error", "tls handshake",
        "sslerror", "openssl_internal", "ssl connect error",
        "connection closed abruptly", "unable to connect to proxy", "proxyerror",
        "remote end closed connection", "transporterror",
    ))


def _tiktok_tls_error_text(text: str) -> bool:
    lowered = text.lower()
    return any(token in lowered for token in (
        "curl: (35)", "tls connect error", "tls handshake", "sslerror",
        "openssl_internal", "ssl connect error",
    ))


def _tiktok_transport_strategies() -> list[tuple[str, list[str], bool]]:
    """Return a bounded, deterministic TikTok transport plan.

    v0.7.4 tried every curl-cffi target exposed by yt-dlp, which multiplied one
    TLS fault into dozens of near-identical attempts. v0.7.8 keeps the plan bounded at
    four strategies: configured, newest Chrome, newest Safari, and one direct
    plain request with proxy variables and user yt-dlp config disabled.
    """
    configured = impersonation_args("tiktok")
    inventory = impersonation_targets()
    available = [str(item) for item in inventory.get("targets", [])]
    candidates: list[tuple[str, list[str], bool]] = []
    if configured:
        candidates.append((f"configured:{configured[-1]}", ["--ignore-config", *configured], False))
    latest_chrome = _latest_impersonation_target(available, "Chrome")
    if latest_chrome:
        candidates.append((f"latest:{latest_chrome}", ["--ignore-config", "--impersonate", latest_chrome], False))
    latest_safari = _latest_impersonation_target(available, "Safari")
    if latest_safari:
        candidates.append((f"latest:{latest_safari}", ["--ignore-config", "--impersonate", latest_safari], False))
    candidates.append(("direct-plain", ["--ignore-config", "--proxy", ""], True))
    result: list[tuple[str, list[str], bool]] = []
    seen: set[tuple[tuple[str, ...], bool]] = set()
    for name, args, direct in candidates:
        key = (tuple(args), direct)
        if key in seen:
            continue
        seen.add(key)
        result.append((name, args, direct))
    return result[:4]


def _tiktok_error_reason(text: str) -> str:
    lowered = text.lower()
    if _tiktok_tls_error_text(text):
        return "tls_failure"
    if "unable to connect to proxy" in lowered or "proxyerror" in lowered:
        return "proxy_failure"
    if "secondary user id" in lowered:
        return "identity_unavailable"
    if "timed out" in lowered:
        return "timeout"
    if "connection closed" in lowered or "curl: (56)" in lowered:
        return "connection_closed"
    return "extractor_failure"


_TIKTOK_SUCCESS_HINT: tuple[str, bool] | None = None


def _tiktok_cursor_from_items(items: list[dict[str, Any]]) -> int | None:
    """Return the oldest known TikTok timestamp in milliseconds.

    TikTok's creator item API uses a timestamp cursor and returns posts older
    than that cursor. Older Media2MD checkpoints only have normalized ISO
    timestamps, so v0.8.0 can migrate them without replaying hundreds of
    playlist entries through yt-dlp.
    """
    values: list[int] = []
    for item in items:
        text = str(item.get("published_at") or "").strip()
        if not text:
            continue
        try:
            parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=timezone.utc)
            values.append(int(parsed.timestamp() * 1000))
        except (TypeError, ValueError, OSError):
            continue
    return min(values) if values else None


def _tiktok_device_id() -> str:
    return str(random.randint(7250000000000000000, 7325099899999994577))


def _tiktok_cursor_query(sec_uid: str, cursor: int, count: int, device_id: str) -> dict[str, str | int]:
    """Build the same cursor query used by yt-dlp's TikTokUserIE.

    Media2MD persists ``cursor`` and ``device_id`` in its checkpoint so each
    run resumes from the oldest known post instead of using --playlist-start,
    which makes every new process replay all earlier TikTok pages.
    """
    return {
        "aid": "1988",
        "app_language": "en",
        "app_name": "tiktok_web",
        "browser_language": "en-US",
        "browser_name": "Mozilla",
        "browser_online": "true",
        "browser_platform": "MacIntel",
        "browser_version": "5.0 (Macintosh)",
        "channel": "tiktok_web",
        "cookie_enabled": "true",
        "count": str(count),
        "cursor": cursor,
        "device_id": device_id,
        "device_platform": "web_pc",
        "focus_state": "true",
        "from_page": "user",
        "history_len": "2",
        "is_fullscreen": "false",
        "is_page_visible": "true",
        "language": "en",
        "os": "mac",
        "priority_region": "",
        "referer": "",
        "region": "US",
        "screen_height": "1080",
        "screen_width": "1920",
        "secUid": sec_uid,
        "type": "1",
        "tz_name": "UTC",
        "verifyFp": f'verify_{"".join(random.choices(string.hexdigits.lower(), k=7))}',
        "webcast_language": "en",
    }


def _normalize_tiktok_cursor_item(raw: dict[str, Any], handle_hint: str) -> dict[str, Any] | None:
    external_id = str(raw.get("id") or "").strip()
    if not external_id:
        return None
    author = raw.get("author") if isinstance(raw.get("author"), dict) else {}
    video = raw.get("video") if isinstance(raw.get("video"), dict) else {}
    handle = str(author.get("uniqueId") or handle_hint).strip().lstrip("@") or handle_hint
    timestamp = raw.get("createTime")
    published_at = None
    try:
        published_at = datetime.fromtimestamp(float(timestamp), tz=timezone.utc).isoformat(timespec="seconds")
    except (TypeError, ValueError, OSError):
        pass
    duration = video.get("duration")
    return {
        "external_id": external_id,
        "title": str(raw.get("desc") or external_id),
        "description": str(raw.get("desc") or ""),
        "source_url": f"https://www.tiktok.com/@{handle}/video/{external_id}",
        "published_at": published_at,
        "duration_seconds": duration,
        "media_type": "tiktok_video",
        "processing_class": processing_class(
            "tiktok_video", duration, long_threshold_seconds=youtube_long_threshold_seconds()
        ),
        "catalog_surface": None,
    }


def _run_tiktok_cursor_request(
    sec_uid: str,
    cursor: int,
    count: int,
    device_id: str,
    source_url: str,
    *,
    timeout_seconds: int,
) -> tuple[dict[str, Any], bool]:
    """Fetch one native TikTok cursor page with macOS system proxy bypassed.

    This intentionally uses the OS curl binary rather than curl-cffi. The live
    StartupBell tests showed curl-cffi repeatedly failing inside BoringSSL while
    ``--proxy ''``/direct transport could succeed. Cookie and public modes are
    both bounded by one request deadline.
    """
    query = urllib.parse.urlencode(_tiktok_cursor_query(sec_uid, cursor, count, device_id))
    endpoint = f"https://www.tiktok.com/api/creator/item_list/?{query}"
    cookie_args = auth_args("tiktok")
    cookie_file = None
    if len(cookie_args) >= 2 and cookie_args[0] == "--cookies":
        cookie_file = cookie_args[1]
    direct_env, _ = _proxy_environment()
    modes = [False] + ([True] if cookie_file else [])
    errors: list[str] = []
    for authenticated in modes:
        cmd = [
            command("curl"), "--fail", "--silent", "--show-error", "--location", "--compressed",
            "--connect-timeout", str(min(20, timeout_seconds)),
            "--max-time", str(timeout_seconds), "--noproxy", "*",
            "--user-agent", (
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/146.0.0.0 Safari/537.36"
            ),
            "--header", "Accept: application/json, text/plain, */*",
            "--header", f"Referer: {source_url}",
        ]
        if authenticated and cookie_file:
            cmd += ["--cookie", cookie_file]
        cmd.append(endpoint)
        print(
            "SYNC_CURSOR_ATTEMPT provider=tiktok backend=native-curl "
            f"authenticated={str(authenticated).lower()} cursor={cursor} count={count} "
            f"timeout_seconds={timeout_seconds}",
            flush=True,
        )
        started = time.monotonic()
        try:
            result = _capture_process(
                cmd, timeout_seconds,
                heartbeat_context=(
                    "provider=tiktok backend=native-curl "
                    f"cursor={cursor} authenticated={str(authenticated).lower()}"
                ),
                heartbeat_interval=max(5.0, float(os.getenv("MEDIA2MD_SYNC_HEARTBEAT_SECONDS", "30"))),
                env=direct_env,
            )
        except subprocess.TimeoutExpired:
            elapsed_seconds = int(time.monotonic() - started)
            errors.append(f"auth={authenticated}: timeout")
            print(
                "SYNC_CURSOR_ATTEMPT_RESULT provider=tiktok backend=native-curl "
                f"authenticated={str(authenticated).lower()} status=failed reason=timeout "
                f"elapsed_seconds={elapsed_seconds}",
                flush=True,
            )
            continue
        if result.returncode != 0:
            elapsed_seconds = int(time.monotonic() - started)
            error_text = (result.stderr or result.stdout)[-1000:]
            lower_error = error_text.lower()
            reason = "timeout" if "timed out" in lower_error else "connection_closed" if ("connection" in lower_error or "reset" in lower_error) else "http_error"
            errors.append(f"auth={authenticated}: {error_text}")
            print(
                "SYNC_CURSOR_ATTEMPT_RESULT provider=tiktok backend=native-curl "
                f"authenticated={str(authenticated).lower()} status=failed reason={reason} "
                f"elapsed_seconds={elapsed_seconds}",
                flush=True,
            )
            continue
        try:
            payload = json.loads(result.stdout)
        except json.JSONDecodeError as exc:
            elapsed_seconds = int(time.monotonic() - started)
            errors.append(f"auth={authenticated}: invalid_json={exc}")
            print(
                "SYNC_CURSOR_ATTEMPT_RESULT provider=tiktok backend=native-curl "
                f"authenticated={str(authenticated).lower()} status=failed reason=invalid_json "
                f"elapsed_seconds={elapsed_seconds}",
                flush=True,
            )
            continue
        if not isinstance(payload, dict):
            elapsed_seconds = int(time.monotonic() - started)
            errors.append(f"auth={authenticated}: non_object_response")
            print(
                "SYNC_CURSOR_ATTEMPT_RESULT provider=tiktok backend=native-curl "
                f"authenticated={str(authenticated).lower()} status=failed reason=invalid_response "
                f"elapsed_seconds={elapsed_seconds}",
                flush=True,
            )
            continue
        status_code = payload.get("statusCode")
        if status_code not in (None, 0, "0"):
            elapsed_seconds = int(time.monotonic() - started)
            errors.append(f"auth={authenticated}: statusCode={status_code}")
            print(
                "SYNC_CURSOR_ATTEMPT_RESULT provider=tiktok backend=native-curl "
                f"authenticated={str(authenticated).lower()} status=failed reason=api_status "
                f"elapsed_seconds={elapsed_seconds}",
                flush=True,
            )
            continue
        print(
            "SYNC_CURSOR_ATTEMPT_RESULT provider=tiktok backend=native-curl "
            f"authenticated={str(authenticated).lower()} status=success "
            f"elapsed_seconds={int(time.monotonic()-started)}",
            flush=True,
        )
        return payload, authenticated
    raise RuntimeError("TikTok native cursor request failed. " + " | ".join(errors)[-3000:])


def _tiktok_cursor_bootstrap_from_registry(handle: str, source_url: str) -> tuple[dict[str, Any], list[str]] | None:
    """Recover stable TikTok identity for a fresh exact rebuild.

    A completed cursor scan deletes its checkpoint. The next explicit Full Sync
    must start a new cursor walk from the present, not fall back to legacy
    ``--playlist-start`` extraction. Registry identity is enough to bootstrap
    that fresh scan while the previous exact catalog remains available until the
    replacement scan reaches its terminal page.
    """
    conn = connect()
    row = conn.execute(
        "SELECT * FROM creators WHERE provider='tiktok' AND lower(handle)=lower(?)",
        (handle,),
    ).fetchone()
    if not row:
        conn.close()
        return None
    identifier_rows = conn.execute(
        "SELECT identifier_type,identifier_value FROM creator_identifiers WHERE creator_id=?",
        (int(row["id"]),),
    ).fetchall()
    identifier_map = {str(item["identifier_type"]): str(item["identifier_value"]) for item in identifier_rows}
    conn.close()
    candidates = [
        identifier_map.get("sec_uid"),
        str(row["external_id"] or ""),
        identifier_map.get("primary"),
    ]
    sec_uid = next((value for value in candidates if value and str(value).startswith("MS4wLjAB")), None)
    if not sec_uid:
        return None
    identifiers = [str(sec_uid)]
    user_id = identifier_map.get("user_id")
    if user_id:
        identifiers.append(str(user_id))
    meta = {
        "external_id": str(sec_uid),
        "handle": str(row["handle"] or handle),
        "display_name": str(row["display_name"] or row["handle"] or handle),
        "source_url": str(row["source_url"] or source_url),
        "identifiers": {**identifier_map, "sec_uid": str(sec_uid)},
    }
    return meta, identifiers


def _cursor_run_snapshot(handle: str) -> dict[str, Any]:
    conn = connect()
    row = conn.execute(
        "SELECT * FROM creators WHERE provider='tiktok' AND lower(handle)=lower(?)",
        (handle,),
    ).fetchone()
    if not row:
        conn.close()
        return {
            "current_total": 0, "current_total_exact": False,
            "media_type_totals": {"tiktok_video": 0},
        }
    creator_id = int(row["id"])
    count = int(conn.execute(
        "SELECT COUNT(*) FROM media WHERE creator_id=? AND is_current=1 AND media_type='tiktok_video'",
        (creator_id,),
    ).fetchone()[0])
    snapshot = {
        "current_total": int(row["current_total"] or count),
        "current_total_exact": bool(row["current_total_exact"]),
        "media_type_totals": {"tiktok_video": count},
    }
    conn.close()
    return snapshot


def _apply_cursor_run_snapshot(summary: dict[str, Any], snapshot: dict[str, Any]) -> dict[str, Any]:
    previous_total = int(snapshot.get("current_total") or 0)
    current_total = int(summary.get("current_total") or 0)
    summary["previous_current_total"] = previous_total
    summary["previous_current_total_exact"] = bool(snapshot.get("current_total_exact"))
    summary["previous_media_type_totals"] = dict(snapshot.get("media_type_totals") or {"tiktok_video": previous_total})
    summary["new_since_last_sync"] = max(0, current_total - previous_total)
    summary["removed_since_last_sync"] = max(0, previous_total - current_total)
    if summary.get("current_total_exact") and summary.get("last_full_exact_total") is not None:
        summary.setdefault("last_full_media_type_totals", {})["tiktok_video"] = int(summary["last_full_exact_total"] or 0)
    return summary


def _tiktok_existing_catalog_summary(
    handle: str,
    meta: dict[str, Any],
    *,
    sync_mode: str = "rebuild_partial",
) -> dict[str, Any]:
    """Read the currently published TikTok catalog without mutating it.

    A fresh Full rebuild is staged in its checkpoint. Until the rebuild reaches
    the terminal cursor page, the last exact catalog remains the active catalog.
    This helper produces the pause/reporting payload without calling
    ``upsert_catalog(... exact=False)``, which would otherwise downgrade the
    proven baseline merely because a refresh request timed out or was rejected.
    """
    conn = connect()
    row = conn.execute(
        "SELECT * FROM creators WHERE provider='tiktok' AND lower(handle)=lower(?)",
        (handle,),
    ).fetchone()
    if not row:
        conn.close()
        raise RuntimeError(f"TikTok creator missing while reporting staged rebuild: {handle}")
    creator_id = int(row["id"])
    count = int(conn.execute(
        "SELECT COUNT(*) FROM media WHERE creator_id=? AND is_current=1 AND media_type='tiktok_video'",
        (creator_id,),
    ).fetchone()[0])
    date_row = conn.execute(
        "SELECT MAX(published_at) newest, MIN(published_at) oldest FROM media "
        "WHERE creator_id=? AND is_current=1 AND media_type='tiktok_video'",
        (creator_id,),
    ).fetchone()
    identifiers = {
        str(item["identifier_type"]): str(item["identifier_value"])
        for item in conn.execute(
            "SELECT identifier_type,identifier_value FROM creator_identifiers WHERE creator_id=?",
            (creator_id,),
        ).fetchall()
    }
    summary = {
        "provider": "tiktok",
        "creator": str(row["handle"] or handle),
        "creator_id": creator_id,
        "external_creator_id": str(row["external_id"] or meta.get("external_id") or handle),
        "sync_mode": sync_mode,
        "previous_current_total": int(row["current_total"] or count),
        "previous_current_total_exact": bool(row["current_total_exact"]),
        "current_total": int(row["current_total"] or count),
        "current_total_exact": bool(row["current_total_exact"]),
        "new_since_last_sync": 0,
        "removed_since_last_sync": 0,
        "newest": date_row["newest"] if date_row else None,
        "oldest": date_row["oldest"] if date_row else None,
        "creator_identifiers": {**identifiers, **(meta.get("identifiers") or {})},
        "media_type_totals": {"tiktok_video": count},
        "media_type_totals_exact": {"tiktok_video": bool(row["current_total_exact"])},
        "youtube_video_total": 0,
        "youtube_video_total_exact": False,
        "youtube_shorts_total": 0,
        "youtube_shorts_total_exact": False,
        "youtube_streams_total": 0,
        "youtube_streams_total_exact": False,
        "previous_media_type_totals": {"tiktok_video": count},
        "last_full_exact_total": row["last_full_exact_total"],
        "last_full_exact_at": row["last_full_exact_at"],
        "last_full_media_type_totals": {
            "youtube_video": int(row["last_full_youtube_video_total"] or 0),
            "youtube_short": int(row["last_full_youtube_shorts_total"] or 0),
            "youtube_stream": int(row["last_full_youtube_streams_total"] or 0),
            **({"tiktok_video": int(row["last_full_exact_total"] or 0)}
               if row["last_full_exact_total"] is not None else {}),
        },
    }
    conn.close()
    return summary


def _sync_tiktok_cursor_catalog(
    *,
    handle: str,
    source_url: str,
    checkpoint_path: Path,
    checkpoint: dict[str, Any],
    collected: list[dict[str, Any]],
    meta: dict[str, Any],
    identifiers: list[str],
    sync_started: float,
    sync_runtime_budget: int,
    sync_max_pages: int,
) -> dict[str, Any]:
    sec_uid = next((value for value in identifiers if str(value).startswith("MS4wLjAB")), None)
    if not sec_uid:
        raise RuntimeError("TikTok cursor backend requires a recovered secUid")
    run_snapshot = _cursor_run_snapshot(handle)
    preserve_exact_baseline = bool(
        checkpoint.get("rebuild_from_exact")
        or (run_snapshot.get("current_total_exact") and not collected)
    )
    checkpoint["rebuild_from_exact"] = preserve_exact_baseline
    cursor = checkpoint.get("tiktok_cursor")
    if cursor is None:
        cursor = _tiktok_cursor_from_items(collected)
        if cursor is None:
            raise RuntimeError("TikTok cursor backend could not derive cursor from checkpoint items")
        print(
            "SYNC_CURSOR_RECOVERED provider=tiktok source=oldest_known_item "
            f"cursor={cursor} known_items={len(collected)}",
            flush=True,
        )
    cursor = int(cursor)
    cursor_state = _load_tiktok_cursor_state(handle)
    device_id = str(
        checkpoint.get("tiktok_device_id")
        or cursor_state.get("device_id")
        or _tiktok_device_id()
    )
    try:
        count = max(10, min(30, int(os.getenv("MEDIA2MD_TIKTOK_CURSOR_PAGE_SIZE", "15"))))
    except ValueError:
        count = 15
    pages_completed = 0
    by_id = {item["external_id"]: item for item in collected if item.get("external_id")}
    seen_page_signatures: set[tuple[str, ...]] = set()
    print(
        "SYNC_CURSOR_MODE provider=tiktok backend=native-curl resumable=true "
        f"cursor={cursor} count={count} known_items={len(collected)} "
        f"staged_rebuild={str(preserve_exact_baseline).lower()}",
        flush=True,
    )

    def pause_summary(reason: str, *, elapsed_seconds: int, last_page_error: str | None = None) -> dict[str, Any]:
        if preserve_exact_baseline:
            summary = _tiktok_existing_catalog_summary(handle, meta)
        else:
            summary = upsert_catalog(
                provider="tiktok", requested_handle=handle, source_url=source_url,
                items=collected, meta=meta, sync_mode="partial", exact=False,
            )
        summary.update({
            "sync_incomplete": True,
            "pause_reason": reason,
            "resume_from": len(collected) + 1,
            "pages_completed_this_run": pages_completed,
            "run_elapsed_seconds": elapsed_seconds,
            "pagination_backend": "cursor_api",
            "tiktok_cursor": cursor,
            "rebuild_in_progress": preserve_exact_baseline,
            "staged_total": len(collected),
            "baseline_preserved": preserve_exact_baseline,
        })
        if last_page_error:
            summary["last_page_error"] = last_page_error
        return _apply_cursor_run_snapshot(summary, run_snapshot)

    while True:
        elapsed = time.monotonic() - sync_started
        if elapsed >= sync_runtime_budget or (sync_max_pages > 0 and pages_completed >= sync_max_pages):
            reason = "runtime_budget" if elapsed >= sync_runtime_budget else "max_pages_per_run"
            summary = pause_summary(reason, elapsed_seconds=int(elapsed))
            print(
                "SYNC_RUN_PAUSED provider=tiktok "
                f"reason={reason} elapsed_seconds={int(elapsed)} pages_completed={pages_completed} "
                f"known_items={len(collected)} resume_from={len(collected)+1} "
                f"exact={str(bool(summary.get('current_total_exact'))).lower()} "
                f"baseline_preserved={str(preserve_exact_baseline).lower()} "
                f"cursor={cursor} backend=cursor_api",
                flush=True,
            )
            return summary
        remaining_float = sync_runtime_budget - elapsed
        if remaining_float < 5.0:
            atomic_json(checkpoint_path, {
                **checkpoint,
                "schema_version": 5, "provider": "tiktok", "creator": handle,
                "source_url": source_url, "mode": "full", "meta": meta,
                "tiktok_identifiers": identifiers, "items": collected,
                "next_start": len(collected) + 1, "tiktok_cursor": cursor,
                "tiktok_device_id": device_id, "pagination_backend": "cursor_api",
                "rebuild_from_exact": preserve_exact_baseline,
                "updated_at": iso_now(),
            })
            summary = pause_summary(
                "runtime_budget", elapsed_seconds=int(time.monotonic() - sync_started)
            )
            print(
                "SYNC_RUN_PAUSED provider=tiktok reason=runtime_budget "
                f"known_items={len(collected)} resume_from={len(collected)+1} "
                f"cursor={cursor} exact={str(bool(summary.get('current_total_exact'))).lower()} "
                f"baseline_preserved={str(preserve_exact_baseline).lower()} backend=cursor_api",
                flush=True,
            )
            return summary
        request_timeout = min(90, max(5, int(remaining_float)))
        try:
            payload, authenticated = _run_tiktok_cursor_request(
                sec_uid, cursor, count, device_id, source_url, timeout_seconds=request_timeout
            )
            _save_tiktok_cursor_state(handle, device_id=device_id, authenticated=authenticated)
        except Exception as exc:
            atomic_json(checkpoint_path, {
                **checkpoint,
                "schema_version": 5, "provider": "tiktok", "creator": handle,
                "source_url": source_url, "mode": "full", "meta": meta,
                "tiktok_identifiers": identifiers, "items": collected,
                "next_start": len(collected) + 1, "tiktok_cursor": cursor,
                "tiktok_device_id": device_id, "pagination_backend": "cursor_api",
                "rebuild_from_exact": preserve_exact_baseline,
                "updated_at": iso_now(),
            })
            summary = pause_summary(
                "cursor_request_failed",
                elapsed_seconds=int(time.monotonic() - sync_started),
                last_page_error=str(exc)[-2000:],
            )
            print(
                "SYNC_RUN_PAUSED provider=tiktok reason=cursor_request_failed "
                f"known_items={len(collected)} resume_from={len(collected)+1} "
                f"cursor={cursor} exact={str(bool(summary.get('current_total_exact'))).lower()} "
                f"baseline_preserved={str(preserve_exact_baseline).lower()} backend=cursor_api",
                flush=True,
            )
            return summary
        raw_items = payload.get("itemList") if isinstance(payload.get("itemList"), list) else []
        signature = tuple(sorted(str(item.get("id") or "") for item in raw_items if isinstance(item, dict)))
        if signature and signature in seen_page_signatures:
            print(
                "SYNC_RUN_PAUSED provider=tiktok reason=repeated_cursor_page "
                f"known_items={len(collected)} cursor={cursor} exact=false",
                flush=True,
            )
            summary = pause_summary(
                "repeated_cursor_page", elapsed_seconds=int(time.monotonic() - sync_started)
            )
            return summary
        if signature:
            seen_page_signatures.add(signature)
        new_unique = 0
        normalized_page: list[dict[str, Any]] = []
        for raw in raw_items:
            if not isinstance(raw, dict):
                continue
            item = _normalize_tiktok_cursor_item(raw, handle)
            if not item:
                continue
            normalized_page.append(item)
            if item["external_id"] not in by_id:
                new_unique += 1
            by_id[item["external_id"]] = item
        collected = merge_catalog_items(by_id.values())
        old_cursor = cursor
        create_times = [
            int(raw.get("createTime")) for raw in raw_items
            if isinstance(raw, dict) and str(raw.get("createTime") or "").isdigit()
        ]
        if create_times:
            cursor = min(create_times) * 1000
        elif payload.get("cursor") is not None:
            cursor = int(payload["cursor"])
        else:
            cursor = old_cursor - 7 * 86_400_000
        has_more = bool(payload.get("hasMorePrevious"))
        pages_completed += 1
        author = next((raw.get("author") for raw in raw_items if isinstance(raw, dict) and isinstance(raw.get("author"), dict)), {})
        meta = {
            **meta,
            "external_id": sec_uid, "handle": handle, "source_url": source_url,
            "display_name": str(author.get("nickname") or meta.get("display_name") or handle),
            "identifiers": {**(meta.get("identifiers") or {}), "sec_uid": sec_uid,
                            **({"user_id": str(author.get("id"))} if author.get("id") else {})},
        }
        checkpoint = {
            "schema_version": 5, "provider": "tiktok", "creator": handle,
            "source_url": source_url, "catalog_source": "creator_item_list_cursor",
            "mode": "full", "meta": meta, "tiktok_identifiers": identifiers,
            "preferred_transport": "native-curl", "preferred_authenticated": authenticated,
            "items": collected, "next_start": len(collected) + 1,
            "tiktok_cursor": cursor, "tiktok_device_id": device_id,
            "pagination_backend": "cursor_api",
            "rebuild_from_exact": preserve_exact_baseline,
            "updated_at": iso_now(),
        }
        atomic_json(checkpoint_path, checkpoint)
        if not preserve_exact_baseline:
            upsert_catalog("tiktok", handle, source_url, collected, meta, "partial", exact=False)
        print(
            "SYNC_CURSOR_PAGE_DONE provider=tiktok "
            f"fetched={len(normalized_page)} new_unique={new_unique} known_items={len(collected)} "
            f"cursor_before={old_cursor} cursor_after={cursor} "
            f"has_more={str(has_more).lower()} pages_completed={pages_completed} "
            f"staged_rebuild={str(preserve_exact_baseline).lower()}",
            flush=True,
        )
        if not has_more:
            summary = upsert_catalog("tiktok", handle, source_url, collected, meta, "full", exact=True)
            checkpoint_path.unlink(missing_ok=True)
            summary.update({"pagination_backend": "cursor_api", "pages_completed_this_run": pages_completed})
            print(
                "SYNC_CURSOR_COMPLETE provider=tiktok "
                f"current_total={len(collected)} exact=true pages_completed={pages_completed}",
                flush=True,
            )
            return _apply_cursor_run_snapshot(summary, run_snapshot)


def _run_tiktok_catalog(
    common: list[str],
    source_url: str,
    *,
    deadline: float | None = None,
    context: str | None = None,
    emit_network_context: bool = True,
    page_state: dict[str, Any] | None = None,
) -> tuple[dict[str, Any], str, bool]:
    """Run one bounded TikTok extraction attempt plan.

    The deadline is shared by every transport and auth mode for this catalog
    page. A timeout is therefore a page budget, not a fresh timeout for every
    fallback. The last successful strategy is tried first on the next page.
    """
    global _TIKTOK_SUCCESS_HINT
    errors: list[str] = []
    auth = auth_args("tiktok")
    strategies = _tiktok_transport_strategies()
    if _TIKTOK_SUCCESS_HINT:
        preferred_name, _ = _TIKTOK_SUCCESS_HINT
        strategies = sorted(strategies, key=lambda item: 0 if item[0] == preferred_name else 1)
    per_attempt_cap = max(15, int(os.getenv("MEDIA2MD_TIKTOK_EXTRACT_TIMEOUT_SECONDS", "120")))
    heartbeat_seconds = max(5.0, float(os.getenv("MEDIA2MD_SYNC_HEARTBEAT_SECONDS", "30")))
    if deadline is None:
        page_budget = max(60, int(os.getenv("MEDIA2MD_TIKTOK_PAGE_BUDGET_SECONDS", "300")))
        deadline = time.monotonic() + page_budget
    direct_env, removed_proxy_keys = _proxy_environment()
    config_proxy_files = _yt_dlp_proxy_config_files()
    system_proxy_kinds = _macos_system_proxy_kinds()
    if emit_network_context:
        print(
            "SYNC_NETWORK_CONTEXT provider=tiktok "
            f"proxy_env_keys={','.join(removed_proxy_keys) if removed_proxy_keys else '-'} "
            f"yt_dlp_proxy_configs={','.join(config_proxy_files) if config_proxy_files else '-'} "
            f"macos_system_proxy={','.join(system_proxy_kinds) if system_proxy_kinds else '-'} "
            "direct_strategy_forces_proxy_empty=true "
            f"strategy_count={len(strategies)}",
            file=sys.stderr,
            flush=True,
        )
    page_state = page_state if page_state is not None else {}
    tls_failures = int(page_state.get("tls_failures", 0) or 0)
    breaker_open = bool(page_state.get("breaker_open", False))
    attempts = int(page_state.get("attempts", 0) or 0)
    for strategy_item in strategies:
        if len(strategy_item) == 2:
            name, transport_args = strategy_item
            direct = name in {"plain", "direct-plain"} and not transport_args
        else:
            name, transport_args, direct = strategy_item
        if breaker_open and not direct:
            print(
                f"SYNC_TRANSPORT_SKIPPED provider=tiktok strategy={name} reason=tls_circuit_open",
                file=sys.stderr,
                flush=True,
            )
            continue
        modes = [False] + ([True] if auth else [])
        if _TIKTOK_SUCCESS_HINT and _TIKTOK_SUCCESS_HINT[0] == name:
            preferred_auth = _TIKTOK_SUCCESS_HINT[1]
            modes = [preferred_auth] + [mode for mode in modes if mode != preferred_auth]
        for authenticated in modes:
            remaining = deadline - time.monotonic()
            if remaining < 5.0:
                combined = " | ".join(errors)[-5000:]
                page_state.update({
                    "tls_failures": tls_failures,
                    "breaker_open": breaker_open,
                    "attempts": attempts,
                })
                raise RuntimeError(
                    "TikTok page budget exhausted before another extractor could start. "
                    f"attempts={attempts} context={context or '-'} remaining_seconds={max(0, int(remaining))} "
                    f"errors={combined}"
                )
            attempts += 1
            page_state["attempts"] = attempts
            strategy_env = direct_env if direct else None
            timeout_seconds = min(per_attempt_cap, max(1, int(remaining)))
            print(
                f"SYNC_TRANSPORT_ATTEMPT provider=tiktok strategy={name} "
                f"authenticated={str(authenticated).lower()} direct={str(direct).lower()} "
                f"attempt_timeout_seconds={timeout_seconds} "
                f"page_budget_remaining_seconds={max(0, int(remaining))}",
                file=sys.stderr,
                flush=True,
            )
            command_line = [common[0], *transport_args, *common[1:]]
            if authenticated:
                command_line += auth
            command_line.append(source_url)
            started = time.monotonic()
            try:
                payload = run_json(
                    command_line,
                    timeout=timeout_seconds,
                    delays=[0],
                    strategy=f"{name}+auth" if authenticated else name,
                    heartbeat_context=(
                        f"provider=tiktok {context or ''} strategy={name} "
                        f"authenticated={str(authenticated).lower()}"
                    ).strip(),
                    heartbeat_interval=heartbeat_seconds,
                    env=strategy_env,
                )
                _TIKTOK_SUCCESS_HINT = (name, authenticated)
                page_state.update({
                    "tls_failures": tls_failures,
                    "breaker_open": breaker_open,
                    "attempts": attempts,
                    "preferred_transport": name,
                    "preferred_authenticated": authenticated,
                })
                print(
                    f"SYNC_ATTEMPT_RESULT provider=tiktok strategy={name} "
                    f"authenticated={str(authenticated).lower()} status=success "
                    f"elapsed_seconds={int(time.monotonic()-started)}",
                    file=sys.stderr,
                    flush=True,
                )
                return payload, name, authenticated
            except RuntimeError as exc:
                error = str(exc)
                reason = _tiktok_error_reason(error)
                errors.append(f"{name}/{'auth' if authenticated else 'public'}: {error}")
                print(
                    f"SYNC_ATTEMPT_RESULT provider=tiktok strategy={name} "
                    f"authenticated={str(authenticated).lower()} status=failed "
                    f"reason={reason} elapsed_seconds={int(time.monotonic()-started)}",
                    file=sys.stderr,
                    flush=True,
                )
                if _tiktok_tls_error_text(error):
                    tls_failures += 1
                    page_state["tls_failures"] = tls_failures
                if tls_failures >= 2 and not direct:
                    breaker_open = True
                    page_state["breaker_open"] = True
                    print(
                        "SYNC_CIRCUIT_BREAKER provider=tiktok "
                        f"reason=repeated_tls_failure count={tls_failures} "
                        "action=skip_remaining_impersonation",
                        file=sys.stderr,
                        flush=True,
                    )
                    break
    combined = " | ".join(errors)[-7000:]
    if time.monotonic() >= deadline:
        raise RuntimeError(
            "TikTok page budget exhausted after transport fallbacks. "
            f"attempts={attempts} context={context or '-'} errors={combined}"
        )
    if any(_tiktok_transport_error_text(item) for item in errors):
        raise RuntimeError(
            "TikTok transport strategies exhausted. root_cause=network_transport_or_proxy_failure. "
            + combined
        )
    raise RuntimeError("TikTok transport strategies exhausted. " + combined)

def _extract_catalog_once(
    provider: str,
    source_url: str,
    limit: int | None,
    start: int | None,
    *,
    tiktok_deadline: float | None = None,
    tiktok_context: str | None = None,
    emit_network_context: bool = True,
    tiktok_handle_hint: str | None = None,
    tiktok_profile_url_hint: str | None = None,
    tiktok_page_state: dict[str, Any] | None = None,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    surface = youtube_surface_from_url(source_url) if provider == "youtube" else None
    surface_media_type = media_type_for_youtube_surface(surface) if surface else None
    threshold = youtube_long_threshold_seconds()
    base = [command("yt-dlp")]
    if provider == "youtube":
        base += youtube_runtime_args()
    base += ["--flat-playlist", "--dump-single-json", "--ignore-errors", "--no-warnings"]
    if start:
        base += ["--playlist-start", str(start)]
    if limit:
        base += ["--playlist-end", str((start or 1) + limit - 1)]
    transport_strategy = None
    transport_authenticated = False
    if provider == "tiktok":
        payload, transport_strategy, transport_authenticated = _run_tiktok_catalog(
            base, source_url, deadline=tiktok_deadline, context=tiktok_context,
            emit_network_context=emit_network_context, page_state=tiktok_page_state
        )
    else:
        public_cmd = [*base, source_url]
        try:
            payload = run_json(public_cmd, timeout=3600)
        except RuntimeError as public_exc:
            if provider == "youtube" and auth_args("youtube"):
                auth = verify_youtube_session(persist=True)
                if not auth.get("authenticated"):
                    state = auth.get("auth_state") or "unknown"
                    action = auth.get("required_action") or "reauthenticate_youtube_in_selected_profile"
                    raise RuntimeError(
                        f"[stage=sync] [error_code=youtube_auth_unverified] [retryable=false] "
                        f"[action_required=true] [required_action={action}] "
                        f"YouTube catalog auth preflight failed: auth_state={state}"
                    ) from public_exc
                payload = run_json([*base, *auth_args("youtube"), source_url], timeout=3600)
            elif provider != "youtube":
                payload = run_json([*base, *auth_args(provider), source_url], timeout=3600)
            else:
                raise
    entries = payload.get("entries") or []
    profile_url = tiktok_profile_url_hint if provider == "tiktok" and tiktok_profile_url_hint else source_url
    meta = _profile_meta(
        provider, payload, profile_url,
        handle_hint=tiktok_handle_hint if provider == "tiktok" else None,
    )
    if provider == "tiktok":
        meta["transport_strategy"] = transport_strategy
        meta["transport_authenticated"] = transport_authenticated
    normalized: list[dict[str, Any]] = []
    for raw in entries:
        if not isinstance(raw, dict):
            continue
        external_id = str(raw.get("id") or "").strip()
        if not external_id:
            continue
        if provider == "youtube":
            url = raw.get("webpage_url") or raw.get("url")
            if not (isinstance(url, str) and url.startswith("http")):
                url = f"https://www.youtube.com/watch?v={external_id}"
        else:
            handle = meta["handle"]
            url = raw.get("webpage_url") or f"https://www.tiktok.com/@{handle}/video/{external_id}"
            match = re.search(r"tiktok\.com/@([A-Za-z0-9._-]+)/video/(\d+)", str(url), re.I)
            if match:
                url = f"https://www.tiktok.com/@{match.group(1)}/video/{match.group(2)}"
        media_type = infer_media_type(provider, str(url), hinted=surface_media_type)
        duration = raw.get("duration")
        normalized.append({
            "external_id": external_id,
            "title": str(raw.get("title") or external_id),
            "description": str(raw.get("description") or ""),
            "source_url": str(url).split("?", 1)[0].split("#", 1)[0],
            "published_at": parse_timestamp(raw),
            "duration_seconds": duration,
            "media_type": media_type,
            "processing_class": processing_class(media_type, duration, long_threshold_seconds=threshold),
            "catalog_surface": surface,
        })
    normalized.sort(key=lambda x: (x.get("published_at") or "", x["external_id"]), reverse=True)
    return meta, normalized


def _tiktok_identity_from_media_url(source_url: str) -> tuple[str, dict[str, str]] | None:
    try:
        target = normalize_media_target("tiktok", source_url, creator="_")
        video_id = str(target.media_id)
    except Exception:
        match = re.search(r"/video/(\d+)", source_url)
        if not match:
            return None
        video_id = match.group(1)
    probe_url = f"https://www.tiktok.com/@_/video/{video_id}"
    common = [
        command("yt-dlp"),
        "--dump-single-json",
        "--skip-download",
        "--no-playlist",
        "--no-warnings",
    ]
    try:
        payload, _, _ = _run_tiktok_catalog(common, probe_url)
    except Exception:
        return None
    handle = str(payload.get("uploader") or payload.get("channel") or "").lstrip("@")
    identifiers: dict[str, str] = {}
    sec_uid = str(payload.get("channel_id") or "").strip()
    user_id = str(payload.get("uploader_id") or payload.get("creator_id") or "").strip()
    if sec_uid: identifiers["sec_uid"] = sec_uid
    if user_id: identifiers["user_id"] = user_id
    return (handle, identifiers) if handle else None


def _tiktok_fallback_identifiers(handle: str) -> list[str]:
    conn = connect()
    creator = conn.execute("SELECT * FROM creators WHERE provider='tiktok' AND handle=? COLLATE NOCASE", (handle,)).fetchone()
    values: list[str] = []
    if creator:
        rows = conn.execute(
            "SELECT identifier_type,identifier_value FROM creator_identifiers WHERE creator_id=? "
            "ORDER BY CASE identifier_type WHEN 'sec_uid' THEN 0 WHEN 'channel_id' THEN 1 WHEN 'user_id' THEN 2 ELSE 3 END",
            (creator["id"],),
        ).fetchall()
        values.extend(str(row["identifier_value"]) for row in rows if row["identifier_value"])
        external = str(creator["external_id"] or "")
        if external and external.lower() != handle.lower():
            values.append(external)
        if not values:
            media = conn.execute("SELECT source_url FROM media WHERE creator_id=? ORDER BY id LIMIT 1", (creator["id"],)).fetchone()
            if media:
                resolved = _tiktok_identity_from_media_url(str(media["source_url"]))
                if resolved:
                    resolved_handle, identifiers = resolved
                    updated = upsert_creator_identity(conn, "tiktok", identifiers.get("sec_uid") or identifiers.get("user_id") or handle, resolved_handle or handle, resolved_handle or handle, creator["source_url"], identifiers=identifiers)
                    values.extend(identifiers.values())
    conn.commit()
    conn.close()
    deduped: list[str] = []
    for value in values:
        if value and value not in deduped:
            deduped.append(value)
    return deduped


def _tiktok_identifiers_from_page(meta: dict[str, Any], items: list[dict[str, Any]]) -> list[str]:
    """Return stable TikTok profile identifiers learned during the current sync.

    Initial handle-based extraction can work for early pages and later fail when
    TikTok stops exposing the secondary user ID. Persist a secUid/user ID from
    the first successful page, or recover it from one discovered video, so later
    pages can use yt-dlp's stable ``tiktokuser:<id>`` target.
    """
    values: list[str] = []
    identifiers = dict(meta.get("identifiers") or {})
    for key in ("sec_uid", "channel_id", "user_id"):
        value = str(identifiers.get(key) or "").strip()
        if value and value not in values:
            values.append(value)
    external = str(meta.get("external_id") or "").strip()
    if _is_tiktok_opaque_identifier(external) and external not in values:
        values.append(external)
    if not values:
        for item in items[:3]:
            resolved = _tiktok_identity_from_media_url(str(item.get("source_url") or ""))
            if not resolved:
                continue
            resolved_handle, learned = resolved
            if resolved_handle and not meta.get("handle"):
                meta["handle"] = resolved_handle
            meta.setdefault("identifiers", {}).update(learned)
            for key in ("sec_uid", "channel_id", "user_id"):
                value = str(learned.get(key) or "").strip()
                if value and value not in values:
                    values.append(value)
            if values:
                meta["external_id"] = values[0]
                break
    return values


def _extract_tiktok_page(
    source_url: str,
    limit: int,
    start: int,
    identifiers: list[str],
) -> tuple[dict[str, Any], list[dict[str, Any]], str]:
    """Extract one TikTok page with one shared deadline and no nested fallback.

    At most one stable identifier and the human handle are attempted. Each
    candidate shares the same page budget, so a fallback cannot restart the
    timeout clock.
    """
    try:
        page_budget = max(60, int(os.getenv("MEDIA2MD_TIKTOK_PAGE_BUDGET_SECONDS", "300")))
    except ValueError:
        page_budget = 300
    deadline = time.monotonic() + page_budget
    candidates: list[tuple[str, str]] = []
    if start > 1 and identifiers:
        candidates.append((f"tiktokuser:{identifiers[0]}", "stable_id"))
    candidates.append((source_url, "handle"))
    deduped: list[tuple[str, str]] = []
    seen: set[str] = set()
    for candidate, kind in candidates:
        if candidate not in seen:
            seen.add(candidate)
            deduped.append((candidate, kind))
    print(
        f"SYNC_PAGE_BUDGET provider=tiktok range={start}-{start+limit-1} "
        f"budget_seconds={page_budget} candidates={len(deduped)}",
        flush=True,
    )
    errors: list[str] = []
    page_state: dict[str, Any] = {"tls_failures": 0, "breaker_open": False, "attempts": 0}
    for index, (candidate, kind) in enumerate(deduped):
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            break
        try:
            try:
                known_handle = _tiktok_handle_from_url(source_url)
                meta, items = _extract_catalog_once(
                    "tiktok", candidate, limit, start,
                    tiktok_deadline=deadline,
                    tiktok_context=f"range={start}-{start+limit-1} candidate={kind}",
                    emit_network_context=index == 0,
                    tiktok_handle_hint=known_handle,
                    tiktok_profile_url_hint=source_url,
                    tiktok_page_state=page_state,
                )
                if kind == "stable_id" and known_handle:
                    print(
                        "SYNC_STABLE_ID_HANDLE_REUSED provider=tiktok "
                        f"handle={known_handle} range={start}-{start+limit-1} "
                        "second_profile_fetch=false",
                        flush=True,
                    )
            except TypeError as exc:
                # Compatibility for injected/legacy extractor callables used by
                # downstream tests and plugins that still expose the v0.7.6
                # four-positional-argument signature.
                if "unexpected keyword argument" not in str(exc):
                    raise
                meta, items = _extract_catalog_once("tiktok", candidate, limit, start)
            return meta, items, candidate
        except Exception as exc:
            errors.append(f"{kind}:{candidate}: {exc}")
    remaining = max(0, int(deadline - time.monotonic()))
    raise RuntimeError(
        "TikTok page extraction failed within bounded page budget. "
        f"range={start}-{start+limit-1} budget_seconds={page_budget} "
        f"remaining_seconds={remaining} candidates_attempted={len(errors)} "
        + " | ".join(errors)[-5000:]
    )

def extract_catalog(provider: str, source_url: str, limit: int | None = None, start: int | None = None) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    if provider == "instagram":
        raise RuntimeError("Instagram catalog is handled by the Instagram engine.")
    try:
        return _extract_catalog_once(provider, source_url, limit, start)
    except RuntimeError as exc:
        if (
            provider != "tiktok"
            or "secondary user ID" not in str(exc)
            or _tiktok_transport_error_text(str(exc))
        ):
            raise
        handle, _ = normalize_creator(provider, source_url)
        errors = [str(exc)]
        for identifier in _tiktok_fallback_identifiers(handle):
            try:
                return _extract_catalog_once(provider, f"tiktokuser:{identifier}", limit, start)
            except RuntimeError as fallback_error:
                errors.append(str(fallback_error))
        raise RuntimeError("TikTok profile sync could not resolve secUid/user ID. " + " | ".join(errors)[-3500:]) from exc

def upsert_catalog(
    provider: str,
    requested_handle: str,
    source_url: str,
    items: list[dict[str, Any]],
    meta: dict[str, Any],
    sync_mode: str,
    exact: bool,
    *,
    exact_by_type: dict[str, bool] | None = None,
) -> dict[str, Any]:
    conn = connect()
    now = iso_now()
    threshold = youtube_long_threshold_seconds()
    external_id = str(meta.get("external_id") or requested_handle)
    discovered_handle = str(meta.get("handle") or requested_handle).lstrip("@")
    handle = requested_handle or discovered_handle or external_id
    identifiers = meta.get("identifiers") or {}
    previous_creator = _creator_by_identity(conn, provider, external_id, handle, identifiers)
    previous_total = int(previous_creator["current_total"] or 0) if previous_creator else 0
    previous_exact = bool(previous_creator["current_total_exact"]) if previous_creator else False
    previous_type_totals = {
        "youtube_video": int(previous_creator["youtube_video_total"] or 0) if previous_creator else 0,
        "youtube_short": int(previous_creator["youtube_shorts_total"] or 0) if previous_creator else 0,
        "youtube_stream": int(previous_creator["youtube_streams_total"] or 0) if previous_creator else 0,
    }
    creator = upsert_creator_identity(
        conn,
        provider,
        external_id,
        handle,
        str(meta.get("display_name") or handle),
        source_url,
        identifiers=identifiers,
    )
    creator_id = int(creator["id"])
    stored_identifiers = {
        str(row["identifier_type"]): str(row["identifier_value"])
        for row in conn.execute(
            "SELECT identifier_type,identifier_value FROM creator_identifiers WHERE creator_id=?",
            (creator_id,),
        ).fetchall()
    }
    identifiers = {**stored_identifiers, **identifiers}
    conn.execute(
        "UPDATE creators SET last_sync_mode=?,last_sync_at=?,last_full_sync_at=CASE WHEN ?='full' THEN ? ELSE last_full_sync_at END,updated_at=? WHERE id=?",
        (sync_mode, now, sync_mode, now, now, creator_id),
    )

    normalized_items: list[dict[str, Any]] = []
    for raw in items:
        item = dict(raw)
        media_type = infer_media_type(provider, item.get("source_url"), hinted=item.get("media_type"))
        item["media_type"] = media_type
        item["processing_class"] = processing_class(
            media_type,
            item.get("duration_seconds"),
            long_threshold_seconds=threshold,
        )
        normalized_items.append(item)
    normalized_items = merge_catalog_items(normalized_items)

    synced_types = {str(item.get("media_type")) for item in normalized_items}
    if provider == "youtube" and exact_by_type:
        synced_types.update(key for key, value in exact_by_type.items() if value)
    if provider == "tiktok":
        synced_types.add("tiktok_video")

    if synced_types:
        placeholders = ",".join("?" for _ in synced_types)
        previous_ids = {
            str(row[0])
            for row in conn.execute(
                f"SELECT external_id FROM media WHERE creator_id=? AND is_current=1 AND media_type IN ({placeholders})",
                (creator_id, *sorted(synced_types)),
            )
        }
    else:
        previous_ids = {
            str(row[0])
            for row in conn.execute(
                "SELECT external_id FROM media WHERE creator_id=? AND is_current=1",
                (creator_id,),
            )
        }
    incoming_ids = {str(item["external_id"]) for item in normalized_items}

    if sync_mode == "full":
        if synced_types:
            placeholders = ",".join("?" for _ in synced_types)
            conn.execute(
                f"UPDATE media SET is_current=0,updated_at=? WHERE creator_id=? AND media_type IN ({placeholders})",
                (now, creator_id, *sorted(synced_types)),
            )
        else:
            conn.execute("UPDATE media SET is_current=0,updated_at=? WHERE creator_id=?", (now, creator_id))

    for rank, item in enumerate(normalized_items, 1):
        conn.execute(
            """INSERT INTO media(
                provider,creator_id,external_id,title,description,source_url,published_at,
                duration_seconds,media_type,processing_class,rank_newest,is_current,status,created_at,updated_at
            ) VALUES(?,?,?,?,?,?,?,?,?,?,?,1,'pending',?,?)
            ON CONFLICT(provider,external_id) DO UPDATE SET
                creator_id=excluded.creator_id,title=excluded.title,description=excluded.description,
                source_url=excluded.source_url,published_at=excluded.published_at,
                duration_seconds=COALESCE(excluded.duration_seconds,media.duration_seconds),
                media_type=excluded.media_type,
                processing_class=CASE
                    WHEN excluded.duration_seconds IS NULL AND media.processing_class='youtube_long' THEN media.processing_class
                    ELSE excluded.processing_class
                END,
                rank_newest=CASE WHEN ?='full' THEN excluded.rank_newest ELSE COALESCE(media.rank_newest,excluded.rank_newest) END,
                is_current=1,updated_at=excluded.updated_at""",
            (
                provider,
                creator_id,
                item["external_id"],
                item.get("title"),
                item.get("description"),
                item["source_url"],
                item.get("published_at"),
                item.get("duration_seconds"),
                item.get("media_type"),
                item.get("processing_class"),
                rank,
                now,
                now,
                sync_mode,
            ),
        )

    if sync_mode == "full":
        ranked = conn.execute(
            "SELECT id FROM media WHERE creator_id=? AND is_current=1 ORDER BY COALESCE(published_at,'') DESC,id DESC",
            (creator_id,),
        ).fetchall()
        for rank, row in enumerate(ranked, 1):
            conn.execute("UPDATE media SET rank_newest=? WHERE id=?", (rank, row["id"]))

    if provider == "youtube":
        exact_flags = {
            "youtube_video": bool((exact_by_type or {}).get("youtube_video", False)),
            "youtube_short": bool((exact_by_type or {}).get("youtube_short", False)),
            "youtube_stream": bool((exact_by_type or {}).get("youtube_stream", False)),
        }
        counts_before_refresh = _type_counts(conn, creator_id)
        configured_types = {
            media_type_for_youtube_surface(surface)
            for surface in youtube_catalog_surfaces()
        }
        combined_exact = bool(exact and all(exact_flags.get(kind, False) for kind in configured_types))
        if counts_before_refresh.get("youtube_stream", 0) and "youtube_stream" not in configured_types:
            combined_exact = False
    elif provider == "tiktok":
        # A bounded Quick Sync only merges the newest slice into an already exact
        # TikTok catalog. It must not erase the proven Full Sync baseline. Cursor
        # rebuild pages use sync_mode='partial' and still intentionally mark the
        # catalog inexact until hasMorePrevious=false.
        combined_exact = bool(exact or (sync_mode == "quick" and previous_exact))
        exact_flags = {"tiktok_video": combined_exact}
    else:
        exact_flags = {}
        combined_exact = bool(exact)

    counts = refresh_creator_type_totals(
        conn,
        creator_id,
        exact_by_type=exact_flags,
        combined_exact=combined_exact,
    )
    creator_after = conn.execute("SELECT * FROM creators WHERE id=?", (creator_id,)).fetchone()
    current_total = int(creator_after["current_total"] or 0)
    current_exact = bool(creator_after["current_total_exact"])
    if sync_mode == "full" and current_exact:
        conn.execute(
            """UPDATE creators SET last_full_exact_total=?,last_full_exact_at=?,
               last_full_youtube_video_total=?,last_full_youtube_shorts_total=?,
               last_full_youtube_streams_total=?,updated_at=? WHERE id=?""",
            (
                current_total,
                now,
                counts.get("youtube_video", 0),
                counts.get("youtube_short", 0),
                counts.get("youtube_stream", 0),
                now,
                creator_id,
            ),
        )
        creator_after = conn.execute("SELECT * FROM creators WHERE id=?", (creator_id,)).fetchone()
    conn.commit()

    added = incoming_ids - previous_ids
    removed = previous_ids - incoming_ids if sync_mode == "full" else set()
    summary = {
        "provider": provider,
        "creator": handle,
        "creator_id": creator_id,
        "external_creator_id": external_id,
        "sync_mode": sync_mode,
        "previous_current_total": previous_total if previous_creator else None,
        "previous_current_total_exact": previous_exact if previous_creator else None,
        "current_total": current_total,
        "current_total_exact": current_exact,
        "new_since_last_sync": len(added),
        "removed_since_last_sync": len(removed),
        "newest": normalized_items[0].get("published_at") if normalized_items else None,
        "oldest": normalized_items[-1].get("published_at") if normalized_items else None,
        "creator_identifiers": identifiers,
        "media_type_totals": counts,
        "media_type_totals_exact": exact_flags,
        "youtube_video_total": counts.get("youtube_video", 0),
        "youtube_video_total_exact": bool(exact_flags.get("youtube_video", False)),
        "youtube_shorts_total": counts.get("youtube_short", 0),
        "youtube_shorts_total_exact": bool(exact_flags.get("youtube_short", False)),
        "youtube_streams_total": counts.get("youtube_stream", 0),
        "youtube_streams_total_exact": bool(exact_flags.get("youtube_stream", False)),
        "previous_media_type_totals": previous_type_totals,
        "last_full_exact_total": creator_after["last_full_exact_total"],
        "last_full_exact_at": creator_after["last_full_exact_at"],
        "last_full_media_type_totals": {
            "youtube_video": int(creator_after["last_full_youtube_video_total"] or 0),
            "youtube_short": int(creator_after["last_full_youtube_shorts_total"] or 0),
            "youtube_stream": int(creator_after["last_full_youtube_streams_total"] or 0),
            **({"tiktok_video": int(creator_after["last_full_exact_total"] or 0)}
               if provider == "tiktok" and creator_after["last_full_exact_total"] is not None else {}),
        },
    }
    conn.close()
    return summary


def _youtube_surface_absent(exc: Exception, surface: str) -> bool:
    lower = str(exc).lower()
    labels = {surface.lower(), surface.lower().rstrip("s")}
    return any(
        phrase in lower
        for label in labels
        for phrase in (
            f"does not have a {label} tab",
            f"doesn't have a {label} tab",
            f"has no {label} tab",
            f"no {label} tab",
        )
    )


def _sync_youtube_creator(
    handle: str,
    source_url: str,
    mode: str,
    quick_window: int,
) -> dict[str, Any]:
    surfaces = youtube_catalog_surfaces()
    surface_urls = youtube_surface_urls(source_url, surfaces)
    exact_by_type = {
        media_type_for_youtube_surface(surface): False
        for surface in surfaces
    }

    if mode == "quick":
        all_items: list[dict[str, Any]] = []
        meta: dict[str, Any] = {}
        surface_results: dict[str, dict[str, Any]] = {}
        for surface, url in surface_urls.items():
            try:
                page_meta, page_items = extract_catalog("youtube", url, limit=quick_window, start=1)
            except RuntimeError as exc:
                if not _youtube_surface_absent(exc, surface):
                    raise
                page_meta, page_items = {}, []
                print(
                    f"SYNC_SURFACE_ABSENT provider=youtube creator={handle} surface={surface} exact=true",
                    flush=True,
                )
            if not meta and page_meta:
                meta = page_meta
            all_items.extend(page_items)
            surface_results[surface] = {
                "fetched": len(page_items),
                "exact": False,
                "absent": not bool(page_items) and not bool(page_meta),
                "url": url,
            }
        summary = upsert_catalog(
            "youtube",
            handle,
            source_url,
            merge_catalog_items(all_items),
            meta,
            "quick",
            exact=False,
            exact_by_type=exact_by_type,
        )
        summary["youtube_surfaces"] = surface_results
        return summary

    page_size = 100
    CHECKPOINT_DIR.mkdir(parents=True, exist_ok=True)
    checkpoint_path = CHECKPOINT_DIR / f"youtube-{safe_name(handle)}-multi-surface.json"
    checkpoint = load_json(checkpoint_path, {})
    if checkpoint.get("source_url") != source_url or checkpoint.get("mode") != "full":
        checkpoint = {
            "schema_version": 2,
            "provider": "youtube",
            "creator": handle,
            "source_url": source_url,
            "mode": "full",
            "surfaces": {},
            "updated_at": iso_now(),
        }

    all_items: list[dict[str, Any]] = []
    meta: dict[str, Any] = dict(checkpoint.get("meta") or {})
    surface_results: dict[str, dict[str, Any]] = {}
    for surface, url in surface_urls.items():
        surface_state = dict(checkpoint.get("surfaces", {}).get(surface) or {})
        collected = [item for item in surface_state.get("items", []) if isinstance(item, dict)]
        next_start = int(surface_state.get("next_start", len(collected) + 1))
        complete = bool(surface_state.get("complete", False))
        by_id = {
            str(item["external_id"]): item
            for item in collected
            if item.get("external_id")
        }
        page = ((next_start - 1) // page_size) + 1
        while not complete:
            print(
                f"SYNC_PAGE_START provider=youtube creator={handle} surface={surface} "
                f"page={page} range={next_start}-{next_start + page_size - 1}",
                flush=True,
            )
            try:
                page_meta, page_items = extract_catalog("youtube", url, limit=page_size, start=next_start)
                surface_absent = False
            except RuntimeError as exc:
                if not _youtube_surface_absent(exc, surface):
                    raise
                page_meta, page_items = {}, []
                surface_absent = True
                print(
                    f"SYNC_SURFACE_ABSENT provider=youtube creator={handle} surface={surface} exact=true",
                    flush=True,
                )
            if not meta and page_meta:
                meta = page_meta
                checkpoint["meta"] = meta
            new_unique = 0
            for item in page_items:
                item["media_type"] = media_type_for_youtube_surface(surface)
                item["catalog_surface"] = surface
                if item["external_id"] not in by_id:
                    new_unique += 1
                by_id[item["external_id"]] = item
            collected = merge_catalog_items(by_id.values())
            complete = surface_absent or len(page_items) < page_size
            next_start += page_size
            checkpoint.setdefault("surfaces", {})[surface] = {
                "url": url,
                "items": collected,
                "next_start": next_start,
                "complete": complete,
                "absent": surface_absent,
                "updated_at": iso_now(),
            }
            checkpoint["updated_at"] = iso_now()
            atomic_json(checkpoint_path, checkpoint)
            print(
                f"SYNC_PAGE_DONE provider=youtube creator={handle} surface={surface} "
                f"page={page} fetched={len(page_items)} new_unique={new_unique} discovered={len(collected)}",
                flush=True,
            )
            page += 1
        all_items.extend(collected)
        media_type = media_type_for_youtube_surface(surface)
        exact_by_type[media_type] = True
        surface_results[surface] = {
            "fetched": len(collected),
            "exact": True,
            "absent": bool(checkpoint.get("surfaces", {}).get(surface, {}).get("absent", False)),
            "url": url,
        }

    summary = upsert_catalog(
        "youtube",
        handle,
        source_url,
        merge_catalog_items(all_items),
        meta,
        "full",
        exact=True,
        exact_by_type=exact_by_type,
    )
    summary["youtube_surfaces"] = surface_results
    checkpoint_path.unlink(missing_ok=True)
    return summary


def _apply_tiktok_identifier_metadata(meta: dict[str, Any], identifiers: list[str]) -> dict[str, Any]:
    """Keep stable TikTok identifiers visible in registry summaries and DB aliases."""
    if not identifiers:
        return meta
    merged = dict(meta or {})
    identifier_map = dict(merged.get("identifiers") or {})
    for value in identifiers:
        text = str(value or "").strip()
        if not text:
            continue
        if text.startswith("MS4wLjAB"):
            identifier_map.setdefault("sec_uid", text)
        elif text.isdigit():
            identifier_map.setdefault("user_id", text)
        else:
            identifier_map.setdefault("channel_id", text)
    merged["identifiers"] = identifier_map
    if not _is_tiktok_opaque_identifier(str(merged.get("external_id") or "")):
        merged["external_id"] = identifiers[0]
    return merged


def _is_tiktok_page_budget_error(error: BaseException | str) -> bool:
    text = str(error).lower()
    return (
        "bounded page budget" in text
        or "page budget exhausted" in text
        or "page deadline exhausted" in text
    )


def _sync_creator_unlocked(provider: str, creator_value: str, mode: str = "full", quick_window: int = 100) -> dict[str, Any]:
    handle, source_url = normalize_creator(provider, creator_value)
    if provider == "youtube":
        return _sync_youtube_creator(handle, source_url, mode, quick_window)
    if mode == "quick":
        meta, items = extract_catalog(provider, source_url, limit=quick_window, start=1)
        return upsert_catalog(provider, handle, source_url, items, meta, mode, exact=False)

    if provider == "tiktok":
        try:
            page_size = max(10, min(100, int(os.getenv("MEDIA2MD_TIKTOK_SYNC_PAGE_SIZE", "100"))))
        except ValueError:
            page_size = 100
        try:
            sync_runtime_budget = max(60, int(os.getenv("MEDIA2MD_TIKTOK_SYNC_MAX_RUNTIME_SECONDS", "1800")))
        except ValueError:
            sync_runtime_budget = 1800
        try:
            sync_max_pages = max(0, int(os.getenv("MEDIA2MD_TIKTOK_SYNC_MAX_PAGES_PER_RUN", "0")))
        except ValueError:
            sync_max_pages = 0
        sync_started = time.monotonic()
        pages_completed_this_run = 0
        print(
            f"SYNC_PAGE_CONFIG provider=tiktok page_size={page_size} processing_batch_size_is_separate=true",
            flush=True,
        )
        print(
            f"SYNC_RUN_BUDGET provider=tiktok max_runtime_seconds={sync_runtime_budget} "
            f"max_pages_per_run={sync_max_pages or 'unlimited'} resumable=true",
            flush=True,
        )
    else:
        page_size = 100
        sync_runtime_budget = 0
        sync_max_pages = 0
        sync_started = time.monotonic()
        pages_completed_this_run = 0
    CHECKPOINT_DIR.mkdir(parents=True, exist_ok=True)
    checkpoint_path = CHECKPOINT_DIR / f"{provider}-{safe_name(handle)}.json"
    checkpoint = load_json(checkpoint_path, {})
    checkpoint_resumable = checkpoint.get("source_url") == source_url and checkpoint.get("mode") == "full"
    if checkpoint_resumable:
        collected = checkpoint.get("items", [])
        next_start = int(checkpoint.get("next_start", len(collected) + 1))
        meta = checkpoint.get("meta") or {}
        tiktok_identifiers = [str(value) for value in checkpoint.get("tiktok_identifiers", []) if value]
    else:
        checkpoint = {}
        collected = []
        next_start = 1
        meta = {}
        tiktok_identifiers = []

    if provider == "tiktok":
        cursor_backend_enabled = os.getenv("MEDIA2MD_TIKTOK_CURSOR_BACKEND", "1").strip().lower() not in {
            "0", "false", "no", "off"
        }
        if not checkpoint_resumable and cursor_backend_enabled:
            bootstrap = _tiktok_cursor_bootstrap_from_registry(handle, source_url)
            if bootstrap:
                meta, tiktok_identifiers = bootstrap
                cursor = int(time.time() * 1000)
                cursor_state = _load_tiktok_cursor_state(handle)
                rebuild_from_exact = bool(_cursor_run_snapshot(handle).get("current_total_exact"))
                checkpoint = {
                    "schema_version": 5, "provider": "tiktok", "creator": handle,
                    "source_url": source_url, "catalog_source": "creator_item_list_cursor",
                    "mode": "full", "meta": meta, "tiktok_identifiers": tiktok_identifiers,
                    "items": [], "next_start": 1, "tiktok_cursor": cursor,
                    "tiktok_device_id": str(cursor_state.get("device_id") or _tiktok_device_id()),
                    "pagination_backend": "cursor_api",
                    "rebuild_from_exact": rebuild_from_exact,
                    "updated_at": iso_now(),
                }
                atomic_json(checkpoint_path, checkpoint)
                print(
                    "SYNC_CURSOR_BOOTSTRAP provider=tiktok source=registry "
                    f"cursor={cursor} rebuild=true existing_catalog_preserved=true "
                    f"baseline_exact={str(rebuild_from_exact).lower()} "
                    f"device_id_reused={str(bool(cursor_state.get('device_id'))).lower()}",
                    flush=True,
                )
        global _TIKTOK_SUCCESS_HINT
        _TIKTOK_SUCCESS_HINT = None
        preferred_transport = str(checkpoint.get("preferred_transport") or "").strip()
        if preferred_transport:
            preferred_authenticated = bool(checkpoint.get("preferred_authenticated", False))
            _TIKTOK_SUCCESS_HINT = (preferred_transport, preferred_authenticated)
            print(
                "SYNC_TRANSPORT_HINT_LOADED provider=tiktok "
                f"strategy={preferred_transport} authenticated={str(preferred_authenticated).lower()} "
                f"source=checkpoint",
                flush=True,
            )
        elif _macos_system_proxy_kinds():
            # The live StartupBell runs repeatedly showed browser-impersonated
            # requests inheriting an enabled macOS proxy while direct-plain could
            # complete pages. Prefer the isolated route on the first v0.8.0 run;
            # a real successful transport will then be persisted to checkpoint.
            _TIKTOK_SUCCESS_HINT = ("direct-plain", False)
            print(
                "SYNC_TRANSPORT_HINT_SELECTED provider=tiktok "
                "strategy=direct-plain authenticated=false "
                "reason=macos_system_proxy source=network_context",
                flush=True,
            )
        meta = _apply_tiktok_identifier_metadata(meta, tiktok_identifiers)

    by_id = {item["external_id"]: item for item in collected if isinstance(item, dict) and item.get("external_id")}

    if provider == "tiktok":
        cursor_backend_enabled = os.getenv("MEDIA2MD_TIKTOK_CURSOR_BACKEND", "1").strip().lower() not in {
            "0", "false", "no", "off"
        }
        has_cursor_sec_uid = any(str(value).startswith("MS4wLjAB") for value in tiktok_identifiers)
        if (
            cursor_backend_enabled
            and has_cursor_sec_uid
            and checkpoint.get("pagination_backend") == "cursor_api"
            and not collected
        ):
            return _sync_tiktok_cursor_catalog(
                handle=handle, source_url=source_url, checkpoint_path=checkpoint_path,
                checkpoint=checkpoint, collected=collected, meta=meta,
                identifiers=tiktok_identifiers, sync_started=sync_started,
                sync_runtime_budget=sync_runtime_budget, sync_max_pages=sync_max_pages,
            )

    if provider == "tiktok" and collected:
        # Older checkpoints may contain hundreds of valid media rows but no stable
        # secUid/user ID. Recover it from the cached metadata or one known video
        # before asking TikTok for the next page.
        if not tiktok_identifiers:
            recovered = _tiktok_identifiers_from_page(meta, collected)
            for value in recovered:
                if value not in tiktok_identifiers:
                    tiktok_identifiers.append(value)
            print(
                "SYNC_IDENTITY_RECOVERY provider=tiktok "
                f"recovered={len(recovered)} source=checkpoint_items",
                flush=True,
            )
        meta = _apply_tiktok_identifier_metadata(meta, tiktok_identifiers)
        # Make successfully discovered pages usable even when a later page is
        # blocked. This remains a lower-bound snapshot and is never labelled exact.
        partial_meta = dict(meta) if meta else {
            "external_id": tiktok_identifiers[0] if tiktok_identifiers else handle,
            "identifiers": {},
            "handle": handle,
            "display_name": handle,
            "source_url": source_url,
        }
        preserve_exact_baseline = bool(checkpoint.get("rebuild_from_exact"))
        if preserve_exact_baseline:
            print(
                "SYNC_STAGED_CATALOG_PRESERVED provider=tiktok "
                f"known_items={len(collected)} baseline_preserved=true next_start={next_start}",
                flush=True,
            )
        else:
            upsert_catalog(
                provider, handle, source_url, collected, partial_meta, "partial", exact=False
            )
            print(
                "SYNC_PARTIAL_CATALOG_SAVED provider=tiktok "
                f"known_items={len(collected)} exact=false next_start={next_start}",
                flush=True,
            )

        cursor_backend_enabled = os.getenv("MEDIA2MD_TIKTOK_CURSOR_BACKEND", "1").strip().lower() not in {
            "0", "false", "no", "off"
        }
        has_cursor_sec_uid = any(str(value).startswith("MS4wLjAB") for value in tiktok_identifiers)
        if cursor_backend_enabled and has_cursor_sec_uid:
            return _sync_tiktok_cursor_catalog(
                handle=handle, source_url=source_url, checkpoint_path=checkpoint_path,
                checkpoint=checkpoint, collected=collected, meta=meta,
                identifiers=tiktok_identifiers, sync_started=sync_started,
                sync_runtime_budget=sync_runtime_budget, sync_max_pages=sync_max_pages,
            )

    page = ((next_start - 1) // page_size) + 1
    while True:
        if provider == "tiktok":
            elapsed_run = time.monotonic() - sync_started
            runtime_exhausted = elapsed_run >= sync_runtime_budget
            pages_exhausted = sync_max_pages > 0 and pages_completed_this_run >= sync_max_pages
            if runtime_exhausted or pages_exhausted:
                partial_meta = dict(meta) if meta else {
                    "external_id": tiktok_identifiers[0] if tiktok_identifiers else handle,
                    "identifiers": {},
                    "handle": handle,
                    "display_name": handle,
                    "source_url": source_url,
                }
                summary = upsert_catalog(
                    provider, handle, source_url, collected, partial_meta, "partial", exact=False
                )
                reason = "runtime_budget" if runtime_exhausted else "max_pages_per_run"
                print(
                    "SYNC_RUN_PAUSED provider=tiktok "
                    f"reason={reason} elapsed_seconds={int(elapsed_run)} "
                    f"pages_completed={pages_completed_this_run} known_items={len(collected)} "
                    f"resume_from={next_start} exact=false",
                    flush=True,
                )
                summary.update({
                    "sync_incomplete": True,
                    "pause_reason": reason,
                    "resume_from": next_start,
                    "pages_completed_this_run": pages_completed_this_run,
                    "run_elapsed_seconds": int(elapsed_run),
                })
                return summary
        print(f"SYNC_PAGE_START provider={provider} creator={handle} page={page} range={next_start}-{next_start + page_size - 1}", flush=True)
        catalog_source = source_url
        if provider == "tiktok":
            try:
                page_meta, page_items, catalog_source = _extract_tiktok_page(
                    source_url, page_size, next_start, tiktok_identifiers
                )
            except Exception as exc:
                partial_meta = dict(meta) if meta else {
                    "external_id": tiktok_identifiers[0] if tiktok_identifiers else handle,
                    "identifiers": {},
                    "handle": handle,
                    "display_name": handle,
                    "source_url": source_url,
                }
                summary = upsert_catalog(
                    provider, handle, source_url, collected, partial_meta, "partial", exact=False
                )
                print(
                    "SYNC_PARTIAL_CATALOG_PRESERVED provider=tiktok "
                    f"known_items={len(collected)} exact=false retry_from={next_start}",
                    file=sys.stderr,
                    flush=True,
                )
                if _is_tiktok_page_budget_error(exc):
                    elapsed_run = int(time.monotonic() - sync_started)
                    print(
                        "SYNC_RUN_PAUSED provider=tiktok "
                        "reason=page_budget_exhausted "
                        f"elapsed_seconds={elapsed_run} pages_completed={pages_completed_this_run} "
                        f"known_items={len(collected)} resume_from={next_start} exact=false",
                        flush=True,
                    )
                    summary.update({
                        "sync_incomplete": True,
                        "pause_reason": "page_budget_exhausted",
                        "resume_from": next_start,
                        "pages_completed_this_run": pages_completed_this_run,
                        "run_elapsed_seconds": elapsed_run,
                        "last_page_error": str(exc)[-2000:],
                    })
                    return summary
                raise RuntimeError(
                    f"{exc} partial_catalog_saved={len(collected)} retry_from={next_start} "
                    "processing_hint=use_creator_run_with_allow_stale_catalog"
                ) from exc
        else:
            page_meta, page_items = extract_catalog(provider, source_url, limit=page_size, start=next_start)
        if not meta:
            meta = dict(page_meta)
        elif provider == "tiktok":
            # Merge identity learned on later pages without replacing the human handle.
            meta.setdefault("identifiers", {}).update(page_meta.get("identifiers") or {})
            for key in ("display_name", "external_id"):
                if not meta.get(key) and page_meta.get(key):
                    meta[key] = page_meta[key]
        if provider == "tiktok":
            learned = _tiktok_identifiers_from_page(page_meta, page_items)
            for value in learned:
                if value not in tiktok_identifiers:
                    tiktok_identifiers.append(value)
            if learned:
                meta.setdefault("identifiers", {}).update(page_meta.get("identifiers") or {})
                if not _is_tiktok_opaque_identifier(meta.get("external_id")):
                    meta["external_id"] = learned[0]
            meta = _apply_tiktok_identifier_metadata(meta, tiktok_identifiers)
        new_unique = 0
        for item in page_items:
            if item["external_id"] not in by_id:
                new_unique += 1
            by_id[item["external_id"]] = item
        collected = merge_catalog_items(by_id.values())
        next_start += page_size
        atomic_json(checkpoint_path, {
            "schema_version": 4,
            "provider": provider,
            "creator": handle,
            "source_url": source_url,
            "catalog_source": catalog_source,
            "mode": "full",
            "meta": meta,
            "tiktok_identifiers": tiktok_identifiers,
            "preferred_transport": _TIKTOK_SUCCESS_HINT[0] if provider == "tiktok" and _TIKTOK_SUCCESS_HINT else None,
            "preferred_authenticated": _TIKTOK_SUCCESS_HINT[1] if provider == "tiktok" and _TIKTOK_SUCCESS_HINT else False,
            "items": collected,
            "next_start": next_start,
            "updated_at": iso_now(),
        })
        if provider == "tiktok" and _TIKTOK_SUCCESS_HINT:
            print(
                "SYNC_TRANSPORT_HINT_SAVED provider=tiktok "
                f"strategy={_TIKTOK_SUCCESS_HINT[0]} "
                f"authenticated={str(_TIKTOK_SUCCESS_HINT[1]).lower()} source=checkpoint",
                flush=True,
            )
        print(f"SYNC_PAGE_DONE provider={provider} creator={handle} page={page} fetched={len(page_items)} new_unique={new_unique} discovered={len(collected)} catalog_source={catalog_source}", flush=True)
        if provider == "tiktok":
            pages_completed_this_run += 1
            print(
                f"SYNC_RUN_PROGRESS provider=tiktok pages_completed={pages_completed_this_run} "
                f"known_items={len(collected)} next_start={next_start} "
                f"elapsed_seconds={int(time.monotonic()-sync_started)}",
                flush=True,
            )
        if len(page_items) < page_size:
            break
        page += 1
    summary = upsert_catalog(provider, handle, source_url, collected, meta, "full", exact=True)
    checkpoint_path.unlink(missing_ok=True)
    return summary


def sync_creator(provider: str, creator_value: str, mode: str = "full", quick_window: int = 100) -> dict[str, Any]:
    handle, _ = normalize_creator(provider, creator_value)
    with operation_lock(
        "creator-sync",
        f"{provider}-{handle.lower()}",
        metadata={"provider": provider, "creator": handle, "mode": mode},
    ):
        return _sync_creator_unlocked(provider, creator_value, mode, quick_window)



def legacy_generic_identity(provider: str, creator_value: str, source_url: str) -> tuple[str, str]:
    raw = str(creator_value or "unknown").lstrip("@")
    handle = raw
    external_id = raw
    if provider == "tiktok":
        url_handle = _tiktok_handle_from_url(source_url)
        if url_handle:
            handle = url_handle
        elif _is_tiktok_opaque_identifier(raw):
            # Preserve the opaque value as platform identity, but never expose it as a handle.
            external_id = raw
            handle = "unknown"
        if _is_tiktok_opaque_identifier(raw):
            external_id = raw
        elif not external_id:
            external_id = handle
    elif provider == "youtube":
        if raw.startswith("UC"):
            external_id = raw
        elif raw:
            handle = raw.lstrip("@")
            external_id = raw
    return handle or external_id, external_id or handle

def sync_generic_status_from_legacy(conn: sqlite3.Connection, provider: str, external_id: str) -> None:
    if not LEGACY_GENERIC_DB.is_file():
        return
    legacy = sqlite3.connect(LEGACY_GENERIC_DB)
    legacy.row_factory = sqlite3.Row
    try:
        row = legacy.execute("SELECT * FROM media WHERE provider=? AND external_id=?", (provider, external_id)).fetchone()
    finally:
        legacy.close()
    if not row:
        return
    conn.execute(
        """UPDATE media SET status=?, markdown_path=?, markdown_sha256=?, last_error=?, completed_at=?, updated_at=?
           WHERE provider=? AND external_id=?""",
        (row["status"], row["markdown_path"], row["markdown_sha256"], row["last_error"], row["completed_at"], iso_now(), provider, external_id),
    )


def _format_eta(seconds: float | None) -> str:
    if seconds is None:
        return "calculating"
    seconds = max(0, int(round(seconds)))
    hours, rem = divmod(seconds, 3600)
    minutes, secs = divmod(rem, 60)
    return f"{hours:02d}:{minutes:02d}:{secs:02d}"



def _youtube_metadata_probe(external_id: str) -> dict[str, Any] | None:
    url = f"https://www.youtube.com/watch?v={external_id}"
    base = [command("yt-dlp"), *youtube_runtime_args(), "--dump-single-json", "--skip-download", "--no-playlist", url]
    try:
        return run_json(base, timeout=300)
    except Exception:
        auth = auth_args("youtube")
        if not auth:
            return None
        verification = verify_youtube_session(external_id, persist=True)
        if not verification.get("authenticated"):
            return None
        try:
            return run_json([command("yt-dlp"), *youtube_runtime_args(), *auth, "--dump-single-json", "--skip-download", "--no-playlist", url], timeout=300)
        except Exception:
            return None


def hydrate_youtube_duration_classes(conn: sqlite3.Connection, creator_id: int, limit: int = 12) -> int:
    threshold = youtube_long_threshold_seconds()
    rows = conn.execute(
        """SELECT id,external_id,media_type,duration_seconds FROM media
           WHERE creator_id=? AND is_current=1 AND media_type='youtube_video'
             AND (duration_seconds IS NULL OR duration_seconds<=0)
             AND status NOT IN ('completed','skipped')
           ORDER BY COALESCE(published_at,'') DESC,id DESC LIMIT ?""",
        (creator_id, max(0, int(limit))),
    ).fetchall()
    updated = 0
    for row in rows:
        payload = _youtube_metadata_probe(str(row["external_id"]))
        if not payload:
            continue
        duration = payload.get("duration")
        try:
            duration_value = float(duration)
        except (TypeError, ValueError):
            continue
        item_class = processing_class("youtube_video", duration_value, long_threshold_seconds=threshold)
        conn.execute(
            "UPDATE media SET duration_seconds=?,processing_class=?,updated_at=? WHERE id=?",
            (duration_value, item_class, iso_now(), row["id"]),
        )
        updated += 1
    if updated:
        conn.commit()
    return updated


def _select_typed_batch(
    conn: sqlite3.Connection,
    provider: str,
    clauses: list[str],
    params: list[Any],
    direction: str,
    batch_size: int,
    batch_sizes: dict[str, int] | None,
) -> list[sqlite3.Row]:
    typed = normalize_batch_sizes(batch_sizes) if batch_sizes else {}
    base_sql = (
        f"SELECT m.*, c.handle FROM media m JOIN creators c ON c.id=m.creator_id "
        f"WHERE {' AND '.join(clauses)}"
    )
    order_sql = f" ORDER BY COALESCE(m.published_at,'') {direction},m.id {direction}"
    if not typed:
        return conn.execute(base_sql + order_sql + " LIMIT ?", [*params, batch_size]).fetchall()

    if provider == "youtube":
        creator_id = int(params[0])
        hydrate_limit = max(typed.get("youtube_video", 0) + typed.get("youtube_long", 0), 12)
        hydrate_youtube_duration_classes(conn, creator_id, hydrate_limit)
        long_quota = typed.get("youtube_long", 1)
        if long_quota > 0:
            long_rows = conn.execute(
                base_sql + " AND COALESCE(m.processing_class,m.media_type)='youtube_long'" + order_sql + " LIMIT ?",
                [*params, long_quota],
            ).fetchall()
            if long_rows:
                return long_rows
        selected: list[sqlite3.Row] = []
        for item_class in ("youtube_video", "youtube_short", "youtube_stream"):
            quota = typed.get(item_class, 0)
            if quota <= 0:
                continue
            rows = conn.execute(
                base_sql + " AND COALESCE(m.processing_class,m.media_type)=?" + order_sql + " LIMIT ?",
                [*params, item_class, quota],
            ).fetchall()
            selected.extend(rows)
        reverse = direction == "DESC"
        selected.sort(
            key=lambda row: (str(row["published_at"] or ""), int(row["id"])),
            reverse=reverse,
        )
        return selected

    target_type = "tiktok_video" if provider == "tiktok" else "instagram_reel"
    quota = typed.get(target_type, batch_size)
    return conn.execute(
        base_sql + " AND COALESCE(m.processing_class,m.media_type)=?" + order_sql + " LIMIT ?",
        [*params, target_type, quota],
    ).fetchall()


def _batch_composition(rows: list[sqlite3.Row]) -> dict[str, int]:
    result: dict[str, int] = {}
    for row in rows:
        key = str(row["processing_class"] or row["media_type"] or "unknown")
        result[key] = result.get(key, 0) + 1
    return result


def _creator_run_summary(
    *, provider: str, handle: str, batches: int, processed: int,
    failures: int, status: str, remaining: int, output: str,
    markdown_root: Path | None = None, latest_markdown_path: str | None = None,
) -> None:
    completed = max(0, processed - failures)
    primary_output_surface = None
    if markdown_root:
        candidate = markdown_root.name
        if candidate in {"videos", "shorts", "streams", "reels"}:
            primary_output_surface = candidate
    if output == "human":
        print(
            f"CREATOR_RUN_COMPLETED provider={provider} creator={handle} status={status} "
            f"batches={batches} processed={processed} completed={completed} "
            f"failures={failures} remaining={max(0, remaining)}"
        )
        if latest_markdown_path:
            print(f"latest_markdown_path={latest_markdown_path}")
        if markdown_root:
            print(f"markdown_root={markdown_root}")
            if primary_output_surface:
                print(f"primary_output_surface={primary_output_surface}")
            print(f"result_folder={markdown_root}")
            print(f"open_in_finder_hint=open \"{markdown_root}\"")
    else:
        emit_cli_event(
            event="creator_run_completed",
            section="run",
            status=creator_run_event_status(status),
            message=f"Creator run finished with status={status}",
            data={
                "provider": provider,
                "creator": handle,
                "run_status": status,
                "status": status,
                "batches": batches,
                "processed": processed,
                "completed": completed,
                "failures": failures,
                "remaining": max(0, remaining),
                "latest_markdown_path": latest_markdown_path,
                "markdown_root": str(markdown_root) if markdown_root else None,
                "primary_output_surface": primary_output_surface,
            },
        )


def _creator_markdown_root(provider: str, handle: str) -> Path:
    return ROOT / "markdown" / provider / safe_name(handle)


def _latest_markdown_path(provider: str, external_id: str) -> str | None:
    conn = connect()
    try:
        row = conn.execute(
            "SELECT markdown_path FROM media WHERE provider=? AND external_id=?",
            (provider, external_id),
        ).fetchone()
    finally:
        conn.close()
    if not row or not row["markdown_path"]:
        return None
    return str(ROOT / str(row["markdown_path"]))


def _render_stage_progress(*, provider: str, creator: str, media_id: str, batch_number: int,
                           batch_count: int, current: int, total: int, stage: str, elapsed: float) -> None:
    stage_map = {
        "pending": ("queued", 0.05),
        "downloading": ("download", 0.28),
        "downloaded": ("download", 0.42),
        "transcribing": ("transcribe", 0.68),
        "transcribed": ("transcribe", 0.78),
        "rendering": ("render", 0.88),
        "validating": ("validate", 0.94),
        "cleaning": ("cleanup", 0.98),
        "completed": ("done", 1.0),
        "failed": ("failed", 1.0),
        "starting": ("starting", 0.02),
    }
    stage_label, stage_fraction = stage_map.get(stage, (stage, 0.12))
    bar_width = 32
    percent = max(0.0, min(1.0, stage_fraction))
    complete = max(0, min(bar_width, int(round(percent * bar_width))))
    bar = "━" * complete + " " * (bar_width - complete)
    percent_text = f"{int(round(percent * 100)):>3}%"
    elapsed_text = _format_eta(elapsed)
    short_id = media_id[:14]
    line = (
        f"\r{stage_label:<10} [{bar}] {percent_text} "
        f"item {current}/{total} batch {batch_number}/{batch_count} "
        f"elapsed {elapsed_text} id {short_id}"
    )
    print(line[:160], end="", flush=True)


def _runtime_limit_error(text: str) -> bool:
    return "item exceeded remaining runtime limit" in str(text or "").lower()


def _actual_creator_remaining(provider: str, handle: str) -> int:
    conn = connect()
    creator = conn.execute(
        "SELECT id FROM creators WHERE provider=? AND handle=?",
        (provider, handle),
    ).fetchone()
    remaining = 0
    if creator:
        remaining = int(conn.execute(
            "SELECT COUNT(*) FROM media WHERE creator_id=? AND is_current=1 "
            "AND status NOT IN ('completed','skipped')",
            (creator["id"],),
        ).fetchone()[0])
    conn.close()
    return remaining


def _creator_run_unlocked(provider: str, creator_value: str, mode: str, batch_size: int,
                          max_batches: int, max_failures: int, stop_on_failure: bool,
                          sleep_between_batches: float, since: str | None, until: str | None,
                          rank_from: int | None, rank_to: int | None, order: str,
                          output: str, max_runtime_minutes: int = 360,
                          batch_sizes: dict[str, int] | None = None) -> int:
    handle, _ = normalize_creator(provider, creator_value)
    conn = connect()
    creator = conn.execute(
        "SELECT * FROM creators WHERE provider=? AND handle=?",
        (provider, handle),
    ).fetchone()
    conn.close()
    if not creator:
        sync_creator(provider, creator_value, mode="full")

    started = time.monotonic()
    runtime_limit = max_runtime_minutes * 60 if max_runtime_minutes > 0 else None
    batches = 0
    failures = 0
    processed_total = 0
    durations: list[float] = []
    runtime_paused = False
    latest_markdown_path: str | None = None

    while True:
        if runtime_limit is not None and time.monotonic() - started >= runtime_limit:
            if output == "human":
                print("RUN_STOPPED reason=max_runtime")
            else:
                emit_cli_event(
                    event="run_stopped",
                    section="run",
                    status="timeout",
                    message="Creator run stopped because the runtime limit was reached",
                    data={"reason": "max_runtime"},
                )
            break

        conn = connect()
        creator_row = conn.execute(
            "SELECT * FROM creators WHERE provider=? AND handle=?",
            (provider, handle),
        ).fetchone()
        if not creator_row:
            conn.close()
            raise RuntimeError(f"Creator not found after sync: {provider}:{handle}")
        clauses = ["m.creator_id=?", "m.is_current=1", "m.status NOT IN ('completed','skipped')"]
        params: list[Any] = [creator_row["id"]]
        if since:
            clauses.append("COALESCE(m.published_at,'') >= ?")
            params.append(since)
        if until:
            clauses.append("COALESCE(m.published_at,'') <= ?")
            params.append(until)
        if rank_from:
            clauses.append("m.rank_newest >= ?")
            params.append(rank_from)
        if rank_to:
            clauses.append("m.rank_newest <= ?")
            params.append(rank_to)
        direction = "ASC" if order == "oldest_first" else "DESC"
        remaining_before = conn.execute(
            f"SELECT COUNT(*) FROM media m WHERE {' AND '.join(clauses)}",
            params,
        ).fetchone()[0]
        rows = _select_typed_batch(
            conn, provider, clauses, params, direction, batch_size, batch_sizes
        )
        conn.close()
        if not rows:
            break

        batches += 1
        capacity = max(1, len(rows) if batch_sizes else batch_size)
        estimated_batches = (remaining_before + capacity - 1) // capacity
        composition = _batch_composition(rows)
        selected_media_ids = [str(row["external_id"]) for row in rows]
        if output == "human":
            print(
                f"BATCH_START provider={provider} creator={handle} "
                f"batch={batches}/{estimated_batches} selected={len(rows)} remaining_before={remaining_before} "
                f"composition={json.dumps(composition, sort_keys=True)} "
                f"selected_media_ids={json.dumps(selected_media_ids)}"
            )
        else:
            emit_cli_event(
                event="batch_started",
                section="run",
                status="ok",
                message="Batch started",
                data={
                    "provider": provider,
                    "creator": handle,
                    "batch_number": batches,
                    "batch_count": estimated_batches,
                    "selected": len(rows),
                    "remaining_before": remaining_before,
                    "composition": composition,
                    "selected_media_ids": selected_media_ids,
                },
            )

        for index, row in enumerate(rows, 1):
            if runtime_limit is not None and time.monotonic() - started >= runtime_limit:
                if output == "human":
                    print("RUN_STOPPED reason=max_runtime")
                return 0 if failures == 0 else 2
            item_started = time.monotonic()
            cmd = [
                sys.executable, str(ROOT / "scripts" / "generic_media.py"),
                "process-registered", provider, str(row["external_id"]),
            ]
            if output == "ndjson":
                cmd += ["--output", "ndjson"]
            item_timeout = None
            if runtime_limit is not None:
                item_timeout = max(1, int(runtime_limit - (time.monotonic() - started)))
            process = subprocess.Popen(
                cmd,
                cwd=ROOT,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                start_new_session=True,
            )
            try:
                stage = "starting"
                poll = getattr(process, "poll", None)
                if not callable(poll):
                    stdout, stderr = process.communicate(timeout=item_timeout)
                    result = subprocess.CompletedProcess(cmd, process.returncode, stdout, stderr)
                else:
                    while True:
                        if process.poll() is not None:
                            break
                        if LEGACY_GENERIC_DB.is_file():
                            try:
                                legacy = sqlite3.connect(LEGACY_GENERIC_DB)
                                legacy.row_factory = sqlite3.Row
                                status_row = legacy.execute(
                                    "SELECT status FROM media WHERE provider=? AND external_id=?",
                                    (provider, str(row["external_id"])),
                                ).fetchone()
                                legacy.close()
                                if status_row and status_row["status"]:
                                    stage = str(status_row["status"])
                            except Exception:
                                pass
                        if output == "human":
                            _render_stage_progress(
                                provider=provider,
                                creator=handle,
                                media_id=str(row["external_id"]),
                                batch_number=batches,
                                batch_count=estimated_batches,
                                current=index,
                                total=len(rows),
                                stage=stage,
                                elapsed=time.monotonic() - item_started,
                            )
                        time.sleep(0.25)
                    stdout, stderr = process.communicate(timeout=5)
                    result = subprocess.CompletedProcess(cmd, process.returncode, stdout, stderr)
            except subprocess.TimeoutExpired:
                try:
                    os.killpg(process.pid, signal.SIGTERM)
                    process.wait(timeout=5)
                except Exception:
                    try:
                        os.killpg(process.pid, signal.SIGKILL)
                    except Exception:
                        pass
                stdout, stderr = process.communicate()
                result = subprocess.CompletedProcess(cmd, 124, stdout, (stderr or "") + "\nItem exceeded remaining runtime limit")
            except KeyboardInterrupt:
                try:
                    os.killpg(process.pid, signal.SIGTERM)
                    process.wait(timeout=5)
                except Exception:
                    try:
                        os.killpg(process.pid, signal.SIGKILL)
                    except Exception:
                        pass
                interrupted = connect()
                interrupted.execute(
                    "UPDATE media SET status='pending',last_error='Interrupted by user; safe to resume',updated_at=? WHERE id=?",
                    (iso_now(), row["id"]),
                )
                interrupted.commit()
                interrupted.close()
                if LEGACY_GENERIC_DB.is_file():
                    legacy = sqlite3.connect(LEGACY_GENERIC_DB)
                    legacy.execute(
                        "UPDATE media SET status='pending',last_error='Interrupted by user; safe to resume',updated_at=? WHERE provider=? AND external_id=?",
                        (iso_now(), provider, row["external_id"]),
                    )
                    legacy.commit(); legacy.close()
                # v0.7.1 preserves complete audio/chunk checkpoints so the next
                # run can resume without downloading or transcribing again.
                print("REGISTRY_INTERRUPTED", file=sys.stderr)
                return 130
            elapsed = time.monotonic() - item_started
            if output == "human":
                print("", flush=True)
            if output == "human" and result.stdout:
                for child_line in result.stdout.splitlines():
                    if child_line.startswith((
                        "TIKTOK_DOWNLOAD_ATTEMPT ",
                        "TIKTOK_DOWNLOAD_ATTEMPT_RESULT ",
                        "TIKTOK_DOWNLOAD_HINT_LOADED ",
                        "TIKTOK_DOWNLOAD_HINT_SAVED ",
                        "TIKTOK_DOWNLOAD_BUDGET_EXHAUSTED ",
                    )):
                        print(child_line, flush=True)
            if result.returncode == 0:
                durations.append(elapsed)
                if len(durations) > 20:
                    durations = durations[-20:]
                latest_markdown_path = _latest_markdown_path(provider, str(row["external_id"])) or latest_markdown_path

            conn = connect()
            sync_generic_status_from_legacy(conn, provider, row["external_id"])
            if result.returncode != 0:
                error_text = (result.stderr or result.stdout or f"generic_media exit code {result.returncode}")[-4000:]
                timed_out = _runtime_limit_error(error_text)
                def marker(name: str) -> str | None:
                    match = re.search(rf"\[{name}=([^\]]+)\]", error_text)
                    return match.group(1) if match else None
                stage = marker("stage") or "process"
                error_code = marker("error_code") or ("runtime_budget_exhausted" if timed_out else "process_error")
                retryable_marker = marker("retryable")
                retryable = True if timed_out else (retryable_marker == "true" if retryable_marker else stage not in {"render", "validation"})
                action_required = marker("action_required") == "true"
                required_action = marker("required_action")
                required_action = validate_required_action(required_action) if required_action else None
                root_cause = marker("root_cause")
                log_path = marker("log_path")
                if timed_out:
                    runtime_paused = True
                    conn.execute(
                        "UPDATE media SET status='pending',last_error='Runtime limit reached; resume will continue from cached checkpoints',updated_at=? WHERE id=?",
                        (iso_now(), row["id"]),
                    )
                    if output == "human":
                        print(
                            f"ITEM_PAUSED provider={provider} creator={handle} media_id={row['external_id']} "
                            f"stage={stage} retryable=true error_code={error_code}"
                        )
                    else:
                        emit_cli_event(
                            event="item_paused",
                            section="process",
                            status="timeout",
                            message="Item paused because the remaining runtime budget was exhausted",
                            data={
                                "provider": provider,
                                "creator": handle,
                                "media_id": row["external_id"],
                                "stage": stage,
                                "error": error_text,
                                "error_code": error_code,
                                "retryable": True,
                                "action_required": False,
                                "required_action": None,
                                "root_cause": root_cause,
                                "log_path": log_path,
                            },
                        )
                else:
                    failures += 1
                    conn.execute("UPDATE media SET status='failed',last_error=?,updated_at=? WHERE id=?", (error_text,iso_now(),row["id"]))
                    if output == "human":
                        print(f"ITEM_FAILED provider={provider} creator={handle} media_id={row['external_id']} stage={stage} retryable={str(retryable).lower()} error_code={error_code} action_required={str(action_required).lower()}")
                        if required_action:
                            print(f"required_action={required_action}")
                        if root_cause:
                            print("root_cause=" + root_cause)
                        if log_path:
                            print("log_path=" + log_path)
                        if not root_cause:
                            print("error_tail=" + error_text.replace("\n", " ")[-1200:])
                    else:
                        emit_cli_event(
                            event="item_failed",
                            section="process",
                            status="warn" if action_required or retryable else "error",
                            message="Item processing failed",
                            data={
                                "provider": provider,
                                "creator": handle,
                                "media_id": row["external_id"],
                                "stage": stage,
                                "error": error_text,
                                "error_code": error_code,
                                "root_cause": root_cause,
                                "log_path": log_path,
                                "retryable": retryable,
                                "action_required": action_required,
                                "required_action": required_action,
                            },
                        )
            conn.commit()
            conn.close()

            processed_total += 1
            percent = round(index * 100 / len(rows), 1)
            average = statistics.median(durations) if durations else None
            batch_remaining = len(rows) - index
            total_remaining = max(0, remaining_before - index)
            batch_eta = average * batch_remaining if average is not None else None
            total_eta = average * total_remaining if average is not None else None
            confidence = "high" if len(durations) >= 10 else "medium" if len(durations) >= 3 else "low"
            if output == "human":
                print(
                    f"PROGRESS {index}/{len(rows)} {percent}% failures={failures} "
                    f"batch_eta={_format_eta(batch_eta)} total_eta={_format_eta(total_eta)} "
                    f"confidence={confidence}"
                )
            else:
                emit_cli_event(
                    event="progress",
                    section="run",
                    status="ok",
                    message="Creator run progress updated",
                    data={
                        "phase": "process",
                        "provider": provider,
                        "creator": handle,
                        "batch_number": batches,
                        "batch_count": estimated_batches,
                        "current": index,
                        "total": len(rows),
                        "percent": percent,
                        "processed_total": processed_total,
                        "remaining_total": total_remaining,
                        "batch_eta_seconds": round(batch_eta) if batch_eta is not None else None,
                        "total_eta_seconds": round(total_eta) if total_eta is not None else None,
                        "eta_confidence": confidence,
                        "failures": failures,
                    },
                )

            if runtime_paused:
                _creator_run_summary(
                    provider=provider, handle=handle, batches=batches, processed=processed_total,
                    failures=failures, status="paused_runtime_limit",
                    remaining=_actual_creator_remaining(provider, handle), output=output,
                    markdown_root=_creator_markdown_root(provider, handle),
                    latest_markdown_path=latest_markdown_path,
                )
                return 0

            if failures >= max_failures or (stop_on_failure and result.returncode != 0):
                _creator_run_summary(
                    provider=provider, handle=handle, batches=batches, processed=processed_total,
                    failures=failures, status="stopped_max_failures",
                    remaining=_actual_creator_remaining(provider, handle), output=output,
                    markdown_root=_creator_markdown_root(provider, handle),
                    latest_markdown_path=latest_markdown_path,
                )
                return 2

        if mode == "batch" or (max_batches and batches >= max_batches):
            break
        if sleep_between_batches:
            time.sleep(sleep_between_batches)

    final_conn = connect()
    final_creator = final_conn.execute(
        "SELECT id FROM creators WHERE provider=? AND handle=?", (provider, handle)
    ).fetchone()
    remaining = 0
    if final_creator:
        remaining = int(final_conn.execute(
            "SELECT COUNT(*) FROM media WHERE creator_id=? AND is_current=1 AND status NOT IN ('completed','skipped')",
            (final_creator["id"],),
        ).fetchone()[0])
    final_conn.close()
    _creator_run_summary(
        provider=provider, handle=handle, batches=batches, processed=processed_total,
        failures=failures, status="completed" if failures == 0 else "completed_with_errors",
        remaining=remaining, output=output,
        markdown_root=_creator_markdown_root(provider, handle),
        latest_markdown_path=latest_markdown_path,
    )
    return 0 if failures == 0 else 2


def creator_run(provider: str, creator_value: str, mode: str, batch_size: int,
                max_batches: int, max_failures: int, stop_on_failure: bool,
                sleep_between_batches: float, since: str | None, until: str | None,
                rank_from: int | None, rank_to: int | None, order: str,
                output: str, max_runtime_minutes: int = 360,
                batch_sizes: dict[str, int] | None = None) -> int:
    handle, _ = normalize_creator(provider, creator_value)
    with operation_lock(
        "creator-run",
        f"{provider}-{handle.lower()}",
        metadata={"provider": provider, "creator": handle, "mode": mode},
    ):
        return _creator_run_unlocked(
            provider, creator_value, mode, batch_size, max_batches, max_failures,
            stop_on_failure, sleep_between_batches, since, until, rank_from,
            rank_to, order, output, max_runtime_minutes, batch_sizes,
        )


def migrate_legacy() -> dict[str, int]:
    conn = connect()
    marker = conn.execute("SELECT 1 FROM migrations WHERE name='legacy-v04'").fetchone()
    if marker:
        conn.close(); return {"instagram_creators":0,"instagram_media":0,"generic_media":0,"already_applied":1}
    counts = {"instagram_creators":0,"instagram_media":0,"generic_media":0,"already_applied":0}
    now = iso_now()
    if LEGACY_INSTAGRAM_DB.is_file():
        old = sqlite3.connect(LEGACY_INSTAGRAM_DB); old.row_factory=sqlite3.Row
        try:
            creators = old.execute("SELECT * FROM creators").fetchall()
            for c in creators:
                handle = c["username"]
                conn.execute("""INSERT OR IGNORE INTO creators(provider,external_id,handle,display_name,source_url,enabled,created_at,updated_at)
                              VALUES('instagram',?,?,?,?,?,?,?)""",
                             (handle,handle,handle,f"https://www.instagram.com/{handle}/reels/",int(c["enabled"]),now,now))
                counts["instagram_creators"] += 1
            videos = old.execute("SELECT v.*, c.username FROM videos v JOIN creators c ON c.id=v.creator_id").fetchall()
            for v in videos:
                creator_id = conn.execute("SELECT id FROM creators WHERE provider='instagram' AND handle=?", (v["username"],)).fetchone()[0]
                conn.execute("""INSERT OR IGNORE INTO media(provider,creator_id,external_id,title,description,source_url,published_at,status,markdown_path,markdown_sha256,last_error,created_at,updated_at,completed_at)
                              VALUES('instagram',?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                             (creator_id,v["shortcode"],v["shortcode"],v["caption"],v["source_url"],v["published_at"],v["status"],v["markdown_path"],v["markdown_sha256"],v["last_error"],v["created_at"],v["updated_at"],v["completed_at"]))
                counts["instagram_media"] += 1
        finally: old.close()
    if LEGACY_GENERIC_DB.is_file():
        old = sqlite3.connect(LEGACY_GENERIC_DB); old.row_factory=sqlite3.Row
        try:
            for v in old.execute("SELECT * FROM media").fetchall():
                provider = v["provider"]
                handle, external_creator_id = legacy_generic_identity(provider, v["creator"], v["source_url"])
                creator = upsert_creator_identity(conn, provider, external_creator_id, handle, handle, v["source_url"])
                creator_id = int(creator["id"])
                conn.execute("""INSERT OR IGNORE INTO media(provider,creator_id,external_id,title,description,source_url,published_at,duration_seconds,status,markdown_path,markdown_sha256,last_error,created_at,updated_at,completed_at)
                              VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                             (provider,creator_id,v["external_id"],v["title"],v["description"],v["source_url"],v["published_at"],v["duration_seconds"],v["status"],v["markdown_path"],v["markdown_sha256"],v["last_error"],v["created_at"],v["updated_at"],v["completed_at"]))
                counts["generic_media"] += 1
        finally: old.close()
    conn.execute("INSERT INTO migrations(name,applied_at,details) VALUES('legacy-v04',?,?)", (now,json.dumps(counts)))
    conn.commit(); conn.close()
    return counts


def refresh_legacy() -> dict[str, int]:
    """Refresh the unified control-plane registry from legacy execution databases."""
    conn = connect()
    counts = {"instagram_creators": 0, "instagram_media": 0, "generic_media": 0}
    now = iso_now()
    if LEGACY_INSTAGRAM_DB.is_file():
        old = sqlite3.connect(LEGACY_INSTAGRAM_DB)
        old.row_factory = sqlite3.Row
        try:
            for c in old.execute("SELECT * FROM creators").fetchall():
                handle = c["username"]
                catalog_path = LEGACY_INSTAGRAM_CATALOG_DIR / f"{handle}.json"
                catalog = load_json(catalog_path, {}) if catalog_path.is_file() else {}
                source_url = str(catalog.get("profile_url") or f"https://www.instagram.com/{handle}/reels/")
                conn.execute(
                    """INSERT INTO creators(provider,external_id,handle,display_name,source_url,enabled,created_at,updated_at)
                       VALUES('instagram',?,?,?,?,?,?,?)
                       ON CONFLICT(provider,handle) DO UPDATE SET source_url=excluded.source_url,enabled=excluded.enabled,updated_at=excluded.updated_at""",
                    (handle, handle, handle, source_url, int(c["enabled"]), now, now),
                )
                counts["instagram_creators"] += 1
                total = catalog.get("current_total")
                exact = bool(catalog.get("current_total_exact", False))
                last_full = catalog.get("last_full_sync_at")
                if total is not None:
                    conn.execute(
                        """UPDATE creators SET current_total=?,current_total_exact=?,last_sync_mode=?,
                           last_sync_at=?,last_full_sync_at=COALESCE(?,last_full_sync_at),
                           last_full_exact_total=CASE WHEN ? THEN ? ELSE last_full_exact_total END,
                           last_full_exact_at=CASE WHEN ? THEN COALESCE(?,?) ELSE last_full_exact_at END,
                           updated_at=? WHERE provider='instagram' AND handle=?""",
                        (
                            int(total), int(exact), catalog.get("last_sync_mode"), catalog.get("last_sync_at"),
                            last_full, int(exact), int(total), int(exact), last_full, catalog.get("updated_at"),
                            now, handle,
                        ),
                    )
            for v in old.execute("SELECT v.*, c.username FROM videos v JOIN creators c ON c.id=v.creator_id").fetchall():
                creator_id = conn.execute(
                    "SELECT id FROM creators WHERE provider='instagram' AND handle=?",
                    (v["username"],),
                ).fetchone()[0]
                markdown_path = v["markdown_path"]
                if markdown_path and markdown_path.startswith("markdown/") and not markdown_path.startswith("markdown/instagram/"):
                    markdown_path = "markdown/instagram/" + markdown_path[len("markdown/"):]
                conn.execute(
                    """INSERT INTO media(provider,creator_id,external_id,title,description,source_url,published_at,status,
                                         markdown_path,markdown_sha256,last_error,created_at,updated_at,completed_at)
                       VALUES('instagram',?,?,?,?,?,?,?,?,?,?,?,?,?)
                       ON CONFLICT(provider,external_id) DO UPDATE SET
                         creator_id=excluded.creator_id,title=excluded.title,description=excluded.description,
                         source_url=excluded.source_url,published_at=excluded.published_at,status=excluded.status,
                         markdown_path=excluded.markdown_path,markdown_sha256=excluded.markdown_sha256,
                         last_error=excluded.last_error,updated_at=excluded.updated_at,completed_at=excluded.completed_at""",
                    (creator_id, v["shortcode"], v["shortcode"], v["caption"], v["source_url"], v["published_at"],
                     v["status"], markdown_path, v["markdown_sha256"], v["last_error"], v["created_at"], v["updated_at"], v["completed_at"]),
                )
                counts["instagram_media"] += 1
        finally:
            old.close()
    if LEGACY_GENERIC_DB.is_file():
        old = sqlite3.connect(LEGACY_GENERIC_DB)
        old.row_factory = sqlite3.Row
        try:
            for v in old.execute("SELECT * FROM media").fetchall():
                provider = v["provider"]
                handle, external_creator_id = legacy_generic_identity(provider, v["creator"], v["source_url"])
                creator = upsert_creator_identity(conn, provider, external_creator_id, handle, handle, v["source_url"])
                creator_id = int(creator["id"])
                conn.execute(
                    """INSERT INTO media(provider,creator_id,external_id,title,description,source_url,published_at,
                                         duration_seconds,status,markdown_path,markdown_sha256,last_error,created_at,updated_at,completed_at)
                       VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                       ON CONFLICT(provider,external_id) DO UPDATE SET
                         creator_id=excluded.creator_id,title=excluded.title,description=excluded.description,
                         source_url=excluded.source_url,published_at=excluded.published_at,
                         duration_seconds=excluded.duration_seconds,status=excluded.status,
                         markdown_path=excluded.markdown_path,markdown_sha256=excluded.markdown_sha256,
                         last_error=excluded.last_error,updated_at=excluded.updated_at,completed_at=excluded.completed_at""",
                    (provider, creator_id, v["external_id"], v["title"], v["description"], v["source_url"],
                     v["published_at"], v["duration_seconds"], v["status"], v["markdown_path"], v["markdown_sha256"],
                     v["last_error"], v["created_at"], v["updated_at"], v["completed_at"]),
                )
                counts["generic_media"] += 1
        finally:
            old.close()
    conn.commit()
    conn.close()
    return counts


def platform_creator_rows() -> list[dict[str, Any]]:
    conn = connect()
    rows = conn.execute("""
      SELECT c.*, COUNT(m.id) AS tracked,
             SUM(CASE WHEN m.status='completed' THEN 1 ELSE 0 END) AS completed,
             SUM(CASE WHEN m.status NOT IN ('completed','skipped') AND m.is_current=1 THEN 1 ELSE 0 END) AS remaining,
             SUM(CASE WHEN m.is_current=0 THEN 1 ELSE 0 END) AS not_current
      FROM creators c LEFT JOIN media m ON m.creator_id=c.id
      GROUP BY c.id ORDER BY c.provider, lower(c.handle)
    """).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def _backup_sqlite(path: Path, label: str) -> Path | None:
    if not path.is_file():
        return None
    destination = ROOT / "data" / "backups" / f"{label}-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}.db"
    destination.parent.mkdir(parents=True, exist_ok=True)
    source = sqlite3.connect(path)
    target = sqlite3.connect(destination)
    try:
        source.backup(target)
    finally:
        source.close()
        target.close()
    return destination


def purge_creator(provider: str, creator_value: str, yes: bool) -> dict[str, Any]:
    if not yes:
        raise RuntimeError("Creator deletion requires --yes.")
    handle, _ = normalize_creator(provider, creator_value)
    conn = connect()
    creator = conn.execute(
        "SELECT * FROM creators WHERE provider=? AND handle=?",
        (provider, handle),
    ).fetchone()
    if not creator:
        conn.close()
        return {"provider":provider,"creator":handle,"deleted":False}

    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    target = QUARANTINE / stamp / provider / safe_name(handle)
    source = ROOT / "markdown" / provider / safe_name(handle)
    if source.exists():
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(source), str(target))

    backups = []
    for db_path, label in ((DB,"media2md"),(LEGACY_INSTAGRAM_DB,"instagram-state"),(LEGACY_GENERIC_DB,"generic-media")):
        backup = _backup_sqlite(db_path, f"before-delete-{provider}-{safe_name(handle)}-{label}")
        if backup:
            backups.append(str(backup.relative_to(ROOT)))

    if provider == "instagram" and LEGACY_INSTAGRAM_DB.is_file():
        legacy = sqlite3.connect(LEGACY_INSTAGRAM_DB)
        legacy.execute("PRAGMA foreign_keys=ON")
        row = legacy.execute("SELECT id FROM creators WHERE username=? COLLATE NOCASE", (handle,)).fetchone()
        if row:
            creator_id = row[0]
            try:
                legacy.execute("DELETE FROM attempts WHERE video_id IN (SELECT id FROM videos WHERE creator_id=?)", (creator_id,))
            except sqlite3.OperationalError:
                pass
            legacy.execute("DELETE FROM videos WHERE creator_id=?", (creator_id,))
            legacy.execute("DELETE FROM creators WHERE id=?", (creator_id,))
            legacy.commit()
        legacy.close()
    elif provider in ("youtube", "tiktok") and LEGACY_GENERIC_DB.is_file():
        legacy = sqlite3.connect(LEGACY_GENERIC_DB)
        legacy.execute("DELETE FROM media WHERE provider=? AND creator=? COLLATE NOCASE", (provider, handle))
        legacy.commit()
        legacy.close()

    conn.execute("DELETE FROM creators WHERE id=?", (creator["id"],))
    conn.commit()
    conn.close()

    policies = load_json(POLICIES, {"creators":{}})
    policies.setdefault("creators",{}).pop(f"{provider}:{handle}", None)
    if provider == "instagram":
        policies["creators"].pop(handle, None)
    atomic_json(POLICIES, policies)
    return {
        "provider":provider,
        "creator":handle,
        "deleted":True,
        "quarantine":str(target.relative_to(ROOT)) if target.exists() else None,
        "backups":backups,
    }



def _legacy_generic_reassign(provider: str, old_creator: str, new_creator: str) -> int:
    if not LEGACY_GENERIC_DB.is_file():
        return 0
    legacy = sqlite3.connect(LEGACY_GENERIC_DB)
    legacy.row_factory = sqlite3.Row
    rows = legacy.execute(
        "SELECT * FROM media WHERE provider=? AND creator=? COLLATE NOCASE",
        (provider, old_creator),
    ).fetchall()
    for row in rows:
        external_id = str(row["external_id"])
        canonical = str(row["source_url"] or "")
        if provider == "tiktok":
            canonical = f"https://www.tiktok.com/@{new_creator}/video/{external_id}"
        markdown = ROOT / "markdown" / provider / new_creator / f"{external_id}.md"
        markdown_path = row["markdown_path"]
        markdown_sha256 = row["markdown_sha256"]
        status = row["status"]
        completed_at = row["completed_at"]
        last_error = row["last_error"]
        if markdown.is_file():
            markdown_path = str(markdown.relative_to(ROOT))
            markdown_sha256 = hashlib.sha256(markdown.read_bytes()).hexdigest()
            status = "completed"
            completed_at = completed_at or iso_now()
            last_error = None
        legacy.execute(
            """UPDATE media SET creator=?,source_url=?,status=?,markdown_path=?,markdown_sha256=?,
                       completed_at=?,last_error=?,updated_at=? WHERE id=?""",
            (new_creator, canonical, status, markdown_path, markdown_sha256, completed_at, last_error, iso_now(), row["id"]),
        )
    legacy.commit()
    legacy.close()
    return len(rows)


def _candidate_from_markdown(conn: sqlite3.Connection, media_rows: list[sqlite3.Row]) -> sqlite3.Row | None:
    handles: set[str] = set()
    for media in media_rows:
        for path in (ROOT / "markdown" / "tiktok").glob(f"*/{media['external_id']}.md"):
            handle = path.parent.name
            if _is_human_tiktok_handle(handle):
                handles.add(handle)
    if len(handles) != 1:
        return None
    return conn.execute(
        "SELECT * FROM creators WHERE provider='tiktok' AND handle=? COLLATE NOCASE",
        (next(iter(handles)),),
    ).fetchone()


def _candidate_from_identifier(conn: sqlite3.Connection, opaque_value: str, exclude_id: int) -> sqlite3.Row | None:
    rows = conn.execute(
        """SELECT DISTINCT c.* FROM creators c
           LEFT JOIN creator_identifiers i ON i.creator_id=c.id
           WHERE c.provider='tiktok' AND c.id<>?
             AND (c.external_id=? OR i.identifier_value=?)""",
        (exclude_id, opaque_value, opaque_value),
    ).fetchall()
    human = [row for row in rows if _is_human_tiktok_handle(str(row["handle"]))]
    return human[0] if len(human) == 1 else None

def repair_identities(live: bool = True) -> dict[str, Any]:
    conn = connect()
    merged = 0
    live_resolved = 0
    heuristic_resolved = 0
    markdown_resolved = 0
    identifier_resolved = 0
    legacy_rows_updated = 0
    artifacts_relinked = 0
    rows = conn.execute("SELECT * FROM creators WHERE provider='tiktok' ORDER BY id").fetchall()
    for row in rows:
        handle = str(row["handle"] or "")
        if not _is_tiktok_opaque_identifier(handle):
            continue
        candidate = _candidate_from_identifier(conn, handle, int(row["id"]))
        identifiers: dict[str, str] = {}
        resolved_handle = str(candidate["handle"]) if candidate else ""
        if candidate:
            identifier_resolved += 1
        media_rows = conn.execute("SELECT * FROM media WHERE creator_id=? ORDER BY id", (row["id"],)).fetchall()
        if not candidate:
            candidate = _candidate_from_markdown(conn, media_rows)
            if candidate:
                resolved_handle = str(candidate["handle"])
                markdown_resolved += 1
        if not candidate and live and media_rows:
            resolved = _tiktok_identity_from_media_url(str(media_rows[0]["source_url"]))
            if resolved:
                resolved_handle, identifiers = resolved
                if _is_human_tiktok_handle(resolved_handle):
                    candidate = conn.execute(
                        "SELECT * FROM creators WHERE provider='tiktok' AND handle=? COLLATE NOCASE",
                        (resolved_handle,),
                    ).fetchone()
                    live_resolved += 1
        if not candidate:
            count = len(media_rows)
            candidates = conn.execute(
                """SELECT c.*, COUNT(m.id) AS tracked FROM creators c LEFT JOIN media m ON m.creator_id=c.id
                   WHERE c.provider='tiktok' AND c.id<>?
                   GROUP BY c.id HAVING c.current_total IS NOT NULL AND (c.current_total-COUNT(m.id))=?""",
                (row["id"], count),
            ).fetchall()
            candidates = [item for item in candidates if _is_human_tiktok_handle(str(item["handle"]))]
            if len(candidates) == 1:
                candidate = candidates[0]
                resolved_handle = str(candidate["handle"])
                heuristic_resolved += 1
        if not candidate or not _is_human_tiktok_handle(resolved_handle):
            continue

        primary_id = int(candidate["id"])
        old_handle = handle
        opaque_external = str(row["external_id"] or "")
        if handle.startswith("MS4wLjAB"):
            identifiers.setdefault("sec_uid", handle)
        elif handle.isdigit():
            identifiers.setdefault("user_id", handle)
        if opaque_external and _is_tiktok_opaque_identifier(opaque_external):
            identifiers.setdefault("sec_uid" if opaque_external.startswith("MS4wLjAB") else "user_id", opaque_external)

        for media in media_rows:
            external_id = str(media["external_id"])
            canonical = f"https://www.tiktok.com/@{resolved_handle}/video/{external_id}"
            markdown = ROOT / "markdown" / "tiktok" / resolved_handle / f"{external_id}.md"
            markdown_path = media["markdown_path"]
            markdown_hash = media["markdown_sha256"]
            status = media["status"]
            completed_at = media["completed_at"]
            last_error = media["last_error"]
            if markdown.is_file():
                markdown_path = str(markdown.relative_to(ROOT))
                markdown_hash = hashlib.sha256(markdown.read_bytes()).hexdigest()
                status = "completed"
                completed_at = completed_at or iso_now()
                last_error = None
                artifacts_relinked += 1
            conn.execute(
                """UPDATE media SET creator_id=?,source_url=?,status=?,markdown_path=?,markdown_sha256=?,
                           completed_at=?,last_error=?,updated_at=? WHERE id=?""",
                (primary_id, canonical, status, markdown_path, markdown_hash, completed_at, last_error, iso_now(), media["id"]),
            )

        _merge_creator_rows(conn, primary_id, int(row["id"]))
        primary = conn.execute("SELECT * FROM creators WHERE id=?", (primary_id,)).fetchone()
        strong_external = identifiers.get("sec_uid") or identifiers.get("user_id") or str(primary["external_id"] or resolved_handle)
        conn.execute(
            "UPDATE creators SET external_id=?,handle=?,display_name=?,source_url=?,updated_at=? WHERE id=?",
            (strong_external, resolved_handle, str(primary["display_name"] or resolved_handle), f"https://www.tiktok.com/@{resolved_handle}", iso_now(), primary_id),
        )
        now = iso_now()
        conn.execute(
            "INSERT OR IGNORE INTO creator_aliases(creator_id,provider,alias,first_seen_at,last_seen_at) VALUES(?,?,?,?,?)",
            (primary_id, "tiktok", old_handle, now, now),
        )
        for identifier_type, identifier_value in identifiers.items():
            conn.execute(
                """INSERT INTO creator_identifiers(creator_id,provider,identifier_type,identifier_value,first_seen_at,last_seen_at)
                   VALUES(?,?,?,?,?,?) ON CONFLICT(provider,identifier_type,identifier_value)
                   DO UPDATE SET creator_id=excluded.creator_id,last_seen_at=excluded.last_seen_at""",
                (primary_id, "tiktok", identifier_type, identifier_value, now, now),
            )
        legacy_rows_updated += _legacy_generic_reassign("tiktok", old_handle, resolved_handle)
        merged += 1
    conn.commit()
    conn.close()
    return {
        "merged_creator_rows": merged,
        "live_resolved": live_resolved,
        "heuristic_resolved": heuristic_resolved,
        "markdown_resolved": markdown_resolved,
        "identifier_resolved": identifier_resolved,
        "legacy_rows_updated": legacy_rows_updated,
        "artifacts_relinked": artifacts_relinked,
    }

def main() -> int:
    parser=argparse.ArgumentParser()
    sub=parser.add_subparsers(dest="cmd",required=True)
    sub.add_parser("migrate"); sub.add_parser("refresh-legacy"); repair=sub.add_parser("repair-identities"); repair.add_argument("--offline", action="store_true")
    sync=sub.add_parser("sync"); sync.add_argument("provider",choices=SUPPORTED); sync.add_argument("creator"); sync.add_argument("--mode",choices=("quick","full"),default="full"); sync.add_argument("--quick-window",type=int,default=100)
    runp=sub.add_parser("run"); runp.add_argument("provider",choices=("youtube","tiktok")); runp.add_argument("creator"); runp.add_argument("--mode",choices=("batch","drain"),default="batch"); runp.add_argument("--batch-size",type=int,default=100); runp.add_argument("--batch-sizes-json"); runp.add_argument("--max-batches",type=int,default=0); runp.add_argument("--max-failures",type=int,default=10); runp.add_argument("--max-runtime-minutes",type=int,default=360); runp.add_argument("--stop-on-failure",action="store_true"); runp.add_argument("--sleep-between-batches",type=float,default=5); runp.add_argument("--since"); runp.add_argument("--until"); runp.add_argument("--rank-from",type=int); runp.add_argument("--rank-to",type=int); runp.add_argument("--order",choices=("newest_first","oldest_first"),default="newest_first"); runp.add_argument("--output",choices=("human","ndjson"),default="human")
    sub.add_parser("status")
    delete=sub.add_parser("delete-creator"); delete.add_argument("provider",choices=SUPPORTED); delete.add_argument("creator"); delete.add_argument("--yes",action="store_true")
    args=parser.parse_args()
    try:
        if args.cmd=="migrate": print(json.dumps(migrate_legacy(),indent=2)); return 0
        if args.cmd=="refresh-legacy": print(json.dumps(refresh_legacy(),indent=2)); return 0
        if args.cmd=="repair-identities": print(json.dumps(repair_identities(live=not args.offline),indent=2)); return 0
        if args.cmd=="sync": print(json.dumps(sync_creator(args.provider,args.creator,args.mode,args.quick_window),ensure_ascii=False,indent=2)); return 0
        if args.cmd=="run":
            typed_sizes = json.loads(args.batch_sizes_json) if args.batch_sizes_json else None
            return creator_run(args.provider,args.creator,args.mode,args.batch_size,args.max_batches,args.max_failures,args.stop_on_failure,args.sleep_between_batches,args.since,args.until,args.rank_from,args.rank_to,args.order,args.output,args.max_runtime_minutes,typed_sizes)
        if args.cmd=="status": print(json.dumps(platform_creator_rows(),ensure_ascii=False,indent=2)); return 0
        if args.cmd=="delete-creator": print(json.dumps(purge_creator(args.provider,args.creator,args.yes),indent=2)); return 0
    except KeyboardInterrupt:
        print("REGISTRY_INTERRUPTED",file=sys.stderr); return 130
    except Exception as exc:
        print(f"ERROR: {exc}",file=sys.stderr); return 2
    return 2

if __name__=="__main__":
    raise SystemExit(main())
