#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
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

from media2md_paths import command_path
from media2md_runtime import run_logged, safe_artifact_stem

from media2md_auth_shared import refresh_if_configured

ROOT = Path(__file__).resolve().parents[1]
DB_PATH = ROOT / "data" / "state.db"
DOWNLOAD_ROOT = ROOT / "workspace" / "downloads"
TRANSCRIPT_ROOT = ROOT / "workspace" / "transcripts"
TEMP_ROOT = ROOT / "workspace" / "temp"
MARKDOWN_ROOT = ROOT / "markdown"
RUN_LOG_DIR = ROOT / "logs" / "runs"
CONFIG_PATH = ROOT / "config" / "social2md.json"
COOKIE_FILE = ROOT / "data" / "secrets" / "instagram-cookies.txt"
INSTALOADER_HELPER = ROOT / "scripts" / "instagram_instaloader.py"
LOCK_NAME = "instagram_video_worker"
LOCK_TTL_HOURS = 12
DEFAULT_MODEL = "mlx-community/whisper-large-v3-turbo"
MAX_ATTEMPTS = 5
RETRY_DELAYS_MINUTES = (10, 60, 360, 1440)


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def iso_now() -> str:
    return utc_now().isoformat(timespec="seconds")


def connect() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH, timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA synchronous = NORMAL")
    return conn


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def acquire_lock(conn: sqlite3.Connection, owner: str) -> None:
    now = utc_now()
    expires = now + timedelta(hours=LOCK_TTL_HOURS)
    conn.execute("BEGIN IMMEDIATE")
    row = conn.execute(
        "SELECT owner, acquired_at, expires_at FROM pipeline_lock WHERE lock_name = ?",
        (LOCK_NAME,),
    ).fetchone()
    if row:
        try:
            expiry = datetime.fromisoformat(row["expires_at"])
        except ValueError:
            expiry = now - timedelta(seconds=1)
        if expiry > now:
            conn.rollback()
            raise RuntimeError(
                "Worker is already running. "
                f"owner={row['owner']} acquired_at={row['acquired_at']} "
                f"expires_at={row['expires_at']}"
            )
    conn.execute(
        """
        INSERT INTO pipeline_lock(lock_name, owner, acquired_at, expires_at)
        VALUES (?, ?, ?, ?)
        ON CONFLICT(lock_name) DO UPDATE SET
          owner = excluded.owner,
          acquired_at = excluded.acquired_at,
          expires_at = excluded.expires_at
        """,
        (LOCK_NAME, owner, now.isoformat(timespec="seconds"), expires.isoformat(timespec="seconds")),
    )
    conn.commit()


def release_lock(conn: sqlite3.Connection, owner: str) -> None:
    conn.execute(
        "DELETE FROM pipeline_lock WHERE lock_name = ? AND owner = ?",
        (LOCK_NAME, owner),
    )
    conn.commit()


def create_run(conn: sqlite3.Connection, run_id: str) -> None:
    conn.execute(
        "INSERT INTO runs(id, started_at, status) VALUES (?, ?, 'running')",
        (run_id, iso_now()),
    )
    conn.commit()


def finish_run(
    conn: sqlite3.Connection,
    run_id: str,
    status: str,
    completed: int,
    failed: int,
    errors: list[str],
) -> None:
    conn.execute(
        """
        UPDATE runs
        SET finished_at = ?, status = ?, videos_completed = ?,
            videos_failed = ?, error_summary = ?
        WHERE id = ?
        """,
        (
            iso_now(),
            status,
            completed,
            failed,
            json.dumps(errors, ensure_ascii=False) if errors else None,
            run_id,
        ),
    )
    conn.commit()


def write_report(report: dict[str, Any]) -> Path:
    RUN_LOG_DIR.mkdir(parents=True, exist_ok=True)
    path = RUN_LOG_DIR / f"{report['run_id']}-worker.json"
    temp = path.with_suffix(".json.tmp")
    temp.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.replace(temp, path)
    return path


