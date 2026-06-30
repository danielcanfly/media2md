from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any, Callable
from urllib.parse import urlsplit

from media2md.cli_output_service import make_output_model, make_section
from media2md.health_taxonomy import health_category, summarize_health
from media2md.provider_registry import provider_adapter
from media2md.remediation_service import auth_status_command


def registry_rows(registry_db: Path, *, include_youtube_totals: bool) -> list[dict[str, Any]]:
    try:
        from media2md_registry import refresh_legacy

        refresh_legacy()
    except Exception:
        pass
    if not registry_db.is_file():
        return []
    conn = sqlite3.connect(registry_db)
    conn.row_factory = sqlite3.Row
    if include_youtube_totals:
        query = """SELECT c.provider,c.handle,c.source_url,c.current_total,c.current_total_exact,
            c.youtube_video_total,c.youtube_video_total_exact,c.youtube_shorts_total,c.youtube_shorts_total_exact,
            c.youtube_streams_total,c.youtube_streams_total_exact,c.last_sync_mode,c.last_sync_at,c.last_full_sync_at,
            c.last_full_exact_total,c.last_full_exact_at,c.last_full_youtube_video_total,
            c.last_full_youtube_shorts_total,c.last_full_youtube_streams_total,
            COUNT(m.id) tracked, SUM(CASE WHEN m.status='completed' THEN 1 ELSE 0 END) completed,
            SUM(CASE WHEN m.is_current=1 AND m.status NOT IN ('completed','skipped') THEN 1 ELSE 0 END) remaining
            FROM creators c LEFT JOIN media m ON m.creator_id=c.id GROUP BY c.id ORDER BY c.provider,lower(c.handle)"""
    else:
        query = """SELECT c.provider,c.handle,c.source_url,c.current_total,c.current_total_exact,c.last_sync_mode,c.last_sync_at,c.last_full_sync_at,
            COUNT(m.id) tracked, SUM(CASE WHEN m.status='completed' THEN 1 ELSE 0 END) completed,
            SUM(CASE WHEN m.is_current=1 AND m.status NOT IN ('completed','skipped') THEN 1 ELSE 0 END) remaining
            FROM creators c LEFT JOIN media m ON m.creator_id=c.id GROUP BY c.id ORDER BY c.provider,lower(c.handle)"""
    rows = conn.execute(query).fetchall()
    conn.close()
    return [dict(row) for row in rows]


def _youtube_surface_from_source_url(source_url: str | None) -> str:
    path = urlsplit(str(source_url or "")).path.rstrip("/").lower()
    for surface in ("videos", "shorts", "streams"):
        if path.endswith(f"/{surface}"):
            return surface
    return "videos"


def creator_catalog_metadata(
    row: dict[str, Any],
    *,
    youtube_catalog_surfaces: Callable[[], tuple[str, ...]] | None = None,
) -> dict[str, Any]:
    metadata: dict[str, Any] = {"source_url": row.get("source_url")}
    if row.get("provider") != "youtube":
        return metadata
    surfaces = tuple(youtube_catalog_surfaces() if youtube_catalog_surfaces is not None else ("videos", "shorts"))
    metadata["catalog_surface"] = _youtube_surface_from_source_url(str(row.get("source_url") or ""))
    metadata["catalog_surfaces"] = list(surfaces)
    return metadata


