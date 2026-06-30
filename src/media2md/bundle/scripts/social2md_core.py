#!/usr/bin/env python3
from __future__ import annotations

import argparse
import fcntl
import json
import math
import os
import re
import signal
import shutil
import sqlite3
import statistics
import subprocess
import sys
import time
import uuid
import urllib.error
import urllib.request
from contextlib import contextmanager
from datetime import date, datetime, time as dt_time, timedelta, timezone
from pathlib import Path
from typing import Any, Iterator
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError, available_timezones

_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
if sys.path and sys.path[0] == _SCRIPT_DIR:
    sys.path.append(sys.path.pop(0))

try:
    from media2md.cli_result_types import cli_result
    from media2md.required_actions import validate_required_action
except ModuleNotFoundError:
    from media2md_contract_compat import cli_result, validate_required_action

from media2md_paths import command_path

ROOT = Path(__file__).resolve().parents[1]
CONFIG_PATH = ROOT / "config" / "social2md.json"
POLICY_PATH = ROOT / "config" / "creator_policies.json"
SCHEDULER_STATE_PATH = ROOT / "data" / "social2md_scheduler_state.json"
PERFORMANCE_PATH = ROOT / "data" / "social2md_performance.json"
DB_PATH = ROOT / "data" / "state.db"
CATALOG_DIR = ROOT / "data" / "creator_catalogs"
RUN_DIR = ROOT / "logs" / "runs"
SCHEDULER_LOCK = ROOT / "logs" / "social2md-scheduler.lock"
ENGINE = ROOT / "scripts" / "creator_bulk.py"
OPENCLAW_SKILL_SOURCE = ROOT / "openclaw" / "SKILL.md"
GENERIC_MEDIA = ROOT / "scripts" / "generic_media.py"
VERSION = "0.4.0"

PROFILE_RE = re.compile(r"https?://(?:www\.)?instagram\.com/([A-Za-z0-9._]+)/?", re.I)
USERNAME_RE = re.compile(r"^[A-Za-z0-9._]+$")
DURATION_RE = re.compile(r"^(\d+(?:\.\d+)?)(m|h|d|w)$", re.I)

LOCALES = ("zh-TW", "zh-CN", "en", "ja")
MESSAGES = {
    "en": {
        "init_done": "Social2MD initialization completed.",
        "batch": "Batch",
        "progress": "Progress",
        "batch_eta": "Batch ETA",
        "total_eta": "Total ETA",
        "calculating": "calculating",
        "remaining": "remaining",
        "completed": "completed",
        "failed": "failed",
        "sync_page": "Sync page",
        "no_work": "No eligible videos remain.",
        "stopped": "Run stopped by a safety limit.",
        "interrupted": "Run interrupted safely. Completed items were preserved.",
    },
    "zh-TW": {
        "init_done": "Social2MD 初始化完成。",
        "batch": "批次",
        "progress": "進度",
        "batch_eta": "本批預估剩餘",
        "total_eta": "全部預估剩餘",
        "calculating": "計算中",
        "remaining": "剩餘",
        "completed": "完成",
        "failed": "失敗",
        "sync_page": "同步頁",
        "no_work": "沒有符合條件且尚未完成的影片。",
        "stopped": "已因安全限制停止執行。",
        "interrupted": "已安全中止。完成項目已保留，下次可接續。",
    },
    "zh-CN": {
        "init_done": "Social2MD 初始化完成。",
        "batch": "批次",
        "progress": "进度",
        "batch_eta": "本批预计剩余",
        "total_eta": "全部预计剩余",
        "calculating": "计算中",
        "remaining": "剩余",
        "completed": "完成",
        "failed": "失败",
        "sync_page": "同步页",
        "no_work": "没有符合条件且尚未完成的视频。",
        "stopped": "已因安全限制停止执行。",
        "interrupted": "已安全中止。已完成项目会保留，下次可继续。",
    },
    "ja": {
        "init_done": "Social2MD の初期化が完了しました。",
        "batch": "バッチ",
        "progress": "進捗",
        "batch_eta": "バッチ残り時間",
        "total_eta": "全体残り時間",
        "calculating": "計算中",
        "remaining": "残り",
        "completed": "完了",
        "failed": "失敗",
        "sync_page": "同期ページ",
        "no_work": "対象となる未処理動画はありません。",
        "stopped": "安全制限により停止しました。",
        "interrupted": "安全に中断しました。完了済みの項目は保持されています。",
    },
}

DEFAULT_CONFIG = {
    "schema_version": 1,
    "ui_locale": "en",
    "markdown_locale": "en",
    "timezone": "UTC",
    "defaults": {
        "sync": {
            "enabled": False,
            "every_minutes": 1440,
            "full_every_minutes": 10080,
            "quick_window": 100,
        },
        "processing": {
            "scheduled": False,
            "every_minutes": 4320,
            "mode": "batch",
            "batch_size": 100,
            "max_batches": 0,
            "max_runtime_minutes": 360,
            "max_failures": 10,
            "stop_on_failure": False,
            "sleep_between_batches": 5,
        },
        "filters": {
            "since": None,
            "until": None,
            "rank_from": None,
            "rank_to": None,
            "order": "newest_first",
        },
    },
    "updates": {
        "enabled": False,
        "repository": None,
        "check_every_minutes": 1440,
    },
}


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def iso_now() -> str:
    return now_utc().isoformat(timespec="seconds")


def run_id() -> str:
    return now_utc().strftime("%Y%m%dT%H%M%SZ") + "-" + uuid.uuid4().hex[:8]


def atomic_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.replace(tmp, path)


def deep_copy(value: Any) -> Any:
    return json.loads(json.dumps(value))


def deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    result = deep_copy(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = deep_merge(result[key], value)
        else:
            result[key] = value
    return result


def load_json(path: Path, default: Any) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return deep_copy(default)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"Invalid JSON file: {path}: {exc}") from exc


def load_config() -> dict[str, Any]:
    return deep_merge(DEFAULT_CONFIG, load_json(CONFIG_PATH, {}))


def load_policies() -> dict[str, Any]:
    payload = load_json(POLICY_PATH, {"schema_version": 1, "creators": {}})
    payload.setdefault("schema_version", 1)
    payload.setdefault("creators", {})
    return payload


def save_policies(payload: dict[str, Any]) -> None:
    atomic_json(POLICY_PATH, payload)


def normalize_creator(value: str) -> str:
    text = value.strip()
    match = PROFILE_RE.match(text)
    username = match.group(1) if match else text.lstrip("@")
    if username.lower() in {"reel", "reels", "p", "tv", "explore", "accounts"}:
        raise RuntimeError("Expected a creator username or profile URL.")
    if not USERNAME_RE.fullmatch(username):
        raise RuntimeError("Unsupported creator identifier.")
    return username


def parse_duration(value: str) -> int:
    match = DURATION_RE.fullmatch(value.strip())
    if not match:
        raise argparse.ArgumentTypeError("Use a duration such as 30m, 6h, 3d, or 2w.")
    number = float(match.group(1))
    unit = match.group(2).lower()
    factor = {"m": 1, "h": 60, "d": 1440, "w": 10080}[unit]
    minutes = int(round(number * factor))
    if minutes < 1:
        raise argparse.ArgumentTypeError("Duration must be at least one minute.")
    return minutes


def duration_text(minutes: int) -> str:
    if minutes % 10080 == 0:
        return f"{minutes // 10080}w"
    if minutes % 1440 == 0:
        return f"{minutes // 1440}d"
    if minutes % 60 == 0:
        return f"{minutes // 60}h"
    return f"{minutes}m"


