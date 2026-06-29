from __future__ import annotations

from media2md.results import HealthResult, ProviderResolutionResult


def test_health_result_defaults():
    result = HealthResult(status="ok", message="ready")
    assert result.status == "ok"
    assert result.message == "ready"
    assert result.provider is None
    assert result.backend is None
    assert result.details == {}


def test_provider_resolution_result_fields():
    result = ProviderResolutionResult(
        provider="youtube",
        kind="creator",
        canonical_url="https://www.youtube.com/@creator-name/videos",
        creator="creator-name",
    )
    assert result.provider == "youtube"
    assert result.kind == "creator"
    assert result.canonical_url.endswith("/videos")
    assert result.creator == "creator-name"
    assert result.media_id is None
