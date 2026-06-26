from __future__ import annotations

import json
import sqlite3
import zipfile
from pathlib import Path


def test_backup_accepts_zero_byte_files_and_excludes_runtime_locks(tmp_path, monkeypatch):
    import media2md_backup as backup
    import media2md_runtime as runtime

    lock_dir = tmp_path / "locks"
    monkeypatch.setattr(runtime, "LOCK_DIR", lock_dir)
    monkeypatch.setattr(runtime, "MAINTENANCE_LOCK_PATH", lock_dir / "maintenance.lock")

    project = tmp_path / "project"
    (project / "config").mkdir(parents=True)
    (project / "data" / "provider_catalog_checkpoints").mkdir(parents=True)

    # This reproduces the live v0.8.5 failure: .creators.lock is a legitimate
    # zero-byte operational artifact, but it must not be part of a portable backup.
    (project / "config" / ".creators.lock").write_bytes(b"")
    (project / "config" / "empty-marker.txt").write_bytes(b"")
    (project / "config" / "social2md.json").write_text(
        '{"timezone":"Asia/Tokyo"}\n', encoding="utf-8"
    )
    (project / "data" / "provider_catalog_checkpoints" / "item.part").write_text(
        "partial", encoding="utf-8"
    )
    (project / "data" / "provider_catalog_checkpoints" / "tiktok-startupbell.json").write_text(
        json.dumps({"creator": "startupbell", "items": ["1"]}), encoding="utf-8"
    )

    db = project / "data" / "media2md.db"
    conn = sqlite3.connect(db)
    conn.execute("CREATE TABLE media(id INTEGER PRIMARY KEY, external_id TEXT)")
    conn.commit()
    conn.close()

    monkeypatch.setattr(backup, "ROOT", project)
    destination = tmp_path / "backup.zip"
    backup.build_backup(destination)
    verified = backup.verify_backup(destination)

    assert verified["event"] == "backup_verified"
    with zipfile.ZipFile(destination) as archive:
        names = set(archive.namelist())
        assert "media2md-state/config/empty-marker.txt" in names
        assert archive.read("media2md-state/config/empty-marker.txt") == b""
        assert "media2md-state/config/.creators.lock" not in names
        assert "media2md-state/data/provider_catalog_checkpoints/item.part" not in names


def test_release_manifest_contains_no_bundled_runtime_lock_files():
    root = Path(__file__).resolve().parents[1]
    manifest = json.loads((root / "docs" / "archive" / "release" / "RELEASE_MANIFEST_v091.json").read_text(encoding="utf-8"))
    assert not any(
        str(path).startswith("src/media2md/bundle/logs/")
        for path in manifest["files"]
    )
