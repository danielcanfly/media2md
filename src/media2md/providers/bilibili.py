from __future__ import annotations

from media2md.urls import detect_provider, normalize_creator

from ..provider_catalog import provider_metadata
from ..provider_contract import ProviderAdapter
from ..results import HealthResult, ProviderResolutionResult


class BilibiliAdapter(ProviderAdapter):
    name = "bilibili"
    backends = list(provider_metadata("bilibili").backends)

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
            surface=normalized.surface,
        )

    def health_check(self) -> HealthResult:
        try:
            import bilibili_api  # noqa: F401
        except Exception:
            return HealthResult(
                status="missing",
                message="bilibili-api-python is not installed",
                provider=self.name,
                active_backend=None,
                backends=tuple(self.backends),
                hints=('Run: python -m pip install -U "media2md[bilibili]"',),
                details={"probe_status": "missing"},
            )
        return HealthResult(
            status="ok",
            message="bilibili-api-python is available",
            provider=self.name,
            active_backend="bilibili-api",
            backends=tuple(self.backends),
            hints=(),
            details={"probe_status": "ok"},
        )
