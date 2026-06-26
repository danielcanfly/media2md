#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import fcntl
import json
import os
import re
import shlex
import signal
import subprocess
import time
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
COMMAND_LOG_DIR = ROOT / "logs" / "runs" / "commands"
LOCK_DIR = ROOT / "logs" / "locks"
MAINTENANCE_LOCK_PATH = LOCK_DIR / "maintenance.lock"


def iso_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def safe_artifact_stem(provider: str, external_id: str, *, max_length: int = 160) -> str:
    """Return a deterministic filesystem/CLI-safe artifact name.

    Platform IDs remain unchanged in metadata and databases. Only local paths and
    command argument values use this stem. Leading dashes are never returned.
    """
    raw = str(external_id or "").strip()
    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "_", raw).strip("._-")
    if not cleaned:
        cleaned = hashlib.sha256(raw.encode("utf-8", errors="replace")).hexdigest()[:16]
    provider_clean = re.sub(r"[^A-Za-z0-9]+", "_", str(provider or "media")).strip("_").lower() or "media"
    needs_prefix = raw != cleaned or raw.startswith("-") or raw.startswith(".")
    stem = f"{provider_clean}_{cleaned}" if needs_prefix else cleaned
    if len(stem) > max_length:
        digest = hashlib.sha256(raw.encode("utf-8", errors="replace")).hexdigest()[:12]
        stem = f"{stem[: max_length - 13]}_{digest}"
    return stem


def _safe_lock_component(value: str, *, max_length: int = 120) -> str:
    raw = str(value or "").strip()
    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "_", raw).strip("._-") or "operation"
    if len(cleaned) > max_length:
        digest = hashlib.sha256(raw.encode("utf-8", errors="replace")).hexdigest()[:12]
        cleaned = f"{cleaned[: max_length - 13]}_{digest}"
    return cleaned


def _lock_owner(path: Path) -> dict[str, Any] | None:
    try:
        raw = path.read_text(encoding="utf-8").strip()
        return json.loads(raw) if raw else None
    except (FileNotFoundError, OSError, json.JSONDecodeError):
        return None


def _acquire_flock(handle: Any, mode: int, *, wait_seconds: float) -> bool:
    deadline = time.monotonic() + max(0.0, float(wait_seconds))
    while True:
        try:
            fcntl.flock(handle.fileno(), mode | fcntl.LOCK_NB)
            return True
        except BlockingIOError:
            if time.monotonic() >= deadline:
                return False
            time.sleep(0.1)


@contextmanager
def maintenance_lock(
    *,
    exclusive: bool,
    operation: str,
    wait_seconds: float = 0,
):
    """Coordinate live mutations with consistent state maintenance.

    Normal sync/process commands take a shared lock. State backup and other
    maintenance commands take an exclusive lock, so a backup can never capture
    a half-mutated checkpoint while a live run is active.
    """
    LOCK_DIR.mkdir(parents=True, exist_ok=True)
    with MAINTENANCE_LOCK_PATH.open("a+", encoding="utf-8") as handle:
        mode = fcntl.LOCK_EX if exclusive else fcntl.LOCK_SH
        if not _acquire_flock(handle, mode, wait_seconds=wait_seconds):
            raise RuntimeError(
                "Media2MD is busy with another live or maintenance operation. "
                f"requested_operation={operation}"
            )
        if exclusive:
            handle.seek(0)
            handle.truncate()
            handle.write(json.dumps({
                "pid": os.getpid(),
                "operation": operation,
                "started_at": iso_now(),
            }, sort_keys=True))
            handle.flush()
            os.fsync(handle.fileno())
        try:
            yield
        finally:
            if exclusive:
                handle.seek(0)
                handle.truncate()
                handle.flush()
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


@contextmanager
def operation_lock(
    scope: str,
    key: str,
    *,
    metadata: dict[str, Any] | None = None,
    wait_seconds: float = 0,
):
    """Prevent duplicate sync/process work while allowing unrelated creators.

    Every live operation also holds the shared maintenance lock. This lets
    backups take an exclusive, point-in-time snapshot without racing writers.
    """
    safe_scope = _safe_lock_component(scope)
    safe_key = _safe_lock_component(key)
    path = LOCK_DIR / f"{safe_scope}--{safe_key}.lock"
    payload = {
        "pid": os.getpid(),
        "scope": scope,
        "key": key,
        "started_at": iso_now(),
        **(metadata or {}),
    }
    with maintenance_lock(exclusive=False, operation=f"{scope}:{key}", wait_seconds=wait_seconds):
        LOCK_DIR.mkdir(parents=True, exist_ok=True)
        with path.open("a+", encoding="utf-8") as handle:
            if not _acquire_flock(handle, fcntl.LOCK_EX, wait_seconds=wait_seconds):
                owner = _lock_owner(path) or {}
                owner_text = " ".join(
                    f"{name}={owner[name]}"
                    for name in ("pid", "scope", "key", "provider", "creator", "media_id", "started_at")
                    if owner.get(name) not in (None, "")
                )
                suffix = f" active_owner=\"{owner_text}\"" if owner_text else ""
                raise RuntimeError(
                    f"Media2MD operation already running: scope={scope} key={key}.{suffix}"
                )
            handle.seek(0)
            handle.truncate()
            handle.write(json.dumps(payload, ensure_ascii=False, sort_keys=True))
            handle.flush()
            os.fsync(handle.fileno())
            try:
                yield path
            finally:
                handle.seek(0)
                handle.truncate()
                handle.flush()
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def extract_root_cause(stdout: str | None, stderr: str | None) -> str:
    text = "\n".join(part for part in (stdout or "", stderr or "") if part).strip()
    if not text:
        return "command failed without output"
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    priority = (
        r"(^|\s)error:\s*.+",
        r"argument\s+--?[A-Za-z0-9_-]+:\s*.+",
        r"unrecognized arguments?:\s*.+",
        r"invalid choice:\s*.+",
        r"no such file or directory:\s*.+",
        r"permission denied:\s*.+",
        r"out of memory|memoryerror|metal.*memory|failed to allocate",
        r"timed out|timeout|connection reset|temporarily unavailable",
    )
    for pattern in priority:
        regex = re.compile(pattern, re.I)
        for line in reversed(lines):
            match = regex.search(line)
            if match:
                return line[-1000:]
    return lines[-1][-1000:]


