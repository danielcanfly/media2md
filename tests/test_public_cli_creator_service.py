from __future__ import annotations

from pathlib import Path

from media2md.bundle.scripts.public_cli_creator_service import (
    creator_policy_payload,
    creator_run_registry_command,
    merge_batch_sizes,
    resolve_existing_row,
)


class _Args:
    def __init__(self, **kwargs):
        self.creator = kwargs.get("creator", "@creator-name")
        self.mode = kwargs.get("mode", "batch")
        self.batch_size = kwargs.get("batch_size")
        self.batch_size_type = kwargs.get("batch_size_type", [])
        self.max_batches = kwargs.get("max_batches")
        self.max_runtime_minutes = kwargs.get("max_runtime_minutes")
        self.max_failures = kwargs.get("max_failures")
        self.sleep_between_batches = kwargs.get("sleep_between_batches")
        self.order = kwargs.get("order")
        self.output = kwargs.get("output", "ndjson")
        self.stop_on_failure = kwargs.get("stop_on_failure", False)
        self.since = kwargs.get("since")
        self.until = kwargs.get("until")
        self.rank_from = kwargs.get("rank_from")
        self.rank_to = kwargs.get("rank_to")
        self.allow_stale_catalog = kwargs.get("allow_stale_catalog", False)
        self.force_full = kwargs.get("force_full", False)


def test_creator_policy_payload_wraps_effective_policy():
    payload = creator_policy_payload(
        provider="youtube",
        creator="creator-name",
        effective_policy=lambda provider, creator: {"provider": provider, "creator": creator},
    )
    assert payload == {
        "event": "creator_policy",
        "provider": "youtube",
        "creator": "creator-name",
        "policy": {"provider": "youtube", "creator": "creator-name"},
    }


def test_resolve_existing_row_matches_case_insensitively():
    rows = [{"provider": "tiktok", "handle": "Acta.SO", "tracked": 1}]
    row = resolve_existing_row(rows, "tiktok", "acta.so")
    assert row == rows[0]


def test_merge_batch_sizes_supports_typed_assignments():
    args = _Args(batch_size=1, batch_size_type=["youtube_long=2"])
    batch_size, batch_sizes = merge_batch_sizes(
        args=args,
        processing={
            "mode": "batch",
            "batch_size": 100,
            "batch_sizes": {"youtube_long": 1, "youtube_short": 30},
        },
        parse_batch_size_assignments=lambda values: {"youtube_long": 2} if values else {},
        normalize_batch_sizes=lambda values: dict(values or {}),
        typed_batch_sizes_supported=True,
    )
    assert batch_size == 1
    assert batch_sizes == {"youtube_long": 2, "youtube_short": 30}


def test_merge_batch_sizes_can_disable_typed_defaults():
    args = _Args(batch_size=1, batch_size_type=[])
    batch_size, batch_sizes = merge_batch_sizes(
        args=args,
        processing={
            "mode": "batch",
            "batch_size": 100,
            "batch_sizes": {"tiktok_video": 100},
        },
        parse_batch_size_assignments=lambda values: {},
        normalize_batch_sizes=lambda values: dict(values or {}),
        typed_batch_sizes_supported=True,
    )
    assert batch_size == 1
    assert batch_sizes == {}


def test_creator_run_registry_command_can_include_typed_batch_sizes():
    args = _Args(
        creator="@acta.so",
        batch_size=1,
        max_batches=1,
        max_runtime_minutes=10,
        max_failures=2,
        sleep_between_batches=0,
    )
    policy = {
        "processing": {
            "mode": "batch",
            "max_batches": 9,
            "max_runtime_minutes": 99,
            "max_failures": 8,
            "sleep_between_batches": 7,
            "stop_on_failure": False,
        },
        "filters": {"order": "newest_first", "since": None, "until": None, "rank_from": None, "rank_to": None},
    }
    cmd = creator_run_registry_command(
        args,
        provider="tiktok",
        policy=policy,
        batch_size=1,
        batch_sizes={"tiktok_video": 1},
        include_typed_batch_sizes=True,
    )
    assert cmd[0:6] == ["run", "tiktok", "@acta.so", "--mode", "batch", "--batch-size"]
    assert "--batch-sizes-json" in cmd


def test_creator_run_registry_command_can_skip_typed_batch_sizes():
    args = _Args(creator="@creator-name")
    policy = {
        "processing": {
            "mode": "batch",
            "max_batches": 1,
            "max_runtime_minutes": 10,
            "max_failures": 1,
            "sleep_between_batches": 0,
            "stop_on_failure": False,
        },
        "filters": {"order": "newest_first", "since": None, "until": None, "rank_from": None, "rank_to": None},
    }
    cmd = creator_run_registry_command(
        args,
        provider="youtube",
        policy=policy,
        batch_size=100,
        batch_sizes={},
        include_typed_batch_sizes=False,
    )
    assert "--batch-sizes-json" not in cmd
