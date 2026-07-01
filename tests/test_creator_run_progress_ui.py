from __future__ import annotations

import argparse
import importlib.util
import sys
from pathlib import Path


def _load_registry():
    root = Path(__file__).resolve().parents[1]
    script_dir = root / "src" / "media2md" / "bundle" / "scripts"
    sys.path.insert(0, str(script_dir))
    try:
        script_path = script_dir / "media2md_registry.py"
        spec = importlib.util.spec_from_file_location("media2md_registry_progress_ui", script_path)
        assert spec and spec.loader
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module
    finally:
        sys.path.pop(0)


def test_render_stage_progress_looks_like_single_line_progress(capsys):
    module = _load_registry()
    module._render_stage_progress(
        provider="youtube",
        creator="creator-name",
        media_id="pBU1tCBOr8c",
        batch_number=1,
        batch_count=163,
        current=1,
        total=1,
        stage="transcribing",
        elapsed=93.0,
    )
    output = capsys.readouterr().out
    assert "\r" in output
    assert "transcribe" in output
    assert "[" in output and "]" in output
    assert "%" in output
    assert "item 1/1" in output
    assert "batch 1/163" in output
    assert "elapsed 00:01:33" in output


def test_render_stage_progress_includes_chunk_hint_for_long_transcription(capsys):
    module = _load_registry()
    module._render_stage_progress(
        provider="bilibili",
        creator="1510588366",
        media_id="BV1xwLJ6qEGw",
        batch_number=1,
        batch_count=7,
        current=3,
        total=5,
        stage="transcribing",
        elapsed=245.0,
        transcription_progress={
            "chunk_count": 7,
            "current_chunk_index": 3,
            "chunk_seconds": 1800,
        },
    )
    output = capsys.readouterr().out
    assert "chunk 3/7" in output
    assert "@1800s" in output


def test_creator_run_summary_includes_result_folder_and_finder_hint(capsys):
    module = _load_registry()
    root = Path("/tmp/media2md/markdown/youtube/creator-name/videos")
    module._creator_run_summary(
        provider="youtube",
        handle="creator-name",
        batches=1,
        processed=1,
        failures=0,
        status="completed",
        remaining=0,
        output="human",
        markdown_root=root,
        latest_markdown_path=str(root / "example.md"),
    )
    output = capsys.readouterr().out
    assert "latest_markdown_path=" in output
    assert "primary_output_surface=videos" in output
    assert "result_folder=" in output
    assert "open_in_finder_hint=open " in output


def test_instagram_human_run_summary_includes_result_folder_hint(monkeypatch, capsys):
    root = Path(__file__).resolve().parents[1]
    script_dir = root / "src" / "media2md" / "bundle" / "scripts"
    sys.path.insert(0, str(script_dir))
    try:
        script_path = script_dir / "social2md_core.py"
        spec = importlib.util.spec_from_file_location("social2md_progress_ui", script_path)
        assert spec and spec.loader
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
    finally:
        sys.path.pop(0)

    class _FakeTime:
        def __init__(self):
            self.value = 0.0

        def monotonic(self):
            self.value += 1.0
            return self.value

        def sleep(self, seconds):
            self.value += float(seconds)

    monkeypatch.setattr(module, "normalize_creator", lambda value: "career_cleo")
    monkeypatch.setattr(module, "load_config", lambda: {"timezone": "UTC"})
    monkeypatch.setattr(
        module,
        "effective_policy",
        lambda creator: {
            "processing": {
                "mode": "batch",
                "batch_size": 1,
                "max_batches": 1,
                "max_runtime_minutes": 360,
                "max_failures": 10,
                "stop_on_failure": False,
                "sleep_between_batches": 0,
            },
            "filters": {"since": None, "until": None, "rank_from": None, "rank_to": None, "order": "newest_first"},
            "sync": {"full_every_minutes": 1440, "quick_window": 100},
        },
    )
    monkeypatch.setattr(module, "ui_locale", lambda non_interactive: "en")
    monkeypatch.setattr(module, "resolve_boundary", lambda value, timezone_name, inclusive_end: value)
    monkeypatch.setattr(module, "load_performance_samples", lambda username: [])
    monkeypatch.setattr(module, "save_performance_samples", lambda username, samples: None)
    monkeypatch.setattr(module, "time", _FakeTime())
    monkeypatch.setattr(module, "sync_once", lambda *args, **kwargs: (0, {}))

    remaining = {"value": 1}
    monkeypatch.setattr(module, "filtered_candidate_count", lambda *args, **kwargs: remaining["value"])

    def fake_stream(command, **kwargs):
        remaining["value"] = 0
        return 0, {
            "completed": 1,
            "failed": 0,
            "report": "/tmp/report.json",
            "log": "/tmp/log.txt",
            "latest_markdown_path": "/tmp/media2md/markdown/instagram/career_cleo/posts/example.md",
        }

    monkeypatch.setattr(module, "stream_engine", fake_stream)
    monkeypatch.setattr(module, "engine_command", lambda *parts: list(parts))
    monkeypatch.setattr(module, "emit_cli_event", lambda **payload: None)

    args = argparse.Namespace(
        creator="career_cleo",
        mode="batch",
        batch_size=1,
        max_batches=None,
        max_runtime_minutes=None,
        max_failures=None,
        stop_on_failure=False,
        sleep_between_batches=0,
        retry_failed=False,
        since=None,
        until=None,
        rank_from=None,
        rank_to=None,
        order=None,
        output="human",
        non_interactive=True,
        force_full_sync=False,
        pause_seconds=0,
        batch_sizes_json=None,
        catalog_surface="posts",
        skip_sync=False,
    )

    assert module.run_creator(args) == 0
    output = capsys.readouterr().out
    assert "latest_markdown_path=/tmp/media2md/markdown/instagram/career_cleo/posts/example.md" in output
    assert "result_folder=/tmp/media2md/markdown/instagram/career_cleo/posts" in output
    assert 'open_in_finder_hint=open "/tmp/media2md/markdown/instagram/career_cleo/posts"' in output
