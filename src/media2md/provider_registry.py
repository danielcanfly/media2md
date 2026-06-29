from __future__ import annotations

from .provider_contract import ProviderAdapter
from .providers import get_provider_adapters


def all_provider_adapters() -> list[ProviderAdapter]:
    return list(get_provider_adapters())


def provider_adapter(name: str) -> ProviderAdapter | None:
    chosen = name.lower()
    for adapter in all_provider_adapters():
        if adapter.name == chosen:
            return adapter
    return None
