from __future__ import annotations

import argparse
import json
import shutil
import sqlite3
import subprocess
import sys
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable
try:
    from media2md.cli_output_service import make_event_payload, make_output_model, make_section
except ModuleNotFoundError:
    from media2md_contract_compat import make_event_payload, make_output_model, make_section
from media2md.remediation_service import uninstall_dry_run_next_step


def scheduler_tick_common(
    args: argparse.Namespace,
    *,
    load_policies: Callable[[], dict[str, Any]],
    load_json: Callable[[Path, Any], Any],
    atomic_json: Callable[[Path, Any], None],
    scheduler_state_path: Path,
    refresh_auth: Callable[[str], None],
    core: Callable[[list[str]], int],
    effective_policy: Callable[[str, str], dict[str, Any]],
    registry: Callable[[list[str]], int],
    creator_run_builder: Callable[[str, str, dict[str, Any], str], argparse.Namespace],
    creator_run: Callable[[argparse.Namespace], int],
    iso_now: Callable[[], str],
    emit: Callable[[dict[str, Any], str], None],
) -> int:
    policies = load_policies()["creators"]
    state = load_json(scheduler_state_path, {"creators": {}})
    now = datetime.now(timezone.utc)
    jobs = 0
    failures = 0
    refresh_auth("instagram")
    refresh_auth("tiktok")
    code = core(["scheduler", "tick", "--output", args.output, "--non-interactive"])
    if code not in (0,):
        failures += 1
    for key in sorted(policies):
        if ":" not in key:
            continue
        provider, creator = key.split(":", 1)
        if provider == "instagram":
            continue
        policy = effective_policy(provider, creator)
        creator_state = state["creators"].setdefault(key, {})
        last = creator_state.get("last_sync_success_at")
        due = True
        if last:
            try:
                due = now >= datetime.fromisoformat(last) + timedelta(minutes=policy["sync"]["every_minutes"])
            except ValueError:
                pass
        if policy["sync"]["enabled"] and due:
            jobs += 1
            last_full = creator_state.get("last_full_sync_at")
            full_due = not last_full
            if last_full:
                try:
                    full_due = now >= datetime.fromisoformat(last_full) + timedelta(minutes=policy["sync"]["full_every_minutes"])
                except ValueError:
                    full_due = True
            sync_code = registry(
                [
                    "sync",
                    provider,
                    creator,
                    "--mode",
                    "full" if full_due else "quick",
                    "--quick-window",
                    str(policy["sync"]["quick_window"]),
                ]
            )
            if sync_code == 0:
                creator_state["last_sync_success_at"] = iso_now()
                if full_due:
                    creator_state["last_full_sync_at"] = iso_now()
            else:
                failures += 1
        processing = policy["processing"]
        last_proc = creator_state.get("last_processing_success_at")
        proc_due = not last_proc
        if last_proc:
            try:
                proc_due = now >= datetime.fromisoformat(last_proc) + timedelta(minutes=processing["every_minutes"])
            except ValueError:
                proc_due = True
        if processing.get("scheduled") and proc_due:
            jobs += 1
            ns = creator_run_builder(provider, creator, processing, args.output)
            run_code = creator_run(ns)
            if run_code == 0:
                creator_state["last_processing_success_at"] = iso_now()
            else:
                failures += 1
        atomic_json(scheduler_state_path, state)
    emit(
        make_output_model(
            event="media2md_scheduler_completed",
            schema="media2md.cli.scheduler_completed/v1",
            summary="Scheduler tick completed",
            sections=(
                make_section(
                    "scheduler",
                    status="ok" if failures == 0 else "warn",
                    message="Scheduled catalog and processing jobs finished",
                    data={"jobs_run": jobs, "failures": failures},
                ),
            ),
            data={"jobs_run": jobs, "failures": failures},
        ).as_dict(),
        args.output,
    )
    if args.output == "human":
        print(f"MEDIA2MD_SCHEDULER_COMPLETED jobs_run={jobs} failures={failures}")
    return 0 if failures == 0 else 2


