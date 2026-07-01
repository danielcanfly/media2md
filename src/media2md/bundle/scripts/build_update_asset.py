#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import zipfile
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
VERSION = "0.9.5"
SCRIPT_PAYLOADS = [
    "install_media2md_v067.py",
    "media2md_cli_v067.py",
    "media2md_registry_v067.py",
    "media2md_urls_v067.py",
    "media2md_update_v067.py",
    "media2md_auth_v067.py",
    "media2md_youtube_session_v067.py",
    "media2md_ytdlp_v067.py",
    "media2md_runtime_v067.py",
    "media2md_doctor_v067.py",
    "generic_media_v067.py",
    "process_worker_media2md_v067.py",
    "process_worker_impl_v067.py",
    "instagram_instaloader_v067.py",
    "creator_bulk_v067.py",
    "build_update_asset_v067.py",
    "reconcile_storage_v067.py",
    "audit_pipeline_v067.py",
    "social2md_core_v03.py",
]
STATIC_FILES = [
    "bin/media2md_v067",
    "openclaw/SKILL_v067.md",
    "MEDIA2MD_V067_INSTALL.md",
]
EXCLUDED_PARTS = {"__pycache__", ".pytest_cache", ".DS_Store"}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def release_files() -> list[Path]:
    files = [ROOT / "scripts" / name for name in SCRIPT_PAYLOADS]
    files.extend(ROOT / relative for relative in STATIC_FILES)
    packaging = ROOT / "packaging"
    files.extend(
        child for child in packaging.rglob("*")
        if child.is_file() and not any(part in EXCLUDED_PARTS for part in child.relative_to(ROOT).parts)
    )
    missing = [str(path.relative_to(ROOT)) for path in files if not path.is_file()]
    if missing:
        raise RuntimeError("Missing release payloads: " + ", ".join(missing))
    return sorted(set(files), key=lambda path: str(path.relative_to(ROOT)))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--tag", default=f"v{VERSION}")
    parser.add_argument("--output-dir", default="dist")
    args = parser.parse_args()
    tag = args.tag if args.tag.startswith("v") else f"v{args.tag}"
    output_dir = ROOT / args.output_dir
    output_dir.mkdir(parents=True, exist_ok=True)
    target = output_dir / f"media2md-{tag}.zip"
    files = release_files()
    manifest = {
        "schema_version": 1,
        "version": VERSION,
        "tag": tag,
        "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "files": [str(path.relative_to(ROOT)) for path in files],
        "excludes": ["scripts/backups", "old version payloads", "config", "data", "workspace", "logs", ".venv"],
    }
    with zipfile.ZipFile(target, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for path in files:
            archive.write(path, path.relative_to(ROOT))
        archive.writestr("RELEASE_MANIFEST.json", json.dumps(manifest, ensure_ascii=False, indent=2) + "\n")
    checksum = target.with_suffix(target.suffix + ".sha256")
    checksum.write_text(f"{sha256(target)}  {target.name}\n", encoding="utf-8")
    print(target)
    print(checksum)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
