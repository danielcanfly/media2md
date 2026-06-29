#!/usr/bin/env python3
from __future__ import annotations

import http.cookiejar
import json
import os
import re
import shutil
import signal
import sqlite3
import subprocess
import tempfile
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from media2md.remediation_service import media2md_install_guidance, youtube_profile_guidance

from media2md_paths import command_path

ROOT = Path(__file__).resolve().parents[1]
AUTH_PROFILES = ROOT / "config" / "auth_profiles.json"
REGISTRY_DB = ROOT / "data" / "media2md.db"

_BROWSER_ROOTS = {
    "chrome": Path.home() / "Library" / "Application Support" / "Google" / "Chrome",
    "chromium": Path.home() / "Library" / "Application Support" / "Chromium",
    "brave": Path.home() / "Library" / "Application Support" / "BraveSoftware" / "Brave-Browser",
    "edge": Path.home() / "Library" / "Application Support" / "Microsoft Edge",
}

# Presence is a strong signal that the selected browser profile has a Google login.
# Values are never read or printed.
_YOUTUBE_AUTH_COOKIE_NAMES = {
    "SID", "HSID", "SSID", "APISID", "SAPISID",
    "__Secure-1PSID", "__Secure-3PSID", "__Secure-1PAPISID", "__Secure-3PAPISID",
    "LOGIN_INFO",
}


