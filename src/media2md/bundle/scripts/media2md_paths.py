#!/usr/bin/env python3
from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def candidate_bin_dirs() -> list[Path]:
    dirs: list[Path] = []
    seen: set[str] = set()
    for extra in (
        Path(sys.executable).expanduser().parent,
        Path(sys.prefix).expanduser() / "bin",
        Path(os.environ.get("VIRTUAL_ENV", "")).expanduser() / "bin" if os.environ.get("VIRTUAL_ENV") else None,
        ROOT / ".venv" / "bin",
    ):
        if extra is None:
            continue
        key = str(extra)
        if key not in seen:
            seen.add(key)
            dirs.append(extra)
    for raw in os.environ.get("PATH", "").split(os.pathsep):
        if not raw:
            continue
        path = Path(raw).expanduser()
        key = str(path)
        if key not in seen:
            seen.add(key)
            dirs.append(path)
    return dirs


def command_path(name: str) -> str | None:
    for directory in candidate_bin_dirs():
        candidate = directory / name
        if candidate.is_file() and os.access(candidate, os.X_OK):
            return str(candidate)
    return shutil.which(name)


def require_command(name: str) -> str:
    found = command_path(name)
    if found:
        return found
    raise RuntimeError(f"Required command not found: {name}")
