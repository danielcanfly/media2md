#!/usr/bin/env python3
from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
import re
import shutil
import signal
import sqlite3
import subprocess
import sys
import time
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
if sys.path and sys.path[0] == _SCRIPT_DIR:
    sys.path.append(sys.path.pop(0))

from media2md_paths import require_command
from media2md_urls import detect_provider as detect_provider_from_value, normalize_media
from media2md_ytdlp import (classify_access_error, impersonation_args, provider_transcription_settings,
    youtube_access_args, youtube_runtime_args, youtube_audio_settings, youtube_download_strategies)
from media2md_youtube_session import youtube_auth_args, verify_youtube_session
from media2md_ocr import ocr_install_extra, perform_ocr
from media2md_runtime import (
    CommandExecutionError, classify_transcription_exception, operation_lock, run_logged, safe_artifact_stem,
)
from media2md_types import infer_media_type, output_bucket, processing_class

from media2md_auth_shared import refresh_if_configured
try:
    from media2md.remediation_service import auth_verify_command, provider_access_guidance
except ModuleNotFoundError:
    from media2md_remediation_compat import auth_verify_command, provider_access_guidance
try:
    from media2md.required_actions import validate_required_action
except ModuleNotFoundError:
    from media2md_contract_compat import validate_required_action

def _project_root() -> Path:
    explicit = os.environ.get("MEDIA2MD_PROJECT_ROOT")
    if explicit:
        root = Path(explicit).expanduser().resolve()
        root.mkdir(parents=True, exist_ok=True)
        return root
    return Path(__file__).resolve().parents[1]


SOURCE_ROOT = Path(__file__).resolve().parents[1]
ROOT = _project_root()
DB = ROOT / "data" / "social2md_media.db"
CONFIG = ROOT / "config" / "social2md.json"
AUTH_PROFILES = ROOT / "config" / "auth_profiles.json"
REGISTRY_DB = ROOT / "data" / "media2md.db"
DOWNLOADS = ROOT / "workspace" / "generic_downloads"
TRANSCRIPTS = ROOT / "workspace" / "generic_transcripts"
MARKDOWN = ROOT / "markdown"
MODEL = os.getenv("WHISPER_MODEL", "mlx-community/whisper-large-v3-turbo")
INSTALOADER_HELPER = SOURCE_ROOT / "scripts" / "instagram_instaloader.py"
TIKTOK_DOWNLOAD_HINT = ROOT / "data" / "state" / "tiktok_download_transport.json"



class StageError(RuntimeError):
    def __init__(self, stage: str, message: str, *, retryable: bool = True,
                 error_code: str = "process_error", action_required: bool = False,
                 required_action: str | None = None, root_cause: str | None = None,
                 log_path: str | None = None):
        self.stage = stage
        self.retryable = retryable
        self.error_code = error_code
        self.action_required = action_required
        self.required_action = validate_required_action(required_action)
        self.root_cause = root_cause or message
        self.log_path = log_path
        markers = [f"[stage={stage}]", f"[error_code={error_code}]", f"[retryable={str(retryable).lower()}]",
                   f"[action_required={str(action_required).lower()}]"]
        if required_action:
            markers.append(f"[required_action={required_action}]")
        if root_cause:
            markers.append(f"[root_cause={root_cause.replace(']', ')')[:1000]}]")
        if log_path:
            markers.append(f"[log_path={log_path}]")
        super().__init__(" ".join(markers) + " " + message)


def iso_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def emit(payload: dict[str, Any], output: str) -> None:
    if output == "ndjson":
        print(json.dumps({"schema_version": 12, "timestamp": iso_now(), **payload}, ensure_ascii=False, sort_keys=True), flush=True)



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


def ensure_registry(metadata: dict[str, Any]) -> None:
    from media2md_registry import (
        connect as registry_connect,
        refresh_creator_type_totals,
        upsert_creator_identity,
        youtube_long_threshold_seconds,
    )

    registry = registry_connect()
    now = iso_now()
    provider = metadata["provider"]
    handle = metadata["creator"]
    external_creator_id = metadata.get("creator_external_id") or handle
    identifiers = metadata.get("creator_identifiers") or {}
    media_type = infer_media_type(provider, metadata.get("source_url"), hinted=metadata.get("media_type"))
    item_class = processing_class(
        media_type,
        metadata.get("duration_seconds"),
        long_threshold_seconds=youtube_long_threshold_seconds(),
    )
    existing_current = registry.execute(
        """SELECT m.creator_id,c.current_total_exact
           FROM media m JOIN creators c ON c.id=m.creator_id
           WHERE m.provider=? AND m.external_id=? AND m.is_current=1""",
        (provider, metadata["external_id"]),
    ).fetchone()
    creator = upsert_creator_identity(
        registry,
        provider,
        str(external_creator_id),
        str(handle),
        str(metadata.get("creator_display_name") or handle),
        str(metadata["source_url"]),
        identifiers=identifiers,
    )
    creator_id = int(creator["id"])
    preserve_exact = bool(
        existing_current
        and int(existing_current["creator_id"]) == creator_id
        and bool(existing_current["current_total_exact"])
    )
    registry.execute(
        """INSERT INTO media(
            provider,creator_id,external_id,title,description,source_url,published_at,
            duration_seconds,media_type,processing_class,is_current,status,created_at,updated_at
        ) VALUES(?,?,?,?,?,?,?,?,?,?,1,'pending',?,?)
        ON CONFLICT(provider,external_id) DO UPDATE SET
            creator_id=excluded.creator_id,title=excluded.title,description=excluded.description,
            source_url=excluded.source_url,published_at=excluded.published_at,
            duration_seconds=COALESCE(excluded.duration_seconds,media.duration_seconds),
            media_type=excluded.media_type,processing_class=excluded.processing_class,
            is_current=1,updated_at=excluded.updated_at""",
        (
            provider,
            creator_id,
            metadata["external_id"],
            metadata["title"],
            metadata["description"],
            metadata["source_url"],
            metadata["published_at"],
            metadata["duration_seconds"],
            media_type,
            item_class,
            now,
            now,
        ),
    )
    # Reprocessing an item already present in an exact current catalog must not
    # downgrade the creator. A genuinely new manual item still invalidates the
    # previous exact snapshot until the next Full Sync.
    refresh_creator_type_totals(registry, creator_id, combined_exact=preserve_exact)
    registry.commit()
    registry.close()

def sync_registry(provider: str, external_id: str, row: sqlite3.Row) -> None:
    if not REGISTRY_DB.is_file():
        return
    try:
        registry = sqlite3.connect(REGISTRY_DB)
        media_type = row["media_type"] if "media_type" in row.keys() else infer_media_type(provider, row["source_url"])
        item_class = row["processing_class"] if "processing_class" in row.keys() else processing_class(media_type, row["duration_seconds"])
        registry.execute(
            """UPDATE media SET status=?, markdown_path=?, markdown_sha256=?, last_error=?,
               completed_at=?,duration_seconds=?,media_type=?,processing_class=?,updated_at=?
               WHERE provider=? AND external_id=?""",
            (
                row["status"],
                row["markdown_path"],
                row["markdown_sha256"],
                row["last_error"],
                row["completed_at"],
                row["duration_seconds"],
                media_type,
                item_class,
                iso_now(),
                provider,
                external_id,
            ),
        )
        registry.commit()
        registry.close()
    except sqlite3.Error:
        pass

def detect_provider(value: str, explicit: str | None = None) -> str:
    provider=explicit or detect_provider_from_value(value)
    if provider not in {"instagram","youtube","tiktok","bilibili"}:
        raise RuntimeError("Provider is required for bare handles or media IDs.")
    return provider


def command(name: str) -> str:
    try:
        return require_command(name)
    except RuntimeError as exc:
        if name == "yt-dlp":
            hint = "pip install 'media2md[youtube]' or pip install 'media2md[tiktok]'"
        elif name == "gallery-dl":
            hint = "pip install 'media2md[instagram]'"
        else:
            hint = "pip install 'media2md[mlx]'"
        raise RuntimeError(f"{exc}. Install it with: {hint}") from exc


def run(cmd: list[str], timeout: int = 7200) -> subprocess.CompletedProcess[str]:
    return run_logged(
        cmd,
        cwd=ROOT,
        timeout=timeout,
        label=Path(cmd[0]).name,
        start_new_session=False,
    )

def load_config() -> dict[str, Any]:
    try:
        return json.loads(CONFIG.read_text(encoding="utf-8"))
    except Exception:
        return {}

def _atomic_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.replace(temp, path)


def _transcription_progress_path(transcript_dir: Path) -> Path:
    return transcript_dir / "transcription_progress.json"


def _write_transcription_progress(
    transcript_dir: Path,
    *,
    stage: str,
    external_id: str,
    model: str,
    chunk_count: int,
    chunk_seconds: int | None,
    current_chunk_index: int | None,
    current_chunk_name: str | None,
    duration_seconds: float | None,
    reused_chunk_transcripts: int = 0,
) -> None:
    payload = {
        "stage": stage,
        "external_id": external_id,
        "model": model,
        "chunk_count": chunk_count,
        "chunk_seconds": chunk_seconds,
        "current_chunk_index": current_chunk_index,
        "current_chunk_name": current_chunk_name,
        "duration_seconds": duration_seconds,
        "reused_chunk_transcripts": reused_chunk_transcripts,
        "updated_at": iso_now(),
    }
    _atomic_json(_transcription_progress_path(transcript_dir), payload)


def _clear_transcription_progress(transcript_dir: Path) -> None:
    _transcription_progress_path(transcript_dir).unlink(missing_ok=True)


def _macos_proxy_types() -> list[str]:
    if sys.platform != "darwin" or not shutil.which("scutil"):
        return []
    try:
        result = subprocess.run(["scutil", "--proxy"], capture_output=True, text=True, timeout=5, check=False)
    except Exception:
        return []
    text = result.stdout or ""
    mapping = (("HTTPEnable", "http"), ("HTTPSEnable", "https"), ("SOCKSEnable", "socks"))
    return [name for key, name in mapping if re.search(rf"\\b{key}\\s*:\\s*1\\b", text)]


