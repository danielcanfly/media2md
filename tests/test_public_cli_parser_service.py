from __future__ import annotations

import argparse
from pathlib import Path

from media2md.bundle.scripts.public_cli_parser_service import (
    add_common_data_commands,
    add_common_repair_commands,
    add_common_top_level_commands,
    add_common_uninstall_command,
    add_common_update_commands,
)


def _parser():
    parser = argparse.ArgumentParser(prog="media2md")
    return parser, parser.add_subparsers(dest="command", required=True)


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
