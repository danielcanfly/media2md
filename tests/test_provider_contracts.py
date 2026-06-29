from __future__ import annotations

from media2md.provider_registry import all_provider_adapters


def test_provider_registry_not_empty():
    adapters = all_provider_adapters()
    assert adapters


def test_provider_names_unique():
    adapters = all_provider_adapters()
    names = [adapter.name for adapter in adapters]
    assert len(names) == len(set(names))


def test_provider_contract_surface():
    for adapter in all_provider_adapters():
        assert adapter.name in {"instagram", "youtube", "tiktok"}
        assert isinstance(adapter.backends, list)
        assert isinstance(adapter.can_handle_url("https://example.com"), bool)
        result = adapter.health_check()
        assert result.status in {"ok", "warn", "missing", "broken", "timeout", "error"}
        assert isinstance(result.message, str)


def test_provider_can_handle_own_urls():
    samples = {
        "instagram": "https://www.instagram.com/example/",
        "youtube": "https://www.youtube.com/@creator-name/videos",
        "tiktok": "https://www.tiktok.com/@creator-name",
    }
    for adapter in all_provider_adapters():
        assert adapter.can_handle_url(samples[adapter.name]) is True


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