def _load_tiktok_download_hint(creator: str) -> dict[str, Any] | None:
    try:
        payload = json.loads(TIKTOK_DOWNLOAD_HINT.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return None
    item = (payload.get("creators") or {}).get(creator)
    return item if isinstance(item, dict) else None


def _save_tiktok_download_hint(creator: str, strategy: str, authenticated: bool) -> None:
    try:
        payload = json.loads(TIKTOK_DOWNLOAD_HINT.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        payload = {"schema_version": 1, "creators": {}}
    payload.setdefault("schema_version", 1)
    creators = payload.setdefault("creators", {})
    creators[creator] = {
        "strategy": strategy,
        "authenticated": bool(authenticated),
        "updated_at": iso_now(),
    }
    _atomic_json(TIKTOK_DOWNLOAD_HINT, payload)


def _tiktok_download_reason(text: str) -> str:
    lower = text.lower()
    if "timed out" in lower or "timeout" in lower:
        return "timeout"
    if "curl: (35)" in lower or "tls connect" in lower or "openssl_internal" in lower:
        return "tls_failure"
    if "connection closed" in lower or "connection reset" in lower or "remote disconnected" in lower:
        return "connection_closed"
    if "403" in lower or "forbidden" in lower:
        return "access_denied"
    return "extractor_failure"


def _tiktok_download_strategies(creator: str) -> list[dict[str, Any]]:
    cookie = auth_args("tiktok")
    impersonated = impersonation_args("tiktok")
    proxy_types = _macos_proxy_types()
    catalogue: list[dict[str, Any]] = []

    def add(name: str, args: list[str], authenticated: bool) -> None:
        if authenticated and not cookie:
            return
        signature = (tuple(args), authenticated)
        if any((tuple(item["args"]), item["authenticated"]) == signature for item in catalogue):
            return
        catalogue.append({
            "name": name,
            "args": list(args),
            "authenticated": authenticated,
            "auth_args": list(cookie) if authenticated else [],
        })

    direct = ["--ignore-config", "--proxy", ""]
    impersonated_direct = [*direct, *impersonated] if impersonated else []
    configured = ["--ignore-config", *impersonated] if impersonated else []

    preferred = _load_tiktok_download_hint(creator)
    if preferred:
        name = str(preferred.get("strategy") or "")
        authenticated = bool(preferred.get("authenticated"))
        args = direct if name == "direct-plain" else impersonated_direct if name == "impersonated-direct" else configured if name == "configured" else []
        if args:
            add(name, args, authenticated)
            print(
                "TIKTOK_DOWNLOAD_HINT_LOADED "
                f"creator={creator} strategy={name} authenticated={str(authenticated).lower()}",
                flush=True,
            )

    # A live macOS system proxy was the source of repeated curl-cffi TLS errors
    # in StartupBell. Prefer explicitly isolated yt-dlp requests in that case.
    add("direct-plain", direct, False)
    add("direct-plain", direct, True)
    if impersonated_direct:
        add("impersonated-direct", impersonated_direct, False)
        add("impersonated-direct", impersonated_direct, True)
    if not proxy_types and configured:
        add("configured", configured, False)
        add("configured", configured, True)
    return catalogue



def _published_to_upload_date(value: str | None) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    match = re.match(r"(\d{4})-(\d{2})-(\d{2})", text)
    return "".join(match.groups()) if match else ""


def _cached_tiktok_metadata(external_id: str, creator: str) -> dict[str, Any] | None:
    """Return locally verified TikTok metadata when live transports are unavailable."""
    queries: list[tuple[Path, str, tuple[Any, ...], str]] = [
        (
            REGISTRY_DB,
            """SELECT m.external_id,m.title,m.description,m.source_url,m.published_at,
                      m.duration_seconds,m.status,m.markdown_path,m.completed_at,
                      c.handle,c.external_id creator_external_id,c.display_name
               FROM media m JOIN creators c ON c.id=m.creator_id
               WHERE m.provider='tiktok' AND m.external_id=?
               ORDER BY m.is_current DESC,m.updated_at DESC LIMIT 1""",
            (external_id,),
            "registry_cache",
        ),
        (
            DB,
            """SELECT external_id,title,description,source_url,published_at,
                      duration_seconds,status,markdown_path,completed_at,creator
               FROM media WHERE provider='tiktok' AND external_id=?
               ORDER BY updated_at DESC LIMIT 1""",
            (external_id,),
            "processing_cache",
        ),
    ]
    for database, query, params, source in queries:
        if not database.is_file():
            continue
        try:
            conn = sqlite3.connect(database, timeout=5)
            conn.row_factory = sqlite3.Row
            row = conn.execute(query, params).fetchone()
            conn.close()
        except (sqlite3.Error, OSError):
            continue
        if not row:
            continue
        data = dict(row)
        handle = _human_tiktok_handle(data.get("handle"), data.get("creator"), creator) or creator
        creator_external_id = str(data.get("creator_external_id") or handle)
        return {
            "id": str(data.get("external_id") or external_id),
            "title": str(data.get("title") or external_id),
            "description": str(data.get("description") or ""),
            "uploader": handle,
            "channel": str(data.get("display_name") or handle),
            "channel_id": creator_external_id if creator_external_id != handle else "",
            "upload_date": _published_to_upload_date(data.get("published_at")),
            "duration": data.get("duration_seconds"),
            "webpage_url": str(data.get("source_url") or f"https://www.tiktok.com/@{handle}/video/{external_id}"),
            "_media2md_metadata_source": source,
            "_media2md_cached_status": data.get("status"),
            "_media2md_cached_markdown_path": data.get("markdown_path"),
            "_media2md_cached_completed_at": data.get("completed_at"),
        }
    return None


def _tiktok_oembed_metadata(canonical_source: str, creator: str, external_id: str) -> dict[str, Any]:
    endpoint = "https://www.tiktok.com/oembed?" + urllib.parse.urlencode({"url": canonical_source})
    request = urllib.request.Request(
        endpoint,
        headers={
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/124 Safari/537.36",
            "Accept": "application/json",
        },
    )
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    with opener.open(request, timeout=20) as response:
        payload = json.loads(response.read(1_000_000).decode("utf-8", "replace"))
    if not isinstance(payload, dict) or not payload.get("title"):
        raise RuntimeError("TikTok oEmbed returned no usable metadata.")
    return {
        "id": external_id,
        "title": str(payload.get("title") or external_id),
        "description": str(payload.get("title") or ""),
        "uploader": creator,
        "channel": str(payload.get("author_name") or creator),
        "channel_id": "",
        "upload_date": "",
        "duration": None,
        "webpage_url": canonical_source,
        "_media2md_metadata_source": "tiktok_oembed",
    }


def tiktok_recent_completion(external_id: str, *, max_age_hours: int = 168) -> dict[str, Any] | None:
    """Return recent real end-to-end completion evidence for Doctor degradation handling."""
    now = datetime.now(timezone.utc)
    candidates: list[dict[str, Any]] = []
    for database, query in (
        (
            REGISTRY_DB,
            """SELECT m.status,m.markdown_path,m.completed_at,m.updated_at,c.handle creator
               FROM media m JOIN creators c ON c.id=m.creator_id
               WHERE m.provider='tiktok' AND m.external_id=?
               ORDER BY m.updated_at DESC LIMIT 1""",
        ),
        (
            DB,
            """SELECT status,markdown_path,completed_at,updated_at,creator
               FROM media WHERE provider='tiktok' AND external_id=?
               ORDER BY updated_at DESC LIMIT 1""",
        ),
    ):
        if not database.is_file():
            continue
        try:
            conn = sqlite3.connect(database, timeout=5)
            conn.row_factory = sqlite3.Row
            row = conn.execute(query, (external_id,)).fetchone()
            conn.close()
        except (sqlite3.Error, OSError):
            continue
        if row:
            candidates.append(dict(row))
    for item in candidates:
        if str(item.get("status") or "").lower() != "completed":
            continue
        stamp = str(item.get("completed_at") or item.get("updated_at") or "")
        try:
            moment = datetime.fromisoformat(stamp.replace("Z", "+00:00"))
            if moment.tzinfo is None:
                moment = moment.replace(tzinfo=timezone.utc)
            age_hours = (now - moment.astimezone(timezone.utc)).total_seconds() / 3600
        except (TypeError, ValueError):
            continue
        if age_hours < 0 or age_hours > max_age_hours:
            continue
        markdown = Path(str(item.get("markdown_path") or ""))
        if markdown and not markdown.is_absolute():
            markdown = ROOT / markdown
        if not markdown.is_file():
            continue
        return {
            "creator": item.get("creator"),
            "completed_at": stamp,
            "age_hours": round(age_hours, 2),
            "markdown_path": str(markdown),
            "markdown_sha256": hashlib.sha256(markdown.read_bytes()).hexdigest(),
        }
    return None


def inspect_tiktok_metadata(
    canonical_source: str,
    creator: str,
    external_id: str,
) -> dict[str, Any]:
    """Inspect TikTok metadata through the same bounded transport cascade as downloads."""
    try:
        total_budget = max(60, int(os.getenv("MEDIA2MD_TIKTOK_INSPECT_BUDGET_SECONDS", "300")))
    except ValueError:
        total_budget = 300
    try:
        attempt_cap = max(30, int(os.getenv("MEDIA2MD_TIKTOK_INSPECT_ATTEMPT_TIMEOUT_SECONDS", "120")))
    except ValueError:
        attempt_cap = 120
    deadline = time.monotonic() + total_budget
    errors: list[str] = []
    for strategy in _tiktok_download_strategies(creator):
        remaining = deadline - time.monotonic()
        if remaining < 5:
            print(
                "TIKTOK_INSPECT_BUDGET_EXHAUSTED "
                f"creator={creator} media_id={external_id} remaining_seconds={max(0, int(remaining))}",
                flush=True,
            )
            break
        timeout = min(attempt_cap, max(5, int(remaining)))
        print(
            "TIKTOK_INSPECT_ATTEMPT "
            f"creator={creator} media_id={external_id} strategy={strategy['name']} "
            f"authenticated={str(strategy['authenticated']).lower()} timeout_seconds={timeout}",
            flush=True,
        )
        started = time.monotonic()
        try:
            result = run([
                command("yt-dlp"), *strategy["args"], *strategy["auth_args"],
                "--dump-single-json", "--skip-download", "--no-playlist", canonical_source,
            ], timeout=timeout)
            payload = json.loads(result.stdout)
            if not isinstance(payload, dict):
                raise RuntimeError("yt-dlp returned a non-object TikTok metadata payload.")
        except KeyboardInterrupt:
            raise
        except Exception as exc:
            elapsed = int(time.monotonic() - started)
            reason = _tiktok_download_reason(str(exc))
            errors.append(f"{strategy['name']}/auth={strategy['authenticated']}: {str(exc)[-1200:]}")
            print(
                "TIKTOK_INSPECT_ATTEMPT_RESULT "
                f"creator={creator} media_id={external_id} strategy={strategy['name']} "
                f"authenticated={str(strategy['authenticated']).lower()} status=failed "
                f"reason={reason} elapsed_seconds={elapsed}",
                flush=True,
            )
            continue
        elapsed = int(time.monotonic() - started)
        _save_tiktok_download_hint(creator, strategy["name"], bool(strategy["authenticated"]))
        print(
            "TIKTOK_INSPECT_ATTEMPT_RESULT "
            f"creator={creator} media_id={external_id} strategy={strategy['name']} "
            f"authenticated={str(strategy['authenticated']).lower()} status=success "
            f"elapsed_seconds={elapsed}",
            flush=True,
        )
        print(
            "TIKTOK_DOWNLOAD_HINT_SAVED "
            f"creator={creator} strategy={strategy['name']} authenticated={str(strategy['authenticated']).lower()}",
            flush=True,
        )
        return payload
    cached = _cached_tiktok_metadata(external_id, creator)
    if cached:
        print(
            "TIKTOK_INSPECT_FALLBACK "
            f"creator={creator} media_id={external_id} source={cached.get('_media2md_metadata_source')} "
            "live_transports_exhausted=true",
            flush=True,
        )
        return cached
    try:
        oembed = _tiktok_oembed_metadata(canonical_source, creator, external_id)
    except Exception as exc:
        errors.append(f"tiktok-oembed: {str(exc)[-1200:]}")
    else:
        print(
            "TIKTOK_INSPECT_FALLBACK "
            f"creator={creator} media_id={external_id} source=tiktok_oembed "
            "live_transports_exhausted=true",
            flush=True,
        )
        return oembed
    raise RuntimeError(
        "TikTok metadata strategies exhausted within bounded inspect budget. "
        + " | ".join(errors)[-5000:]
    )


def download_tiktok_audio(
    canonical_source: str,
    work: Path,
    external_id: str,
    creator: str,
    template: str,
) -> tuple[Path, str, bool, list[dict[str, Any]]]:
    try:
        total_budget = max(60, int(os.getenv("MEDIA2MD_TIKTOK_DOWNLOAD_ITEM_BUDGET_SECONDS", "300")))
    except ValueError:
        total_budget = 300
    try:
        attempt_cap = max(30, int(os.getenv("MEDIA2MD_TIKTOK_DOWNLOAD_ATTEMPT_TIMEOUT_SECONDS", "120")))
    except ValueError:
        attempt_cap = 120
    deadline = time.monotonic() + total_budget
    attempts: list[dict[str, Any]] = []
    errors: list[str] = []
    for strategy in _tiktok_download_strategies(creator):
        remaining = deadline - time.monotonic()
        if remaining < 5:
            print(
                "TIKTOK_DOWNLOAD_BUDGET_EXHAUSTED "
                f"creator={creator} media_id={external_id} remaining_seconds={max(0, int(remaining))}",
                flush=True,
            )
            break
        timeout = min(attempt_cap, max(5, int(remaining)))
        _cleanup_partial_downloads(work)
        print(
            "TIKTOK_DOWNLOAD_ATTEMPT "
            f"creator={creator} media_id={external_id} strategy={strategy['name']} "
            f"authenticated={str(strategy['authenticated']).lower()} timeout_seconds={timeout}",
            flush=True,
        )
        started = time.monotonic()
        command_line = [
            command("yt-dlp"), *strategy["args"], *strategy["auth_args"],
            "--no-playlist", "--no-progress", "--retries", "1", "--extractor-retries", "1",
            "--socket-timeout", "45", "-f", "ba/b", "-x", "--audio-format", "m4a",
            "-o", template, canonical_source,
        ]
        try:
            run(command_line, timeout=timeout)
            files = _audio_candidates(work)
            if not files:
                raise RuntimeError("yt-dlp completed but no media file was created.")
            media = max(files, key=lambda path: path.stat().st_size)
        except KeyboardInterrupt:
            raise
        except Exception as exc:
            elapsed = int(time.monotonic() - started)
            reason = _tiktok_download_reason(str(exc))
            attempts.append({
                "strategy": strategy["name"], "uses_auth": strategy["authenticated"],
                "ok": False, "reason": reason, "elapsed_seconds": elapsed,
                "error": str(exc)[-1000:],
            })
            errors.append(f"{strategy['name']}/auth={strategy['authenticated']}: {str(exc)[-1200:]}")
            print(
                "TIKTOK_DOWNLOAD_ATTEMPT_RESULT "
                f"creator={creator} media_id={external_id} strategy={strategy['name']} "
                f"authenticated={str(strategy['authenticated']).lower()} status=failed "
                f"reason={reason} elapsed_seconds={elapsed}",
                flush=True,
            )
            continue
        elapsed = int(time.monotonic() - started)
        attempts.append({
            "strategy": strategy["name"], "uses_auth": strategy["authenticated"],
            "ok": True, "reason": None, "elapsed_seconds": elapsed, "error": None,
        })
        _save_tiktok_download_hint(creator, strategy["name"], bool(strategy["authenticated"]))
        print(
            "TIKTOK_DOWNLOAD_ATTEMPT_RESULT "
            f"creator={creator} media_id={external_id} strategy={strategy['name']} "
            f"authenticated={str(strategy['authenticated']).lower()} status=success "
            f"elapsed_seconds={elapsed}",
            flush=True,
        )
        print(
            "TIKTOK_DOWNLOAD_HINT_SAVED "
            f"creator={creator} strategy={strategy['name']} authenticated={str(strategy['authenticated']).lower()}",
            flush=True,
        )
        return media, str(strategy["name"]), bool(strategy["authenticated"]), attempts
    raise RuntimeError(
        "TikTok download strategies exhausted within bounded item budget. "
        + " | ".join(errors)[-5000:]
    )



def instagram_backend() -> str:
    value = str(load_config().get("providers", {}).get("instagram", {}).get("backend", "auto"))
    return value if value in {"auto", "gallery-dl", "instaloader"} else "auto"


def _inspect_instagram_gallery(url: str, target: Any, creator: str | None) -> dict[str, Any]:
    cmd=[command("gallery-dl")]
    cookie_file=ROOT/"data"/"secrets"/"instagram-cookies.txt"
    if cookie_file.is_file(): cmd += ["--cookies",str(cookie_file)]
    cmd += ["--resolve-json",url]
    result=run(cmd,timeout=300); payload=json.loads(result.stdout); metadata=None
    assets: list[dict[str, Any]] = []
    if isinstance(payload,list):
        for event in payload:
            if not (isinstance(event, list) and len(event) >= 3 and isinstance(event[2], dict)):
                continue
            event_type = event[0]
            event_url = str(event[1] or "")
            item = event[2]
            if metadata is None:
                metadata = item
            if event_type != 3:
                continue
            display_url = str(item.get("display_url") or event_url or "").strip()
            video_url = str(item.get("video_url") or "").strip()
            extension = str(item.get("extension") or "").strip().lower()
            is_video = bool(video_url) or extension in {"mp4", "mov", "m4v", "webm"}
            asset_url = video_url if is_video and video_url else display_url or event_url
            if not asset_url:
                continue
            assets.append({
                "index": int(item.get("num") or len(assets) + 1),
                "kind": "video" if is_video else "image",
                "source_url": asset_url,
                "display_url": display_url or asset_url,
                "width": item.get("width"),
                "height": item.get("height"),
                "ocr_candidate": not is_video,
            })
    if not metadata: raise RuntimeError("gallery-dl returned no Instagram metadata.")
    external_id=str(metadata.get("post_shortcode") or metadata.get("shortcode") or target.media_id or "")
    handle=str(metadata.get("username") or (metadata.get("owner") or {}).get("username") or creator or "unknown")
    surface = str(getattr(target, "surface", None) or "reel")
    if surface == "reel":
        media_type = "instagram_reel"
    else:
        sidecar_count = int(metadata.get("sidecar_count") or metadata.get("count") or 0)
        image_count = len([item for item in assets if str(item.get("kind") or "") == "image"])
        video_count = len([item for item in assets if str(item.get("kind") or "") == "video"])
        asset_count = len(assets)
        media_type = "instagram_carousel" if max(sidecar_count, image_count, video_count, asset_count, 0) > 1 else "instagram_post"
    return {"provider":"instagram","external_id":external_id,"creator":handle,"creator_external_id":str(metadata.get("owner_id") or metadata.get("user_id") or handle),
            "creator_identifiers":{"user_id": str(metadata.get("owner_id") or metadata.get("user_id") or "")},
            "creator_display_name":handle,"title":f"Instagram {'Reel' if media_type == 'instagram_reel' else 'Post'} {external_id}","description":str(metadata.get("description") or ""),
            "published_at":str(metadata.get("post_date") or metadata.get("date") or "") or None,"duration_seconds":metadata.get("duration") if media_type == "instagram_reel" else None,"source_url":url,
            "surface":surface,
            "media_type":media_type,"processing_class":media_type,"assets": assets,
            "backend_used":"gallery-dl"}


def _inspect_instagram_instaloader(shortcode: str) -> dict[str, Any]:
    if not INSTALOADER_HELPER.is_file():
        raise RuntimeError(f"Instaloader helper is missing: {INSTALOADER_HELPER}")
    result = run([sys.executable, str(INSTALOADER_HELPER), "inspect", shortcode], timeout=300)
    payload = json.loads(result.stdout)
    payload.setdefault("backend_used", "instaloader")
    payload.setdefault("creator_identifiers", {"user_id": str(payload.get("creator_external_id") or "")})
    return payload


def _youtube_challenge_hint(error: str) -> str:
    lower = error.lower()
    if any(token in lower for token in ("challenge solver", "signature solving", "only images are available", "requested format is not available")):
        guidance = provider_access_guidance("youtube", error_code="missing_dependency", required_action="install_provider_extra")
        doctor_command = "media2md doctor youtube-access --video-id=<VIDEO_ID>"
        install_guidance = guidance[0] if guidance else "Run: python -m pip install -U \"media2md[youtube]\""
        return error + f"\nRun '{doctor_command}' and ensure YouTube support is installed. {install_guidance}"
    return error


def _instagram_metadata_access_hint(error: str) -> str:
    lower = error.lower()
    if any(token in lower for token in (
        "403", "forbidden", "login", "challenge", "anonymous metadata access",
        "could not inspect shortcode", "owner metadata", "no instagram metadata",
    )):
        verify_command = auth_verify_command("instagram")
        return (
            error
            + "\nInstagram metadata access was rejected. Reconnect or verify the selected browser profile, "
              f"then retry with '{verify_command}'."
        )
    return error


def _bilibili_access_hint(error: str) -> str:
    lower = error.lower()
    if any(token in lower for token in ("missing_dependency", "not installed", "bilibili support is not installed")):
        guidance = provider_access_guidance("bilibili", error_code="missing_dependency", required_action="install_provider_extra")
        doctor_command = "media2md doctor bilibili-access --video-id=<BV_VIDEO_ID>"
        install_guidance = guidance[0] if guidance else 'Run: python -m pip install -U "media2md[bilibili]"'
        return error + f"\nRun '{doctor_command}' and ensure Bilibili support is installed. {install_guidance}"
    if any(token in lower for token in ("sessdata", "credential", "audio stream", "subtitle", "playable pages", "valid cid")):
        guidance = provider_access_guidance("bilibili", required_action="repair_provider_identities")
        doctor_command = "media2md doctor bilibili-access --video-id=<BV_VIDEO_ID>"
        extra = guidance[0] if guidance else "Run: media2md repair identities"
        return error + f"\nRun '{doctor_command}' to verify the Bilibili pipeline. {extra}"
    return error


def _is_tiktok_opaque_identifier(value: str | None) -> bool:
    text = str(value or "").strip().lstrip("@")
    return bool(text) and (text.isdigit() or text.startswith("MS4wLjAB") or len(text) > 40)


def _human_tiktok_handle(*values: str | None) -> str | None:
    for value in values:
        text = str(value or "").strip().lstrip("@")
        if text and not _is_tiktok_opaque_identifier(text) and re.fullmatch(r"[A-Za-z0-9._-]+", text):
            return text
    return None


def canonical_media_source(provider: str, external_id: str, source_url: str, creator: str) -> str:
    if provider == "youtube":
        if not re.fullmatch(r"[A-Za-z0-9_-]{11}", external_id):
            raise StageError("validation", f"Invalid YouTube video ID: {external_id}", retryable=False)
        canonical = f"https://www.youtube.com/watch?v={external_id}"
        if "?v=" not in canonical:
            raise StageError("validation", "YouTube watch URL is missing the required v parameter.", retryable=False)
        return canonical
    if provider == "tiktok":
        if not re.fullmatch(r"\d{8,24}", external_id):
            raise StageError("validation", f"Invalid TikTok video ID: {external_id}", retryable=False)
        handle = _human_tiktok_handle(creator)
        if not handle:
            match = re.search(r"tiktok\.com/@([A-Za-z0-9._-]+)/video/", source_url, re.I)
            handle = _human_tiktok_handle(match.group(1) if match else None)
        if not handle:
            raise StageError("validation", "TikTok media has no human-readable creator handle.", retryable=False)
        return f"https://www.tiktok.com/@{handle}/video/{external_id}"
    if provider == "bilibili":
        if not re.fullmatch(r"BV[A-Za-z0-9]{10}", external_id):
            raise StageError("validation", f"Invalid Bilibili BV video ID: {external_id}", retryable=False)
        return f"https://www.bilibili.com/video/{external_id}"
    try:
        return normalize_media(provider, source_url, creator=creator).canonical_url
    except ValueError as exc:
        raise StageError("validation", str(exc), retryable=False) from exc


def cleanup_workspace_paths(*paths: Path) -> None:
    for path in paths:
        shutil.rmtree(path, ignore_errors=True)
    for path in paths:
        parent = path.parent
        while parent != ROOT and parent.name in {"generic_downloads", "generic_transcripts", "youtube", "tiktok"}:
            try:
                parent.rmdir()
            except OSError:
                break
            parent = parent.parent


def inspect(value: str, provider: str | None = None, creator: str | None = None) -> dict[str, Any]:
    original_value = value
    provider=detect_provider(value,provider)
    try:
        target=normalize_media(provider,value,creator=creator)
    except ValueError as exc:
        raise RuntimeError(str(exc)) from exc
    url=target.canonical_url
    if provider=="instagram":
        backend = instagram_backend()
        gallery_error: Exception | None = None
        if backend in {"auto", "gallery-dl"}:
            try:
                return _inspect_instagram_gallery(url, target, creator)
            except Exception as exc:
                gallery_error = exc
                if backend == "gallery-dl":
                    raise
                print(f"BACKEND_FALLBACK provider=instagram from=gallery-dl to=instaloader reason={type(exc).__name__}: {exc}", file=sys.stderr)
        if backend in {"auto", "instaloader"}:
            try:
                payload = _inspect_instagram_instaloader(str(target.media_id))
                surface = str(target.surface or payload.get("surface") or "reel")
                payload["surface"] = surface
                payload["source_url"] = target.canonical_url
                if surface == "tv":
                    payload["media_type"] = "instagram_reel"
                    payload["processing_class"] = "instagram_reel"
                elif surface == "post":
                    assets = payload.get("assets") or []
                    payload["media_type"] = "instagram_carousel" if len(assets) > 1 else "instagram_post"
                    payload["processing_class"] = str(payload["media_type"])
                else:
                    payload.setdefault("media_type", "instagram_reel")
                    payload.setdefault("processing_class", "instagram_reel")
                if gallery_error:
                    payload["backend_fallback_from"] = "gallery-dl"
                    payload["backend_fallback_reason"] = str(gallery_error)
                return payload
            except Exception as instaloader_error:
                if gallery_error:
                    combined = (
                        f"Both Instagram metadata backends failed. "
                        f"gallery-dl={gallery_error}; instaloader={instaloader_error}"
                    )
                    raise RuntimeError(_instagram_metadata_access_hint(combined)) from instaloader_error
                raise
    if provider == "tiktok":
        tiktok_creator = _human_tiktok_handle(target.creator, creator)
        if not tiktok_creator:
            raise RuntimeError("TikTok metadata inspection requires a human-readable creator handle.")
        data = inspect_tiktok_metadata(url, tiktok_creator, str(target.media_id or ""))
    elif provider == "bilibili":
        try:
            data = inspect_bilibili_metadata(url, str(target.media_id or ""))
        except Exception as exc:
            raise RuntimeError(_bilibili_access_hint(str(exc))) from exc
    else:
        ytdlp_args = youtube_runtime_args()
        public_cmd = [command("yt-dlp"), *ytdlp_args, "--dump-single-json", "--skip-download", "--no-playlist", url]
        try:
            result = run(public_cmd, timeout=300)
        except RuntimeError as public_exc:
            if auth_args("youtube"):
                try:
                    _auth_preflight(str(target.media_id or ""))
                    result = run([command("yt-dlp"), *ytdlp_args, *auth_args("youtube"), "--dump-single-json", "--skip-download", "--no-playlist", url], timeout=300)
                except Exception as auth_exc:
                    raise RuntimeError(_youtube_challenge_hint(str(auth_exc))) from auth_exc
            else:
                raise RuntimeError(_youtube_challenge_hint(str(public_exc))) from public_exc
        data = json.loads(result.stdout)
    upload=str(data.get("upload_date") or ""); published=None
    if re.fullmatch(r"\d{8}",upload): published=datetime.strptime(upload,"%Y%m%d").replace(tzinfo=timezone.utc).isoformat(timespec="seconds")
    published = str(data.get("_media2md_bilibili_published_at") or published or "") or None
    identifiers: dict[str, str] = {}
    if provider=="tiktok":
        sec_uid = str(data.get("channel_id") or "").strip()
        user_id = str(data.get("uploader_id") or data.get("creator_id") or "").strip()
        handle = _human_tiktok_handle(
            target.creator,
            creator,
            data.get("uploader"),
            data.get("channel"),
            data.get("uploader_id"),
        )
        if not handle:
            raise RuntimeError("TikTok metadata did not contain a human-readable creator handle.")
        if sec_uid: identifiers["sec_uid"] = sec_uid
        if user_id and user_id != handle: identifiers["user_id"] = user_id
        creator_external_id = sec_uid or user_id or handle
    else:
        raw=str(data.get("uploader_id") or data.get("channel") or data.get("uploader") or creator or "unknown")
        handle=raw.lstrip("@")
        channel_id = str(data.get("channel_id") or "").strip()
        uploader_id = str(data.get("uploader_id") or "").strip()
        if channel_id: identifiers["channel_id"] = channel_id
        if uploader_id: identifiers["uploader_id"] = uploader_id
        creator_external_id=channel_id or uploader_id or handle
    external_id=str(data.get("id") or target.media_id or "")
    if not external_id: raise RuntimeError("Metadata did not contain a media id.")
    hinted_media_type: str | None = None
    if provider == "instagram":
        if str(target.surface or "") == "post":
            hinted_media_type = "instagram_post"
        elif str(target.surface or "") == "tv":
            hinted_media_type = "instagram_reel"
    media_type = infer_media_type(provider, url, hinted=hinted_media_type)
    item_class = processing_class(
        media_type,
        data.get("duration"),
        long_threshold_seconds=int(load_config().get("providers", {}).get("youtube", {}).get("long_video_threshold_seconds", 2700)),
    )
    return {"provider":provider,"external_id":external_id,"creator":handle,"creator_external_id":creator_external_id,
            "creator_identifiers": identifiers,
            "creator_display_name":str(data.get("channel") or data.get("uploader") or handle),"title":str(data.get("title") or external_id),
            "description":str(data.get("description") or ""),"published_at":published,"duration_seconds":data.get("duration"),
            "source_url":url,"media_type":media_type,"processing_class":item_class,
            "metadata_source":str(data.get("_media2md_metadata_source") or "yt-dlp-live")}

def connect() -> sqlite3.Connection:
    DB.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB, timeout=60)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=60000")
    conn.execute("""
        CREATE TABLE IF NOT EXISTS media (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            provider TEXT NOT NULL,
            external_id TEXT NOT NULL,
            creator TEXT NOT NULL,
            title TEXT,
            description TEXT,
            source_url TEXT NOT NULL,
            published_at TEXT,
            duration_seconds REAL,
            media_type TEXT,
            processing_class TEXT,
            status TEXT NOT NULL DEFAULT 'pending',
            markdown_path TEXT,
            markdown_sha256 TEXT,
            last_error TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            completed_at TEXT,
            UNIQUE(provider, external_id)
        )
    """)
    columns = {row[1] for row in conn.execute("PRAGMA table_info(media)")}
    for name in ("media_type", "processing_class"):
        if name not in columns:
            conn.execute(f"ALTER TABLE media ADD COLUMN {name} TEXT")
    threshold = int(load_config().get("providers", {}).get("youtube", {}).get("long_video_threshold_seconds", 2700))
    conn.execute("UPDATE media SET media_type='instagram_reel' WHERE provider='instagram' AND (media_type IS NULL OR media_type='')")
    conn.execute("UPDATE media SET media_type='tiktok_video' WHERE provider='tiktok' AND (media_type IS NULL OR media_type='')")
    conn.execute("UPDATE media SET media_type='youtube_video' WHERE provider='youtube' AND (media_type IS NULL OR media_type='')")
    conn.execute("UPDATE media SET media_type='bilibili_video' WHERE provider='bilibili' AND (media_type IS NULL OR media_type='')")
    conn.execute(
        "UPDATE media SET processing_class=CASE WHEN provider='youtube' AND media_type='youtube_video' "
        "AND COALESCE(duration_seconds,0)>=? THEN 'youtube_long' ELSE media_type END "
        "WHERE processing_class IS NULL OR processing_class=''",
        (threshold,),
    )
    conn.commit()
    return conn


def safe(value: str) -> str:
    cleaned = re.sub(r"[^\w.-]+", "_", value.strip(), flags=re.UNICODE)
    return cleaned[:120] or "unknown"


def locale_pack() -> dict[str, str]:
    locale = "en"
    try:
        locale = json.loads(CONFIG.read_text()).get("markdown_locale", "en")
    except Exception:
        pass
    packs = {
        "en": {
            "caption": "Description",
            "transcript": "Transcript",
            "title": "Social Video",
            "image_ocr": "Image OCR",
            "combined_ocr": "Combined OCR Notes",
            "image": "Image",
            "no_image_text": "_No text detected in image._",
            "filtered_sponsor_segments": "Filtered Sponsor Segments",
        },
        "zh-TW": {
            "caption": "原始說明",
            "transcript": "語音逐字稿",
            "title": "社群影片",
            "image_ocr": "圖片文字擷取",
            "combined_ocr": "合併文字筆記",
            "image": "圖片",
            "no_image_text": "_圖片中未偵測到文字。_",
            "filtered_sponsor_segments": "已過濾的業配段落",
        },
        "zh-CN": {
            "caption": "原始说明",
            "transcript": "语音转录",
            "title": "社交视频",
            "image_ocr": "图片文字提取",
            "combined_ocr": "合并文字笔记",
            "image": "图片",
            "no_image_text": "_图片中未检测到文字。_",
            "filtered_sponsor_segments": "已过滤的赞助段落",
        },
        "ja": {
            "caption": "元の説明",
            "transcript": "文字起こし",
            "title": "ソーシャル動画",
            "image_ocr": "画像OCR",
            "combined_ocr": "OCR統合メモ",
            "image": "画像",
            "no_image_text": "_画像内にテキストは検出されませんでした。_",
            "filtered_sponsor_segments": "フィルタ済みスポンサー区間",
        },
    }
    return packs.get(locale, packs["en"])


_YOUTUBE_SPONSOR_STRONG_PATTERNS = (
    r"\bthis (video|episode|stream) is sponsored by\b",
    r"\bthanks to .{0,80}\bfor sponsoring (this (video|episode|stream)|today(?:'s)? (video|episode|stream))\b",
    r"\bbrought to you by\b",
    r"\bpaid promotion\b",
    r"\bour sponsor(?:s|ed)?\b",
    r"\baffiliate link(?:s)?\b",
    r"\bpromo code\b",
    r"\bdiscount code\b",
    r"\buse code\s+[A-Za-z0-9_-]{3,}\b",
)

_YOUTUBE_SPONSOR_WEAK_PATTERNS = (
    r"\bcheck out\b",
    r"\blink in (the )?description\b",
    r"\bfree trial\b",
    r"\bsign up\b",
    r"\bjoin today\b",
    r"\bpartner(?:ed)? with\b",
)


def youtube_sponsor_filter_mode() -> str:
    youtube = load_config().get("providers", {}).get("youtube", {})
    value = str(youtube.get("sponsor_filter", "conservative") or "conservative").strip().lower()
    return value if value in {"off", "conservative", "aggressive"} else "conservative"


def _split_youtube_transcript_blocks(text: str) -> list[str]:
    chunk_heading = re.compile(r"^### \d{2}:\d{2}:\d{2}[–-]\d{2}:\d{2}:\d{2}\s*$", re.M)
    if chunk_heading.search(text):
        blocks: list[str] = []
        current: list[str] = []
        for line in text.splitlines():
            if chunk_heading.match(line.strip()):
                if current:
                    blocks.append("\n".join(current).strip())
                    current = []
            current.append(line)
        if current:
            blocks.append("\n".join(current).strip())
        return [block for block in blocks if block.strip()]
    paragraphs = [part.strip() for part in re.split(r"\n\s*\n", text) if part.strip()]
    if len(paragraphs) > 1:
        return paragraphs
    return [line.strip() for line in text.splitlines() if line.strip()]


def _is_probable_youtube_sponsor_block(block: str) -> bool:
    return _is_probable_youtube_sponsor_block_for_mode(block, "conservative")


def _is_probable_youtube_sponsor_block_for_mode(block: str, mode: str) -> bool:
    lower = block.lower()
    strong_hits = sum(1 for pattern in _YOUTUBE_SPONSOR_STRONG_PATTERNS if re.search(pattern, lower, re.I))
    weak_hits = sum(1 for pattern in _YOUTUBE_SPONSOR_WEAK_PATTERNS if re.search(pattern, lower, re.I))
    if strong_hits == 0 and weak_hits == 0:
        return False
    if len(block) > 1600:
        return False
    if lower.count("http") >= 2 or ("link" in lower and "description" in lower):
        return True
    if any(token in lower for token in ("promo code", "discount code", "affiliate link", "use code ")):
        return True
    if strong_hits >= 2:
        return True
    if mode == "aggressive":
        if strong_hits >= 1 and weak_hits >= 1:
            return True
        if weak_hits >= 2 and any(token in lower for token in ("description", "trial", "sign up", "partner")):
            return True
    return bool(re.search(r"\bsponsored by\b", lower, re.I))


def filter_youtube_sponsor_segments(text: str, *, mode: str = "conservative") -> dict[str, Any]:
    resolved_mode = mode if mode in {"off", "conservative", "aggressive"} else "conservative"
    if resolved_mode == "off":
        return {
            "text": text,
            "filtered": False,
            "mode": "off",
            "removed_segments": [],
            "removed_count": 0,
            "reason": "disabled",
        }
    blocks = _split_youtube_transcript_blocks(text)
    removed: list[str] = []
    kept: list[str] = []
    for block in blocks:
        if _is_probable_youtube_sponsor_block_for_mode(block, resolved_mode):
            removed.append(block)
        else:
            kept.append(block)
    filtered_text = "\n\n".join(kept).strip()
    if removed and not filtered_text:
        return {
            "text": text,
            "filtered": False,
            "mode": resolved_mode,
            "removed_segments": [],
            "removed_count": 0,
            "reason": "no_safe_non_sponsor_content_remaining",
        }
    return {
        "text": filtered_text or text,
        "filtered": bool(removed),
        "mode": resolved_mode,
        "removed_segments": removed,
        "removed_count": len(removed),
        "reason": (
            f"youtube_sponsor_filter_{resolved_mode}"
            if removed
            else "no_sponsor_segments_detected"
        ),
    }


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024*1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _instagram_media_assets(metadata: dict[str, Any], work: Path) -> list[Path]:
    assets = metadata.get("assets") or []
    files: list[Path] = []
    for index, asset in enumerate(assets, start=1):
        kind = str(asset.get("kind") or "").strip().lower()
        display_url = str(asset.get("display_url") or "").strip()
        source_url = str(asset.get("source_url") or "").strip()
        if kind != "image" and not display_url:
            continue
        download_url = source_url if kind == "image" else display_url or source_url
        if kind == "video" and display_url:
            download_url = display_url
        source_url = download_url.strip()
        if not source_url:
            continue
        suffix = Path(source_url.split("?", 1)[0]).suffix or ".jpg"
        target = work / f"asset_{index}{suffix}"
        request = urllib.request.Request(
            source_url,
            headers={"User-Agent": "Mozilla/5.0", "Referer": str(metadata.get("source_url") or "https://www.instagram.com/")},
        )
        with urllib.request.urlopen(request, timeout=180) as response, target.open("wb") as handle:
            while True:
                chunk = response.read(1024 * 1024)
                if not chunk:
                    break
                handle.write(chunk)
        if target.is_file() and target.stat().st_size > 0:
            files.append(target)
    return files


def render_standard_markdown(
    *,
    provider: str,
    creator: str,
    external_id: str,
    media_type: str,
    item_class: str,
    artifact_stem: str,
    canonical_source: str,
    published_at: str,
    transcription_source: str,
    caption_language: str | None,
    transcription_model: str | None,
    processed_duration: float,
    audio_download_strategy: str | None,
    audio_used_auth: bool | None,
    audio_attempts: list[dict[str, Any]],
    chunk_count: int,
    chunk_seconds_used: int | None,
    resumed_from_checkpoint: bool,
    caption_probe_result: str | None,
    transcript_filter_reason: str | None,
    sponsor_filter_applied: bool,
    sponsor_filter_mode: str | None,
    sponsor_segments_filtered: int,
    sponsor_segments_removed: list[str],
    title: str,
    description: str,
    text: str,
) -> str:
    pack = locale_pack()
    lines = [
        "---",
        f"platform: {provider}",
        f"creator: {json.dumps(creator, ensure_ascii=False)}",
        f"media_id: {json.dumps(external_id)}",
        f"media_type: {json.dumps(media_type)}",
        f"processing_class: {json.dumps(item_class)}",
        f"artifact_stem: {json.dumps(artifact_stem)}",
        f"source_url: {json.dumps(canonical_source)}",
        f"published_at: {json.dumps(published_at or '')}",
        f"processed_at: {json.dumps(iso_now())}",
        f"transcription_source: {json.dumps(transcription_source)}",
        f"caption_language: {json.dumps(caption_language)}",
        f"caption_probe_result: {json.dumps(caption_probe_result)}",
        f"transcription_model: {json.dumps(transcription_model)}",
        f"duration_seconds: {json.dumps(processed_duration)}",
        f"audio_download_strategy: {json.dumps(audio_download_strategy)}",
        f"audio_used_auth: {json.dumps(audio_used_auth)}",
        f"audio_attempts: {json.dumps(audio_attempts, ensure_ascii=False)}",
        f"chunk_count: {json.dumps(chunk_count)}",
        f"chunk_seconds: {json.dumps(chunk_seconds_used)}",
        f"resumed_from_checkpoint: {json.dumps(resumed_from_checkpoint)}",
        f"transcript_filter_reason: {json.dumps(transcript_filter_reason)}",
        f"sponsor_filter_applied: {json.dumps(sponsor_filter_applied)}",
        f"sponsor_filter_mode: {json.dumps(sponsor_filter_mode)}",
        f"sponsor_segments_filtered: {json.dumps(sponsor_segments_filtered)}",
        "---", "",
        f"# {pack['title']}: {title or external_id}", "",
        f"## {pack['caption']}", "", description or "_No description provided._", "",
        f"## {pack['transcript']}", "", text or "_No speech detected._", "",
    ]
    if sponsor_segments_removed:
        lines.extend([
            f"## {pack['filtered_sponsor_segments']}",
            "",
        ])
        for index, segment in enumerate(sponsor_segments_removed, start=1):
            lines.extend([
                f"### {index}",
                "",
                segment,
                "",
            ])
    return "\n".join(lines)


def render_instagram_post_markdown(
    *,
    metadata: dict[str, Any],
    creator: str,
    external_id: str,
    media_type: str,
    item_class: str,
    artifact_stem: str,
    canonical_source: str,
    published_at: str,
    work: Path,
) -> str:
    pack = locale_pack()
    images = _instagram_media_assets(metadata, work)
    if not images:
        raise RuntimeError("Instagram post OCR rendering requires at least one image asset.")
    ocr_payloads: list[dict[str, Any]] = []
    combined_lines: list[str] = []
    for index, image in enumerate(images, start=1):
        try:
            ocr = perform_ocr(image, config=load_config())
        except Exception as exc:
            extra = ocr_install_extra()
            raise RuntimeError(
                f"Instagram OCR failed for {image.name}: {exc}. "
                f"Install support with: python -m pip install 'media2md[{extra}]'"
            ) from exc
        text = str(ocr.get("text") or "").strip()
        if text:
            combined_lines.append(text)
        ocr_payloads.append({"index": index, "image": image, "ocr": ocr})
    engine = str(ocr_payloads[0]["ocr"].get("engine") or "unknown")
    lines = [
        "---",
        "platform: instagram",
        f"creator: {json.dumps(creator, ensure_ascii=False)}",
        f"media_id: {json.dumps(external_id)}",
        f"media_type: {json.dumps(media_type)}",
        f"processing_class: {json.dumps(item_class)}",
        f"artifact_stem: {json.dumps(artifact_stem)}",
        f"source_url: {json.dumps(canonical_source)}",
        f"published_at: {json.dumps(published_at or '')}",
        f"processed_at: {json.dumps(iso_now())}",
        f"ocr_engine: {json.dumps(engine)}",
        f"image_count: {json.dumps(len(images))}",
        "---",
        "",
        f"# Instagram Post: {external_id}",
        "",
        f"## {pack['caption']}",
        "",
        str(metadata.get("description") or "").strip() or "_No description provided._",
        "",
        f"## {pack['image_ocr']}",
        "",
    ]
    for payload in ocr_payloads:
        image = payload["image"]
        index = payload["index"]
        text = str(payload["ocr"].get("text") or "").strip()
        lines.extend([
            f"### {pack['image']} {index}",
            "",
            f"Source image: `{image.name}`",
            "",
            text or pack["no_image_text"],
            "",
        ])
    lines.extend([
        f"## {pack['combined_ocr']}",
        "",
        "\n\n".join(combined_lines).strip() or pack["no_image_text"],
        "",
    ])
    return "\n".join(lines)


def _hydrate_instagram_post_metadata(canonical_source: str, creator: str | None = None) -> dict[str, Any]:
    payload = inspect(canonical_source, provider="instagram", creator=creator)
    if str(payload.get("provider") or "") != "instagram":
        raise RuntimeError("Instagram post OCR hydration returned non-Instagram metadata.")
    return payload


def summarize_instagram_assets(metadata: dict[str, Any]) -> dict[str, Any]:
    assets = [dict(item) for item in (metadata.get("assets") or []) if isinstance(item, dict)]
    image_assets = [item for item in assets if str(item.get("kind") or "") == "image"]
    video_assets = [item for item in assets if str(item.get("kind") or "") == "video"]
    return {
        "asset_count": len(assets),
        "image_count": len(image_assets),
        "video_count": len(video_assets),
        "asset_kinds": [str(item.get("kind") or "unknown") for item in assets],
    }


def _require_bilibili_api() -> tuple[Any, Any]:
    try:
        from bilibili_api.video import Video, VideoDownloadURLDataDetecter
    except ImportError as exc:
        guidance = provider_access_guidance("bilibili", error_code="missing_dependency", required_action="install_provider_extra")
        root_cause = guidance[0] if guidance else 'Run: python -m pip install -U "media2md[bilibili]"'
        raise StageError(
            "inspect",
            "Bilibili support is not installed.",
            retryable=False,
            error_code="missing_dependency",
            action_required=True,
            required_action="install_provider_extra",
            root_cause=root_cause,
        ) from exc
    return Video, VideoDownloadURLDataDetecter


def _bilibili_run(coro: Any) -> Any:
    return asyncio.run(coro)


def _bilibili_cid_from_info(info: dict[str, Any]) -> int:
    pages = info.get("pages") or []
    if not isinstance(pages, list) or not pages:
        raise RuntimeError("Bilibili metadata did not include any playable pages.")
    first = pages[0] if isinstance(pages[0], dict) else {}
    cid = first.get("cid")
    if not isinstance(cid, int) or cid <= 0:
        raise RuntimeError("Bilibili metadata did not include a valid cid.")
    return cid


def _bilibili_published_iso(info: dict[str, Any]) -> str | None:
    for key in ("pubdate", "ctime"):
        raw = info.get(key)
        try:
            stamp = int(raw)
        except (TypeError, ValueError):
            continue
        if stamp > 0:
            return datetime.fromtimestamp(stamp, tz=timezone.utc).isoformat(timespec="seconds")
    return None


def inspect_bilibili_metadata(canonical_source: str, external_id: str) -> dict[str, Any]:
    del canonical_source
    Video, _ = _require_bilibili_api()
    video = Video(bvid=external_id)
    info = _bilibili_run(video.get_info())
    cid = _bilibili_cid_from_info(info)
    subtitles: list[Any] = []
    try:
        player = _bilibili_run(video.get_player_info(cid=cid))
    except Exception as exc:
        message = str(exc).lower()
        if "sessdata" not in message and "credential" not in message:
            raise
    else:
        subtitles = ((player.get("subtitle") or {}).get("subtitles") or []) if isinstance(player, dict) else []
    owner = info.get("owner") or {}
    uploader = str(owner.get("name") or external_id)
    uploader_id = str(owner.get("mid") or "")
    return {
        "id": external_id,
        "title": str(info.get("title") or external_id),
        "description": str(info.get("desc") or ""),
        "uploader": uploader,
        "channel": uploader,
        "channel_id": uploader_id,
        "upload_date": "",
        "duration": info.get("duration"),
        "webpage_url": f"https://www.bilibili.com/video/{external_id}",
        "_media2md_metadata_source": "bilibili-api",
        "_media2md_bilibili_cid": cid,
        "_media2md_bilibili_has_subtitles": bool(subtitles),
        "_media2md_bilibili_published_at": _bilibili_published_iso(info),
    }


def _fetch_json_url(url: str) -> dict[str, Any]:
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0",
            "Referer": "https://www.bilibili.com/",
            "Accept": "application/json",
        },
    )
    with urllib.request.urlopen(request, timeout=60) as response:
        return json.loads(response.read(2_000_000).decode("utf-8", "replace"))


