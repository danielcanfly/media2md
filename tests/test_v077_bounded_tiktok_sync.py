from __future__ import annotations

import json
import time


def _item(index: int) -> dict:
    media_id = str(7400000000000000000 + index)
    return {
        "external_id": media_id,
        "title": media_id,
        "description": "",
        "source_url": f"https://www.tiktok.com/@startupbell/video/{media_id}",
        "published_at": "2026-06-24T00:00:00+00:00",
        "duration_seconds": 30,
        "media_type": "tiktok_video",
        "processing_class": "tiktok_video",
    }


def test_tiktok_page_candidates_share_one_deadline_and_no_nested_fallback(monkeypatch):
    import media2md_registry as registry

    calls = []

    def fake_extract(provider, source_url, limit, start, **kwargs):
        calls.append((source_url, kwargs.get("tiktok_deadline"), kwargs.get("emit_network_context")))
        if source_url.startswith("tiktokuser:"):
            raise RuntimeError("stable target unavailable")
        return {
            "external_id": "SEC",
            "handle": "startupbell",
            "display_name": "Startup Bell",
            "identifiers": {"sec_uid": "SEC"},
        }, [_item(1)]

    monkeypatch.setattr(registry, "_extract_catalog_once", fake_extract)
    meta, items, source = registry._extract_tiktok_page(
        "https://www.tiktok.com/@startupbell", 25, 201, ["SEC"]
    )
    assert len(calls) == 2
    assert calls[0][1] == calls[1][1]
    assert calls[0][2] is True
    assert calls[1][2] is False
    assert source == "https://www.tiktok.com/@startupbell"
    assert len(items) == 1


def test_tiktok_sync_pauses_after_page_budget_and_keeps_checkpoint(tmp_path, monkeypatch):
    import media2md_registry as registry

    monkeypatch.setattr(registry, "DB", tmp_path / "media2md.db")
    monkeypatch.setattr(registry, "CHECKPOINT_DIR", tmp_path / "checkpoints")
    monkeypatch.setattr(registry, "CONFIG", tmp_path / "config.json")
    (tmp_path / "config.json").write_text("{}")
    monkeypatch.setenv("MEDIA2MD_TIKTOK_SYNC_PAGE_SIZE", "25")
    monkeypatch.setenv("MEDIA2MD_TIKTOK_SYNC_MAX_PAGES_PER_RUN", "1")

    meta = {
        "external_id": "SEC",
        "handle": "startupbell",
        "display_name": "Startup Bell",
        "identifiers": {"sec_uid": "SEC"},
    }

    monkeypatch.setattr(
        registry,
        "_extract_tiktok_page",
        lambda *args, **kwargs: (meta, [_item(i) for i in range(25)], "https://www.tiktok.com/@startupbell"),
    )

    result = registry.sync_creator("tiktok", "@startupbell", mode="full")
    assert result["sync_incomplete"] is True
    assert result["pause_reason"] == "max_pages_per_run"
    assert result["resume_from"] == 26
    checkpoint = json.loads((registry.CHECKPOINT_DIR / "tiktok-startupbell.json").read_text())
    assert checkpoint["next_start"] == 26
    assert len(checkpoint["items"]) == 25


def test_tiktok_transport_uses_shared_page_deadline(monkeypatch):
    import media2md_registry as registry

    monkeypatch.setattr(
        registry,
        "_tiktok_transport_strategies",
        lambda: [
            ("configured:chrome", ["--ignore-config", "--impersonate", "chrome"], False),
            ("direct-plain", ["--ignore-config", "--proxy", ""], True),
        ],
    )
    monkeypatch.setattr(registry, "auth_args", lambda provider: [])
    seen_timeouts = []

    def fake_run_json(command_line, **kwargs):
        seen_timeouts.append(kwargs["timeout"])
        if len(seen_timeouts) == 1:
            raise RuntimeError("curl: (35) TLS connect error")
        return {"entries": []}

    monkeypatch.setattr(registry, "run_json", fake_run_json)
    deadline = time.monotonic() + 40
    payload, strategy, authenticated = registry._run_tiktok_catalog(
        ["yt-dlp", "--dump-single-json"],
        "https://www.tiktok.com/@startupbell",
        deadline=deadline,
        context="range=201-225 candidate=handle",
    )
    assert payload == {"entries": []}
    assert strategy == "direct-plain"
    assert authenticated is False
    assert all(5 <= value <= 40 for value in seen_timeouts)


def test_waiting_output_replaces_restarting_heartbeat_label():
    from pathlib import Path

    root = Path(__file__).resolve().parents[1]
    text = (root / "src" / "media2md" / "bundle" / "scripts" / "media2md_registry.py").read_text()
    assert "SYNC_WAITING" in text
    assert "f\"SYNC_HEARTBEAT " not in text
    assert "MEDIA2MD_TIKTOK_PAGE_BUDGET_SECONDS" in text
    assert "MEDIA2MD_TIKTOK_SYNC_MAX_RUNTIME_SECONDS" in text
