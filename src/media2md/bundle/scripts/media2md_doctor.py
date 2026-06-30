#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import re
import signal
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

from media2md.cli_output_service import make_output_model, make_section
from media2md.health_taxonomy import health_category, normalize_health_status, summarize_health
from media2md.remediation_service import media2md_install_guidance, provider_access_guidance
from media2md.results import HealthResult
from media2md.probe import probe_command
from media2md_paths import command_path
from media2md_ytdlp import (
    classify_access_error, doctor_payload as youtube_environment_payload,
    browser_safety_payload, impersonation_args, impersonation_targets, po_token_providers, youtube_access_args,
    youtube_audio_settings, youtube_download_strategies,
)
from media2md_youtube_session import configured_youtube_profile, youtube_auth_args, verify_youtube_session
from media2md_runtime import safe_artifact_stem

ROOT = Path(__file__).resolve().parents[1]
AUTH_PROFILES = ROOT / "config" / "auth_profiles.json"
INSTALOADER = ROOT / "scripts" / "instagram_instaloader.py"


def command(name: str) -> str | None:
    return command_path(name)


def _command_ready(name: str, *, package: str | None = None) -> tuple[bool, dict[str, Any]]:
    probe = probe_command(name, package=package or name)
    return probe.ok, {
        "status": probe.status,
        "category": health_category(probe.status),
        "output": probe.output or None,
        "hint": probe.hint or None,
    }


def _attach_health(payload: dict[str, Any], *, status: str | None, message: str | None = None) -> dict[str, Any]:
    normalized = normalize_health_status(status)
    payload["health_status"] = normalized
    payload["health_category"] = health_category(normalized)
    if message is not None and "health_message" not in payload:
        payload["health_message"] = message
    return payload


def _summarize_command_probes(probes: list[dict[str, Any]]) -> dict[str, object]:
    results = [
        HealthResult(
            status=normalize_health_status(item.get("status")),
            message=str(item.get("hint") or item.get("output") or item.get("status") or ""),
        )
        for item in probes
    ]
    return summarize_health(results)


def auth_args(provider: str) -> list[str]:
    if provider == "youtube":
        return youtube_auth_args()
    try:
        profiles = json.loads(AUTH_PROFILES.read_text(encoding="utf-8")).get("providers", {})
    except Exception:
        profiles = {}
    profile = profiles.get(provider, {})
    cookie_file = profile.get("cookie_file")
    if cookie_file and Path(cookie_file).expanduser().is_file():
        return ["--cookies", str(Path(cookie_file).expanduser())]
    return []


def _run(cmd: list[str], timeout: int) -> subprocess.CompletedProcess[str]:
    process = subprocess.Popen(cmd, cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, start_new_session=True)
    try:
        stdout, stderr = process.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        try: os.killpg(process.pid, signal.SIGTERM)
        except ProcessLookupError: pass
        try: process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            try: os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError: pass
        stdout, stderr = process.communicate()
        return subprocess.CompletedProcess(cmd, 124, stdout, (stderr or "") + f"\nTimed out after {timeout} seconds")
    return subprocess.CompletedProcess(cmd, process.returncode, stdout, stderr)


