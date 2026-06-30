from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ProviderCapabilities:
    single_media: bool
    creator_sync: bool
    batch_drain: bool


@dataclass(frozen=True)
class ProviderCommandCapabilities:
    read: tuple[str, ...] = ()
    write: tuple[str, ...] = ()
    confirmation: tuple[str, ...] = ()


@dataclass(frozen=True)
class ProviderMetadata:
    name: str
    backends: tuple[str, ...]
    capabilities: ProviderCapabilities
    command_capabilities: ProviderCommandCapabilities
    extra: str | None = None
    default_backend: str | None = None


_CATALOG: tuple[ProviderMetadata, ...] = (
    ProviderMetadata(
        name="instagram",
        backends=("gallery-dl", "instaloader"),
        capabilities=ProviderCapabilities(single_media=True, creator_sync=True, batch_drain=True),
        command_capabilities=ProviderCommandCapabilities(
            read=("auth status", "creator status", "creator policy show", "doctor instagram-access"),
            write=("auth connect instagram", "creator add", "creator refresh-catalog", "creator run"),
            confirmation=("creator delete",),
        ),
        extra="instagram",
        default_backend="auto",
    ),
    ProviderMetadata(
        name="youtube",
        backends=("yt-dlp", "yt-dlp-ejs"),
        capabilities=ProviderCapabilities(single_media=True, creator_sync=True, batch_drain=True),
        command_capabilities=ProviderCommandCapabilities(
            read=("auth status", "creator status", "creator policy show", "doctor youtube-access"),
            write=("auth connect youtube", "creator add", "creator refresh-catalog", "creator run"),
            confirmation=("creator delete",),
        ),
        extra="youtube",
    ),
    ProviderMetadata(
        name="tiktok",
        backends=("yt-dlp",),
        capabilities=ProviderCapabilities(single_media=True, creator_sync=True, batch_drain=True),
        command_capabilities=ProviderCommandCapabilities(
            read=("auth status", "creator status", "creator policy show", "doctor tiktok-access"),
            write=("auth connect tiktok", "creator add", "creator refresh-catalog", "creator run"),
            confirmation=("creator delete",),
        ),
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


def provider_command_matrix() -> dict[str, dict[str, list[str]]]:
    return {
        item.name: {
            "read": list(item.command_capabilities.read),
            "write": list(item.command_capabilities.write),
            "confirmation": list(item.command_capabilities.confirmation),
        }
        for item in _CATALOG
    }