def start_attempt(conn: sqlite3.Connection, video_id: int, run_id: str, stage: str) -> int:
    cursor = conn.execute(
        """
        INSERT INTO attempts(video_id, run_id, stage, started_at, status)
        VALUES (?, ?, ?, ?, 'running')
        """,
        (video_id, run_id, stage, iso_now()),
    )
    conn.commit()
    return int(cursor.lastrowid)


def finish_attempt(
    conn: sqlite3.Connection,
    attempt_id: int,
    status: str,
    error: Exception | None = None,
) -> None:
    conn.execute(
        """
        UPDATE attempts
        SET finished_at = ?, status = ?, error_type = ?, error_message = ?
        WHERE id = ?
        """,
        (
            iso_now(),
            status,
            type(error).__name__ if error else None,
            str(error)[:4000] if error else None,
            attempt_id,
        ),
    )
    conn.commit()


def set_status(
    conn: sqlite3.Connection,
    video_id: int,
    status: str,
    *,
    last_error: str | None = None,
    next_retry_at: str | None = None,
) -> None:
    conn.execute(
        """
        UPDATE videos
        SET status = ?, last_error = ?, next_retry_at = ?, updated_at = ?
        WHERE id = ?
        """,
        (status, last_error, next_retry_at, iso_now(), video_id),
    )
    conn.commit()


def claim_next(conn: sqlite3.Connection, shortcode: str | None) -> sqlite3.Row | None:
    now = iso_now()
    conn.execute("BEGIN IMMEDIATE")
    where = """
      (v.status = 'pending' OR
       (v.status = 'retry_wait' AND (v.next_retry_at IS NULL OR v.next_retry_at <= ?)))
    """
    params: list[Any] = [now]
    if shortcode:
        where += " AND v.shortcode = ?"
        params.append(shortcode)
    row = conn.execute(
        f"""
        SELECT v.*, c.username, c.language
        FROM videos v
        JOIN creators c ON c.id = v.creator_id
        WHERE {where} AND c.enabled = 1
        ORDER BY v.published_at DESC, v.id DESC
        LIMIT 1
        """,
        params,
    ).fetchone()
    if not row:
        conn.commit()
        return None
    conn.execute(
        """
        UPDATE videos
        SET status = 'downloading', attempt_count = attempt_count + 1,
            next_retry_at = NULL, last_error = NULL, updated_at = ?
        WHERE id = ?
        """,
        (iso_now(), row["id"]),
    )
    conn.commit()
    return conn.execute(
        """
        SELECT v.*, c.username, c.language
        FROM videos v JOIN creators c ON c.id = v.creator_id
        WHERE v.id = ?
        """,
        (row["id"],),
    ).fetchone()


def paths_for(username: str, shortcode: str) -> tuple[Path, Path, Path, Path]:
    stem = safe_artifact_stem("instagram", shortcode)
    return (
        DOWNLOAD_ROOT / username / stem,
        TRANSCRIPT_ROOT / username / stem,
        TEMP_ROOT / username / stem,
        MARKDOWN_ROOT / "instagram" / username / f"{stem}.md",
    )


def run_command(command: list[str], timeout: int) -> None:
    run_logged(
        command,
        cwd=ROOT,
        timeout=timeout,
        label=Path(command[0]).name,
        start_new_session=False,
    )

def instagram_backend() -> str:
    try:
        payload = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
        value = payload.get("providers", {}).get("instagram", {}).get("backend", "auto")
    except (FileNotFoundError, json.JSONDecodeError, TypeError):
        value = "auto"
    value = str(value).lower()
    return value if value in {"auto", "gallery-dl", "instaloader"} else "auto"