def instagram_payload(shortcode: str | None) -> dict[str, Any]:
    gallery = command("gallery-dl")
    instaloader = command("instaloader")
    gallery_ready, gallery_probe = _command_ready("gallery-dl")
    instaloader_ready, instaloader_probe = _command_ready("instaloader")
    cookie = ROOT / "data" / "secrets" / "instagram-cookies.txt"
    payload: dict[str, Any] = {
        "event": "instagram_backends_doctor", "gallery_dl_available": bool(gallery),
        "instaloader_available": bool(instaloader), "cookie_file": str(cookie),
        "cookie_file_exists": cookie.is_file(), "probe_shortcode": shortcode,
        "gallery_dl_probe": None, "instaloader_probe": None,
        "gallery_dl_command_probe": gallery_probe,
        "instaloader_command_probe": instaloader_probe,
    }
    if shortcode:
        url = f"https://www.instagram.com/reel/{shortcode}/"
        if gallery:
            cmd = [gallery]
            if cookie.is_file(): cmd += ["--cookies", str(cookie)]
            result = _run([*cmd, "--resolve-json", url], 300)
            payload["gallery_dl_probe"] = {"ok": result.returncode == 0 and bool(result.stdout.strip()), "error": (result.stderr or result.stdout)[-1000:] if result.returncode else None}
        if INSTALOADER.is_file():
            result = _run([sys.executable, str(INSTALOADER), "inspect", shortcode], 300)
            payload["instaloader_probe"] = {"ok": result.returncode == 0, "error": (result.stderr or result.stdout)[-1000:] if result.returncode else None}
    payload["ready"] = bool(gallery_ready and instaloader_ready and payload["cookie_file_exists"])
    payload["dependency_health"] = _summarize_command_probes([gallery_probe, instaloader_probe])
    _attach_health(payload, status="ok" if payload["ready"] else payload["dependency_health"]["status"], message="Instagram backend doctor status")
    return payload


def impersonation_payload() -> dict[str, Any]:
    inventory = impersonation_targets()
    payload = {
        "event": "impersonation_doctor", "ready": bool(inventory["ready"]),
        "curl_cffi_version": inventory["curl_cffi_version"], "targets": inventory["targets"],
        "preferred_target": inventory["preferred_target"],
        "remediation": [] if inventory["ready"] else [media2md_install_guidance("youtube", "tiktok")],
    }
    _attach_health(
        payload,
        status="ok" if payload["ready"] else "warn",
        message="Impersonation target availability",
    )
    return payload


def _youtube_caption_probe(yt: str, base: list[str], url: str) -> dict[str, Any]:
    with tempfile.TemporaryDirectory(prefix="media2md-youtube-captions-") as temp:
        output = str(Path(temp) / "%(id)s.%(language)s.%(ext)s")
        result = _run([
            yt, *base, "--skip-download", "--write-subs", "--write-auto-subs",
            "--sub-format", "vtt", "--sub-langs", "zh-Hant,zh-Hans,zh,en.*",
            "--no-playlist", "--no-progress", "-o", output, url,
        ], 300)
        files = [path for path in Path(temp).glob("*.vtt") if path.is_file() and path.stat().st_size > 0]
        return {
            "caption_ready": bool(files),
            "caption_files": [path.name for path in files],
            "caption_probe_error": None if result.returncode == 0 else (result.stderr or result.stdout or "caption probe failed")[-2000:],
        }


def _model_cached(model: str) -> bool:
    cache_name = "models--" + model.replace("/", "--")
    roots = [
        Path.home() / ".cache" / "huggingface" / "hub" / cache_name,
        Path(os.environ.get("HF_HOME", "")) / "hub" / cache_name if os.environ.get("HF_HOME") else None,
    ]
    return any(root and root.is_dir() for root in roots)


