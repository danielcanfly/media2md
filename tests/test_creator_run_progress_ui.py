from __future__ import annotations

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
