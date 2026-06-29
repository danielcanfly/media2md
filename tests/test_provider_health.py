from __future__ import annotations

from media2md.probe import ProbeResult
from media2md.provider_health import probe_health_result


def test_probe_health_result_ok_keeps_active_backend():
    result = probe_health_result(
        provider="youtube",
        backend="yt-dlp",
        backends=("yt-dlp", "yt-dlp-ejs"),
        probe=ProbeResult("ok", output="2026.06.30"),
        success_message="yt-dlp is available",
        missing_message="yt-dlp is not installed",
        failure_message="yt-dlp probe failed",
    )
    assert result.status == "ok"
    assert result.active_backend == "yt-dlp"
    assert result.backends == ("yt-dlp", "yt-dlp-ejs")
    assert result.details["probe_status"] == "ok"
    assert result.details["probe_output"] == "2026.06.30"


def test_probe_health_result_missing_maps_to_warn():
    result = probe_health_result(
        provider="instagram",
        backend="gallery-dl",
        backends=("gallery-dl", "instaloader"),
        probe=ProbeResult("missing"),
        success_message="gallery-dl is available",
        missing_message="gallery-dl is not installed",
        failure_message="gallery-dl probe failed",
    )
    assert result.status == "warn"
    assert result.message == "gallery-dl is not installed"
    assert result.active_backend is None
    assert result.backends == ("gallery-dl", "instaloader")


def test_probe_health_result_failure_exposes_hint():
    result = probe_health_result(
        provider="tiktok",
        backend="yt-dlp",
        backends=("yt-dlp",),
        probe=ProbeResult("broken", hint="reinstall yt-dlp"),
        success_message="yt-dlp is available",
        missing_message="yt-dlp is not installed",
        failure_message="yt-dlp probe failed",
    )
    assert result.status == "broken"
    assert result.message == "reinstall yt-dlp"
    assert result.hints == ("reinstall yt-dlp",)
    assert result.active_backend is None
