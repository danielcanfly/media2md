from __future__ import annotations

import argparse
from pathlib import Path

from media2md.bundle.scripts.public_cli_parser_service import (
    add_common_creator_commands,
    add_common_data_commands,
    add_common_repair_commands,
    add_common_top_level_commands,
    add_common_uninstall_command,
    add_common_update_commands,
)


def _parser():
    parser = argparse.ArgumentParser(prog="media2md")
    return parser, parser.add_subparsers(dest="command", required=True)


def _find_subparser(parser: argparse.ArgumentParser, name: str) -> argparse.ArgumentParser:
    for action in parser._actions:
        if isinstance(action, argparse._SubParsersAction):
            if name in action.choices:
                return action.choices[name]
    raise KeyError(name)


def test_add_common_top_level_commands_registers_expected_commands():
    parser, sub = _parser()
    add_common_top_level_commands(
        sub,
        version="0.9.4",
        system_status=lambda args: 0,
        settings_show=lambda args: 0,
        settings_set=lambda args: 0,
        agent_status=lambda args: 0,
        init_command=lambda args: 0,
        locales=("en", "ja"),
        core=lambda args: 0,
        auth=lambda args: 0,
        generic=lambda args: 0,
    )
    args = parser.parse_args(["init", "--language", "en", "--non-interactive"])
    assert args.command == "init"
    assert args.language == "en"
    root_help = parser.format_help().lower()
    assert "show project, provider, and output-location status" in root_help
    assert "one-shot media" in root_help
    assert "processing commands" in root_help


def test_settings_set_registers_instagram_catalog_surface():
    parser, sub = _parser()
    add_common_top_level_commands(
        sub,
        version="0.9.4",
        system_status=lambda args: 0,
        settings_show=lambda args: 0,
        settings_set=lambda args: 0,
        agent_status=lambda args: 0,
        init_command=lambda args: 0,
        locales=("en", "ja"),
        core=lambda args: 0,
        auth=lambda args: 0,
        generic=lambda args: 0,
    )
    args = parser.parse_args(["settings", "set", "--instagram-catalog-surface", "mixed"])
    assert args.command == "settings"
    assert args.settings_command == "set"
    assert args.instagram_catalog_surface == "mixed"


def test_add_common_update_commands_registers_check_repository():
    parser, sub = _parser()
    recorded = []
    update = sub.add_parser("update")
    add_common_update_commands(update, update_tool=lambda args: recorded.append(args) or 0)
    args = parser.parse_args(["update", "check", "--repository", "danielcanfly/media2md"])
    assert args.command == "update"
    assert args.update_command == "check"
    assert args.repository == "danielcanfly/media2md"


def test_add_common_repair_commands_registers_workspace():
    parser, sub = _parser()
    repair = sub.add_parser("repair")
    add_common_repair_commands(
        repair,
        registry=lambda args: 0,
        repair_active_states=lambda args: 0,
        repair_workspace=lambda args: 0,
    )
    args = parser.parse_args(["repair", "workspace", "--yes"])
    assert args.command == "repair"
    assert args.repair_command == "workspace"
    assert args.yes is True


def test_add_common_data_commands_registers_delete_all():
    parser, sub = _parser()
    data = sub.add_parser("data")
    add_common_data_commands(
        data,
        backup_script=Path("/tmp/backup.py"),
        run=lambda args: 0,
        data_delete_all=lambda args: 0,
    )
    args = parser.parse_args(["data", "delete-all", "--yes", "--confirm", "DELETE-ALL-DATA"])
    assert args.command == "data"
    assert args.data_command == "delete-all"
    assert args.confirm == "DELETE-ALL-DATA"


def test_add_common_uninstall_command_registers_dry_run():
    parser, sub = _parser()
    add_common_uninstall_command(sub, uninstall=lambda args: 0)
    args = parser.parse_args(["uninstall", "--dry-run"])
    assert args.command == "uninstall"
    assert args.dry_run is True


