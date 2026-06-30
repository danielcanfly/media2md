from __future__ import annotations

from media2md.required_actions import REQUIRED_ACTIONS, is_required_action, validate_required_action


def test_required_action_catalog_contains_known_public_actions():
    for action in (
        "install_impersonation",
        "install_provider_extra",
        "provide_valid_video_id",
        "verify_youtube_session_or_configure_non_browser_access",
        "upgrade_media2md_or_report_internal_bug",
    ):
        assert action in REQUIRED_ACTIONS
        assert is_required_action(action) is True
        assert validate_required_action(action) == action


def test_required_action_validation_rejects_unknown_values():
    try:
        validate_required_action("totally_unknown_required_action")
    except ValueError as exc:
        assert "Unknown required_action" in str(exc)
    else:
        raise AssertionError("expected ValueError")

