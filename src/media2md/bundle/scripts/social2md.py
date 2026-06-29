#!/usr/bin/env python3
from __future__ import annotations

import argparse
import importlib
import json
import os
import shutil
import sqlite3
import subprocess
import sys
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from creator_run_shared import prepare_catalog_for_creator_run
from media2md_urls import detect_provider as detect_provider_url, normalize_creator as normalize_creator_target
try:
    from public_cli_imports import optional_attr, optional_attrs
except ModuleNotFoundError:
    def optional_attr(module_name: str, attr_name: str):
        try:
            module = importlib.import_module(module_name)
        except ModuleNotFoundError:
            return None
        return getattr(module, attr_name, None)

    def optional_attrs(module_name: str, *attr_names: str):
        try:
            module = importlib.import_module(module_name)
        except ModuleNotFoundError:
            return tuple(None for _ in attr_names)
        return tuple(getattr(module, attr_name, None) for attr_name in attr_names)

ROOT = Path(__file__).resolve().parents[1]
CORE = ROOT / "scripts" / "social2md_core.py"
REGISTRY = ROOT / "scripts" / "media2md_registry.py"
AUTH = ROOT / "scripts" / "media2md_auth.py"
GENERIC = ROOT / "scripts" / "generic_media.py"
UPDATE = ROOT / "scripts" / "media2md_update.py"
DOCTOR = ROOT / "scripts" / "media2md_doctor.py"
BACKUP = ROOT / "scripts" / "media2md_backup.py"
CONFIG = ROOT / "config" / "social2md.json"
POLICIES = ROOT / "config" / "provider_policies.json"
SCHEDULER_STATE = ROOT / "data" / "media2md_scheduler_state.json"
REGISTRY_DB = ROOT / "data" / "media2md.db"
AUTH_PROFILES = ROOT / "config" / "auth_profiles.json"
VERSION = "0.9.4"
REPOSITORY = "danielcanfly/media2md"
PROVIDERS = ("instagram", "youtube", "tiktok")
LOCALES = ("zh-TW", "zh-CN", "en", "ja")


def iso_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def load_json(path: Path, default: Any) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return json.loads(json.dumps(default))


def atomic_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.replace(temp, path)


def emit(payload: dict[str, Any], output: str) -> None:
    if output == "ndjson":
        print(json.dumps({"schema_version": 12, "timestamp": iso_now(), **payload}, ensure_ascii=False, sort_keys=True), flush=True)


def run(cmd: list[str], check: bool = False) -> int:
    result = subprocess.run(cmd, cwd=ROOT)
    if check and result.returncode != 0:
        raise RuntimeError(f"Command failed with exit code {result.returncode}: {' '.join(cmd)}")
    return result.returncode


def core(args: list[str]) -> int:
    return run([sys.executable, str(CORE), *args])


def registry(args: list[str]) -> int:
    return run([sys.executable, str(REGISTRY), *args])


def auth(args: list[str]) -> int:
    return run([sys.executable, str(AUTH), *args])


def refresh_auth(provider: str) -> None:
    if provider in {"instagram", "tiktok"}:
        subprocess.run([sys.executable, str(AUTH), "refresh", provider, "--quiet"], cwd=ROOT, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False)


def generic(args: list[str]) -> int:
    return run([sys.executable, str(GENERIC), *args])


def detect_provider(value: str) -> str | None:
    detect_provider_service = optional_attr("creator_resolution_service", "detect_provider")
    if detect_provider_service is not None:
        return detect_provider_service(value)
    return detect_provider_url(value)


def normalize_creator(provider: str, value: str) -> str:
    normalize_creator_handle_service = optional_attr("creator_resolution_service", "normalize_creator_handle")
    if normalize_creator_handle_service is not None:
        return normalize_creator_handle_service(provider, value)
    return str(normalize_creator_target(provider, value).creator)


def resolve_creator_provider(value: str, provider: str | None, *, command_name: str) -> str:
    resolve_provider_for_creator_service = optional_attr("creator_resolution_service", "resolve_provider_for_creator")
    if resolve_provider_for_creator_service is not None:
        return resolve_provider_for_creator_service(value, provider, command_name=command_name)
    if provider:
        return provider
    detected = detect_provider(value)
    if detected:
        return detected
    raise RuntimeError(
        f"{command_name} requires --provider when <creator> is a bare handle. "
        "Use a full creator URL or pass --provider instagram|youtube|tiktok."
    )


def update_tool(args: list[str], capture: bool = False) -> int | subprocess.CompletedProcess[str]:
    cmd=[sys.executable,str(UPDATE),*args]
    if capture:
        return subprocess.run(cmd,cwd=ROOT,capture_output=True,text=True,check=False,timeout=8)
    return run(cmd)


def policy_defaults() -> dict[str, Any]:
    return {
        "sync": {"enabled": False, "every_minutes": 1440, "full_every_minutes": 10080, "quick_window": 100},
        "processing": {"scheduled": False, "every_minutes": 4320, "mode": "batch", "batch_size": 100,
                       "max_batches": 0, "max_runtime_minutes": 360, "max_failures": 10,
                       "stop_on_failure": False, "sleep_between_batches": 5},
        "filters": {"since": None, "until": None, "rank_from": None, "rank_to": None, "order": "newest_first"},
    }


def load_policies() -> dict[str, Any]:
    data = load_json(POLICIES, {"schema_version": 2, "creators": {}})
    data.setdefault("schema_version", 2); data.setdefault("creators", {})
    return data


def merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    out = json.loads(json.dumps(base))
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(out.get(key), dict): out[key] = merge(out[key], value)
        else: out[key] = value
    return out


def effective_policy(provider: str, creator: str) -> dict[str, Any]:
    effective_policy_service = optional_attr("creator_policy_service", "effective_policy")
    if effective_policy_service is not None:
        return effective_policy_service(load_json, CONFIG, POLICIES, provider, creator)
    return merge(policy_defaults(), load_policies()["creators"].get(f"{provider}:{creator}", {}))


def parse_duration(text: str) -> int:
    import re
    match = re.fullmatch(r"(\d+(?:\.\d+)?)(m|h|d|w)", text.strip(), re.I)
    if not match: raise argparse.ArgumentTypeError("Use 30m, 6h, 1d, or 1w.")
    return int(round(float(match.group(1)) * {"m":1,"h":60,"d":1440,"w":10080}[match.group(2).lower()]))


def duration(minutes: int) -> str:
    for unit, factor in (("w",10080),("d",1440),("h",60)):
        if minutes % factor == 0: return f"{minutes//factor}{unit}"
    return f"{minutes}m"


