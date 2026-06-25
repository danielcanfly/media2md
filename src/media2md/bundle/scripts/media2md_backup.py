#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import sqlite3
import tempfile
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from media2md_runtime import maintenance_lock

ROOT = Path(__file__).resolve().parents[1]
DATABASE_NAMES = ("media2md.db", "state.db", "social2md_media.db")
STATE_DIRECTORIES = (
    Path("config"),
    Path("data/provider_catalog_checkpoints"),
    Path("data/creator_catalogs"),
    Path("data/state"),
)
STATE_FILES = (
    Path("data/media2md_scheduler_state.json"),
)
DEFAULT_BACKUP_DIR = Path.home() / "media2md-backups"


def iso_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def safe_archive_member(name: str) -> bool:
    path = Path(name)
    return bool(name) and not path.is_absolute() and ".." not in path.parts


def sqlite_snapshot(source: Path, destination: Path) -> dict[str, Any]:
    destination.parent.mkdir(parents=True, exist_ok=True)
    source_uri = f"file:{source.resolve()}?mode=ro"
    source_conn = sqlite3.connect(source_uri, uri=True, timeout=60)
    destination_conn = sqlite3.connect(destination, timeout=60)
    try:
        source_conn.execute("PRAGMA busy_timeout=60000")
        destination_conn.execute("PRAGMA busy_timeout=60000")
        source_conn.backup(destination_conn)
        destination_conn.commit()
        integrity = str(destination_conn.execute("PRAGMA integrity_check").fetchone()[0])
        if integrity.lower() != "ok":
            raise RuntimeError(f"SQLite integrity check failed for {source.name}: {integrity}")
        page_count = int(destination_conn.execute("PRAGMA page_count").fetchone()[0])
    finally:
        destination_conn.close()
        source_conn.close()
    return {"integrity": "ok", "page_count": page_count}


def copy_state_file(source: Path, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, destination)


def is_runtime_artifact(relative: Path) -> bool:
    """Return True for ephemeral files that must never enter a state backup."""
    name = relative.name
    if name == ".DS_Store" or name.startswith("._"):
        return True
    if name.endswith((".tmp", ".part", ".lock", ".pid")):
        return True
    return False


def resolve_destination(value: str | None) -> Path:
    if value:
        requested = Path(value).expanduser().resolve()
        if requested.suffix.lower() == ".zip":
            return requested
        return requested / f"media2md-state-{stamp()}.zip"
    return DEFAULT_BACKUP_DIR / f"media2md-state-{stamp()}.zip"


