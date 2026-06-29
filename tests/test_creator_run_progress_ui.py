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
