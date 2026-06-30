from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ProviderCapabilities:
    single_media: bool
    creator_sync: bool
    batch_drain: bool


@dataclass(frozen=True)
class ProviderMetadata:
    name: str
    backends: tuple[str, ...]
    capabilities: ProviderCapabilities
    extra: str | None = None
    default_backend: str | None = None


_CATALOG: tuple[ProviderMetadata, ...] = (
    ProviderMetadata(
        name="instagram",
        backends=("gallery-dl", "instaloader"),
        capabilities=ProviderCapabilities(single_media=True, creator_sync=True, batch_drain=True),
        extra="instagram",
        default_backend="auto",
    ),
    ProviderMetadata(
        name="youtube",
        backends=("yt-dlp", "yt-dlp-ejs"),
        capabilities=ProviderCapabilities(single_media=True, creator_sync=True, batch_drain=True),
        extra="youtube",
    ),
    ProviderMetadata(
        name="tiktok",
        backends=("yt-dlp",),
        capabilities=ProviderCapabilities(single_media=True, creator_sync=True, batch_drain=True),
        extra="tiktok",
    ),
)


def provider_catalog() -> tuple[ProviderMetadata, ...]:
    return _CATALOG


def provider_names() -> tuple[str, ...]:
    return tuple(item.name for item in _CATALOG)


def provider_metadata(name: str) -> ProviderMetadata | None:
    chosen = name.lower()
    for item in _CATALOG:
        if item.name == chosen:
            return item
    return None