def build_backup(destination: Path, *, force: bool = False, wait_seconds: float = 0) -> dict[str, Any]:
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists() and not force:
        raise RuntimeError(f"Backup already exists: {destination}. Use --force to replace it.")

    with maintenance_lock(exclusive=True, operation="data-backup", wait_seconds=wait_seconds):
        with tempfile.TemporaryDirectory(prefix="media2md-backup-") as temporary_name:
            stage = Path(temporary_name) / "media2md-state"
            stage.mkdir(parents=True, exist_ok=True)
            database_details: dict[str, Any] = {}

            for name in DATABASE_NAMES:
                source = ROOT / "data" / name
                if not source.is_file():
                    continue
                target = stage / "data" / name
                database_details[name] = sqlite_snapshot(source, target)

            copied: set[Path] = set()
            for relative_dir in STATE_DIRECTORIES:
                source_dir = ROOT / relative_dir
                if not source_dir.is_dir():
                    continue
                for source in sorted(source_dir.rglob("*")):
                    if not source.is_file():
                        continue
                    relative = source.relative_to(ROOT)
                    if is_runtime_artifact(relative):
                        continue
                    # Browser/session secrets are deliberately excluded from the
                    # portable state backup. They continue to live only on the Mac.
                    if relative.parts[:2] == ("data", "secrets"):
                        continue
                    copy_state_file(source, stage / relative)
                    copied.add(relative)

            for relative in STATE_FILES:
                source = ROOT / relative
                if source.is_file() and relative not in copied:
                    copy_state_file(source, stage / relative)
                    copied.add(relative)

            entries: list[dict[str, Any]] = []
            for path in sorted(stage.rglob("*")):
                if not path.is_file() or path.name == "manifest.json":
                    continue
                relative = path.relative_to(stage).as_posix()
                entries.append({
                    "path": relative,
                    "size": path.stat().st_size,
                    "sha256": sha256_file(path),
                })

            manifest = {
                "schema_version": 1,
                "created_at": iso_now(),
                "source_root": str(ROOT),
                "secrets_included": False,
                "excluded": [
                    "data/secrets",
                    "workspace",
                    "downloads",
                    "transcripts",
                    "markdown",
                    "logs",
                    "**/*.lock",
                    "**/*.pid",
                    "**/*.tmp",
                    "**/*.part",
                    "**/.DS_Store",
                    "**/._*",
                ],
                "databases": database_details,
                "entries": entries,
            }
            (stage / "manifest.json").write_text(
                json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )

            temporary_archive = destination.with_suffix(destination.suffix + f".{os.getpid()}.tmp")
            temporary_archive.unlink(missing_ok=True)
            with zipfile.ZipFile(temporary_archive, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
                for path in sorted(stage.rglob("*")):
                    if path.is_file():
                        archive.write(path, (Path("media2md-state") / path.relative_to(stage)).as_posix())
            os.replace(temporary_archive, destination)
            try:
                destination.chmod(0o600)
            except OSError:
                pass

    return {
        "event": "backup_created",
        "path": str(destination),
        "sha256": sha256_file(destination),
        "files": len(entries),
        "databases": sorted(database_details),
        "secrets_included": False,
    }


def verify_backup(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise RuntimeError(f"Backup not found: {path}")
    with zipfile.ZipFile(path, "r") as archive:
        bad = archive.testzip()
        if bad:
            raise RuntimeError(f"Backup ZIP CRC failed: {bad}")
        names = set(archive.namelist())
        manifest_name = "media2md-state/manifest.json"
        if manifest_name not in names:
            raise RuntimeError("Backup manifest is missing.")
        manifest = json.loads(archive.read(manifest_name).decode("utf-8"))
        if int(manifest.get("schema_version") or 0) != 1:
            raise RuntimeError("Unsupported backup manifest schema.")
        entries = manifest.get("entries")
        if not isinstance(entries, list):
            raise RuntimeError("Backup manifest entries are invalid.")
        for entry in entries:
            relative = str(entry.get("path") or "")
            member = f"media2md-state/{relative}"
            if not safe_archive_member(member) or member not in names:
                raise RuntimeError(f"Backup member is missing or unsafe: {relative}")
            payload = archive.read(member)
            actual_hash = hashlib.sha256(payload).hexdigest()
            if actual_hash != str(entry.get("sha256") or ""):
                raise RuntimeError(f"Backup hash mismatch: {relative}")
            expected_size = entry.get("size")
            if not isinstance(expected_size, int) or expected_size < 0:
                raise RuntimeError(f"Backup manifest size is invalid: {relative}")
            if len(payload) != expected_size:
                raise RuntimeError(f"Backup size mismatch: {relative}")

        with tempfile.TemporaryDirectory(prefix="media2md-verify-") as temporary_name:
            verify_root = Path(temporary_name)
            verified_databases: list[str] = []
            for name in (manifest.get("databases") or {}):
                member = f"media2md-state/data/{name}"
                if member not in names:
                    raise RuntimeError(f"Database snapshot missing: {name}")
                target = verify_root / name
                target.write_bytes(archive.read(member))
                conn = sqlite3.connect(f"file:{target}?mode=ro", uri=True)
                try:
                    integrity = str(conn.execute("PRAGMA integrity_check").fetchone()[0])
                finally:
                    conn.close()
                if integrity.lower() != "ok":
                    raise RuntimeError(f"Database integrity failed: {name}: {integrity}")
                verified_databases.append(name)

    return {
        "event": "backup_verified",
        "path": str(path),
        "sha256": sha256_file(path),
        "files": len(entries),
        "databases": sorted(verified_databases),
        "secrets_included": bool(manifest.get("secrets_included")),
    }


def emit(payload: dict[str, Any], output: str) -> None:
    if output == "ndjson":
        print(json.dumps({"schema_version": 1, "timestamp": iso_now(), **payload}, ensure_ascii=False, sort_keys=True))
        return
    if payload["event"] == "backup_created":
        print("MEDIA2MD_BACKUP_CREATED")
    else:
        print("MEDIA2MD_BACKUP_VERIFIED")
    print(f"path={payload['path']}")
    print(f"sha256={payload['sha256']}")
    print(f"files={payload['files']}")
    print("databases=" + ",".join(payload["databases"]))
    print(f"secrets_included={str(payload['secrets_included']).lower()}")


def main() -> int:
    parser = argparse.ArgumentParser(prog="media2md data")
    sub = parser.add_subparsers(dest="command", required=True)
    backup = sub.add_parser("backup")
    backup.add_argument("--destination")
    backup.add_argument("--force", action="store_true")
    backup.add_argument("--wait-seconds", type=float, default=0)
    backup.add_argument("--output", choices=("human", "ndjson"), default="human")
    verify = sub.add_parser("verify-backup")
    verify.add_argument("path")
    verify.add_argument("--output", choices=("human", "ndjson"), default="human")
    args = parser.parse_args()
    try:
        if args.command == "backup":
            emit(build_backup(resolve_destination(args.destination), force=args.force, wait_seconds=args.wait_seconds), args.output)
            return 0
        emit(verify_backup(Path(args.path).expanduser().resolve()), args.output)
        return 0
    except (RuntimeError, OSError, sqlite3.Error, zipfile.BadZipFile, json.JSONDecodeError) as exc:
        print(f"ERROR: {exc}", file=os.sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
