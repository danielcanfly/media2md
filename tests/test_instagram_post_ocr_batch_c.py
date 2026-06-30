from __future__ import annotations

import importlib.util
import sqlite3
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _load_module(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec is not None and spec.loader is not None
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def test_summarize_instagram_assets_counts_images_and_videos():
    generic_media = _load_module(
        ROOT / "src" / "media2md" / "bundle" / "scripts" / "generic_media.py",
        "test_batch_c_asset_summary",
    )

    summary = generic_media.summarize_instagram_assets(
        {
            "assets": [
                {"index": 1, "kind": "image", "source_url": "https://cdn.example.com/1.jpg"},
                {"index": 2, "kind": "image", "source_url": "https://cdn.example.com/2.jpg"},
                {"index": 3, "kind": "video", "source_url": "https://cdn.example.com/3.mp4"},
            ]
        }
    )

    assert summary["asset_count"] == 3
    assert summary["image_count"] == 2
    assert summary["video_count"] == 1
    assert summary["asset_kinds"] == ["image", "image", "video"]


def test_registered_process_completion_emits_asset_counts(monkeypatch, capsys):
    generic_media = _load_module(
        ROOT / "src" / "media2md" / "bundle" / "scripts" / "generic_media.py",
        "test_batch_c_registered_process",
    )

    db = sqlite3.connect(":memory:")
    db.row_factory = sqlite3.Row
    db.execute(
        """
        CREATE TABLE media (
            id INTEGER PRIMARY KEY,
            provider TEXT,
            external_id TEXT,
            creator TEXT,
            title TEXT,
            description TEXT,
            source_url TEXT,
            published_at TEXT,
            duration_seconds REAL,
            media_type TEXT,
            processing_class TEXT,
            status TEXT,
            markdown_path TEXT,
            markdown_sha256 TEXT,
            last_error TEXT,
            created_at TEXT,
            updated_at TEXT,
            completed_at TEXT,
            UNIQUE(provider, external_id)
        )
        """
    )
    monkeypatch.setattr(generic_media, "connect", lambda: db)
    monkeypatch.setattr(
        generic_media,
        "registered_metadata",
        lambda provider, external_id: {
            "provider": "instagram",
            "external_id": external_id,
            "creator": "creator.name",
            "creator_external_id": "12345",
            "creator_identifiers": {},
            "creator_display_name": "Creator Name",
            "title": "Instagram Post ABC123xyz9",
            "description": "caption",
            "published_at": "2026-06-30T00:00:00+00:00",
            "duration_seconds": None,
            "media_type": "instagram_carousel",
            "processing_class": "instagram_carousel",
            "source_url": "https://www.instagram.com/p/ABC123xyz9/",
        },
    )
    monkeypatch.setattr(
        generic_media,
        "process_row",
        lambda conn, row: {
            "final_path": generic_media.ROOT / "markdown" / "instagram" / "creator.name" / "posts" / "ABC123xyz9.md",
            "media_type": "instagram_carousel",
            "processing_class": "instagram_carousel",
            "result_summary": {"asset_count": 3, "image_count": 3, "video_count": 0, "asset_kinds": ["image", "image", "image"]},
        },
    )
    monkeypatch.setattr(generic_media, "sync_registry", lambda provider, external_id, row: None)
    monkeypatch.setattr(generic_media, "emit", lambda payload, output: None)

    code = generic_media._process_registered_unlocked("instagram", "ABC123xyz9", "human")

    out = capsys.readouterr().out
    assert code == 0
    assert "MEDIA_COMPLETED" in out
    assert "result_folder=" in out
    assert "latest_markdown_path=" in out
    assert "asset_count=3" in out
    assert "image_count=3" in out
    final = generic_media.ROOT / "markdown" / "instagram" / "creator.name" / "posts" / "ABC123xyz9.md"
    final.unlink(missing_ok=True)
