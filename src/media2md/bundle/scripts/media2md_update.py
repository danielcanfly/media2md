#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import urllib.error
import urllib.request
import zipfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "config" / "social2md.json"
CACHE = Path.home() / ".cache" / "media2md" / "updates"
STATE = CACHE / "state.json"
REPOSITORY = "danielcanfly/media2md"
CURRENT_VERSION = "0.9.1"


def now() -> datetime:
    return datetime.now(timezone.utc)


def iso_now() -> str:
    return now().isoformat(timespec="seconds")


def load_json(path: Path, default: Any) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError, TypeError):
        return json.loads(json.dumps(default))


def atomic_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.replace(tmp, path)


def version_tuple(value: str) -> tuple[int, int, int]:
    parts = [int(x) for x in re.findall(r"\d+", value)[:3]]
    return tuple((parts + [0, 0, 0])[:3])  # type: ignore[return-value]


def settings() -> dict[str, Any]:
    config = load_json(CONFIG, {})
    updates = config.setdefault("updates", {})
    updates.setdefault("repository", REPOSITORY)
    updates.setdefault("enabled", True)
    updates.setdefault("check_on_use", True)
    updates.setdefault("check_every_minutes", 43200)
    updates.setdefault("auto_download", False)
    updates.setdefault("auto_install", False)
    return updates


def github_release(repository: str) -> dict[str, Any]:
    request = urllib.request.Request(
        f"https://api.github.com/repos/{repository}/releases/latest",
        headers={"Accept": "application/vnd.github+json", "User-Agent": "media2md"},
    )
    try:
        with urllib.request.urlopen(request, timeout=5) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            return {"status": "no_release_published"}
        raise RuntimeError(f"GitHub update check failed: HTTP {exc.code}") from exc


def select_asset(release: dict[str, Any]) -> dict[str, Any] | None:
    assets = [a for a in release.get("assets", []) if isinstance(a, dict)]
    version = str(release.get("tag_name") or "").lstrip("v")
    priorities = [
        f"media2md-{version}-py3-none-any.whl",
        f"media2md-v{version}.zip",
        f"media2md-{version}.zip",
    ]
    for expected in priorities:
        for asset in assets:
            if str(asset.get("name")) == expected:
                return asset
    for asset in assets:
        name = str(asset.get("name") or "").lower()
        if name.endswith(".zip") and "media2md" in name:
            return asset
    for asset in assets:
        if str(asset.get("name") or "").endswith(".whl"):
            return asset
    return None


def check(repository: str | None = None, persist: bool = True) -> dict[str, Any]:
    cfg = settings()
    repo = repository or str(cfg.get("repository") or REPOSITORY)
    release = github_release(repo)
    payload: dict[str, Any] = {
        "event": "update_check",
        "repository": repo,
        "current_version": CURRENT_VERSION,
        "checked_at": iso_now(),
    }
    if release.get("status") == "no_release_published":
        payload.update({"status": "no_release_published", "latest_version": None, "update_available": False})
    else:
        latest = str(release.get("tag_name") or "")
        asset = select_asset(release)
        payload.update({
            "status": "ok",
            "latest_version": latest,
            "update_available": version_tuple(latest) > version_tuple(CURRENT_VERSION),
            "release_url": release.get("html_url"),
            "release_notes": str(release.get("body") or "")[:4000],
            "asset": asset,
        })
    if persist:
        state = load_json(STATE, {})
        state["last_successful_check_at"] = payload["checked_at"]
        state["last_check"] = payload
        atomic_json(STATE, state)
    return payload


