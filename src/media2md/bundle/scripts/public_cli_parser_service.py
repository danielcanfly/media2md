from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Callable


def add_common_top_level_commands(
    subparsers,
    *,
    version: str,
    system_status,
    settings_show,
    settings_set,
    agent_status,
    init_command,
    locales: tuple[str, ...],
    core,
    auth,
    generic,
) -> None:
    ver = subparsers.add_parser("version")
    ver.set_defaults(func=lambda a: (print(f"media2md {version}") or 0))

    status = subparsers.add_parser("status")
    status.add_argument("--output", choices=("human", "ndjson"), default="human")
    status.set_defaults(func=system_status)

    settingsp = subparsers.add_parser("settings")
    setsub = settingsp.add_subparsers(dest="settings_command", required=True)
    show = setsub.add_parser("show")
    show.add_argument("--output", choices=("human", "ndjson"), default="human")
    show.set_defaults(func=settings_show)

    setcmd = setsub.add_parser("set")
    setcmd.add_argument("--instagram-backend", choices=("auto", "gallery-dl", "instaloader"))
    setcmd.add_argument("--youtube-js-runtime", choices=("auto", "deno", "node", "quickjs"))
    setcmd.add_argument("--youtube-allow-remote-ejs", action=argparse.BooleanOptionalAction)
    setcmd.add_argument("--youtube-po-token-provider", choices=("disabled", "none", "bgutil", "wpc-experimental"))
    setcmd.add_argument("--youtube-pot-browser-path")
    setcmd.add_argument("--youtube-caption-first", action=argparse.BooleanOptionalAction)
    setcmd.add_argument("--youtube-caption-languages")
    setcmd.add_argument("--youtube-audio-strategies")
    setcmd.add_argument("--youtube-long-video-threshold-minutes", type=float)
    setcmd.add_argument("--youtube-chunk-minutes", type=float)
    setcmd.add_argument("--youtube-chunk-model")
    setcmd.add_argument("--tiktok-impersonate")
    setcmd.add_argument("--update-check-every-days", type=float)
    setcmd.add_argument("--update-check-on-use", action=argparse.BooleanOptionalAction)
    setcmd.add_argument("--output", choices=("human", "ndjson"), default="human")
    setcmd.set_defaults(func=settings_set)

    agentp = subparsers.add_parser("agent")
    agentsub = agentp.add_subparsers(dest="agent_command", required=True)
    ast = agentsub.add_parser("status")
    ast.add_argument("--output", choices=("human", "ndjson"), default="human")
    ast.set_defaults(func=agent_status)

    init = subparsers.add_parser("init")
    init.add_argument("--language", "--ui-locale", dest="language", choices=locales)
    init.add_argument("--markdown-language", "--markdown-locale", dest="markdown_language", choices=locales)
    init.add_argument("--timezone")
    init.add_argument("--non-interactive", action="store_true")
    init.set_defaults(func=init_command)

    providers = subparsers.add_parser("providers")
    providers.add_argument("args", nargs=argparse.REMAINDER)
    providers.set_defaults(func=lambda a: core(["providers", *a.args]))

    authp = subparsers.add_parser("auth")
    authp.add_argument("args", nargs=argparse.REMAINDER)
    authp.set_defaults(func=lambda a: auth(a.args))

    media = subparsers.add_parser("media")
    media.add_argument("args", nargs=argparse.REMAINDER)
    media.set_defaults(func=lambda a: generic(a.args))


def add_common_update_commands(update_parser, *, update_tool) -> None:
    us = update_parser.add_subparsers(dest="update_command", required=True)
    for name in ("status", "check", "download", "install", "rollback"):
        commandp = us.add_parser(name)
        commandp.add_argument("--output", choices=("human", "ndjson"), default="human")
        if name == "check":
            commandp.add_argument("--repository")
        if name in {"install", "rollback"}:
            commandp.add_argument("--yes", action="store_true")
        if name == "install":
            commandp.add_argument("--non-interactive", action="store_true")
        commandp.set_defaults(
            func=lambda a, n=name: update_tool(
                [n]
                + ((["--repository", a.repository] if n == "check" and a.repository else []))
                + ((["--yes"] if n in {"install", "rollback"} and a.yes else []))
                + ((["--non-interactive"] if n == "install" and a.non_interactive else []))
                + ["--output", a.output]
            )
        )


def add_common_repair_commands(repair_parser, *, registry, repair_active_states, repair_workspace) -> None:
    rs = repair_parser.add_subparsers(dest="repair_command", required=True)
    active = rs.add_parser("active-states")
    active.add_argument("--yes", action="store_true")
    active.set_defaults(func=repair_active_states)

    identity = rs.add_parser("identities")
    identity.add_argument("--offline", action="store_true")
    identity.set_defaults(func=lambda a: registry(["repair-identities"] + (["--offline"] if a.offline else [])))

    workspace = rs.add_parser("workspace")
    workspace.add_argument("--yes", action="store_true")
    workspace.set_defaults(func=repair_workspace)


def add_common_data_commands(
    data_parser,
    *,
    backup_script: Path,
    run: Callable[[list[str]], int],
    data_delete_all,
) -> None:
    ds = data_parser.add_subparsers(dest="data_command", required=True)
    backup = ds.add_parser("backup")
    backup.add_argument("--destination")
    backup.add_argument("--force", action="store_true")
    backup.add_argument("--wait-seconds", type=float, default=0)
    backup.add_argument("--output", choices=("human", "ndjson"), default="human")
    backup.set_defaults(
        func=lambda a: run(
            [sys.executable, str(backup_script), "backup"]
            + (["--destination", a.destination] if a.destination else [])
            + (["--force"] if a.force else [])
            + ["--wait-seconds", str(a.wait_seconds), "--output", a.output]
        )
    )

    verify = ds.add_parser("verify-backup")
    verify.add_argument("path")
    verify.add_argument("--output", choices=("human", "ndjson"), default="human")
    verify.set_defaults(func=lambda a: run([sys.executable, str(backup_script), "verify-backup", a.path, "--output", a.output]))

    deleteall = ds.add_parser("delete-all")
    deleteall.add_argument("--yes", action="store_true")
    deleteall.add_argument("--confirm")
    deleteall.set_defaults(func=data_delete_all)


def add_common_uninstall_command(subparsers, *, uninstall) -> None:
    uninstallp = subparsers.add_parser("uninstall")
    uninstallp.add_argument("--purge-data", action="store_true")
    uninstallp.add_argument("--yes", action="store_true")
    uninstallp.add_argument("--confirm")
    uninstallp.add_argument("--dry-run", action="store_true")
    uninstallp.set_defaults(func=uninstall)
