from __future__ import annotations

import importlib.util
from pathlib import Path


def _load_cli():
    root = Path(__file__).resolve().parents[1]
    script_path = root / "src" / "media2md" / "bundle" / "scripts" / "media2md.py"
    spec = importlib.util.spec_from_file_location("media2md_cli_refresh_catalog_alias", script_path)
    assert spec and spec.loader
    cli = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(cli)
    return cli


def test_refresh_catalog_alias_is_present():
    cli = _load_cli()
    parser = cli.parser()
    args = parser.parse_args(["creator", "refresh-catalog", "@creator-name", "--provider", "youtube"])
    assert args.creator_command == "refresh-catalog"
    assert args.provider == "youtube"
    assert args.creator == "@creator-name"


def test_sync_command_still_exists_for_full_command_surface():
    cli = _load_cli()
    parser = cli.parser()
    args = parser.parse_args(["creator", "sync", "@creator-name", "--provider", "youtube"])
    assert args.creator_command == "sync"
