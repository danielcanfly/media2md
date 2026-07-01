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


def settings_show_command(*, output: str | None = None) -> str:
    if output:
        return f"media2md settings show --output {output}"
    return "media2md settings show"


def update_check_command(*, repository: str | None = None) -> str:
    if repository:
        return f"media2md update check --repository {repository}"
    return "media2md update check"


def doctor_access_command(provider: str) -> str:
    placeholders = {
        "youtube": "--video-id=<VIDEO_ID>",
        "tiktok": "--video-id=<VIDEO_ID> --creator=<CREATOR>",
        "bilibili": "--video-id=<BV_VIDEO_ID>",
    }
    suffix = placeholders.get(provider, "")
    return f"media2md doctor {provider}-access{(' ' + suffix) if suffix else ''}".strip()


def repair_identities_command(*, offline: bool = False) -> str:
    return "media2md repair identities --offline" if offline else "media2md repair identities"


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
        return [f"Run: {doctor_access_command('youtube')}"]
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
                auth_verify_guidance("youtube"),
                f"Run: {doctor_access_command('youtube')}",
            ]
        )
    if required_action == "provide_valid_video_id":
        lines.append("Retry with a valid media URL or media ID.")
    elif required_action == "configure_youtube_audio_strategies":
        lines.append(f"Run: {settings_show_command()}")
    elif required_action == "install_impersonation":
        lines.append(media2md_install_guidance("tiktok", "youtube"))
    elif required_action == "install_provider_extra":
        lines.append(media2md_install_guidance(provider))
        if provider == "bilibili":
            lines.append(f"Run: {doctor_access_command('bilibili')}")
    elif required_action == "verify_or_reauthenticate_instagram_session":
        lines.append(auth_verify_guidance("instagram"))
    elif required_action == "configure_non_browser_po_token_or_try_another_video":
        lines.extend(
            [
                f"Run: {settings_show_command()}",
                f"Run: {doctor_access_command('youtube')}",
            ]
        )
    elif required_action == "inspect_render_error":
        lines.append("Inspect the command log referenced by the failure output, then retry.")
    elif required_action in {"verify_or_reauthenticate_youtube_session", "verify_youtube_session_or_configure_non_browser_access"}:
        lines.extend(youtube_profile_guidance(action="doctor"))
    elif required_action == "repair_provider_identities":
        lines.extend(
            [
                f"Run: {repair_identities_command()}",
                f"Run: {status_command()}",
            ]
        )
    return guidance_lines(lines)
