from __future__ import annotations

from media2md.results import HealthResult
from media2md.bundle.scripts.public_cli_state_service import (
    agent_status_payload,
    apply_settings_updates,
    creator_catalog_metadata,
    provider_auth_rows,
    render_creator_status,
    settings_payload,
    system_status_payload,
)


class _Args:
    instagram_backend = None
    youtube_js_runtime = None
    youtube_allow_remote_ejs = None
    youtube_po_token_provider = None
    youtube_pot_browser_path = None
    youtube_caption_first = None
    youtube_caption_languages = None
    youtube_audio_strategies = None
    youtube_long_video_threshold_minutes = None
    youtube_chunk_minutes = None
    youtube_chunk_model = None
    tiktok_impersonate = None
    update_check_every_days = None
    update_check_on_use = None


def test_system_status_payload_builds_provider_rows(tmp_path):
    cookie = tmp_path / "instagram.cookies.txt"
    cookie.write_text("ok", encoding="utf-8")
    payload = system_status_payload(
        config={"timezone": "UTC", "updates": {"check_every_minutes": 1440}},
        auth_data={
            "instagram": {"cookie_file": str(cookie)},
            "youtube": {"mode": "browser_profile", "browser": "chrome", "profile": "Profile 1"},
        },
        providers=("instagram", "youtube", "tiktok"),
        version="0.9.4",
        root=tmp_path,
        repository="danielcanfly/media2md",
        creator_count=2,
        registry_db=tmp_path / "db.sqlite3",
    )
    assert payload["event"] == "system_status"
    assert payload["schema"] == "media2md.cli.system_status/v1"
    assert payload["status"] in {"ok", "warn", "missing", "broken", "timeout", "error"}
    assert payload["category"] in {"ready", "action_required", "degraded"}
    assert len(payload["sections"]) == 2
    assert payload["creator_count"] == 2
    assert payload["providers"][0]["configured"] is True
    assert payload["providers"][1]["configured"] is True
    assert payload["providers"][2]["configured"] is False
    assert payload["providers"][0]["health_status"] in {"ok", "warn", "missing", "broken", "timeout", "error"}
    assert payload["provider_health"]["status"] in {"ok", "warn", "missing", "broken", "timeout", "error"}


def test_provider_auth_rows_include_health_contract(monkeypatch, tmp_path):
    cookie = tmp_path / "instagram.cookies.txt"
    cookie.write_text("ok", encoding="utf-8")

    class _Adapter:
        def __init__(self, name: str, result: HealthResult):
            self.name = name
            self._result = result

        def health_check(self) -> HealthResult:
            return self._result

    adapters = {
        "instagram": _Adapter("instagram", HealthResult(status="ok", message="ready", provider="instagram", active_backend="gallery-dl", backends=("gallery-dl", "instaloader"))),
        "youtube": _Adapter("youtube", HealthResult(status="warn", message="missing auth", provider="youtube", active_backend=None, backends=("yt-dlp", "yt-dlp-ejs"))),
        "tiktok": _Adapter("tiktok", HealthResult(status="broken", message="broken", provider="tiktok", active_backend=None, backends=("yt-dlp",), hints=("reinstall",))),
    }

    monkeypatch.setattr(
        "media2md.bundle.scripts.public_cli_state_service.provider_adapter",
        lambda name: adapters.get(name),
    )

    rows = provider_auth_rows(
        {
            "instagram": {"cookie_file": str(cookie)},
            "youtube": {"mode": "browser_profile", "browser": "chrome", "profile": "Profile 1"},
        },
        ("instagram", "youtube", "tiktok"),
    )
    assert rows[0]["configured"] is True
    assert rows[0]["health_status"] == "ok"
    assert rows[0]["health_category"] == "ready"
    assert rows[0]["active_backend"] == "gallery-dl"
    assert rows[1]["health_status"] == "warn"
    assert rows[1]["health_category"] == "action_required"
    assert rows[2]["health_status"] == "broken"
    assert rows[2]["health_category"] == "degraded"
    assert rows[2]["hints"] == ["reinstall"]


def test_settings_payload_is_minimal_projection():
    payload = settings_payload(
        {
            "timezone": "UTC",
            "ui_locale": "en",
            "markdown_locale": "ja",
            "defaults": {"sync": {}},
            "providers": {"youtube": {"chunk_model": "small"}},
            "updates": {"enabled": True},
        }
    )
    assert payload["event"] == "settings"
    assert payload["schema"] == "media2md.cli.settings/v1"
    assert payload["status"] == "ok"
    assert len(payload["sections"]) == 3
    assert payload["sections"][0]["name"] == "localization"
    assert payload["markdown_locale"] == "ja"
    assert payload["providers"]["youtube"]["chunk_model"] == "small"


