from __future__ import annotations

import json
from pathlib import Path


def _meta() -> dict:
    sec_uid = "MS4wLjABAAAA_STAGED_REBUILD_TEST"
    return {
        "external_id": sec_uid,
        "handle": "startupbell",
        "display_name": "Startup Bell",
        "source_url": "https://www.tiktok.com/@startupbell",
        "identifiers": {"primary": sec_uid, "sec_uid": sec_uid, "user_id": "7353505829380916257"},
    }


def _item(media_id: str, published_at: str) -> dict:
    return {
        "external_id": media_id,
        "title": media_id,
        "description": "",
        "source_url": f"https://www.tiktok.com/@startupbell/video/{media_id}",
        "published_at": published_at,
        "duration_seconds": 30,
        "media_type": "tiktok_video",
        "processing_class": "tiktok_video",
    }


def _raw(media_id: str, create_time: int) -> dict:
    return {
        "id": media_id,
        "desc": media_id,
        "createTime": create_time,
        "author": {
            "id": "7353505829380916257",
            "uniqueId": "startupbell",
            "nickname": "Startup Bell",
        },
        "video": {"duration": 30},
    }


def _prepare_registry(tmp_path: Path, monkeypatch):
    import media2md_registry as registry

    monkeypatch.setattr(registry, "DB", tmp_path / "media2md.db")
    monkeypatch.setattr(registry, "CHECKPOINT_DIR", tmp_path / "checkpoints")
    monkeypatch.setattr(registry, "TIKTOK_CURSOR_STATE", tmp_path / "checkpoints" / "tiktok-cursor-state.json")
    monkeypatch.setattr(registry, "CONFIG", tmp_path / "config.json")
    (tmp_path / "config.json").write_text("{}", encoding="utf-8")
    registry.CHECKPOINT_DIR.mkdir(parents=True, exist_ok=True)
    return registry


def _seed_exact(registry):
    return registry.upsert_catalog(
        "tiktok",
        "startupbell",
        "https://www.tiktok.com/@startupbell",
        [_item("10", "2026-06-23T00:00:00+00:00"), _item("11", "2026-06-22T00:00:00+00:00")],
        _meta(),
        "full",
        exact=True,
    )


def test_fresh_exact_rebuild_request_failure_preserves_active_catalog(tmp_path, monkeypatch, capsys):
    registry = _prepare_registry(tmp_path, monkeypatch)
    _seed_exact(registry)
    monkeypatch.setenv("MEDIA2MD_TIKTOK_CURSOR_BACKEND", "1")
    monkeypatch.setenv("MEDIA2MD_TIKTOK_SYNC_MAX_PAGES_PER_RUN", "12")
    monkeypatch.setattr(registry.time, "time", lambda: 1_780_000_000.0)
    monkeypatch.setattr(
        registry,
        "_run_tiktok_cursor_request",
        lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("HTTP 403")),
    )

    result = registry.sync_creator("tiktok", "@startupbell", mode="full")
    output = capsys.readouterr().out

    assert "SYNC_CURSOR_BOOTSTRAP" in output
    assert "baseline_exact=true" in output
    assert "SYNC_RUN_PAUSED" in output
    assert "baseline_preserved=true" in output
    assert result["pause_reason"] == "cursor_request_failed"
    assert result["current_total"] == 2
    assert result["current_total_exact"] is True
    assert result["baseline_preserved"] is True
    assert result["rebuild_in_progress"] is True
    assert result["staged_total"] == 0

    conn = registry.connect()
    creator = conn.execute(
        "SELECT current_total,current_total_exact,last_full_exact_total FROM creators "
        "WHERE provider='tiktok' AND handle='startupbell'"
    ).fetchone()
    current_ids = {
        row[0]
        for row in conn.execute(
            "SELECT external_id FROM media WHERE is_current=1 ORDER BY external_id"
        ).fetchall()
    }
    conn.close()
    assert tuple(creator) == (2, 1, 2)
    assert current_ids == {"10", "11"}

    checkpoint = json.loads((registry.CHECKPOINT_DIR / "tiktok-startupbell.json").read_text(encoding="utf-8"))
    assert checkpoint["rebuild_from_exact"] is True
    assert checkpoint["items"] == []


def test_partial_exact_rebuild_stages_pages_without_publishing_them(tmp_path, monkeypatch, capsys):
    registry = _prepare_registry(tmp_path, monkeypatch)
    _seed_exact(registry)
    monkeypatch.setenv("MEDIA2MD_TIKTOK_CURSOR_BACKEND", "1")
    monkeypatch.setenv("MEDIA2MD_TIKTOK_SYNC_MAX_PAGES_PER_RUN", "1")
    monkeypatch.setattr(registry.time, "time", lambda: 1_780_000_000.0)
    monkeypatch.setattr(
        registry,
        "_run_tiktok_cursor_request",
        lambda *args, **kwargs: ({"itemList": [_raw("20", 1_779_999_000)], "hasMorePrevious": True}, False),
    )

    result = registry.sync_creator("tiktok", "@startupbell", mode="full")
    output = capsys.readouterr().out

    assert "SYNC_CURSOR_PAGE_DONE" in output
    assert "staged_rebuild=true" in output
    assert result["pause_reason"] == "max_pages_per_run"
    assert result["current_total"] == 2
    assert result["current_total_exact"] is True
    assert result["staged_total"] == 1
    assert result["baseline_preserved"] is True

    conn = registry.connect()
    current_ids = {
        row[0]
        for row in conn.execute(
            "SELECT external_id FROM media WHERE is_current=1 ORDER BY external_id"
        ).fetchall()
    }
    conn.close()
    assert current_ids == {"10", "11"}

    checkpoint = json.loads((registry.CHECKPOINT_DIR / "tiktok-startupbell.json").read_text(encoding="utf-8"))
    assert checkpoint["rebuild_from_exact"] is True
    assert [item["external_id"] for item in checkpoint["items"]] == ["20"]


