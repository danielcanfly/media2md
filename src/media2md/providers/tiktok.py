from __future__ import annotations

from media2md.urls import detect_provider, normalize_creator

from ..probe import probe_command
from ..provider_contract import ProviderAdapter
from ..results import HealthResult, ProviderResolutionResult


class TikTokAdapter(ProviderAdapter):
    name = "tiktok"
    backends = ["yt-dlp"]

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
        probe = probe_command("yt-dlp", package="yt-dlp")
        if probe.ok:
            return HealthResult("ok", "yt-dlp is available", provider=self.name, backend="yt-dlp")
        if probe.status == "missing":
            return HealthResult("warn", "yt-dlp is not installed", provider=self.name, backend="yt-dlp")
        return HealthResult(probe.status, probe.hint or probe.output or "yt-dlp probe failed", provider=self.name, backend="yt-dlp")
