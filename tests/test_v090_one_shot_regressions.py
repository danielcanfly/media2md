from __future__ import annotations

import argparse
import io
import json
import sqlite3
import urllib.error
from pathlib import Path


def test_instagram_accounts_edit_is_authenticated_even_if_bundle_mentions_checkpoint(monkeypatch):
    import media2md_auth as auth

    class Response:
        status = 200
        def geturl(self): return "https://www.instagram.com/accounts/edit/"
        def read(self, _limit): return b"window.__bundle='checkpoint';"
        def __enter__(self): return self
        def __exit__(self, *_args): return False

    class Opener:
        def open(self, *_args, **_kwargs): return Response()

    monkeypatch.setattr(auth.urllib.request, "build_opener", lambda *_args: Opener())
    state, status, final, error = auth._probe("instagram", object())
    assert (state, status, final, error) == (
        "authenticated", 200, "https://www.instagram.com/accounts/edit/", None,
    )


def test_instagram_challenge_redirect_is_not_authenticated(monkeypatch):
    import media2md_auth as auth

    class Response:
        status = 200
        def geturl(self): return "https://www.instagram.com/challenge/123/"
        def read(self, _limit): return b"challenge"
        def __enter__(self): return self
        def __exit__(self, *_args): return False

    class Opener:
        def open(self, *_args, **_kwargs): return Response()

    monkeypatch.setattr(auth.urllib.request, "build_opener", lambda *_args: Opener())
    assert auth._probe("instagram", object())[0] == "platform_challenge"


def test_tiktok_inspect_uses_bounded_fallback_and_saves_success(monkeypatch, capsys):
    import generic_media as media

    strategies = [
        {"name": "direct-plain", "args": ["--proxy", ""], "authenticated": False, "auth_args": []},
        {"name": "impersonated-direct", "args": ["--impersonate", "chrome"], "authenticated": True, "auth_args": ["--cookies", "x"]},
    ]
    monkeypatch.setattr(media, "_tiktok_download_strategies", lambda _creator: strategies)
    saved = {}
    monkeypatch.setattr(media, "_save_tiktok_download_hint", lambda creator, strategy, authenticated: saved.update(
        creator=creator, strategy=strategy, authenticated=authenticated
    ))

    calls = {"count": 0}
    def fake_run(_command, timeout=None):
        calls["count"] += 1
        if calls["count"] == 1:
            raise RuntimeError("curl: (35) TLS connect error")
        return argparse.Namespace(stdout=json.dumps({
            "id": "7338632507950189826", "uploader": "antscreation",
            "channel_id": "SECUID", "duration": 54,
        }))

    monkeypatch.setattr(media, "command", lambda name: name)
    monkeypatch.setattr(media, "run", fake_run)
    result = media.inspect_tiktok_metadata(
        "https://www.tiktok.com/@antscreation/video/7338632507950189826",
        "antscreation", "7338632507950189826",
    )
    output = capsys.readouterr().out
    assert result["id"] == "7338632507950189826"
    assert calls["count"] == 2
    assert "status=failed reason=tls_failure" in output
    assert "status=success" in output
    assert saved == {"creator": "antscreation", "strategy": "impersonated-direct", "authenticated": True}


def test_youtube_shorts_only_channel_treats_missing_videos_as_empty_exact(tmp_path, monkeypatch):
    import media2md_registry as registry

    monkeypatch.setattr(registry, "CHECKPOINT_DIR", tmp_path / "checkpoints")
    monkeypatch.setattr(registry, "youtube_catalog_surfaces", lambda: ("videos", "shorts"))

    meta = {
        "external_id": "UC_TEST", "handle": "huai-syuanhuang5857",
        "display_name": "Huai Hsuan", "identifiers": {"channel_id": "UC_TEST"},
    }
    short = {
        "external_id": "1teLDiN9VO8", "title": "test", "description": "",
        "source_url": "https://www.youtube.com/watch?v=1teLDiN9VO8",
        "published_at": "2026-06-25T00:00:00+00:00", "duration_seconds": 8,
    }

    def fake_extract(_provider, url, limit=None, start=None):
        if url.endswith("/videos"):
            raise RuntimeError("This channel does not have a videos tab")
        return meta, [short]

    captured = {}
    def fake_upsert(provider, handle, source_url, items, page_meta, sync_mode, exact, *, exact_by_type=None):
        captured.update(provider=provider, handle=handle, items=items, meta=page_meta,
                        sync_mode=sync_mode, exact=exact, exact_by_type=exact_by_type)
        return {"current_total": len(items), "current_total_exact": exact}

    monkeypatch.setattr(registry, "extract_catalog", fake_extract)
    monkeypatch.setattr(registry, "upsert_catalog", fake_upsert)

    summary = registry._sync_youtube_creator(
        "huai-syuanhuang5857", "https://www.youtube.com/@huai-syuanhuang5857", "full", 50,
    )
    assert summary["current_total"] == 1
    assert captured["exact"] is True
    assert captured["exact_by_type"]["youtube_video"] is True
    assert captured["exact_by_type"]["youtube_short"] is True
    assert summary["youtube_surfaces"]["videos"]["fetched"] == 0
    assert summary["youtube_surfaces"]["videos"]["absent"] is True
    assert summary["youtube_surfaces"]["shorts"]["fetched"] == 1