def set_policy(args: argparse.Namespace, sync_enabled: bool | None = None) -> int:
    set_policy_service = optional_attr("creator_policy_service", "set_policy")
    if set_policy_service is not None:
        return set_policy_service(
            args,
            load_json=load_json,
            atomic_json=atomic_json,
            config_path=CONFIG,
            policies_path=POLICIES,
            sync_enabled=sync_enabled,
        )
    provider = args.provider
    creator = normalize_creator(provider, args.creator)
    data = load_policies(); entry = data["creators"].setdefault(f"{provider}:{creator}", {})
    if sync_enabled is not None: entry.setdefault("sync", {})["enabled"] = sync_enabled
    if getattr(args, "every", None) is not None: entry.setdefault("sync", {})["every_minutes"] = args.every
    if getattr(args, "full_every", None) is not None: entry.setdefault("sync", {})["full_every_minutes"] = args.full_every
    if getattr(args, "quick_window", None) is not None: entry.setdefault("sync", {})["quick_window"] = args.quick_window
    for key in ("mode","batch_size","max_batches","max_runtime_minutes","max_failures","sleep_between_batches"):
        value = getattr(args, key, None)
        if value is not None: entry.setdefault("processing", {})[key] = value
    if getattr(args, "stop_on_failure", None) is not None: entry.setdefault("processing", {})["stop_on_failure"] = args.stop_on_failure
    if getattr(args, "scheduled_processing", None) is not None: entry.setdefault("processing", {})["scheduled"] = args.scheduled_processing
    if getattr(args, "processing_every", None) is not None: entry.setdefault("processing", {})["every_minutes"] = args.processing_every
    for key in ("since","until","rank_from","rank_to","order"):
        value = getattr(args, key, None)
        if value is not None: entry.setdefault("filters", {})[key] = value
    atomic_json(POLICIES, data)
    result = effective_policy(provider, creator)
    print("CREATOR_POLICY_UPDATED")
    print(f"provider={provider}")
    print(f"creator={creator}")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


def registry_rows() -> list[dict[str, Any]]:
    registry_rows_service = optional_attr("public_cli_state_service", "registry_rows")
    if registry_rows_service is not None:
        return registry_rows_service(REGISTRY_DB, include_youtube_totals=False)
    try:
        from media2md_registry import refresh_legacy
        refresh_legacy()
    except Exception:
        pass
    if not REGISTRY_DB.is_file(): return []
    conn = sqlite3.connect(REGISTRY_DB); conn.row_factory=sqlite3.Row
    rows = conn.execute("""SELECT c.provider,c.handle,c.source_url,c.current_total,c.current_total_exact,c.last_sync_mode,c.last_sync_at,c.last_full_sync_at,
        COUNT(m.id) tracked, SUM(CASE WHEN m.status='completed' THEN 1 ELSE 0 END) completed,
        SUM(CASE WHEN m.is_current=1 AND m.status NOT IN ('completed','skipped') THEN 1 ELSE 0 END) remaining
        FROM creators c LEFT JOIN media m ON m.creator_id=c.id GROUP BY c.id ORDER BY c.provider,lower(c.handle)""").fetchall()
    conn.close(); return [dict(r) for r in rows]


def creator_status(args: argparse.Namespace) -> int:
    render_creator_status_service = optional_attr("public_cli_state_service", "render_creator_status")
    rows=registry_rows(); policies=load_policies()["creators"]
    if args.provider: rows=[r for r in rows if r["provider"]==args.provider]
    if args.creator:
        handle=normalize_creator(args.provider or detect_provider(args.creator) or "instagram",args.creator)
        rows=[r for r in rows if r["handle"].lower()==handle.lower()]
    if render_creator_status_service is not None:
        return render_creator_status_service(
            args,
            rows=rows,
            effective_policy=effective_policy,
            emit=emit,
            duration=duration,
            include_youtube_breakdown=False,
            include_batch_limits=False,
        )
    if args.output=="ndjson":
        for row in rows:
            policy=effective_policy(row["provider"],row["handle"])
            emit({"event":"creator_status",**row,"policy":policy},args.output)
        emit({"event":"creator_status_completed","count":len(rows)},args.output); return 0
    print("PLATFORM   CREATOR                    SYNC  EVERY  FULL  MODE   BATCH  TRACKED  DONE  LEFT  LAST SYNC")
    for row in rows:
        p=effective_policy(row["provider"],row["handle"])
        print(f"{row['provider']:<10} {row['handle'][:26]:<26} {str(p['sync']['enabled']).lower():<5} {duration(p['sync']['every_minutes']):<6} {duration(p['sync']['full_every_minutes']):<5} {p['processing']['mode']:<6} {p['processing']['batch_size']:<6} {row['tracked'] or 0:<8} {row['completed'] or 0:<5} {row['remaining'] or 0:<5} {row['last_sync_at'] or '-'}")
    print(f"TOTAL={len(rows)}")
    return 0


def system_status(args: argparse.Namespace) -> int:
    print_system_status_service, system_status_payload_service = optional_attrs(
        "public_cli_state_service",
        "print_system_status",
        "system_status_payload",
    )
    config=load_json(CONFIG,{})
    auth_data=load_json(AUTH_PROFILES,{"providers":{}}).get("providers",{})
    if system_status_payload_service is not None:
        payload = system_status_payload_service(
            config=config,
            auth_data=auth_data,
            providers=PROVIDERS,
            version=VERSION,
            root=ROOT,
            repository=REPOSITORY,
            creator_count=len(registry_rows()),
            registry_db=REGISTRY_DB,
        )
        if args.output=="ndjson": emit(payload,args.output); return 0
        print_system_status_service(payload)
        return 0
    providers=[]
    for name in PROVIDERS:
        profile=auth_data.get(name,{})
        cookie=profile.get("cookie_file")
        configured = bool(cookie and Path(cookie).is_file()) or bool(name == "youtube" and profile.get("mode") == "browser_profile" and profile.get("browser") and profile.get("profile"))
        providers.append({"provider":name,"configured":configured,"auth_mode":profile.get("mode"),"browser":profile.get("browser"),"profile":profile.get("profile")})
    payload={"event":"system_status","version":VERSION,"project_root":str(ROOT),"timezone":config.get("timezone","UTC"),
             "ui_locale":config.get("ui_locale","en"),"markdown_locale":config.get("markdown_locale","en"),
             "instagram_backend":config.get("providers",{}).get("instagram",{}).get("backend","auto"),
             "update_repository":config.get("updates",{}).get("repository") or REPOSITORY,
             "update_check_on_use":bool(config.get("updates",{}).get("check_on_use",True)),
             "update_check_every_days":round(int(config.get("updates",{}).get("check_every_minutes",43200))/1440,1),
             "providers":providers,"creator_count":len(registry_rows()),"registry_db":str(REGISTRY_DB)}
    if args.output=="ndjson": emit(payload,args.output); return 0
    print("MEDIA2MD_STATUS")
    for key in ("version","project_root","timezone","ui_locale","markdown_locale","instagram_backend","update_repository","update_check_on_use","update_check_every_days","creator_count","registry_db"):
        print(f"{key}={payload[key]}")
    print("\nPROVIDER   CONFIGURED  MODE              BROWSER   PROFILE")
    for item in providers: print(f"{item['provider']:<10} {str(item['configured']).lower():<11} {(item['auth_mode'] or '-'):<17} {(item['browser'] or '-'):<9} {item['profile'] or '-'}")
    return 0


