from __future__ import annotations

from media2md.bundle.scripts import media2md_doctor as doctor


def test_doctor_event_payload_wraps_single_section():
    payload = doctor.doctor_event_payload(
        event="browser_safety_doctor",
        section="browser_safety",
        status="ok",
        message="Browser launch safety policy",
        data={"browser_launch_allowed": False},
    )
    assert payload["event"] == "browser_safety_doctor"
    assert payload["schema"] == "media2md.cli.browser_safety_doctor/v1"
    assert payload["status"] == "ok"
    assert payload["sections"][0]["name"] == "browser_safety"
    assert payload["browser_launch_allowed"] is False


def test_youtube_access_payload_invalid_id_keeps_guidance_contract():
    payload = doctor.youtube_access_payload("bad-id")
    assert payload["event"] == "youtube_access_doctor"
    assert payload["required_action"] == "provide_valid_video_id"
    assert payload["health_status"] == "warn"

