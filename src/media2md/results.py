from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class HealthResult:
    status: str
    message: str
    provider: str | None = None
    active_backend: str | None = None
    backends: tuple[str, ...] = ()
    hints: tuple[str, ...] = ()
    artifacts: dict[str, str] = field(default_factory=dict)
    # Deprecated alias retained for compatibility with older callers/tests.
    backend: str | None = None
    details: dict[str, object] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "backends", tuple(self.backends))
        object.__setattr__(self, "hints", tuple(self.hints))
        object.__setattr__(self, "artifacts", dict(self.artifacts))
        object.__setattr__(self, "details", dict(self.details))
        if self.active_backend is None and self.backend is not None:
            object.__setattr__(self, "active_backend", self.backend)
        if self.backend is None and self.active_backend is not None:
            object.__setattr__(self, "backend", self.active_backend)
        if not self.backends:
            chosen = self.active_backend or self.backend
            if chosen:
                object.__setattr__(self, "backends", (chosen,))

    def as_dict(self) -> dict[str, object]:
        return {
            "status": self.status,
            "message": self.message,
            "provider": self.provider,
            "active_backend": self.active_backend,
            "backends": list(self.backends),
            "hints": list(self.hints),
            "artifacts": dict(self.artifacts),
            "details": dict(self.details),
            "backend": self.backend,
        }


@dataclass(frozen=True)
class ProviderResolutionResult:
    provider: str
    kind: str
    canonical_url: str
    creator: str | None = None
    media_id: str | None = None
    surface: str | None = None