def settings_show(args: argparse.Namespace) -> int:
    print_json_block_service, settings_payload_service = optional_attrs(
        "public_cli_state_service",
        "print_json_block",
        "settings_payload",
    )
    config=load_json(CONFIG,{})
    if settings_payload_service is not None:
        payload = settings_payload_service(config)
        if args.output=="ndjson": emit(payload,args.output); return 0
        print_json_block_service("MEDIA2MD_SETTINGS", payload)
        return 0
    payload={"event":"settings","timezone":config.get("timezone","UTC"),"ui_locale":config.get("ui_locale","en"),
             "markdown_locale":config.get("markdown_locale","en"),"defaults":config.get("defaults",{}),
             "providers":config.get("providers",{}),"updates":config.get("updates",{})}
    if args.output=="ndjson": emit(payload,args.output); return 0
    print("MEDIA2MD_SETTINGS")
    print(json.dumps(payload,ensure_ascii=False,indent=2)); return 0


def settings_set(args: argparse.Namespace) -> int:
    apply_settings_updates_service = optional_attr("public_cli_state_service", "apply_settings_updates")
    config=load_json(CONFIG,{})
    if apply_settings_updates_service is not None:
        config = apply_settings_updates_service(config, args)
        atomic_json(CONFIG,config); return settings_show(argparse.Namespace(output=args.output))
    if args.instagram_backend:
        config.setdefault("providers",{}).setdefault("instagram",{})["backend"]=args.instagram_backend
    if getattr(args, "youtube_js_runtime", None):
        config.setdefault("providers",{}).setdefault("youtube",{})["js_runtime"]=args.youtube_js_runtime
    if getattr(args, "youtube_allow_remote_ejs", None) is not None:
        config.setdefault("providers",{}).setdefault("youtube",{})["allow_remote_ejs"]=args.youtube_allow_remote_ejs
    if getattr(args, "youtube_po_token_provider", None):
        config.setdefault("providers",{}).setdefault("youtube",{})["po_token_provider"]=args.youtube_po_token_provider
    if getattr(args, "youtube_pot_browser_path", None):
        config.setdefault("providers",{}).setdefault("youtube",{})["pot_browser_path"]=args.youtube_pot_browser_path
    if getattr(args, "youtube_caption_first", None) is not None:
        config.setdefault("providers",{}).setdefault("youtube",{})["caption_first"]=args.youtube_caption_first
    if getattr(args, "youtube_caption_languages", None):
        config.setdefault("providers",{}).setdefault("youtube",{})["caption_languages"]=[item.strip() for item in args.youtube_caption_languages.split(",") if item.strip()]
    if getattr(args, "youtube_audio_strategies", None):
        config.setdefault("providers",{}).setdefault("youtube",{})["audio_download_strategies"]=[item.strip() for item in args.youtube_audio_strategies.split(",") if item.strip()]
    if getattr(args, "youtube_long_video_threshold_minutes", None) is not None:
        config.setdefault("providers",{}).setdefault("youtube",{})["long_video_threshold_seconds"]=max(60,int(args.youtube_long_video_threshold_minutes*60))
    if getattr(args, "youtube_chunk_minutes", None) is not None:
        config.setdefault("providers",{}).setdefault("youtube",{})["chunk_seconds"]=max(60,int(args.youtube_chunk_minutes*60))
    if getattr(args, "youtube_chunk_model", None):
        config.setdefault("providers",{}).setdefault("youtube",{})["chunk_model"]=args.youtube_chunk_model
    if getattr(args, "tiktok_impersonate", None):
        config.setdefault("providers",{}).setdefault("tiktok",{})["impersonate"]=args.tiktok_impersonate
    if args.update_check_every_days is not None:
        config.setdefault("updates",{})["check_every_minutes"]=int(args.update_check_every_days*1440)
    if args.update_check_on_use is not None:
        config.setdefault("updates",{})["check_on_use"]=args.update_check_on_use
        config.setdefault("updates",{})["enabled"]=args.update_check_on_use
    atomic_json(CONFIG,config); return settings_show(argparse.Namespace(output=args.output))


def init_command(args: argparse.Namespace) -> int:
    forwarded = ["init"]
    if args.language:
        forwarded.extend(["--language", args.language])
    if args.markdown_language:
        forwarded.extend(["--markdown-language", args.markdown_language])
    if args.timezone:
        forwarded.extend(["--timezone", args.timezone])
    if args.non_interactive:
        forwarded.append("--non-interactive")
    return core(forwarded)


def agent_status(args: argparse.Namespace) -> int:
    agent_status_payload_service, print_json_block_service = optional_attrs(
        "public_cli_state_service",
        "agent_status_payload",
        "print_json_block",
    )
    config=load_json(CONFIG,{})
    if agent_status_payload_service is not None:
        payload = agent_status_payload_service(config, schema_version=12)
        if args.output=="ndjson": emit(payload,args.output); return 0
        print_json_block_service("MEDIA2MD_AGENT_STATUS", payload); return 0
    agent=config.get("agent",{})
    payload={"event":"agent_status","non_interactive_locale":"en","ndjson_schema_version":12,
             "permissions":agent,"update_confirmation_required":True,"delete_confirmation_required":True,
             "drain_confirmation_required":True,"stale_catalog_confirmation_required":True,"browser_launch_confirmation_required":True,
             "browser_launch_policy":"never","normal_commands_may_launch_browser":False,"human_required_for":["password","2fa","captcha","platform_challenge"],"commands":{"read":["status","settings show","creator status","creator policy show","auth status","doctor all","update status"],"write":["settings set","creator add","creator policy set","creator run","scheduler tick","auth refresh"],"confirmation":["update install","update rollback","creator delete","data delete-all","drain"]}}
    if args.output=="ndjson": emit(payload,args.output); return 0
    print("MEDIA2MD_AGENT_STATUS"); print(json.dumps(payload,ensure_ascii=False,indent=2)); return 0


def refresh_registry_legacy() -> None:
    try:
        from media2md_registry import refresh_legacy
        refresh_legacy()
    except Exception:
        pass


def policy_show(args: argparse.Namespace) -> int:
    creator_policy_payload_service, print_policy_service = optional_attrs(
        "public_cli_creator_service",
        "creator_policy_payload",
        "print_policy",
    )
    provider=args.provider or detect_provider(args.creator) or "instagram"
    creator=normalize_creator(provider,args.creator)
    if creator_policy_payload_service is not None:
        payload = creator_policy_payload_service(provider=provider, creator=creator, effective_policy=effective_policy)
        if args.output=="ndjson": emit(payload,args.output); return 0
        print_policy_service(payload); return 0
    payload={"event":"creator_policy","provider":provider,"creator":creator,"policy":effective_policy(provider,creator)}
    if args.output=="ndjson": emit(payload,args.output); return 0
    print("CREATOR_POLICY"); print(json.dumps(payload,ensure_ascii=False,indent=2)); return 0


