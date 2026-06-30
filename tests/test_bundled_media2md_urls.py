from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


def _load_module():
    root = Path(__file__).resolve().parents[1]
    path = root / "src" / "media2md" / "bundle" / "scripts" / "media2md_urls.py"
    spec = importlib.util.spec_from_file_location("bundled_media2md_urls_test", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_bundled_normalize_creator_matches_public_youtube_canonical_url():
    module = _load_module()
    result = module.normalize_creator("youtube", "@creator-name")
    assert result.kind == "creator"
    assert result.creator == "creator-name"
    assert result.canonical_url == "https://www.youtube.com/@creator-name/videos"


def test_bundled_normalize_creator_matches_current_public_surface_canonicalization():
    module = _load_module()
    result = module.normalize_creator("youtube", "https://www.youtube.com/@creator-name/shorts")
    assert result.canonical_url == "https://www.youtube.com/@creator-name/shorts"
    assert result.creator == "creator-name"
    assert result.surface == "shorts"
