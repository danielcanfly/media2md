from __future__ import annotations

from media2md.bundle.scripts.public_cli_state_service import (
    agent_status_payload,
    apply_settings_updates,
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
    assert payload["creator_count"] == 2
    assert payload["providers"][0]["configured"] is True
    assert payload["providers"][1]["configured"] is True
    assert payload["providers"][2]["configured"] is False


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
    assert payload["ndjson_schema_version"] == 13
    assert payload["permissions"] == {"mode": "strict"}
    assert "creator run" in payload["commands"]["write"]
