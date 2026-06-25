#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import sqlite3
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
STATE_DB = ROOT / "data" / "state.db"
REGISTRY_DB = ROOT / "data" / "media2md.db"
MARKDOWN_DIR = ROOT / "markdown"
WORKSPACE_DIRS = (
    ROOT / "workspace" / "downloads",
    ROOT / "workspace" / "transcripts",
    ROOT / "workspace" / "temp",
    ROOT / "workspace" / "generic_downloads",
    ROOT / "workspace" / "generic_transcripts",
)
ACTIVE_STATUSES = ("downloading", "downloaded", "transcribing", "transcribed", "rendering", "validating", "cleaning")


def add_check(report: dict[str, Any], name: str, passed: bool, detail: str, severity: str = "error") -> None:
    report["checks"].append({"name": name, "passed": passed, "detail": detail, "severity": severity})
    if not passed:
        report["warnings" if severity == "warning" else "failures"].append(f"{name}: {detail}")


def db_check(report: dict[str, Any], path: Path, label: str) -> sqlite3.Connection | None:
    if not path.is_file():
        add_check(report, f"{label}_database_exists", False, str(path))
        return None
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    integrity = conn.execute("PRAGMA integrity_check").fetchone()[0]
    add_check(report, f"{label}_sqlite_integrity", integrity == "ok", str(integrity))
    fk = conn.execute("PRAGMA foreign_key_check").fetchall()
    add_check(report, f"{label}_sqlite_foreign_keys", not fk, "ok" if not fk else f"errors={len(fk)}")
    return conn


def audit() -> dict[str, Any]:
    report: dict[str, Any] = {"checks": [], "warnings": [], "failures": [], "completed_files": 0, "workspace_files": [], "orphan_markdown": []}
    tracked: set[Path] = set()

    state = db_check(report, STATE_DB, "instagram")
    if state:
        placeholders = ",".join("?" for _ in ACTIVE_STATUSES)
        active = state.execute(f"SELECT shortcode,status FROM videos WHERE status IN ({placeholders}) ORDER BY shortcode", ACTIVE_STATUSES).fetchall()
        add_check(report, "no_abandoned_active_states", not active, "ok" if not active else ", ".join(f"{r['shortcode']}={r['status']}" for r in active))
        state.close()

    registry = db_check(report, REGISTRY_DB, "registry")
    if registry:
        active = registry.execute(
            f"SELECT provider,external_id,status FROM media WHERE status IN ({','.join('?' for _ in ACTIVE_STATUSES)}) ORDER BY provider,external_id",
            ACTIVE_STATUSES,
        ).fetchall()
        add_check(report, "no_abandoned_registry_states", not active, "ok" if not active else ", ".join(f"{r['provider']}:{r['external_id']}={r['status']}" for r in active))
        rows = registry.execute(
            """SELECT m.provider,m.external_id,m.markdown_path,m.markdown_sha256,c.handle
               FROM media m JOIN creators c ON c.id=m.creator_id
               WHERE m.status='completed' ORDER BY m.provider,c.handle,m.external_id"""
        ).fetchall()
        for row in rows:
            key = f"{row['provider']}:{row['external_id']}"
            relative = row["markdown_path"]
            if not relative:
                add_check(report, f"markdown_artifact:{key}", False, "completed row has no markdown_path")
                continue
            path = (ROOT / relative).resolve()
            tracked.add(path)
            if not path.is_file():
                add_check(report, f"markdown_artifact:{key}", False, f"missing: {relative}")
                continue
            data = path.read_bytes()
            actual = hashlib.sha256(data).hexdigest()
            expected = str(row["markdown_sha256"] or "")
            text = data.decode("utf-8", errors="replace")
            structure = text.startswith("---\n") and str(row["external_id"]) in text and any(marker in text for marker in ("## Transcript", "## 語音逐字稿", "## 语音转录", "## 文字起こし"))
            passed = actual == expected and len(data) >= 100 and structure
            add_check(report, f"markdown_artifact:{key}", passed, f"path={relative} bytes={len(data)} hash_ok={actual == expected} structure_ok={structure}")
            if passed:
                report["completed_files"] += 1
        registry.close()

    actual = {path.resolve() for path in MARKDOWN_DIR.rglob("*.md") if path.is_file()}
    orphans = sorted(str(path.relative_to(ROOT)) for path in actual - tracked)
    report["orphan_markdown"] = orphans
    add_check(report, "no_untracked_markdown", not orphans, "ok" if not orphans else ", ".join(orphans), severity="warning")

    workspace_files = sorted(str(path.relative_to(ROOT)) for base in WORKSPACE_DIRS if base.exists() for path in base.rglob("*") if path.is_file())
    report["workspace_files"] = workspace_files
    add_check(report, "workspace_cleanup", not workspace_files, "no intermediate files" if not workspace_files else ", ".join(workspace_files), severity="warning")
    return report


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    report = audit()
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        for item in report["checks"]:
            label = "PASS" if item["passed"] else "WARN" if item["severity"] == "warning" else "FAIL"
            print(f"[{label}] {item['name']} | {item['detail']}")
        print("\nAUDIT_COMPLETED" if not report["failures"] else "\nAUDIT_FAILED")
        print(f"completed_files={report['completed_files']}")
        print(f"failures={len(report['failures'])}")
        print(f"warnings={len(report['warnings'])}")
    return 0 if not report["failures"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