def test_add_common_creator_commands_media2md_shape():
    parser, sub = _parser()
    creator = sub.add_parser("creator")
    add_common_creator_commands(
        creator,
        providers=("instagram", "youtube", "tiktok"),
        parse_duration=lambda text: 1,
        creator_status=lambda args: 0,
        creator_sync=lambda args: 0,
        creator_run=lambda args: 0,
        policy_show=lambda args: 0,
        set_policy=lambda args, enabled=None: 0,
        add_creator=lambda args: 0,
        registry=lambda args: 0,
        resolve_creator_provider=lambda creator, provider, command_name: provider or "youtube",
        strict_provider_resolution=True,
        include_refresh_catalog=True,
        include_typed_batch_sizes=True,
        include_retry_failed=True,
        default_provider_for_bare_handles=None,
    )
    args = parser.parse_args(["creator", "refresh-catalog", "@creator-name", "--provider", "youtube"])
    assert args.command == "creator"
    assert args.creator_command == "refresh-catalog"
    help_text = creator.format_help().lower()
    assert "refresh the saved creator catalog" in help_text
    assert "prefer `refresh-catalog`" in help_text
    status_help = _find_subparser(creator, "status").format_help().lower()
    assert "source, policy, and remaining work" in status_help
    refresh_help = _find_subparser(creator, "refresh-catalog").format_help().lower()
    assert "provider for bare handles" in refresh_help
    assert "supported for `creator refresh-catalog`" in refresh_help
    assert "instagram," in refresh_help
    assert "tiktok, youtube" in refresh_help
    assert "every configured surface" in refresh_help
    assert "catalog-surface" in refresh_help


def test_add_common_creator_commands_social2md_shape():
    parser, sub = _parser()
    creator = sub.add_parser("creator")
    add_common_creator_commands(
        creator,
        providers=("instagram", "youtube", "tiktok"),
        parse_duration=lambda text: 1,
        creator_status=lambda args: 0,
        creator_sync=lambda args: 0,
        creator_run=lambda args: 0,
        policy_show=lambda args: 0,
        set_policy=lambda args, enabled=None: 0,
        add_creator=lambda args: 0,
        registry=lambda args: 0,
        resolve_creator_provider=None,
        strict_provider_resolution=False,
        include_refresh_catalog=False,
        include_typed_batch_sizes=False,
        include_retry_failed=False,
        default_provider_for_bare_handles="instagram",
    )
    args = parser.parse_args(["creator", "policy-set", "@creator-name"])
    assert args.provider == "instagram"


def test_creator_run_help_mentions_cached_catalog_wording():
    parser, sub = _parser()
    creator = sub.add_parser("creator")
    add_common_creator_commands(
        creator,
        providers=("instagram", "youtube", "tiktok"),
        parse_duration=lambda text: 1,
        creator_status=lambda args: 0,
        creator_sync=lambda args: 0,
        creator_run=lambda args: 0,
        policy_show=lambda args: 0,
        set_policy=lambda args, enabled=None: 0,
        add_creator=lambda args: 0,
        registry=lambda args: 0,
        resolve_creator_provider=lambda creator, provider, command_name: provider or "youtube",
        strict_provider_resolution=True,
        include_refresh_catalog=True,
        include_typed_batch_sizes=True,
        include_retry_failed=True,
        default_provider_for_bare_handles=None,
    )
    creator_help = creator.format_help().lower()
    run_help = _find_subparser(creator, "run").format_help().lower()
    assert "current policy" in creator_help
    assert "cached results" in run_help
    assert "supported for `creator run`" in run_help
    for provider in ("instagram", "tiktok", "youtube"):
        assert provider in run_help


def test_creator_run_help_mentions_instagram_catalog_surface():
    parser, sub = _parser()
    creator = sub.add_parser("creator")
    add_common_creator_commands(
        creator,
        providers=("instagram", "youtube", "tiktok"),
        parse_duration=lambda text: 1,
        creator_status=lambda args: 0,
        creator_sync=lambda args: 0,
        creator_run=lambda args: 0,
        policy_show=lambda args: 0,
        set_policy=lambda args, enabled=None: 0,
        add_creator=lambda args: 0,
        registry=lambda args: 0,
        resolve_creator_provider=lambda creator, provider, command_name: provider or "instagram",
        strict_provider_resolution=True,
        include_refresh_catalog=True,
        include_typed_batch_sizes=True,
        include_retry_failed=True,
        default_provider_for_bare_handles=None,
    )
    run_help = _find_subparser(creator, "run").format_help().lower()
    assert "catalog-surface" in run_help
    assert "reels, posts, or mixed" in run_help
