from __future__ import annotations

import json

from media2md.results import HealthResult
from media2md.bundle.scripts.public_cli_state_service import (
    agent_status_payload,
    apply_settings_updates,
    creator_catalog_metadata,
    provider_auth_rows,
    registry_rows,
    render_creator_status,
    settings_payload,
    system_status_payload,
)
from media2md.bundle.scripts import media2md_registry


class _Args:
    instagram_backend = None
    instagram_catalog_surface = None
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
    args.instagram_catalog_surface = "mixed"
    args.youtube_caption_languages = "ja,en"
    args.youtube_audio_strategies = "direct,proxy"
    args.youtube_long_video_threshold_minutes = 7
    args.youtube_chunk_minutes = 3
    args.tiktok_impersonate = "chrome"
    args.update_check_every_days = 2
    args.update_check_on_use = True
    config = apply_settings_updates({}, args)
    assert config["providers"]["instagram"]["backend"] == "gallery-dl"
    assert config["providers"]["instagram"]["catalog_surface"] == "mixed"
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


def test_creator_catalog_metadata_derives_instagram_surface_from_source_url():
    metadata = creator_catalog_metadata(
        {"provider": "instagram", "source_url": "https://www.instagram.com/creator.name/reels/"}
    )
    assert metadata["source_url"] == "https://www.instagram.com/creator.name/reels/"
    assert metadata["catalog_surface"] == "reels"
    assert metadata["catalog_surfaces"] == ["reels"]

    mixed_like = creator_catalog_metadata(
        {"provider": "instagram", "source_url": "https://www.instagram.com/creator.name/"}
    )
    assert mixed_like["catalog_surface"] == "posts"
    assert mixed_like["catalog_surfaces"] == ["reels", "posts"]


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


def test_render_creator_status_human_includes_instagram_catalog_metadata(capsys):
    class _Args:
        output = "human"

    result = render_creator_status(
        _Args(),
        rows=[{
            "provider": "instagram",
            "handle": "creator.name",
            "source_url": "https://www.instagram.com/creator.name/",
            "current_total": 8,
            "current_total_exact": 1,
            "tracked": 8,
            "completed": 0,
            "remaining": 8,
            "last_full_exact_total": 8,
            "last_full_exact_at": "2026-06-30T00:00:00+00:00",
        }],
        effective_policy=lambda provider, creator: {"sync": {"enabled": True, "every_minutes": 60, "full_every_minutes": 1440}, "processing": {"mode": "batch", "batch_sizes": {}}, "filters": {}},
        emit=lambda payload, output: None,
        duration=lambda minutes: f"{minutes}m",
        normalize_batch_sizes=lambda value: dict(value or {}),
        include_youtube_breakdown=True,
        include_batch_limits=True,
        youtube_catalog_surfaces=lambda: ("videos", "shorts"),
    )
    assert result == 0
    out = capsys.readouterr().out
    assert "SOURCE surface=posts catalog_surfaces=reels,posts" in out


