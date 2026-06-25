#!/usr/bin/env python3
from __future__ import annotations

import argparse
import fcntl
import json
import os
import re
import sqlite3
import subprocess
import sys
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
LOG_DIR = ROOT / "logs"
RUN_LOG_DIR = LOG_DIR / "runs"
LOCK_PATH = LOG_DIR / "pipeline.lock"
DB_PATH = ROOT / "data" / "state.db"
DEFAULT_COOKIE_FILE = ROOT / "data" / "secrets" / "instagram-cookies.txt"

REPORT_LINE = re.compile(r"^report=(.+)$", re.MULTILINE)


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def iso_now() -> str:
    return utc_now().isoformat(timespec="seconds")


@contextmanager
def pipeline_lock():
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    with LOCK_PATH.open("a+", encoding="utf-8") as handle:
        try:
            fcntl.flock(
                handle.fileno(),
                fcntl.LOCK_EX | fcntl.LOCK_NB,
            )
        except BlockingIOError as exc:
            raise RuntimeError(
                "Another full pipeline process is already running."
            ) from exc

        handle.seek(0)
        handle.truncate()
        handle.write(
            json.dumps(
                {
                    "pid": os.getpid(),
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


def status_counts() -> dict[str, int]:
    if not DB_PATH.exists():
        return {}

    connection = sqlite3.connect(DB_PATH, timeout=30)
    connection.row_factory = sqlite3.Row
    try:
        rows = connection.execute(
            """
            SELECT status, COUNT(*) AS count
            FROM videos
            GROUP BY status
            ORDER BY status
            """
        ).fetchall()
        return {row["status"]: row["count"] for row in rows}
    finally:
        connection.close()


def save_report(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    os.replace(temporary, path)


def run_command(name: str, command: list[str]) -> dict[str, Any]:
    print()
    print("=" * 72)
    print(f"STEP {name}")
    print("=" * 72)
    print("COMMAND " + " ".join(command))

    started_at = iso_now()
    lines: list[str] = []

    process = subprocess.Popen(
        command,
        cwd=ROOT,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
    )

    assert process.stdout is not None
    for line in process.stdout:
        print(line, end="", flush=True)
        lines.append(line)

    return_code = process.wait()
    output = "".join(lines)
    report_match = REPORT_LINE.findall(output)

    return {
        "name": name,
        "command": command,
        "started_at": started_at,
        "finished_at": iso_now(),
        "return_code": return_code,
        "child_report": report_match[-1] if report_match else None,
        "output_tail": output[-12000:],
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run the complete Instagram-to-Markdown pipeline."
    )
    auth_group = parser.add_mutually_exclusive_group()
    auth_group.add_argument(
        "--cookies-file",
        type=Path,
        default=DEFAULT_COOKIE_FILE,
        help="Netscape-format Instagram cookie file.",
    )
    auth_group.add_argument(
        "--cookies-browser",
        help="Explicit browser-cookie fallback, e.g. chrome/instagram.com.",
    )
    parser.add_argument("--scan-limit", type=int, default=50)
    parser.add_argument("--worker-limit", type=int, default=50)
    parser.add_argument("--force-ipv4", action="store_true")
    parser.add_argument("--skip-scan", action="store_true")
    parser.add_argument("--skip-worker", action="store_true")
    parser.add_argument("--skip-auth-check", action="store_true")
    return parser


def main() -> int:
    args = build_parser().parse_args()

    if not 1 <= args.scan_limit <= 500:
        print("ERROR: --scan-limit must be between 1 and 500.", file=sys.stderr)
        return 1
    if not 1 <= args.worker_limit <= 500:
        print("ERROR: --worker-limit must be between 1 and 500.", file=sys.stderr)
        return 1

    cookie_file: Path | None = None
    if args.cookies_browser:
        auth_mode = "browser"
    else:
        auth_mode = "cookie_file"
        cookie_file = args.cookies_file.expanduser().resolve()

    run_id = (
        utc_now().strftime("%Y%m%dT%H%M%SZ")
        + "-"
        + uuid.uuid4().hex[:8]
    )
    RUN_LOG_DIR.mkdir(parents=True, exist_ok=True)
    report_path = RUN_LOG_DIR / f"{run_id}-pipeline.json"
    audit_path = RUN_LOG_DIR / f"{run_id}-audit.json"

    report: dict[str, Any] = {
        "run_id": run_id,
        "type": "full_pipeline",
        "started_at": iso_now(),
        "finished_at": None,
        "status": "running",
        "requires_attention": False,
        "auth_mode": auth_mode,
        "cookies_file": str(cookie_file) if cookie_file else None,
        "cookies_browser": args.cookies_browser,
        "arguments": {
            "scan_limit": args.scan_limit,
            "worker_limit": args.worker_limit,
            "force_ipv4": args.force_ipv4,
            "skip_scan": args.skip_scan,
            "skip_worker": args.skip_worker,
            "skip_auth_check": args.skip_auth_check,
        },
        "steps": [],
        "status_counts_before": status_counts(),
        "status_counts_after": {},
        "audit": None,
        "errors": [],
    }

    return_code = 1

    try:
        with pipeline_lock():
            health_step = run_command(
                "health_and_config_sync",
                [
                    sys.executable,
                    str(ROOT / "scripts" / "init_system.py"),
                ],
            )
            report["steps"].append(health_step)

            if health_step["return_code"] != 0:
                report["errors"].append(
                    "Health check or creator config sync failed."
                )
            else:
                auth_ok = True

                if auth_mode == "cookie_file":
                    if cookie_file is None:
                        raise RuntimeError(
                            "Cookie file path is missing."
                        )

                    if cookie_file.is_symlink():
                        raise RuntimeError(
                            "Cookie file must not be a symbolic link: "
                            f"{cookie_file}"
                        )

                    if not cookie_file.is_file():
                        raise RuntimeError(
                            f"Cookie file does not exist: {cookie_file}"
                        )

                    os.chmod(
                        cookie_file.parent,
                        0o700,
                    )

                    os.chmod(
                        cookie_file,
                        0o600,
                    )

                    cookie_mode = (
                        cookie_file.stat().st_mode
                        & 0o777
                    )

                    if cookie_mode != 0o600:
                        raise RuntimeError(
                            "Could not secure cookie file. "
                            f"mode={oct(cookie_mode)} "
                            f"path={cookie_file}"
                        )

                    print(
                        "COOKIE_FILE_SECURED "
                        f"mode={oct(cookie_mode)} "
                        f"path={cookie_file}"
                    )

                if not args.skip_auth_check and auth_mode == "cookie_file":
                    auth_step = run_command(
                        "instagram_auth_check",
                        [
                            sys.executable,
                            str(ROOT / "scripts" / "check_instagram_auth.py"),
                        ],
                    )
                    report["steps"].append(auth_step)
                    auth_ok = auth_step["return_code"] == 0
                    if not auth_ok:
                        report["errors"].append(
                            "Instagram cookie authentication check failed."
                        )

                if auth_ok and not args.skip_scan:
                    scan_command = [
                        sys.executable,
                        str(ROOT / "scripts" / "scan_gallery.py"),
                        "--scan-limit",
                        str(args.scan_limit),
                    ]
                    if auth_mode == "browser":
                        scan_command += [
                            "--cookies-browser",
                            args.cookies_browser,
                        ]
                    else:
                        scan_command += [
                            "--cookies-file",
                            str(cookie_file),
                        ]
                    if args.force_ipv4:
                        scan_command.append("--force-ipv4")

                    scan_step = run_command(
                        "scan_creators",
                        scan_command,
                    )
                    report["steps"].append(scan_step)
                    if scan_step["return_code"] != 0:
                        report["errors"].append(
                            "Creator scan reported errors."
                        )

                if auth_ok and not args.skip_worker:
                    worker_command = [
                        sys.executable,
                        str(ROOT / "scripts" / "process_worker.py"),
                        "--limit",
                        str(args.worker_limit),
                    ]
                    if auth_mode == "browser":
                        worker_command += [
                            "--cookies-browser",
                            args.cookies_browser,
                        ]
                    else:
                        worker_command += [
                            "--cookies-file",
                            str(cookie_file),
                        ]
                    if args.force_ipv4:
                        worker_command.append("--force-ipv4")

                    worker_step = run_command(
                        "process_queue",
                        worker_command,
                    )
                    report["steps"].append(worker_step)
                    if worker_step["return_code"] != 0:
                        report["errors"].append(
                            "Worker reported errors."
                        )

                audit_step = run_command(
                    "final_audit",
                    [
                        sys.executable,
                        str(ROOT / "scripts" / "audit_pipeline.py"),
                        "--json-output",
                        str(audit_path),
                    ],
                )
                report["steps"].append(audit_step)

                if audit_path.exists():
                    report["audit"] = json.loads(
                        audit_path.read_text(encoding="utf-8")
                    )

                if audit_step["return_code"] != 0:
                    report["errors"].append(
                        "Final integrity audit failed."
                    )

            report["status_counts_after"] = status_counts()

            active = sum(
                report["status_counts_after"].get(status, 0)
                for status in (
                    "downloading",
                    "downloaded",
                    "transcribing",
                    "transcribed",
                    "rendering",
                    "validating",
                    "cleaning",
                )
            )
            unresolved = sum(
                report["status_counts_after"].get(status, 0)
                for status in ("retry_wait", "failed")
            )

            if active:
                report["errors"].append(
                    f"Abandoned active states: {active}"
                )
            if unresolved:
                report["errors"].append(
                    f"Unresolved retry_wait/failed items: {unresolved}"
                )

            audit_failed = (
                report["audit"] is not None
                and report["audit"].get("status") == "failed"
            )

            if audit_failed or active or any(
                step["name"] in (
                    "health_and_config_sync",
                    "instagram_auth_check",
                )
                and step["return_code"] != 0
                for step in report["steps"]
            ):
                report["status"] = "failed"
                report["requires_attention"] = True
                return_code = 1
            elif report["errors"]:
                report["status"] = "completed_with_errors"
                report["requires_attention"] = True
                return_code = 2
            else:
                report["status"] = "completed"
                report["requires_attention"] = False
                return_code = 0

    except Exception as exc:
        report["status"] = "failed"
        report["requires_attention"] = True
        report["errors"].append(f"{type(exc).__name__}: {exc}")
        return_code = 1

    finally:
        report["finished_at"] = iso_now()
        if not report["status_counts_after"]:
            report["status_counts_after"] = status_counts()

        save_report(report_path, report)

        print()
        print("=" * 72)
        print(f"PIPELINE_{report['status'].upper()}")
        print("=" * 72)
        print(
            f"requires_attention="
            f"{str(report['requires_attention']).lower()}"
        )
        print(
            "status_counts="
            + json.dumps(
                report["status_counts_after"],
                ensure_ascii=False,
                sort_keys=True,
            )
        )
        print(f"errors={len(report['errors'])}")
        print(f"report={report_path}")

    return return_code


if __name__ == "__main__":
    raise SystemExit(main())
