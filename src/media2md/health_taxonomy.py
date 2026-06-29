from __future__ import annotations

from .results import HealthResult

HEALTH_STATUSES = ("ok", "warn", "missing", "broken", "timeout", "error")


def normalize_health_status(value: str | None, *, default: str = "error") -> str:
    text = str(value or "").strip().lower()
    if text in HEALTH_STATUSES:
        return text
    return default


def health_category(status: str | None) -> str:
    normalized = normalize_health_status(status)
    if normalized == "ok":
        return "ready"
    if normalized in {"warn", "missing"}:
        return "action_required"
    return "degraded"


def status_rank(status: str | None) -> int:
    normalized = normalize_health_status(status)
    return {
        "ok": 0,
        "warn": 1,
        "missing": 2,
        "timeout": 3,
        "broken": 4,
        "error": 5,
    }[normalized]


def summarize_health(results: list[HealthResult]) -> dict[str, object]:
    if not results:
        return {
            "status": "ok",
            "category": "ready",
            "ready_count": 0,
            "action_required_count": 0,
            "degraded_count": 0,
        }
    ordered = sorted(results, key=lambda item: status_rank(item.status))
    chosen = ordered[-1]
    categories = [health_category(item.status) for item in results]
    return {
        "status": normalize_health_status(chosen.status),
        "category": health_category(chosen.status),
        "ready_count": sum(1 for item in categories if item == "ready"),
        "action_required_count": sum(1 for item in categories if item == "action_required"),
        "degraded_count": sum(1 for item in categories if item == "degraded"),
    }