def _bilibili_caption_text_from_body(body: Any) -> str:
    if not isinstance(body, list):
        return ""
    lines: list[str] = []
    for item in body:
        if not isinstance(item, dict):
            continue
        text = str(item.get("content") or "").strip()
        if text and (not lines or lines[-1] != text):
            lines.append(text)
    return "\n".join(lines).strip()


def try_bilibili_captions(source_url: str, external_id: str) -> tuple[str | None, str | None]:
    del source_url
    Video, _ = _require_bilibili_api()
    video = Video(bvid=external_id)
    info = _bilibili_run(video.get_info())
    cid = _bilibili_cid_from_info(info)
    try:
        player = _bilibili_run(video.get_player_info(cid=cid))
    except Exception as exc:
        # Public Bilibili metadata often works without session state while
        # subtitle/player endpoints may require SESSDATA. Treat that as a clean
        # miss so the public-first pipeline can continue into audio fallback.
        message = str(exc).lower()
        if "sessdata" in message or "credential" in message:
            return None, None
        raise
    subtitles = ((player.get("subtitle") or {}).get("subtitles") or []) if isinstance(player, dict) else []
    for item in subtitles:
        if not isinstance(item, dict):
            continue
        subtitle_url = str(item.get("subtitle_url") or "").strip()
        if not subtitle_url:
            continue
        if subtitle_url.startswith("//"):
            subtitle_url = "https:" + subtitle_url
        elif subtitle_url.startswith("/"):
            subtitle_url = "https://www.bilibili.com" + subtitle_url
        payload = _fetch_json_url(subtitle_url)
        text = _bilibili_caption_text_from_body(payload.get("body"))
        if text:
            language = str(item.get("lan") or item.get("lan_doc") or "").strip() or None
            return text, language
    return None, None


