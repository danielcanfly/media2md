from __future__ import annotations

from media2md_urls import detect_provider as detect_provider_url, normalize_creator as normalize_creator_target


def detect_provider(value: str) -> str | None:
    return detect_provider_url(value)


def normalize_creator_handle(provider: str, value: str) -> str:
    return str(normalize_creator_target(provider, value).creator)


def resolve_provider_for_creator(value: str, provider: str | None, *, command_name: str) -> str:
    if provider:
        return provider
    detected = detect_provider(value)
    if detected:
        return detected
    raise RuntimeError(
        f"{command_name} requires --provider when <creator> is a bare handle. "
        "Use a full creator URL or pass --provider instagram|youtube|tiktok."
    )
