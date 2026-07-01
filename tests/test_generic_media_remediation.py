from __future__ import annotations

from media2md.bundle.scripts.generic_media import (
    _bilibili_access_hint,
    _instagram_metadata_access_hint,
    _youtube_challenge_hint,
)


def test_instagram_metadata_access_hint_uses_public_verify_command():
    message = _instagram_metadata_access_hint("403 forbidden")
    assert "media2md auth verify instagram" in message


def test_youtube_challenge_hint_uses_public_doctor_and_install_guidance():
    message = _youtube_challenge_hint("challenge solver failed")
    assert "media2md doctor youtube-access --video-id=<VIDEO_ID>" in message
    assert 'python -m pip install -U "media2md[youtube]"' in message


def test_bilibili_access_hint_uses_public_doctor_and_install_guidance():
    message = _bilibili_access_hint("Bilibili support is not installed.")
    assert "media2md doctor bilibili-access --video-id=<BV_VIDEO_ID>" in message
    assert 'python -m pip install -U "media2md[bilibili]"' in message


def test_bilibili_access_hint_suggests_identity_repair_for_pipeline_failures():
    message = _bilibili_access_hint("Bilibili did not return an audio stream URL.")
    assert "media2md doctor bilibili-access --video-id=<BV_VIDEO_ID>" in message
    assert "media2md repair identities" in message
