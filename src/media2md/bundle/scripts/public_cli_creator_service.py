from __future__ import annotations

import json
import sqlite3
import subprocess
import sys
from pathlib import Path
from typing import Any, Callable
from urllib.parse import urlsplit
try:
    from media2md.cli_output_service import make_event_payload, make_output_model, make_section
except ModuleNotFoundError:
    from media2md_contract_compat import make_event_payload, make_output_model, make_section


def creator_policy_payload(*, provider: str, creator: str, effective_policy: Callable[[str, str], dict[str, Any]]) -> dict[str, Any]:
    policy = effective_policy(provider, creator)
    return make_output_model(
        event="creator_policy",
        schema="media2md.cli.creator_policy/v1",
        summary="Creator policy projection",
        sections=(
            make_section(
                "policy",
                status="ok",
                message="Effective creator policy",
                data={"provider": provider, "creator": creator, "policy": policy},
            ),
        ),
        data={"provider": provider, "creator": creator, "policy": policy},
    ).as_dict()


def print_policy(payload: dict[str, Any]) -> None:
    print("CREATOR_POLICY")
    print(json.dumps(payload, ensure_ascii=False, indent=2))


def creator_sync_common(
    args,
    *,
    root: Path,
    provider: str,
    normalize_creator: Callable[[str, str], str],
    effective_policy: Callable[[str, str], dict[str, Any]],
    registry: Callable[[list[str]], int],
    run: Callable[[list[str], bool], int],
) -> int:
    if provider == "instagram":
        engine = root / "scripts" / "creator_bulk.py"
        cmd = [sys.executable, str(engine), "status", args.creator]
        if args.force_full:
            cmd.append("--force-full-sync")
        return run(cmd)
    mode = "full" if args.force_full else "quick"
    policy = effective_policy(provider, normalize_creator(provider, args.creator))
    return registry(["sync", provider, args.creator, "--mode", mode, "--quick-window", str(policy["sync"]["quick_window"])])


def resolve_existing_row(rows: list[dict[str, Any]], provider: str, creator: str) -> dict[str, Any] | None:
    return next((row for row in rows if row["provider"] == provider and row["handle"].lower() == creator.lower()), None)


def _youtube_surface_from_source_url(source_url: str | None) -> str:
    path = urlsplit(str(source_url or "")).path.rstrip("/").lower()
    for surface in ("videos", "shorts", "streams"):
        if path.endswith(f"/{surface}"):
            return surface
    return "videos"


def emit_creator_run_catalog_context(
    *,
    args,
    provider: str,
    creator: str,
    existing_row: dict[str, Any] | None,
    emit: Callable[[dict[str, Any], str], None],
    youtube_catalog_surfaces: Callable[[], tuple[str, ...]] | None = None,
) -> None:
    source_url = existing_row.get("source_url") if existing_row else None
    payload_data: dict[str, Any] = {
        "provider": provider,
        "creator": creator,
        "catalog_source_url": source_url,
        "tracked": int(existing_row.get("tracked") or 0) if existing_row else 0,
        "catalog_last_synced_at": existing_row.get("last_sync_at") if existing_row else None,
        "catalog_exact": bool(existing_row.get("current_total_exact")) if existing_row else False,
        "using_saved_catalog": existing_row is not None,
    }
    if provider == "youtube":
        surfaces = list(youtube_catalog_surfaces() if youtube_catalog_surfaces is not None else ("videos", "shorts"))
        payload_data["catalog_surface"] = _youtube_surface_from_source_url(source_url)
        payload_data["catalog_surfaces"] = surfaces
    payload = make_output_model(
        event="creator_run_catalog_context",
        schema="media2md.cli.creator_run_catalog_context/v1",
        summary="Catalog context for creator run",
        sections=(
            make_section(
                "catalog",
                status="ok" if payload_data["using_saved_catalog"] else "warn",
                message="Saved catalog context resolved before creator run",
                data=payload_data,
            ),
        ),
        data=payload_data,
    ).as_dict()
    if args.output == "human":
        print("CREATOR_RUN_CATALOG", flush=True)
        print(f"provider={provider}", flush=True)
        print(f"creator={creator}", flush=True)
        print(f"using_saved_catalog={str(payload['using_saved_catalog']).lower()}", flush=True)
        print(f"catalog_last_synced_at={payload['catalog_last_synced_at'] or '-'}", flush=True)
        print(f"catalog_exact={str(payload['catalog_exact']).lower()}", flush=True)
        print(f"tracked={payload['tracked']}", flush=True)
        if provider == "youtube":
            print(f"catalog_surface={payload['catalog_surface']}", flush=True)
            print(f"catalog_surfaces={','.join(payload['catalog_surfaces'])}", flush=True)
        print(f"catalog_source_url={source_url or '-'}", flush=True)
    else:
        emit(payload, args.output)