def creator_sync(args: argparse.Namespace) -> int:
    creator_sync_common_service = optional_attr("public_cli_creator_service", "creator_sync_common")
    provider=args.provider or detect_provider(args.creator) or "instagram"
    refresh_auth(provider)
    if creator_sync_common_service is not None:
        return creator_sync_common_service(
            args,
            root=ROOT,
            provider=provider,
            normalize_creator=normalize_creator,
            effective_policy=effective_policy,
            registry=registry,
            run=run,
        )
    if provider=="instagram":
        command=["creator_bulk.py","status"]
        # Use existing engine directly through its status command.
        engine=ROOT/"scripts"/"creator_bulk.py"
        extra=[sys.executable,str(engine),"status",args.creator]
        if args.force_full: extra.append("--force-full-sync")
        return run(extra)
    mode="full" if args.force_full else "quick"
    policy=effective_policy(provider,normalize_creator(provider,args.creator))
    return registry(["sync",provider,args.creator,"--mode",mode,"--quick-window",str(policy["sync"]["quick_window"])])


def creator_run(args: argparse.Namespace) -> int:
    (
        creator_run_context_service,
        creator_run_catalog_preflight_service,
        creator_run_instagram_service,
        creator_run_registry_command_service,
    ) = optional_attrs(
        "public_cli_creator_service",
        "creator_run_context",
        "creator_run_catalog_preflight",
        "creator_run_instagram",
        "creator_run_registry_command",
    )
    provider=args.provider or detect_provider(args.creator) or "instagram"
    refresh_auth(provider)
    creator=normalize_creator(provider,args.creator)
    policy=effective_policy(provider,creator)
    if creator_run_context_service is not None:
        run_ctx = creator_run_context_service(
            args=args,
            provider=provider,
            creator=creator,
            policy=policy,
            parse_batch_size_assignments=None,
            normalize_batch_sizes=None,
            typed_batch_sizes_supported=False,
        )
        mode = run_ctx["mode"]
        batch_size = run_ctx["batch_size"]
        batch_sizes = run_ctx["batch_sizes"]
    else:
        mode=args.mode or policy["processing"]["mode"]
        batch_size=args.batch_size or policy["processing"]["batch_size"]
        batch_sizes = {}
    if provider=="instagram":
        if creator_run_instagram_service is not None:
            return creator_run_instagram_service(
                args,
                batch_size=batch_size,
                mode=mode,
                core=core,
                retry_failed_supported=False,
                refresh_registry=refresh_registry_legacy,
            )
        cmd=["creator","run",args.creator,"--mode",mode,"--batch-size",str(batch_size),"--output",args.output]
        for name, flag in (("since","--since"),("until","--until"),("rank_from","--rank-from"),("rank_to","--rank-to"),("order","--order"),("max_batches","--max-batches"),("max_runtime_minutes","--max-runtime-minutes"),("max_failures","--max-failures"),("sleep_between_batches","--sleep-between-batches")):
            value=getattr(args,name,None)
            if value is not None: cmd += [flag,str(value)]
        if args.stop_on_failure: cmd.append("--stop-on-failure")
        code = core(cmd)
        refresh_registry_legacy()
        return code
    # Use the shared pre-run catalog decision so every public CLI surface
    # follows the same partial-cursor behavior.
    current_rows = registry_rows()
    if creator_run_catalog_preflight_service is not None:
        existing_row, outcome = creator_run_catalog_preflight_service(
            args=args,
            provider=provider,
            creator=creator,
            policy=policy,
            registry_rows=current_rows,
            prepare_catalog_for_creator_run=prepare_catalog_for_creator_run,
            registry_call=registry,
            emit_call=emit,
        )
        if outcome is not None:
            return outcome
    else:
        existing_row = next((r for r in current_rows if r["provider"]==provider and r["handle"].lower()==creator.lower()), None)
        sync_code = prepare_catalog_for_creator_run(
            provider=provider,
            creator_arg=args.creator,
            normalized_creator=creator,
            existing_row=existing_row,
            quick_window=int(policy["sync"]["quick_window"]),
            output=args.output,
            registry_call=registry,
            emit_call=emit,
        )
        if sync_code != 0:
            can_use_stale = bool(args.allow_stale_catalog and existing_row and int(existing_row.get("tracked") or 0) > 0)
            if not can_use_stale:
                if args.output=="human": print(f"SYNC_FAILED provider={provider} creator={creator}; batch_not_started=true",file=sys.stderr)
                else: emit({"event":"sync_failed","provider":provider,"creator":creator,"batch_not_started":True},args.output)
                return sync_code
            warning = {
                "event": "sync_warning",
                "provider": provider,
                "creator": creator,
                "using_cached_catalog": True,
                "catalog_last_synced_at": existing_row.get("last_sync_at"),
                "tracked": int(existing_row.get("tracked") or 0),
                "confirmation_was_explicit": True,
            }
            if args.output=="human":
                print("SYNC_WARNING", flush=True)
                print(f"provider={provider}", flush=True)
                print(f"creator={creator}", flush=True)
                print("using_cached_catalog=true", flush=True)
                print(f"catalog_last_synced_at={existing_row.get('last_sync_at') or '-'}", flush=True)
                print(f"tracked={int(existing_row.get('tracked') or 0)}", flush=True)
            else:
                emit(warning,args.output)
    if creator_run_registry_command_service is not None:
        cmd = creator_run_registry_command_service(
            args,
            provider=provider,
            policy=policy,
            batch_size=batch_size,
            batch_sizes=batch_sizes,
            include_typed_batch_sizes=False,
        )
    else:
        cmd=["run",provider,args.creator,"--mode",mode,"--batch-size",str(batch_size),"--max-batches",str(args.max_batches if args.max_batches is not None else policy["processing"]["max_batches"]),"--max-runtime-minutes",str(args.max_runtime_minutes if args.max_runtime_minutes is not None else policy["processing"]["max_runtime_minutes"]),"--max-failures",str(args.max_failures if args.max_failures is not None else policy["processing"]["max_failures"]),"--sleep-between-batches",str(args.sleep_between_batches if args.sleep_between_batches is not None else policy["processing"]["sleep_between_batches"]),"--order",args.order or policy["filters"]["order"],"--output",args.output]
        if args.stop_on_failure or policy["processing"].get("stop_on_failure"): cmd.append("--stop-on-failure")
        for val,flag in ((args.since or policy["filters"].get("since"),"--since"),(args.until or policy["filters"].get("until"),"--until"),(args.rank_from or policy["filters"].get("rank_from"),"--rank-from"),(args.rank_to or policy["filters"].get("rank_to"),"--rank-to")):
            if val is not None: cmd += [flag,str(val)]
    return registry(cmd)


