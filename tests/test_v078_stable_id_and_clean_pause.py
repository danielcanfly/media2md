from __future__ import annotations

import json


def _item(index: int) -> dict:
    media_id = str(7500000000000000000 + index)
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


def test_stable_id_success_reuses_known_handle_without_second_profile_fetch(monkeypatch, capsys):
    import media2md_registry as registry

    monkeypatch.setenv("MEDIA2MD_TIKTOK_CURSOR_BACKEND", "0")

    calls: list[str] = []

    def fake_run(common, source_url, **kwargs):
        calls.append(source_url)
        return {
            "id": "MS4wLjABAAAA_STABLE",
            "channel_id": "MS4wLjABAAAA_STABLE",
            # Stable tiktokuser payload intentionally has no uploader/channel handle.
            "entries": [
                {
                    "id": "7500000000000000001",
                    "title": "fixture",
                    "url": "https://www.tiktok.com/@startupbell/video/7500000000000000001",
                }
            ],
        }, "latest:Chrome-146", False

    monkeypatch.setattr(registry, "command", lambda name: name)
    monkeypatch.setattr(registry, "_run_tiktok_catalog", fake_run)
    meta, items, catalog_source = registry._extract_tiktok_page(
        "https://www.tiktok.com/@startupbell", 25, 376, ["MS4wLjABAAAA_STABLE"]
    )

    assert calls == ["tiktokuser:MS4wLjABAAAA_STABLE"]
    assert catalog_source == "tiktokuser:MS4wLjABAAAA_STABLE"
    assert meta["handle"] == "startupbell"
    assert meta["source_url"] == "https://www.tiktok.com/@startupbell"
    assert len(items) == 1
    output = capsys.readouterr().out
    assert "SYNC_STABLE_ID_HANDLE_REUSED" in output
    assert "second_profile_fetch=false" in output


def test_page_budget_exhaustion_returns_clean_resumable_pause(tmp_path, monkeypatch, capsys):
    import media2md_registry as registry

    monkeypatch.setenv("MEDIA2MD_TIKTOK_CURSOR_BACKEND", "0")

    monkeypatch.setattr(registry, "DB", tmp_path / "media2md.db")
    monkeypatch.setattr(registry, "CHECKPOINT_DIR", tmp_path / "checkpoints")
    monkeypatch.setattr(registry, "CONFIG", tmp_path / "config.json")
    (tmp_path / "config.json").write_text("{}")
    monkeypatch.setenv("MEDIA2MD_TIKTOK_SYNC_PAGE_SIZE", "25")
    monkeypatch.setenv("MEDIA2MD_TIKTOK_SYNC_MAX_PAGES_PER_RUN", "4")

    registry.CHECKPOINT_DIR.mkdir(parents=True)
    checkpoint = {
        "schema_version": 3,
        "provider": "tiktok",
        "creator": "startupbell",
        "source_url": "https://www.tiktok.com/@startupbell",
        "catalog_source": "tiktokuser:MS4wLjABAAAA_STABLE",
        "mode": "full",
        "meta": {
            "external_id": "MS4wLjABAAAA_STABLE",
            "identifiers": {"sec_uid": "MS4wLjABAAAA_STABLE"},
            "handle": "startupbell",
            "display_name": "Startup Bell",
            "source_url": "https://www.tiktok.com/@startupbell",
        },
        "tiktok_identifiers": ["MS4wLjABAAAA_STABLE"],
        "items": [_item(1)],
        "next_start": 376,
        "updated_at": "2026-06-24T00:00:00+00:00",
    }
    checkpoint_path = registry.CHECKPOINT_DIR / "tiktok-startupbell.json"
    checkpoint_path.write_text(json.dumps(checkpoint))

    monkeypatch.setattr(
        registry,
        "_extract_tiktok_page",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            RuntimeError("TikTok page extraction failed within bounded page budget. range=376-400")
        ),
    )

    result = registry.sync_creator("tiktok", "@startupbell", mode="full")

    assert result["sync_incomplete"] is True
    assert result["pause_reason"] == "page_budget_exhausted"
    assert result["resume_from"] == 376
    assert checkpoint_path.is_file()
    saved = json.loads(checkpoint_path.read_text())
    assert saved["next_start"] == 376
    assert len(saved["items"]) == 1
    output = capsys.readouterr()
    assert "SYNC_RUN_PAUSED provider=tiktok reason=page_budget_exhausted" in output.out
    assert "SYNC_PARTIAL_CATALOG_PRESERVED" in output.err


def test_v078_release_docs_capture_live_regression():
    from pathlib import Path

    root = Path(__file__).resolve().parents[1]
    text = (root / "STRICT_ACCEPTANCE_V078.md").read_text()
    assert "stable-ID" in text
    assert "page_budget_exhausted" in text
    assert "second_profile_fetch=false" in text