def render_creator_status(
    args,
    *,
    rows: list[dict[str, Any]],
    effective_policy: Callable[[str, str], dict[str, Any]],
    emit: Callable[[dict[str, Any], str], None],
    duration: Callable[[int], str],
    normalize_batch_sizes: Callable[[Any], dict[str, int]] | None = None,
    include_youtube_breakdown: bool,
    include_batch_limits: bool,
    youtube_catalog_surfaces: Callable[[], tuple[str, ...]] | None = None,
) -> int:
    if args.output == "ndjson":
        for row in rows:
            policy = effective_policy(row["provider"], row["handle"])
            emit(
                {
                    "event": "creator_status",
                    **row,
                    **creator_catalog_metadata(row, youtube_catalog_surfaces=youtube_catalog_surfaces),
                    "policy": policy,
                },
                args.output,
            )
        emit({"event": "creator_status_completed", "count": len(rows)}, args.output)
        return 0
    if include_youtube_breakdown:
        print("PLATFORM   CREATOR                    SYNC  EVERY  FULL  MODE   TRACKED  DONE  LEFT  TOTALS")
    else:
        print("PLATFORM   CREATOR                    SYNC  EVERY  FULL  MODE   BATCH  TRACKED  DONE  LEFT  LAST SYNC")
    for row in rows:
        policy = effective_policy(row["provider"], row["handle"])
        metadata = creator_catalog_metadata(row, youtube_catalog_surfaces=youtube_catalog_surfaces)
        if include_youtube_breakdown:
            totals = f"all:{row['current_total'] or 0}"
            if row["provider"] == "youtube":
                totals += f",videos:{row['youtube_video_total'] or 0},shorts:{row['youtube_shorts_total'] or 0}"
                if (row.get("youtube_streams_total") or 0) or "streams" in metadata.get("catalog_surfaces", []):
                    totals += f",streams:{row['youtube_streams_total'] or 0}"
            print(
                f"{row['provider']:<10} {row['handle'][:26]:<26} {str(policy['sync']['enabled']).lower():<5} "
                f"{duration(policy['sync']['every_minutes']):<6} {duration(policy['sync']['full_every_minutes']):<5} "
                f"{policy['processing']['mode']:<6} {row['tracked'] or 0:<8} {row['completed'] or 0:<5} "
                f"{row['remaining'] or 0:<5} {totals}"
            )
            if row["provider"] == "youtube":
                print(
                    f"  SOURCE surface={metadata['catalog_surface']} "
                    f"catalog_surfaces={','.join(metadata['catalog_surfaces'])} "
                    f"url={metadata.get('source_url') or '-'}"
                )
            else:
                print(f"  SOURCE url={metadata.get('source_url') or '-'}")
            if include_batch_limits and normalize_batch_sizes is not None:
                sizes = normalize_batch_sizes(policy["processing"].get("batch_sizes"))
                batch_text = ",".join(f"{key}={value}" for key, value in sizes.items() if value)
                print(f"  BATCH_LIMITS {batch_text}")
            print(
                f"  EXACT current={str(bool(row['current_total_exact'])).lower()} "
                f"last_full_total={row['last_full_exact_total'] if row.get('last_full_exact_total') is not None else '-'} "
                f"last_full_at={row.get('last_full_exact_at') or '-'}"
            )
        else:
            print(
                f"{row['provider']:<10} {row['handle'][:26]:<26} {str(policy['sync']['enabled']).lower():<5} "
                f"{duration(policy['sync']['every_minutes']):<6} {duration(policy['sync']['full_every_minutes']):<5} "
                f"{policy['processing']['mode']:<6} {policy['processing']['batch_size']:<6} {row['tracked'] or 0:<8} "
                f"{row['completed'] or 0:<5} {row['remaining'] or 0:<5} {row['last_sync_at'] or '-'}"
            )
    print(f"TOTAL={len(rows)}")
    return 0


def provider_auth_rows(auth_data: dict[str, Any], providers: tuple[str, ...]) -> list[dict[str, Any]]:
    items = []
    health_results = []
    for name in providers:
        profile = auth_data.get(name, {})
        cookie = profile.get("cookie_file")
        configured = bool(cookie and Path(cookie).is_file()) or bool(
            name == "youtube"
            and profile.get("mode") == "browser_profile"
            and profile.get("browser")
            and profile.get("profile")
        )
        adapter = provider_adapter(name)
        health = adapter.health_check() if adapter is not None else None
        if health is not None:
            health_results.append(health)
        items.append(
            {
                "provider": name,
                "configured": configured,
                "auth_mode": profile.get("mode"),
                "browser": profile.get("browser"),
                "profile": profile.get("profile"),
                "health_status": health.status if health is not None else "error",
                "health_category": health_category(health.status if health is not None else "error"),
                "health_message": health.message if health is not None else "Provider adapter is unavailable",
                "active_backend": health.active_backend if health is not None else None,
                "backends": list(health.backends) if health is not None else [],
                "hints": list(health.hints) if health is not None else [],
            }
        )
    return items