def add_creator(args: argparse.Namespace) -> int:
    add_creator_instagram_service = optional_attr("public_cli_creator_service", "add_creator_instagram")
    provider = args.provider
    refresh_auth(provider)
    if provider == "instagram":
        normalized = normalize_creator(provider, args.creator)
        creator_input = args.creator
        if add_creator_instagram_service is not None:
            code = add_creator_instagram_service(root=ROOT, creator_input=creator_input, normalized_creator=normalized)
            if code != 0:
                return code
        else:
            try:
                import yaml  # type: ignore  # noqa: F401
            except ImportError as exc:
                raise RuntimeError('Instagram support is not installed. Run: python -m pip install "media2md[instagram]"') from exc
            manager = ROOT / "scripts" / "manage_creators.py"
            result = subprocess.run([sys.executable, str(manager), "add", args.creator], cwd=ROOT)
            if result.returncode not in (0,):
                # Existing creator is not a destructive error for an idempotent add command.
                conn = sqlite3.connect(ROOT / "data" / "state.db") if (ROOT / "data" / "state.db").is_file() else None
                exists = False
                if conn:
                    try:
                        exists = conn.execute("SELECT 1 FROM creators WHERE username=? COLLATE NOCASE", (args.creator.lstrip('@'),)).fetchone() is not None
                    finally:
                        conn.close()
                if not exists:
                    return result.returncode
        registry(["migrate"])
        print(f"CREATOR_ADDED provider=instagram creator={normalized} sync_enabled=false")
        return 0
    # For YouTube and TikTok, a full initial catalog establishes the platform identity.
    code = registry(["sync", provider, args.creator, "--mode", "full"])
    if code == 0:
        print(f"CREATOR_ADDED provider={provider} creator={normalize_creator(provider,args.creator)} sync_enabled=false")
    return code


def scheduler_tick(args: argparse.Namespace) -> int:
    build_scheduler_creator_run_namespace_service, scheduler_tick_common_service = optional_attrs(
        "public_cli_tail_service",
        "build_scheduler_creator_run_namespace",
        "scheduler_tick_common",
    )
    if scheduler_tick_common_service is not None:
        return scheduler_tick_common_service(
            args,
            load_policies=load_policies,
            load_json=load_json,
            atomic_json=atomic_json,
            scheduler_state_path=SCHEDULER_STATE,
            refresh_auth=refresh_auth,
            core=core,
            effective_policy=effective_policy,
            registry=registry,
            creator_run_builder=lambda provider, creator, processing, output: build_scheduler_creator_run_namespace_service(
                provider=provider,
                creator=creator,
                processing=processing,
                output=output,
                batch_size_type_supported=False,
                retry_failed_supported=False,
            ),
            creator_run=creator_run,
            iso_now=iso_now,
            emit=emit,
        )
    policies=load_policies()["creators"]; state=load_json(SCHEDULER_STATE,{"creators":{}}); now=datetime.now(timezone.utc)
    jobs=0; failures=0
    # Refresh browser-backed snapshots before unattended work.
    refresh_auth("instagram"); refresh_auth("tiktok")
    # Instagram legacy scheduler first for compatibility.
    code=core(["scheduler","tick","--output",args.output,"--non-interactive"])
    if code not in (0,): failures += 1
    for key in sorted(policies):
        if ":" not in key: continue
        provider,creator=key.split(":",1)
        if provider=="instagram": continue
        policy=effective_policy(provider,creator); creator_state=state["creators"].setdefault(key,{})
        last=creator_state.get("last_sync_success_at")
        due=True
        if last:
            try: due=now >= datetime.fromisoformat(last)+timedelta(minutes=policy["sync"]["every_minutes"])
            except ValueError: pass
        if policy["sync"]["enabled"] and due:
            jobs += 1
            last_full=creator_state.get("last_full_sync_at")
            full_due=not last_full
            if last_full:
                try: full_due=now >= datetime.fromisoformat(last_full)+timedelta(minutes=policy["sync"]["full_every_minutes"])
                except ValueError: full_due=True
            sync_code=registry(["sync",provider,creator,"--mode","full" if full_due else "quick","--quick-window",str(policy["sync"]["quick_window"])])
            if sync_code==0:
                creator_state["last_sync_success_at"]=iso_now()
                if full_due: creator_state["last_full_sync_at"]=iso_now()
            else: failures += 1
        processing=policy["processing"]
        last_proc=creator_state.get("last_processing_success_at")
        proc_due=not last_proc
        if last_proc:
            try: proc_due=now >= datetime.fromisoformat(last_proc)+timedelta(minutes=processing["every_minutes"])
            except ValueError: proc_due=True
        if processing.get("scheduled") and proc_due:
            jobs += 1
            ns=argparse.Namespace(provider=provider,creator=creator,mode=processing["mode"],batch_size=processing["batch_size"],max_batches=processing["max_batches"],max_runtime_minutes=processing["max_runtime_minutes"],max_failures=processing["max_failures"],stop_on_failure=processing["stop_on_failure"],sleep_between_batches=processing["sleep_between_batches"],since=None,until=None,rank_from=None,rank_to=None,order=None,output=args.output)
            run_code=creator_run(ns)
            if run_code==0: creator_state["last_processing_success_at"]=iso_now()
            else: failures += 1
        atomic_json(SCHEDULER_STATE,state)
    emit({"event":"media2md_scheduler_completed","jobs_run":jobs,"failures":failures},args.output)
    if args.output=="human": print(f"MEDIA2MD_SCHEDULER_COMPLETED jobs_run={jobs} failures={failures}")
    return 0 if failures==0 else 2


def update_check(args: argparse.Namespace) -> int:
    update_check_common_service = optional_attr("public_cli_tail_service", "update_check_common")
    if update_check_common_service is not None:
        return update_check_common_service(args, repository=REPOSITORY, version=VERSION, emit=emit)
    repo=args.repository or REPOSITORY
    request=urllib.request.Request(f"https://api.github.com/repos/{repo}/releases/latest",headers={"Accept":"application/vnd.github+json","User-Agent":"media2md"})
    try:
        with urllib.request.urlopen(request,timeout=20) as response: release=json.loads(response.read().decode())
        latest=str(release.get("tag_name") or "")
        def parts(v:str): return tuple(int(x) for x in __import__('re').findall(r"\d+",v)[:3])
        available=parts(latest)>parts(VERSION)
        payload={"event":"update_check","repository":repo,"current_version":VERSION,"latest_version":latest,"update_available":available,"release_url":release.get("html_url")}
    except urllib.error.HTTPError as exc:
        if exc.code==404:
            payload={"event":"update_check","repository":repo,"current_version":VERSION,"latest_version":None,"update_available":False,"status":"no_release_published"}
        else: raise RuntimeError(f"GitHub update check failed: HTTP {exc.code}")
    if args.output=="ndjson": emit(payload,args.output)
    else:
        print("UPDATE_CHECK")
        for k,v in payload.items():
            if k!="event": print(f"{k}={v}")
    return 0


