from __future__ import annotations

import argparse
import json
from pathlib import Path


def test_public_cli_accepts_and_forwards_instagram_retry_failed(monkeypatch):
    import media2md as package
    import media2md as _package  # keep package import stable for test collection
    import media2md as __package_alias
    import importlib

    cli = importlib.import_module("media2md")
    # The package and script share a name; load the script explicitly through its file.
    import importlib.util
    import sys
    root = Path(__file__).resolve().parents[1]
    script = root / "src" / "media2md" / "bundle" / "scripts" / "media2md.py"
    spec = importlib.util.spec_from_file_location("media2md_cli_v076", script)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules["media2md_cli_v076"] = module
    spec.loader.exec_module(module)

    policy = {
        "processing": {
            "mode": "batch",
            "batch_size": 100,
            "batch_sizes": {"instagram_reel": 3},
            "max_batches": 0,
            "max_runtime_minutes": 360,
            "max_failures": 10,
            "stop_on_failure": False,
            "sleep_between_batches": 0,
        },
        "filters": {"since": None, "until": None, "rank_from": None, "rank_to": None, "order": "newest_first"},
        "sync": {"quick_window": 100},
    }
    captured: list[list[str]] = []
    monkeypatch.setattr(module, "refresh_auth", lambda provider: None)
    monkeypatch.setattr(module, "effective_policy", lambda provider, creator: policy)
    monkeypatch.setattr(module, "core", lambda args: captured.append(list(args)) or 0)
    monkeypatch.setattr(module, "normalize_creator", lambda provider, value: "career_cleo")

    args = module.parser().parse_args([
        "creator", "run", "career_cleo", "--provider", "instagram",
        "--max-batches", "1", "--max-failures", "1", "--retry-failed",
    ])
    assert args.retry_failed is True
    assert args.func(args) == 0
    assert captured
    assert "--retry-failed" in captured[0]


def test_instagram_default_worker_command_restores_legacy_cookie_resolution():
    import creator_bulk

    default = creator_bulk.worker_command("ABC123", None, False)
    assert "--cookies-file" not in default
    explicit = creator_bulk.worker_command("ABC123", Path("/tmp/ig-cookies.txt"), False)
    assert explicit[-2:] == ["--cookies-file", "/tmp/ig-cookies.txt"]


def test_tiktok_direct_strategy_forces_empty_proxy(monkeypatch):
    import media2md_registry as registry

    monkeypatch.setattr(registry, "impersonation_args", lambda provider: [])
    monkeypatch.setattr(registry, "impersonation_targets", lambda: {"targets": []})
    strategies = registry._tiktok_transport_strategies()
    assert strategies == [("direct-plain", ["--ignore-config", "--proxy", ""], True)]


def test_tiktok_old_checkpoint_recovers_identity_and_persists_partial_catalog(tmp_path, monkeypatch):
    import media2md_registry as registry

    monkeypatch.setattr(registry, "DB", tmp_path / "media2md.db")
    monkeypatch.setattr(registry, "CHECKPOINT_DIR", tmp_path / "checkpoints")
    monkeypatch.setattr(registry, "CONFIG", tmp_path / "config.json")
    registry.CHECKPOINT_DIR.mkdir()
    (tmp_path / "config.json").write_text("{}")
    checkpoint = registry.CHECKPOINT_DIR / "tiktok-startupbell.json"
    item = {
        "external_id": "1234567890",
        "title": "fixture",
        "description": "",
        "source_url": "https://www.tiktok.com/@startupbell/video/1234567890",
        "published_at": "2026-06-01T00:00:00+00:00",
        "duration_seconds": 20,
        "media_type": "tiktok_video",
        "processing_class": "tiktok_video",
    }
    checkpoint.write_text(json.dumps({
        "schema_version": 3,
        "provider": "tiktok",
        "creator": "startupbell",
        "source_url": "https://www.tiktok.com/@startupbell",
        "mode": "full",
        "meta": {
            "handle": "startupbell",
            "external_id": "startupbell",
            "display_name": "startupbell",
            "identifiers": {},
        },
        "tiktok_identifiers": [],
        "items": [item],
        "next_start": 201,
    }))
    monkeypatch.setattr(registry, "_tiktok_identifiers_from_page", lambda meta, items: ["SEC_UID_FIXTURE"])
    monkeypatch.setattr(
        registry,
        "_extract_tiktok_page",
        lambda *a, **k: (_ for _ in ()).throw(RuntimeError("curl: (35) TLS connect error")),
    )

    try:
        registry.sync_creator("tiktok", "@startupbell", mode="full")
    except RuntimeError as exc:
        assert "partial_catalog_saved=1" in str(exc)
        assert "retry_from=201" in str(exc)
    else:
        raise AssertionError("expected TikTok page failure")

    saved = json.loads(checkpoint.read_text())
    assert saved["next_start"] == 201
    conn = registry.connect()
    creator = conn.execute("SELECT current_total,current_total_exact,last_sync_mode FROM creators WHERE provider='tiktok'").fetchone()
    media_count = conn.execute("SELECT COUNT(*) FROM media WHERE provider='tiktok' AND is_current=1").fetchone()[0]
    conn.close()
    assert tuple(creator) == (1, 0, "partial")
    assert media_count == 1