def download_bilibili_audio(source_url: str, work: Path, external_id: str) -> tuple[Path, str, bool, list[dict[str, Any]]]:
    del source_url
    Video, VideoDownloadURLDataDetecter = _require_bilibili_api()
    video = Video(bvid=external_id)
    info = _bilibili_run(video.get_info())
    cid = _bilibili_cid_from_info(info)
    download_data = _bilibili_run(video.get_download_url(cid=cid, html5=False))
    detector = VideoDownloadURLDataDetecter(download_data)
    streams = detector.detect_best_streams()
    audio_stream_url = None
    for stream in streams:
        if hasattr(stream, "audio_quality") and getattr(stream, "url", None):
            audio_stream_url = str(stream.url)
            break
    if not audio_stream_url:
        raise RuntimeError("Bilibili did not return an audio stream URL.")
    target = work / f"{safe_artifact_stem('bilibili', external_id)}.m4a"
    request = urllib.request.Request(
        audio_stream_url,
        headers={
            "User-Agent": "Mozilla/5.0",
            "Referer": f"https://www.bilibili.com/video/{external_id}",
        },
    )
    with urllib.request.urlopen(request, timeout=300) as response, target.open("wb") as handle:
        while True:
            chunk = response.read(1024 * 1024)
            if not chunk:
                break
            handle.write(chunk)
    if not target.is_file() or target.stat().st_size <= 0:
        raise RuntimeError("Bilibili audio download completed but no audio file was created.")
    _write_audio_manifest(
        work, target, source_url=f"https://www.bilibili.com/video/{external_id}", external_id=external_id,
        strategy="bilibili-api-audio-stream", uses_auth=False,
    )
    return target, "bilibili-api-audio-stream", False, [{
        "strategy": "bilibili-api-audio-stream",
        "client": "bilibili-api",
        "uses_auth": False,
        "ok": True,
        "error": None,
    }]




