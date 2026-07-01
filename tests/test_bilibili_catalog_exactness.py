from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _load_registry():
    script_path = ROOT / "src" / "media2md" / "bundle" / "scripts" / "media2md_registry.py"
    spec = importlib.util.spec_from_file_location("media2md_registry_bilibili_exactness", script_path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_bilibili_full_sync_marks_exact_only_after_follow_up_page_finishes(tmp_path, monkeypatch):
    registry = _load_registry()
    monkeypatch.setattr(registry, "DB", tmp_path / "media2md.db")
    monkeypatch.setattr(registry, "CHECKPOINT_DIR", tmp_path / "checkpoints")
    monkeypatch.setattr(registry, "CONFIG", tmp_path / "config.json")
    (tmp_path / "config.json").write_text("{}", encoding="utf-8")

    def fake_extract_catalog(provider: str, source_url: str, limit: int | None, start: int | None):
        assert provider == "bilibili"
        assert limit == 50
        assert start in {1, 51}
        meta = {
            "external_id": "1510588366",
            "handle": "1510588366",
            "display_name": "Creator",
            "source_url": source_url,
            "identifiers": {"mid": "1510588366"},
        }
        if start == 1:
            items = [
                {
                    "external_id": f"BV{index:010d}",
                    "title": f"video-{index}",
                    "description": "",
                    "source_url": f"https://www.bilibili.com/video/BV{index:010d}",
                    "published_at": f"2026-07-{(index % 28) + 1:02d}T00:00:00+00:00",
                    "duration_seconds": 60,
                    "media_type": "bilibili_video",
                }
                for index in range(50)
            ]
            return meta, items
        return meta, []

    monkeypatch.setattr(registry, "extract_catalog", fake_extract_catalog)

    result = registry.sync_creator("bilibili", "https://space.bilibili.com/1510588366", mode="full")

    assert result["current_total"] == 50
    assert result["current_total_exact"] is True


def test_bilibili_full_sync_requests_second_page_after_first_full_backend_page(tmp_path, monkeypatch):
    registry = _load_registry()
    monkeypatch.setattr(registry, "DB", tmp_path / "media2md.db")
    monkeypatch.setattr(registry, "CHECKPOINT_DIR", tmp_path / "checkpoints")
    monkeypatch.setattr(registry, "CONFIG", tmp_path / "config.json")
    (tmp_path / "config.json").write_text("{}", encoding="utf-8")

    starts: list[int] = []

    def fake_extract_catalog(provider: str, source_url: str, limit: int | None, start: int | None):
        assert provider == "bilibili"
        assert limit == 50
        starts.append(int(start or 0))
        meta = {
            "external_id": "1510588366",
            "handle": "1510588366",
            "display_name": "Creator",
            "source_url": source_url,
            "identifiers": {"mid": "1510588366"},
        }
        if start == 1:
            items = [
                {
                    "external_id": f"BV{index:010d}",
                    "title": f"video-{index}",
                    "description": "",
                    "source_url": f"https://www.bilibili.com/video/BV{index:010d}",
                    "published_at": f"2026-07-{(index % 28) + 1:02d}T00:00:00+00:00",
                    "duration_seconds": 60,
                    "media_type": "bilibili_video",
                }
                for index in range(50)
            ]
            return meta, items
        return meta, []

    monkeypatch.setattr(registry, "extract_catalog", fake_extract_catalog)

    registry.sync_creator("bilibili", "https://space.bilibili.com/1510588366", mode="full")

    assert starts == [1, 51]