def data_delete_all(args: argparse.Namespace) -> int:
    data_delete_all_common_service = optional_attr("public_cli_tail_service", "data_delete_all_common")
    if data_delete_all_common_service is not None:
        return data_delete_all_common_service(args, root=ROOT)
    from media2md_runtime import maintenance_lock

    if not args.yes or args.confirm != "DELETE-ALL-DATA":
        raise RuntimeError("Use --yes --confirm DELETE-ALL-DATA.")
    with maintenance_lock(exclusive=True, operation="data-delete-all"):
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        quarantine = ROOT / ".media2md-quarantine" / f"all-data-{stamp}"
        quarantine.mkdir(parents=True, exist_ok=True)
        moved: list[str] = []
        for relative in ("data", "markdown", "workspace", "logs", "config"):
            source = ROOT / relative
            if not source.exists():
                continue
            target = quarantine / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(source), str(target))
            moved.append(relative)
        for relative in ("data", "markdown", "workspace", "logs/runs", "config"):
            (ROOT / relative).mkdir(parents=True, exist_ok=True)
    print(f"ALL_DATA_QUARANTINED path={quarantine.relative_to(ROOT)}")
    print(f"moved={','.join(moved)}")
    print("recoverable=true")
    return 0


def remove_openclaw_cron() -> tuple[int, list[str]]:
    remove_openclaw_cron_common_service = optional_attr("public_cli_tail_service", "remove_openclaw_cron_common")
    if remove_openclaw_cron_common_service is not None:
        return remove_openclaw_cron_common_service()
    executable = shutil.which("openclaw")
    if not executable:
        return 0, []
    removed: list[str] = []
    result = subprocess.run([executable, "cron", "list", "--json"], capture_output=True, text=True, check=False)
    if result.returncode != 0:
        return 0, []
    try:
        payload = json.loads(result.stdout)
    except json.JSONDecodeError:
        return 0, []
    jobs = payload.get("jobs", payload if isinstance(payload, list) else [])
    if not isinstance(jobs, list):
        return 0, []
    for job in jobs:
        if not isinstance(job, dict):
            continue
        name = str(job.get("name") or job.get("title") or "")
        job_id = job.get("id") or job.get("job_id")
        if name in {"Media2MD scheduler", "Social2MD scheduler"} and job_id:
            removal = subprocess.run([executable, "cron", "remove", str(job_id)], check=False)
            if removal.returncode == 0:
                removed.append(str(job_id))
    return 0, removed


def uninstall(args: argparse.Namespace) -> int:
    uninstall_common_service = optional_attr("public_cli_tail_service", "uninstall_common")
    if uninstall_common_service is not None:
        return uninstall_common_service(
            args,
            data_delete_all=data_delete_all,
            remove_openclaw_cron=remove_openclaw_cron,
            run=run,
        )
    if args.purge_data:
        data_delete_all(argparse.Namespace(yes=args.yes, confirm=args.confirm))
    _, removed_jobs = remove_openclaw_cron()
    removed_skills = []
    for name in ("media2md", "social2md"):
        skill = Path.home() / ".openclaw" / "skills" / name
        if skill.exists():
            shutil.rmtree(skill)
            removed_skills.append(name)
    registry_file = Path.home() / ".config" / "media2md" / "project.json"
    registry_file.unlink(missing_ok=True)
    print("MEDIA2MD_UNINSTALL_PREPARED")
    print(f"openclaw_cron_removed={len(removed_jobs)}")
    print(f"openclaw_skills_removed={','.join(removed_skills) or '-'}")
    print(f"data_purged={str(args.purge_data).lower()}")
    print("package_command=python -m pip uninstall -y media2md social2md")
    if getattr(args, "dry_run", False):
        print("package_uninstalled=false")
        print("next_step=run `media2md uninstall` to remove the installed Python package")
        return 0
    print("package_uninstalled=true")
    return run([sys.executable, "-m", "pip", "uninstall", "-y", "media2md", "social2md"])



def repair_active_states(args: argparse.Namespace) -> int:
    if not args.yes:
        raise RuntimeError("Use --yes to requeue abandoned active states.")
    active=("downloading","downloaded","transcribing","transcribed","rendering","validating","cleaning")
    repaired={}
    for path,table,key in ((ROOT/"data"/"state.db","videos","status"),(ROOT/"data"/"social2md_media.db","media","status"),(ROOT/"data"/"media2md.db","media","status")):
        if not path.is_file(): continue
        conn=sqlite3.connect(path)
        placeholders=','.join('?' for _ in active)
        try:
            cursor=conn.execute(f"UPDATE {table} SET status='pending',last_error='Recovered from abandoned active state',updated_at=? WHERE {key} IN ({placeholders})",(iso_now(),*active))
            conn.commit(); repaired[path.name]=cursor.rowcount
        finally: conn.close()
    registry(["repair-identities"]); print("ACTIVE_STATES_REPAIRED"); print(json.dumps(repaired,indent=2)); return 0


def repair_workspace(args: argparse.Namespace) -> int:
    if not args.yes:
        raise RuntimeError("Use --yes to remove stale intermediate workspace files.")
    active = ("downloading", "downloaded", "transcribing", "transcribed", "rendering", "validating", "cleaning")
    databases = ((ROOT / "data" / "state.db", "videos"), (ROOT / "data" / "social2md_media.db", "media"), (ROOT / "data" / "media2md.db", "media"))
    active_rows = 0
    for path, table in databases:
        if not path.is_file():
            continue
        conn = sqlite3.connect(path)
        placeholders = ",".join("?" for _ in active)
        try:
            active_rows += int(conn.execute(f"SELECT COUNT(*) FROM {table} WHERE status IN ({placeholders})", active).fetchone()[0])
        finally:
            conn.close()
    if active_rows:
        raise RuntimeError(f"Refusing workspace cleanup while {active_rows} active media rows exist. Run repair active-states only after confirming no worker is running.")
    targets = (
        ROOT / "workspace" / "downloads",
        ROOT / "workspace" / "transcripts",
        ROOT / "workspace" / "temp",
        ROOT / "workspace" / "generic_downloads",
        ROOT / "workspace" / "generic_transcripts",
    )
    removed_files = 0
    for target in targets:
        if target.exists():
            removed_files += sum(1 for path in target.rglob("*") if path.is_file())
            shutil.rmtree(target)
        target.mkdir(parents=True, exist_ok=True)
    print("WORKSPACE_REPAIRED")
    print(f"removed_files={removed_files}")
    print("active_rows=0")
    return 0


def maybe_check_update(args: argparse.Namespace) -> None:
    if getattr(args,"command",None) in {"update","scheduler","openclaw","uninstall"}:
        return
    try:
        result=update_tool(["check-if-due","--output","ndjson"],capture=True)
    except subprocess.TimeoutExpired:
        return
    assert isinstance(result,subprocess.CompletedProcess)
    if result.returncode!=0 or not result.stdout.strip(): return
    try: payload=json.loads(result.stdout.strip().splitlines()[-1])
    except json.JSONDecodeError: return
    if not payload.get("update_available"): return
    output=getattr(args,"output","human")
    update_event={"event":"update_available","current_version":payload.get("current_version"),"latest_version":payload.get("latest_version"),
                  "release_url":payload.get("release_url"),"release_notes":payload.get("release_notes"),
                  "user_confirmation_required":True,"auto_install":False}
    if output=="ndjson":
        emit(update_event,"ndjson")
        return
    if not sys.stdin.isatty():
        print(f"UPDATE_AVAILABLE current={payload.get('current_version')} latest={payload.get('latest_version')} confirmation_required=true")
        return
    print(f"Media2MD {payload.get('latest_version')} is available (current {payload.get('current_version')}).")
    answer=input("Download the update package now? [y/N]: ").strip().lower()
    if answer in {"y","yes"}: update_tool(["download"])

