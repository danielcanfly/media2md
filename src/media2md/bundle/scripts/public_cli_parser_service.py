from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Callable

from media2md.provider_catalog import provider_names


PROVIDER_CHOICES = provider_names()


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
    ver = subparsers.add_parser("version", help="Show the installed Media2MD version.")
    ver.set_defaults(func=lambda a: (print(f"media2md {version}") or 0))

    status = subparsers.add_parser("status", help="Show project, provider, and output-location status.")
    status.add_argument("--output", choices=("human", "ndjson"), default="human")
    status.set_defaults(func=system_status)

    settingsp = subparsers.add_parser("settings", help="Inspect or update CLI settings.")
    setsub = settingsp.add_subparsers(dest="settings_command", required=True)
    show = setsub.add_parser("show", help="Show the current settings projection.")
    show.add_argument("--output", choices=("human", "ndjson"), default="human")
    show.set_defaults(func=settings_show)

    setcmd = setsub.add_parser("set", help="Update one or more saved settings.")
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

    agentp = subparsers.add_parser("agent", help="Show agent-facing command and confirmation policy.")
    agentsub = agentp.add_subparsers(dest="agent_command", required=True)
    ast = agentsub.add_parser("status", help="Show agent permissions and guarded commands.")
    ast.add_argument("--output", choices=("human", "ndjson"), default="human")
    ast.set_defaults(func=agent_status)

    init = subparsers.add_parser("init", help="Initialize locale, timezone, and first-run defaults.")
    init.add_argument("--language", "--ui-locale", dest="language", choices=locales)
    init.add_argument("--markdown-language", "--markdown-locale", dest="markdown_language", choices=locales)
    init.add_argument("--timezone")
    init.add_argument("--non-interactive", action="store_true")
    init.set_defaults(func=init_command)

    providers = subparsers.add_parser("providers", help="Pass through to the provider capability listing.")
    providers.add_argument("args", nargs=argparse.REMAINDER)
    providers.set_defaults(func=lambda a: core(["providers", *a.args]))

    authp = subparsers.add_parser("auth", help="Pass through to authentication setup, verify, and status commands.")
    authp.add_argument("args", nargs=argparse.REMAINDER)
    authp.set_defaults(func=lambda a: auth(a.args))

    media = subparsers.add_parser("media", help="Pass through to one-shot media inspection and processing commands.")
    media.add_argument("args", nargs=argparse.REMAINDER)
    media.set_defaults(func=lambda a: generic(a.args))


def add_common_update_commands(update_parser, *, update_tool) -> None:
    us = update_parser.add_subparsers(dest="update_command", required=True)
    for name in ("status", "check", "download", "install", "rollback"):
        help_text = {
            "status": "Show update settings and local update state.",
            "check": "Check whether a newer published version is available.",
            "download": "Download the latest update package without installing it.",
            "install": "Install the downloaded update package.",
            "rollback": "Roll back to the previous installed version.",
        }[name]
        commandp = us.add_parser(name, help=help_text)
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
    active = rs.add_parser("active-states", help="Repair stuck in-progress media rows after an interrupted run.")
    active.add_argument("--yes", action="store_true")
    active.set_defaults(func=repair_active_states)

    identity = rs.add_parser("identities", help="Repair creator identity metadata and cached registry references.")
    identity.add_argument("--offline", action="store_true")
    identity.set_defaults(func=lambda a: registry(["repair-identities"] + (["--offline"] if a.offline else [])))

    workspace = rs.add_parser("workspace", help="Remove stale intermediate workspace files after confirming no run is active.")
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
    backup = ds.add_parser("backup", help="Create a backup snapshot of config, data, markdown, and logs.")
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

    verify = ds.add_parser("verify-backup", help="Verify a previously created backup artifact.")
    verify.add_argument("path")
    verify.add_argument("--output", choices=("human", "ndjson"), default="human")
    verify.set_defaults(func=lambda a: run([sys.executable, str(backup_script), "verify-backup", a.path, "--output", a.output]))

    deleteall = ds.add_parser("delete-all", help="Permanently remove local Media2MD data after confirmation.")
    deleteall.add_argument("--yes", action="store_true")
    deleteall.add_argument("--confirm")
    deleteall.set_defaults(func=data_delete_all)


def add_common_uninstall_command(subparsers, *, uninstall) -> None:
    uninstallp = subparsers.add_parser("uninstall", help="Uninstall Media2MD and optionally purge local project data.")
    uninstallp.add_argument("--purge-data", action="store_true")
    uninstallp.add_argument("--yes", action="store_true")
    uninstallp.add_argument("--confirm")
    uninstallp.add_argument("--dry-run", action="store_true")
    uninstallp.set_defaults(func=uninstall)