def emit_sync_warning_or_fail(
    *,
    args,
    provider: str,
    creator: str,
    sync_code: int,
    existing_row: dict[str, Any] | None,
    emit: Callable[[dict[str, Any], str], None],
) -> int | None:
    can_use_stale = bool(getattr(args, "allow_stale_catalog", False) and existing_row and int(existing_row.get("tracked") or 0) > 0)
    if not can_use_stale:
        if args.output == "human":
            print(f"SYNC_FAILED provider={provider} creator={creator}; batch_not_started=true", file=sys.stderr)
        else:
            emit(
                make_output_model(
                    event="sync_failed",
                    schema="media2md.cli.sync_failed/v1",
                    summary="Catalog refresh failed before batch start",
                    sections=(
                        make_section(
                            "catalog",
                            status="error",
                            message="Catalog refresh failed and no cached catalog could be used",
                            data={"provider": provider, "creator": creator, "batch_not_started": True},
                        ),
                    ),
                    data={"provider": provider, "creator": creator, "batch_not_started": True},
                ).as_dict(),
                args.output,
            )
        return sync_code
    warning = make_output_model(
        event="sync_warning",
        schema="media2md.cli.sync_warning/v1",
        summary="Cached catalog will be used for this creator run",
        sections=(
            make_section(
                "catalog",
                status="warn",
                message="Live refresh failed; continuing with an explicitly accepted cached catalog",
                data={
                    "provider": provider,
                    "creator": creator,
                    "using_cached_catalog": True,
                    "catalog_last_synced_at": existing_row.get("last_sync_at"),
                    "tracked": int(existing_row.get("tracked") or 0),
                    "confirmation_was_explicit": True,
                },
            ),
        ),
        data={
            "provider": provider,
            "creator": creator,
            "using_cached_catalog": True,
            "catalog_last_synced_at": existing_row.get("last_sync_at"),
            "tracked": int(existing_row.get("tracked") or 0),
            "confirmation_was_explicit": True,
        },
    ).as_dict()
    if args.output == "human":
        print("SYNC_WARNING", flush=True)
        print(f"provider={provider}", flush=True)
        print(f"creator={creator}", flush=True)
        print("using_cached_catalog=true", flush=True)
        print(f"catalog_last_synced_at={existing_row.get('last_sync_at') or '-'}", flush=True)
        print(f"tracked={int(existing_row.get('tracked') or 0)}", flush=True)
    else:
        emit(warning, args.output)
    return None


def creator_run_instagram(
    args,
    *,
    batch_size: int,
    mode: str,
    core: Callable[[list[str]], int],
    retry_failed_supported: bool,
    refresh_registry: Callable[[], None],
) -> int:
    cmd = ["creator", "run", args.creator, "--mode", mode, "--batch-size", str(batch_size), "--output", args.output]
    for name, flag in (
        ("since", "--since"),
        ("until", "--until"),
        ("rank_from", "--rank-from"),
        ("rank_to", "--rank-to"),
        ("order", "--order"),
        ("max_batches", "--max-batches"),
        ("max_runtime_minutes", "--max-runtime-minutes"),
        ("max_failures", "--max-failures"),
        ("sleep_between_batches", "--sleep-between-batches"),
    ):
        value = getattr(args, name, None)
        if value is not None:
            cmd += [flag, str(value)]
    if args.stop_on_failure:
        cmd.append("--stop-on-failure")
    if retry_failed_supported and getattr(args, "retry_failed", False):
        cmd.append("--retry-failed")
    code = core(cmd)
    refresh_registry()
    return code


def creator_run_context(
    args,
    *,
    provider: str,
    creator: str,
    policy: dict[str, Any],
    parse_batch_size_assignments: Callable[[Any], dict[str, int]] | None,
    normalize_batch_sizes: Callable[[Any], dict[str, int]] | None,
    typed_batch_sizes_supported: bool,
) -> dict[str, Any]:
    mode = args.mode or policy["processing"]["mode"]
    batch_size, batch_sizes = merge_batch_sizes(
        args=args,
        processing=policy["processing"],
        parse_batch_size_assignments=parse_batch_size_assignments,
        normalize_batch_sizes=normalize_batch_sizes,
        typed_batch_sizes_supported=typed_batch_sizes_supported,
    )
    return {
        "provider": provider,
        "creator": creator,
        "policy": policy,
        "mode": mode,
        "batch_size": batch_size,
        "batch_sizes": batch_sizes,
    }