def parser() -> argparse.ArgumentParser:
    p=argparse.ArgumentParser(prog="media2md")
    sub=p.add_subparsers(dest="command",required=True)
    add_common_top_level_commands_service, add_common_update_commands_service, add_common_repair_commands_service, add_common_data_commands_service, add_common_uninstall_command_service = optional_attrs(
        "public_cli_parser_service",
        "add_common_top_level_commands",
        "add_common_update_commands",
        "add_common_repair_commands",
        "add_common_data_commands",
        "add_common_uninstall_command",
    )
    if add_common_top_level_commands_service is not None:
        add_common_top_level_commands_service(
            sub,
            version=VERSION,
            system_status=system_status,
            settings_show=settings_show,
            settings_set=settings_set,
            agent_status=agent_status,
            init_command=init_command,
            locales=LOCALES,
            core=core,
            auth=auth,
            generic=generic,
        )
    else:
        ver=sub.add_parser("version"); ver.set_defaults(func=lambda a:(print(f"media2md {VERSION}") or 0))
        status=sub.add_parser("status"); status.add_argument("--output",choices=("human","ndjson"),default="human"); status.set_defaults(func=system_status)
        settingsp=sub.add_parser("settings"); setsub=settingsp.add_subparsers(dest="settings_command",required=True)
        show=setsub.add_parser("show"); show.add_argument("--output",choices=("human","ndjson"),default="human"); show.set_defaults(func=settings_show)
        setcmd=setsub.add_parser("set"); setcmd.add_argument("--instagram-backend",choices=("auto","gallery-dl","instaloader")); setcmd.add_argument("--youtube-js-runtime",choices=("auto","deno","node","quickjs")); setcmd.add_argument("--youtube-allow-remote-ejs",action=argparse.BooleanOptionalAction); setcmd.add_argument("--youtube-po-token-provider",choices=("disabled","none","bgutil","wpc-experimental")); setcmd.add_argument("--youtube-pot-browser-path"); setcmd.add_argument("--youtube-caption-first",action=argparse.BooleanOptionalAction); setcmd.add_argument("--youtube-caption-languages"); setcmd.add_argument("--youtube-audio-strategies"); setcmd.add_argument("--youtube-long-video-threshold-minutes",type=float); setcmd.add_argument("--youtube-chunk-minutes",type=float); setcmd.add_argument("--youtube-chunk-model"); setcmd.add_argument("--tiktok-impersonate"); setcmd.add_argument("--update-check-every-days",type=float); setcmd.add_argument("--update-check-on-use",action=argparse.BooleanOptionalAction); setcmd.add_argument("--output",choices=("human","ndjson"),default="human"); setcmd.set_defaults(func=settings_set)
        agentp=sub.add_parser("agent"); agentsub=agentp.add_subparsers(dest="agent_command",required=True); ast=agentsub.add_parser("status"); ast.add_argument("--output",choices=("human","ndjson"),default="human"); ast.set_defaults(func=agent_status)
        init=sub.add_parser("init")
        init.add_argument("--language", "--ui-locale", dest="language", choices=LOCALES)
        init.add_argument("--markdown-language", "--markdown-locale", dest="markdown_language", choices=LOCALES)
        init.add_argument("--timezone")
        init.add_argument("--non-interactive", action="store_true")
        init.set_defaults(func=init_command)
        providers=sub.add_parser("providers"); providers.add_argument("args",nargs=argparse.REMAINDER); providers.set_defaults(func=lambda a:core(["providers",*a.args]))
        authp=sub.add_parser("auth"); authp.add_argument("args",nargs=argparse.REMAINDER); authp.set_defaults(func=lambda a:auth(a.args))
        media=sub.add_parser("media"); media.add_argument("args",nargs=argparse.REMAINDER); media.set_defaults(func=lambda a:generic(a.args))
    creator=sub.add_parser("creator"); cs=creator.add_subparsers(dest="creator_command",required=True)
    add=cs.add_parser("add"); add.add_argument("creator"); add.add_argument("--provider",choices=PROVIDERS,default="instagram"); add.set_defaults(func=add_creator)
    stat=cs.add_parser("status"); stat.add_argument("--provider",choices=PROVIDERS); stat.add_argument("--creator"); stat.add_argument("--output",choices=("human","ndjson"),default="human"); stat.set_defaults(func=creator_status)
    listing=cs.add_parser("list"); listing.add_argument("--provider",choices=PROVIDERS); listing.add_argument("--creator"); listing.add_argument("--output",choices=("human","ndjson"),default="human"); listing.set_defaults(func=creator_status)
    for name,enabled in (("sync-enable",True),("sync-disable",False)):
        c=cs.add_parser(name); c.add_argument("creator"); c.add_argument("--provider",choices=PROVIDERS,default="instagram"); c.add_argument("--every",type=parse_duration); c.add_argument("--full-every",type=parse_duration); c.add_argument("--quick-window",type=int); c.set_defaults(func=lambda a,e=enabled:set_policy(a,e))
    sync=cs.add_parser("sync"); sync.add_argument("creator"); sync.add_argument("--provider",choices=PROVIDERS); sync.add_argument("--force-full",action="store_true"); sync.set_defaults(func=creator_sync)
    policy=cs.add_parser("policy-set"); policy.add_argument("creator"); policy.add_argument("--provider",choices=PROVIDERS,default="instagram"); policy.add_argument("--every",type=parse_duration); policy.add_argument("--full-every",type=parse_duration); policy.add_argument("--quick-window",type=int); policy.add_argument("--mode",choices=("batch","drain")); policy.add_argument("--batch-size",type=int); policy.add_argument("--max-batches",type=int); policy.add_argument("--max-runtime-minutes",type=int); policy.add_argument("--max-failures",type=int); policy.add_argument("--stop-on-failure",action=argparse.BooleanOptionalAction); policy.add_argument("--sleep-between-batches",type=int); policy.add_argument("--scheduled-processing",action=argparse.BooleanOptionalAction); policy.add_argument("--processing-every",type=parse_duration); policy.add_argument("--since"); policy.add_argument("--until"); policy.add_argument("--rank-from",type=int); policy.add_argument("--rank-to",type=int); policy.add_argument("--order",choices=("newest_first","oldest_first")); policy.set_defaults(func=set_policy)
    pshow=cs.add_parser("policy-show"); pshow.add_argument("creator"); pshow.add_argument("--provider",choices=PROVIDERS); pshow.add_argument("--output",choices=("human","ndjson"),default="human"); pshow.set_defaults(func=policy_show)
    pgroup=cs.add_parser("policy"); psub=pgroup.add_subparsers(dest="policy_command",required=True)
    pset=psub.add_parser("set"); pset.add_argument("creator"); pset.add_argument("--provider",choices=PROVIDERS,default="instagram"); pset.add_argument("--every",type=parse_duration); pset.add_argument("--full-every",type=parse_duration); pset.add_argument("--quick-window",type=int); pset.add_argument("--mode",choices=("batch","drain")); pset.add_argument("--batch-size",type=int); pset.add_argument("--max-batches",type=int); pset.add_argument("--max-runtime-minutes",type=int); pset.add_argument("--max-failures",type=int); pset.add_argument("--stop-on-failure",action=argparse.BooleanOptionalAction); pset.add_argument("--sleep-between-batches",type=int); pset.add_argument("--scheduled-processing",action=argparse.BooleanOptionalAction); pset.add_argument("--processing-every",type=parse_duration); pset.add_argument("--since"); pset.add_argument("--until"); pset.add_argument("--rank-from",type=int); pset.add_argument("--rank-to",type=int); pset.add_argument("--order",choices=("newest_first","oldest_first")); pset.set_defaults(func=set_policy)
    pshow2=psub.add_parser("show"); pshow2.add_argument("creator"); pshow2.add_argument("--provider",choices=PROVIDERS); pshow2.add_argument("--output",choices=("human","ndjson"),default="human"); pshow2.set_defaults(func=policy_show)
    runp=cs.add_parser("run"); runp.add_argument("creator"); runp.add_argument("--provider",choices=PROVIDERS); runp.add_argument("--mode",choices=("batch","drain")); runp.add_argument("--batch-size",type=int); runp.add_argument("--max-batches",type=int); runp.add_argument("--max-runtime-minutes",type=int); runp.add_argument("--max-failures",type=int); runp.add_argument("--stop-on-failure",action="store_true"); runp.add_argument("--sleep-between-batches",type=int); runp.add_argument("--since"); runp.add_argument("--until"); runp.add_argument("--rank-from",type=int); runp.add_argument("--rank-to",type=int); runp.add_argument("--order",choices=("newest_first","oldest_first")); runp.add_argument("--allow-stale-catalog",action="store_true",help="Continue with the last saved catalog when sync fails. This is an explicit authorization."); runp.add_argument("--output",choices=("human","ndjson"),default="human"); runp.set_defaults(func=creator_run)
    delete=cs.add_parser("delete"); delete.add_argument("creator"); delete.add_argument("--provider",choices=PROVIDERS,required=True); delete.add_argument("--yes",action="store_true"); delete.set_defaults(func=lambda a:registry(["delete-creator",a.provider,a.creator]+(["--yes"] if a.yes else [])))
    scheduler=sub.add_parser("scheduler"); ss=scheduler.add_subparsers(dest="scheduler_command",required=True); tick=ss.add_parser("tick"); tick.add_argument("--output",choices=("human","ndjson"),default="human"); tick.add_argument("--non-interactive",action="store_true"); tick.set_defaults(func=scheduler_tick)
    update=sub.add_parser("update")
    if add_common_update_commands_service is not None:
        add_common_update_commands_service(update, update_tool=update_tool)
    else:
        us=update.add_subparsers(dest="update_command",required=True)
        for name in ("status","check","download","install","rollback"):
            commandp=us.add_parser(name); commandp.add_argument("--output",choices=("human","ndjson"),default="human")
            if name=="check": commandp.add_argument("--repository")
            if name in {"install","rollback"}: commandp.add_argument("--yes",action="store_true")
            if name=="install": commandp.add_argument("--non-interactive",action="store_true")
            commandp.set_defaults(func=lambda a,n=name:update_tool([n]+((["--repository",a.repository] if n=="check" and a.repository else []))+((["--yes"] if n in {"install","rollback"} and a.yes else []))+((["--non-interactive"] if n=="install" and a.non_interactive else []))+["--output",a.output]))
    doctor=sub.add_parser("doctor"); doctor.add_argument("args",nargs=argparse.REMAINDER); doctor.set_defaults(func=lambda a:run([sys.executable,str(DOCTOR),*a.args]))
    openclaw=sub.add_parser("openclaw"); openclaw.add_argument("args",nargs=argparse.REMAINDER); openclaw.set_defaults(func=lambda a:core(["openclaw",*a.args]))
    repair=sub.add_parser("repair")
    if add_common_repair_commands_service is not None:
        add_common_repair_commands_service(repair, registry=registry, repair_active_states=repair_active_states, repair_workspace=repair_workspace)
    else:
        rs=repair.add_subparsers(dest="repair_command",required=True); active=rs.add_parser("active-states"); active.add_argument("--yes",action="store_true"); active.set_defaults(func=repair_active_states)
        identity=rs.add_parser("identities"); identity.add_argument("--offline",action="store_true"); identity.set_defaults(func=lambda a:registry(["repair-identities"]+(["--offline"] if a.offline else [])))
        workspace=rs.add_parser("workspace"); workspace.add_argument("--yes",action="store_true"); workspace.set_defaults(func=repair_workspace)
    data=sub.add_parser("data")
    if add_common_data_commands_service is not None:
        add_common_data_commands_service(data, backup_script=BACKUP, run=run, data_delete_all=data_delete_all)
    else:
        ds=data.add_subparsers(dest="data_command",required=True)
        backup=ds.add_parser("backup"); backup.add_argument("--destination"); backup.add_argument("--force",action="store_true"); backup.add_argument("--wait-seconds",type=float,default=0); backup.add_argument("--output",choices=("human","ndjson"),default="human"); backup.set_defaults(func=lambda a:run([sys.executable,str(BACKUP),"backup"]+(["--destination",a.destination] if a.destination else [])+(["--force"] if a.force else [])+["--wait-seconds",str(a.wait_seconds),"--output",a.output]))
        verify=ds.add_parser("verify-backup"); verify.add_argument("path"); verify.add_argument("--output",choices=("human","ndjson"),default="human"); verify.set_defaults(func=lambda a:run([sys.executable,str(BACKUP),"verify-backup",a.path,"--output",a.output]))
        deleteall=ds.add_parser("delete-all"); deleteall.add_argument("--yes",action="store_true"); deleteall.add_argument("--confirm"); deleteall.set_defaults(func=data_delete_all)
    if add_common_uninstall_command_service is not None:
        add_common_uninstall_command_service(sub, uninstall=uninstall)
    else:
        uninstallp=sub.add_parser("uninstall"); uninstallp.add_argument("--purge-data",action="store_true"); uninstallp.add_argument("--yes",action="store_true"); uninstallp.add_argument("--confirm"); uninstallp.add_argument("--dry-run",action="store_true"); uninstallp.set_defaults(func=uninstall)
    return p


def main() -> int:
    args=parser().parse_args()
    try:
        maybe_check_update(args)
        return int(args.func(args))
    except KeyboardInterrupt:
        print("MEDIA2MD_INTERRUPTED",file=sys.stderr); return 130
    except RuntimeError as exc:
        print(f"ERROR: {exc}",file=sys.stderr); return 2

if __name__=="__main__": raise SystemExit(main())
