from __future__ import annotations

import pytest

from media2md.health_taxonomy import health_category, normalize_health_status
from media2md.provider_registry import all_provider_adapters, provider_adapter
from media2md.provider_resolution import resolve_creator_target, resolve_provider_for_creator

EXPECTED_BACKENDS = {
    "instagram": ["gallery-dl", "instaloader"],
    "youtube": ["yt-dlp", "yt-dlp-ejs"],
    "tiktok": ["yt-dlp"],
}


def test_provider_registry_not_empty():
    adapters = all_provider_adapters()
    assert adapters


def test_provider_names_unique():
    adapters = all_provider_adapters()
    names = [adapter.name for adapter in adapters]
    assert len(names) == len(set(names))


def test_provider_registry_matches_declared_provider_catalog():
    adapters = all_provider_adapters()
    registry_names = {adapter.name for adapter in adapters}
    declared_names = set(EXPECTED_BACKENDS)
    assert registry_names == declared_names


def test_provider_adapter_lookup_is_case_insensitive():
    assert provider_adapter("YOUTUBE") is not None
    assert provider_adapter("YOUTUBE").name == "youtube"
    assert provider_adapter("Instagram").name == "instagram"
    assert provider_adapter("no-such-provider") is None


def test_provider_contract_surface():
    for adapter in all_provider_adapters():
        assert adapter.name in {"instagram", "youtube", "tiktok"}
        assert isinstance(adapter.backends, list)
        assert adapter.backends
        assert len(adapter.backends) == len(set(adapter.backends))
        assert adapter.backends == EXPECTED_BACKENDS[adapter.name]
        assert isinstance(adapter.can_handle_url("https://example.com"), bool)
        result = adapter.health_check()
        assert result.status in {"ok", "warn", "missing", "broken", "timeout", "error"}
        assert isinstance(result.message, str)
        assert result.provider == adapter.name
        assert result.backend == result.active_backend
        assert isinstance(result.active_backend, str | type(None))
        assert result.backends == tuple(adapter.backends)
        assert isinstance(result.hints, tuple)
        assert isinstance(result.artifacts, dict)
        assert isinstance(result.details, dict)
        assert normalize_health_status(result.status) == result.status
        assert health_category(result.status) in {"ready", "action_required", "degraded"}
        if result.active_backend is not None:
            assert result.active_backend in result.backends
        if result.status == "ok":
            assert result.active_backend is not None
        if result.status in {"warn", "missing", "broken", "timeout", "error"}:
            assert result.active_backend is None
        if result.hints:
            assert all(isinstance(item, str) and item for item in result.hints)
        if result.artifacts:
            assert all(isinstance(key, str) and key for key in result.artifacts)
            assert all(isinstance(value, str) and value for value in result.artifacts.values())
        assert "probe_status" in result.details
        assert result.details["probe_status"] == result.status or (
            result.status == "warn" and result.details["probe_status"] == "missing"
        )


def test_provider_can_handle_own_urls():
    samples = {
        "instagram": "https://www.instagram.com/example/",
        "youtube": "https://www.youtube.com/@creator-name/videos",
        "tiktok": "https://www.tiktok.com/@creator-name",
    }
    for adapter in all_provider_adapters():
        assert adapter.can_handle_url(samples[adapter.name]) is True


def test_provider_does_not_claim_other_provider_urls():
    samples = {
        "instagram": "https://www.instagram.com/example/",
        "youtube": "https://www.youtube.com/@creator-name/videos",
        "tiktok": "https://www.tiktok.com/@creator-name",
    }
    for adapter in all_provider_adapters():
        for provider_name, sample in samples.items():
            if provider_name == adapter.name:
                continue
            assert adapter.can_handle_url(sample) is False


def test_provider_creator_resolution():
    expected = {
        "instagram": ("https://www.instagram.com/creator.name/reels/", "creator.name"),
        "youtube": ("https://www.youtube.com/@creator-name/videos", "creator-name"),
        "tiktok": ("https://www.tiktok.com/@creator_name", "creator_name"),
    }
    inputs = {
        "instagram": "@creator.name",
        "youtube": "@creator-name",
        "tiktok": "@creator_name",
    }
    for adapter in all_provider_adapters():
        result = adapter.resolve_creator_input(inputs[adapter.name])
        canonical_url, creator = expected[adapter.name]
        assert result.provider == adapter.name
        assert result.kind == "creator"
        assert result.canonical_url == canonical_url
        assert result.creator == creator
        assert result.media_id is None


def test_provider_resolution_matches_shared_resolution_path():
    cases = {
        "instagram": ("@creator.name", "instagram"),
        "youtube": "https://www.youtube.com/@creator-name",
        "tiktok": "https://www.tiktok.com/@creator_name",
    }
    for adapter in all_provider_adapters():
        case = cases[adapter.name]
        if isinstance(case, tuple):
            value, provider = case
        else:
            value, provider = case, None
        direct = adapter.resolve_creator_input(value)
        shared = resolve_creator_target(value, provider, command_name="creator add")
        assert direct == shared


def test_provider_resolution_requires_explicit_provider_for_bare_handle():
    for bare in ("@creator-name", "creator-name"):
        with pytest.raises(RuntimeError) as excinfo:
            resolve_provider_for_creator(bare, None, command_name="creator run")
        assert "creator run" in str(excinfo.value)
        assert "--provider" in str(excinfo.value)
