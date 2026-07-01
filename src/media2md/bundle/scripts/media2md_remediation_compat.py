from __future__ import annotations


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


def settings_show_command(*, output: str | None = None) -> str:
    if output:
        return f"media2md settings show --output {output}"
    return "media2md settings show"


def doctor_access_command(provider: str) -> str:
    placeholders = {
        "youtube": "--video-id=<VIDEO_ID>",
        "tiktok": "--video-id=<VIDEO_ID> --creator=<CREATOR>",
    }
    suffix = placeholders.get(provider, "")
    return f"media2md doctor {provider}-access{(' ' + suffix) if suffix else ''}".strip()


def guidance_lines(*groups) -> list[str]:
    lines: list[str] = []
    for group in groups:
        for item in group:
            text = str(item).strip()
            if text and text not in lines:
                lines.append(text)
    return lines


def youtube_profile_guidance(*, action: str, browser: str | None = None, profile: str | None = None) -> list[str]:
    label = profile or "the selected browser profile"
    browser_name = browser or "Chrome"
    if action == "doctor":
        return [f"Run: {doctor_access_command('youtube')}"]
    if action == "open_youtube":
        return [
            f"Open youtube.com in {browser_name} profile '{label}' and confirm the avatar is signed in.",
            f"Run: {auth_verify_command('youtube')}",
            "Do not let an agent repeatedly retry authenticated downloads until authenticated=true.",
        ]
    return [f"Run: {auth_verify_command('youtube')}"]


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
                f"Run: {auth_verify_command('youtube')}",
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
    elif required_action == "verify_or_reauthenticate_instagram_session":
        lines.append(f"Run: {auth_verify_command('instagram')}")
    elif required_action == "configure_non_browser_po_token_or_try_another_video":
        lines.extend(
            [
                f"Run: {settings_show_command()}",
                f"Run: {doctor_access_command('youtube')}",
            ]
        )
    elif required_action in {"verify_or_reauthenticate_youtube_session", "verify_youtube_session_or_configure_non_browser_access"}:
        lines.extend(youtube_profile_guidance(action="doctor"))
    return guidance_lines(lines)
