from __future__ import annotations

import io
import json
from contextlib import redirect_stdout
from pathlib import Path

from media2md.bundle.scripts import media2md_registry as registry


def _capture_payload(func, *args, **kwargs) -> dict:
    stream = io.StringIO()
    with redirect_stdout(stream):
        func(*args, **kwargs)
    lines = [line for line in stream.getvalue().splitlines() if line.strip()]
    assert lines
    return json.loads(lines[-1])


def test_creator_run_summary_ndjson_uses_shared_cli_contract():
    payload = _capture_payload(
        registry._creator_run_summary,
        provider="youtube",
        handle="creator-name",
        batches=2,
        processed=4,
        failures=1,
        status="completed",
        remaining=3,
        output="ndjson",
        markdown_root=Path("/tmp/media2md/markdown/youtube/creator-name/videos"),
        latest_markdown_path="/tmp/media2md/markdown/youtube/creator-name/videos/example.md",
        strategy_summary={"transcription_progress:chunked": 2},
    )
    assert payload["event"] == "creator_run_completed"
    assert payload["schema"] == "media2md.cli.creator_run_completed/v1"
    assert payload["status"] == "ok"
    assert payload["sections"][0]["name"] == "run"
    assert payload["run_status"] == "completed"
    assert payload["provider"] == "youtube"
    assert payload["creator"] == "creator-name"
    assert payload["strategy_summary"] == {"transcription_progress:chunked": 2}


def test_registry_emit_cli_event_uses_shared_contract():
    payload = _capture_payload(
        registry.emit_cli_event,
        event="batch_started",
        section="run",
        status="ok",
        message="Batch started",
        data={"provider": "youtube", "creator": "creator-name", "batch_number": 1},
    )
    assert payload["event"] == "batch_started"
    assert payload["schema"] == "media2md.cli.batch_started/v1"
    assert payload["status"] == "ok"
    assert payload["sections"][0]["name"] == "run"
    assert payload["provider"] == "youtube"


def test_creator_run_event_status_maps_known_summary_states():
    assert registry.creator_run_event_status("completed") == "ok"
    assert registry.creator_run_event_status("paused_runtime_limit") == "timeout"
    assert registry.creator_run_event_status("stopped_max_failures") == "error"
    assert registry.creator_run_event_status("interrupted") == "warn"
