#!/usr/bin/env python3
from __future__ import annotations

from collections.abc import Callable
from typing import Any

RegistryCall = Callable[[list[str]], int]
EmitCall = Callable[[dict[str, Any], str], None]


def _tracked(existing_row: dict[str, Any] | None) -> int:
    if not existing_row:
        return 0
    try:
        return max(0, int(existing_row.get("tracked") or 0))
    except (TypeError, ValueError):
        return 0


def _is_exact(existing_row: dict[str, Any] | None) -> bool:
    if not existing_row:
        return False
    value = existing_row.get("current_total_exact")
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "on"}
    return bool(value)


def prepare_catalog_for_creator_run(
    *,
    provider: str,
    creator_arg: str,
    normalized_creator: str,
    existing_row: dict[str, Any] | None,
    quick_window: int,
    output: str,
    registry_call: RegistryCall,
    emit_call: EmitCall,
) -> int:
    """Choose exactly one pre-run catalog action for every public CLI surface.

    A partial TikTok cursor catalog is already a valid processing source. Running a
    legacy profile Quick Sync before every batch is both redundant and expensive,
    so it is skipped until the cursor Full Sync reaches an exact terminal state.
    """
    tracked = _tracked(existing_row)
    usable_tiktok_catalog = provider == "tiktok" and existing_row is not None and tracked > 0
    if usable_tiktok_catalog:
        exact = _is_exact(existing_row)
        reason = "exact_catalog_available" if exact else "full_catalog_in_progress"
        payload = {
            "event": "auto_sync_skipped",
            "provider": "tiktok",
            "creator": normalized_creator,
            "reason": reason,
            "using_cached_catalog": True,
            "tracked": tracked,
            "current_total_exact": exact,
        }
        if output == "human":
            print(
                "AUTO_SYNC_SKIPPED provider=tiktok "
                f"reason={reason} using_cached_catalog=true "
                f"tracked={tracked} current_total_exact={str(exact).lower()}",
                flush=True,
            )
        else:
            emit_call(payload, output)
        return 0

    usable_bilibili_catalog = provider == "bilibili" and existing_row is not None and tracked > 0
    if usable_bilibili_catalog and _is_exact(existing_row):
        payload = {
            "event": "auto_sync_skipped",
            "provider": "bilibili",
            "creator": normalized_creator,
            "reason": "exact_catalog_available",
            "using_cached_catalog": True,
            "tracked": tracked,
            "current_total_exact": True,
        }
        if output == "human":
            print(
                "AUTO_SYNC_SKIPPED provider=bilibili "
                "reason=exact_catalog_available using_cached_catalog=true "
                f"tracked={tracked} current_total_exact=true",
                flush=True,
            )
        else:
            emit_call(payload, output)
        return 0

    mode = "quick" if existing_row is not None else "full"
    return registry_call([
        "sync",
        provider,
        creator_arg,
        "--mode",
        mode,
        "--quick-window",
        str(quick_window),
    ])
