from __future__ import annotations

from media2md.urls import detect_provider, normalize_creator

from ..probe import probe_command
from ..provider_contract import ProviderAdapter
from ..results import HealthResult, ProviderResolutionResult


class InstagramAdapter(ProviderAdapter):
    name = "instagram"
    backends = ["gallery-dl", "instaloader"]

    def can_handle_url(self, url: str) -> bool:
        return detect_provider(url) == self.name

    def resolve_creator_input(self, value: str) -> ProviderResolutionResult:
        normalized = normalize_creator(self.name, value)
        return ProviderResolutionResult(
            provider=normalized.provider,
            kind=normalized.kind,
            canonical_url=normalized.canonical_url,
            creator=normalized.creator,
            media_id=normalized.media_id,
        )

    def health_check(self) -> HealthResult:
        primary = probe_command("gallery-dl", package="gallery-dl")
        if primary.ok:
            return HealthResult("ok", "gallery-dl is available", provider=self.name, backend="gallery-dl")
        if primary.status == "missing":
            return HealthResult("warn", "gallery-dl is not installed", provider=self.name, backend="gallery-dl")
        return HealthResult(primary.status, primary.hint or primary.output or "gallery-dl probe failed", provider=self.name, backend="gallery-dl")
