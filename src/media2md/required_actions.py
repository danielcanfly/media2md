from __future__ import annotations

from typing import Final


REQUIRED_ACTIONS: Final[frozenset[str]] = frozenset(
    {
        "close_browser_and_check_profile_cookie_access",
        "complete_instagram_challenge_in_selected_profile",
        "complete_tiktok_challenge_in_selected_profile",
        "configure_non_browser_po_token_or_try_another_video",
        "configure_youtube_audio_strategies",
        "connect_instagram_browser_profile",
        "connect_tiktok_browser_profile",
        "connect_youtube_browser_profile",
        "inspect_instagram_access_error",
        "inspect_instagram_failure_report",
        "inspect_render_error",
        "inspect_tiktok_access_error",
        "inspect_transcription_log",
        "inspect_youtube_access_error",
        "install_auth_browser_dependencies",
        "install_impersonation",
        "install_mlx_whisper",
        "install_provider_extra",
        "install_youtube_extra",
        "login_to_youtube_in_selected_profile",
        "provide_valid_video_id",
        "reauthenticate_instagram_in_selected_profile",
        "reauthenticate_tiktok_in_selected_profile",
        "reauthenticate_youtube_in_selected_profile",
        "reconnect_instagram_browser_profile",
        "reconnect_tiktok_browser_profile",
        "refresh_tiktok_cookies",
        "select_existing_browser_profile",
        "upgrade_media2md_or_report_internal_bug",
        "use_smaller_model_or_shorter_chunks",
        "verify_or_reauthenticate_instagram_session",
        "verify_or_reauthenticate_youtube_session",
        "verify_youtube_session_after_opening_youtube",
        "verify_youtube_session_or_configure_non_browser_access",
    }
)


def is_required_action(value: str | None) -> bool:
    return bool(value) and str(value) in REQUIRED_ACTIONS


def validate_required_action(value: str | None) -> str | None:
    if value is None:
        return None
    text = str(value)
    if text not in REQUIRED_ACTIONS:
        raise ValueError(f"Unknown required_action: {text}")
    return text