def system_status_payload(
    *,
    config: dict[str, Any],
    auth_data: dict[str, Any],
    providers: tuple[str, ...],
    version: str,
    root: Path,
    repository: str,
    creator_count: int,
    registry_db: Path,
) -> dict[str, Any]:
    provider_rows = provider_auth_rows(auth_data, providers)
    health_summary = summarize_health([
        provider_adapter(item["provider"]).health_check()
        for item in provider_rows
        if provider_adapter(item["provider"]) is not None
    ])
    payload = make_output_model(
        event="system_status",
        schema="media2md.cli.system_status/v1",
        summary="System status summary",
        sections=(
            make_section(
                "providers",
                status=str(health_summary["status"]),
                message="Provider health summary",
                data={"providers": provider_rows, "provider_health": health_summary},
            ),
            make_section(
                "workspace",
                status="ok",
                message="Workspace metadata is available",
                data={"project_root": str(root), "registry_db": str(registry_db), "creator_count": creator_count},
            ),
        ),
        data={
            "version": version,
            "project_root": str(root),
            "timezone": config.get("timezone", "UTC"),
            "ui_locale": config.get("ui_locale", "en"),
            "markdown_locale": config.get("markdown_locale", "en"),
            "instagram_backend": config.get("providers", {}).get("instagram", {}).get("backend", "auto"),
            "update_repository": config.get("updates", {}).get("repository") or repository,
            "update_check_on_use": bool(config.get("updates", {}).get("check_on_use", True)),
            "update_check_every_days": round(int(config.get("updates", {}).get("check_every_minutes", 43200)) / 1440, 1),
            "providers": provider_rows,
            "provider_health": health_summary,
            "creator_count": creator_count,
            "registry_db": str(registry_db),
        },
    )
    return payload.as_dict()


def print_system_status(payload: dict[str, Any]) -> None:
    print("MEDIA2MD_STATUS")
    for key in (
        "version",
        "project_root",
        "timezone",
        "ui_locale",
        "markdown_locale",
        "instagram_backend",
        "update_repository",
        "update_check_on_use",
        "update_check_every_days",
        "creator_count",
        "registry_db",
    ):
        print(f"{key}={payload[key]}")
    provider_health = payload.get("provider_health", {})
    if provider_health:
        print(f"provider_health_status={provider_health.get('status')}")
        print(f"provider_health_category={provider_health.get('category')}")
    print(f"primary_markdown_root={payload['project_root']}/markdown")
    print(f"primary_workspace_root={payload['project_root']}/workspace")
    print(f"tip=Run `{auth_status_command(output='ndjson')}` for machine-readable auth details.")
    print("\nPROVIDER   CONFIGURED  HEALTH    CATEGORY         BACKEND      MODE              BROWSER   PROFILE")
    for item in payload["providers"]:
        print(
            f"{item['provider']:<10} {str(item['configured']).lower():<11} {item.get('health_status', '-'): <9} "
            f"{item.get('health_category', '-'): <16} {(item.get('active_backend') or '-'): <12} {(item['auth_mode'] or '-'):<17} "
            f"{(item['browser'] or '-'):<9} {item['profile'] or '-'}"
        )


def settings_payload(config: dict[str, Any]) -> dict[str, Any]:
    payload = make_output_model(
        event="settings",
        schema="media2md.cli.settings/v1",
        summary="Current settings projection",
        sections=(
            make_section(
                "settings",
                status="ok",
                message="Settings are available",
                data={
                    "timezone": config.get("timezone", "UTC"),
                    "ui_locale": config.get("ui_locale", "en"),
                    "markdown_locale": config.get("markdown_locale", "en"),
                },
            ),
        ),
        data={
            "timezone": config.get("timezone", "UTC"),
            "ui_locale": config.get("ui_locale", "en"),
            "markdown_locale": config.get("markdown_locale", "en"),
            "defaults": config.get("defaults", {}),
            "providers": config.get("providers", {}),
            "updates": config.get("updates", {}),
        },
    )
    return payload.as_dict()


def print_json_block(title: str, payload: dict[str, Any]) -> None:
    print(title)
    print(json.dumps(payload, ensure_ascii=False, indent=2))