def _meta() -> dict:
    sec_uid = "MS4wLjABAAAA_V090_EXACT"
    return {
        "external_id": sec_uid, "handle": "startupbell", "display_name": "Startup Bell",
        "source_url": "https://www.tiktok.com/@startupbell",
        "identifiers": {"primary": sec_uid, "sec_uid": sec_uid},
    }


def _item(media_id: str) -> dict:
    return {
        "external_id": media_id, "title": media_id, "description": "",
        "source_url": f"https://www.tiktok.com/@startupbell/video/{media_id}",
        "published_at": "2026-06-23T00:00:00+00:00", "duration_seconds": 30,
        "media_type": "tiktok_video", "processing_class": "tiktok_video",
    }


def test_resumed_staged_exact_checkpoint_never_publishes_partial(tmp_path, monkeypatch, capsys):
    import media2md_registry as registry

    monkeypatch.setattr(registry, "DB", tmp_path / "media2md.db")
    monkeypatch.setattr(registry, "CHECKPOINT_DIR", tmp_path / "checkpoints")
    monkeypatch.setattr(registry, "TIKTOK_CURSOR_STATE", tmp_path / "checkpoints" / "cursor-state.json")
    monkeypatch.setattr(registry, "CONFIG", tmp_path / "config.json")
    (tmp_path / "config.json").write_text("{}", encoding="utf-8")
    registry.CHECKPOINT_DIR.mkdir(parents=True)
    registry.upsert_catalog(
        "tiktok", "startupbell", "https://www.tiktok.com/@startupbell",
        [_item("10"), _item("11")], _meta(), "full", exact=True,
    )
    checkpoint = registry.CHECKPOINT_DIR / "tiktok-startupbell.json"
    checkpoint.write_text(json.dumps({
        "schema_version": 5, "provider": "tiktok", "creator": "startupbell",
        "source_url": "https://www.tiktok.com/@startupbell", "mode": "full",
        "meta": _meta(), "tiktok_identifiers": [_meta()["external_id"]],
        "items": [_item("20")], "next_start": 2, "tiktok_cursor": 123,
        "tiktok_device_id": "device", "pagination_backend": "cursor_api",
        "rebuild_from_exact": True,
    }), encoding="utf-8")
    monkeypatch.setenv("MEDIA2MD_TIKTOK_CURSOR_BACKEND", "1")
    monkeypatch.setattr(
        registry, "_run_tiktok_cursor_request",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("HTTP 403")),
    )

    result = registry.sync_creator("tiktok", "@startupbell", mode="full")
    output = capsys.readouterr().out
    assert "SYNC_STAGED_CATALOG_PRESERVED" in output
    assert "SYNC_PARTIAL_CATALOG_SAVED" not in output
    assert result["current_total"] == 2
    assert result["current_total_exact"] is True
    conn = registry.connect()
    creator = conn.execute(
        "SELECT current_total,current_total_exact,last_full_exact_total FROM creators WHERE handle='startupbell'"
    ).fetchone()
    conn.close()
    assert tuple(creator) == (2, 1, 2)


def test_manual_reprocess_of_existing_current_item_preserves_exact(tmp_path, monkeypatch):
    import generic_media as media
    import media2md_registry as registry

    monkeypatch.setattr(registry, "DB", tmp_path / "media2md.db")
    monkeypatch.setattr(registry, "CONFIG", tmp_path / "config.json")
    monkeypatch.setattr(media, "REGISTRY_DB", registry.DB)
    (tmp_path / "config.json").write_text("{}", encoding="utf-8")
    meta = {
        "provider": "tiktok", "creator": "startupbell", "creator_external_id": _meta()["external_id"],
        "creator_identifiers": _meta()["identifiers"], "creator_display_name": "Startup Bell",
        "external_id": "10", "title": "10", "description": "",
        "source_url": "https://www.tiktok.com/@startupbell/video/10",
        "published_at": "2026-06-23T00:00:00+00:00", "duration_seconds": 30,
        "media_type": "tiktok_video",
    }
    registry.upsert_catalog(
        "tiktok", "startupbell", "https://www.tiktok.com/@startupbell", [_item("10")], _meta(), "full", exact=True,
    )
    media.ensure_registry(meta)
    conn = registry.connect()
    assert conn.execute("SELECT current_total_exact FROM creators WHERE handle='startupbell'").fetchone()[0] == 1
    conn.close()

    media.ensure_registry({**meta, "external_id": "99", "source_url": "https://www.tiktok.com/@startupbell/video/99"})
    conn = registry.connect()
    assert conn.execute("SELECT current_total_exact FROM creators WHERE handle='startupbell'").fetchone()[0] == 0
    conn.close()


