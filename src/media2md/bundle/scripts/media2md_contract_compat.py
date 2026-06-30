from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Final, Iterable


REQUIRED_ACTIONS: Final[frozenset[str]] = frozenset(
    {
        "close_browser_and_check_profile_cookie_access",
        "complete_instagram_challenge_in_selected_profile",
        "complete_tiktok_challenge_in_selected_profile",
        "configure_non_browser_po_token_or_try_another_video",
        "configure_youtube_audio_strategies",
        "connect_instagram_browser_profile",
        "connect_tiktok_browser_profile",
        "connect_youtube_browser_profile",
        "inspect_instagram_access_error",
        "inspect_instagram_failure_report",
        "inspect_render_error",
        "inspect_tiktok_access_error",
        "inspect_transcription_log",
        "inspect_youtube_access_error",
        "install_auth_browser_dependencies",
        "install_impersonation",
        "install_mlx_whisper",
        "install_provider_extra",
        "install_youtube_extra",
        "login_to_youtube_in_selected_profile",
        "provide_valid_video_id",
        "reauthenticate_instagram_in_selected_profile",
        "reauthenticate_tiktok_in_selected_profile",
        "reauthenticate_youtube_in_selected_profile",
        "reconnect_instagram_browser_profile",
        "reconnect_tiktok_browser_profile",
        "refresh_tiktok_cookies",
        "select_existing_browser_profile",
        "upgrade_media2md_or_report_internal_bug",
        "use_smaller_model_or_shorter_chunks",
        "verify_or_reauthenticate_instagram_session",
        "verify_or_reauthenticate_youtube_session",
        "verify_youtube_session_after_opening_youtube",
        "verify_youtube_session_or_configure_non_browser_access",
    }
)

HEALTH_STATUSES = ("ok", "warn", "missing", "broken", "timeout", "error")


def validate_required_action(value: str | None) -> str | None:
    if value is None:
        return None
    text = str(value)
    if text not in REQUIRED_ACTIONS:
        raise ValueError(f"Unknown required_action: {text}")
    return text


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


@dataclass(frozen=True)
class HealthResult:
    status: str
    message: str


def summarize_health(results: list[HealthResult]) -> dict[str, object]:
    if not results:
        return {
            "status": "ok",
            "category": "ready",
            "ready_count": 0,
            "action_required_count": 0,
            "degraded_count": 0,
        }
    rank = {"ok": 0, "warn": 1, "missing": 2, "timeout": 3, "broken": 4, "error": 5}
    ordered = sorted(results, key=lambda item: rank[normalize_health_status(item.status)])
    chosen = ordered[-1]
    categories = [health_category(item.status) for item in results]
    return {
        "status": normalize_health_status(chosen.status),
        "category": health_category(chosen.status),
        "ready_count": sum(1 for item in categories if item == "ready"),
        "action_required_count": sum(1 for item in categories if item == "action_required"),
        "degraded_count": sum(1 for item in categories if item == "degraded"),
    }


@dataclass(frozen=True)
class CliSection:
    name: str
    status: str
    category: str
    message: str | None = None
    data: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "status": self.status,
            "category": self.category,
            "message": self.message,
            "data": dict(self.data),
        }


@dataclass(frozen=True)
class CliOutputModel:
    event: str
    schema: str
    status: str
    category: str
    summary: str | None = None
    sections: tuple[CliSection, ...] = ()
    data: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "sections", tuple(self.sections))
        object.__setattr__(self, "data", dict(self.data))

    def as_dict(self) -> dict[str, Any]:
        payload = {
            "event": self.event,
            "schema": self.schema,
            "status": self.status,
            "category": self.category,
            "summary": self.summary,
            "sections": [section.as_dict() for section in self.sections],
        }
        reserved = {"event", "schema", "status", "category", "summary", "sections"}
        payload.update({key: value for key, value in self.data.items() if key not in reserved})
        return payload


def make_event_payload(*, event: str, schema: str, data: dict[str, Any] | None = None) -> dict[str, Any]:
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


def cli_result(
    *,
    event: str,
    section: str,
    status: str,
    message: str,
    data: dict[str, Any],
    schema: str | None = None,
) -> dict[str, Any]:
    return make_output_model(
        event=event,
        schema=schema or f"media2md.cli.{event}/v1",
        summary=message,
        sections=(make_section(section, status=status, message=message, data=data),),
        data=data,
    ).as_dict()