def apply_settings_updates(config: dict[str, Any], args) -> dict[str, Any]:
    if args.instagram_backend:
        config.setdefault("providers", {}).setdefault("instagram", {})["backend"] = args.instagram_backend
    if getattr(args, "youtube_js_runtime", None):
        config.setdefault("providers", {}).setdefault("youtube", {})["js_runtime"] = args.youtube_js_runtime
    if getattr(args, "youtube_allow_remote_ejs", None) is not None:
        config.setdefault("providers", {}).setdefault("youtube", {})["allow_remote_ejs"] = args.youtube_allow_remote_ejs
    if getattr(args, "youtube_po_token_provider", None):
        config.setdefault("providers", {}).setdefault("youtube", {})["po_token_provider"] = args.youtube_po_token_provider
    if getattr(args, "youtube_pot_browser_path", None):
        config.setdefault("providers", {}).setdefault("youtube", {})["pot_browser_path"] = args.youtube_pot_browser_path
    if getattr(args, "youtube_caption_first", None) is not None:
        config.setdefault("providers", {}).setdefault("youtube", {})["caption_first"] = args.youtube_caption_first
    if getattr(args, "youtube_caption_languages", None):
        config.setdefault("providers", {}).setdefault("youtube", {})["caption_languages"] = [
            item.strip() for item in args.youtube_caption_languages.split(",") if item.strip()
        ]
    if getattr(args, "youtube_audio_strategies", None):
        config.setdefault("providers", {}).setdefault("youtube", {})["audio_download_strategies"] = [
            item.strip() for item in args.youtube_audio_strategies.split(",") if item.strip()
        ]
    if getattr(args, "youtube_long_video_threshold_minutes", None) is not None:
        config.setdefault("providers", {}).setdefault("youtube", {})["long_video_threshold_seconds"] = max(
            60, int(args.youtube_long_video_threshold_minutes * 60)
        )
    if getattr(args, "youtube_chunk_minutes", None) is not None:
        config.setdefault("providers", {}).setdefault("youtube", {})["chunk_seconds"] = max(
            60, int(args.youtube_chunk_minutes * 60)
        )
    if getattr(args, "youtube_chunk_model", None):
        config.setdefault("providers", {}).setdefault("youtube", {})["chunk_model"] = args.youtube_chunk_model
    if getattr(args, "tiktok_impersonate", None):
        config.setdefault("providers", {}).setdefault("tiktok", {})["impersonate"] = args.tiktok_impersonate
    if args.update_check_every_days is not None:
        config.setdefault("updates", {})["check_every_minutes"] = int(args.update_check_every_days * 1440)
    if args.update_check_on_use is not None:
        config.setdefault("updates", {})["check_on_use"] = args.update_check_on_use
        config.setdefault("updates", {})["enabled"] = args.update_check_on_use
    return config


def agent_status_payload(config: dict[str, Any], *, schema_version: int) -> dict[str, Any]:
    payload = make_output_model(
        event="agent_status",
        schema="media2md.cli.agent_status/v1",
        summary="Agent-facing command and confirmation policy",
        sections=(
            make_section(
                "permissions",
                status="ok",
                message="Agent permissions model",
                data={"permissions": config.get("agent", {})},
            ),
        ),
        data={
            "non_interactive_locale": "en",
            "ndjson_schema_version": schema_version,
            "permissions": config.get("agent", {}),
            "update_confirmation_required": True,
            "delete_confirmation_required": True,
            "drain_confirmation_required": True,
            "stale_catalog_confirmation_required": True,
            "browser_launch_confirmation_required": True,
            "browser_launch_policy": "never",
            "normal_commands_may_launch_browser": False,
            "human_required_for": ["password", "2fa", "captcha", "platform_challenge"],
            "commands": {
                "read": ["status", "settings show", "creator status", "creator policy show", "auth status", "doctor all", "update status"],
                "write": ["settings set", "creator add", "creator policy set", "creator run", "scheduler tick", "auth refresh"],
                "confirmation": ["update install", "update rollback", "creator delete", "data delete-all", "drain"],
            },
        },
    )
    return payload.as_dict()
