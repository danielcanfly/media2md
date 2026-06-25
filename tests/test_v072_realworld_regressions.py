from __future__ import annotations

import argparse
import importlib.util
from pathlib import Path
from types import SimpleNamespace


def _tiktok_item(index: int) -> dict:
    media_id = str(7300000000000000000 + index)
    return {
        "external_id": media_id,
        "title": media_id,
        "description": "",
        "source_url": f"https://www.tiktok.com/@startupbell/video/{media_id}",
        "published_at": f"2026-06-{(index % 28) + 1:02d}T00:00:00+00:00",
        "duration_seconds": 30,
        "media_type": "tiktok_video",
        "processing_class": "tiktok_video",
    }


def test_instagram_creator_url_is_normalized_before_legacy_manager(tmp_path, monkeypatch):
    root = Path(__file__).resolve().parents[1]
    script_path = root / "src" / "media2md" / "bundle" / "scripts" / "media2md.py"
    spec = importlib.util.spec_from_file_location("media2md_cli_script_v072", script_path)
    assert spec and spec.loader
    cli = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(cli)

    (tmp_path / "scripts").mkdir()
    (tmp_path / "scripts" / "manage_creators.py").write_text("# stub\n")
    monkeypatch.setattr(cli, "ROOT", tmp_path)
    monkeypatch.setattr(cli, "refresh_auth", lambda provider: None)
    monkeypatch.setattr(cli, "registry", lambda args: 0)

    captured: list[list[str]] = []

    def fake_run(cmd, **kwargs):
        captured.append([str(item) for item in cmd])
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr(cli.subprocess, "run", fake_run)
    args = argparse.Namespace(
        provider="instagram",
        creator="https://www.instagram.com/career_cleo/reels/",
    )

    assert cli.add_creator(args) == 0
    assert captured[0][-1] == "career_cleo"


def test_tiktok_full_sync_reuses_secuid_after_first_page(tmp_path, monkeypatch):
    import media2md_registry as registry

    monkeypatch.setattr(registry, "DB", tmp_path / "media2md.db")
    monkeypatch.setattr(registry, "CHECKPOINT_DIR", tmp_path / "checkpoints")
    monkeypatch.setattr(registry, "CONFIG", tmp_path / "config.json")
    (tmp_path / "config.json").write_text("{}")

    meta = {
        "external_id": "MS4wLjABAAAA_STABLE",
        "handle": "startupbell",
        "display_name": "Startup Bell",
        "identifiers": {"sec_uid": "MS4wLjABAAAA_STABLE", "user_id": "123456789"},
    }
    first_page = [_tiktok_item(i) for i in range(100)]
    second_page = [_tiktok_item(100 + i) for i in range(2)]
    calls: list[tuple[str, int | None]] = []

    def fake_extract_once(provider, source_url, limit, start, **kwargs):
        calls.append((source_url, start))
        assert provider == "tiktok"
        if start == 1:
            assert source_url == "https://www.tiktok.com/@startupbell"
            return meta, first_page
        assert source_url == "tiktokuser:MS4wLjABAAAA_STABLE"
        assert start == 101
        return meta, second_page

    monkeypatch.setattr(registry, "_extract_catalog_once", fake_extract_once)

    result = registry.sync_creator("tiktok", "@startupbell", mode="full")
    assert result["current_total"] == 102
    assert result["current_total_exact"] is True
    assert calls == [
        ("https://www.tiktok.com/@startupbell", 1),
        ("tiktokuser:MS4wLjABAAAA_STABLE", 101),
    ]


def test_install_guide_is_fail_fast_and_checks_archive():
    root = Path(__file__).resolve().parents[1]
    guide = (root / "MEDIA2MD_V072_INSTALL.md").read_text()
    assert "set -euo pipefail" in guide
    assert 'test -f "$ZIP"' in guide
    assert "media2md 0.7.2" in guide
