from __future__ import annotations

import json
import subprocess
from datetime import datetime, timezone


def _item(index: int, timestamp: int) -> dict:
    media_id = str(7700000000000000000 + index)
    return {
        "external_id": media_id,
        "title": media_id,
        "description": "",
        "source_url": f"https://www.tiktok.com/@startupbell/video/{media_id}",
        "published_at": datetime.fromtimestamp(timestamp, tz=timezone.utc).isoformat(timespec="seconds"),
        "duration_seconds": 30,
        "media_type": "tiktok_video",
        "processing_class": "tiktok_video",
    }


def _raw(index: int, timestamp: int) -> dict:
    return {
        "id": str(7800000000000000000 + index),
        "desc": f"post {index}",
        "createTime": timestamp,
        "author": {
            "id": "1234567890",
            "uniqueId": "startupbell",
            "nickname": "Startup Bell",
        },
        "video": {"duration": 30},
    }


def _checkpoint(items: list[dict]) -> dict:
    sec_uid = "MS4wLjABAAAA_CURSOR_TEST"
    return {
        "schema_version": 4,
        "provider": "tiktok",
        "creator": "startupbell",
        "source_url": "https://www.tiktok.com/@startupbell",
        "mode": "full",
        "meta": {
            "external_id": sec_uid,
            "identifiers": {"sec_uid": sec_uid},
            "handle": "startupbell",
            "display_name": "Startup Bell",
            "source_url": "https://www.tiktok.com/@startupbell",
        },
        "tiktok_identifiers": [sec_uid],
        "items": items,
        "next_start": len(items) + 1,
        "updated_at": "2026-06-24T00:00:00+00:00",
    }


def _prepare(tmp_path, monkeypatch, items):
    import media2md_registry as registry

    monkeypatch.setattr(registry, "DB", tmp_path / "media2md.db")
    monkeypatch.setattr(registry, "CHECKPOINT_DIR", tmp_path / "checkpoints")
    monkeypatch.setattr(registry, "CONFIG", tmp_path / "config.json")
    (tmp_path / "config.json").write_text("{}")
    registry.CHECKPOINT_DIR.mkdir(parents=True)
    path = registry.CHECKPOINT_DIR / "tiktok-startupbell.json"
    path.write_text(json.dumps(_checkpoint(items)))
    monkeypatch.setenv("MEDIA2MD_TIKTOK_CURSOR_BACKEND", "1")
    monkeypatch.setenv("MEDIA2MD_TIKTOK_SYNC_MAX_RUNTIME_SECONDS", "1800")
    return registry, path


def test_cursor_is_recovered_from_oldest_known_item():
    import media2md_registry as registry

    items = [_item(1, 1_720_000_000), _item(2, 1_710_000_000)]
    assert registry._tiktok_cursor_from_items(items) == 1_710_000_000_000


def test_resumed_catalog_uses_cursor_api_and_finishes_exact(tmp_path, monkeypatch, capsys):
    items = [_item(i, 1_720_000_000 - i * 60) for i in range(3)]
    registry, checkpoint_path = _prepare(tmp_path, monkeypatch, items)
    monkeypatch.setenv("MEDIA2MD_TIKTOK_SYNC_MAX_PAGES_PER_RUN", "4")
    calls = []

    def fake_request(sec_uid, cursor, count, device_id, source_url, *, timeout_seconds):
        calls.append((sec_uid, cursor, count, device_id, source_url, timeout_seconds))
        return ({"itemList": [_raw(10, 1_719_999_000), _raw(11, 1_719_998_000)], "hasMorePrevious": False}, False)

    monkeypatch.setattr(registry, "_run_tiktok_cursor_request", fake_request)
    monkeypatch.setattr(registry, "_extract_tiktok_page", lambda *a, **k: (_ for _ in ()).throw(AssertionError("legacy deep pagination must not run")))

    result = registry.sync_creator("tiktok", "@startupbell", mode="full")

    assert result["current_total_exact"] is True
    assert result["current_total"] == 5
    assert result["pagination_backend"] == "cursor_api"
    assert len(calls) == 1
    assert calls[0][1] == registry._tiktok_cursor_from_items(items)
    assert not checkpoint_path.exists()
    output = capsys.readouterr().out
    assert "SYNC_CURSOR_MODE" in output
    assert "SYNC_CURSOR_COMPLETE" in output


def test_cursor_checkpoint_persists_and_resumes_without_playlist_start(tmp_path, monkeypatch):
    items = [_item(i, 1_720_000_000 - i * 60) for i in range(3)]
    registry, checkpoint_path = _prepare(tmp_path, monkeypatch, items)
    monkeypatch.setenv("MEDIA2MD_TIKTOK_SYNC_MAX_PAGES_PER_RUN", "1")

    def fake_request(sec_uid, cursor, count, device_id, source_url, *, timeout_seconds):
        return ({"itemList": [_raw(20, 1_719_990_000)], "hasMorePrevious": True}, True)

    monkeypatch.setattr(registry, "_run_tiktok_cursor_request", fake_request)
    result = registry.sync_creator("tiktok", "@startupbell", mode="full")

    saved = json.loads(checkpoint_path.read_text())
    assert result["pause_reason"] == "max_pages_per_run"
    assert result["pagination_backend"] == "cursor_api"
    assert saved["schema_version"] == 5
    assert saved["pagination_backend"] == "cursor_api"
    assert saved["tiktok_cursor"] == 1_719_990_000_000
    assert saved["next_start"] == 5
    assert saved["tiktok_device_id"]


def test_native_cursor_request_forces_direct_network_and_cursor(monkeypatch):
    import media2md_registry as registry

    captured = {}
    monkeypatch.setattr(registry, "command", lambda name: "/usr/bin/curl")
    monkeypatch.setattr(registry, "auth_args", lambda provider: [])
    monkeypatch.setattr(registry, "_proxy_environment", lambda: ({"PATH": "/usr/bin"}, ["HTTP_PROXY"]))

    def fake_capture(command, timeout, **kwargs):
        captured["command"] = command
        captured["env"] = kwargs.get("env")
        return subprocess.CompletedProcess(command, 0, json.dumps({"itemList": [], "hasMorePrevious": False}), "")

    monkeypatch.setattr(registry, "_capture_process", fake_capture)
    payload, authenticated = registry._run_tiktok_cursor_request(
        "MS4wLjABAAAA_CURSOR_TEST", 1_700_000_000_000, 15, "7250000000000000001",
        "https://www.tiktok.com/@startupbell", timeout_seconds=60,
    )

    command = captured["command"]
    assert authenticated is False
    assert payload["hasMorePrevious"] is False
    assert "--noproxy" in command and "*" in command
    url = command[-1]
    assert "creator/item_list" in url
    assert "cursor=1700000000000" in url
    assert "secUid=MS4wLjABAAAA_CURSOR_TEST" in url
    assert captured["env"] == {"PATH": "/usr/bin"}


def test_v080_acceptance_documents_cursor_architecture():
    from pathlib import Path

    root = Path(__file__).resolve().parents[1]
    text = (root / "docs" / "archive" / "acceptance" / "STRICT_ACCEPTANCE_V080.md").read_text()
    assert "cursor API" in text
    assert "--playlist-start" in text
    assert "SYNC_CURSOR_MODE" in text
    assert "tiktok_cursor" in text
