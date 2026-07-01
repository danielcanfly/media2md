from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _load_registry():
    script_path = ROOT / "src" / "media2md" / "bundle" / "scripts" / "media2md_registry.py"
    spec = importlib.util.spec_from_file_location("media2md_registry_bilibili_identity_merge", script_path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_bilibili_single_media_and_creator_catalog_share_identity(tmp_path, monkeypatch):
    registry = _load_registry()
    monkeypatch.setattr(registry, "DB", tmp_path / "media2md.db")
    monkeypatch.setattr(registry, "CHECKPOINT_DIR", tmp_path / "checkpoints")
    monkeypatch.setattr(registry, "CONFIG", tmp_path / "config.json")
    (tmp_path / "config.json").write_text("{}", encoding="utf-8")

    conn = registry.connect()
    try:
        single = registry.upsert_creator_identity(
            conn,
            "bilibili",
            "史丹福机器人庞博士",
            "史丹福机器人庞博士",
            "史丹福机器人庞博士",
            "https://www.bilibili.com/video/BV1ah4y1M7aQ",
            identifiers={"channel_id": "1510588366"},
        )
        merged = registry.upsert_creator_identity(
            conn,
            "bilibili",
            "1510588366",
            "1510588366",
            "史丹福机器人庞博士",
            "https://space.bilibili.com/1510588366",
            identifiers={"mid": "1510588366"},
        )
        rows = conn.execute(
            "SELECT id, external_id, handle, display_name, source_url FROM creators WHERE provider='bilibili'"
        ).fetchall()
        identifier_rows = conn.execute(
            "SELECT identifier_type, identifier_value FROM creator_identifiers WHERE creator_id=? ORDER BY identifier_type",
            (int(merged["id"]),),
        ).fetchall()
    finally:
        conn.close()

    assert int(single["id"]) == int(merged["id"])
    assert len(rows) == 1
    assert rows[0]["external_id"] == "1510588366"
    assert rows[0]["handle"] == "1510588366"
    assert rows[0]["display_name"] == "史丹福机器人庞博士"
    assert rows[0]["source_url"] == "https://space.bilibili.com/1510588366"
    assert {row["identifier_type"]: row["identifier_value"] for row in identifier_rows} == {
        "channel_id": "1510588366",
        "mid": "1510588366",
        "primary": "1510588366",
    }


def test_bilibili_legacy_like_single_media_refresh_does_not_downgrade_space_identity(tmp_path, monkeypatch):
    registry = _load_registry()
    monkeypatch.setattr(registry, "DB", tmp_path / "media2md.db")
    monkeypatch.setattr(registry, "CHECKPOINT_DIR", tmp_path / "checkpoints")
    monkeypatch.setattr(registry, "CONFIG", tmp_path / "config.json")
    (tmp_path / "config.json").write_text("{}", encoding="utf-8")

    conn = registry.connect()
    try:
        creator = registry.upsert_creator_identity(
            conn,
            "bilibili",
            "1510588366",
            "1510588366",
            "史丹福机器人庞博士",
            "https://space.bilibili.com/1510588366",
            identifiers={"mid": "1510588366"},
        )
        refreshed = registry.upsert_creator_identity(
            conn,
            "bilibili",
            "史丹福机器人庞博士",
            "史丹福机器人庞博士",
            "史丹福机器人庞博士",
            "https://www.bilibili.com/video/BV1ah4y1M7aQ",
            identifiers={"channel_id": "1510588366"},
        )
        row = conn.execute(
            "SELECT external_id, handle, display_name, source_url FROM creators WHERE id=?",
            (int(creator["id"]),),
        ).fetchone()
    finally:
        conn.close()

    assert int(refreshed["id"]) == int(creator["id"])
    assert row["external_id"] == "1510588366"
    assert row["handle"] == "1510588366"
    assert row["display_name"] == "史丹福机器人庞博士"
    assert row["source_url"] == "https://space.bilibili.com/1510588366"
