from __future__ import annotations

import json

from pathlib import Path

from media2md.bundle.scripts.public_cli_creator_service import (
    emit_creator_run_catalog_context,
    creator_run_catalog_preflight,
    creator_run_context,
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
    assert payload["event"] == "creator_policy"
    assert payload["schema"] == "media2md.cli.creator_policy/v1"
    assert payload["status"] == "ok"
    assert payload["sections"][0]["name"] == "policy"
    assert payload["provider"] == "youtube"
    assert payload["creator"] == "creator-name"
    assert payload["policy"] == {"provider": "youtube", "creator": "creator-name"}


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


def test_creator_run_context_computes_mode_and_batch_sizes():
    args = _Args(mode=None, batch_size=1, batch_size_type=["youtube_long=2"])
    policy = {
        "sync": {"quick_window": 100},
        "processing": {
            "mode": "batch",
            "batch_size": 100,
            "batch_sizes": {"youtube_long": 1, "youtube_short": 30},
        },
    }
    context = creator_run_context(
        args,
        provider="youtube",
        creator="creator-name",
        policy=policy,
        parse_batch_size_assignments=lambda values: {"youtube_long": 2} if values else {},
        normalize_batch_sizes=lambda values: dict(values or {}),
        typed_batch_sizes_supported=True,
    )
    assert context["mode"] == "batch"
    assert context["batch_size"] == 1
    assert context["batch_sizes"] == {"youtube_long": 2, "youtube_short": 30}


def test_creator_run_catalog_preflight_returns_existing_row_on_success():
    args = _Args(creator="@acta.so", output="ndjson")
    rows = [{"provider": "tiktok", "handle": "acta.so", "tracked": 3, "last_sync_at": "2026-06-30T00:00:00+00:00"}]
    emitted = []
    existing_row, outcome = creator_run_catalog_preflight(
        args=args,
        provider="tiktok",
        creator="acta.so",
        policy={"sync": {"quick_window": 100}},
        registry_rows=rows,
        prepare_catalog_for_creator_run=lambda **kwargs: 0,
        registry_call=lambda cmd: 0,
        emit_call=lambda payload, output: emitted.append(payload),
    )
    assert existing_row == rows[0]
    assert outcome is None
    assert emitted[0]["event"] == "creator_run_catalog_context"
    assert emitted[0]["schema"] == "media2md.cli.creator_run_catalog_context/v1"
    assert emitted[0]["status"] in {"ok", "warn"}
    assert emitted[0]["sections"][0]["name"] == "catalog"
    assert emitted[0]["using_saved_catalog"] is True


def test_emit_creator_run_catalog_context_includes_youtube_surfaces(capsys):
    class _Args:
        output = "human"

    emit_creator_run_catalog_context(
        args=_Args(),
        provider="youtube",
        creator="creator-name",
        existing_row={
            "source_url": "https://www.youtube.com/@creator-name/shorts",
            "tracked": 12,
            "last_sync_at": "2026-06-30T00:00:00+00:00",
            "current_total_exact": 1,
        },
        emit=lambda payload, output: None,
        youtube_catalog_surfaces=lambda: ("videos", "shorts", "streams"),
    )
    out = capsys.readouterr().out
    assert "CREATOR_RUN_CATALOG" in out
    assert "catalog_surface=shorts" in out
    assert "catalog_surfaces=videos,shorts,streams" in out
    assert "catalog_source_url=https://www.youtube.com/@creator-name/shorts" in out


def test_emit_creator_run_catalog_context_includes_instagram_surfaces(capsys):
    class _Args:
        output = "human"

    emit_creator_run_catalog_context(
        args=_Args(),
        provider="instagram",
        creator="creator.name",
        existing_row={
            "source_url": "https://www.instagram.com/creator.name/",
            "tracked": 12,
            "last_sync_at": "2026-06-30T00:00:00+00:00",
            "current_total_exact": 1,
        },
        emit=lambda payload, output: None,
        youtube_catalog_surfaces=None,
    )
    out = capsys.readouterr().out
    assert "CREATOR_RUN_CATALOG" in out
    assert "catalog_surface=posts" in out
    assert "catalog_surfaces=reels,posts" in out
    assert "catalog_source_url=https://www.instagram.com/creator.name/" in out


def test_emit_creator_run_catalog_context_includes_bilibili_video_surface(capsys):
    class _Args:
        output = "human"

    emit_creator_run_catalog_context(
        args=_Args(),
        provider="bilibili",
        creator="1510588366",
        existing_row={
            "source_url": "https://space.bilibili.com/1510588366",
            "tracked": 50,
            "last_sync_at": "2026-07-01T00:00:00+00:00",
            "current_total_exact": 1,
        },
        emit=lambda payload, output: None,
        youtube_catalog_surfaces=None,
    )
    out = capsys.readouterr().out
    assert "catalog_surface=videos" in out
    assert "catalog_surfaces=videos" in out
    assert "catalog_source_url=https://space.bilibili.com/1510588366" in out


def test_creator_run_instagram_forwards_batch_sizes_and_catalog_surface():
    recorded: list[list[str]] = []

    class _Args:
        creator = "@creator.name"
        output = "human"
        since = None
        until = None
        rank_from = None
        rank_to = None
        order = None
        max_batches = None
        max_runtime_minutes = None
        max_failures = None
        sleep_between_batches = None
        stop_on_failure = False
        retry_failed = False
        catalog_surface = "mixed"

    from media2md.bundle.scripts.public_cli_creator_service import creator_run_instagram

    result = creator_run_instagram(
        _Args(),
        batch_size=10,
        batch_sizes={"instagram_reel": 2, "instagram_post": 3, "instagram_carousel": 1},
        mode="batch",
        core=lambda cmd: recorded.append(list(cmd)) or 0,
        retry_failed_supported=True,
        refresh_registry=lambda: None,
    )
    assert result == 0
    assert recorded[0][0:3] == ["creator", "run", "@creator.name"]
    assert "--batch-sizes-json" in recorded[0]
    payload = json.loads(recorded[0][recorded[0].index("--batch-sizes-json") + 1])
    assert payload["instagram_post"] == 3
    assert payload["instagram_carousel"] == 1
    assert recorded[0][-2:] == ["--catalog-surface", "mixed"]