def test_openclaw_install_defaults_to_no_delivery(tmp_path, monkeypatch, capsys):
    import social2md_core as core

    skill = tmp_path / "SKILL.md"
    skill.write_text("test", encoding="utf-8")
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setattr(core, "OPENCLAW_SKILL_SOURCE", skill)
    monkeypatch.setattr(core, "load_config", lambda: {"timezone": "Asia/Tokyo"})
    args = argparse.Namespace(
        timezone="Asia/Tokyo", name="acceptance", cron="0 * * * *", agent=None,
        announce=False, channel=None, to=None, dry_run=True, allow_duplicate=False,
    )
    assert core.openclaw_install(args) == 0
    assert '"--no-deliver"' in capsys.readouterr().out


def test_openclaw_announce_requires_explicit_recipient(tmp_path, monkeypatch):
    import pytest
    import social2md_core as core

    skill = tmp_path / "SKILL.md"
    skill.write_text("test", encoding="utf-8")
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setattr(core, "OPENCLAW_SKILL_SOURCE", skill)
    monkeypatch.setattr(core, "load_config", lambda: {"timezone": "Asia/Tokyo"})
    args = argparse.Namespace(
        timezone="Asia/Tokyo", name="acceptance", cron="0 * * * *", agent=None,
        announce=True, channel=None, to=None, dry_run=True, allow_duplicate=False,
    )
    with pytest.raises(RuntimeError, match="requires both"):
        core.openclaw_install(args)


def test_update_404_is_unpublished_and_scheduler_network_warning_is_nonfatal(tmp_path, monkeypatch, capsys):
    import social2md_core as core

    def raise_404(*_args, **_kwargs):
        raise urllib.error.HTTPError("url", 404, "Not Found", {}, io.BytesIO())

    monkeypatch.setattr(core.urllib.request, "urlopen", raise_404)
    assert core.fetch_latest_release("owner/repo") == {"_not_published": True}

    monkeypatch.setattr(core, "POLICY_PATH", tmp_path / "policy.json")
    monkeypatch.setattr(core, "SCHEDULER_STATE_PATH", tmp_path / "scheduler.json")
    monkeypatch.setattr(core, "SCHEDULER_LOCK", tmp_path / "scheduler.lock")
    monkeypatch.setattr(core, "load_policies", lambda: {"creators": {}})
    monkeypatch.setattr(core, "load_config", lambda: {
        "updates": {"enabled": True, "repository": "owner/repo"}, "timezone": "Asia/Tokyo"
    })
    monkeypatch.setattr(core, "fetch_latest_release", lambda _repo: (_ for _ in ()).throw(RuntimeError("offline")))
    assert core.scheduler_tick(argparse.Namespace(output="ndjson", non_interactive=True)) == 0
    output = capsys.readouterr().out
    assert '"event": "update_check_warning"' in output
    assert '"failures": 0' in output


def test_v090_installer_repairs_exact_and_marks_nonempty_cursor_checkpoint_staged(tmp_path):
    import importlib.util

    root = Path(__file__).resolve().parents[1]
    installer_path = root / "docs" / "archive" / "installers" / "install_media2md_v090.py"
    spec = importlib.util.spec_from_file_location("installer_v090", installer_path)
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
            id INTEGER PRIMARY KEY, provider TEXT, handle TEXT,
            current_total INTEGER, current_total_exact INTEGER,
            last_full_exact_total INTEGER, last_full_exact_at TEXT, updated_at TEXT
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
        "schema_version": 5, "provider": "tiktok", "creator": "startupbell",
        "mode": "full", "pagination_backend": "cursor_api",
        "items": [{"external_id": "staged-item"}], "next_start": 174,
        "tiktok_device_id": "stable-device-v090",
    }), encoding="utf-8")

    assert installer.repair_tiktok_exact_state(tmp_path) == 1
    migrated, staged = installer.migrate_tiktok_cursor_state(tmp_path)
    assert migrated == 1
    assert staged == 1
    updated = json.loads(checkpoint.read_text(encoding="utf-8"))
    assert updated["rebuild_from_exact"] is True
    assert updated["items"] == [{"external_id": "staged-item"}]
