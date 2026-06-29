from __future__ import annotations

from media2md.remediation_service import (
    auth_status_command,
    auth_verify_command,
    media2md_install_command,
    media2md_install_guidance,
    provider_profile_guidance,
    uninstall_dry_run_next_step,
    youtube_profile_guidance,
)


def test_media2md_install_command_without_extras():
    assert media2md_install_command() == "python -m pip install -U media2md"


def test_media2md_install_command_with_sorted_deduped_extras():
    assert media2md_install_command("tiktok", "youtube", "youtube") == 'python -m pip install -U "media2md[tiktok,youtube]"'


def test_media2md_install_guidance_wraps_command():
    assert media2md_install_guidance("youtube") == 'Run: python -m pip install -U "media2md[youtube]"'


def test_auth_commands_render_public_cli_forms():
    assert auth_verify_command("instagram") == "media2md auth verify instagram"
    assert auth_status_command(output="ndjson") == "media2md auth status --output ndjson"


def test_provider_profile_guidance_login_is_universal():
    guidance = provider_profile_guidance(
        "instagram",
        browser="chrome",
        profile="Profile 1",
        action="login",
    )
    assert guidance[0] == "Open Profile 1 in chrome."
    assert guidance[1] == "Log in to instagram manually."
    assert guidance[2] == "Run: media2md auth verify instagram"


def test_youtube_profile_guidance_uses_public_media2md_commands():
    guidance = youtube_profile_guidance(action="connect")
    assert guidance == [
        "Run: media2md auth profiles youtube --browser <BROWSER>",
        "Run: media2md auth connect youtube --browser <BROWSER> --profile <PROFILE>",
        "Run: media2md auth verify youtube",
    ]


def test_uninstall_dry_run_next_step_matches_cli_message():
    assert uninstall_dry_run_next_step() == "run `media2md uninstall` to remove the installed Python package"