def test_apply_settings_updates_handles_provider_fields():
    args = _Args()
    args.instagram_backend = "gallery-dl"
    args.youtube_caption_languages = "ja,en"
    args.youtube_audio_strategies = "direct,proxy"
    args.youtube_long_video_threshold_minutes = 7
    args.youtube_chunk_minutes = 3
    args.tiktok_impersonate = "chrome"
    args.update_check_every_days = 2
    args.update_check_on_use = True
    config = apply_settings_updates({}, args)
    assert config["providers"]["instagram"]["backend"] == "gallery-dl"
    assert config["providers"]["youtube"]["caption_languages"] == ["ja", "en"]
    assert config["providers"]["youtube"]["audio_download_strategies"] == ["direct", "proxy"]
    assert config["providers"]["youtube"]["long_video_threshold_seconds"] == 420
    assert config["providers"]["youtube"]["chunk_seconds"] == 180
    assert config["providers"]["tiktok"]["impersonate"] == "chrome"
    assert config["updates"]["check_every_minutes"] == 2880
    assert config["updates"]["check_on_use"] is True
    assert config["updates"]["enabled"] is True


def test_agent_status_payload_keeps_schema_version():
    payload = agent_status_payload({"agent": {"mode": "strict"}}, schema_version=13)
    assert payload["event"] == "agent_status"
    assert payload["schema"] == "media2md.cli.agent_status/v1"
    assert payload["ndjson_schema_version"] == 13
    assert payload["permissions"] == {"mode": "strict"}
    assert "creator add" in payload["commands"]["write"]
    assert "creator run" in payload["commands"]["write"]
    assert "creator delete" in payload["commands"]["confirmation"]
    assert "youtube" in payload["provider_commands"]
    assert "doctor youtube-access" in payload["provider_commands"]["youtube"]["read"]
    assert "provider_capabilities" in payload
    assert payload["provider_capabilities"]["youtube"]["backends"] == ["yt-dlp", "yt-dlp-ejs"]
    assert payload["provider_capabilities"]["instagram"]["default_backend"] == "auto"
    assert payload["provider_capabilities"]["tiktok"]["extra"] == "tiktok"
    assert payload["provider_capabilities"]["youtube"]["capabilities"]["creator_sync"] is True
    assert "creator refresh-catalog" in payload["provider_capabilities"]["youtube"]["commands"]["write"]


def test_creator_catalog_metadata_derives_youtube_surface_and_configured_surfaces():
    metadata = creator_catalog_metadata(
        {"provider": "youtube", "source_url": "https://www.youtube.com/@creator-name/shorts"},
        youtube_catalog_surfaces=lambda: ("videos", "shorts", "streams"),
    )
    assert metadata["source_url"] == "https://www.youtube.com/@creator-name/shorts"
    assert metadata["catalog_surface"] == "shorts"
    assert metadata["catalog_surfaces"] == ["videos", "shorts", "streams"]


def test_render_creator_status_ndjson_includes_youtube_catalog_metadata():
    emitted = []

    class _Args:
        output = "ndjson"

    result = render_creator_status(
        _Args(),
        rows=[{
            "provider": "youtube",
            "handle": "creator-name",
            "source_url": "https://www.youtube.com/@creator-name/shorts",
            "current_total": 12,
            "current_total_exact": 1,
            "youtube_video_total": 5,
            "youtube_video_total_exact": 1,
            "youtube_shorts_total": 7,
            "youtube_shorts_total_exact": 1,
            "youtube_streams_total": 0,
            "youtube_streams_total_exact": 0,
            "tracked": 12,
            "completed": 0,
            "remaining": 12,
            "last_full_exact_total": 12,
            "last_full_exact_at": "2026-06-30T00:00:00+00:00",
        }],
        effective_policy=lambda provider, creator: {"sync": {"enabled": True, "every_minutes": 60, "full_every_minutes": 1440}, "processing": {"mode": "batch", "batch_sizes": {}}, "filters": {}},
        emit=lambda payload, output: emitted.append(payload),
        duration=lambda minutes: f"{minutes}m",
        normalize_batch_sizes=lambda value: dict(value or {}),
        include_youtube_breakdown=True,
        include_batch_limits=True,
        youtube_catalog_surfaces=lambda: ("videos", "shorts"),
    )
    assert result == 0
    assert emitted[0]["schema"] == "media2md.cli.creator_status/v1"
    assert emitted[0]["catalog_surface"] == "shorts"
    assert emitted[0]["catalog_surfaces"] == ["videos", "shorts"]
    assert emitted[0]["source_url"] == "https://www.youtube.com/@creator-name/shorts"
    assert emitted[1]["event"] == "creator_status_completed"
    assert emitted[1]["schema"] == "media2md.cli.creator_status_completed/v1"