def youtube_caption_settings() -> tuple[bool, list[str]]:
    youtube = load_config().get("providers", {}).get("youtube", {})
    enabled = bool(youtube.get("caption_first", True))
    raw = youtube.get("caption_languages", ["zh-Hant", "zh-Hans", "zh", "en.*"])
    if isinstance(raw, str):
        langs = [item.strip() for item in raw.split(",") if item.strip()]
    elif isinstance(raw, list):
        langs = [str(item).strip() for item in raw if str(item).strip()]
    else:
        langs = ["zh-Hant", "zh-Hans", "zh", "en.*"]
    return enabled, langs


def provider_caption_first_enabled(provider: str) -> bool:
    settings = provider_transcription_settings(provider)
    return bool(settings.get("caption_first", True))


def parse_vtt_text(raw: str) -> str:
    entries: list[str] = []
    buffer: list[str] = []

    def flush() -> None:
        if not buffer:
            return
        text = " ".join(buffer)
        text = re.sub(r"<[^>]+>", "", text)
        text = text.replace("&nbsp;", " ")
        text = re.sub(r"\s+", " ", text).strip()
        buffer.clear()
        if text and (not entries or entries[-1] != text):
            entries.append(text)

    for line in raw.splitlines():
        value = line.strip()
        if not value or value.startswith(("WEBVTT", "Kind:", "Language:", "NOTE")):
            flush()
            continue
        if "-->" in value or value.isdigit():
            flush()
            continue
        buffer.append(value)
    flush()
    return "\n".join(entries).strip()


def try_youtube_captions(source_url: str, work: Path, external_id: str, ytdlp_args: list[str]) -> tuple[str | None, str | None]:
    enabled, languages = youtube_caption_settings()
    if not enabled:
        return None, None
    artifact_stem = safe_artifact_stem("youtube", external_id)
    template = str(work / f"{artifact_stem}.%(language)s.%(ext)s")

    def attempt(extra_auth: list[str]) -> None:
        command_line = [
            command("yt-dlp"), *ytdlp_args, *extra_auth, "--skip-download",
            "--write-subs", "--write-auto-subs", "--sub-format", "vtt",
            "--sub-langs", ",".join(languages), "--no-playlist", "--no-progress",
            "-o", template, source_url,
        ]
        try:
            run(command_line, timeout=600)
        except KeyboardInterrupt:
            raise
        except Exception:
            pass

    def inspect_candidates() -> tuple[str | None, str | None]:
        candidates = sorted(work.glob(f"{artifact_stem}.*.vtt"))
        for candidate in candidates:
            text = parse_vtt_text(candidate.read_text(encoding="utf-8", errors="replace"))
            if text:
                language_match = re.match(rf"{re.escape(artifact_stem)}\.(.+)\.vtt$", candidate.name)
                return text, (language_match.group(1) if language_match else None)
        return None, None

    # Public-first policy: do not touch browser cookies during caption probing.
    # Strict session verification occurs only if all anonymous audio strategies
    # fail and an authenticated fallback is actually needed.
    attempt([])
    return inspect_candidates()


