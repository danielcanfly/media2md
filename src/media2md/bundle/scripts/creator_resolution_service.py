from __future__ import annotations

from media2md.provider_catalog import provider_names
from media2md_urls import detect_provider as detect_provider_url, normalize_creator as normalize_creator_target


PROVIDERS = provider_names()


def detect_provider(value: str) -> str | None:
    return detect_provider_url(value)


def normalize_creator_handle(provider: str, value: str) -> str:
    return str(normalize_creator_target(provider, value).creator)


def resolve_provider_for_creator(value: str, provider: str | None, *, command_name: str) -> str:
    if provider:
        chosen = provider.lower()
        if chosen in PROVIDERS:
            return chosen
        raise RuntimeError(
            f"Unsupported provider: {provider}. Use one of {', '.join(PROVIDERS)}."
        )
    detected = detect_provider(value)
    if detected:
        return detected
    raise RuntimeError(
        f"{command_name} requires --provider when <creator> is a bare handle. "
        f"Use a full creator URL or pass --provider {'|'.join(PROVIDERS)}."
    )