def _transcription_probe(whisper: str | None, ffmpeg: str | None, *, smoke_test: bool) -> dict[str, Any]:
    settings = youtube_audio_settings()
    model = str(settings.get("chunk_model") or "mlx-community/whisper-large-v3-turbo")
    payload: dict[str, Any] = {
        "transcription_binary_ready": bool(whisper),
        "transcription_cli_ready": False,
        "transcription_model": model,
        "transcription_model_cached": _model_cached(model),
        "transcription_smoke_tested": False,
        "transcription_smoke_ready": False,
        "transcription_smoke_error": None,
        "artifact_name_probe": safe_artifact_stem("youtube", "-AHFhntQ07k"),
    }
    if not whisper:
        payload["transcription_smoke_error"] = "mlx_whisper is not installed"
        return payload
    cli = _run([whisper, "--help"], 60)
    payload["transcription_cli_ready"] = cli.returncode == 0
    if cli.returncode != 0:
        payload["transcription_smoke_error"] = (cli.stderr or cli.stdout or "mlx_whisper --help failed")[-2000:]
        return payload
    if not smoke_test:
        return payload
    payload["transcription_smoke_tested"] = True
    if not ffmpeg:
        payload["transcription_smoke_error"] = "ffmpeg is not installed"
        return payload
    with tempfile.TemporaryDirectory(prefix="media2md-whisper-smoke-") as temp:
        root = Path(temp)
        audio = root / "one-second-silence.wav"
        generated = _run([
            ffmpeg, "-v", "error", "-f", "lavfi", "-i", "anullsrc=r=16000:cl=mono",
            "-t", "1", str(audio),
        ], 60)
        if generated.returncode != 0:
            payload["transcription_smoke_error"] = (generated.stderr or generated.stdout or "ffmpeg smoke fixture failed")[-2000:]
            return payload
        name = payload["artifact_name_probe"]
        result = _run([
            whisper, str(audio), "--model", model, "--output-dir", str(root),
            f"--output-name={name}", "--output-format", "txt", "--task", "transcribe",
        ], 7200)
        transcript = root / f"{name}.txt"
        payload["transcription_smoke_ready"] = result.returncode == 0 and transcript.is_file()
        if not payload["transcription_smoke_ready"]:
            payload["transcription_smoke_error"] = (result.stderr or result.stdout or "Whisper smoke test did not create output")[-3000:]
    return payload


