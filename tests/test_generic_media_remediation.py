from __future__ import annotations

from media2md.bundle.scripts.generic_media import _instagram_metadata_access_hint, _youtube_challenge_hint


def test_instagram_metadata_access_hint_uses_public_verify_command():
    message = _instagram_metadata_access_hint("403 forbidden")
    assert "media2md auth verify instagram" in message


def test_youtube_challenge_hint_uses_public_doctor_and_install_guidance():
    message = _youtube_challenge_hint("challenge solver failed")
    assert "media2md doctor youtube-access --video-id=<VIDEO_ID>" in message
    assert 'python -m pip install -U "media2md[youtube]"' in message
