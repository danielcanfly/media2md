from __future__ import annotations

from typing import Any, Iterable

from .cli_output_model import CliOutputModel, CliSection
from .health_taxonomy import health_category, normalize_health_status, summarize_health
from .results import HealthResult


def make_event_payload(
    *,
    event: str,
    schema: str,
    data: dict[str, Any] | None = None,
) -> dict[str, Any]:
    payload = {"event": event, "schema": schema}
    payload.update(data or {})
    return payload


def make_section(
    name: str,
    *,
    status: str,
    message: str | None = None,
    data: dict[str, Any] | None = None,
) -> CliSection:
    normalized = normalize_health_status(status)
    return CliSection(
        name=name,
        status=normalized,
        category=health_category(normalized),
        message=message,
        data=data or {},
    )


def make_output_model(
    *,
    event: str,
    schema: str,
    sections: Iterable[CliSection] = (),
    summary: str | None = None,
    data: dict[str, Any] | None = None,
) -> CliOutputModel:
    section_items = tuple(sections)
    section_health = summarize_health(
        [HealthResult(status=section.status, message=section.message or section.name) for section in section_items]
    )
    return CliOutputModel(
        event=event,
        schema=schema,
        status=str(section_health["status"]),
        category=str(section_health["category"]),
        summary=summary,
        sections=section_items,
        data=data or {},
    )
