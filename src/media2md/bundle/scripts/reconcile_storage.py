#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import sqlite3
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[1]
STATE_DB = ROOT / "data" / "state.db"
REGISTRY_DB = ROOT / "data" / "media2md.db"
MARKDOWN_DIR = ROOT / "markdown"


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def parse_frontmatter(path: Path) -> dict[str, Any]:
    text = path.read_text(encoding="utf-8", errors="replace")
    if not text.startswith("---\n"):
        raise RuntimeError("missing YAML frontmatter")
    parts = text.split("---", 2)
    if len(parts) < 3:
        raise RuntimeError("unterminated YAML frontmatter")
    payload = yaml.safe_load(parts[1]) or {}
    if not isinstance(payload, dict):
        raise RuntimeError("frontmatter is not a mapping")
    return payload


def registry_rows() -> list[dict[str, Any]]:
    if not REGISTRY_DB.is_file():
        return []
    conn = sqlite3.connect(REGISTRY_DB)
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        """SELECT m.*, c.handle AS creator FROM media m
           JOIN creators c ON c.id=m.creator_id ORDER BY m.id"""
    ).fetchall()
    conn.close()
    return [dict(row) for row in rows]


def state_counts() -> dict[str, int]:
    if not STATE_DB.is_file():
        return {}
    conn = sqlite3.connect(STATE_DB)
    rows = conn.execute("SELECT status,COUNT(*) FROM videos GROUP BY status ORDER BY status").fetchall()
    conn.close()
    return {str(status): int(count) for status, count in rows}


def inventory() -> dict[str, Any]:
    rows = registry_rows()
    tracked_paths: set[Path] = set()
    missing: list[dict[str, Any]] = []
    hash_mismatches: list[dict[str, Any]] = []
    structure_errors: list[dict[str, Any]] = []
    noncompleted_artifacts: list[dict[str, Any]] = []

    provider_counts: dict[str, dict[str, int]] = {}
    for row in rows:
        provider = str(row.get("provider") or "unknown")
        status = str(row.get("status") or "unknown")
        provider_counts.setdefault(provider, {})[status] = provider_counts.setdefault(provider, {}).get(status, 0) + 1
        relative = row.get("markdown_path")
        path = (ROOT / relative).resolve() if relative else None
        if path:
            try:
                path.relative_to(MARKDOWN_DIR.resolve())
            except ValueError:
                structure_errors.append({"provider": provider, "creator": row.get("creator"), "media_id": row.get("external_id"), "issue": "path_outside_markdown", "path": str(path)})
                continue
            tracked_paths.add(path)
        exists = bool(path and path.is_file())
        if status == "completed":
            if not exists:
                missing.append({"provider": provider, "creator": row.get("creator"), "media_id": row.get("external_id"), "path": relative})
                continue
            actual_hash = sha256_file(path)
            expected_hash = str(row.get("markdown_sha256") or "")
            if actual_hash != expected_hash:
                hash_mismatches.append({"provider": provider, "creator": row.get("creator"), "media_id": row.get("external_id"), "path": relative, "stored_hash": expected_hash, "actual_hash": actual_hash})
            try:
                metadata = parse_frontmatter(path)
                text = path.read_text(encoding="utf-8", errors="replace")
                expected_id = str(row.get("external_id") or "")
                id_present = expected_id in text or str(metadata.get("media_id") or metadata.get("shortcode") or "") == expected_id
                transcript_present = any(marker in text for marker in ("## Transcript", "## 語音逐字稿", "## 语音转录", "## 文字起こし"))
                if not id_present or not transcript_present:
                    structure_errors.append({"provider": provider, "creator": row.get("creator"), "media_id": expected_id, "issue": "markdown_structure", "path": relative})
            except Exception as exc:
                structure_errors.append({"provider": provider, "creator": row.get("creator"), "media_id": row.get("external_id"), "issue": f"frontmatter:{type(exc).__name__}:{exc}", "path": relative})
        elif exists:
            noncompleted_artifacts.append({"provider": provider, "creator": row.get("creator"), "media_id": row.get("external_id"), "status": status, "path": relative})

    actual_markdown = {path.resolve() for path in MARKDOWN_DIR.rglob("*.md") if path.is_file()}
    orphans: list[dict[str, Any]] = []
    for path in sorted(actual_markdown - tracked_paths):
        item: dict[str, Any] = {"path": str(path.relative_to(ROOT)), "creator": None, "media_id": None, "source_url": None, "published_at": None, "parse_error": None}
        try:
            metadata = parse_frontmatter(path)
            item.update({
                "creator": metadata.get("creator"),
                "media_id": metadata.get("media_id") or metadata.get("shortcode"),
                "source_url": metadata.get("source_url"),
                "published_at": metadata.get("published_at"),
            })
        except Exception as exc:
            item["parse_error"] = f"{type(exc).__name__}: {exc}"
        orphans.append(item)

    return {
        "status_counts": state_counts(),
        "provider_status_counts": provider_counts,
        "missing_completed": missing,
        "hash_mismatches": hash_mismatches,
        "structure_errors": structure_errors,
        "noncompleted_artifacts": noncompleted_artifacts,
        "orphans": orphans,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    report = inventory()
    differences = sum(len(report[key]) for key in ("missing_completed", "hash_mismatches", "structure_errors", "noncompleted_artifacts", "orphans"))
    if args.json:
        print(json.dumps({"type": "storage_reconciliation", "applied": False, **report, "difference_count": differences}, ensure_ascii=False, indent=2))
        return 0 if differences == 0 else 1
    print("STORAGE_RECONCILIATION")
    print("applied=false")
    print("status_counts=" + json.dumps(report["status_counts"], ensure_ascii=False, sort_keys=True))
    print("provider_status_counts=" + json.dumps(report["provider_status_counts"], ensure_ascii=False, sort_keys=True))
    for key in ("missing_completed", "hash_mismatches", "structure_errors", "noncompleted_artifacts", "orphans"):
        print(f"\n{key}={len(report[key])}")
        for item in report[key]:
            print("  " + json.dumps(item, ensure_ascii=False, sort_keys=True))
    print("\nRECONCILIATION_CLEAN" if differences == 0 else f"\nRECONCILIATION_DIFFERENCES_FOUND count={differences}")
    return 0 if differences == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
