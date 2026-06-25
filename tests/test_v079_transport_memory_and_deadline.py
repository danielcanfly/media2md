from __future__ import annotations

import json
import time


def _item(index: int) -> dict:
    media_id = str(7600000000000000000 + index)
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


def _checkpoint(items: list[dict], *, next_start: int = 476) -> dict:
    sec_uid = "MS4wLjABAAAA_PERSISTED"
    return {
        "schema_version": 4,
        "provider": "tiktok",
        "creator": "startupbell",
        "source_url": "https://www.tiktok.com/@startupbell",
        "catalog_source": f"tiktokuser:{sec_uid}",
        "mode": "full",
        "meta": {
            "external_id": sec_uid,
            "identifiers": {"sec_uid": sec_uid},
            "handle": "startupbell",
            "display_name": "Startup Bell",
            "source_url": "https://www.tiktok.com/@startupbell",
        },
        "tiktok_identifiers": [sec_uid],
        "preferred_transport": "direct-plain",
        "preferred_authenticated": False,
        "items": items,
        "next_start": next_start,
        "updated_at": "2026-06-24T00:00:00+00:00",
    }


def test_transport_hint_loads_from_checkpoint_and_new_success_is_persisted(tmp_path, monkeypatch, capsys):
    import media2md_registry as registry

    monkeypatch.setenv("MEDIA2MD_TIKTOK_CURSOR_BACKEND", "0")

    monkeypatch.setattr(registry, "DB", tmp_path / "media2md.db")
    monkeypatch.setattr(registry, "CHECKPOINT_DIR", tmp_path / "checkpoints")
    monkeypatch.setattr(registry, "CONFIG", tmp_path / "config.json")
    (tmp_path / "config.json").write_text("{}")
    registry.CHECKPOINT_DIR.mkdir(parents=True)
    checkpoint_path = registry.CHECKPOINT_DIR / "tiktok-startupbell.json"
    checkpoint_path.write_text(json.dumps(_checkpoint([_item(i) for i in range(25)])))
    monkeypatch.setenv("MEDIA2MD_TIKTOK_SYNC_PAGE_SIZE", "25")
    monkeypatch.setenv("MEDIA2MD_TIKTOK_SYNC_MAX_PAGES_PER_RUN", "1")

    def fake_page(*args, **kwargs):
        assert registry._TIKTOK_SUCCESS_HINT == ("direct-plain", False)
        registry._TIKTOK_SUCCESS_HINT = ("latest:Chrome-146", True)
        return ({
            "external_id": "MS4wLjABAAAA_PERSISTED",
            "identifiers": {"sec_uid": "MS4wLjABAAAA_PERSISTED"},
            "handle": "startupbell",
            "display_name": "Startup Bell",
        }, [_item(100 + i) for i in range(25)], "tiktokuser:MS4wLjABAAAA_PERSISTED")

    monkeypatch.setattr(registry, "_extract_tiktok_page", fake_page)
    result = registry.sync_creator("tiktok", "@startupbell", mode="full")

    assert result["pause_reason"] == "max_pages_per_run"
    saved = json.loads(checkpoint_path.read_text())
    assert saved["preferred_transport"] == "latest:Chrome-146"
    assert saved["preferred_authenticated"] is True
    assert saved["schema_version"] == 4
    assert result["creator_identifiers"]["sec_uid"] == "MS4wLjABAAAA_PERSISTED"
    output = capsys.readouterr().out
    assert "SYNC_TRANSPORT_HINT_LOADED" in output
    assert "SYNC_TRANSPORT_HINT_SAVED" in output