def iso_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def load_auth_profiles() -> dict[str, Any]:
    try:
        data = json.loads(AUTH_PROFILES.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        data = {"schema_version": 2, "providers": {}}
    data.setdefault("schema_version", 2)
    data.setdefault("providers", {})
    return data


def save_auth_profiles(data: dict[str, Any]) -> None:
    AUTH_PROFILES.parent.mkdir(parents=True, exist_ok=True)
    temp = AUTH_PROFILES.with_suffix(".tmp")
    temp.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.replace(temp, AUTH_PROFILES)
    os.chmod(AUTH_PROFILES, 0o600)


def browser_root(browser: str) -> Path:
    name = browser.lower()
    if name not in _BROWSER_ROOTS:
        raise RuntimeError(f"Profile discovery is not supported for browser: {browser}")
    return _BROWSER_ROOTS[name]


def _profile_display_names(root: Path) -> dict[str, str]:
    state = root / "Local State"
    try:
        data = json.loads(state.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError, PermissionError):
        return {}
    info = data.get("profile", {}).get("info_cache", {})
    result: dict[str, str] = {}
    if isinstance(info, dict):
        for profile_id, payload in info.items():
            if isinstance(payload, dict):
                result[str(profile_id)] = str(payload.get("name") or profile_id)
    return result


def profile_inventory(browser: str) -> list[dict[str, Any]]:
    root = browser_root(browser)
    names = _profile_display_names(root)
    ids: set[str] = set(names)
    if root.is_dir():
        for child in root.iterdir():
            if child.is_dir() and (child.name == "Default" or re.fullmatch(r"Profile \d+", child.name)):
                ids.add(child.name)
    rows: list[dict[str, Any]] = []
    for profile_id in sorted(ids, key=lambda item: (item != "Default", item.lower())):
        path = root / profile_id
        cookie_candidates = [path / "Network" / "Cookies", path / "Cookies"]
        rows.append({
            "profile": profile_id,
            "display_name": names.get(profile_id, profile_id),
            "path": str(path),
            "exists": path.is_dir(),
            "cookie_db_exists": any(candidate.is_file() for candidate in cookie_candidates),
        })
    return rows


def validate_profile(browser: str, profile: str) -> dict[str, Any]:
    match = next((row for row in profile_inventory(browser) if row["profile"] == profile), None)
    if not match:
        known = ", ".join(row["profile"] for row in profile_inventory(browser)) or "none"
        raise RuntimeError(f"Chrome profile not found: {profile}. Available profiles: {known}")
    if not match["exists"]:
        raise RuntimeError(f"Chrome profile directory does not exist: {match['path']}")
    return match


def browser_cookie_spec(browser: str, profile: str | None) -> str:
    return f"{browser}:{profile}" if profile else browser


def configured_youtube_profile() -> dict[str, Any]:
    profile = load_auth_profiles().get("providers", {}).get("youtube", {})
    return profile if isinstance(profile, dict) else {}


def youtube_auth_args() -> list[str]:
    profile = configured_youtube_profile()
    mode = str(profile.get("mode") or "")
    browser = str(profile.get("browser") or "").strip()
    selected = str(profile.get("profile") or "").strip()
    if mode == "browser_profile" and browser and selected:
        return ["--cookies-from-browser", browser_cookie_spec(browser, selected)]
    if browser and profile.get("use_live_browser_cookies"):
        return ["--cookies-from-browser", browser_cookie_spec(browser, selected or None)]
    cookie_file = profile.get("cookie_file")
    if cookie_file and Path(str(cookie_file)).expanduser().is_file():
        return ["--cookies", str(Path(str(cookie_file)).expanduser())]
    return []


def default_probe_video_id() -> str:
    if REGISTRY_DB.is_file():
        try:
            conn = sqlite3.connect(REGISTRY_DB)
            row = conn.execute(
                "SELECT external_id FROM media WHERE provider='youtube' ORDER BY CASE status WHEN 'pending' THEN 0 ELSE 1 END,id LIMIT 1"
            ).fetchone()
            conn.close()
            if row and re.fullmatch(r"[A-Za-z0-9_-]{11}", str(row[0])):
                return str(row[0])
        except sqlite3.Error:
            pass
    return "dQw4w9WgXcQ"


def _command(name: str) -> str | None:
    return command_path(name)


def _run(cmd: list[str], timeout: int = 180) -> subprocess.CompletedProcess[str]:
    process = subprocess.Popen(cmd, cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, start_new_session=True)
    try:
        stdout, stderr = process.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        try:
            os.killpg(process.pid, signal.SIGTERM)
        except ProcessLookupError:
            pass
        try:
            process.wait(timeout=3)
        except subprocess.TimeoutExpired:
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
        stdout, stderr = process.communicate()
        return subprocess.CompletedProcess(cmd, 124, stdout, (stderr or "") + f"\nTimed out after {timeout} seconds")
    return subprocess.CompletedProcess(cmd, process.returncode, stdout, stderr)


def parse_netscape_cookie_records(path: Path) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    try:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    except FileNotFoundError:
        return records
    for line in lines:
        if not line or (line.startswith("#") and not line.startswith("#HttpOnly_")):
            continue
        parts = line.split("\t")
        if len(parts) < 7:
            continue
        try:
            expires = int(parts[4] or 0)
        except ValueError:
            expires = 0
        records.append({
            "domain": parts[0].removeprefix("#HttpOnly_"),
            "path": parts[2],
            "secure": parts[3].upper() == "TRUE",
            "expires": expires,
            "name": parts[5],
        })
    return records


def parse_netscape_cookie_names(path: Path) -> set[str]:
    return {str(record["name"]) for record in parse_netscape_cookie_records(path)}


def _youtube_account_probe(cookie_path: Path, timeout: int = 30) -> dict[str, Any]:
    jar = http.cookiejar.MozillaCookieJar(str(cookie_path))
    try:
        jar.load(ignore_discard=True, ignore_expires=False)
    except Exception as exc:
        return {"state": "unknown", "authenticated": False, "error": f"Could not load exported cookies: {exc}", "status": None}
    opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))
    request = urllib.request.Request(
        "https://www.youtube.com/feed/history?hl=en&persist_hl=1",
        headers={
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/149 Safari/537.36",
            "Accept-Language": "en-US,en;q=0.9",
        },
    )
    try:
        with opener.open(request, timeout=timeout) as response:
            body = response.read(2_000_000).decode("utf-8", errors="replace")
            final_url = response.geturl()
            status = getattr(response, "status", 200)
    except urllib.error.HTTPError as exc:
        body = exc.read(1_000_000).decode("utf-8", errors="replace")
        final_url = exc.geturl()
        status = exc.code
    except Exception as exc:
        return {"state": "unknown", "authenticated": False, "error": str(exc), "status": None}
    lower_url = final_url.lower()
    authenticated_markers = (
        '"LOGGED_IN":true', '"isLoggedIn":true', '"isSignedIn":true',
        '\\"LOGGED_IN\\":true', '\\"isLoggedIn\\":true',
    )
    rejected_markers = (
        '"LOGGED_IN":false', '"isLoggedIn":false', '"isSignedIn":false',
        'accounts.google.com/ServiceLogin', 'Sign in to continue to YouTube',
    )
    if any(marker in body for marker in authenticated_markers):
        return {"state": "authenticated", "authenticated": True, "error": None, "status": status, "final_url": final_url}
    if "accounts.google.com" in lower_url or any(marker in body for marker in rejected_markers):
        return {"state": "rejected", "authenticated": False, "error": "YouTube did not accept the browser session as signed in.", "status": status, "final_url": final_url}
    return {
        "state": "unknown", "authenticated": False,
        "error": "YouTube account page did not expose a reliable signed-in marker.",
        "status": status, "final_url": final_url,
    }