def _remove_non_caption_files(work: Path) -> None:
    for path in work.iterdir() if work.exists() else []:
        if path.is_file() and path.suffix.lower() != ".vtt":
            path.unlink(missing_ok=True)
        elif path.is_dir() and path.name not in {"captions"}:
            shutil.rmtree(path, ignore_errors=True)


def _audio_manifest_path(work: Path) -> Path:
    return work / "audio-manifest.json"


def _audio_candidates(work: Path) -> list[Path]:
    ignored = {".vtt", ".part", ".ytdl", ".json", ".tmp"}
    return [
        path for path in work.iterdir() if path.is_file() and path.stat().st_size > 0
        and path.suffix.lower() not in ignored
    ] if work.exists() else []


def _write_audio_manifest(
    work: Path, media: Path, *, source_url: str, external_id: str,
    strategy: str, uses_auth: bool,
) -> None:
    payload = {
        "schema_version": 1,
        "source_url": source_url,
        "external_id": external_id,
        "file": media.name,
        "size": media.stat().st_size,
        "sha256": sha256(media),
        "strategy": strategy,
        "uses_auth": uses_auth,
        "completed_at": iso_now(),
    }
    path = _audio_manifest_path(work)
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.replace(tmp, path)


def find_cached_audio(work: Path, source_url: str, external_id: str) -> tuple[Path, dict[str, Any]] | None:
    path = _audio_manifest_path(work)
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return None
    if payload.get("source_url") != source_url or payload.get("external_id") != external_id:
        return None
    media = work / str(payload.get("file") or "")
    if not media.is_file() or media.stat().st_size <= 0:
        return None
    if int(payload.get("size") or -1) != media.stat().st_size:
        return None
    expected = str(payload.get("sha256") or "")
    if expected and sha256(media) != expected:
        return None
    return media, payload


def _auth_preflight(external_id: str) -> dict[str, Any]:
    payload = verify_youtube_session(external_id, persist=True)
    if payload.get("authenticated"):
        return payload
    state = str(payload.get("auth_state") or "unknown")
    expired_states = {"cookie_expired", "server_rejected", "cookie_missing"}
    code = "youtube_session_expired" if state in expired_states else "youtube_auth_unverified"
    action = payload.get("required_action") or (
        "reauthenticate_youtube_in_selected_profile" if state in expired_states
        else "verify_youtube_session_before_authenticated_download"
    )
    raise StageError(
        "download",
        f"Authenticated YouTube fallback was blocked by auth preflight: auth_state={state}",
        retryable=False,
        error_code=code,
        action_required=True,
        required_action=str(action),
        root_cause=str(payload.get("error") or f"YouTube auth state is {state}"),
    )


def download_youtube_audio(source_url: str, work: Path, external_id: str) -> tuple[Path, str, bool, list[dict[str, Any]]]:
    """Download YouTube audio using a public-first, browser-safe strategy cascade."""
    settings = youtube_audio_settings()
    strategies = youtube_download_strategies(auth_args("youtube"))
    attempts: list[dict[str, Any]] = []
    if not strategies:
        guidance = provider_access_guidance("youtube", required_action="configure_youtube_audio_strategies")
        raise StageError(
            "download", "No YouTube audio download strategies are configured.",
            retryable=False, error_code="youtube_no_download_strategy",
            action_required=True, required_action="configure_youtube_audio_strategies",
            root_cause=" | ".join(guidance) if guidance else None,
        )
    auth_checked = False
    artifact_stem = safe_artifact_stem("youtube", external_id)
    for strategy in strategies:
        if strategy["uses_auth"] and not auth_checked:
            try:
                auth_payload = _auth_preflight(external_id)
                attempts.append({
                    "strategy": "authenticated_preflight", "client": "session",
                    "uses_auth": True, "ok": True, "auth_state": auth_payload.get("auth_state"), "error": None,
                })
            except StageError as exc:
                attempts.append({
                    "strategy": "authenticated_preflight", "client": "session",
                    "uses_auth": True, "ok": False, "auth_state": None, "error": str(exc),
                })
                raise
            auth_checked = True
        _remove_non_caption_files(work)
        template = str(work / f"{artifact_stem}.%(ext)s")
        cmd = [
            command("yt-dlp"), *strategy["args"], *strategy["auth_args"],
            "--no-playlist", "--no-progress", "--retries", "3",
            "--fragment-retries", "3", "--socket-timeout", "90",
            "-f", str(strategy["format"]), "-x", "--audio-format", str(settings["audio_format"]),
            "-o", template, source_url,
        ]
        try:
            run(cmd, timeout=1800)
            files = _audio_candidates(work)
            if not files:
                raise RuntimeError("yt-dlp completed but no audio file was created.")
            media = max(files, key=lambda path: path.stat().st_size)
            _write_audio_manifest(
                work, media, source_url=source_url, external_id=external_id,
                strategy=str(strategy["name"]), uses_auth=bool(strategy["uses_auth"]),
            )
            attempts.append({
                "strategy": strategy["name"], "client": strategy["client"],
                "uses_auth": bool(strategy["uses_auth"]), "ok": True, "error": None,
            })
            return media, str(strategy["name"]), bool(strategy["uses_auth"]), attempts
        except KeyboardInterrupt:
            raise
        except Exception as exc:
            attempts.append({
                "strategy": strategy["name"], "client": strategy["client"],
                "uses_auth": bool(strategy["uses_auth"]), "ok": False,
                "error": str(exc)[-1500:],
            })
    summary = "; ".join(
        f"{item['strategy']}={item['error']}" for item in attempts if not item["ok"]
    )
    classification = classify_access_error("youtube", summary)
    if classification["error_code"] == "youtube_po_token_required":
        classification["required_action"] = "configure_non_browser_po_token_or_try_another_video"
    guidance = provider_access_guidance(
        "youtube",
        error_code=str(classification.get("error_code") or ""),
        required_action=str(classification.get("required_action") or ""),
    )
    raise StageError(
        "download", f"All YouTube audio strategies failed: {summary}",
        retryable=bool(classification["retryable"]),
        error_code=str(classification["error_code"]),
        action_required=bool(classification["action_required"]),
        required_action=classification.get("required_action"),
        root_cause=" | ".join(guidance) if guidance else (summary[-1000:] if summary else "all YouTube audio strategies failed"),
    )


def _duration_seconds(media: Path, hinted: Any = None) -> float:
    try:
        value = float(hinted or 0)
        if value > 0:
            return value
    except (TypeError, ValueError):
        pass
    result = run([
        command("ffprobe"), "-v", "error", "-show_entries", "format=duration",
        "-of", "default=nw=1:nk=1", str(media),
    ], timeout=120)
    try:
        return float(result.stdout.strip())
    except ValueError as exc:
        raise RuntimeError(f"Could not determine audio duration: {result.stdout!r}") from exc


def _format_clock(seconds: int | float) -> str:
    total = max(0, int(seconds))
    hours, rem = divmod(total, 3600)
    minutes, secs = divmod(rem, 60)
    return f"{hours:02d}:{minutes:02d}:{secs:02d}"


def _chunk_manifest(media: Path, chunk_seconds: int, duration: float) -> dict[str, Any]:
    return {
        "source": str(media),
        "source_size": media.stat().st_size,
        "source_mtime_ns": media.stat().st_mtime_ns,
        "chunk_seconds": chunk_seconds,
        "duration_seconds": duration,
    }