def _access_probe(provider: str, url: str, *, transcription_smoke_test: bool = False) -> dict[str, Any]:
    yt = command("yt-dlp")
    ffmpeg = command("ffmpeg")
    whisper = command("mlx_whisper")
    yt_ready, yt_probe = _command_ready("yt-dlp", package="yt-dlp")
    ffmpeg_ready, ffmpeg_probe = _command_ready("ffmpeg", package="ffmpeg")
    whisper_ready, whisper_probe = _command_ready("mlx_whisper", package="mlx-whisper")
    base: list[str] = []
    if provider == "youtube":
        # Public metadata/captions first. Auth is considered only inside the
        # authenticated strategy branch after strict session preflight.
        base += youtube_access_args(allow_browser_launch=False)
    elif provider == "tiktok":
        base += impersonation_args("tiktok")
        base += auth_args(provider)
    selected_auth = configured_youtube_profile() if provider == "youtube" else {}
    transcription = _transcription_probe(whisper, ffmpeg, smoke_test=transcription_smoke_test)
    payload: dict[str, Any] = {
        "event": f"{provider}_access_doctor", "provider": provider, "url": url,
        "metadata_ready": False, "caption_ready": False, "caption_files": [],
        "audio_download_ready": False, "audio_download_strategy": None,
        "audio_strategy_results": [], "download_ready": False,
        "ffmpeg_ready": bool(ffmpeg), "pipeline_strategy": None,
        "pipeline_ready": False, "pipeline_readiness": "not_ready",
        "pipeline_end_to_end_verified": False, "fully_ready": False,
        "error": None, "error_code": None, "retryable": None,
        "action_required": False, "required_action": None,
        "args": base, "browser_launch_allowed": False, "browser_launch_attempts": 0,
        "browser_safety": browser_safety_payload(),
        "yt_dlp_command_probe": yt_probe,
        "ffmpeg_command_probe": ffmpeg_probe,
        "mlx_whisper_command_probe": whisper_probe,
        "auth_mode": selected_auth.get("mode") if provider == "youtube" else None,
        "auth_browser": selected_auth.get("browser") if provider == "youtube" else None,
        "auth_profile": selected_auth.get("profile") if provider == "youtube" else None,
        **transcription,
    }
    payload["transcription_ready"] = bool(payload["transcription_cli_ready"])
    payload["ffmpeg_ready_probe"] = bool(ffmpeg_ready)
    payload["transcription_binary_ready_probe"] = bool(whisper_ready)
    if not yt_ready:
        payload.update(error="yt-dlp is not installed", error_code="missing_dependency", retryable=False, action_required=True, required_action="install_provider_extra")
        payload["guidance"] = provider_access_guidance(provider, error_code="missing_dependency", required_action="install_provider_extra")
        payload["dependency_health"] = _summarize_command_probes([yt_probe, ffmpeg_probe, whisper_probe])
        _attach_health(payload, status="warn", message=payload["error"])
        return payload
    if provider == "tiktok" and not impersonation_args("tiktok"):
        payload.update(error="No browser impersonation target is available.", error_code="impersonation_unavailable", retryable=False, action_required=True, required_action="install_impersonation")
        payload["guidance"] = provider_access_guidance(provider, error_code="impersonation_unavailable", required_action="install_impersonation")
        payload["dependency_health"] = _summarize_command_probes([yt_probe, ffmpeg_probe, whisper_probe])
        _attach_health(payload, status="warn", message=payload["error"])
        return payload
    payload["dependency_health"] = _summarize_command_probes([yt_probe, ffmpeg_probe, whisper_probe])
    metadata = _run([yt, *base, "--dump-single-json", "--skip-download", "--no-playlist", url], 300)
    payload["metadata_used_auth"] = False
    auth_preflight: dict[str, Any] | None = None
    if metadata.returncode != 0 and provider == "youtube" and auth_args("youtube"):
        auth_preflight = verify_youtube_session(persist=False)
        payload["auth_preflight"] = {
            "authenticated": bool(auth_preflight.get("authenticated")),
            "auth_state": auth_preflight.get("auth_state"),
            "required_action": auth_preflight.get("required_action"),
            "guidance": auth_preflight.get("guidance", []),
        }
        if auth_preflight.get("authenticated"):
            metadata = _run([
                yt, *base, *auth_args("youtube"), "--dump-single-json",
                "--skip-download", "--no-playlist", url,
            ], 300)
            payload["metadata_used_auth"] = metadata.returncode == 0
    if metadata.returncode != 0:
        error = (metadata.stderr or metadata.stdout or "metadata probe failed")[-4000:]
        payload.update(error=error, **classify_access_error(provider, error))
        if auth_preflight is not None and not auth_preflight.get("authenticated"):
            payload.update(
                error_code="youtube_session_unavailable", retryable=False,
                action_required=True,
                required_action=auth_preflight.get("required_action") or "verify_or_reauthenticate_youtube_session",
                auth_state=auth_preflight.get("auth_state"),
                guidance=auth_preflight.get("guidance", []),
            )
        else:
            payload["guidance"] = provider_access_guidance(
                provider,
                error_code=str(payload.get("error_code") or ""),
                required_action=payload.get("required_action"),
            )
        _attach_health(payload, status=payload.get("error_code") == "youtube_session_unavailable" and "warn" or "error", message=payload["error"])
        return payload
    payload["metadata_ready"] = True
    try:
        metadata_payload: dict[str, Any] = json.loads(metadata.stdout or "{}")
    except json.JSONDecodeError:
        metadata_payload = {}
    payload["duration_seconds"] = metadata_payload.get("duration")
    if provider == "youtube":
        payload.update(_youtube_caption_probe(yt, base, url))
        if payload["caption_ready"]:
            payload["pipeline_strategy"] = "youtube_captions"
            payload["download_ready"] = True
            payload["pipeline_ready"] = True
            payload["pipeline_readiness"] = "verified_caption_path"
            payload["pipeline_end_to_end_verified"] = True
            payload["fully_ready"] = True
            return payload

        results: list[dict[str, Any]] = []
        successful: dict[str, Any] | None = None
        for strategy in youtube_download_strategies(auth_args("youtube")):
            if strategy["uses_auth"]:
                if auth_preflight is None:
                    auth_preflight = verify_youtube_session(persist=False)
                if not auth_preflight.get("authenticated"):
                    results.append({
                        "strategy": strategy["name"], "client": strategy["client"],
                        "uses_auth": True, "ok": False,
                        "skipped": True, "auth_state": auth_preflight.get("auth_state"),
                        "error": f"authenticated fallback blocked: {auth_preflight.get('required_action')}",
                    })
                    continue
            with tempfile.TemporaryDirectory(prefix="media2md-youtube-probe-") as temp:
                output = str(Path(temp) / "%id.%(ext)s").replace("%id", "%(id)s")
                probe = _run([
                    yt, *strategy["args"], *strategy["auth_args"], "--test",
                    "--no-playlist", "--no-progress", "-f", str(strategy["format"]),
                    "-x", "--audio-format", "mp3", "-o", output, url,
                ], 600)
                item = {
                    "strategy": strategy["name"], "client": strategy["client"],
                    "uses_auth": bool(strategy["uses_auth"]), "ok": probe.returncode == 0,
                    "error": None if probe.returncode == 0 else (probe.stderr or probe.stdout or "download probe failed")[-2000:],
                }
                results.append(item)
                if item["ok"]:
                    successful = strategy
                    break
        payload["audio_strategy_results"] = results
        if not successful:
            error = "; ".join(f"{item['strategy']}={item['error']}" for item in results) or "No YouTube audio strategy was available"
            payload.update(error=error, **classify_access_error(provider, error))
            payload["guidance"] = provider_access_guidance(
                provider,
                error_code=str(payload.get("error_code") or ""),
                required_action=payload.get("required_action"),
            )
            _attach_health(payload, status="error", message=payload["error"])
            return payload
        payload["audio_download_ready"] = True
        payload["audio_download_strategy"] = successful["name"]
        payload["audio_used_auth"] = bool(successful["uses_auth"])
        payload["download_ready"] = True
        settings = youtube_audio_settings()
        duration = float(payload.get("duration_seconds") or 0)
        payload["long_video_threshold_seconds"] = settings["long_video_threshold_seconds"]
        payload["chunk_seconds"] = settings["chunk_seconds"]
        payload["pipeline_strategy"] = (
            "local_whisper_chunked" if duration >= float(settings["long_video_threshold_seconds"])
            else "local_whisper"
        )
    else:
        with tempfile.TemporaryDirectory(prefix=f"media2md-{provider}-probe-") as temp:
            output = str(Path(temp) / "%(id)s.%(ext)s")
            probe = _run([yt, *base, "--test", "--no-playlist", "--no-progress", "-f", "ba/b", "-o", output, url], 600)
            if probe.returncode != 0:
                error = (probe.stderr or probe.stdout or "download probe failed")[-4000:]
                payload.update(error=error, **classify_access_error(provider, error))
                payload["guidance"] = provider_access_guidance(
                    provider,
                    error_code=str(payload.get("error_code") or ""),
                    required_action=payload.get("required_action"),
                )
                _attach_health(payload, status="error", message=payload["error"])
                return payload
            payload["audio_download_ready"] = True
            payload["download_ready"] = True
            payload["pipeline_strategy"] = "local_whisper"
    payload["pipeline_ready"] = bool(
        payload["metadata_ready"] and payload["audio_download_ready"]
        and payload["transcription_cli_ready"] and payload["ffmpeg_ready"]
    )
    if payload["pipeline_ready"]:
        if payload["transcription_smoke_tested"] and payload["transcription_smoke_ready"]:
            payload["pipeline_readiness"] = "verified_with_local_transcription_smoke_test"
            payload["pipeline_end_to_end_verified"] = True
            payload["fully_ready"] = True
        else:
            payload["pipeline_readiness"] = "probable_not_end_to_end_verified"
            payload["pipeline_end_to_end_verified"] = False
            payload["fully_ready"] = False
            payload["verification_note"] = "Run again with --transcription-smoke-test for a strong local transcription check."
    _attach_health(
        payload,
        status="ok" if payload.get("fully_ready") else "warn" if payload.get("pipeline_ready") else "error",
        message=payload.get("error") or payload.get("verification_note") or "Access doctor status",
    )
    return payload