def test_completed_cursor_run_persists_device_id_for_next_rebuild(tmp_path, monkeypatch):
    registry = _prepare_registry(tmp_path, monkeypatch)
    _seed_exact(registry)
    registry._save_tiktok_cursor_state("startupbell", device_id="stable-device-123", authenticated=False)
    monkeypatch.setenv("MEDIA2MD_TIKTOK_CURSOR_BACKEND", "1")
    monkeypatch.setenv("MEDIA2MD_TIKTOK_SYNC_MAX_PAGES_PER_RUN", "1")
    monkeypatch.setattr(registry.time, "time", lambda: 1_780_000_000.0)
    captured: dict[str, str] = {}

    def fail_after_capture(sec_uid, cursor, count, device_id, source_url, timeout_seconds):
        captured["device_id"] = device_id
        raise RuntimeError("HTTP 403")

    monkeypatch.setattr(registry, "_run_tiktok_cursor_request", fail_after_capture)
    registry.sync_creator("tiktok", "@startupbell", mode="full")
    assert captured["device_id"] == "stable-device-123"


def test_retryable_failed_item_remains_in_actual_remaining_count(tmp_path, monkeypatch):
    registry = _prepare_registry(tmp_path, monkeypatch)
    _seed_exact(registry)
    conn = registry.connect()
    creator = conn.execute(
        "SELECT id FROM creators WHERE provider='tiktok' AND handle='startupbell'"
    ).fetchone()
    conn.execute(
        "UPDATE media SET status='completed' WHERE creator_id=? AND external_id='10'",
        (creator["id"],),
    )
    conn.execute(
        "UPDATE media SET status='failed' WHERE creator_id=? AND external_id='11'",
        (creator["id"],),
    )
    conn.commit()
    conn.close()
    assert registry._actual_creator_remaining("tiktok", "startupbell") == 1


def test_installer_repairs_exact_and_migrates_cursor_device_state(tmp_path):
    import importlib.util
    import sqlite3

    root = Path(__file__).resolve().parents[1]
    installer_path = root / "install_media2md_v084.py"
    spec = importlib.util.spec_from_file_location("installer_v084", installer_path)
    assert spec and spec.loader
    installer = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(installer)

    db = tmp_path / "data" / "media2md.db"
    checkpoint_dir = tmp_path / "data" / "provider_catalog_checkpoints"
    checkpoint_dir.mkdir(parents=True)
    conn = sqlite3.connect(db)
    conn.executescript(
        """
        CREATE TABLE creators (
            id INTEGER PRIMARY KEY,
            provider TEXT,
            handle TEXT,
            current_total INTEGER,
            current_total_exact INTEGER,
            last_full_exact_total INTEGER,
            last_full_exact_at TEXT,
            updated_at TEXT
        );
        INSERT INTO creators VALUES (
            1,'tiktok','startupbell',1159,0,1159,
            '2026-06-24T17:31:01+00:00','old'
        );
        """
    )
    conn.commit()
    conn.close()

    checkpoint = checkpoint_dir / "tiktok-startupbell.json"
    checkpoint.write_text(json.dumps({
        "schema_version": 5,
        "provider": "tiktok",
        "creator": "startupbell",
        "mode": "full",
        "items": [],
        "tiktok_device_id": "stable-device-456",
        "preferred_authenticated": False,
        "pagination_backend": "cursor_api",
    }), encoding="utf-8")

    assert installer.repair_tiktok_exact_state(tmp_path) == 1
    migrated, staged = installer.migrate_tiktok_cursor_state(tmp_path)
    assert migrated == 1
    assert staged == 1

    state = json.loads((checkpoint_dir / "tiktok-cursor-state.json").read_text(encoding="utf-8"))
    assert state["creators"]["startupbell"]["device_id"] == "stable-device-456"
    updated_checkpoint = json.loads(checkpoint.read_text(encoding="utf-8"))
    assert updated_checkpoint["rebuild_from_exact"] is True


def test_v084_acceptance_documents_staged_rebuild_contract():
    root = Path(__file__).resolve().parents[1]
    text = (root / "STRICT_ACCEPTANCE_V084.md").read_text(encoding="utf-8")
    for token in (
        "baseline_preserved",
        "rebuild_in_progress",
        "staged_total",
        "device ID",
        "retryable failed items",
    ):
        assert token.lower() in text.lower()