def _gallery_download(
    source_url: str,
    shortcode: str,
    output_dir: Path,
    cookies_browser: str,
    cookies_file: Path | None,
    force_ipv4: bool,
) -> list[Path]:
    try:
        refresh_if_configured("instagram")
    except Exception:
        pass
    executable = command_path("gallery-dl")
    if not executable:
        raise RuntimeError("gallery-dl command was not found")
    output_dir.mkdir(parents=True, exist_ok=True)
    command = [executable]
    selected_cookie_file = cookies_file if cookies_file and cookies_file.is_file() else None
    if selected_cookie_file is None and COOKIE_FILE.is_file():
        selected_cookie_file = COOKIE_FILE
    if selected_cookie_file is not None:
        command += ["--cookies", str(selected_cookie_file)]
        print(f"  COOKIE_SOURCE file={selected_cookie_file}", file=sys.stderr, flush=True)
    else:
        command += ["--cookies-from-browser", cookies_browser]
        print(f"  COOKIE_SOURCE browser={cookies_browser}", file=sys.stderr, flush=True)
    command += [
        "--retries", "5", "--http-timeout", "120",
        "--directory", str(output_dir),
        "--filename", f"{shortcode}_{{num}}.{{extension}}", source_url,
    ]
    if force_ipv4:
        command.insert(1, "--force-ipv4")
    run_command(command, timeout=900)
    files = sorted(
        [p for p in output_dir.rglob("*.mp4") if p.is_file() and p.stat().st_size > 0],
        key=lambda p: p.name,
    )
    if not files:
        raise RuntimeError("gallery-dl completed but no non-empty MP4 was found")
    return files


def _instaloader_download(shortcode: str, output_dir: Path) -> list[Path]:
    if not INSTALOADER_HELPER.is_file():
        raise RuntimeError(f"Instaloader fallback helper is missing: {INSTALOADER_HELPER}")
    result = subprocess.run(
        [sys.executable, str(INSTALOADER_HELPER), "download", shortcode, "--output-dir", str(output_dir)],
        cwd=ROOT, capture_output=True, text=True, timeout=900, check=False,
    )
    if result.returncode != 0:
        raise RuntimeError("Instaloader download failed: " + (result.stderr.strip()[-3000:] or "unknown error"))
    try:
        payload = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"Instaloader download returned invalid JSON: {exc}") from exc
    files = [Path(value) for value in payload if Path(value).is_file() and Path(value).stat().st_size > 0]
    if not files:
        raise RuntimeError("Instaloader completed but no non-empty MP4 was found")
    return files


def download_media(
    source_url: str,
    shortcode: str,
    output_dir: Path,
    cookies_browser: str,
    cookies_file: Path | None,
    force_ipv4: bool,
) -> list[Path]:
    backend = instagram_backend()
    gallery_error: Exception | None = None
    if backend in {"auto", "gallery-dl"}:
        try:
            files = _gallery_download(
                source_url, shortcode, output_dir, cookies_browser, cookies_file, force_ipv4
            )
            print("  BACKEND_SELECTED backend=gallery-dl", file=sys.stderr, flush=True)
            return files
        except Exception as exc:
            gallery_error = exc
            if backend == "gallery-dl":
                raise
            print(
                f"  BACKEND_FALLBACK gallery-dl -> instaloader reason={type(exc).__name__}",
                file=sys.stderr, flush=True,
            )
            shutil.rmtree(output_dir, ignore_errors=True)
    try:
        files = _instaloader_download(shortcode, output_dir)
        print("  BACKEND_SELECTED backend=instaloader", file=sys.stderr, flush=True)
        return files
    except Exception as instaloader_error:
        if gallery_error is not None:
            raise RuntimeError(
                f"Both Instagram download backends failed. gallery-dl={gallery_error}; "
                f"instaloader={instaloader_error}"
            ) from instaloader_error
        raise


