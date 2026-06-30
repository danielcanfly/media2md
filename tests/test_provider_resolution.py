from __future__ import annotations

import pytest

from media2md.provider_resolution import (
    normalize_creator_handle,
    resolve_creator_target,
    resolve_provider_for_creator,
)


def test_resolve_provider_for_creator_accepts_explicit_provider():
    assert resolve_provider_for_creator("@creator-name", "youtube", command_name="creator run") == "youtube"


def test_resolve_provider_for_creator_detects_full_url():
    assert resolve_provider_for_creator("https://www.tiktok.com/@creator-name", None, command_name="creator sync") == "tiktok"


def test_resolve_provider_for_creator_requires_provider_for_bare_handle():
    with pytest.raises(RuntimeError) as excinfo:
        resolve_provider_for_creator("@creator-name", None, command_name="creator add")
    assert "creator add" in str(excinfo.value)
    assert "--provider" in str(excinfo.value)


def test_resolve_provider_for_creator_rejects_unknown_explicit_provider():
    with pytest.raises(RuntimeError) as excinfo:
        resolve_provider_for_creator("@creator-name", "unknown", command_name="creator add")
    message = str(excinfo.value)
    assert "Unsupported provider" in message
    assert "instagram, youtube, tiktok" in message


def test_normalize_creator_handle_returns_handle_only():
    assert normalize_creator_handle("instagram", "@creator.name") == "creator.name"
    assert normalize_creator_handle("youtube", "@creator-name") == "creator-name"
    assert normalize_creator_handle("tiktok", "@creator_name") == "creator_name"


def test_resolve_creator_target_returns_structured_result():
    result = resolve_creator_target("https://www.youtube.com/@creator-name", None, command_name="creator add")
    assert result.provider == "youtube"
    assert result.kind == "creator"
    assert result.creator == "creator-name"
    assert result.canonical_url == "https://www.youtube.com/@creator-name/videos"
    assert result.surface == "videos"


def test_resolve_creator_target_preserves_youtube_surface():
    result = resolve_creator_target("https://www.youtube.com/@creator-name/shorts", None, command_name="creator add")
    assert result.provider == "youtube"
    assert result.creator == "creator-name"
    assert result.canonical_url == "https://www.youtube.com/@creator-name/shorts"
    assert result.surface == "shorts"
