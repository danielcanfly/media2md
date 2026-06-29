from __future__ import annotations

from .provider_registry import all_provider_adapters
from .results import ProviderResolutionResult
from .urls import detect_provider, normalize_creator


PROVIDERS = ("instagram", "youtube", "tiktok")


def resolve_provider_for_creator(
    value: str,
    provider: str | None,
    *,
    command_name: str,
) -> str:
    if provider:
        return provider
    detected = detect_provider(value)
    if detected:
        return detected
    raise RuntimeError(
        f"{command_name} requires --provider when <creator> is a bare handle. "
        "Use a full creator URL or pass --provider instagram|youtube|tiktok."
    )


def normalize_creator_handle(provider: str, value: str) -> str:
    return str(normalize_creator(provider, value).creator)


def resolve_creator_target(
    value: str,
    provider: str | None,
    *,
    command_name: str,
) -> ProviderResolutionResult:
    chosen = resolve_provider_for_creator(value, provider, command_name=command_name)
    for adapter in all_provider_adapters():
        if adapter.name == chosen:
            return adapter.resolve_creator_input(value)
    normalized = normalize_creator(chosen, value)
    return ProviderResolutionResult(
        provider=normalized.provider,
        kind=normalized.kind,
        canonical_url=normalized.canonical_url,
        creator=normalized.creator,
        media_id=normalized.media_id,
    )