def youtube_access_payload(video_id: str, *, transcription_smoke_test: bool = False) -> dict[str, Any]:
    if not re.fullmatch(r"[A-Za-z0-9_-]{11}", video_id):
        payload = {"event": "youtube_access_doctor", "provider": "youtube", "pipeline_ready": False, "fully_ready": False, "error_code": "invalid_video_id", "error": f"Invalid YouTube video ID: {video_id}", "retryable": False, "action_required": True, "required_action": "provide_valid_video_id"}
        return _attach_health(payload, status="warn", message=payload["error"])
    payload = _access_probe("youtube", f"https://www.youtube.com/watch?v={video_id}", transcription_smoke_test=transcription_smoke_test)
    payload["po_token_providers"] = po_token_providers()
    payload["browser_safety"] = browser_safety_payload()
    return payload

def tiktok_access_payload(video_id: str, creator: str, *, transcription_smoke_test: bool = False) -> dict[str, Any]:
    if not re.fullmatch(r"\d{8,24}", video_id):
        payload = {"event": "tiktok_access_doctor", "provider": "tiktok", "pipeline_ready": False, "fully_ready": False, "error_code": "invalid_video_id", "error": f"Invalid TikTok video ID: {video_id}", "retryable": False, "action_required": True, "required_action": "provide_valid_video_id"}
        return _attach_health(payload, status="warn", message=payload["error"])
    handle = creator.strip().lstrip("@")
    url = f"https://www.tiktok.com/@{handle}/video/{video_id}"
    payload = _access_probe("tiktok", url, transcription_smoke_test=transcription_smoke_test)
    if payload.get("pipeline_ready"):
        payload["live_probe_ready"] = True
        payload["degraded"] = False
        _attach_health(payload, status="ok", message=payload.get("health_message"))
        return payload

    # The simple Doctor route can hit a transient curl-cffi/TLS failure even
    # when the real processing cascade succeeds. Reuse the production metadata
    # and download paths before declaring the provider unavailable.
    from generic_media import download_tiktok_audio, inspect_tiktok_metadata, tiktok_recent_completion

    live_error = payload.get("error")
    try:
        metadata = inspect_tiktok_metadata(url, handle, video_id)
    except Exception as exc:
        payload["metadata_fallback_error"] = str(exc)[-3000:]
        metadata = None
    if metadata:
        payload["metadata_ready"] = True
        payload["duration_seconds"] = metadata.get("duration")
        payload["metadata_source"] = metadata.get("_media2md_metadata_source", "yt-dlp-live-cascade")

    shared_download_error: str | None = None
    if metadata:
        try:
            with tempfile.TemporaryDirectory(prefix="media2md-tiktok-doctor-") as temp:
                work = Path(temp)
                template = str(work / "%(id)s.%(ext)s")
                media, strategy, used_auth, attempts = download_tiktok_audio(
                    url, work, video_id, handle, template,
                )
                payload["audio_download_ready"] = media.is_file()
                payload["audio_download_strategy"] = strategy
                payload["audio_used_auth"] = used_auth
                payload["audio_strategy_results"] = attempts
        except Exception as exc:
            shared_download_error = str(exc)
            payload["shared_download_error"] = shared_download_error[-3000:]

    if payload.get("metadata_ready") and payload.get("audio_download_ready"):
        payload["download_ready"] = True
        payload["pipeline_strategy"] = "local_whisper"
        payload["pipeline_ready"] = bool(
            payload.get("transcription_cli_ready") and payload.get("ffmpeg_ready")
        )
        payload["pipeline_readiness"] = (
            "verified_with_shared_processing_cascade_and_local_transcription_smoke_test"
            if payload.get("transcription_smoke_tested") and payload.get("transcription_smoke_ready")
            else "verified_with_shared_processing_cascade"
        )
        payload["pipeline_end_to_end_verified"] = bool(payload["pipeline_ready"])
        payload["fully_ready"] = bool(payload["pipeline_ready"])
        payload["live_probe_ready"] = bool(payload["pipeline_ready"])
        payload["degraded"] = False
        payload["error"] = None
        payload["error_code"] = None
        payload["retryable"] = None
        _attach_health(payload, status="ok", message="TikTok shared processing cascade is ready")
        return payload

    recent = tiktok_recent_completion(video_id)
    if recent and payload.get("metadata_ready"):
        payload["recent_completed_artifact"] = recent
        payload["download_ready"] = True
        payload["pipeline_strategy"] = "local_whisper"
        payload["pipeline_ready"] = bool(
            payload.get("transcription_cli_ready") and payload.get("ffmpeg_ready")
        )
        payload["pipeline_readiness"] = "verified_by_recent_completed_artifact_degraded_live_probe"
        payload["pipeline_end_to_end_verified"] = True
        payload["fully_ready"] = False
        payload["live_probe_ready"] = False
        payload["degraded"] = True
        payload["retryable"] = True
        payload["action_required"] = False
        payload["required_action"] = None
        payload["warning"] = (
            "The live TikTok transport probe is temporarily unavailable, but a recent "
            "real end-to-end completion and local artifact verify the pipeline."
        )
        payload["error"] = shared_download_error or live_error
        payload["error_code"] = "transient_network_error"
        _attach_health(payload, status="warn", message=payload["warning"])
        return payload

    payload["live_probe_ready"] = False
    payload["degraded"] = False
    _attach_health(payload, status="error", message=payload.get("error") or "TikTok access doctor failed")
    return payload