def _add_creator_policy_arguments(parser, *, parse_duration, include_typed_batch_sizes: bool, default_provider: str | None) -> None:
    parser.add_argument("creator")
    if default_provider is None:
        parser.add_argument("--provider", choices=PROVIDER_CHOICES, help="Provider for bare handles such as @creator-name.")
    else:
        parser.add_argument("--provider", choices=PROVIDER_CHOICES, default=default_provider, help="Provider for bare handles such as @creator-name.")
    parser.add_argument("--every", type=parse_duration)
    parser.add_argument("--full-every", type=parse_duration)
    parser.add_argument("--quick-window", type=int)
    parser.add_argument("--mode", choices=("batch", "drain"))
    parser.add_argument("--batch-size", type=int)
    if include_typed_batch_sizes:
        parser.add_argument("--batch-size-type", action="append", default=[])
    parser.add_argument("--max-batches", type=int)
    parser.add_argument("--max-runtime-minutes", type=int)
    parser.add_argument("--max-failures", type=int)
    parser.add_argument("--stop-on-failure", action=argparse.BooleanOptionalAction)
    parser.add_argument("--sleep-between-batches", type=int)
    parser.add_argument("--scheduled-processing", action=argparse.BooleanOptionalAction)
    parser.add_argument("--processing-every", type=parse_duration)
    parser.add_argument("--since")
    parser.add_argument("--until")
    parser.add_argument("--rank-from", type=int)
    parser.add_argument("--rank-to", type=int)
    parser.add_argument("--order", choices=("newest_first", "oldest_first"))


def _add_creator_run_arguments(parser, *, include_typed_batch_sizes: bool, include_retry_failed: bool) -> None:
    parser.add_argument("creator")
    parser.add_argument("--provider", choices=PROVIDER_CHOICES, help="Provider for bare handles such as @creator-name.")
    parser.add_argument("--mode", choices=("batch", "drain"))
    parser.add_argument("--batch-size", type=int)
    if include_typed_batch_sizes:
        parser.add_argument("--batch-size-type", action="append", default=[])
    parser.add_argument("--max-batches", type=int)
    parser.add_argument("--max-runtime-minutes", type=int)
    parser.add_argument("--max-failures", type=int)
    parser.add_argument("--stop-on-failure", action="store_true")
    if include_retry_failed:
        parser.add_argument("--retry-failed", action="store_true", help="Requeue retry_wait/failed Instagram items for this run.")
    parser.add_argument("--sleep-between-batches", type=int)
    parser.add_argument("--since")
    parser.add_argument("--until")
    parser.add_argument("--rank-from", type=int)
    parser.add_argument("--rank-to", type=int)
    parser.add_argument("--order", choices=("newest_first", "oldest_first"))
    parser.add_argument("--allow-stale-catalog", action="store_true", help="Continue with the last saved catalog when refresh-catalog fails. Use this only when you explicitly want cached results.")
    parser.add_argument("--output", choices=("human", "ndjson"), default="human")


