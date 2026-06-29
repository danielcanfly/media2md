from __future__ import annotations

import shutil
import subprocess
from dataclasses import dataclass
from typing import Optional, Sequence

BROKEN_EXIT_CODES = (126, 127)


@dataclass(frozen=True)
class ProbeResult:
    status: str
    output: str = ""
    hint: str = ""

    @property
    def ok(self) -> bool:
        return self.status == "ok"


def reinstall_hint(package: str) -> str:
    return (
        "Command exists but could not execute. This often means the tool was "
        "installed against a stale Python environment. Reinstall it with:\n"
        f"  python -m pip install -U {package}"
    )


def probe_command(
    cmd: str,
    args: Sequence[str] = ("--version",),
    *,
    timeout: int = 10,
    retries: int = 0,
    package: Optional[str] = None,
) -> ProbeResult:
    path = shutil.which(cmd)
    if not path:
        return ProbeResult("missing")

    last: Optional[ProbeResult] = None
    for _ in range(retries + 1):
        last = _run_once(path, args, timeout, package or cmd)
        if last.ok:
            return last
        if last.status in {"missing", "broken"}:
            return last
    return last or ProbeResult("error", hint="unknown probe failure")


def _run_once(path: str, args: Sequence[str], timeout: int, package: str) -> ProbeResult:
    try:
        result = subprocess.run(
            [path, *args],
            capture_output=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
        )
    except FileNotFoundError:
        return ProbeResult("broken", hint=reinstall_hint(package))
    except OSError:
        return ProbeResult("broken", hint=reinstall_hint(package))
    except subprocess.TimeoutExpired:
        return ProbeResult("timeout", hint=f"`{path}` timed out after {timeout}s")

    if result.returncode in BROKEN_EXIT_CODES:
        return ProbeResult("broken", hint=reinstall_hint(package))

    output = ((result.stdout or "") + (result.stderr or "")).strip()
    if result.returncode != 0:
        return ProbeResult("error", output=output)
    return ProbeResult("ok", output=output)