def _redacted_command(command: list[str]) -> list[str]:
    # Values are intentionally not globally redacted because paths and profile
    # names are useful diagnostics. Cookie contents are never command arguments.
    return [str(item) for item in command]


def write_command_log(
    command: list[str],
    returncode: int,
    stdout: str | None,
    stderr: str | None,
    *,
    label: str = "command",
) -> Path:
    COMMAND_LOG_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S.%fZ")
    safe_label = re.sub(r"[^A-Za-z0-9._-]+", "_", label).strip("._-") or "command"
    path = COMMAND_LOG_DIR / f"{timestamp}-{safe_label}-{os.getpid()}.log"
    payload = [
        f"timestamp={iso_now()}",
        f"returncode={returncode}",
        "command=" + shlex.join(_redacted_command(command)),
        "",
        "--- stdout ---",
        stdout or "",
        "",
        "--- stderr ---",
        stderr or "",
        "",
    ]
    path.write_text("\n".join(payload), encoding="utf-8")
    try:
        path.chmod(0o600)
    except OSError:
        pass
    return path


class CommandExecutionError(RuntimeError):
    def __init__(
        self,
        command: list[str],
        returncode: int,
        stdout: str | None,
        stderr: str | None,
        log_path: Path,
    ) -> None:
        self.command = list(command)
        self.returncode = int(returncode)
        self.stdout = stdout or ""
        self.stderr = stderr or ""
        self.log_path = log_path
        self.root_cause = extract_root_cause(self.stdout, self.stderr)
        super().__init__(f"{self.root_cause} (full_log={log_path})")


def run_logged(
    command: list[str],
    *,
    cwd: Path | None = None,
    timeout: int = 300,
    label: str = "command",
    start_new_session: bool = True,
) -> subprocess.CompletedProcess[str]:
    process = subprocess.Popen(
        command,
        cwd=cwd or ROOT,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        start_new_session=start_new_session,
    )
    timed_out = False
    try:
        stdout, stderr = process.communicate(timeout=timeout)
    except KeyboardInterrupt:
        try:
            os.killpg(process.pid, signal.SIGTERM)
        except ProcessLookupError:
            pass
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
        raise
    except subprocess.TimeoutExpired:
        timed_out = True
        try:
            os.killpg(process.pid, signal.SIGTERM)
        except ProcessLookupError:
            pass
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
        stdout, stderr = process.communicate()
        stderr = (stderr or "") + f"\nERROR: timed out after {timeout} seconds"
    returncode = 124 if timed_out else process.returncode
    result = subprocess.CompletedProcess(command, returncode, stdout, stderr)
    if returncode != 0:
        log_path = write_command_log(command, returncode, stdout, stderr, label=label)
        raise CommandExecutionError(command, returncode, stdout, stderr, log_path)
    return result


def classify_transcription_exception(exc: Exception) -> dict[str, Any]:
    root = getattr(exc, "root_cause", str(exc))
    lower = str(root).lower()
    log_path = str(getattr(exc, "log_path", "")) or None
    if any(token in lower for token in (
        "expected one argument", "unrecognized argument", "unrecognized option",
        "invalid choice", "usage:", "unknown option",
    )):
        return {
            "error_code": "invalid_transcription_argument",
            "retryable": False,
            "action_required": True,
            "required_action": "upgrade_media2md_or_report_internal_bug",
            "root_cause": str(root),
            "log_path": log_path,
        }
    if any(token in lower for token in ("command not found", "no such file or directory", "mlx_whisper command was not found")):
        return {
            "error_code": "missing_transcription_dependency",
            "retryable": False,
            "action_required": True,
            "required_action": "install_mlx_whisper",
            "root_cause": str(root),
            "log_path": log_path,
        }
    if any(token in lower for token in ("out of memory", "memoryerror", "metal", "failed to allocate")):
        return {
            "error_code": "transcription_resource_exhausted",
            "retryable": False,
            "action_required": True,
            "required_action": "use_smaller_model_or_shorter_chunks",
            "root_cause": str(root),
            "log_path": log_path,
        }
    if any(token in lower for token in (
        "timed out", "timeout", "connection reset", "temporarily unavailable",
        "name resolution", "network is unreachable", "http error 429", "http error 5",
    )):
        return {
            "error_code": "transcription_transient_error",
            "retryable": True,
            "action_required": False,
            "required_action": None,
            "root_cause": str(root),
            "log_path": log_path,
        }
    if "expected transcript" in lower or "did not create" in lower:
        return {
            "error_code": "transcription_output_missing",
            "retryable": False,
            "action_required": True,
            "required_action": "inspect_transcription_log",
            "root_cause": str(root),
            "log_path": log_path,
        }
    return {
        "error_code": "transcription_process_error",
        "retryable": False,
        "action_required": True,
        "required_action": "inspect_transcription_log",
        "root_cause": str(root),
        "log_path": log_path,
    }
