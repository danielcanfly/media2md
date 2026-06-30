from __future__ import annotations

from .provider_catalog import provider_catalog


PROVIDERS = {
    item.name: {
        "single_media": item.capabilities.single_media,
        "creator_sync": item.capabilities.creator_sync,
        "batch_drain": item.capabilities.batch_drain,
        "commands": {
            "read": list(item.command_capabilities.read),
            "write": list(item.command_capabilities.write),
            "confirmation": list(item.command_capabilities.confirmation),
        },
        "backends": list(item.backends),
        "default_backend": item.default_backend,
        "extra": item.extra,
    }
    for item in provider_catalog()
}