def update_check_common(
    args: argparse.Namespace,
    *,
    repository: str,
    version: str,
    emit: Callable[[dict[str, Any], str], None],
) -> int:
    repo = args.repository or repository
    request = urllib.request.Request(
        f"https://api.github.com/repos/{repo}/releases/latest",
        headers={"Accept": "application/vnd.github+json", "User-Agent": "media2md"},
    )
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            release = json.loads(response.read().decode())
        latest = str(release.get("tag_name") or "")
        parts = lambda value: tuple(int(item) for item in __import__("re").findall(r"\d+", value)[:3])
        available = parts(latest) > parts(version)
        payload = make_output_model(
            event="update_check",
            schema="media2md.cli.update_check/v1",
            summary="Published update check result",
            sections=(
                make_section(
                    "update",
                    status="warn" if available else "ok",
                    message="Published GitHub release status",
                    data={
                        "repository": repo,
                        "current_version": version,
                        "latest_version": latest,
                        "update_available": available,
                        "release_url": release.get("html_url"),
                    },
                ),
            ),
            data={
                "repository": repo,
                "current_version": version,
                "latest_version": latest,
                "update_available": available,
                "release_url": release.get("html_url"),
            },
        ).as_dict()
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            payload = make_output_model(
                event="update_check",
                schema="media2md.cli.update_check/v1",
                summary="No published GitHub release was found",
                sections=(
                    make_section(
                        "update",
                        status="ok",
                        message="No published GitHub release was found",
                        data={
                            "repository": repo,
                            "current_version": version,
                            "latest_version": None,
                            "update_available": False,
                            "release_status": "no_release_published",
                        },
                    ),
                ),
                data={
                    "repository": repo,
                    "current_version": version,
                    "latest_version": None,
                    "update_available": False,
                    "release_status": "no_release_published",
                },
            ).as_dict()
        else:
            raise RuntimeError(f"GitHub update check failed: HTTP {exc.code}")
    if args.output == "ndjson":
        emit(payload, args.output)
    else:
        print("UPDATE_CHECK")
        for key, value in payload.items():
            if key != "event":
                print(f"{key}={value}")
    return 0


def data_delete_all_common(args: argparse.Namespace, *, root: Path) -> int:
    from media2md_runtime import maintenance_lock

    if not args.yes or args.confirm != "DELETE-ALL-DATA":
        raise RuntimeError("Use --yes --confirm DELETE-ALL-DATA.")
    with maintenance_lock(exclusive=True, operation="data-delete-all"):
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        quarantine = root / ".media2md-quarantine" / f"all-data-{stamp}"
        quarantine.mkdir(parents=True, exist_ok=True)
        moved: list[str] = []
        for relative in ("data", "markdown", "workspace", "logs", "config"):
            source = root / relative
            if not source.exists():
                continue
            target = quarantine / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(source), str(target))
            moved.append(relative)
        for relative in ("data", "markdown", "workspace", "logs/runs", "config"):
            (root / relative).mkdir(parents=True, exist_ok=True)
    payload = make_output_model(
        event="data_delete_all",
        schema="media2md.cli.data_delete_all/v1",
        summary="All managed data was quarantined",
        sections=(
            make_section(
                "maintenance",
                status="warn",
                message="Managed data was moved to quarantine and can still be recovered",
                data={
                    "quarantine_path": str(quarantine.relative_to(root)),
                    "moved": moved,
                    "recoverable": True,
                },
            ),
        ),
        data={
            "quarantine_path": str(quarantine.relative_to(root)),
            "moved": moved,
            "recoverable": True,
        },
    ).as_dict()
    print(f"ALL_DATA_QUARANTINED path={quarantine.relative_to(root)}")
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


def remove_openclaw_cron_common() -> tuple[int, list[str]]:
    executable = shutil.which("openclaw")
    if not executable:
        return 0, []
    removed: list[str] = []
    result = subprocess.run([executable, "cron", "list", "--json"], capture_output=True, text=True, check=False)
    if result.returncode != 0:
        return 0, []
    try:
        payload = json.loads(result.stdout)
    except json.JSONDecodeError:
        return 0, []
    jobs = payload.get("jobs", payload if isinstance(payload, list) else [])
    if not isinstance(jobs, list):
        return 0, []
    for job in jobs:
        if not isinstance(job, dict):
            continue
        name = str(job.get("name") or job.get("title") or "")
        job_id = job.get("id") or job.get("job_id")
        if name in {"Media2MD scheduler", "Social2MD scheduler"} and job_id:
            removal = subprocess.run([executable, "cron", "remove", str(job_id)], check=False)
            if removal.returncode == 0:
                removed.append(str(job_id))
    return 0, removed


