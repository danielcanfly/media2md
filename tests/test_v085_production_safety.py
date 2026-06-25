from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest


def _isolated_locks(tmp_path: Path, monkeypatch):
    import media2md_runtime as runtime

    lock_dir = tmp_path / "locks"
    monkeypatch.setattr(runtime, "LOCK_DIR", lock_dir)
    monkeypatch.setattr(runtime, "MAINTENANCE_LOCK_PATH", lock_dir / "maintenance.lock")
    return runtime


def test_duplicate_creator_operation_is_rejected_with_owner_metadata(tmp_path, monkeypatch):
    runtime = _isolated_locks(tmp_path, monkeypatch)

    with runtime.operation_lock(
        "creator-run",
        "tiktok-startupbell",
        metadata={"provider": "tiktok", "creator": "startupbell"},
    ):
        with pytest.raises(RuntimeError) as captured:
            with runtime.operation_lock("creator-run", "tiktok-startupbell"):
                pass

    message = str(captured.value)
    assert "operation already running" in message
    assert "scope=creator-run" in message
    assert "creator=startupbell" in message


def test_exclusive_maintenance_is_blocked_by_live_operation(tmp_path, monkeypatch):
    runtime = _isolated_locks(tmp_path, monkeypatch)

    with runtime.operation_lock("creator-sync", "tiktok-startupbell"):
        with pytest.raises(RuntimeError, match="busy with another live or maintenance operation"):
            with runtime.maintenance_lock(exclusive=True, operation="data-backup"):
                pass


def test_registry_run_wrapper_rejects_duplicate_creator_run(tmp_path, monkeypatch):
    runtime = _isolated_locks(tmp_path, monkeypatch)
    import media2md_registry as registry

    called = {"value": False}

    def should_not_run(*args, **kwargs):
        called["value"] = True
        return 0

    monkeypatch.setattr(registry, "_creator_run_unlocked", should_not_run)
    with runtime.operation_lock("creator-run", "tiktok-startupbell"):
        with pytest.raises(RuntimeError, match="operation already running"):
            registry.creator_run(
                "tiktok", "@startupbell", "batch", 1, 1, 1, False,
                0, None, None, None, None, "newest_first", "human", 5, None,
            )
    assert called["value"] is False


def test_state_backup_is_verified_and_excludes_secrets(tmp_path, monkeypatch):
    runtime = _isolated_locks(tmp_path, monkeypatch)
    import media2md_backup as backup

    project = tmp_path / "project"
    (project / "data" / "provider_catalog_checkpoints").mkdir(parents=True)
    (project / "data" / "secrets").mkdir(parents=True)
    (project / "config").mkdir(parents=True)
    (project / "config" / "social2md.json").write_text('{"timezone":"Asia/Tokyo"}\n', encoding="utf-8")
    (project / "data" / "provider_catalog_checkpoints" / "tiktok-startupbell.json").write_text(
        json.dumps({"creator": "startupbell", "items": ["1"]}), encoding="utf-8"
    )
    (project / "data" / "secrets" / "instagram-cookies.txt").write_text("SECRET", encoding="utf-8")

    db = project / "data" / "media2md.db"
    conn = sqlite3.connect(db)
    conn.execute("CREATE TABLE media(id INTEGER PRIMARY KEY, external_id TEXT)")
    conn.execute("INSERT INTO media(external_id) VALUES('7626060966479826198')")
    conn.commit()
    conn.close()

    monkeypatch.setattr(backup, "ROOT", project)
    destination = tmp_path / "backup.zip"
    created = backup.build_backup(destination)
    verified = backup.verify_backup(destination)

    assert created["event"] == "backup_created"
    assert verified["event"] == "backup_verified"
    assert verified["databases"] == ["media2md.db"]
    assert verified["secrets_included"] is False

    import zipfile
    with zipfile.ZipFile(destination) as archive:
        names = set(archive.namelist())
        assert "media2md-state/data/media2md.db" in names
        assert "media2md-state/config/social2md.json" in names
        assert "media2md-state/data/provider_catalog_checkpoints/tiktok-startupbell.json" in names
        assert all("secrets" not in name for name in names)


def test_public_cli_exposes_backup_and_verify_commands():
    import importlib.util

    script = Path(__file__).resolve().parents[1] / "src" / "media2md" / "bundle" / "scripts" / "media2md.py"
    spec = importlib.util.spec_from_file_location("media2md_public_script_v085", script)
    assert spec and spec.loader
    public_cli = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(public_cli)
    parser = public_cli.parser()
    backup = parser.parse_args(["data", "backup", "--destination", "/tmp/state.zip"])
    verify = parser.parse_args(["data", "verify-backup", "/tmp/state.zip"])
    assert backup.data_command == "backup"
    assert verify.data_command == "verify-backup"
