from __future__ import annotations

from typing import Iterable
from .provider_catalog import provider_command_matrix


def media2md_install_command(*extras: str) -> str:
    selected = [extra.strip() for extra in extras if extra and extra.strip()]
    if not selected:
        return "python -m pip install -U media2md"
    unique = sorted(dict.fromkeys(selected))
    return f'python -m pip install -U "media2md[{",".join(unique)}]"'


def media2md_install_guidance(*extras: str) -> str:
    return f"Run: {media2md_install_command(*extras)}"


def auth_verify_command(provider: str) -> str:
    return f"media2md auth verify {provider}"


def auth_verify_guidance(provider: str) -> str:
    return f"Run: {auth_verify_command(provider)}"


def status_command(*, output: str | None = None) -> str:
    if output:
        return f"media2md status --output {output}"
    return "media2md status"


def auth_status_command(*, output: str | None = None) -> str:
    if output:
        return f"media2md auth status --output {output}"
    return "media2md auth status"


def uninstall_command() -> str:
    return "media2md uninstall"


def uninstall_dry_run_next_step() -> str:
    return f"run `{uninstall_command()}` to remove the installed Python package"


def provider_profile_guidance(
    provider: str,
    *,
    browser: str | None = None,
    profile: str | None = None,
    action: str,
) -> list[str]:
    label = profile or "the selected browser profile"
    browser_text = f" in {browser}" if browser else ""
    if action == "login":
        return [
            f"Open {label}{browser_text}.",
            f"Log in to {provider} manually.",
            auth_verify_guidance(provider),
        ]
    if action == "challenge":
        return [
            f"Open {label}{browser_text} and complete the {provider} verification challenge.",
            auth_verify_guidance(provider),
        ]
    if action == "refresh_login":
        return [
            f"Open {label}{browser_text} and refresh the {provider} login.",
            auth_verify_guidance(provider),
        ]
    if action == "open_site":
        return [
            f"Open {provider}.com or the native app in {label}{browser_text} and confirm the account is signed in.",
            auth_verify_guidance(provider),
        ]
    raise ValueError(f"Unsupported provider profile guidance action: {action}")


def youtube_profile_guidance(
    *,
    browser: str | None = None,
    profile: str | None = None,
    action: str,
) -> list[str]:
    label = profile or "the selected browser profile"
    browser_name = browser or "Chrome"
    if action == "connect":
        return [
            "Run: media2md auth profiles youtube --browser <BROWSER>",
            "Run: media2md auth connect youtube --browser <BROWSER> --profile <PROFILE>",
            auth_verify_guidance("youtube"),
        ]
    if action == "reconnect":
        return ["List profiles again and reconnect an existing profile."]
    if action == "close_browser":
        return [
            f"Confirm YouTube is signed in inside {browser_name} profile '{label}'.",
            f"Close {browser_name} if macOS blocks cookie database access.",
            auth_verify_guidance("youtube"),
        ]
    if action == "login":
        return [
            f"Open {browser_name} profile '{label}' and sign in to YouTube.",
            auth_verify_guidance("youtube"),
        ]
    if action == "refresh_login":
        return [
            f"Open {browser_name} profile '{label}' and refresh the YouTube login.",
            auth_verify_guidance("youtube"),
        ]
    if action == "open_youtube":
        return [
            f"Open youtube.com in {browser_name} profile '{label}' and confirm the avatar is signed in.",
            auth_verify_guidance("youtube"),
            "Do not let an agent repeatedly retry authenticated downloads until authenticated=true.",
        ]
    if action == "doctor":
        return ["Run: media2md doctor youtube-access --video-id=<VIDEO_ID>"]
    raise ValueError(f"Unsupported YouTube guidance action: {action}")


def guidance_lines(*groups: Iterable[str]) -> list[str]:
    lines: list[str] = []
    for group in groups:
        for item in group:
            text = str(item).strip()
            if text and text not in lines:
                lines.append(text)
    return lines


def provider_command_guidance(provider: str) -> dict[str, list[str]]:
    return provider_command_matrix().get(provider, {"read": [], "write": [], "confirmation": []})


def provider_access_guidance(
    provider: str,
    *,
    error_code: str | None = None,
    required_action: str | None = None,
) -> list[str]:
    lines: list[str] = []
    if error_code == "missing_dependency":
        lines.append(media2md_install_guidance(provider))
    if error_code == "impersonation_unavailable":
        lines.append(media2md_install_guidance("tiktok", "youtube"))
    if error_code == "youtube_po_token_required":
        lines.extend(
            [
                "Run: media2md auth verify youtube",
                "Run: media2md doctor youtube-access --video-id=<VIDEO_ID>",
            ]
        )
    if required_action == "provide_valid_video_id":
        lines.append("Retry with a valid media URL or media ID.")
    elif required_action == "configure_youtube_audio_strategies":
        lines.append("Run: media2md settings show")
    elif required_action == "install_impersonation":
        lines.append(media2md_install_guidance("tiktok", "youtube"))
    elif required_action == "install_provider_extra":
        lines.append(media2md_install_guidance(provider))
    elif required_action in {"verify_or_reauthenticate_youtube_session", "verify_youtube_session_or_configure_non_browser_access"}:
        lines.extend(youtube_profile_guidance(action="doctor"))
    return guidance_lines(lines)