def uninstall_common(
    args: argparse.Namespace,
    *,
    data_delete_all: Callable[[argparse.Namespace], int],
    remove_openclaw_cron: Callable[[], tuple[int, list[str]]],
    run: Callable[[list[str], bool], int],
) -> int:
    if args.purge_data:
        data_delete_all(argparse.Namespace(yes=args.yes, confirm=args.confirm))
    _, removed_jobs = remove_openclaw_cron()
    removed_skills = []
    for name in ("media2md", "social2md"):
        skill = Path.home() / ".openclaw" / "skills" / name
        if skill.exists():
            shutil.rmtree(skill)
            removed_skills.append(name)
    registry_file = Path.home() / ".config" / "media2md" / "project.json"
    registry_file.unlink(missing_ok=True)
    payload = make_output_model(
        event="uninstall_prepared",
        schema="media2md.cli.uninstall_prepared/v1",
        summary="Uninstall plan prepared",
        sections=(
            make_section(
                "uninstall",
                status="warn" if getattr(args, "dry_run", False) else "ok",
                message="Package uninstall plan is ready",
                data={
                    "openclaw_cron_removed": len(removed_jobs),
                    "openclaw_skills_removed": removed_skills,
                    "data_purged": bool(args.purge_data),
                    "package_command": "python -m pip uninstall -y media2md social2md",
                    "package_uninstalled": False if getattr(args, "dry_run", False) else True,
                    "next_step": uninstall_dry_run_next_step() if getattr(args, "dry_run", False) else None,
                },
            ),
        ),
        data={
            "openclaw_cron_removed": len(removed_jobs),
            "openclaw_skills_removed": removed_skills,
            "data_purged": bool(args.purge_data),
            "package_command": "python -m pip uninstall -y media2md social2md",
            "package_uninstalled": False if getattr(args, "dry_run", False) else True,
            "next_step": uninstall_dry_run_next_step() if getattr(args, "dry_run", False) else None,
        },
    ).as_dict()
    print("MEDIA2MD_UNINSTALL_PREPARED")
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    if getattr(args, "dry_run", False):
        print("package_uninstalled=false")
        print(f"next_step={uninstall_dry_run_next_step()}")
        return 0
    print("package_uninstalled=true")
    return run([sys.executable, "-m", "pip", "uninstall", "-y", "media2md", "social2md"])


def build_scheduler_creator_run_namespace(
    *,
    provider: str,
    creator: str,
    processing: dict[str, Any],
    output: str,
    batch_size_type_supported: bool,
    retry_failed_supported: bool,
) -> argparse.Namespace:
    payload = {
        "provider": provider,
        "creator": creator,
        "mode": processing["mode"],
        "batch_size": processing["batch_size"],
        "max_batches": processing["max_batches"],
        "max_runtime_minutes": processing["max_runtime_minutes"],
        "max_failures": processing["max_failures"],
        "stop_on_failure": processing["stop_on_failure"],
        "sleep_between_batches": processing["sleep_between_batches"],
        "since": None,
        "until": None,
        "rank_from": None,
        "rank_to": None,
        "order": None,
        "output": output,
        "allow_stale_catalog": False,
    }
    if batch_size_type_supported:
        payload["batch_size_type"] = []
    if retry_failed_supported:
        payload["retry_failed"] = False
    return argparse.Namespace(**payload)


def active_state_repairs(
    *,
    root: Path,
    iso_now: Callable[[], str],
    registry: Callable[[list[str]], int],
) -> dict[str, int]:
    active = ("downloading", "downloaded", "transcribing", "transcribed", "rendering", "validating", "cleaning")
    repaired: dict[str, int] = {}
    for path, table, key in (
        (root / "data" / "state.db", "videos", "status"),
        (root / "data" / "social2md_media.db", "media", "status"),
        (root / "data" / "media2md.db", "media", "status"),
    ):
        if not path.is_file():
            continue
        conn = sqlite3.connect(path)
        placeholders = ",".join("?" for _ in active)
        try:
            cursor = conn.execute(
                f"UPDATE {table} SET status='pending',last_error='Recovered from abandoned active state',updated_at=? WHERE {key} IN ({placeholders})",
                (iso_now(), *active),
            )
            conn.commit()
            repaired[path.name] = cursor.rowcount
        finally:
            conn.close()
    registry(["repair-identities"])
    return repaired