def merge_batch_sizes(
    *,
    args,
    processing: dict[str, Any],
    parse_batch_size_assignments: Callable[[Any], dict[str, int]] | None,
    normalize_batch_sizes: Callable[[Any], dict[str, int]] | None,
    typed_batch_sizes_supported: bool,
) -> tuple[int, dict[str, int]]:
    mode = processing["mode"]
    _ = mode
    batch_size = args.batch_size or processing["batch_size"]
    if not typed_batch_sizes_supported or parse_batch_size_assignments is None or normalize_batch_sizes is None:
        return batch_size, {}
    typed_assignments = parse_batch_size_assignments(getattr(args, "batch_size_type", None))
    batch_sizes = normalize_batch_sizes(processing.get("batch_sizes"))
    if args.batch_size is not None and not typed_assignments:
        batch_sizes = {}
    else:
        batch_sizes.update(typed_assignments)
    return batch_size, batch_sizes


def creator_run_catalog_preflight(
    *,
    args,
    provider: str,
    creator: str,
    policy: dict[str, Any],
    registry_rows: list[dict[str, Any]],
    prepare_catalog_for_creator_run: Callable[..., int],
    registry_call: Callable[[list[str]], int],
    emit_call: Callable[[dict[str, Any], str], None],
    youtube_catalog_surfaces: Callable[[], tuple[str, ...]] | None = None,
) -> tuple[dict[str, Any] | None, int | None]:
    existing_row = resolve_existing_row(registry_rows, provider, creator)
    emit_creator_run_catalog_context(
        args=args,
        provider=provider,
        creator=creator,
        existing_row=existing_row,
        emit=emit_call,
        youtube_catalog_surfaces=youtube_catalog_surfaces,
    )
    sync_code = prepare_catalog_for_creator_run(
        provider=provider,
        creator_arg=args.creator,
        normalized_creator=creator,
        existing_row=existing_row,
        quick_window=int(policy["sync"]["quick_window"]),
        output=args.output,
        registry_call=registry_call,
        emit_call=emit_call,
    )
    if sync_code == 0:
        return existing_row, None
    outcome = emit_sync_warning_or_fail(
        args=args,
        provider=provider,
        creator=creator,
        sync_code=sync_code,
        existing_row=existing_row,
        emit=emit_call,
    )
    return existing_row, outcome


def creator_run_registry_command(
    args,
    *,
    provider: str,
    policy: dict[str, Any],
    batch_size: int,
    batch_sizes: dict[str, int],
    include_typed_batch_sizes: bool,
) -> list[str]:
    cmd = [
        "run",
        provider,
        args.creator,
        "--mode",
        args.mode or policy["processing"]["mode"],
        "--batch-size",
        str(batch_size),
    ]
    if include_typed_batch_sizes:
        cmd += ["--batch-sizes-json", json.dumps(batch_sizes, sort_keys=True)]
    cmd += [
        "--max-batches",
        str(args.max_batches if args.max_batches is not None else policy["processing"]["max_batches"]),
        "--max-runtime-minutes",
        str(args.max_runtime_minutes if args.max_runtime_minutes is not None else policy["processing"]["max_runtime_minutes"]),
        "--max-failures",
        str(args.max_failures if args.max_failures is not None else policy["processing"]["max_failures"]),
        "--sleep-between-batches",
        str(args.sleep_between_batches if args.sleep_between_batches is not None else policy["processing"]["sleep_between_batches"]),
        "--order",
        args.order or policy["filters"]["order"],
        "--output",
        args.output,
    ]
    if args.stop_on_failure or policy["processing"].get("stop_on_failure"):
        cmd.append("--stop-on-failure")
    for value, flag in (
        (args.since or policy["filters"].get("since"), "--since"),
        (args.until or policy["filters"].get("until"), "--until"),
        (args.rank_from or policy["filters"].get("rank_from"), "--rank-from"),
        (args.rank_to or policy["filters"].get("rank_to"), "--rank-to"),
    ):
        if value is not None:
            cmd += [flag, str(value)]
    return cmd


def add_creator_instagram(
    *,
    root: Path,
    creator_input: str,
    normalized_creator: str,
) -> int:
    try:
        import yaml  # type: ignore  # noqa: F401
    except ImportError as exc:
        raise RuntimeError('Instagram support is not installed. Run: python -m pip install "media2md[instagram]"') from exc
    manager = root / "scripts" / "manage_creators.py"
    result = subprocess.run([sys.executable, str(manager), "add", creator_input], cwd=root)
    if result.returncode not in (0,):
        conn = sqlite3.connect(root / "data" / "state.db") if (root / "data" / "state.db").is_file() else None
        exists = False
        if conn:
            try:
                exists = conn.execute(
                    "SELECT 1 FROM creators WHERE username=? COLLATE NOCASE",
                    (normalized_creator,),
                ).fetchone() is not None
            finally:
                conn.close()
        if not exists:
            return result.returncode
    return 0