def transcribe_media(
    files: list[Path],
    output_dir: Path,
    shortcode: str,
    language: str,
    model: str,
) -> list[tuple[Path, str]]:
    executable = command_path("mlx_whisper")
    if not executable:
        raise RuntimeError("mlx_whisper command was not found")
    output_dir.mkdir(parents=True, exist_ok=True)
    results: list[tuple[Path, str]] = []
    for index, media in enumerate(files, start=1):
        name = safe_artifact_stem("instagram", shortcode if len(files) == 1 else f"{shortcode}_part_{index}")
        command = [
            executable,
            str(media),
            "--model", model,
            "--output-dir", str(output_dir),
            f"--output-name={name}",
            "--output-format", "txt",
            "--task", "transcribe",
        ]
        if language and language.lower() != "auto":
            command.extend(["--language", language])
        run_command(command, timeout=7200)
        transcript = output_dir / f"{name}.txt"
        if not transcript.is_file():
            raise RuntimeError(f"Expected transcript not created: {transcript}")
        results.append((media, transcript.read_text(encoding="utf-8").strip()))
    return results


def yaml_value(value: Any) -> str:
    return json.dumps("" if value is None else str(value), ensure_ascii=False)


def render_markdown(
    video: sqlite3.Row,
    transcripts: list[tuple[Path, str]],
    model: str,
    temp_dir: Path,
    final_path: Path,
) -> tuple[Path, str]:
    temp_dir.mkdir(parents=True, exist_ok=True)
    final_path.parent.mkdir(parents=True, exist_ok=True)
    caption = (video["caption"] or "").strip()
    lines = [
        "---",
        "platform: instagram",
        f"creator: {yaml_value(video['username'])}",
        f"shortcode: {yaml_value(video['shortcode'])}",
        f"source_url: {yaml_value(video['source_url'])}",
        f"published_at: {yaml_value(video['published_at'])}",
        f"processed_at: {yaml_value(iso_now())}",
        f"transcription_model: {yaml_value(model)}",
        "---",
        "",
        f"# Instagram Reel: {video['shortcode']}",
        "",
        "## 原始 Caption",
        "",
        caption or "_No caption provided._",
        "",
        "## 語音逐字稿",
        "",
    ]
    for index, (media, text) in enumerate(transcripts, start=1):
        if len(transcripts) > 1:
            lines.extend([f"### Part {index}", "", f"Source media: `{media.name}`", ""])
        lines.extend([text or "_No speech detected._", ""])
    content = "\n".join(lines).rstrip() + "\n"
    temp_path = temp_dir / f".{video['shortcode']}.md.tmp"
    temp_path.write_text(content, encoding="utf-8")
    required = (video["shortcode"], video["source_url"], "## 原始 Caption", "## 語音逐字稿")
    if temp_path.stat().st_size < 150 or any(token not in content for token in required):
        raise RuntimeError("Rendered Markdown failed validation")
    os.replace(temp_path, final_path)
    return final_path, sha256_file(final_path)


def cleanup(download_dir: Path, transcript_dir: Path, temp_dir: Path) -> None:
    for path in (download_dir, transcript_dir, temp_dir):
        if path.exists():
            shutil.rmtree(path)
    for parent in (download_dir.parent, transcript_dir.parent, temp_dir.parent):
        try:
            parent.rmdir()
        except OSError:
            pass


def next_retry(attempt_count: int) -> str | None:
    if attempt_count >= MAX_ATTEMPTS:
        return None
    index = min(max(attempt_count - 1, 0), len(RETRY_DELAYS_MINUTES) - 1)
    return (utc_now() + timedelta(minutes=RETRY_DELAYS_MINUTES[index])).isoformat(timespec="seconds")


def mark_failure(conn: sqlite3.Connection, video: sqlite3.Row, error: Exception) -> str:
    count = int(video["attempt_count"])
    status = "failed" if count >= MAX_ATTEMPTS else "retry_wait"
    set_status(
        conn,
        video["id"],
        status,
        last_error=f"{type(error).__name__}: {error}"[:4000],
        next_retry_at=next_retry(count),
    )
    return status


