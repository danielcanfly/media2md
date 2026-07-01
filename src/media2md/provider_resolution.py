from __future__ import annotations

from .provider_catalog import provider_names
from .provider_registry import all_provider_adapters
from .results import ProviderResolutionResult
from .urls import detect_provider, normalize_creator


PROVIDERS = provider_names()


def resolve_provider_for_creator(
    value: str,
    provider: str | None,
    *,
    command_name: str,
) -> str:
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


def normalize_creator_handle(provider: str, value: str) -> str:
    return str(normalize_creator(provider, value).creator)


def resolve_bilibili_creator_from_video(value: str) -> ProviderResolutionResult:
    import importlib

    generic_media = importlib.import_module("media2md.bundle.scripts.generic_media")
    normalized = generic_media.normalize_media("bilibili", value)
    metadata = generic_media.inspect_bilibili_metadata(normalized.canonical_url, str(normalized.media_id or ""))
    creator = str(metadata.get("channel_id") or "").strip()
    if not creator:
        raise RuntimeError("Bilibili video metadata did not include a canonical creator ID.")
    canonical = normalize_creator("bilibili", creator)
    return ProviderResolutionResult(
        provider="bilibili",
        kind="creator",
        canonical_url=canonical.canonical_url,
        creator=canonical.creator,
        media_id=str(normalized.media_id or ""),
        surface=canonical.surface,
        lookup_source="bilibili_video",
    )


def resolve_creator_target(
    value: str,
    provider: str | None,
    *,
    command_name: str,
) -> ProviderResolutionResult:
    chosen = resolve_provider_for_creator(value, provider, command_name=command_name)
    for adapter in all_provider_adapters():
        if adapter.name == chosen:
            result = adapter.resolve_creator_input(value)
            if chosen == "bilibili" and result.lookup_source == "bilibili_video":
                return resolve_bilibili_creator_from_video(value)
            return result
    normalized = normalize_creator(chosen, value)
    return ProviderResolutionResult(
        provider=normalized.provider,
        kind=normalized.kind,
        canonical_url=normalized.canonical_url,
        creator=normalized.creator,
        media_id=normalized.media_id,
        surface=normalized.surface,
        lookup_source="direct_creator",
    )