def due_for_check() -> bool:
    cfg = settings()
    if not cfg.get("enabled", True) or not cfg.get("check_on_use", True):
        return False
    state = load_json(STATE, {})
    last = state.get("last_successful_check_at")
    if last:
        try:
            return now() >= datetime.fromisoformat(last) + timedelta(minutes=int(cfg.get("check_every_minutes", 43200)))
        except (ValueError, TypeError):
            return True
    last_attempt = state.get("last_attempt_at")
    if last_attempt:
        try:
            return now() >= datetime.fromisoformat(last_attempt) + timedelta(days=1)
        except (ValueError, TypeError):
            pass
    return True


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def download_asset(payload: dict[str, Any] | None = None) -> dict[str, Any]:
    payload = payload or check()
    if not payload.get("update_available"):
        raise RuntimeError("No newer Media2MD release is available.")
    asset = payload.get("asset")
    if not isinstance(asset, dict) or not asset.get("browser_download_url"):
        raise RuntimeError("The latest release has no compatible update asset. Attach media2md-vX.Y.Z.zip to the GitHub Release.")
    CACHE.mkdir(parents=True, exist_ok=True)
    name = str(asset.get("name") or "media2md-update.zip")
    target = CACHE / name
    request = urllib.request.Request(str(asset["browser_download_url"]), headers={"User-Agent": "media2md"})
    with urllib.request.urlopen(request, timeout=120) as response, target.open("wb") as handle:
        shutil.copyfileobj(response, handle)
    actual = sha256(target)
    digest = str(asset.get("digest") or "")
    expected = digest.split(":", 1)[1].lower() if digest.startswith("sha256:") else _fetch_sidecar_sha256(str(asset["browser_download_url"]), name)
    if not expected:
        target.unlink(missing_ok=True)
        raise RuntimeError("Release asset has no verifiable SHA-256 digest or sidecar file.")
    if actual.lower() != expected:
        target.unlink(missing_ok=True)
        raise RuntimeError("Downloaded update failed SHA-256 verification.")
    state = load_json(STATE, {})
    state["downloaded"] = {
        "version": payload.get("latest_version"),
        "path": str(target),
        "sha256": actual,
        "downloaded_at": iso_now(),
        "release_url": payload.get("release_url"),
    }
    atomic_json(STATE, state)
    return state["downloaded"]


def _backup_members() -> list[Path]:
    candidates = [
        ROOT / "scripts", ROOT / "bin", ROOT / "src", ROOT / "openclaw", ROOT / "config",
        ROOT / ".github", ROOT / "pyproject.toml", ROOT / "README.md", ROOT / ".gitignore",
        ROOT / "data" / "state.db", ROOT / "data" / "media2md.db", ROOT / "data" / "social2md_media.db",
    ]
    return [path for path in candidates if path.exists()]


