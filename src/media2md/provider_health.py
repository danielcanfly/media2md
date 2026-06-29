from __future__ import annotations

from .probe import ProbeResult
from .results import HealthResult


def probe_health_result(
    *,
    provider: str,
    backend: str,
    backends: tuple[str, ...] | list[str],
    probe: ProbeResult,
    success_message: str,
    missing_message: str,
    failure_message: str,
) -> HealthResult:
    hints: list[str] = []
    details: dict[str, object] = {"probe_status": probe.status}
    if probe.output:
        details["probe_output"] = probe.output
    if probe.hint:
        hints.append(probe.hint)

    if probe.ok:
        return HealthResult(
            status="ok",
            message=success_message,
            provider=provider,
            active_backend=backend,
            backends=tuple(backends),
            hints=tuple(hints),
            details=details,
        )

    if probe.status == "missing":
        return HealthResult(
            status="warn",
            message=missing_message,
            provider=provider,
            active_backend=None,
            backends=tuple(backends),
            hints=tuple(hints),
            details=details,
        )

    return HealthResult(
        status=probe.status,
        message=probe.hint or probe.output or failure_message,
        provider=provider,
        active_backend=None,
        backends=tuple(backends),
        hints=tuple(hints),
        details=details,
    )
