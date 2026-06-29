from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from creator_resolution_service import normalize_creator_handle
from media2md_types import DEFAULT_BATCH_SIZES, normalize_batch_sizes, parse_batch_size_assignments


def merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    out = json.loads(json.dumps(base))
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(out.get(key), dict):
            out[key] = merge(out[key], value)
        else:
            out[key] = value
    return out


def policy_defaults(load_json, config_path: Path) -> dict[str, Any]:
    base = {
        "sync": {"enabled": False, "every_minutes": 1440, "full_every_minutes": 10080, "quick_window": 100},
        "processing": {
            "scheduled": False,
            "every_minutes": 4320,
            "mode": "batch",
            "batch_size": 100,
            "batch_sizes": dict(DEFAULT_BATCH_SIZES),
            "max_batches": 0,
            "max_runtime_minutes": 360,
            "max_failures": 10,
            "stop_on_failure": False,
            "sleep_between_batches": 5,
        },
        "filters": {"since": None, "until": None, "rank_from": None, "rank_to": None, "order": "newest_first"},
    }
    configured = load_json(config_path, {}).get("defaults", {})
    return merge(base, configured) if configured else base


def effective_policy(load_json, config_path: Path, policies_path: Path, provider: str, creator: str) -> dict[str, Any]:
    policies = load_json(policies_path, {"schema_version": 2, "creators": {}})
    policies.setdefault("schema_version", 2)
    policies.setdefault("creators", {})
    return merge(policy_defaults(load_json, config_path), policies["creators"].get(f"{provider}:{creator}", {}))


def set_policy(
    args: argparse.Namespace,
    *,
    load_json,
    atomic_json,
    config_path: Path,
    policies_path: Path,
    sync_enabled: bool | None = None,
) -> int:
    provider = args.provider
    creator = normalize_creator_handle(provider, args.creator)
    data = load_json(policies_path, {"schema_version": 2, "creators": {}})
    data.setdefault("schema_version", 2)
    data.setdefault("creators", {})
    entry = data["creators"].setdefault(f"{provider}:{creator}", {})
    if sync_enabled is not None:
        entry.setdefault("sync", {})["enabled"] = sync_enabled
    if getattr(args, "every", None) is not None:
        entry.setdefault("sync", {})["every_minutes"] = args.every
    if getattr(args, "full_every", None) is not None:
        entry.setdefault("sync", {})["full_every_minutes"] = args.full_every
    if getattr(args, "quick_window", None) is not None:
        entry.setdefault("sync", {})["quick_window"] = args.quick_window
    for key in ("mode", "batch_size", "max_batches", "max_runtime_minutes", "max_failures", "sleep_between_batches"):
        value = getattr(args, key, None)
        if value is not None:
            entry.setdefault("processing", {})[key] = value
    assignments = parse_batch_size_assignments(getattr(args, "batch_size_type", None))
    if assignments:
        entry.setdefault("processing", {}).setdefault("batch_sizes", {}).update(assignments)
    if getattr(args, "stop_on_failure", None) is not None:
        entry.setdefault("processing", {})["stop_on_failure"] = args.stop_on_failure
    if getattr(args, "scheduled_processing", None) is not None:
        entry.setdefault("processing", {})["scheduled"] = args.scheduled_processing
    if getattr(args, "processing_every", None) is not None:
        entry.setdefault("processing", {})["every_minutes"] = args.processing_every
    for key in ("since", "until", "rank_from", "rank_to", "order"):
        value = getattr(args, key, None)
        if value is not None:
            entry.setdefault("filters", {})[key] = value
    atomic_json(policies_path, data)
    result = effective_policy(load_json, config_path, policies_path, provider, creator)
    result["processing"]["batch_sizes"] = normalize_batch_sizes(result["processing"].get("batch_sizes"))
    print("CREATOR_POLICY_UPDATED")
    print(f"provider={provider}")
    print(f"creator={creator}")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0
