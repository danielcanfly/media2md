from __future__ import annotations

from abc import ABC, abstractmethod

from .results import HealthResult, ProviderResolutionResult


class ProviderAdapter(ABC):
    name: str = ""
    backends: list[str] = []

    @abstractmethod
    def can_handle_url(self, url: str) -> bool:
        ...

    @abstractmethod
    def resolve_creator_input(self, value: str) -> ProviderResolutionResult:
        ...

    @abstractmethod
    def health_check(self) -> HealthResult:
        ...
