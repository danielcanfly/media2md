#!/usr/bin/env python3
from __future__ import annotations

import importlib.metadata
import json
import re
import subprocess
from pathlib import Path
from typing import Any

from media2md_paths import command_path

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "config" / "social2md.json"


def load_config() -> dict[str, Any]:
    try:
        return json.loads(CONFIG.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def package_version(*names: str) -> str | None:
    for name in names:
        try:
            return importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:
            continue
    return None


def _version_tuple(text: str) -> tuple[int, ...]:
    return tuple(int(item) for item in re.findall(r"\d+", text)[:3])


def _binary_version(name: str) -> dict[str, Any]:
    path = command_path(name)
    if not path:
        return {"name": name, "available": False, "path": None, "version": None}
    output = ""
    for cmd in ([path, "--version"], [path, "-v"]):
        result = subprocess.run(cmd, capture_output=True, text=True, check=False)
        output = (result.stdout or result.stderr).strip()
        if result.returncode == 0 and output:
            break
    return {"name": name, "available": True, "path": path, "version": output.splitlines()[0] if output else None}


def ejs_version() -> str | None:
    return package_version("yt-dlp-ejs", "yt_dlp_ejs")


def runtime_inventory() -> list[dict[str, Any]]:
    runtimes: list[dict[str, Any]] = []
    deno = _binary_version("deno")
    deno["supported"] = bool(deno["available"] and _version_tuple(str(deno["version"] or "0")) >= (2, 3))
    runtimes.append(deno)
    node = _binary_version("node")
    node["supported"] = bool(node["available"] and _version_tuple(str(node["version"] or "0")) >= (22,))
    runtimes.append(node)
    qjs = _binary_version("qjs")
    qjs["supported"] = bool(qjs["available"])
    runtimes.append(qjs)
    return runtimes


def selected_runtime(config: dict[str, Any] | None = None) -> dict[str, Any] | None:
    config = config or load_config()
    requested = str(config.get("providers", {}).get("youtube", {}).get("js_runtime") or "auto").lower()
    inventory = runtime_inventory()
    mapping = {"deno": "deno", "node": "node", "quickjs": "qjs", "qjs": "qjs"}
    if requested != "auto":
        binary = mapping.get(requested)
        item = next((entry for entry in inventory if entry["name"] == binary), None) if binary else None
        if item and item.get("supported"):
            return {**item, "runtime": "quickjs" if binary == "qjs" else binary, "requested": requested}
        return None
    for binary, runtime in (("deno", "deno"), ("node", "node"), ("qjs", "quickjs")):
        item = next((entry for entry in inventory if entry["name"] == binary), None)
        if item and item.get("supported"):
            return {**item, "runtime": runtime, "requested": "auto"}
    return None


def youtube_runtime_args(config: dict[str, Any] | None = None) -> list[str]:
    config = config or load_config()
    selected = selected_runtime(config)
    args: list[str] = []
    if selected:
        runtime = selected["runtime"]
        path = selected.get("path")
        args += ["--js-runtimes", f"{runtime}:{path}" if path else runtime]
    youtube = config.get("providers", {}).get("youtube", {})
    if bool(youtube.get("allow_remote_ejs", False)) and not ejs_version():
        args += ["--remote-components", "ejs:github"]
    return args


def impersonation_targets() -> dict[str, Any]:
    yt = _binary_version("yt-dlp")
    curl_version = package_version("curl-cffi", "curl_cffi")
    targets: list[str] = []
    raw = ""
    if yt["available"]:
        result = subprocess.run([str(yt["path"]), "--list-impersonate-targets"], capture_output=True, text=True, check=False)
        raw = (result.stdout or result.stderr).strip()
        if result.returncode == 0:
            for line in raw.splitlines():
                match = re.match(r"\s*((?:chrome|edge|safari)[A-Za-z0-9_.:-]*)\b", line, re.I)
                if match:
                    value = match.group(1)
                    if value.lower() not in {item.lower() for item in targets}:
                        targets.append(value)
    preferred = "chrome" if any(item.lower().startswith("chrome") for item in targets) else (targets[0] if targets else None)
    return {
        "curl_cffi_version": curl_version,
        "targets": targets,
        "preferred_target": preferred,
        "ready": bool(curl_version and targets),
        "raw": raw[-3000:],
    }


def selected_impersonation_target(provider: str, config: dict[str, Any] | None = None) -> str | None:
    config = config or load_config()
    requested = config.get("providers", {}).get(provider, {}).get("impersonate", "auto")
    if requested in (False, None, "false", "off", "none"):
        return None
    inventory = impersonation_targets()
    if not inventory["ready"]:
        return None
    if str(requested).lower() == "auto":
        return str(inventory["preferred_target"] or "chrome")
    return str(requested)


def impersonation_args(provider: str, config: dict[str, Any] | None = None) -> list[str]:
    target = selected_impersonation_target(provider, config)
    return ["--impersonate", target] if target else []


def po_token_providers() -> dict[str, Any]:
    wpc = package_version("yt-dlp-getpot-wpc", "yt_dlp_getpot_wpc")
    bgutil = package_version("bgutil-ytdlp-pot-provider", "bgutil_ytdlp_pot_provider")
    chrome = command_path("google-chrome") or command_path("chromium") or command_path("chromium-browser")
    mac_chrome = Path("/Applications/Google Chrome.app/Contents/MacOS/Google Chrome")
    if not chrome and mac_chrome.is_file():
        chrome = str(mac_chrome)
    return {
        "wpc_version": wpc,
        "bgutil_version": bgutil,
        "chrome_path": chrome,
        "ready": bool((wpc and chrome) or bgutil),
        "preferred": "wpc" if wpc and chrome else "bgutil" if bgutil else None,
    }


def youtube_access_args(config: dict[str, Any] | None = None, *, allow_browser_launch: bool = False) -> list[str]:
    """Return YouTube args without launching a GUI browser.

    Browser-based PO-token providers are quarantined in v0.7.1. Normal Doctor,
    Batch, Drain, Agent, and Scheduler code paths always call this with the
    default ``allow_browser_launch=False``. Even when WPC is installed or an
    older config says ``auto``/``wpc``, it is not activated.
    """
    config = config or load_config()
    args = youtube_runtime_args(config)
    youtube = config.get("providers", {}).get("youtube", {})
    requested = str(youtube.get("po_token_provider") or "disabled").lower()
    providers = po_token_providers()

    # Non-GUI bgutil may be used only when explicitly selected and installed.
    if requested == "bgutil" and providers.get("bgutil_version"):
        args += ["--extractor-args", "youtube:player_client=mweb"]
        mode = str(youtube.get("bgutil_mode") or "http")
        if mode == "script":
            server_home = str(youtube.get("bgutil_server_home") or "").strip()
            if server_home:
                args += ["--extractor-args", f"youtubepot-bgutilscript:server_home={server_home}"]
        else:
            base_url = str(youtube.get("bgutil_base_url") or "http://127.0.0.1:4416")
            args += ["--extractor-args", f"youtubepot-bgutilhttp:base_url={base_url}"]

    # WPC/nodriver is deliberately never activated here. ``allow_browser_launch``
    # exists only to make the safety boundary explicit to callers and tests.
    # A future audited expert command may implement a one-shot browser flow.
    _ = allow_browser_launch
    return args



DEFAULT_YOUTUBE_AUDIO_STRATEGIES = [
    "anonymous_default",
    "anonymous_default_ejs",
    "anonymous_web_safari_hls",
    "anonymous_android_vr",
    "authenticated_default",
    "authenticated_web_safari_hls",
    "configured_non_browser_pot",
]


def youtube_audio_settings(config: dict[str, Any] | None = None) -> dict[str, Any]:
    config = config or load_config()
    youtube = config.get("providers", {}).get("youtube", {})
    raw_strategies = youtube.get("audio_download_strategies", DEFAULT_YOUTUBE_AUDIO_STRATEGIES)
    if isinstance(raw_strategies, str):
        strategies = [item.strip() for item in raw_strategies.split(",") if item.strip()]
    elif isinstance(raw_strategies, list):
        strategies = [str(item).strip() for item in raw_strategies if str(item).strip()]
    else:
        strategies = list(DEFAULT_YOUTUBE_AUDIO_STRATEGIES)
    return {
        "audio_download_strategies": strategies or list(DEFAULT_YOUTUBE_AUDIO_STRATEGIES),
        "audio_format": str(youtube.get("audio_format") or "mp3").lower(),
        "long_video_threshold_seconds": max(60, int(youtube.get("long_video_threshold_seconds") or 2700)),
        "chunk_seconds": max(60, int(youtube.get("chunk_seconds") or 1800)),
        "chunk_model": str(youtube.get("chunk_model") or "mlx-community/whisper-large-v3-turbo"),
    }


def provider_transcription_settings(provider: str, config: dict[str, Any] | None = None) -> dict[str, Any]:
    config = config or load_config()
    chosen = str(provider or "").strip().lower()
    if chosen == "youtube":
        settings = youtube_audio_settings(config)
        settings["caption_first"] = bool(config.get("providers", {}).get("youtube", {}).get("caption_first", True))
        return settings
    if chosen == "bilibili":
        bilibili = config.get("providers", {}).get("bilibili", {})
        return {
            "caption_first": bool(bilibili.get("caption_first", True)),
            "long_video_threshold_seconds": max(60, int(bilibili.get("long_video_threshold_seconds") or 2700)),
            "chunk_seconds": max(60, int(bilibili.get("chunk_seconds") or 1800)),
            "chunk_model": str(bilibili.get("chunk_model") or "mlx-community/whisper-large-v3-turbo"),
        }
    return {
        "caption_first": True,
        "long_video_threshold_seconds": 2700,
        "chunk_seconds": 1800,
        "chunk_model": "mlx-community/whisper-large-v3-turbo",
    }


def youtube_download_strategies(
    auth_args: list[str] | None = None,
    config: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """Build a browser-safe YouTube audio download cascade.

    Public, logged-out attempts come first. This intentionally mirrors the
    simplest successful yt-dlp workflow used by the user's reference project
    and avoids forcing authenticated clients into PO-token enforcement. The
    explicit Chrome profile is used only after the anonymous strategies fail.
    """
    config = config or load_config()
    auth_args = list(auth_args or [])
    settings = youtube_audio_settings(config)
    runtime = youtube_runtime_args(config)
    configured_access = youtube_access_args(config, allow_browser_launch=False)
    catalogue: dict[str, dict[str, Any]] = {
        "anonymous_default": {
            "name": "anonymous_default",
            "args": [],
            "auth_args": [],
            "format": "ba/b",
            "uses_auth": False,
            "client": "default",
        },
        "anonymous_default_ejs": {
            "name": "anonymous_default_ejs",
            "args": list(runtime),
            "auth_args": [],
            "format": "ba/b",
            "uses_auth": False,
            "client": "default+ejs",
        },
        "anonymous_web_safari_hls": {
            "name": "anonymous_web_safari_hls",
            "args": [*runtime, "--extractor-args", "youtube:player_client=web_safari"],
            "auth_args": [],
            "format": "b[protocol^=m3u8]/ba/b",
            "uses_auth": False,
            "client": "web_safari",
        },
        "anonymous_android_vr": {
            "name": "anonymous_android_vr",
            "args": [*runtime, "--extractor-args", "youtube:player_client=android_vr,default"],
            "auth_args": [],
            "format": "ba/b",
            "uses_auth": False,
            "client": "android_vr,default",
        },
        "authenticated_default": {
            "name": "authenticated_default",
            "args": list(runtime),
            "auth_args": list(auth_args),
            "format": "ba/b",
            "uses_auth": True,
            "client": "default",
        },
        "authenticated_web_safari_hls": {
            "name": "authenticated_web_safari_hls",
            "args": [*runtime, "--extractor-args", "youtube:player_client=web_safari"],
            "auth_args": list(auth_args),
            "format": "b[protocol^=m3u8]/ba/b",
            "uses_auth": True,
            "client": "web_safari",
        },
        "configured_non_browser_pot": {
            "name": "configured_non_browser_pot",
            "args": list(configured_access),
            "auth_args": list(auth_args),
            "format": "ba/b",
            "uses_auth": bool(auth_args),
            "client": "configured",
        },
    }
    results: list[dict[str, Any]] = []
    seen: set[tuple[tuple[str, ...], tuple[str, ...], str]] = set()
    for name in settings["audio_download_strategies"]:
        item = catalogue.get(name)
        if not item:
            continue
        if item["uses_auth"] and not auth_args:
            continue
        # Do not duplicate configured_non_browser_pot when it is identical to
        # the ordinary authenticated or anonymous default strategy.
        signature = (tuple(item["args"]), tuple(item["auth_args"]), str(item["format"]))
        if signature in seen:
            continue
        seen.add(signature)
        results.append(item)
    return results

def browser_safety_payload(config: dict[str, Any] | None = None) -> dict[str, Any]:
    config = config or load_config()
    youtube = config.get("providers", {}).get("youtube", {})
    providers = po_token_providers()
    requested = str(youtube.get("po_token_provider") or "disabled").lower()
    return {
        "browser_launch_policy": "never",
        "browser_launch_allowed": False,
        "browser_launch_attempts_max": 0,
        "wpc_installed": bool(providers.get("wpc_version")),
        "wpc_quarantined": True,
        "configured_po_token_provider": requested,
        "normal_commands_may_launch_browser": False,
        "affected_commands": ["doctor youtube-access", "creator run", "scheduler tick"],
    }


def classify_access_error(provider: str, text: str) -> dict[str, Any]:
    lower = text.lower()
    transient = any(token in lower for token in (
        "read timed out", "timed out", "timeout", "connection reset", "connection aborted",
        "temporarily unavailable", "remote disconnected", "http error 429", "too many requests",
        "http error 500", "http error 502", "http error 503", "http error 504",
        "curl: (35)", "curl error 35", "tls connect error", "tls handshake", "sslerror",
        "openssl_internal", "ssl connect error", "connection closed during tls",
    ))
    if transient:
        return RequiredActionResult("transient_network_error", True, False, None).as_dict()
    if provider == "tiktok" and ("no impersonate target" in lower or "impersonation" in lower and "available" in lower):
        return RequiredActionResult("impersonation_unavailable", False, True, validate_required_action("install_impersonation")).as_dict()
    if "403" in lower or "forbidden" in lower:
        if provider == "youtube":
            return RequiredActionResult("youtube_po_token_required", False, True, validate_required_action("verify_youtube_session_or_configure_non_browser_access")).as_dict()
        if provider == "tiktok":
            inventory = impersonation_targets()
            action = "refresh_tiktok_cookies" if inventory.get("ready") else "install_impersonation"
            code = "platform_access_denied" if inventory.get("ready") else "impersonation_unavailable"
            return RequiredActionResult(code, False, True, validate_required_action(action)).as_dict()
    return RequiredActionResult("extractor_error", True, False, None).as_dict()


def doctor_payload() -> dict[str, Any]:
    config = load_config()
    inventory = runtime_inventory()
    selected = selected_runtime(config)
    ejs = ejs_version()
    yt = _binary_version("yt-dlp")
    ffmpeg = _binary_version("ffmpeg")
    ffprobe = _binary_version("ffprobe")
    ready = bool(yt["available"] and ffmpeg["available"] and selected and ejs)
    remediation: list[str] = []
    if not yt["available"] or not ejs:
        remediation.append("Install the YouTube extra with: python -m pip install -U '.[youtube]'")
    if not selected:
        remediation.append("Install Deno >=2.3 or Node >=22.")
    if not ffmpeg["available"]:
        remediation.append("Install FFmpeg and ensure ffmpeg is available on PATH.")
    return {
        "event": "youtube_doctor", "ready": ready, "yt_dlp": yt, "ffmpeg": ffmpeg, "ffprobe": ffprobe,
        "ejs_version": ejs, "runtime_inventory": inventory, "selected_runtime": selected,
        "runtime_args": youtube_runtime_args(config), "pot_providers": po_token_providers(), "browser_safety": browser_safety_payload(config), "remediation": remediation,
    }
try:
    from media2md.required_actions import validate_required_action
    from media2md.results import RequiredActionResult
except ModuleNotFoundError:
    from media2md_contract_compat import validate_required_action
    from media2md_results_compat import RequiredActionResult