def test_registry_rows_count_current_catalog_progress_separately(tmp_path):
    registry_db = tmp_path / "media2md.db"
    conn = __import__("sqlite3").connect(registry_db)
    try:
        conn.execute(
            """CREATE TABLE creators (
                id INTEGER PRIMARY KEY,
                provider TEXT NOT NULL,
                handle TEXT NOT NULL,
                source_url TEXT,
                current_total INTEGER,
                current_total_exact INTEGER,
                youtube_video_total INTEGER,
                youtube_video_total_exact INTEGER,
                youtube_shorts_total INTEGER,
                youtube_shorts_total_exact INTEGER,
                youtube_streams_total INTEGER,
                youtube_streams_total_exact INTEGER,
                last_sync_mode TEXT,
                last_sync_at TEXT,
                last_full_sync_at TEXT,
                last_full_exact_total INTEGER,
                last_full_exact_at TEXT,
                last_full_youtube_video_total INTEGER,
                last_full_youtube_shorts_total INTEGER,
                last_full_youtube_streams_total INTEGER
            )"""
        )
        conn.execute(
            """CREATE TABLE media (
                id INTEGER PRIMARY KEY,
                provider TEXT NOT NULL,
                creator_id INTEGER NOT NULL,
                external_id TEXT NOT NULL,
                source_url TEXT NOT NULL,
                status TEXT NOT NULL,
                is_current INTEGER NOT NULL
            )"""
        )
        conn.execute(
            """INSERT INTO creators (
                id, provider, handle, source_url, current_total, current_total_exact,
                youtube_video_total, youtube_video_total_exact, youtube_shorts_total, youtube_shorts_total_exact,
                youtube_streams_total, youtube_streams_total_exact, last_sync_mode, last_sync_at,
                last_full_sync_at, last_full_exact_total, last_full_exact_at,
                last_full_youtube_video_total, last_full_youtube_shorts_total, last_full_youtube_streams_total
            ) VALUES (1, 'bilibili', '1510588366', 'https://space.bilibili.com/1510588366', 2, 1, 0, 0, 0, 0, 0, 0,
                'full', '2026-07-01T00:00:00+00:00', '2026-07-01T00:00:00+00:00', 2, '2026-07-01T00:00:00+00:00', 0, 0, 0)"""
        )
        conn.executemany(
            "INSERT INTO media (id, provider, creator_id, external_id, source_url, status, is_current) VALUES (?, ?, ?, ?, ?, ?, ?)",
            [
                (1, "bilibili", 1, "old-video", "https://www.bilibili.com/video/old-video", "completed", 0),
                (2, "bilibili", 1, "current-video-1", "https://www.bilibili.com/video/current-video-1", "pending", 1),
                (3, "bilibili", 1, "current-video-2", "https://www.bilibili.com/video/current-video-2", "pending", 1),
            ],
        )
        conn.commit()
    finally:
        conn.close()

    rows = registry_rows(registry_db, include_youtube_totals=True)

    assert len(rows) == 1
    row = rows[0]
    assert row["tracked"] == 2
    assert row["completed"] == 0
    assert row["remaining"] == 2
    assert row["lifetime_tracked"] == 3
    assert row["lifetime_completed"] == 1
    assert row["historical_tracked"] == 1


def test_refresh_legacy_preserves_instagram_catalog_profile_url(tmp_path, monkeypatch):
    registry_db = tmp_path / "media2md.db"
    legacy_db = tmp_path / "state.db"
    catalog_dir = tmp_path / "creator_catalogs"
    catalog_dir.mkdir(parents=True, exist_ok=True)

    monkeypatch.setattr(media2md_registry, "DB", registry_db)
    monkeypatch.setattr(media2md_registry, "LEGACY_INSTAGRAM_DB", legacy_db)
    monkeypatch.setattr(media2md_registry, "LEGACY_INSTAGRAM_CATALOG_DIR", catalog_dir)

    conn = media2md_registry.connect()
    conn.close()

    old = __import__("sqlite3").connect(legacy_db)
    try:
        old.execute("CREATE TABLE creators (id INTEGER PRIMARY KEY, username TEXT NOT NULL, enabled INTEGER NOT NULL)")
        old.execute(
            "CREATE TABLE videos (id INTEGER PRIMARY KEY, creator_id INTEGER NOT NULL, shortcode TEXT, source_url TEXT, published_at TEXT, caption TEXT, status TEXT, markdown_path TEXT, markdown_sha256 TEXT, last_error TEXT, created_at TEXT, updated_at TEXT, completed_at TEXT)"
        )
        old.execute("INSERT INTO creators (id, username, enabled) VALUES (1, 'creator.name', 1)")
        old.commit()
    finally:
        old.close()

    (catalog_dir / "creator.name.json").write_text(
        json.dumps({
            "creator": "creator.name",
            "profile_url": "https://www.instagram.com/creator.name/",
            "current_total": 3,
            "current_total_exact": True,
            "last_full_sync_at": "2026-06-30T00:00:00+00:00",
            "updated_at": "2026-06-30T00:00:00+00:00",
        }),
        encoding="utf-8",
    )

    media2md_registry.refresh_legacy()

    conn = media2md_registry.connect()
    try:
        row = conn.execute(
            "SELECT source_url FROM creators WHERE provider='instagram' AND handle='creator.name'"
        ).fetchone()
    finally:
        conn.close()
    assert row is not None
    assert row["source_url"] == "https://www.instagram.com/creator.name/"