def render(payload: dict[str, Any], output: str, title: str) -> None:
    if output == "ndjson":
        print(json.dumps({"schema_version": 12, **payload}, ensure_ascii=False, sort_keys=True))
        return
    print(title)
    for key, value in payload.items():
        if key != "event":
            print(f"{key}={json.dumps(value, ensure_ascii=False) if isinstance(value, (dict, list)) else value}")


def main() -> int:
    argv = sys.argv[1:]
    sentinel = "__MEDIA2MD_VIDEO_ID__"
    for index, value in enumerate(argv[:-1]):
        if value == "--video-id" and re.fullmatch(r"-[A-Za-z0-9_-]{10}", argv[index + 1]):
            argv[index + 1] = sentinel + argv[index + 1]
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)
    youtube = sub.add_parser("youtube"); youtube.add_argument("--output", choices=("human", "ndjson"), default="human")
    instagram = sub.add_parser("instagram-backends"); instagram.add_argument("--shortcode"); instagram.add_argument("--output", choices=("human", "ndjson"), default="human")
    impersonation = sub.add_parser("impersonation"); impersonation.add_argument("--output", choices=("human", "ndjson"), default="human")
    browser_safety = sub.add_parser("browser-safety"); browser_safety.add_argument("--output", choices=("human", "ndjson"), default="human")
    youtube_access = sub.add_parser("youtube-access"); youtube_access.add_argument("--video-id", required=True); youtube_access.add_argument("--transcription-smoke-test", action="store_true"); youtube_access.add_argument("--output", choices=("human", "ndjson"), default="human")
    tiktok_access = sub.add_parser("tiktok-access"); tiktok_access.add_argument("--video-id", required=True); tiktok_access.add_argument("--creator", required=True); tiktok_access.add_argument("--transcription-smoke-test", action="store_true"); tiktok_access.add_argument("--output", choices=("human", "ndjson"), default="human")
    allp = sub.add_parser("all"); allp.add_argument("--shortcode"); allp.add_argument("--youtube-video-id"); allp.add_argument("--tiktok-video-id"); allp.add_argument("--tiktok-creator"); allp.add_argument("--transcription-smoke-test", action="store_true"); allp.add_argument("--output", choices=("human", "ndjson"), default="human")
    args = parser.parse_args(argv)
    if hasattr(args, "video_id") and str(args.video_id).startswith(sentinel): args.video_id = str(args.video_id)[len(sentinel):]
    if args.command == "youtube":
        payload = youtube_environment_payload(); render(payload, args.output, "YOUTUBE_DOCTOR"); return 0 if payload["ready"] else 2
    if args.command == "instagram-backends":
        payload = instagram_payload(args.shortcode); render(payload, args.output, "INSTAGRAM_BACKENDS_DOCTOR"); return 0 if payload["ready"] else 2
    if args.command == "impersonation":
        payload = impersonation_payload(); render(payload, args.output, "IMPERSONATION_DOCTOR"); return 0 if payload["ready"] else 2
    if args.command == "browser-safety":
        payload = {"event": "browser_safety_doctor", **browser_safety_payload()}; render(payload, args.output, "BROWSER_SAFETY_DOCTOR"); return 0
    if args.command == "youtube-access":
        payload = youtube_access_payload(args.video_id, transcription_smoke_test=args.transcription_smoke_test); render(payload, args.output, "YOUTUBE_ACCESS_DOCTOR"); return 0 if payload.get("pipeline_ready") else 2
    if args.command == "tiktok-access":
        payload = tiktok_access_payload(args.video_id, args.creator, transcription_smoke_test=args.transcription_smoke_test); render(payload, args.output, "TIKTOK_ACCESS_DOCTOR"); return 0 if payload.get("pipeline_ready") else 2
    payload: dict[str, Any] = {"event": "doctor_all", "youtube": youtube_environment_payload(), "instagram": instagram_payload(args.shortcode), "impersonation": impersonation_payload()}
    if args.youtube_video_id: payload["youtube_access"] = youtube_access_payload(args.youtube_video_id, transcription_smoke_test=args.transcription_smoke_test)
    if args.tiktok_video_id and args.tiktok_creator: payload["tiktok_access"] = tiktok_access_payload(args.tiktok_video_id, args.tiktok_creator, transcription_smoke_test=args.transcription_smoke_test)
    checks = [payload["youtube"].get("ready"), payload["instagram"].get("ready"), payload["impersonation"].get("ready")]
    if "youtube_access" in payload: checks.append(payload["youtube_access"].get("pipeline_ready"))
    if "tiktok_access" in payload: checks.append(payload["tiktok_access"].get("pipeline_ready"))
    payload["ready"] = all(bool(item) for item in checks)
    doctor_results = [
        HealthResult(status=payload["instagram"].get("health_status", "error"), message=str(payload["instagram"].get("health_message") or "instagram")),
        HealthResult(status=payload["impersonation"].get("health_status", "error"), message=str(payload["impersonation"].get("health_message") or "impersonation")),
    ]
    if "youtube_access" in payload:
        doctor_results.append(HealthResult(status=payload["youtube_access"].get("health_status", "error"), message=str(payload["youtube_access"].get("health_message") or "youtube_access")))
    if "tiktok_access" in payload:
        doctor_results.append(HealthResult(status=payload["tiktok_access"].get("health_status", "error"), message=str(payload["tiktok_access"].get("health_message") or "tiktok_access")))
    payload["health"] = summarize_health(doctor_results)
    _attach_health(payload, status="ok" if payload["ready"] else payload["health"]["status"], message="Combined doctor status")
    payload["schema"] = "media2md.cli.doctor/v1"
    payload["sections"] = [
        make_section("instagram", status=payload["instagram"].get("health_status", "error"), message=payload["instagram"].get("health_message"), data=payload["instagram"]).as_dict(),
        make_section("impersonation", status=payload["impersonation"].get("health_status", "error"), message=payload["impersonation"].get("health_message"), data=payload["impersonation"]).as_dict(),
        *(
            [make_section("youtube_access", status=payload["youtube_access"].get("health_status", "error"), message=payload["youtube_access"].get("health_message"), data=payload["youtube_access"]).as_dict()]
            if "youtube_access" in payload else []
        ),
        *(
            [make_section("tiktok_access", status=payload["tiktok_access"].get("health_status", "error"), message=payload["tiktok_access"].get("health_message"), data=payload["tiktok_access"]).as_dict()]
            if "tiktok_access" in payload else []
        ),
    ]
    render(payload, args.output, "MEDIA2MD_DOCTOR"); return 0 if payload["ready"] else 2


if __name__ == "__main__":
    try: raise SystemExit(main())
    except KeyboardInterrupt: raise SystemExit(130)
