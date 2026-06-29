from __future__ import annotations

from media2md.results import HealthResult, ProviderResolutionResult


def test_health_result_defaults():
    result = HealthResult(status="ok", message="ready")
    assert result.status == "ok"
    assert result.message == "ready"
    assert result.provider is None
    assert result.active_backend is None
    assert result.backend is None
    assert result.backends == ()
    assert result.hints == ()
    assert result.artifacts == {}
    assert result.details == {}


def test_health_result_preserves_backend_aliases_and_serializes():
    result = HealthResult(
        status="ok",
        message="ready",
        provider="youtube",
        active_backend="yt-dlp",
        backends=["yt-dlp", "yt-dlp-ejs"],
        hints=["install ffmpeg"],
        artifacts={"doctor_log": "/tmp/doctor.log"},
        details={"probe_status": "ok"},
    )
    assert result.backend == "yt-dlp"
    assert result.active_backend == "yt-dlp"
    assert result.backends == ("yt-dlp", "yt-dlp-ejs")
    assert result.hints == ("install ffmpeg",)
    payload = result.as_dict()
    assert payload["active_backend"] == "yt-dlp"
    assert payload["backends"] == ["yt-dlp", "yt-dlp-ejs"]
    assert payload["hints"] == ["install ffmpeg"]


def test_health_result_backfills_active_backend_from_legacy_backend():
    result = HealthResult(status="warn", message="missing", backend="gallery-dl")
    assert result.backend == "gallery-dl"
    assert result.active_backend == "gallery-dl"
    assert result.backends == ("gallery-dl",)


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
