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


def test_bilibili_access_payload_invalid_id_keeps_guidance_contract():
    payload = doctor.bilibili_access_payload("bad-id")
    assert payload["event"] == "bilibili_access_doctor"
    assert payload["required_action"] == "provide_valid_video_id"
    assert payload["health_status"] == "warn"
    assert "Bilibili" in payload["error"]
    assert payload["live_probe_ready"] is False
    assert payload["degraded"] is False


def test_instagram_payload_reports_ocr_route(monkeypatch):
    monkeypatch.setattr(doctor, "command", lambda name: f"/tmp/{name}")
    monkeypatch.setattr(doctor, "_command_ready", lambda name, package=None: (True, {"status": "ok", "category": "ready", "output": name, "hint": None}))
    monkeypatch.setattr(doctor, "_module_probe", lambda module_name, package=None: (False, {"status": "missing", "category": "action_required", "output": None, "hint": "install"}))
    monkeypatch.setattr(doctor.platform, "system", lambda: "Darwin")

    payload = doctor.instagram_payload(None)

    assert payload["event"] == "instagram_backends_doctor"
    assert payload["supported_media_surfaces"] == ["reel", "post", "carousel", "tv_legacy"]
    assert payload["ocr_platform_route"] == "vision_with_easyocr_fallback"
    assert payload["ocr_preferred_engine"] == "vision"
    assert payload["ocr_fallback_engine"] == "easyocr"
    assert payload["ocr_install_extra"] == "ocr-mac-os"
    assert payload["vision_supported"] is True
    assert payload["post_ocr_ready"] is True
