from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class HealthResult:
    status: str
    message: str
    provider: str | None = None
    backend: str | None = None
    details: dict[str, object] = field(default_factory=dict)


@dataclass(frozen=True)
class ProviderResolutionResult:
    provider: str
    kind: str
    canonical_url: str
    creator: str | None = None
    media_id: str | None = None