def _persist_verification(payload: dict[str, Any]) -> None:
    data = load_auth_profiles()
    profile = data.get("providers", {}).get("youtube")
    if not isinstance(profile, dict):
        return
    profile["last_verified_at"] = iso_now()
    profile["last_auth_state"] = payload.get("auth_state")
    profile["last_authenticated"] = bool(payload.get("authenticated"))
    profile["last_verify_error"] = payload.get("error")
    save_auth_profiles(data)


def verify_youtube_session(video_id: str | None = None, *, persist: bool = False) -> dict[str, Any]:
    video_id = video_id or default_probe_video_id()
    selected = configured_youtube_profile()
    browser = str(selected.get("browser") or "")
    profile = str(selected.get("profile") or "")
    payload: dict[str, Any] = {
        "event": "youtube_auth_verify",
        "browser_launch_allowed": False,
        "browser": browser or None,
        "profile": profile or None,
        "profile_configured": bool(browser and profile and selected.get("mode") == "browser_profile"),
        "profile_path_exists": False,
        "cookie_extraction_ready": False,
        "youtube_auth_cookies_found": False,
        "auth_cookie_names": [],
        "auth_cookie_active_count": 0,
        "auth_cookie_expired_count": 0,
        "metadata_ready": False,
        "server_auth_probe": "not_run",
        "server_auth_status": None,
        "auth_state": "unconfigured",
        "authenticated": False,
        "video_id": video_id,
        "error": None,
        "required_action": None,
        "guidance": [],
    }
    if not payload["profile_configured"]:
        payload["required_action"] = "connect_youtube_browser_profile"
        payload["guidance"] = youtube_profile_guidance(action="connect")
        return payload
    try:
        row = validate_profile(browser, profile)
        payload["profile_path_exists"] = bool(row["exists"])
    except RuntimeError as exc:
        payload["auth_state"] = "profile_missing"
        payload["error"] = str(exc)
        payload["required_action"] = "select_existing_browser_profile"
        payload["guidance"] = youtube_profile_guidance(action="reconnect")
        if persist:
            _persist_verification(payload)
        return payload
    yt = _command("yt-dlp")
    if not yt:
        payload["auth_state"] = "dependency_missing"
        payload["error"] = "yt-dlp is not installed"
        payload["required_action"] = "install_youtube_extra"
        payload["guidance"] = [media2md_install_guidance("youtube")]
        if persist:
            _persist_verification(payload)
        return payload
    url = f"https://www.youtube.com/watch?v={video_id}"
    with tempfile.TemporaryDirectory(prefix="media2md-youtube-auth-") as temp_dir:
        cookie_path = Path(temp_dir) / "youtube-cookies.txt"
        command = [
            yt, "--cookies-from-browser", browser_cookie_spec(browser, profile),
            "--cookies", str(cookie_path), "--dump-single-json", "--skip-download",
            "--no-playlist", url,
        ]
        result = _run(command, timeout=240)
        records = parse_netscape_cookie_records(cookie_path)
        names = {str(record["name"]) for record in records}
        auth_records = [record for record in records if record["name"] in _YOUTUBE_AUTH_COOKIE_NAMES]
        now_epoch = int(datetime.now(timezone.utc).timestamp())
        active = [record for record in auth_records if int(record["expires"] or 0) == 0 or int(record["expires"]) > now_epoch]
        expired = [record for record in auth_records if int(record["expires"] or 0) > 0 and int(record["expires"]) <= now_epoch]
        found = sorted({str(record["name"]) for record in auth_records})
        payload["cookie_extraction_ready"] = bool(cookie_path.is_file() and records)
        payload["youtube_auth_cookies_found"] = bool(found)
        payload["auth_cookie_names"] = found
        payload["auth_cookie_active_count"] = len(active)
        payload["auth_cookie_expired_count"] = len(expired)
        payload["metadata_ready"] = result.returncode == 0

        if not payload["cookie_extraction_ready"]:
            error_text = (result.stderr or result.stdout or "Cookie extraction failed")[-4000:]
            payload["auth_state"] = "cookie_store_locked" if any(token in error_text.lower() for token in ("keychain", "decrypt", "database is locked", "permission")) else "cookie_missing"
            payload["error"] = error_text
            payload["required_action"] = "close_browser_and_check_profile_cookie_access"
            payload["guidance"] = youtube_profile_guidance(
                browser=browser or "Chrome",
                profile=selected.get("profile_display_name") or profile,
                action="close_browser",
            )
        elif not auth_records:
            payload["auth_state"] = "cookie_missing"
            payload["error"] = "No Google/YouTube authentication cookies were found in the selected profile."
            payload["required_action"] = "login_to_youtube_in_selected_profile"
            payload["guidance"] = youtube_profile_guidance(
                browser=browser or "Chrome",
                profile=selected.get("profile_display_name") or profile,
                action="login",
            )
        elif not active:
            payload["auth_state"] = "cookie_expired"
            payload["error"] = "The selected profile contains YouTube authentication cookies, but all detected auth cookies are expired."
            payload["required_action"] = "reauthenticate_youtube_in_selected_profile"
            payload["guidance"] = youtube_profile_guidance(
                browser=browser or "Chrome",
                profile=selected.get("profile_display_name") or profile,
                action="refresh_login",
            )
        else:
            account = _youtube_account_probe(cookie_path)
            payload["server_auth_probe"] = account["state"]
            payload["server_auth_status"] = account.get("status")
            payload["authenticated"] = bool(account.get("authenticated"))
            if payload["authenticated"]:
                payload["auth_state"] = "authenticated"
                payload["required_action"] = None
            elif account["state"] == "rejected":
                payload["auth_state"] = "server_rejected"
                payload["error"] = account.get("error")
                payload["required_action"] = "reauthenticate_youtube_in_selected_profile"
                payload["guidance"] = youtube_profile_guidance(
                    browser=browser or "Chrome",
                    profile=selected.get("profile_display_name") or profile,
                    action="refresh_login",
                )
            else:
                payload["auth_state"] = "configured_unverified"
                payload["error"] = account.get("error")
                payload["required_action"] = "verify_youtube_session_after_opening_youtube"
                payload["guidance"] = youtube_profile_guidance(
                    browser=browser or "Chrome",
                    profile=selected.get("profile_display_name") or profile,
                    action="open_youtube",
                )

        if result.returncode != 0 and not payload["error"]:
            payload["error"] = (result.stderr or result.stdout or "YouTube metadata verification failed")[-4000:]
        if payload["authenticated"] and not payload["metadata_ready"]:
            payload["authenticated"] = False
            payload["auth_state"] = "youtube_challenge"
            payload["required_action"] = "inspect_youtube_access_error"
            payload["guidance"] = youtube_profile_guidance(action="doctor")
    if persist:
        _persist_verification(payload)
    return payload
