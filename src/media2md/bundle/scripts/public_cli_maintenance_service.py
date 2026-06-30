from __future__ import annotations

import json
import shutil
import sqlite3
from pathlib import Path
from typing import Callable
try:
    from media2md.cli_output_service import make_output_model, make_section
except ModuleNotFoundError:
    from media2md_contract_compat import make_output_model, make_section


ACTIVE_STATES = ("downloading", "downloaded", "transcribing", "transcribed", "rendering", "validating", "cleaning")
DATABASES = (
    ("data/state.db", "videos", "status"),
    ("data/social2md_media.db", "media", "status"),
    ("data/media2md.db", "media", "status"),
)
WORKSPACE_TARGETS = (
    "workspace/downloads",
    "workspace/transcripts",
    "workspace/temp",
    "workspace/generic_downloads",
    "workspace/generic_transcripts",
)


def repair_active_states_common(args, *, root: Path, iso_now: Callable[[], str], registry: Callable[[list[str]], int]) -> int:
    if not args.yes:
        raise RuntimeError("Use --yes to requeue abandoned active states.")
    repaired: dict[str, int] = {}
    for relative, table, key in DATABASES:
        path = root / relative
        if not path.is_file():
            continue
        conn = sqlite3.connect(path)
        placeholders = ",".join("?" for _ in ACTIVE_STATES)
        try:
            cursor = conn.execute(
                f"UPDATE {table} SET status='pending',last_error='Recovered from abandoned active state',updated_at=? WHERE {key} IN ({placeholders})",
                (iso_now(), *ACTIVE_STATES),
            )
            conn.commit()
            repaired[path.name] = cursor.rowcount
        finally:
            conn.close()
    registry(["repair-identities"])
    payload = make_output_model(
        event="repair_active_states",
        schema="media2md.cli.repair_active_states/v1",
        summary="Active states were requeued",
        sections=(
            make_section(
                "maintenance",
                status="ok",
                message="Abandoned active states were repaired",
                data={"repaired": repaired},
            ),
        ),
        data={"repaired": repaired},
    ).as_dict()
    print("ACTIVE_STATES_REPAIRED")
    print(json.dumps(payload, indent=2))
    return 0


def repair_workspace_common(args, *, root: Path) -> int:
    if not args.yes:
        raise RuntimeError("Use --yes to remove stale intermediate workspace files.")
    active_rows = 0
    for relative, table, _key in DATABASES:
        path = root / relative
        if not path.is_file():
            continue
        conn = sqlite3.connect(path)
        placeholders = ",".join("?" for _ in ACTIVE_STATES)
        try:
            active_rows += int(conn.execute(f"SELECT COUNT(*) FROM {table} WHERE status IN ({placeholders})", ACTIVE_STATES).fetchone()[0])
        finally:
            conn.close()
    if active_rows:
        raise RuntimeError(
            f"Refusing workspace cleanup while {active_rows} active media rows exist. Run repair active-states only after confirming no worker is running."
        )
    removed_files = 0
    for relative in WORKSPACE_TARGETS:
        target = root / relative
        if target.exists():
            removed_files += sum(1 for path in target.rglob("*") if path.is_file())
            shutil.rmtree(target)
        target.mkdir(parents=True, exist_ok=True)
    payload = make_output_model(
        event="repair_workspace",
        schema="media2md.cli.repair_workspace/v1",
        summary="Workspace intermediates were cleaned",
        sections=(
            make_section(
                "maintenance",
                status="ok",
                message="Workspace cleanup completed",
                data={"removed_files": removed_files, "active_rows": 0},
            ),
        ),
        data={"removed_files": removed_files, "active_rows": 0},
    ).as_dict()
    print("WORKSPACE_REPAIRED")
    print(json.dumps(payload, indent=2))
    return 0