def _split_audio(media: Path, chunks_dir: Path, chunk_seconds: int, duration: float) -> tuple[list[Path], bool]:
    manifest_path = chunks_dir / "chunks-manifest.json"
    expected = _chunk_manifest(media, chunk_seconds, duration)
    try:
        saved = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        saved = None
    existing = sorted(path for path in chunks_dir.glob("chunk_*.mp3") if path.is_file() and path.stat().st_size > 0)
    if saved == expected and existing:
        return existing, True
    shutil.rmtree(chunks_dir, ignore_errors=True)
    chunks_dir.mkdir(parents=True, exist_ok=True)
    target = chunks_dir / "chunk_%03d.mp3"
    try:
        run([
            command("ffmpeg"), "-v", "error", "-i", str(media),
            "-f", "segment", "-segment_time", str(chunk_seconds),
            "-reset_timestamps", "1", "-c", "copy", str(target),
        ], timeout=1800)
    except Exception:
        shutil.rmtree(chunks_dir, ignore_errors=True)
        chunks_dir.mkdir(parents=True, exist_ok=True)
        run([
            command("ffmpeg"), "-v", "error", "-i", str(media),
            "-f", "segment", "-segment_time", str(chunk_seconds),
            "-reset_timestamps", "1", "-ac", "1", "-ar", "16000",
            "-c:a", "libmp3lame", "-b:a", "64k", str(target),
        ], timeout=3600)
    chunks = sorted(path for path in chunks_dir.glob("chunk_*.mp3") if path.stat().st_size > 0)
    if not chunks:
        raise RuntimeError("FFmpeg did not create any audio chunks.")
    manifest_path.write_text(json.dumps(expected, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return chunks, False


def _extract_audio_track(media: Path, work: Path, artifact_stem: str) -> Path:
    target = work / f"{artifact_stem}.m4a"
    try:
        run([
            command("ffmpeg"), "-v", "error", "-y", "-i", str(media),
            "-vn", "-acodec", "aac", str(target),
        ], timeout=1800)
    except Exception as exc:
        text = "\n".join(
            part for part in (
                getattr(exc, "stderr", None),
                getattr(exc, "stdout", None),
                getattr(exc, "root_cause", None),
                str(exc),
            ) if part
        ).lower()
        if (
            "does not contain any stream" in text
            or "does not contain an audio stream" in text
            or "output file does not contain any stream" in text
            or "stream map" in text
        ):
            raise RuntimeError("Media file does not contain an audio stream.") from exc
        raise
    if not target.is_file() or target.stat().st_size <= 0:
        raise RuntimeError("FFmpeg did not create an extracted audio track.")
    return target


def _whisper_command(media: Path, output_dir: Path, output_name: str, model: str) -> list[str]:
    # Use the --option=value form so argparse can never reinterpret a leading
    # dash in a platform ID as a new option. output_name is safe regardless.
    return [
        command("mlx_whisper"), str(media), "--model", model,
        "--output-dir", str(output_dir), f"--output-name={output_name}",
        "--output-format", "txt", "--task", "transcribe",
    ]


def transcribe_audio(
    media: Path,
    transcript_dir: Path,
    external_id: str,
    hinted_duration: Any = None,
    *,
    provider: str = "youtube",
) -> dict[str, Any]:
    settings = provider_transcription_settings(provider)
    duration = _duration_seconds(media, hinted_duration)
    threshold = int(settings["long_video_threshold_seconds"])
    chunk_seconds = int(settings["chunk_seconds"])
    artifact_stem = safe_artifact_stem(provider, external_id)
    transcript_dir.mkdir(parents=True, exist_ok=True)
    if duration < threshold:
        transcript_path = transcript_dir / f"{artifact_stem}.txt"
        resumed = transcript_path.is_file() and transcript_path.stat().st_size > 0
        _write_transcription_progress(
            transcript_dir,
            stage="single",
            external_id=external_id,
            model=MODEL,
            chunk_count=1,
            chunk_seconds=None,
            current_chunk_index=1,
            current_chunk_name=media.name,
            duration_seconds=duration,
            reused_chunk_transcripts=1 if resumed else 0,
        )
        if not resumed:
            run(_whisper_command(media, transcript_dir, artifact_stem, MODEL), timeout=7200)
        if not transcript_path.is_file():
            raise RuntimeError("Whisper did not create the expected transcript.")
        _clear_transcription_progress(transcript_dir)
        return {
            "text": transcript_path.read_text(encoding="utf-8").strip(),
            "source": "local_whisper", "model": MODEL, "duration_seconds": duration,
            "chunk_count": 1, "chunk_seconds": None,
            "resumed_from_checkpoint": resumed,
        }

    chunks_dir = transcript_dir / "audio_chunks"
    outputs_dir = transcript_dir / "chunk_transcripts"
    split_result = _split_audio(media, chunks_dir, chunk_seconds, duration)
    if isinstance(split_result, tuple) and len(split_result) == 2:
        chunks, chunks_reused = split_result
    else:  # compatibility with injected/test splitters from older releases
        chunks, chunks_reused = split_result, False
    outputs_dir.mkdir(parents=True, exist_ok=True)
    model = str(settings["chunk_model"])
    merged: list[str] = []
    reused_count = 0
    _write_transcription_progress(
        transcript_dir,
        stage="chunked",
        external_id=external_id,
        model=model,
        chunk_count=len(chunks),
        chunk_seconds=chunk_seconds,
        current_chunk_index=None,
        current_chunk_name=None,
        duration_seconds=duration,
        reused_chunk_transcripts=0,
    )
    for index, chunk in enumerate(chunks):
        name = safe_artifact_stem("chunk", chunk.stem)
        transcript_path = outputs_dir / f"{name}.txt"
        _write_transcription_progress(
            transcript_dir,
            stage="chunked",
            external_id=external_id,
            model=model,
            chunk_count=len(chunks),
            chunk_seconds=chunk_seconds,
            current_chunk_index=index + 1,
            current_chunk_name=chunk.name,
            duration_seconds=duration,
            reused_chunk_transcripts=reused_count,
        )
        if transcript_path.is_file() and transcript_path.stat().st_size > 0:
            reused_count += 1
        else:
            run(_whisper_command(chunk, outputs_dir, name, model), timeout=7200)
        if not transcript_path.is_file():
            raise RuntimeError(f"Whisper did not create transcript for {chunk.name}.")
        text = transcript_path.read_text(encoding="utf-8").strip()
        start = index * chunk_seconds
        end = min(int(duration), start + chunk_seconds)
        merged.append(f"### {_format_clock(start)}–{_format_clock(end)}\n\n{text or '_No speech detected._'}")
    _clear_transcription_progress(transcript_dir)
    return {
        "text": "\n\n".join(merged).strip(),
        "source": "local_whisper_chunked", "model": model,
        "duration_seconds": duration, "chunk_count": len(chunks),
        "chunk_seconds": chunk_seconds,
        "resumed_from_checkpoint": bool(chunks_reused or reused_count),
        "reused_chunk_transcripts": reused_count,
    }


def _cleanup_partial_downloads(work: Path) -> None:
    manifest = _audio_manifest_path(work)
    preserved: set[Path] = set()
    try:
        payload = json.loads(manifest.read_text(encoding="utf-8"))
        media = work / str(payload.get("file") or "")
        if media.is_file() and media.stat().st_size > 0:
            preserved.update({manifest.resolve(), media.resolve()})
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        pass
    for path in list(work.rglob("*")) if work.exists() else []:
        if not path.is_file():
            continue
        if path.resolve() in preserved or path.suffix.lower() == ".vtt":
            continue
        # Files without a completed manifest are partial/untrusted and must not
        # be mistaken for resumable audio on the next run.
        path.unlink(missing_ok=True)


def process_row(conn: sqlite3.Connection, row: sqlite3.Row) -> dict[str, Any]:
    provider = str(row["provider"])
    external_id = str(row["external_id"])
    media_type = (str(row["media_type"]) if "media_type" in row.keys() and row["media_type"] else infer_media_type(provider, row["source_url"]))
    threshold = int(provider_transcription_settings(provider)["long_video_threshold_seconds"])
    item_class = processing_class(media_type, row["duration_seconds"], long_threshold_seconds=threshold)
    artifact_stem = safe_artifact_stem(provider, external_id)
    raw_creator = str(row["creator"] if "creator" in row.keys() else row["handle"])
    if provider == "tiktok":
        creator = _human_tiktok_handle(raw_creator)
        if not creator:
            raise StageError("validation", f"TikTok creator handle is opaque: {raw_creator}", retryable=False)
    else:
        creator = safe(raw_creator)
    work = DOWNLOADS / provider / creator / artifact_stem
    transcript_dir = TRANSCRIPTS / provider / creator / artifact_stem
    work.mkdir(parents=True, exist_ok=True)
    transcript_dir.mkdir(parents=True, exist_ok=True)
    conn.execute("UPDATE media SET status='downloading', updated_at=? WHERE id=?", (iso_now(), row["id"]))
    conn.commit()
    template = str(work / f"{artifact_stem}.%(ext)s")
    canonical_source = canonical_media_source(provider, external_id, str(row["source_url"]), creator)
    ytdlp_args = youtube_access_args(allow_browser_launch=False) if provider == "youtube" else impersonation_args("tiktok") if provider == "tiktok" else []
    transcription_source = "local_whisper"
    transcription_model: str | None = MODEL
    caption_language: str | None = None
    audio_download_strategy: str | None = None
    audio_used_auth: bool | None = None
    audio_attempts: list[dict[str, Any]] = []
    chunk_count = 0
    chunk_seconds_used: int | None = None
    processed_duration = float(row["duration_seconds"] or 0)
    resumed_from_checkpoint = False
    caption_probe_result: str | None = "not_applicable"
    transcript_filter_reason: str | None = "not_applicable"
    sponsor_filter_applied = False
    sponsor_filter_mode: str | None = None
    sponsor_segments_removed: list[str] = []
    succeeded = False
    no_audio_stream = False
    result_summary: dict[str, Any] = {}
    try:
        text: str | None = None
        post_ocr_mode = provider == "instagram" and media_type in {"instagram_post", "instagram_carousel"}
        if provider == "youtube":
            text, caption_language = try_youtube_captions(canonical_source, work, external_id, ytdlp_args)
            if text:
                caption_probe_result = "hit"
                transcription_source = "youtube_captions"
                transcription_model = None
                chunk_count = 0
                conn.execute("UPDATE media SET status='transcribing', updated_at=? WHERE id=?", (iso_now(), row["id"]))
                conn.commit()
            else:
                caption_probe_result = "disabled" if not youtube_caption_settings()[0] else "miss"
        elif provider == "bilibili" and provider_caption_first_enabled("bilibili"):
            text, caption_language = try_bilibili_captions(canonical_source, external_id)
            if text:
                caption_probe_result = "hit"
                transcription_source = "bilibili_captions"
                transcription_model = None
                chunk_count = 0
                conn.execute("UPDATE media SET status='transcribing', updated_at=? WHERE id=?", (iso_now(), row["id"]))
                conn.commit()
            else:
                caption_probe_result = "miss"
        elif provider == "bilibili":
            caption_probe_result = "disabled"

        if post_ocr_mode:
            text = ""
            transcription_source = "instagram_post_ocr"
            transcription_model = None
            chunk_count = 0
            chunk_seconds_used = None
            processed_duration = 0.0
        elif not text:
            cached = find_cached_audio(work, canonical_source, external_id)
            if cached:
                media, manifest = cached
                audio_download_strategy = "cached_audio"
                audio_used_auth = bool(manifest.get("uses_auth"))
                resumed_from_checkpoint = True
                audio_attempts.append({
                    "strategy": "cached_audio", "client": "local_checkpoint",
                    "uses_auth": audio_used_auth, "ok": True, "error": None,
                })
            elif provider == "youtube":
                if caption_probe_result != "disabled":
                    caption_probe_result = "fallback_to_audio"
                media, audio_download_strategy, audio_used_auth, audio_attempts = download_youtube_audio(
                    canonical_source, work, external_id
                )
            elif provider == "bilibili":
                caption_probe_result = "fallback_to_audio"
                try:
                    media, audio_download_strategy, audio_used_auth, audio_attempts = download_bilibili_audio(
                        canonical_source, work, external_id
                    )
                except Exception as exc:
                    raise RuntimeError(_bilibili_access_hint(str(exc))) from exc
            else:
                try:
                    if provider == "tiktok":
                        media, audio_download_strategy, audio_used_auth, audio_attempts = download_tiktok_audio(
                            canonical_source, work, external_id, creator, template
                        )
                    else:
                        provider_auth_args = auth_args(provider)
                        if provider == "instagram":
                            run([
                                command("yt-dlp"), *ytdlp_args, *provider_auth_args, "--no-playlist", "--no-progress",
                                "--retries", "5", "--socket-timeout", "120", "-f", "bv*+ba/b",
                                "-o", template, canonical_source
                            ], timeout=1800)
                        else:
                            run([
                                command("yt-dlp"), *ytdlp_args, *provider_auth_args, "--no-playlist", "--no-progress",
                                "--retries", "5", "--socket-timeout", "120", "-f", "ba/b", "-x",
                                "--audio-format", "m4a", "-o", template, canonical_source
                            ], timeout=1800)
                        files = _audio_candidates(work)
                        if not files:
                            raise RuntimeError("yt-dlp completed but no media file was created.")
                        media = max(files, key=lambda path: path.stat().st_size)
                        if provider == "instagram":
                            try:
                                media = _extract_audio_track(media, work, artifact_stem)
                            except RuntimeError as exc:
                                if "does not contain an audio stream" in str(exc).lower():
                                    no_audio_stream = True
                                    media = media
                                else:
                                    raise
                        audio_download_strategy = "yt-dlp-default"
                        audio_used_auth = bool(provider_auth_args)
                        audio_attempts.append({
                            "strategy": "yt-dlp-default", "client": "default",
                            "uses_auth": audio_used_auth, "ok": True, "error": None,
                        })
                        _write_audio_manifest(
                            work, media, source_url=canonical_source, external_id=external_id,
                            strategy=str(audio_download_strategy), uses_auth=bool(audio_used_auth),
                        )
                except KeyboardInterrupt:
                    raise
                except Exception as exc:
                    classification = classify_access_error(provider, str(exc))
                    raise StageError(
                        "download", str(exc), retryable=bool(classification["retryable"]),
                        error_code=str(classification["error_code"]), action_required=bool(classification["action_required"]),
                        required_action=classification.get("required_action"),
                        root_cause=str(getattr(exc, "root_cause", str(exc))),
                        log_path=str(getattr(exc, "log_path", "")) or None,
                    ) from exc

            conn.execute("UPDATE media SET status='transcribing', updated_at=? WHERE id=?", (iso_now(), row["id"]))
            conn.commit()
            if no_audio_stream:
                text = ""
                transcription_source = "no_audio_stream"
                transcription_model = None
                chunk_count = 0
                chunk_seconds_used = None
            else:
                try:
                    result = transcribe_audio(
                        media,
                        transcript_dir,
                        external_id,
                        row["duration_seconds"],
                        provider=provider,
                    )
                    text = str(result["text"])
                    transcription_source = str(result["source"])
                    transcription_model = str(result["model"])
                    processed_duration = float(result["duration_seconds"])
                    chunk_count = int(result["chunk_count"])
                    chunk_seconds_used = result["chunk_seconds"]
                    resumed_from_checkpoint = bool(resumed_from_checkpoint or result.get("resumed_from_checkpoint"))
                except KeyboardInterrupt:
                    _clear_transcription_progress(transcript_dir)
                    raise
                except Exception as exc:
                    _clear_transcription_progress(transcript_dir)
                    classification = classify_transcription_exception(exc)
                    raise StageError(
                        "transcribe", str(exc),
                        retryable=bool(classification["retryable"]),
                        error_code=str(classification["error_code"]),
                        action_required=bool(classification["action_required"]),
                        required_action=classification.get("required_action"),
                        root_cause=str(classification.get("root_cause") or str(exc)),
                        log_path=classification.get("log_path"),
                    ) from exc
        if provider == "youtube" and text:
            sponsor_filter = filter_youtube_sponsor_segments(str(text), mode=youtube_sponsor_filter_mode())
            text = str(sponsor_filter["text"])
            sponsor_filter_applied = bool(sponsor_filter["filtered"])
            sponsor_filter_mode = str(sponsor_filter["mode"])
            sponsor_segments_removed = list(sponsor_filter["removed_segments"])
            transcript_filter_reason = str(sponsor_filter["reason"])

        item_class = processing_class(media_type, processed_duration, long_threshold_seconds=threshold)
        try:
            final = MARKDOWN / provider / creator / output_bucket(media_type) / f"{artifact_stem}.md"
            final.parent.mkdir(parents=True, exist_ok=True)
            if post_ocr_mode:
                metadata_for_render = _hydrate_instagram_post_metadata(canonical_source, creator=creator)
                metadata_for_render.update(
                    {
                        "provider": provider,
                        "external_id": external_id,
                        "source_url": canonical_source,
                        "description": str(row["description"] or metadata_for_render.get("description") or ""),
                    }
                )
                result_summary = summarize_instagram_assets(metadata_for_render)
                content = render_instagram_post_markdown(
                    metadata=metadata_for_render,
                    creator=creator,
                    external_id=external_id,
                    media_type=media_type,
                    item_class=item_class,
                    artifact_stem=artifact_stem,
                    canonical_source=canonical_source,
                    published_at=str(row["published_at"] or ""),
                    work=work,
                )
            else:
                content = render_standard_markdown(
                    provider=provider,
                    creator=creator,
                    external_id=external_id,
                    media_type=media_type,
                    item_class=item_class,
                    artifact_stem=artifact_stem,
                    canonical_source=canonical_source,
                    published_at=str(row["published_at"] or ""),
                    transcription_source=transcription_source,
                    caption_language=caption_language,
                    transcription_model=transcription_model,
                    processed_duration=processed_duration,
                    audio_download_strategy=audio_download_strategy,
                    audio_used_auth=audio_used_auth,
                    audio_attempts=audio_attempts,
                    chunk_count=chunk_count,
                    chunk_seconds_used=chunk_seconds_used,
                    resumed_from_checkpoint=resumed_from_checkpoint,
                    caption_probe_result=caption_probe_result,
                    transcript_filter_reason=transcript_filter_reason,
                    sponsor_filter_applied=sponsor_filter_applied,
                    sponsor_filter_mode=sponsor_filter_mode,
                    sponsor_segments_filtered=len(sponsor_segments_removed),
                    sponsor_segments_removed=sponsor_segments_removed,
                    title=str(row["title"] or external_id),
                    description=str(row["description"] or ""),
                    text=str(text or ""),
                )
            tmp = final.with_suffix(".md.tmp")
            tmp.write_text(content, encoding="utf-8")
            if tmp.stat().st_size < 100:
                raise RuntimeError("Rendered Markdown failed validation.")
            os.replace(tmp, final)
            digest = sha256(final)
        except Exception as exc:
            raise StageError("render", str(exc), retryable=False, error_code="render_error", action_required=True, required_action="inspect_render_error") from exc

        columns = {info[1] for info in conn.execute("PRAGMA table_info(media)").fetchall()}
        if {"media_type", "processing_class"}.issubset(columns):
            conn.execute(
                "UPDATE media SET creator=?,source_url=?,duration_seconds=?,media_type=?,processing_class=?,status='completed', "
                "markdown_path=?, markdown_sha256=?, completed_at=?, updated_at=?, last_error=NULL WHERE id=?",
                (creator, canonical_source, processed_duration, media_type, item_class, str(final.relative_to(ROOT)), digest, iso_now(), iso_now(), row["id"]),
            )
        else:
            conn.execute(
                "UPDATE media SET creator=?,source_url=?,duration_seconds=?,status='completed', "
                "markdown_path=?, markdown_sha256=?, completed_at=?, updated_at=?, last_error=NULL WHERE id=?",
                (creator, canonical_source, processed_duration, str(final.relative_to(ROOT)), digest, iso_now(), iso_now(), row["id"]),
            )
        conn.commit()
        updated_row = conn.execute("SELECT * FROM media WHERE id=?", (row["id"],)).fetchone()
        if updated_row:
            sync_registry(provider, external_id, updated_row)
        succeeded = True
        return {
            "final_path": final,
            "media_type": media_type,
            "processing_class": item_class,
            "result_summary": result_summary,
        }
    finally:
        if succeeded:
            cleanup_workspace_paths(work, transcript_dir)
        else:
            _cleanup_partial_downloads(work)

def add(url: str, process_now: bool, output: str, provider: str | None = None, creator: str | None = None) -> int:
    metadata = inspect(url,provider=provider,creator=creator)
    ensure_registry(metadata)
    conn = connect()
    now = iso_now()
    conn.execute("""
        INSERT INTO media(provider, external_id, creator, title, description, source_url, published_at, duration_seconds, media_type, processing_class, status, created_at, updated_at)
        VALUES(?,?,?,?,?,?,?,?,?,?, 'pending', ?, ?)
        ON CONFLICT(provider, external_id) DO UPDATE SET
          creator=excluded.creator, title=excluded.title, description=excluded.description,
          source_url=excluded.source_url, published_at=excluded.published_at,
          duration_seconds=excluded.duration_seconds, media_type=excluded.media_type,
          processing_class=excluded.processing_class, status='pending', last_error=NULL,
          markdown_path=NULL, markdown_sha256=NULL, completed_at=NULL,
          updated_at=excluded.updated_at
    """, (
        metadata["provider"], metadata["external_id"], metadata["creator"], metadata["title"], metadata["description"],
        metadata["source_url"], metadata["published_at"], metadata["duration_seconds"], metadata["media_type"], metadata["processing_class"], now, now,
    ))
    conn.commit()
    row = conn.execute("SELECT * FROM media WHERE provider=? AND external_id=?", (metadata["provider"], metadata["external_id"])).fetchone()
    print("MEDIA_TRACKED")
    print(f"provider={metadata['provider']}")
    print(f"media_id={metadata['external_id']}")
    print(f"creator={metadata['creator']}")
    print(f"status={row['status']}")
    emit({"event":"media_tracked", **metadata, "status":row["status"]}, output)
    if process_now and row["status"] != "completed":
        try:
            processed = process_row(conn, row)
            final = Path(processed["final_path"])
            summary = dict(processed.get("result_summary") or {})
            print("MEDIA_COMPLETED")
            print(f"markdown={final.relative_to(ROOT)}")
            print(f"result_folder={final.parent}")
            print(f"latest_markdown_path={final}")
            if "asset_count" in summary:
                print(f"asset_count={summary['asset_count']}")
            if "image_count" in summary:
                print(f"image_count={summary['image_count']}")
            emit({"event":"media_completed", **metadata, "markdown_path":str(final.relative_to(ROOT)), **summary}, output)
        except KeyboardInterrupt:
            conn.execute("UPDATE media SET status='pending', last_error='Interrupted by user; safe to resume', updated_at=? WHERE id=?", (iso_now(), row["id"]))
            conn.commit()
            print("MEDIA_INTERRUPTED", file=sys.stderr)
            return 130
        except Exception as exc:
            conn.execute("UPDATE media SET status='failed', last_error=?, updated_at=? WHERE id=?", (str(exc)[:4000], iso_now(), row["id"]))
            conn.commit()
            raise
    final_row = conn.execute("SELECT * FROM media WHERE id=?", (row["id"],)).fetchone() if row else None
    if final_row:
        sync_registry(metadata["provider"], metadata["external_id"], final_row)
    conn.close()
    return 0



def registered_metadata(provider: str, external_id: str) -> dict[str, Any]:
    if not REGISTRY_DB.is_file():
        raise RuntimeError(f"Registry database is missing: {REGISTRY_DB}")
    registry = sqlite3.connect(REGISTRY_DB)
    registry.row_factory = sqlite3.Row
    row = registry.execute(
        """SELECT m.*, c.handle, c.external_id AS creator_external_id, c.display_name
           FROM media m JOIN creators c ON c.id=m.creator_id
           WHERE m.provider=? AND m.external_id=?""",
        (provider, external_id),
    ).fetchone()
    if not row:
        registry.close()
        raise RuntimeError(f"Registered media not found: {provider}:{external_id}")
    identifiers = {
        str(item["identifier_type"]): str(item["identifier_value"])
        for item in registry.execute(
            "SELECT identifier_type,identifier_value FROM creator_identifiers WHERE creator_id=?",
            (row["creator_id"],),
        ).fetchall()
    }
    registry.close()
    canonical_source = canonical_media_source(
        provider,
        str(row["external_id"]),
        str(row["source_url"]),
        str(row["handle"]),
    )
    return {
        "provider": provider,
        "external_id": str(row["external_id"]),
        "creator": str(row["handle"]),
        "creator_external_id": str(row["creator_external_id"] or row["handle"]),
        "creator_identifiers": identifiers,
        "creator_display_name": str(row["display_name"] or row["handle"]),
        "title": str(row["title"] or row["external_id"]),
        "description": str(row["description"] or ""),
        "published_at": row["published_at"],
        "duration_seconds": row["duration_seconds"],
        "media_type": str(row["media_type"] or infer_media_type(provider, row["source_url"])),
        "processing_class": str(row["processing_class"] or processing_class(infer_media_type(provider, row["source_url"]), row["duration_seconds"])),
        "source_url": canonical_source,
    }


def _process_registered_unlocked(provider: str, external_id: str, output: str) -> int:
    metadata = registered_metadata(provider, external_id)
    conn = connect()
    now = iso_now()
    conn.execute(
        """INSERT INTO media(provider, external_id, creator, title, description, source_url, published_at, duration_seconds, media_type, processing_class, status, created_at, updated_at)
           VALUES(?,?,?,?,?,?,?,?,?,?, 'pending', ?, ?)
           ON CONFLICT(provider, external_id) DO UPDATE SET
             creator=excluded.creator, title=excluded.title, description=excluded.description,
             source_url=excluded.source_url, published_at=excluded.published_at,
             duration_seconds=excluded.duration_seconds, media_type=excluded.media_type,
             processing_class=excluded.processing_class, status='pending', last_error=NULL,
             markdown_path=NULL, markdown_sha256=NULL, completed_at=NULL,
             updated_at=excluded.updated_at""",
        (metadata["provider"], metadata["external_id"], metadata["creator"], metadata["title"], metadata["description"],
         metadata["source_url"], metadata["published_at"], metadata["duration_seconds"], metadata["media_type"], metadata["processing_class"], now, now),
    )
    conn.commit()
    row = conn.execute(
        "SELECT * FROM media WHERE provider=? AND external_id=?",
        (provider, external_id),
    ).fetchone()
    if row["status"] == "completed":
        emit({"event": "media_already_completed", **metadata}, output)
        conn.close()
        return 0
    print("REGISTERED_MEDIA_SELECTED")
    print(f"provider={provider}")
    print(f"media_id={external_id}")
    print(f"source_url={metadata['source_url']}")
    emit({"event": "registered_media_selected", **metadata}, output)
    try:
        processed = process_row(conn, row)
        final = Path(processed["final_path"])
        summary = dict(processed.get("result_summary") or {})
        print("MEDIA_COMPLETED")
        print(f"markdown={final.relative_to(ROOT)}")
        print(f"result_folder={final.parent}")
        print(f"latest_markdown_path={final}")
        if "asset_count" in summary:
            print(f"asset_count={summary['asset_count']}")
        if "image_count" in summary:
            print(f"image_count={summary['image_count']}")
        emit({"event": "media_completed", **metadata, "markdown_path": str(final.relative_to(ROOT)), **summary}, output)
    except KeyboardInterrupt:
        conn.execute(
            "UPDATE media SET status='pending', last_error='Interrupted by user; safe to resume', updated_at=? WHERE id=?",
            (iso_now(), row["id"]),
        )
        conn.commit()
        print("MEDIA_INTERRUPTED", file=sys.stderr)
        return 130
    except Exception as exc:
        conn.execute(
            "UPDATE media SET status='failed', last_error=?, updated_at=? WHERE id=?",
            (str(exc)[:4000], iso_now(), row["id"]),
        )
        conn.commit()
        raise
    final_row = conn.execute("SELECT * FROM media WHERE id=?", (row["id"],)).fetchone()
    if final_row:
        sync_registry(provider, external_id, final_row)
    conn.close()
    return 0


def process_registered(provider: str, external_id: str, output: str) -> int:
    with operation_lock(
        "media-process",
        f"{provider}-{external_id}",
        metadata={"provider": provider, "media_id": external_id},
    ):
        return _process_registered_unlocked(provider, external_id, output)

def listing(provider: str | None, status: str | None, output: str) -> int:
    conn = connect()
    clauses, params = [], []
    if provider:
        clauses.append("provider=?"); params.append(provider)
    if status:
        clauses.append("status=?"); params.append(status)
    where = " WHERE " + " AND ".join(clauses) if clauses else ""
    rows = conn.execute(f"SELECT * FROM media{where} ORDER BY published_at DESC, id DESC", params).fetchall()
    for row in rows:
        payload = dict(row)
        if output == "ndjson": emit({"event":"media", **payload}, output)
        else: print(f"{row['provider']} | {row['external_id']} | {row['creator']} | {row['status']} | {row['published_at'] or '-'}")
    if output == "ndjson": emit({"event":"media_list_completed", "count":len(rows)}, output)
    else: print(f"TOTAL={len(rows)}")
    conn.close()
    return 0


def main() -> int:
    argv = sys.argv[1:]
    sentinel = "__MEDIA2MD_YOUTUBE_ID__"
    if len(argv) >= 2 and argv[0] in {"inspect", "add"} and re.fullmatch(r"-[A-Za-z0-9_-]{10}", argv[1]):
        argv[1] = sentinel + argv[1]
    if len(argv) >= 3 and argv[0] == "process-registered" and re.fullmatch(r"-[A-Za-z0-9_-]{10}", argv[2]):
        argv[2] = sentinel + argv[2]
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)
    inspect_cmd = sub.add_parser("inspect")
    inspect_cmd.add_argument("url")
    inspect_cmd.add_argument("--provider", choices=("instagram","youtube","tiktok","bilibili"))
    inspect_cmd.add_argument("--creator")
    inspect_cmd.add_argument("--output", choices=("human","ndjson"), default="human")
    add_cmd = sub.add_parser("add")
    add_cmd.add_argument("url")
    add_cmd.add_argument("--provider", choices=("instagram","youtube","tiktok","bilibili"))
    add_cmd.add_argument("--creator")
    add_cmd.add_argument("--process-now", action="store_true")
    add_cmd.add_argument("--output", choices=("human","ndjson"), default="human")
    registered_cmd = sub.add_parser("process-registered")
    registered_cmd.add_argument("provider", choices=("youtube","tiktok","bilibili"))
    registered_cmd.add_argument("external_id")
    registered_cmd.add_argument("--output", choices=("human","ndjson"), default="human")
    list_cmd = sub.add_parser("list")
    list_cmd.add_argument("--provider", choices=("youtube","tiktok","bilibili"))
    list_cmd.add_argument("--status")
    list_cmd.add_argument("--output", choices=("human","ndjson"), default="human")
    args = parser.parse_args(argv)
    if hasattr(args, "url") and isinstance(args.url, str) and args.url.startswith(sentinel):
        args.url = args.url[len(sentinel):]
    if hasattr(args, "external_id") and isinstance(args.external_id, str) and args.external_id.startswith(sentinel):
        args.external_id = args.external_id[len(sentinel):]
    if args.command == "inspect":
        data = inspect(args.url,provider=args.provider,creator=args.creator)
        if args.output == "ndjson": emit({"event":"media_inspected", **data}, args.output)
        else:
            print("MEDIA_INSPECTED")
            for key, value in data.items(): print(f"{key}={value}")
        return 0
    if args.command == "add": return add(args.url,args.process_now,args.output,args.provider,args.creator)
    if args.command == "process-registered": return process_registered(args.provider,args.external_id,args.output)
    return listing(args.provider, args.status, args.output)


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        print("MEDIA_INTERRUPTED", file=sys.stderr)
        raise SystemExit(130)
    except (RuntimeError, OSError, sqlite3.Error, subprocess.SubprocessError, json.JSONDecodeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise SystemExit(1)
