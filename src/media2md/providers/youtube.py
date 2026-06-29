from __future__ import annotations

from media2md.urls import detect_provider, normalize_creator

from ..probe import probe_command
from ..provider_contract import ProviderAdapter
from ..provider_health import probe_health_result
from ..results import HealthResult, ProviderResolutionResult


class YouTubeAdapter(ProviderAdapter):
    name = "youtube"
    backends = ["yt-dlp", "yt-dlp-ejs"]

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
        return probe_health_result(
            provider=self.name,
            backend="yt-dlp",
            backends=self.backends,
            probe=probe,
            success_message="yt-dlp is available",
            missing_message="yt-dlp is not installed",
            failure_message="yt-dlp probe failed",
        )