def run_stage(conn: sqlite3.Connection, video_id: int, run_id: str, stage: str, function):
    attempt_id = start_attempt(conn, video_id, run_id, stage)
    try:
        value = function()
        finish_attempt(conn, attempt_id, "completed")
        return value
    except Exception as exc:
        finish_attempt(conn, attempt_id, "failed", exc)
        raise


def process_one(
    conn: sqlite3.Connection,
    video: sqlite3.Row,
    run_id: str,
    cookies_browser: str,
    cookies_file: Path | None,
    force_ipv4: bool,
    model: str,
) -> dict[str, Any]:
    username = video["username"]
    shortcode = video["shortcode"]
    download_dir, transcript_dir, temp_dir, markdown_path = paths_for(username, shortcode)
    result: dict[str, Any] = {
        "creator": username,
        "shortcode": shortcode,
        "attempt_count": int(video["attempt_count"]),
        "status": "running",
        "markdown_path": None,
        "error": None,
    }
    try:
        print("  STAGE downloading")
        media = run_stage(
            conn, video["id"], run_id, "download",
            lambda: download_media(
                video["source_url"], shortcode, download_dir, cookies_browser, cookies_file, force_ipv4
            ),
        )
        set_status(conn, video["id"], "downloaded")
        set_status(conn, video["id"], "transcribing")
        print("  STAGE transcribing")
        transcripts = run_stage(
            conn, video["id"], run_id, "transcribe",
            lambda: transcribe_media(
                media, transcript_dir, shortcode, video["language"] or "auto", model
            ),
        )
        set_status(conn, video["id"], "transcribed")
        set_status(conn, video["id"], "rendering")
        print("  STAGE rendering")
        final_path, digest = run_stage(
            conn, video["id"], run_id, "render",
            lambda: render_markdown(video, transcripts, model, temp_dir, markdown_path),
        )
        set_status(conn, video["id"], "validating")
        print("  STAGE validating")
        if not final_path.is_file() or final_path.stat().st_size < 150:
            raise RuntimeError("Final Markdown validation failed")
        set_status(conn, video["id"], "cleaning")
        print("  STAGE cleaning")
        run_stage(
            conn, video["id"], run_id, "cleanup",
            lambda: cleanup(download_dir, transcript_dir, temp_dir),
        )
        conn.execute(
            """
            UPDATE videos
            SET status = 'completed', markdown_path = ?, markdown_sha256 = ?,
                completed_at = ?, next_retry_at = NULL, last_error = NULL,
                updated_at = ?
            WHERE id = ?
            """,
            (
                str(final_path.relative_to(ROOT)),
                digest,
                iso_now(),
                iso_now(),
                video["id"],
            ),
        )
        conn.commit()
        result["status"] = "completed"
        result["markdown_path"] = str(final_path.relative_to(ROOT))
    except Exception as exc:
        conn.rollback()
        result["status"] = mark_failure(conn, video, exc)
        result["error"] = f"{type(exc).__name__}: {exc}"
    return result


def list_queue(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    return conn.execute(
        """
        SELECT c.username, v.shortcode, v.published_at, v.status,
               v.attempt_count, v.next_retry_at, v.last_error
        FROM videos v JOIN creators c ON c.id = v.creator_id
        WHERE v.status IN ('pending', 'retry_wait', 'failed')
        ORDER BY v.published_at DESC, v.id DESC
        """
    ).fetchall()


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="Download queued Reels, transcribe them, write Markdown, and clean intermediates."
    )
    p.add_argument("--limit", type=int, default=1)
    p.add_argument("--shortcode")
    p.add_argument(
        "--cookies-browser",
        default=os.environ.get("GALLERY_DL_COOKIES_BROWSER", "chrome/instagram.com"),
    )
    p.add_argument(
        "--cookies-file",
        type=Path,
        default=None,
        help=(
            "Netscape-format Instagram cookie file. If omitted or missing, use the managed "
            "data/secrets/instagram-cookies.txt file, then fall back to --cookies-browser."
        ),
    )
    p.add_argument("--force-ipv4", action="store_true")
    p.add_argument("--model", default=os.environ.get("WHISPER_MODEL", DEFAULT_MODEL))
    p.add_argument("--list", action="store_true")
    return p