def add_common_creator_commands(
    creator_parser,
    *,
    providers: tuple[str, ...],
    parse_duration,
    creator_status,
    creator_sync,
    creator_run,
    policy_show,
    set_policy,
    add_creator,
    registry,
    resolve_creator_provider=None,
    strict_provider_resolution: bool,
    include_refresh_catalog: bool,
    include_typed_batch_sizes: bool,
    include_retry_failed: bool,
    default_provider_for_bare_handles: str | None,
) -> None:
    del providers
    cs = creator_parser.add_subparsers(dest="creator_command", required=True)

    add = cs.add_parser("add", help="Register a creator so it can be refreshed and processed later.")
    add.add_argument("creator")
    if default_provider_for_bare_handles is None:
        add.add_argument("--provider", choices=PROVIDER_CHOICES, help="Provider for bare handles such as @creator-name.")
    else:
        add.add_argument("--provider", choices=PROVIDER_CHOICES, default=default_provider_for_bare_handles, help="Provider for bare handles such as @creator-name.")
    if strict_provider_resolution and resolve_creator_provider is not None:
        add.set_defaults(func=lambda a: (setattr(a, "provider", resolve_creator_provider(a.creator, a.provider, command_name="creator add")) or add_creator(a)))
    else:
        add.set_defaults(func=add_creator)

    stat = cs.add_parser("status", help="Show tracked creator status, policy, and remaining work.")
    stat.add_argument("--provider", choices=PROVIDER_CHOICES)
    stat.add_argument("--creator")
    stat.add_argument("--output", choices=("human", "ndjson"), default="human")
    stat.set_defaults(func=creator_status)

    listing = cs.add_parser("list", help="Alias of `creator status`.")
    listing.add_argument("--provider", choices=PROVIDER_CHOICES)
    listing.add_argument("--creator")
    listing.add_argument("--output", choices=("human", "ndjson"), default="human")
    listing.set_defaults(func=creator_status)

    for name, enabled in (("sync-enable", True), ("sync-disable", False)):
        command = cs.add_parser(name, help=f"{'Enable' if enabled else 'Disable'} scheduled catalog refresh for one creator.")
        command.add_argument("creator")
        if default_provider_for_bare_handles is None:
            command.add_argument("--provider", choices=PROVIDER_CHOICES, help="Provider for bare handles such as @creator-name.")
        else:
            command.add_argument("--provider", choices=PROVIDER_CHOICES, default=default_provider_for_bare_handles, help="Provider for bare handles such as @creator-name.")
        command.add_argument("--every", type=parse_duration)
        command.add_argument("--full-every", type=parse_duration)
        command.add_argument("--quick-window", type=int)
        if strict_provider_resolution and resolve_creator_provider is not None:
            command.set_defaults(func=lambda a, e=enabled, n=name: (setattr(a, "provider", resolve_creator_provider(a.creator, a.provider, command_name=f"creator {n}")) or set_policy(a, e)))
        else:
            command.set_defaults(func=lambda a, e=enabled: set_policy(a, e))

    sync = cs.add_parser("sync", help="Refresh the saved creator catalog. Kept for compatibility; prefer `refresh-catalog`.")
    sync.add_argument("creator")
    sync.add_argument("--provider", choices=PROVIDER_CHOICES, help="Provider for bare handles such as @creator-name.")
    sync.add_argument("--force-full", action="store_true")
    sync.set_defaults(func=creator_sync)

    if include_refresh_catalog:
        refresh = cs.add_parser("refresh-catalog", help="Refresh the saved creator catalog before reviewing status or running items.")
        refresh.add_argument("creator")
        refresh.add_argument("--provider", choices=PROVIDER_CHOICES, help="Provider for bare handles such as @creator-name.")
        refresh.add_argument("--force-full", action="store_true")
        refresh.set_defaults(func=creator_sync)

    policy = cs.add_parser("policy-set", help="Update creator sync and processing policy in one command.")
    _add_creator_policy_arguments(
        policy,
        parse_duration=parse_duration,
        include_typed_batch_sizes=include_typed_batch_sizes,
        default_provider=default_provider_for_bare_handles,
    )
    if strict_provider_resolution and resolve_creator_provider is not None:
        policy.set_defaults(func=lambda a: (setattr(a, "provider", resolve_creator_provider(a.creator, a.provider, command_name="creator policy-set")) or set_policy(a)))
    else:
        policy.set_defaults(func=set_policy)

    pshow = cs.add_parser("policy-show", help="Show the effective policy for one creator.")
    pshow.add_argument("creator")
    pshow.add_argument("--provider", choices=PROVIDER_CHOICES)
    pshow.add_argument("--output", choices=("human", "ndjson"), default="human")
    pshow.set_defaults(func=policy_show)

    pgroup = cs.add_parser("policy", help="Grouped policy commands.")
    psub = pgroup.add_subparsers(dest="policy_command", required=True)

    pset = psub.add_parser("set", help="Update the saved policy for one creator.")
    _add_creator_policy_arguments(
        pset,
        parse_duration=parse_duration,
        include_typed_batch_sizes=include_typed_batch_sizes,
        default_provider=default_provider_for_bare_handles,
    )
    if strict_provider_resolution and resolve_creator_provider is not None:
        pset.set_defaults(func=lambda a: (setattr(a, "provider", resolve_creator_provider(a.creator, a.provider, command_name="creator policy set")) or set_policy(a)))
    else:
        pset.set_defaults(func=set_policy)

    pshow2 = psub.add_parser("show", help="Show the effective policy for one creator.")
    pshow2.add_argument("creator")
    pshow2.add_argument("--provider", choices=PROVIDER_CHOICES)
    pshow2.add_argument("--output", choices=("human", "ndjson"), default="human")
    pshow2.set_defaults(func=policy_show)

    runp = cs.add_parser("run", help="Process queued items for one creator using the saved catalog and current policy.")
    _add_creator_run_arguments(
        runp,
        include_typed_batch_sizes=include_typed_batch_sizes,
        include_retry_failed=include_retry_failed,
    )
    runp.set_defaults(func=creator_run)

    delete = cs.add_parser("delete", help="Delete one tracked creator after confirmation.")
    delete.add_argument("creator")
    delete.add_argument("--provider", choices=PROVIDER_CHOICES, required=True)
    delete.add_argument("--yes", action="store_true")
    delete.set_defaults(func=lambda a: registry(["delete-creator", a.provider, a.creator] + (["--yes"] if a.yes else [])))
