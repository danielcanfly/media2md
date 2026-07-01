from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest


def _load_cli():
    root = Path(__file__).resolve().parents[1]
    script_path = root / "src" / "media2md" / "bundle" / "scripts" / "media2md.py"
    spec = importlib.util.spec_from_file_location("media2md_cli_provider_resolution", script_path)
    assert spec and spec.loader
    cli = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(cli)
    return cli


def test_resolve_creator_provider_accepts_full_creator_urls():
    cli = _load_cli()
    assert cli.resolve_creator_provider("https://www.youtube.com/@creator-name", None, command_name="creator add") == "youtube"
    assert cli.resolve_creator_provider("https://www.tiktok.com/@creator-name", None, command_name="creator sync") == "tiktok"
    assert cli.resolve_creator_provider("https://www.instagram.com/creator.name/", None, command_name="creator run") == "instagram"
    assert cli.resolve_creator_provider("https://www.bilibili.com/video/BV1ah4y1M7aQ", None, command_name="creator add") == "bilibili"


@pytest.mark.parametrize(
    ("command_name", "value"),
    [
        ("creator add", "@creator-name"),
        ("creator sync", "creator-name"),
        ("creator run", "@creator-name"),
        ("creator status", "creator-name"),
        ("creator policy show", "@creator-name"),
    ],
)
def test_resolve_creator_provider_requires_provider_for_bare_handles(command_name: str, value: str):
    cli = _load_cli()
    with pytest.raises(RuntimeError) as excinfo:
        cli.resolve_creator_provider(value, None, command_name=command_name)
    message = str(excinfo.value)
    assert command_name in message
    assert "--provider" in message
    assert "bare handle" in message


def test_resolve_creator_provider_accepts_explicit_provider_for_bare_handles():
    cli = _load_cli()
    assert cli.resolve_creator_provider("@creator-name", "youtube", command_name="creator sync") == "youtube"
    assert cli.resolve_creator_provider("creator-name", "tiktok", command_name="creator run") == "tiktok"