def create_backup() -> Path:
    CACHE.mkdir(parents=True, exist_ok=True)
    backup = CACHE / f"rollback-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}.zip"
    with zipfile.ZipFile(backup, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for path in _backup_members():
            if path.is_dir():
                for child in path.rglob("*"):
                    if child.is_file():
                        archive.write(child, child.relative_to(ROOT))
            else:
                archive.write(path, path.relative_to(ROOT))
    return backup


def _safe_extract(archive: zipfile.ZipFile, destination: Path) -> None:
    base=destination.resolve()
    for member in archive.infolist():
        target=(destination/member.filename).resolve()
        if target != base and base not in target.parents:
            raise RuntimeError(f"Unsafe path in update archive: {member.filename}")
        if member.is_dir(): continue
        mode=(member.external_attr >> 16) & 0o170000
        if mode == 0o120000:
            raise RuntimeError(f"Symlinks are not allowed in update archives: {member.filename}")
    archive.extractall(destination)


def _fetch_sidecar_sha256(asset_url: str, asset_name: str) -> str | None:
    for suffix in ('.sha256', '.sha256.txt'):
        try:
            req=urllib.request.Request(asset_url+suffix,headers={'User-Agent':'media2md'})
            with urllib.request.urlopen(req,timeout=30) as response:
                text=response.read().decode('utf-8','replace').strip()
            match=re.search(r'\b([0-9a-fA-F]{64})\b',text)
            if match: return match.group(1).lower()
        except Exception:
            continue
    return None

def install_downloaded(yes: bool, non_interactive: bool) -> dict[str, Any]:
    if (non_interactive or not sys.stdin.isatty()) and not yes:
        raise RuntimeError("Update installation requires explicit --yes in non-interactive mode.")
    state = load_json(STATE, {})
    downloaded = state.get("downloaded")
    if not isinstance(downloaded, dict) or not Path(str(downloaded.get("path") or "")).is_file():
        downloaded = download_asset()
    package = Path(str(downloaded["path"]))
    backup = create_backup()
    if package.suffix.lower() == ".zip":
        with zipfile.ZipFile(package) as archive:
            _safe_extract(archive, ROOT)
        installers = list((ROOT / "scripts").glob("install_media2md_v*.py"))
        if not installers:
            raise RuntimeError("Update ZIP did not contain an install_media2md_v*.py installer.")
        installer = max(installers, key=lambda path: version_tuple(path.stem))
        result = subprocess.run([sys.executable, str(installer)], cwd=ROOT, check=False)
        if result.returncode != 0:
            raise RuntimeError(f"Update installer failed with exit code {result.returncode}.")
        if (ROOT / "pyproject.toml").is_file():
            dep = subprocess.run([sys.executable,"-m","pip","install","--upgrade","-e",str(ROOT)],cwd=ROOT,check=False)
            if dep.returncode != 0:
                raise RuntimeError(f"Update files installed, but dependency reconciliation failed with exit code {dep.returncode}.")
    elif package.suffix.lower() == ".whl":
        result = subprocess.run([sys.executable, "-m", "pip", "install", "--upgrade", str(package)], cwd=ROOT, check=False)
        if result.returncode != 0:
            raise RuntimeError(f"pip upgrade failed with exit code {result.returncode}.")
    else:
        raise RuntimeError(f"Unsupported update package: {package.name}")
    state["last_install"] = {"version": downloaded.get("version"), "installed_at": iso_now(), "rollback_backup": str(backup)}
    atomic_json(STATE, state)
    return state["last_install"]


def rollback(yes: bool) -> dict[str, Any]:
    if not yes:
        raise RuntimeError("Rollback requires --yes.")
    state = load_json(STATE, {})
    install = state.get("last_install")
    if not isinstance(install, dict):
        raise RuntimeError("No update-managed or manual-installer rollback backup is recorded.")
    backup = Path(str(install.get("rollback_backup") or ""))
    if not backup.is_file():
        raise RuntimeError(f"Rollback backup is missing: {backup}")
    for relative in ("scripts", "bin", "src", "openclaw", ".github"):
        target = ROOT / relative
        if target.is_dir():
            shutil.rmtree(target)
        elif target.exists():
            target.unlink()
    with zipfile.ZipFile(backup) as archive:
        _safe_extract(archive, ROOT)
    pip_exit = None
    if (ROOT / "pyproject.toml").is_file():
        result = subprocess.run([sys.executable, "-m", "pip", "install", "-e", "."], cwd=ROOT, check=False)
        pip_exit = result.returncode
        if result.returncode != 0:
            raise RuntimeError(f"Rollback files were restored, but editable package reinstall failed with exit code {result.returncode}.")
    state["last_rollback"] = {"restored_at": iso_now(), "backup": str(backup), "pip_exit_code": pip_exit}
    atomic_json(STATE, state)
    return state["last_rollback"]


def render(payload: dict[str, Any], output: str, title: str) -> None:
    if output == "ndjson":
        print(json.dumps({"schema_version": 12, **payload}, ensure_ascii=False, sort_keys=True))
        return
    print(title)
    for key, value in payload.items():
        if key not in {"event", "asset", "release_notes"}:
            print(f"{key}={value}")
    if payload.get("release_notes"):
        print("release_notes=" + str(payload["release_notes"]).replace("\n", " ")[:500])


def main() -> int:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)
    status = sub.add_parser("status"); status.add_argument("--output", choices=("human", "ndjson"), default="human")
    checkp = sub.add_parser("check"); checkp.add_argument("--repository"); checkp.add_argument("--output", choices=("human", "ndjson"), default="human")
    due = sub.add_parser("check-if-due"); due.add_argument("--output", choices=("human", "ndjson"), default="ndjson")
    dl = sub.add_parser("download"); dl.add_argument("--output", choices=("human", "ndjson"), default="human")
    install = sub.add_parser("install"); install.add_argument("--yes", action="store_true"); install.add_argument("--non-interactive", action="store_true"); install.add_argument("--output", choices=("human", "ndjson"), default="human")
    rb = sub.add_parser("rollback"); rb.add_argument("--yes", action="store_true"); rb.add_argument("--output", choices=("human", "ndjson"), default="human")
    args = parser.parse_args()
    if args.command == "status":
        payload = {"event": "update_status", "settings": settings(), "state": load_json(STATE, {})}
        render(payload, args.output, "UPDATE_STATUS"); return 0
    if args.command == "check":
        payload = check(args.repository); render(payload, args.output, "UPDATE_CHECK"); return 0
    if args.command == "check-if-due":
        if not due_for_check():
            payload = {"event": "update_check_skipped", "reason": "not_due"}
        else:
            state = load_json(STATE, {})
            state["last_attempt_at"] = iso_now()
            atomic_json(STATE, state)
            try:
                payload = check()
            except Exception as exc:
                state = load_json(STATE, {})
                state["last_failure"] = {"at": iso_now(), "error": str(exc)[:1000]}
                atomic_json(STATE, state)
                payload = {"event": "update_check_failed", "error": str(exc), "retry_after_hours": 24}
        render(payload, args.output, "UPDATE_CHECK"); return 0
    if args.command == "download":
        payload = {"event": "update_downloaded", **download_asset()}; render(payload, args.output, "UPDATE_DOWNLOADED"); return 0
    if args.command == "install":
        payload = {"event": "update_installed", **install_downloaded(args.yes, args.non_interactive)}; render(payload, args.output, "UPDATE_INSTALLED"); return 0
    payload = {"event": "update_rolled_back", **rollback(args.yes)}; render(payload, args.output, "UPDATE_ROLLED_BACK"); return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        raise SystemExit(130)
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise SystemExit(2)
