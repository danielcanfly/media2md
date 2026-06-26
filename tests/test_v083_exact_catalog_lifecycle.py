from __future__ import annotations

import importlib.util
import sqlite3
from pathlib import Path


def _meta() -> dict:
    sec_uid = "MS4wLjABAAAA_EXACT_LIFECYCLE_TEST"
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


def _prepare_registry(tmp_path: Path, monkeypatch):
    import media2md_registry as registry

    monkeypatch.setattr(registry, "DB", tmp_path / "media2md.db")
    monkeypatch.setattr(registry, "CHECKPOINT_DIR", tmp_path / "checkpoints")
    monkeypatch.setattr(registry, "CONFIG", tmp_path / "config.json")
    (tmp_path / "config.json").write_text("{}", encoding="utf-8")
    registry.CHECKPOINT_DIR.mkdir(parents=True, exist_ok=True)
    return registry


def test_quick_sync_does_not_downgrade_exact_tiktok_baseline(tmp_path, monkeypatch):
    registry = _prepare_registry(tmp_path, monkeypatch)
    full = registry.upsert_catalog(
        "tiktok", "startupbell", "https://www.tiktok.com/@startupbell",
        [_item("1", "2026-06-23T00:00:00+00:00"), _item("2", "2026-06-22T00:00:00+00:00")],
        _meta(), "full", exact=True,
    )
    assert full["current_total_exact"] is True
    assert full["media_type_totals_exact"] == {"tiktok_video": True}

    quick = registry.upsert_catalog(
        "tiktok", "startupbell", "https://www.tiktok.com/@startupbell",
        [_item("3", "2026-06-24T00:00:00+00:00")],
        _meta(), "quick", exact=False,
    )
    assert quick["previous_current_total"] == 2
    assert quick["current_total"] == 3
    assert quick["new_since_last_sync"] == 1
    assert quick["current_total_exact"] is True
    assert quick["media_type_totals_exact"] == {"tiktok_video": True}
    assert quick["last_full_exact_total"] == 2
    assert quick["last_full_media_type_totals"]["tiktok_video"] == 2


def test_exact_tiktok_catalog_skips_hidden_quick_sync(capsys):
    from creator_run_shared import prepare_catalog_for_creator_run

    calls: list[list[str]] = []
    result = prepare_catalog_for_creator_run(
        provider="tiktok",
        creator_arg="@startupbell",
        normalized_creator="startupbell",
        existing_row={"tracked": 1159, "current_total_exact": 1},
        quick_window=100,
        output="human",
        registry_call=lambda command: calls.append(command) or 0,
        emit_call=lambda payload, output: None,
    )
    output = capsys.readouterr().out
    assert result == 0
    assert calls == []
    assert "AUTO_SYNC_SKIPPED provider=tiktok" in output
    assert "reason=exact_catalog_available" in output
    assert "current_total_exact=true" in output


def test_force_full_after_exact_completion_bootstraps_fresh_cursor_scan(tmp_path, monkeypatch, capsys):
    registry = _prepare_registry(tmp_path, monkeypatch)
    items = [
        _item("10", "2026-06-23T00:00:00+00:00"),
        _item("11", "2026-06-22T00:00:00+00:00"),
    ]
    registry.upsert_catalog(
        "tiktok", "startupbell", "https://www.tiktok.com/@startupbell",
        items, _meta(), "full", exact=True,
    )
    checkpoint = registry.CHECKPOINT_DIR / "tiktok-startupbell.json"
    assert not checkpoint.exists()
    monkeypatch.setenv("MEDIA2MD_TIKTOK_CURSOR_BACKEND", "1")
    monkeypatch.setenv("MEDIA2MD_TIKTOK_SYNC_MAX_PAGES_PER_RUN", "4")
    monkeypatch.setattr(registry.time, "time", lambda: 1_750_000_000.0)

    raw = [
        {
            "id": "10", "desc": "10", "createTime": 1_750_000_000,
            "author": {"id": "7353505829380916257", "uniqueId": "startupbell", "nickname": "Startup Bell"},
            "video": {"duration": 30},
        },
        {
            "id": "11", "desc": "11", "createTime": 1_749_999_000,
            "author": {"id": "7353505829380916257", "uniqueId": "startupbell", "nickname": "Startup Bell"},
            "video": {"duration": 30},
        },
    ]
    monkeypatch.setattr(
        registry,
        "_run_tiktok_cursor_request",
        lambda *args, **kwargs: ({"itemList": raw, "hasMorePrevious": False}, False),
    )
    monkeypatch.setattr(
        registry,
        "extract_catalog",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("legacy extractor must not run")),
    )
    result = registry.sync_creator("tiktok", "@startupbell", mode="full")
    output = capsys.readouterr().out
    assert "SYNC_CURSOR_BOOTSTRAP provider=tiktok source=registry" in output
    assert "SYNC_CURSOR_COMPLETE" in output
    assert result["previous_current_total"] == 2
    assert result["current_total"] == 2
    assert result["new_since_last_sync"] == 0
    assert result["removed_since_last_sync"] == 0
    assert result["current_total_exact"] is True
    assert result["last_full_exact_total"] == 2
    assert not checkpoint.exists()


def test_installer_repairs_only_matching_tiktok_exact_snapshot(tmp_path):
    root = Path(__file__).resolve().parents[1]
    installer_path = root / "docs" / "archive" / "installers" / "install_media2md_v083.py"
    spec = importlib.util.spec_from_file_location("installer_v083", installer_path)
    assert spec and spec.loader
    installer = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(installer)

    db = tmp_path / "data" / "media2md.db"
    db.parent.mkdir(parents=True)
    conn = sqlite3.connect(db)
    conn.executescript(
        """
        CREATE TABLE creators (
            id INTEGER PRIMARY KEY,
            provider TEXT,
            current_total INTEGER,
            current_total_exact INTEGER,
            last_full_exact_total INTEGER,
            last_full_exact_at TEXT,
            updated_at TEXT
        );
        INSERT INTO creators VALUES (1,'tiktok',1159,0,1159,'2026-06-24T17:31:01+00:00','old');
        INSERT INTO creators VALUES (2,'tiktok',1160,0,1159,'2026-06-24T17:31:01+00:00','old');
        INSERT INTO creators VALUES (3,'youtube',1159,0,1159,'2026-06-24T17:31:01+00:00','old');
        """
    )
    conn.commit()
    conn.close()

    assert installer.repair_tiktok_exact_state(tmp_path) == 1
    conn = sqlite3.connect(db)
    rows = conn.execute("SELECT id,current_total_exact FROM creators ORDER BY id").fetchall()
    conn.close()
    assert rows == [(1, 1), (2, 0), (3, 0)]