def test_page_circuit_breaker_is_shared_across_stable_id_and_handle(monkeypatch):
    import media2md_registry as registry

    monkeypatch.setenv("MEDIA2MD_TIKTOK_CURSOR_BACKEND", "0")

    registry._TIKTOK_SUCCESS_HINT = None
    monkeypatch.setattr(registry, "command", lambda name: name)
    monkeypatch.setattr(registry, "auth_args", lambda provider: [])
    monkeypatch.setattr(
        registry,
        "_tiktok_transport_strategies",
        lambda: [
            ("configured:chrome", ["--ignore-config", "--impersonate", "chrome"], False),
            ("latest:Chrome-146", ["--ignore-config", "--impersonate", "Chrome-146"], False),
            ("direct-plain", ["--ignore-config", "--proxy", ""], True),
        ],
    )
    calls: list[tuple[str, str]] = []

    def fake_run_json(command, **kwargs):
        source = command[-1]
        strategy = kwargs.get("strategy", "")
        calls.append((source, strategy))
        if "--impersonate" in command:
            raise RuntimeError("curl: (35) TLS connect error OPENSSL_internal")
        if source.startswith("tiktokuser:"):
            raise RuntimeError("direct stable-id extractor failure")
        return {
            "id": "MS4wLjABAAAA_SHARED",
            "channel_id": "MS4wLjABAAAA_SHARED",
            "entries": [{
                "id": "7600000000000000001",
                "url": "https://www.tiktok.com/@startupbell/video/7600000000000000001",
                "title": "ok",
            }],
        }

    monkeypatch.setattr(registry, "run_json", fake_run_json)
    meta, items, source = registry._extract_tiktok_page(
        "https://www.tiktok.com/@startupbell", 25, 476, ["MS4wLjABAAAA_SHARED"]
    )

    assert source == "https://www.tiktok.com/@startupbell"
    assert len(items) == 1
    handle_calls = [strategy for url, strategy in calls if url.startswith("https://www.tiktok.com/@")]
    assert handle_calls == ["direct-plain"]


def test_less_than_five_seconds_remaining_never_launches_extractor(monkeypatch):
    import media2md_registry as registry

    monkeypatch.setenv("MEDIA2MD_TIKTOK_CURSOR_BACKEND", "0")

    registry._TIKTOK_SUCCESS_HINT = None
    monkeypatch.setattr(registry, "auth_args", lambda provider: [])
    monkeypatch.setattr(registry, "_tiktok_transport_strategies", lambda: [("direct-plain", ["--ignore-config", "--proxy", ""], True)])
    called = False

    def fake_run_json(*args, **kwargs):
        nonlocal called
        called = True
        raise AssertionError("extractor must not start")

    monkeypatch.setattr(registry, "run_json", fake_run_json)
    deadline = time.monotonic() + 1.0
    try:
        registry._run_tiktok_catalog(["yt-dlp"], "https://www.tiktok.com/@startupbell", deadline=deadline)
    except RuntimeError as exc:
        assert "before another extractor could start" in str(exc)
    else:
        raise AssertionError("expected bounded pause error")
    assert called is False



def test_macos_proxy_prefers_direct_plain_when_checkpoint_has_no_hint(tmp_path, monkeypatch, capsys):
    import media2md_registry as registry

    monkeypatch.setenv("MEDIA2MD_TIKTOK_CURSOR_BACKEND", "0")

    monkeypatch.setattr(registry, "DB", tmp_path / "media2md.db")
    monkeypatch.setattr(registry, "CHECKPOINT_DIR", tmp_path / "checkpoints")
    monkeypatch.setattr(registry, "CONFIG", tmp_path / "config.json")
    (tmp_path / "config.json").write_text("{}")
    registry.CHECKPOINT_DIR.mkdir(parents=True)
    checkpoint = _checkpoint([_item(i) for i in range(25)])
    checkpoint.pop("preferred_transport", None)
    checkpoint.pop("preferred_authenticated", None)
    (registry.CHECKPOINT_DIR / "tiktok-startupbell.json").write_text(json.dumps(checkpoint))
    monkeypatch.setenv("MEDIA2MD_TIKTOK_SYNC_PAGE_SIZE", "25")
    monkeypatch.setenv("MEDIA2MD_TIKTOK_SYNC_MAX_PAGES_PER_RUN", "1")
    monkeypatch.setattr(registry, "_macos_system_proxy_kinds", lambda: ["http", "https", "socks"])

    def fake_page(*args, **kwargs):
        assert registry._TIKTOK_SUCCESS_HINT == ("direct-plain", False)
        return ({
            "external_id": "MS4wLjABAAAA_PERSISTED",
            "identifiers": {"sec_uid": "MS4wLjABAAAA_PERSISTED"},
            "handle": "startupbell",
        }, [_item(200 + i) for i in range(25)], "tiktokuser:MS4wLjABAAAA_PERSISTED")

    monkeypatch.setattr(registry, "_extract_tiktok_page", fake_page)
    registry.sync_creator("tiktok", "@startupbell", mode="full")
    assert "SYNC_TRANSPORT_HINT_SELECTED provider=tiktok strategy=direct-plain" in capsys.readouterr().out

def test_v079_acceptance_documents_live_efficiency_regressions():
    from pathlib import Path

    root = Path(__file__).resolve().parents[1]
    text = (root / "STRICT_ACCEPTANCE_V079.md").read_text()
    assert "preferred_transport" in text
    assert "page-wide circuit breaker" in text
    assert "remaining page budget is below five seconds" in text
    assert "creator_identifiers.sec_uid" in text
