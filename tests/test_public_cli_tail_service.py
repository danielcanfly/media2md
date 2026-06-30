from __future__ import annotations

import argparse
import json
from pathlib import Path

from media2md.bundle.scripts.public_cli_tail_service import (
    build_scheduler_creator_run_namespace,
    scheduler_tick_common,
    uninstall_common,
    update_check_common,
)


def test_build_scheduler_creator_run_namespace_media2md_shape():
    ns = build_scheduler_creator_run_namespace(
        provider="youtube",
        creator="creator-name",
        processing={
            "mode": "batch",
            "batch_size": 1,
            "max_batches": 2,
            "max_runtime_minutes": 3,
            "max_failures": 4,
            "stop_on_failure": True,
            "sleep_between_batches": 5,
        },
        output="ndjson",
        batch_size_type_supported=True,
        retry_failed_supported=True,
    )
    assert ns.provider == "youtube"
    assert ns.batch_size_type == []
    assert ns.retry_failed is False
    assert ns.allow_stale_catalog is False


def test_build_scheduler_creator_run_namespace_social2md_shape():
    ns = build_scheduler_creator_run_namespace(
        provider="tiktok",
        creator="creator-name",
        processing={
            "mode": "batch",
            "batch_size": 10,
            "max_batches": 2,
            "max_runtime_minutes": 3,
            "max_failures": 4,
            "stop_on_failure": False,
            "sleep_between_batches": 5,
        },
        output="human",
        batch_size_type_supported=False,
        retry_failed_supported=False,
    )
    assert not hasattr(ns, "batch_size_type")
    assert not hasattr(ns, "retry_failed")
    assert ns.output == "human"


def test_uninstall_common_dry_run_skips_pip(monkeypatch, capsys):
    calls = []
    monkeypatch.setattr("shutil.rmtree", lambda path: None)
    monkeypatch.setattr(Path, "home", lambda: Path("/tmp/home"))
    args = argparse.Namespace(purge_data=False, yes=False, confirm=None, dry_run=True)
    result = uninstall_common(
        args,
        data_delete_all=lambda _args: 0,
        remove_openclaw_cron=lambda: (0, []),
        run=lambda cmd, check=False: calls.append(cmd) or 0,
    )
    out = capsys.readouterr().out
    assert result == 0
    assert "package_uninstalled=false" in out
    assert calls == []


def test_update_check_common_ndjson_uses_emit(monkeypatch):
    emitted = []

    class _Response:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def read(self):
            return json.dumps({"tag_name": "v0.9.5", "html_url": "https://example.com/release"}).encode()

    monkeypatch.setattr("urllib.request.urlopen", lambda *args, **kwargs: _Response())
    args = argparse.Namespace(repository=None, output="ndjson")
    result = update_check_common(args, repository="danielcanfly/media2md", version="0.9.4", emit=lambda payload, output: emitted.append((payload, output)))
    assert result == 0
    assert emitted
    payload, output = emitted[0]
    assert output == "ndjson"
    assert payload["schema"] == "media2md.cli.update_check/v1"
    assert payload["update_available"] is True


def test_scheduler_tick_common_ndjson_uses_shared_schema():
    emitted = []
    args = argparse.Namespace(output="ndjson")
    result = scheduler_tick_common(
        args,
        load_policies=lambda: {"creators": {}},
        load_json=lambda path, default: {"creators": {}},
        atomic_json=lambda path, payload: None,
        scheduler_state_path=Path("/tmp/scheduler-state.json"),
        refresh_auth=lambda provider: None,
        core=lambda argv: 0,
        effective_policy=lambda provider, creator: {"sync": {"enabled": False, "every_minutes": 60, "full_every_minutes": 1440}, "processing": {"scheduled": False}},
        registry=lambda argv: 0,
        creator_run_builder=lambda provider, creator, processing, output: argparse.Namespace(),
        creator_run=lambda ns: 0,
        iso_now=lambda: "2026-06-30T00:00:00+00:00",
        emit=lambda payload, output: emitted.append((payload, output)),
    )
    assert result == 0
    assert emitted
    payload, output = emitted[0]
    assert output == "ndjson"
    assert payload["event"] == "media2md_scheduler_completed"
    assert payload["schema"] == "media2md.cli.scheduler_completed/v1"
