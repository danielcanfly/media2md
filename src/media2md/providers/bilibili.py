from __future__ import annotations

from media2md.urls import BILIBILI_BVID_RE, detect_provider, normalize_creator

from ..provider_catalog import provider_metadata
from ..provider_contract import ProviderAdapter
from ..results import HealthResult, ProviderResolutionResult


class BilibiliAdapter(ProviderAdapter):
    name = "bilibili"
    backends = list(provider_metadata("bilibili").backends)

    def can_handle_url(self, url: str) -> bool:
        return detect_provider(url) == self.name

    def resolve_creator_input(self, value: str) -> ProviderResolutionResult:
        text = str(value or "").strip()
        if "bilibili.com/video/" in text.lower() or BILIBILI_BVID_RE.fullmatch(text):
            return ProviderResolutionResult(
                provider=self.name,
                kind="creator",
                canonical_url=text if text.startswith("http") else f"https://www.bilibili.com/video/{text}",
                creator=None,
                media_id=(text if BILIBILI_BVID_RE.fullmatch(text) else None),
                surface=None,
                lookup_source="bilibili_video",
            )
        normalized = normalize_creator(self.name, value)
        return ProviderResolutionResult(
            provider=normalized.provider,
            kind=normalized.kind,
            canonical_url=normalized.canonical_url,
            creator=normalized.creator,
            media_id=normalized.media_id,
            surface=normalized.surface,
            lookup_source="direct_creator",
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