def detect_timezone() -> str:
    env = os.getenv("TZ")
    if env:
        try:
            ZoneInfo(env)
            return env
        except ZoneInfoNotFoundError:
            pass
    try:
        target = Path("/etc/localtime").resolve()
        marker = "/zoneinfo/"
        text = str(target)
        if marker in text:
            zone = text.split(marker, 1)[1]
            ZoneInfo(zone)
            return zone
    except (OSError, ZoneInfoNotFoundError):
        pass
    return "UTC"


def offset_label(zone_name: str) -> str:
    zone = ZoneInfo(zone_name)
    offset = datetime.now(zone).utcoffset() or timedelta(0)
    total_minutes = int(offset.total_seconds() // 60)
    sign = "+" if total_minutes >= 0 else "-"
    total_minutes = abs(total_minutes)
    return f"UTC{sign}{total_minutes // 60:02d}:{total_minutes % 60:02d}"


def select_timezone(default: str) -> str:
    # One representative IANA zone for each currently used civil UTC offset.
    representatives = [
        ("UTC-12:00", "Etc/GMT+12", "International Date Line West"),
        ("UTC-11:00", "Pacific/Pago_Pago", "Pago Pago"),
        ("UTC-10:00", "Pacific/Honolulu", "Honolulu"),
        ("UTC-09:30", "Pacific/Marquesas", "Marquesas"),
        ("UTC-09:00", "Pacific/Gambier", "Gambier"),
        ("UTC-08:00", "Pacific/Pitcairn", "Adamstown"),
        ("UTC-07:00", "America/Phoenix", "Phoenix"),
        ("UTC-06:00", "America/Guatemala", "Guatemala City"),
        ("UTC-05:00", "America/Bogota", "Bogota"),
        ("UTC-04:00", "America/Santo_Domingo", "Santo Domingo"),
        ("UTC-03:30", "America/St_Johns", "St. John's"),
        ("UTC-03:00", "America/Argentina/Buenos_Aires", "Buenos Aires"),
        ("UTC-02:00", "America/Noronha", "Fernando de Noronha"),
        ("UTC-01:00", "Atlantic/Cape_Verde", "Praia"),
        ("UTC+00:00", "UTC", "UTC"),
        ("UTC+01:00", "Africa/Lagos", "Lagos"),
        ("UTC+02:00", "Africa/Johannesburg", "Johannesburg"),
        ("UTC+03:00", "Europe/Moscow", "Moscow"),
        ("UTC+03:30", "Asia/Tehran", "Tehran"),
        ("UTC+04:00", "Asia/Dubai", "Dubai"),
        ("UTC+04:30", "Asia/Kabul", "Kabul"),
        ("UTC+05:00", "Asia/Karachi", "Karachi"),
        ("UTC+05:30", "Asia/Kolkata", "Kolkata"),
        ("UTC+05:45", "Asia/Kathmandu", "Kathmandu"),
        ("UTC+06:00", "Asia/Dhaka", "Dhaka"),
        ("UTC+06:30", "Asia/Yangon", "Yangon"),
        ("UTC+07:00", "Asia/Bangkok", "Bangkok"),
        ("UTC+08:00", "Asia/Taipei", "Taipei"),
        ("UTC+08:45", "Australia/Eucla", "Eucla"),
        ("UTC+09:00", "Asia/Tokyo", "Tokyo"),
        ("UTC+09:30", "Australia/Darwin", "Darwin"),
        ("UTC+10:00", "Pacific/Port_Moresby", "Port Moresby"),
        ("UTC+10:30", "Australia/Lord_Howe", "Lord Howe Island"),
        ("UTC+11:00", "Pacific/Noumea", "Noumea"),
        ("UTC+12:00", "Pacific/Fiji", "Suva"),
        ("UTC+12:45", "Pacific/Chatham", "Chatham Islands"),
        ("UTC+13:00", "Pacific/Apia", "Apia"),
        ("UTC+14:00", "Pacific/Kiritimati", "Kiritimati"),
    ]
    print("Select timezone:")
    for idx, (offset, zone, city) in enumerate(representatives, start=1):
        marker = " [system]" if zone == default else ""
        print(f"{idx}. {offset} · {city} ({zone}){marker}")
    print(f"{len(representatives)+1}. Use detected system timezone ({default})")
    print(f"{len(representatives)+2}. Enter another IANA timezone")
    raw = input("Choice: ").strip()
    if not raw:
        return default
    try:
        selected = int(raw)
    except ValueError as exc:
        raise RuntimeError("Invalid timezone selection.") from exc
    if selected == len(representatives) + 1:
        return default
    if selected == len(representatives) + 2:
        custom = input("IANA timezone: ").strip()
        ZoneInfo(custom)
        return custom
    if not 1 <= selected <= len(representatives):
        raise RuntimeError("Invalid timezone selection.")
    return representatives[selected - 1][1]


def effective_policy(username: str) -> dict[str, Any]:
    config = load_config()
    policies = load_policies()
    override = policies["creators"].get(username, {})
    return deep_merge(config["defaults"], override)


def ensure_policy(username: str) -> tuple[dict[str, Any], dict[str, Any]]:
    policies = load_policies()
    policies["creators"].setdefault(username, {})
    return policies, effective_policy(username)


def ui_locale(non_interactive: bool = False) -> str:
    config = load_config()
    value = config.get("ui_locale")
    if value in LOCALES:
        return value
    return "en" if non_interactive else "en"


def msg(key: str, locale: str) -> str:
    return MESSAGES.get(locale, MESSAGES["en"]).get(key, MESSAGES["en"].get(key, key))


def emit(payload: dict[str, Any], output: str) -> None:
    payload = {"schema_version": 1, "timestamp": iso_now(), **payload}
    if output == "ndjson":
        print(json.dumps(payload, ensure_ascii=False, sort_keys=True), flush=True)


def emit_cli_event(*, event: str, section: str, status: str, message: str, data: dict[str, Any], output: str) -> None:
    emit(
        cli_result(
            event=event,
            section=section,
            status=status,
            message=message,
            data=data,
        ),
        output,
    )


def parse_iso(value: str | None) -> datetime | None:
    if not value:
        return None
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def resolve_boundary(value: str | None, zone_name: str, is_until: bool) -> str | None:
    if not value:
        return None
    zone = ZoneInfo(zone_name)
    text = value.strip()
    try:
        if re.fullmatch(r"\d{4}-\d{2}-\d{2}", text):
            day = date.fromisoformat(text)
            local = datetime.combine(
                day,
                dt_time.max if is_until else dt_time.min,
                tzinfo=zone,
            )
        else:
            local = datetime.fromisoformat(text)
            if local.tzinfo is None:
                local = local.replace(tzinfo=zone)
        return local.astimezone(timezone.utc).isoformat(timespec="seconds")
    except ValueError as exc:
        raise RuntimeError(f"Invalid date/time: {value}") from exc


def fmt_seconds(seconds: float | None) -> str:
    if seconds is None or math.isinf(seconds) or math.isnan(seconds):
        return "-"
    seconds = max(0, int(round(seconds)))
    hours, rem = divmod(seconds, 3600)
    minutes, secs = divmod(rem, 60)
    return f"{hours:02d}:{minutes:02d}:{secs:02d}"


class EtaEstimator:
    def __init__(self, initial_samples: list[float] | None = None) -> None:
        self.last_at: float | None = None
        self.samples: list[float] = [
            float(value)
            for value in (initial_samples or [])[-20:]
            if 0 < float(value) < 7200
        ]
        self.ewma: float | None = (
            statistics.median(self.samples) if self.samples else None
        )

    def observe(self, current: int) -> float | None:
        now = time.monotonic()
        if current <= 0:
            self.last_at = now
            return None
        if self.last_at is not None:
            sample = now - self.last_at
            if 0 < sample < 7200:
                self.samples.append(sample)
                self.samples = self.samples[-20:]
                self.ewma = sample if self.ewma is None else 0.3 * sample + 0.7 * self.ewma
        self.last_at = now
        return self.seconds_per_item()

    def seconds_per_item(self) -> float | None:
        if not self.samples:
            return None
        median = statistics.median(self.samples)
        return median if self.ewma is None else (median + self.ewma) / 2

    def confidence(self) -> str:
        count = len(self.samples)
        if count < 3:
            return "calculating"
        if count < 10:
            return "low"
        if count < 30:
            return "medium"
        return "high"


def engine_command(*parts: str) -> list[str]:
    return [sys.executable, str(ENGINE), *parts]


def stream_engine(
    command: list[str],
    *,
    output: str,
    locale: str,
    batch_number: int | None = None,
    batch_count: int | None = None,
    account_remaining_start: int | None = None,
    estimator: EtaEstimator | None = None,
) -> tuple[int, dict[str, Any]]:
    RUN_DIR.mkdir(parents=True, exist_ok=True)
    log_path = RUN_DIR / f"{run_id()}-social2md-engine.log"
    process = subprocess.Popen(
        command,
        cwd=ROOT,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
        start_new_session=True,
    )
    assert process.stdout is not None
    estimator = estimator or EtaEstimator()
    summary: dict[str, Any] = {"log": str(log_path), "errors": [], "interrupted": False}
    block: str | None = None
    try:
        with log_path.open("w", encoding="utf-8") as log:
            for raw in process.stdout:
                log.write(raw)
                log.flush()
                line = raw.rstrip("\n")
                if line in {"CREATOR_BATCH_RESULT", "CREATOR_BULK_STATUS", "CREATOR_SYNC_RESULT", "CREATOR_QUICK_SYNC_RESULT"}:
                    block = line
                    continue
                if line.startswith("ERROR:"):
                    summary["errors"].append(line[6:].strip())
                if "=" in line and block:
                    key, value = line.split("=", 1)
                    if re.fullmatch(r"[A-Za-z0-9_]+", key):
                        summary[key] = value
                if line.startswith("AGENT_PROGRESS "):
                    try:
                        event = json.loads(line[len("AGENT_PROGRESS "):])
                    except json.JSONDecodeError:
                        continue
                    phase = event.get("phase")
                    if event.get("error"):
                        summary.setdefault("errors", []).append(
                            f"{event.get('shortcode') or '-'}: {str(event.get('error'))[-2000:]}"
                        )
                    if phase == "process":
                        current = int(event.get("current") or 0)
                        total = int(event.get("total") or 0)
                        seconds_per_item = estimator.observe(current)
                        batch_eta = (total - current) * seconds_per_item if seconds_per_item is not None else None
                        account_remaining = event.get("account_remaining")
                        total_eta = (
                            float(account_remaining) * seconds_per_item
                            if seconds_per_item is not None and account_remaining is not None
                            else None
                        )
                        enriched = {
                            "phase": "process",
                            "batch_number": batch_number,
                            "batch_count": batch_count,
                            "current": current,
                            "total": total,
                            "percent": event.get("percent"),
                            "completed": event.get("completed"),
                            "failed": event.get("failed"),
                            "shortcode": event.get("shortcode"),
                            "status": event.get("status"),
                            "account_completed": event.get("account_completed"),
                            "account_total": event.get("account_total"),
                            "account_percent": event.get("account_percent"),
                            "account_remaining": account_remaining,
                            "account_total_exact": event.get("account_total_exact"),
                            "seconds_per_item": round(seconds_per_item, 2) if seconds_per_item is not None else None,
                            "batch_eta_seconds": round(batch_eta) if batch_eta is not None else None,
                            "total_eta_seconds": round(total_eta) if total_eta is not None else None,
                            "eta_confidence": estimator.confidence(),
                        }
                        emit_cli_event(
                            event="progress",
                            section="progress",
                            status="ok",
                            message="Instagram processing progress update",
                            data=enriched,
                            output=output,
                        )
                        if output == "human":
                            prefix = ""
                            if batch_number is not None and batch_count is not None:
                                prefix = f"{msg('batch', locale)} {batch_number}/{batch_count} · "
                            eta_text = fmt_seconds(batch_eta) if batch_eta is not None else msg("calculating", locale)
                            text = (
                                f"{prefix}{msg('progress', locale)} {current}/{total} "
                                f"({float(event.get('percent') or 0):.1f}%) · "
                                f"completed={int(event.get('completed') or 0)} "
                                f"failed={int(event.get('failed') or 0)} · "
                                f"{msg('batch_eta', locale)} {eta_text}"
                            )
                            if batch_count and batch_count > 1:
                                total_eta_text = fmt_seconds(total_eta) if total_eta is not None else msg("calculating", locale)
                                text += f" · {msg('total_eta', locale)} {total_eta_text}"
                            print(text, flush=True)
                            if event.get("status") and event.get("status") != "completed":
                                print(
                                    f"ITEM_RESULT shortcode={event.get('shortcode') or '-'} "
                                    f"status={event.get('status')} "
                                    f"error={str(event.get('error') or '-')[-800:]}",
                                    file=sys.stderr,
                                    flush=True,
                                )
                    elif phase in {"sync", "sync_complete", "quick_sync"}:
                        emit_cli_event(
                            event="progress",
                            section="progress",
                            status="ok",
                            message="Instagram sync progress update",
                            data=event,
                            output=output,
                        )
                        if output == "human" and phase == "sync":
                            page = event.get("page")
                            current = event.get("current")
                            if page:
                                print(f"{msg('sync_page', locale)} {page} · discovered={current}", flush=True)
    except KeyboardInterrupt:
        summary["interrupted"] = True
        summary["interrupt_at"] = iso_now()
        try:
            os.killpg(process.pid, signal.SIGINT)
        except (ProcessLookupError, PermissionError):
            pass
        try:
            process.wait(timeout=20)
        except subprocess.TimeoutExpired:
            try:
                os.killpg(process.pid, signal.SIGTERM)
            except (ProcessLookupError, PermissionError):
                pass
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                try:
                    os.killpg(process.pid, signal.SIGKILL)
                except (ProcessLookupError, PermissionError):
                    pass
                process.wait()
        summary["return_code"] = 130
        return 130, summary
    return_code = process.wait()
    summary["return_code"] = return_code
    return return_code, summary


def sync_once(username: str, policy: dict[str, Any], output: str, locale: str, force_full: bool = False) -> tuple[int, dict[str, Any]]:
    args = [
        "status",
        username,
        "--full-sync-interval-minutes",
        str(policy["sync"]["full_every_minutes"]),
        "--quick-sync-size",
        str(policy["sync"]["quick_window"]),
    ]
    if force_full:
        args.append("--force-full-sync")
    return stream_engine(engine_command(*args), output=output, locale=locale)


def catalog_path(username: str) -> Path:
    return CATALOG_DIR / f"{username}.json"


def filtered_candidate_count(
    username: str,
    *,
    since: str | None,
    until: str | None,
    rank_from: int | None,
    rank_to: int | None,
    oldest_first: bool,
    retry_failed: bool,
) -> int:
    catalog = load_json(catalog_path(username), {"items": []})
    items = list(catalog.get("items", []))
    items.sort(
        key=lambda item: (parse_iso(item.get("published_at")) or datetime.min.replace(tzinfo=timezone.utc), item.get("shortcode", "")),
        reverse=not oldest_first,
    )
    since_dt = parse_iso(since)
    until_dt = parse_iso(until)
    filtered = []
    for item in items:
        published = parse_iso(item.get("published_at"))
        if published is None:
            continue
        if since_dt and published < since_dt:
            continue
        if until_dt and published > until_dt:
            continue
        filtered.append(item)
    start = rank_from - 1 if rank_from else 0
    stop = rank_to if rank_to else None
    filtered = filtered[start:stop]
    if not DB_PATH.is_file():
        return len(filtered)
    connection = sqlite3.connect(DB_PATH)
    connection.row_factory = sqlite3.Row
    try:
        creator = connection.execute("SELECT id FROM creators WHERE username = ? COLLATE NOCASE", (username,)).fetchone()
        rows = {}
        if creator:
            rows = {
                row["shortcode"]: row["status"]
                for row in connection.execute("SELECT shortcode, status FROM videos WHERE creator_id = ?", (creator["id"],))
            }
    finally:
        connection.close()
    count = 0
    for item in filtered:
        status = rows.get(item.get("shortcode"))
        if status is None or status == "pending":
            count += 1
        elif status in {"retry_wait", "failed"} and retry_failed:
            count += 1
    return count


def load_performance_samples(username: str) -> list[float]:
    payload = load_json(PERFORMANCE_PATH, {"schema_version": 1, "creators": {}})
    values = payload.get("creators", {}).get(username, {}).get("seconds_per_item", [])
    return [float(value) for value in values if isinstance(value, (int, float))]


def save_performance_samples(username: str, samples: list[float]) -> None:
    payload = load_json(PERFORMANCE_PATH, {"schema_version": 1, "creators": {}})
    payload.setdefault("schema_version", 1)
    payload.setdefault("creators", {})
    payload["creators"][username] = {
        "seconds_per_item": [round(float(value), 3) for value in samples[-100:]],
        "updated_at": iso_now(),
    }
    atomic_json(PERFORMANCE_PATH, payload)


def run_creator(args: argparse.Namespace) -> int:
    username = normalize_creator(args.creator)
    config = load_config()
    policy = effective_policy(username)
    locale = ui_locale(args.non_interactive)
    output = args.output
    timezone_name = config["timezone"]
    mode = args.mode or policy["processing"]["mode"]
    batch_size = args.batch_size or int(policy["processing"]["batch_size"])
    since_local = args.since if args.since is not None else policy["filters"].get("since")
    until_local = args.until if args.until is not None else policy["filters"].get("until")
    since = resolve_boundary(since_local, timezone_name, False)
    until = resolve_boundary(until_local, timezone_name, True)
    rank_from = args.rank_from if args.rank_from is not None else policy["filters"].get("rank_from")
    rank_to = args.rank_to if args.rank_to is not None else policy["filters"].get("rank_to")
    order = args.order or policy["filters"].get("order", "newest_first")
    oldest_first = order == "oldest_first"
    max_batches = args.max_batches if args.max_batches is not None else int(policy["processing"].get("max_batches", 0))
    max_runtime = args.max_runtime_minutes if args.max_runtime_minutes is not None else float(policy["processing"].get("max_runtime_minutes", 360))
    max_failures = args.max_failures if args.max_failures is not None else int(policy["processing"].get("max_failures", 10))
    stop_on_failure = args.stop_on_failure or bool(policy["processing"].get("stop_on_failure", False))
    sleep_between = args.sleep_between_batches if args.sleep_between_batches is not None else float(policy["processing"].get("sleep_between_batches", 5))

    if not getattr(args, "skip_sync", False):
        sync_code, _ = sync_once(username, policy, output, locale, force_full=args.force_full_sync)
        if sync_code != 0:
            return sync_code

    remaining = filtered_candidate_count(
        username,
        since=since,
        until=until,
        rank_from=rank_from,
        rank_to=rank_to,
        oldest_first=oldest_first,
        retry_failed=args.retry_failed,
    )
    if remaining <= 0:
        emit_cli_event(
            event="run_completed",
            section="run",
            status="ok",
            message="Instagram creator run completed with no remaining work",
            data={"creator": username, "status": "no_work", "remaining": 0},
            output=output,
        )
        if output == "human": print(msg("no_work", locale))
        return 0

    planned_batches = 1 if mode == "batch" else math.ceil(remaining / batch_size)
    if max_batches and mode == "drain":
        planned_batches = min(planned_batches, max_batches)
    started = time.monotonic()
    run_estimator = EtaEstimator(load_performance_samples(username))
    total_failed = 0
    total_completed = 0
    batches_run = 0
    last_summary: dict[str, Any] = {}
    emit_cli_event(
        event="run_started",
        section="run",
        status="ok",
        message="Instagram creator run started",
        data={
            "creator": username,
            "mode": mode,
            "batch_size": batch_size,
            "eligible_remaining": remaining,
            "planned_batches": planned_batches,
            "timezone": timezone_name,
            "filters": {"since": since_local, "until": until_local, "rank_from": rank_from, "rank_to": rank_to, "order": order},
        },
        output=output,
    )

    while remaining > 0:
        if mode == "batch" and batches_run >= 1:
            break
        if max_batches and batches_run >= max_batches:
            break
        if max_runtime > 0 and (time.monotonic() - started) / 60 >= max_runtime:
            break
        batches_run += 1
        current_batch_size = min(batch_size, remaining)
        command = [
            "run",
            username,
            "--batch-size", str(current_batch_size),
            "--no-auto-sync",
            "--pause-seconds", str(args.pause_seconds),
            "--max-failures", str(max_failures),
        ]
        if oldest_first: command.append("--oldest-first")
        if args.retry_failed: command.append("--retry-failed")
        if since: command += ["--since", since]
        if until: command += ["--until", until]
        if rank_from is not None: command += ["--rank-from", str(rank_from)]
        if rank_to is not None: command += ["--rank-to", str(rank_to)]
        code, summary = stream_engine(
            engine_command(*command),
            output=output,
            locale=locale,
            batch_number=batches_run,
            batch_count=planned_batches,
            account_remaining_start=remaining,
            estimator=run_estimator,
        )
        last_summary = summary
        if code == 130 or summary.get("interrupted"):
            remaining = filtered_candidate_count(
                username,
                since=since,
                until=until,
                rank_from=rank_from,
                rank_to=rank_to,
                oldest_first=oldest_first,
                retry_failed=args.retry_failed,
            )
            save_performance_samples(username, run_estimator.samples)
            emit_cli_event(
                event="run_interrupted",
                section="run",
                status="warn",
                message="Instagram creator run was interrupted safely",
                data={
                    "creator": username,
                    "mode": mode,
                    "batch_number": batches_run,
                    "batch_count": planned_batches,
                    "remaining": remaining,
                    "resume_supported": True,
                    "exit_code": 130,
                    "engine_log": summary.get("log"),
                },
                output=output,
            )
            if output == "human":
                print(msg("interrupted", locale))
                print(f"remaining={remaining}")
                print("resume_supported=true")
            return 130
        try:
            failed = int(summary.get("failed", 0))
        except (TypeError, ValueError):
            failed = 1 if code else 0
        completed = int(summary.get("completed", 0) or 0)
        total_completed += completed
        total_failed += failed
        remaining = filtered_candidate_count(
            username,
            since=since,
            until=until,
            rank_from=rank_from,
            rank_to=rank_to,
            oldest_first=oldest_first,
            retry_failed=args.retry_failed,
        )
        emit_cli_event(
            event="batch_completed",
            section="batch",
            status="warn" if failed else "ok",
            message="Instagram batch completed",
            data={
                "creator": username,
                "batch_number": batches_run,
                "batch_count": planned_batches,
                "return_code": code,
                "completed": completed,
                "failed": failed,
                "remaining": remaining,
                "report": summary.get("report"),
                "engine_log": summary.get("log"),
            },
            output=output,
        )
        if code not in {0, 2}:
            break
        if failed and stop_on_failure:
            break
        if max_failures > 0 and total_failed >= max_failures:
            break
        if mode == "batch" or remaining <= 0:
            break
        if sleep_between > 0:
            time.sleep(sleep_between)

    save_performance_samples(username, run_estimator.samples)
    stopped = remaining > 0 and (mode == "drain" or batches_run == 0)
    emit_cli_event(
        event="run_completed",
        section="run",
        status="warn" if total_failed else "ok",
        message="Instagram creator run finished",
        data={
            "creator": username,
            "mode": mode,
            "batches_run": batches_run,
            "failed": total_failed,
            "remaining": remaining,
            "status": "stopped" if stopped else "completed",
            "elapsed_seconds": round(time.monotonic() - started, 1),
        },
        output=output,
    )
    if output == "human":
        if stopped:
            print(msg("stopped", locale))
        status = "completed" if total_failed == 0 else "completed_with_errors"
        print(
            f"CREATOR_RUN_COMPLETED provider=instagram creator={username} "
            f"status={status} batches={batches_run} processed={total_completed + total_failed} "
            f"completed={total_completed} failures={total_failed} remaining={remaining}"
        )
        if last_summary.get("report"):
            print(f"report={last_summary['report']}")
        if last_summary.get("log"):
            print(f"engine_log={last_summary['log']}")
        if total_failed:
            examples = list(last_summary.get("errors") or [])[:3]
            for example in examples:
                print(f"failure_example={str(example).replace(chr(10), ' ')[-1200:]}")
            validated_required_action = validate_required_action("inspect_instagram_failure_report")
            print(f"required_action={validated_required_action}")  # required_action=inspect_instagram_failure_report
    return 0 if total_failed == 0 else 2



def provider_from_url(url: str) -> str:
    host = url.lower()
    if "instagram.com/" in host:
        return "instagram"
    if "youtube.com/" in host or "youtu.be/" in host:
        return "youtube"
    if "tiktok.com/" in host:
        return "tiktok"
    raise RuntimeError("Unsupported URL. Supported providers: Instagram, YouTube, TikTok.")


def provider_status() -> list[dict[str, Any]]:
    return [
        {
            "provider": "instagram",
            "installed": bool(command_path("gallery-dl")),
            "creator_sync": True,
            "single_media": True,
            "required_extra": "instagram",
        },
        {
            "provider": "youtube",
            "installed": bool(command_path("yt-dlp")),
            "creator_sync": True,
            "single_media": True,
            "required_extra": "youtube",
        },
        {
            "provider": "tiktok",
            "installed": bool(command_path("yt-dlp")),
            "creator_sync": True,
            "single_media": True,
            "required_extra": "tiktok",
        },
    ]


def providers_list(args: argparse.Namespace) -> int:
    rows = provider_status()
    if args.output == "ndjson":
        for row in rows:
            emit_cli_event(
                event="provider",
                section="provider",
                status="ok" if row.get("installed") else "warn",
                message="Provider capability row",
                data=row,
                output=args.output,
            )
        emit_cli_event(
            event="provider_list_completed",
            section="provider",
            status="ok",
            message="Provider capability listing completed",
            data={"count": len(rows)},
            output=args.output,
        )
        return 0
    print("PROVIDER   INSTALLED  CREATOR_SYNC  SINGLE_MEDIA  EXTRA")
    for row in rows:
        print(
            f"{row['provider']:<10} "
            f"{str(row['installed']).lower():<10} "
            f"{str(row['creator_sync']).lower():<13} "
            f"{str(row['single_media']).lower():<13} "
            f"{row['required_extra']}"
        )
    return 0


def generic_media_command(*parts: str) -> list[str]:
    if not GENERIC_MEDIA.is_file():
        raise RuntimeError(f"Generic media adapter missing: {GENERIC_MEDIA}")
    return [sys.executable, str(GENERIC_MEDIA), *parts]


def run_generic_media(args: argparse.Namespace) -> int:
    provider = provider_from_url(args.url) if hasattr(args, "url") else None
    if provider == "instagram" and args.media_command == "add":
        command = [
            sys.executable,
            str(ROOT / "scripts" / "manage_videos.py"),
            "add",
            "--url",
            args.url,
        ]
        if args.process_now:
            command.append("--process-now")
    else:
        command = generic_media_command(args.media_command)
        if hasattr(args, "url"):
            command.append(args.url)
        if getattr(args, "process_now", False):
            command.append("--process-now")
        if getattr(args, "provider", None):
            command += ["--provider", args.provider]
        if getattr(args, "status", None):
            command += ["--status", args.status]
        command += ["--output", args.output]
    result = subprocess.run(command, cwd=ROOT, check=False)
    return result.returncode


def version_command(args: argparse.Namespace) -> int:
    payload = {"event": "version", "version": VERSION}
    if args.output == "ndjson":
        emit(payload, args.output)
    else:
        print(f"social2md {VERSION}")
    return 0


def version_tuple(value: str) -> tuple[int, ...]:
    match = re.search(r"(\\d+(?:\\.\\d+)+)", value or "")
    return tuple(int(part) for part in match.group(1).split(".")) if match else ()


def update_configure(args: argparse.Namespace) -> int:
    config = load_config()
    updates = config.setdefault("updates", {})
    if args.repository is not None:
        if not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", args.repository):
            raise RuntimeError("--repository must use owner/repository format.")
        updates["repository"] = args.repository
    if args.enabled is not None:
        updates["enabled"] = args.enabled
    if args.every is not None:
        updates["check_every_minutes"] = args.every
    atomic_json(CONFIG_PATH, config)
    print("UPDATE_POLICY_UPDATED")
    print(f"enabled={str(bool(updates.get('enabled'))).lower()}")
    print(f"repository={updates.get('repository') or '-'}")
    print(f"every={duration_text(int(updates.get('check_every_minutes', 1440)))}")
    return 0


def fetch_latest_release(repository: str) -> dict[str, Any]:
    request = urllib.request.Request(
        f"https://api.github.com/repos/{repository}/releases/latest",
        headers={"Accept": "application/vnd.github+json", "User-Agent": f"social2md/{VERSION}"},
    )
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            # A repository without a published Release is a valid project state.
            return {"_not_published": True}
        raise RuntimeError(f"GitHub release check failed: HTTP {exc.code}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"GitHub release check failed: {exc.reason}") from exc


def update_check(args: argparse.Namespace) -> int:
    config = load_config()
    updates = config.get("updates", {})
    repository = args.repository or updates.get("repository")
    if not repository:
        raise RuntimeError("No update repository configured. Use update configure --repository OWNER/REPO.")
    release = fetch_latest_release(repository)
    latest = str(release.get("tag_name") or release.get("name") or "")
    available = bool(version_tuple(latest) and version_tuple(latest) > version_tuple(VERSION))
    payload = {
        "event": "update_unpublished" if release.get("_not_published") else "update_check",
        "repository": repository,
        "current_version": VERSION,
        "latest_version": latest,
        "update_available": available,
        "release_url": release.get("html_url"),
    }
    if args.output == "ndjson":
        emit(payload, args.output)
    else:
        print("UPDATE_CHECK")
        for key in ("repository", "current_version", "latest_version", "update_available", "release_url"):
            print(f"{key}={payload.get(key)}")
    return 0

def creator_list(args: argparse.Namespace) -> int:
    policies = load_policies()["creators"]
    config = load_config()
    default_sync = config["defaults"]["sync"]
    rows: list[sqlite3.Row] = []
    if DB_PATH.is_file():
        connection = sqlite3.connect(DB_PATH)
        connection.row_factory = sqlite3.Row
        try:
            rows = connection.execute("SELECT username, enabled FROM creators ORDER BY lower(username)").fetchall()
        finally:
            connection.close()
    names = {row["username"] for row in rows} | set(policies)
    results = []
    for username in sorted(names, key=str.lower):
        override = policies.get(username, {})
        sync = deep_merge(default_sync, override.get("sync", {}))
        state = "enabled" if sync.get("enabled") else "disabled"
        if args.sync != "all" and state != args.sync:
            continue
        results.append({
            "creator": username,
            "sync": state,
            "sync_every": duration_text(int(sync["every_minutes"])),
            "full_sync_every": duration_text(int(sync["full_every_minutes"])),
            "quick_window": int(sync["quick_window"]),
        })
    if args.output == "ndjson":
        for item in results: emit({"event": "creator", **item}, "ndjson")
        emit({"event": "creator_list_completed", "count": len(results), "filter": args.sync}, "ndjson")
    else:
        print("CREATOR                         SYNC      EVERY  FULL    QUICK")
        for item in results:
            print(f"{item['creator']:<31} {item['sync']:<9} {item['sync_every']:<6} {item['full_sync_every']:<7} {item['quick_window']}")
        print(f"TOTAL={len(results)}")
    return 0


def set_sync(args: argparse.Namespace, enabled: bool) -> int:
    username = normalize_creator(args.creator)
    policies = load_policies()
    entry = policies["creators"].setdefault(username, {})
    sync = entry.setdefault("sync", {})
    sync["enabled"] = enabled
    if args.every is not None: sync["every_minutes"] = args.every
    if args.full_every is not None: sync["full_every_minutes"] = args.full_every
    if args.quick_window is not None: sync["quick_window"] = args.quick_window
    save_policies(policies)
    policy = effective_policy(username)
    print("CREATOR_SYNC_POLICY_UPDATED")
    print(f"creator={username}")
    print(f"sync_enabled={str(enabled).lower()}")
    print(f"sync_every={duration_text(policy['sync']['every_minutes'])}")
    print(f"full_sync_every={duration_text(policy['sync']['full_every_minutes'])}")
    print(f"quick_window={policy['sync']['quick_window']}")
    return 0


def policy_set(args: argparse.Namespace) -> int:
    username = normalize_creator(args.creator)
    policies = load_policies()
    entry = policies["creators"].setdefault(username, {})
    if args.mode is not None: entry.setdefault("processing", {})["mode"] = args.mode
    if args.batch_size is not None: entry.setdefault("processing", {})["batch_size"] = args.batch_size
    if args.max_batches is not None: entry.setdefault("processing", {})["max_batches"] = args.max_batches
    if args.max_runtime_minutes is not None: entry.setdefault("processing", {})["max_runtime_minutes"] = args.max_runtime_minutes
    if args.max_failures is not None: entry.setdefault("processing", {})["max_failures"] = args.max_failures
    if args.stop_on_failure is not None: entry.setdefault("processing", {})["stop_on_failure"] = args.stop_on_failure
    if args.sleep_between_batches is not None: entry.setdefault("processing", {})["sleep_between_batches"] = args.sleep_between_batches
    if args.scheduled_processing is not None: entry.setdefault("processing", {})["scheduled"] = args.scheduled_processing
    if args.processing_every is not None: entry.setdefault("processing", {})["every_minutes"] = args.processing_every
    filters = entry.setdefault("filters", {})
    for key in ("since", "until", "rank_from", "rank_to", "order"):
        value = getattr(args, key)
        if value is not None: filters[key] = value
    save_policies(policies)
    print(json.dumps({"creator": username, "policy": effective_policy(username)}, ensure_ascii=False, indent=2))
    return 0


def policy_show(args: argparse.Namespace) -> int:
    username = normalize_creator(args.creator)
    print(json.dumps({"creator": username, "policy": effective_policy(username)}, ensure_ascii=False, indent=2))
    return 0


def scheduler_state() -> dict[str, Any]:
    payload = load_json(SCHEDULER_STATE_PATH, {"schema_version": 1, "creators": {}})
    payload.setdefault("creators", {})
    return payload


def is_due(last: str | None, every_minutes: int, now: datetime) -> bool:
    parsed = parse_iso(last)
    return parsed is None or now >= parsed + timedelta(minutes=every_minutes)


@contextmanager
def scheduler_lock() -> Iterator[None]:
    SCHEDULER_LOCK.parent.mkdir(parents=True, exist_ok=True)
    with SCHEDULER_LOCK.open("a+", encoding="utf-8") as handle:
        try:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise RuntimeError("Another scheduler tick is already running.") from exc
        try:
            yield
        finally:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def scheduler_tick(args: argparse.Namespace) -> int:
    policies = load_policies()["creators"]
    state = scheduler_state()
    now = now_utc()
    due_creators: list[tuple[str, bool, bool, dict[str, Any]]] = []
    for username in sorted(policies, key=str.lower):
        policy = effective_policy(username)
        creator_state = state["creators"].setdefault(username, {})
        sync = policy["sync"]
        processing = policy["processing"]
        sync_due = bool(
            sync.get("enabled")
            and is_due(
                creator_state.get("last_sync_success_at"),
                int(sync["every_minutes"]),
                now,
            )
        )
        process_due = bool(
            processing.get("scheduled")
            and is_due(
                creator_state.get("last_processing_success_at"),
                int(processing["every_minutes"]),
                now,
            )
        )
        if sync_due or process_due:
            due_creators.append((username, sync_due, process_due, policy))

    due_jobs = sum(int(sync_due) + int(process_due) for _, sync_due, process_due, _ in due_creators)
    emit({"event": "scheduler_tick_started", "due_jobs": due_jobs, "due_creators": len(due_creators)}, args.output)
    failures = 0
    jobs_run = 0

    with scheduler_lock():
        for username, sync_due, process_due, policy in due_creators:
            creator_state = state["creators"].setdefault(username, {})
            sync_succeeded = False

            if sync_due:
                jobs_run += 1
                code, summary = sync_once(username, policy, args.output, "en", force_full=False)
                creator_state["last_sync_attempt_at"] = iso_now()
                if code == 0:
                    creator_state["last_sync_success_at"] = iso_now()
                    creator_state.pop("last_sync_error", None)
                    sync_succeeded = True
                else:
                    failures += 1
                    creator_state["last_sync_error"] = summary.get("errors")
                atomic_json(SCHEDULER_STATE_PATH, state)

            if process_due:
                jobs_run += 1
                run_args = argparse.Namespace(
                    creator=username,
                    non_interactive=True,
                    output=args.output,
                    mode=policy["processing"]["mode"],
                    batch_size=policy["processing"]["batch_size"],
                    since=None,
                    until=None,
                    rank_from=None,
                    rank_to=None,
                    order=None,
                    max_batches=policy["processing"].get("max_batches", 0),
                    max_runtime_minutes=policy["processing"].get("max_runtime_minutes", 360),
                    max_failures=policy["processing"].get("max_failures", 10),
                    stop_on_failure=policy["processing"].get("stop_on_failure", False),
                    sleep_between_batches=policy["processing"].get("sleep_between_batches", 5),
                    retry_failed=False,
                    force_full_sync=False,
                    pause_seconds=1.0,
                    skip_sync=sync_succeeded,
                )
                code = run_creator(run_args)
                creator_state["last_processing_attempt_at"] = iso_now()
                if code == 0:
                    creator_state["last_processing_success_at"] = iso_now()
                    creator_state.pop("last_processing_exit_code", None)
                else:
                    failures += 1
                    creator_state["last_processing_exit_code"] = code
                atomic_json(SCHEDULER_STATE_PATH, state)

    update_event = None
    update_policy = load_config().get("updates", {})
    if update_policy.get("enabled") and update_policy.get("repository"):
        try:
            release = fetch_latest_release(str(update_policy["repository"]))
            latest = str(release.get("tag_name") or release.get("name") or "")
            available = bool(version_tuple(latest) and version_tuple(latest) > version_tuple(VERSION))
            update_event = {
                "event": "update_available" if available else "update_current",
                "repository": update_policy["repository"],
                "current_version": VERSION,
                "latest_version": latest,
                "update_available": available,
                "release_url": release.get("html_url"),
            }
            emit(update_event, args.output)
        except RuntimeError as exc:
            # Update discovery is advisory. Network or GitHub availability must
            # never turn a successful scheduler workload into a failed Cron run.
            emit({"event": "update_check_warning", "error": str(exc), "nonfatal": True}, args.output)
    emit({"event": "scheduler_tick_completed", "jobs_run": jobs_run, "failures": failures}, args.output)
    if args.output == "human":
        print(f"SCHEDULER_TICK_COMPLETED jobs_run={jobs_run} failures={failures}")
    return 0 if failures == 0 else 2

def init_project(args: argparse.Namespace) -> int:
    non_interactive = args.non_interactive
    detected = detect_timezone()
    if args.language:
        language = args.language
    elif non_interactive:
        language = "en"
    else:
        print("Select interface language:")
        print("1. 繁體中文")
        print("2. 简体中文")
        print("3. English")
        print("4. 日本語")
        raw = input("Choice [3]: ").strip() or "3"
        language = {"1":"zh-TW", "2":"zh-CN", "3":"en", "4":"ja"}.get(raw)
        if language is None: raise RuntimeError("Invalid language selection.")
    markdown_language = args.markdown_language or language
    if args.timezone:
        ZoneInfo(args.timezone)
        timezone_name = args.timezone
    elif non_interactive:
        timezone_name = detected
    else:
        timezone_name = select_timezone(detected)
    config = deep_copy(DEFAULT_CONFIG)
    existing = load_json(CONFIG_PATH, {})
    config = deep_merge(config, existing)
    config["ui_locale"] = language
    config["markdown_locale"] = markdown_language
    config["timezone"] = timezone_name
    atomic_json(CONFIG_PATH, config)
    if not POLICY_PATH.exists():
        atomic_json(POLICY_PATH, {"schema_version": 1, "creators": {}})
    print("SOCIAL2MD_INITIALIZED")
    print(f"ui_locale={language}")
    print(f"markdown_locale={markdown_language}")
    print(f"timezone={timezone_name}")
    print(f"timezone_display={offset_label(timezone_name)}")
    print(msg("init_done", language))
    return 0


def openclaw_install(args: argparse.Namespace) -> int:
    config = load_config()
    timezone_name = args.timezone or config["timezone"]
    ZoneInfo(timezone_name)
    target = Path.home() / ".openclaw" / "skills" / "media2md"
    target.mkdir(parents=True, exist_ok=True)
    source = OPENCLAW_SKILL_SOURCE
    if not source.is_file():
        raise RuntimeError(f"OpenClaw skill source missing: {source}")
    shutil.copy2(source, target / "SKILL.md")
    prompt = (
        "Use the Media2MD skill. Run this exact command with the shell tool: "
        f"cd {ROOT} && ./bin/media2md scheduler tick "
        "--output ndjson --non-interactive. Read the NDJSON events. "
        "Report a concise English summary only when work ran or an error occurred. "
        "Do not change creator policies unless the user explicitly requests it."
    )
    command = [
        "openclaw", "cron", "add",
        "--name", args.name,
        "--cron", args.cron,
        "--tz", timezone_name,
        "--session", "isolated",
        "--message", prompt,
    ]
    if args.announce:
        if not args.channel or not args.to:
            raise RuntimeError("--announce requires both --channel and --to.")
        command += ["--announce", "--channel", args.channel, "--to", args.to]
    else:
        # Isolated OpenClaw Cron jobs otherwise default to announcement delivery.
        # A local scheduler must not fail merely because no chat recipient exists.
        command += ["--no-deliver"]
    if args.agent:
        command += ["--agent", args.agent]
    print(f"skill={target / 'SKILL.md'}")
    print("cron_command=" + " ".join(json.dumps(part) for part in command))
    if args.dry_run:
        print("OPENCLAW_INSTALL_DRY_RUN")
        return 0
    executable = shutil.which("openclaw")
    if not executable:
        print("OPENCLAW_SKILL_INSTALLED_CRON_NOT_CREATED")
        print("reason=openclaw_not_found")
        return 2
    command[0] = executable
    existing = subprocess.run(
        [executable, "cron", "list"],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    if existing.returncode == 0 and args.name in existing.stdout and not args.allow_duplicate:
        print("OPENCLAW_SKILL_INSTALLED")
        print("OPENCLAW_CRON_ALREADY_EXISTS")
        print(f"name={args.name}")
        return 0
    result = subprocess.run(command, cwd=ROOT, text=True, capture_output=True, check=False)
    if result.stdout: print(result.stdout.rstrip())
    if result.stderr: print(result.stderr.rstrip(), file=sys.stderr)
    if result.returncode != 0:
        return result.returncode
    print("OPENCLAW_INTEGRATION_INSTALLED")
    return 0


def openclaw_status(args: argparse.Namespace) -> int:
    executable = shutil.which("openclaw")
    skill = Path.home() / ".openclaw" / "skills" / "media2md" / "SKILL.md"
    print(f"skill_installed={str(skill.is_file()).lower()}")
    if not executable:
        print("openclaw_available=false")
        return 2
    print("openclaw_available=true")
    for command in ([executable, "skills", "check", "--json"], [executable, "cron", "list"]):
        result = subprocess.run(command, text=True, capture_output=True, check=False)
        print(f"COMMAND {' '.join(command[1:])}")
        if result.stdout: print(result.stdout.rstrip())
        if result.stderr: print(result.stderr.rstrip(), file=sys.stderr)
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="media2md", description="Production CLI for social-video-to-Markdown workflows.")
    commands = parser.add_subparsers(dest="command", required=True)

    init = commands.add_parser("init")
    init.add_argument("--language", choices=LOCALES)
    init.add_argument("--markdown-language", choices=LOCALES)
    init.add_argument("--timezone")
    init.add_argument("--non-interactive", action="store_true")
    init.set_defaults(function=init_project)

    version = commands.add_parser("version")
    version.add_argument("--output", choices=("human", "ndjson"), default="human")
    version.set_defaults(function=version_command)

    providers = commands.add_parser("providers")
    providers_commands = providers.add_subparsers(dest="providers_command", required=True)
    providers_list_cmd = providers_commands.add_parser("list")
    providers_list_cmd.add_argument("--output", choices=("human", "ndjson"), default="human")
    providers_list_cmd.set_defaults(function=providers_list)

    media = commands.add_parser("media")
    media_commands = media.add_subparsers(dest="media_command", required=True)
    media_inspect = media_commands.add_parser("inspect")
    media_inspect.add_argument("url")
    media_inspect.add_argument("--output", choices=("human", "ndjson"), default="human")
    media_inspect.set_defaults(function=run_generic_media)
    media_add = media_commands.add_parser("add")
    media_add.add_argument("url")
    media_add.add_argument("--process-now", action="store_true")
    media_add.add_argument("--output", choices=("human", "ndjson"), default="human")
    media_add.set_defaults(function=run_generic_media)
    media_list = media_commands.add_parser("list")
    media_list.add_argument("--provider", choices=("youtube", "tiktok"))
    media_list.add_argument("--status")
    media_list.add_argument("--output", choices=("human", "ndjson"), default="human")
    media_list.set_defaults(function=run_generic_media)

    update = commands.add_parser("update")
    update_commands = update.add_subparsers(dest="update_command", required=True)
    update_config = update_commands.add_parser("configure")
    update_config.add_argument("--repository")
    update_toggle = update_config.add_mutually_exclusive_group()
    update_toggle.add_argument("--enable", dest="enabled", action="store_true")
    update_toggle.add_argument("--disable", dest="enabled", action="store_false")
    update_config.set_defaults(enabled=None)
    update_config.add_argument("--every", type=parse_duration)
    update_config.set_defaults(function=update_configure)
    update_check_cmd = update_commands.add_parser("check")
    update_check_cmd.add_argument("--repository")
    update_check_cmd.add_argument("--output", choices=("human", "ndjson"), default="human")
    update_check_cmd.set_defaults(function=update_check)

    creator = commands.add_parser("creator")
    creator_commands = creator.add_subparsers(dest="creator_command", required=True)

    listing = creator_commands.add_parser("list")
    listing.add_argument("--sync", choices=("all", "enabled", "disabled"), default="all")
    listing.add_argument("--output", choices=("human", "ndjson"), default="human")
    listing.set_defaults(function=creator_list)

    for name, enabled in (("sync-enable", True), ("sync-disable", False)):
        command = creator_commands.add_parser(name)
        command.add_argument("creator")
        command.add_argument("--every", type=parse_duration)
        command.add_argument("--full-every", type=parse_duration)
        command.add_argument("--quick-window", type=int)
        command.set_defaults(function=lambda args, enabled=enabled: set_sync(args, enabled))

    policy = creator_commands.add_parser("policy")
    policy_commands = policy.add_subparsers(dest="policy_command", required=True)
    show = policy_commands.add_parser("show")
    show.add_argument("creator")
    show.set_defaults(function=policy_show)
    setp = policy_commands.add_parser("set")
    setp.add_argument("creator")
    setp.add_argument("--mode", choices=("batch", "drain"))
    setp.add_argument("--batch-size", type=int)
    setp.add_argument("--max-batches", type=int)
    setp.add_argument("--max-runtime-minutes", type=float)
    setp.add_argument("--max-failures", type=int)
    stop = setp.add_mutually_exclusive_group()
    stop.add_argument("--stop-on-failure", dest="stop_on_failure", action="store_true")
    stop.add_argument("--continue-on-failure", dest="stop_on_failure", action="store_false")
    setp.set_defaults(stop_on_failure=None)
    setp.add_argument("--sleep-between-batches", type=float)
    sched = setp.add_mutually_exclusive_group()
    sched.add_argument("--schedule-processing", dest="scheduled_processing", action="store_true")
    sched.add_argument("--no-schedule-processing", dest="scheduled_processing", action="store_false")
    setp.set_defaults(scheduled_processing=None)
    setp.add_argument("--processing-every", type=parse_duration)
    setp.add_argument("--since")
    setp.add_argument("--until")
    setp.add_argument("--rank-from", type=int)
    setp.add_argument("--rank-to", type=int)
    setp.add_argument("--order", choices=("newest_first", "oldest_first"))
    setp.set_defaults(function=policy_set)

    run = creator_commands.add_parser("run")
    run.add_argument("creator")
    run.add_argument("--mode", choices=("batch", "drain"))
    run.add_argument("--batch-size", type=int)
    run.add_argument("--since")
    run.add_argument("--until")
    run.add_argument("--rank-from", type=int)
    run.add_argument("--rank-to", type=int)
    run.add_argument("--order", choices=("newest_first", "oldest_first"))
    run.add_argument("--max-batches", type=int)
    run.add_argument("--max-runtime-minutes", type=float)
    run.add_argument("--max-failures", type=int)
    run.add_argument("--stop-on-failure", action="store_true")
    run.add_argument("--sleep-between-batches", type=float)
    run.add_argument("--retry-failed", action="store_true")
    run.add_argument("--force-full-sync", action="store_true")
    run.add_argument("--pause-seconds", type=float, default=1.0)
    run.add_argument("--output", choices=("human", "ndjson"), default="human")
    run.add_argument("--non-interactive", action="store_true")
    run.set_defaults(function=run_creator)

    scheduler = commands.add_parser("scheduler")
    scheduler_commands = scheduler.add_subparsers(dest="scheduler_command", required=True)
    tick = scheduler_commands.add_parser("tick")
    tick.add_argument("--output", choices=("human", "ndjson"), default="human")
    tick.add_argument("--non-interactive", action="store_true")
    tick.set_defaults(function=scheduler_tick)

    openclaw = commands.add_parser("openclaw")
    openclaw_commands = openclaw.add_subparsers(dest="openclaw_command", required=True)
    install = openclaw_commands.add_parser("install")
    install.add_argument("--cron", default="0 * * * *")
    install.add_argument("--timezone")
    install.add_argument("--agent")
    install.add_argument("--name", default="Media2MD scheduler")
    install.add_argument("--dry-run", action="store_true")
    install.add_argument("--allow-duplicate", action="store_true")
    install.add_argument("--announce", action="store_true", help="Deliver Cron summaries to an explicit recipient.")
    install.add_argument("--channel", help="OpenClaw delivery channel used with --announce.")
    install.add_argument("--to", help="OpenClaw delivery recipient used with --announce.")
    install.set_defaults(function=openclaw_install)
    status = openclaw_commands.add_parser("status")
    status.set_defaults(function=openclaw_status)

    return parser


def validate_args(args: argparse.Namespace) -> None:
    if hasattr(args, "batch_size") and args.batch_size is not None and not 1 <= args.batch_size <= 500:
        raise RuntimeError("--batch-size must be between 1 and 500.")
    if hasattr(args, "quick_window") and args.quick_window is not None and not 1 <= args.quick_window <= 500:
        raise RuntimeError("--quick-window must be between 1 and 500.")
    for name in ("rank_from", "rank_to"):
        value = getattr(args, name, None)
        if value is not None and value < 1:
            raise RuntimeError(f"--{name.replace('_','-')} must be 1 or greater.")
    if getattr(args, "rank_from", None) and getattr(args, "rank_to", None) and args.rank_from > args.rank_to:
        raise RuntimeError("--rank-from cannot exceed --rank-to.")


def main() -> int:
    args = build_parser().parse_args()
    validate_args(args)
    return args.function(args)


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        print("RUN_INTERRUPTED", file=sys.stderr)
        raise SystemExit(130)
    except (RuntimeError, OSError, sqlite3.Error, subprocess.SubprocessError, ZoneInfoNotFoundError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise SystemExit(1)