def main() -> int:
    args = parser().parse_args()
    if not DB_PATH.exists():
        print(f"ERROR: Database not found: {DB_PATH}", file=sys.stderr)
        return 1
    if not 1 <= args.limit <= 100:
        print("ERROR: --limit must be between 1 and 100", file=sys.stderr)
        return 1

    conn = connect()
    if args.list:
        rows = list_queue(conn)
        print("CREATOR | SHORTCODE | PUBLISHED_AT | STATUS | ATTEMPTS | NEXT_RETRY | LAST_ERROR")
        print("-" * 130)
        for row in rows:
            error = (row["last_error"] or "-").replace("\n", " ")[:100]
            print(
                f"{row['username']} | {row['shortcode']} | {row['published_at'] or '-'} | "
                f"{row['status']} | {row['attempt_count']} | {row['next_retry_at'] or '-'} | {error}"
            )
        if not rows:
            print("(queue empty)")
        conn.close()
        return 0

    run_id = utc_now().strftime("%Y%m%dT%H%M%SZ") + "-" + uuid.uuid4().hex[:8]
    owner = f"{socket.gethostname()}:{os.getpid()}:{run_id}"
    report: dict[str, Any] = {
        "run_id": run_id,
        "type": "worker",
        "started_at": iso_now(),
        "finished_at": None,
        "status": "running",
        "limit": args.limit,
        "model": args.model,
        "items": [],
        "completed": 0,
        "failed": 0,
        "errors": [],
    }
    locked = False
    try:
        acquire_lock(conn, owner)
        locked = True
        create_run(conn, run_id)
        for _ in range(args.limit):
            video = claim_next(conn, args.shortcode)
            if not video:
                break
            print(f"\nProcessing {video['username']}/{video['shortcode']} attempt={video['attempt_count']}")
            result = process_one(
                conn,
                video,
                run_id,
                args.cookies_browser,
                args.cookies_file.expanduser().resolve() if args.cookies_file else None,
                args.force_ipv4,
                args.model,
            )
            report["items"].append(result)
            if result["status"] == "completed":
                report["completed"] += 1
                print(f"  COMPLETED {result['markdown_path']}")
            else:
                report["failed"] += 1
                report["errors"].append(
                    f"{result['creator']}/{result['shortcode']}: {result['error']}"
                )
                print(f"  {result['status'].upper()} {result['error']}", file=sys.stderr)
            if args.shortcode:
                break

        report["finished_at"] = iso_now()
        report["status"] = "completed_with_errors" if report["errors"] else "completed"
        finish_run(
            conn,
            run_id,
            report["status"],
            report["completed"],
            report["failed"],
            report["errors"],
        )
        report_path = write_report(report)
        print(f"\nWORKER_{report['status'].upper()}")
        print(f"completed={report['completed']}")
        print(f"failed={report['failed']}")
        print(f"report={report_path}")
        return 0 if not report["errors"] else 2
    except Exception as exc:
        conn.rollback()
        report["finished_at"] = iso_now()
        report["status"] = "failed"
        report["errors"].append(f"{type(exc).__name__}: {exc}")
        try:
            if conn.execute("SELECT id FROM runs WHERE id = ?", (run_id,)).fetchone():
                finish_run(conn, run_id, "failed", report["completed"], report["failed"] + 1, report["errors"])
        except sqlite3.Error:
            pass
        report_path = write_report(report)
        print(f"ERROR: {exc}", file=sys.stderr)
        print(f"report={report_path}", file=sys.stderr)
        return 1
    finally:
        if locked:
            try:
                release_lock(conn, owner)
            except sqlite3.Error as exc:
                print(f"WARNING: Could not release lock: {exc}", file=sys.stderr)
        conn.close()


if __name__ == "__main__":
    raise SystemExit(main())
