from __future__ import annotations

import sqlite3
from pathlib import Path


def _yt_item(media_id: str, media_type: str, published: str, duration: float = 60.0):
    return {
        "external_id": media_id,
        "title": media_id,
        "description": "",
        "source_url": f"https://www.youtube.com/watch?v={media_id}",
        "published_at": published,
        "duration_seconds": duration,
        "media_type": media_type,
        "processing_class": media_type,
    }


def test_youtube_surface_urls_share_one_creator():
    from media2md_types import youtube_surface_urls

    urls = youtube_surface_urls("https://www.youtube.com/@TheProductFolks/shorts")
    assert urls == {
        "videos": "https://www.youtube.com/@TheProductFolks/videos",
        "shorts": "https://www.youtube.com/@TheProductFolks/shorts",
    }


def test_youtube_full_sync_merges_videos_and_shorts_with_exact_totals(tmp_path, monkeypatch):
    import media2md_registry as registry

    monkeypatch.setattr(registry, "DB", tmp_path / "media2md.db")
    monkeypatch.setattr(registry, "CHECKPOINT_DIR", tmp_path / "checkpoints")
    monkeypatch.setattr(registry, "CONFIG", tmp_path / "social2md.json")
    (tmp_path / "social2md.json").write_text(
        '{"providers":{"youtube":{"catalog_surfaces":["videos","shorts"],"long_video_threshold_seconds":2700}}}'
    )

    meta = {
        "external_id": "UC_TEST",
        "handle": "TheProductFolks",
        "display_name": "The Product Folks",
        "identifiers": {"channel_id": "UC_TEST", "uploader_id": "@TheProductFolks"},
    }

    def fake_extract(provider, source_url, limit=None, start=None):
        assert provider == "youtube"
        if source_url.endswith("/videos"):
            return meta, [
                _yt_item("AAAAAAAAAAA", "youtube_video", "2026-06-24T00:00:00+00:00", 900),
                _yt_item("BBBBBBBBBBB", "youtube_video", "2026-06-23T00:00:00+00:00", 50),
            ]
        assert source_url.endswith("/shorts")
        return meta, [
            _yt_item("BBBBBBBBBBB", "youtube_short", "2026-06-23T00:00:00+00:00", 50),
            _yt_item("CCCCCCCCCCC", "youtube_short", "2026-06-22T00:00:00+00:00", 45),
        ]

    monkeypatch.setattr(registry, "extract_catalog", fake_extract)
    result = registry.sync_creator("youtube", "@TheProductFolks", mode="full")
    assert result["current_total"] == 3
    assert result["current_total_exact"] is True
    assert result["youtube_video_total"] == 1
    assert result["youtube_video_total_exact"] is True
    assert result["youtube_shorts_total"] == 2
    assert result["youtube_shorts_total_exact"] is True

    conn = registry.connect()
    rows = conn.execute("SELECT external_id,media_type FROM media ORDER BY external_id").fetchall()
    assert [(r["external_id"], r["media_type"]) for r in rows] == [
        ("AAAAAAAAAAA", "youtube_video"),
        ("BBBBBBBBBBB", "youtube_short"),
        ("CCCCCCCCCCC", "youtube_short"),
    ]
    conn.close()


def _typed_selection_db(tmp_path, monkeypatch):
    import media2md_registry as registry

    monkeypatch.setattr(registry, "DB", tmp_path / "typed.db")
    monkeypatch.setattr(registry, "CONFIG", tmp_path / "config.json")
    (tmp_path / "config.json").write_text('{"providers":{"youtube":{"long_video_threshold_seconds":2700}}}')
    conn = registry.connect()
    now = registry.iso_now()
    conn.execute(
        "INSERT INTO creators(provider,external_id,handle,source_url,created_at,updated_at) VALUES('youtube','UC','typed','https://www.youtube.com/@typed/videos',?,?)",
        (now, now),
    )
    creator_id = conn.execute("SELECT id FROM creators").fetchone()[0]
    return registry, conn, creator_id, now


def test_youtube_long_video_is_exclusive_batch(tmp_path, monkeypatch):
    registry, conn, creator_id, now = _typed_selection_db(tmp_path, monkeypatch)
    monkeypatch.setattr(registry, "hydrate_youtube_duration_classes", lambda *a, **k: 0)
    items = [
        ("LONGVIDEO01", "youtube_video", "youtube_long", 4000),
        ("NORMALVID01", "youtube_video", "youtube_video", 800),
        ("SHORTVIDEO1", "youtube_short", "youtube_short", 40),
    ]
    for index, (media_id, media_type, item_class, duration) in enumerate(items):
        conn.execute(
            """INSERT INTO media(provider,creator_id,external_id,source_url,duration_seconds,media_type,processing_class,is_current,status,published_at,created_at,updated_at)
               VALUES('youtube',?,?,?,?,?,?,1,'pending',?,?,?)""",
            (creator_id, media_id, f"https://www.youtube.com/watch?v={media_id}", duration, media_type, item_class, f"2026-06-{24-index:02d}", now, now),
        )
    conn.commit()
    clauses = ["m.creator_id=?", "m.is_current=1", "m.status NOT IN ('completed','skipped')"]
    rows = registry._select_typed_batch(
        conn, "youtube", clauses, [creator_id], "DESC", 100,
        {"youtube_long": 1, "youtube_video": 5, "youtube_short": 30},
    )
    assert [row["external_id"] for row in rows] == ["LONGVIDEO01"]
    conn.close()


def test_youtube_typed_batch_combines_normal_and_shorts_without_long(tmp_path, monkeypatch):
    registry, conn, creator_id, now = _typed_selection_db(tmp_path, monkeypatch)
    monkeypatch.setattr(registry, "hydrate_youtube_duration_classes", lambda *a, **k: 0)
    for index in range(4):
        media_id = f"VIDEO{index:06d}"[-11:]
        conn.execute(
            """INSERT INTO media(provider,creator_id,external_id,source_url,duration_seconds,media_type,processing_class,is_current,status,published_at,created_at,updated_at)
               VALUES('youtube',?,?,?,?,?,'youtube_video',1,'pending',?,?,?)""",
            (creator_id, media_id, f"https://www.youtube.com/watch?v={media_id}", 800, "youtube_video", f"2026-06-{24-index:02d}", now, now),
        )
    for index in range(5):
        media_id = f"SHORT{index:06d}"[-11:]
        conn.execute(
            """INSERT INTO media(provider,creator_id,external_id,source_url,duration_seconds,media_type,processing_class,is_current,status,published_at,created_at,updated_at)
               VALUES('youtube',?,?,?,?,?,'youtube_short',1,'pending',?,?,?)""",
            (creator_id, media_id, f"https://www.youtube.com/watch?v={media_id}", 40, "youtube_short", f"2026-05-{24-index:02d}", now, now),
        )
    conn.commit()
    clauses = ["m.creator_id=?", "m.is_current=1", "m.status NOT IN ('completed','skipped')"]
    rows = registry._select_typed_batch(
        conn, "youtube", clauses, [creator_id], "DESC", 100,
        {"youtube_long": 1, "youtube_video": 2, "youtube_short": 3},
    )
    composition = registry._batch_composition(rows)
    assert composition == {"youtube_video": 2, "youtube_short": 3}
    conn.close()


def test_manual_short_updates_creator_counts_and_invalidates_exact_snapshot(tmp_path, monkeypatch):
    import generic_media
    import media2md_registry as registry

    registry_db = tmp_path / "media2md.db"
    monkeypatch.setattr(registry, "DB", registry_db)
    monkeypatch.setattr(registry, "CONFIG", tmp_path / "config.json")
    monkeypatch.setattr(generic_media, "REGISTRY_DB", registry_db)
    (tmp_path / "config.json").write_text('{"providers":{"youtube":{"long_video_threshold_seconds":2700}}}')

    generic_media.ensure_registry({
        "provider": "youtube",
        "external_id": "0jttCFj5ZWM",
        "creator": "TheProductFolks",
        "creator_external_id": "UC_TEST",
        "creator_identifiers": {"channel_id": "UC_TEST"},
        "creator_display_name": "The Product Folks",
        "title": "Short",
        "description": "",
        "source_url": "https://www.youtube.com/shorts/0jttCFj5ZWM",
        "published_at": None,
        "duration_seconds": 30,
        "media_type": "youtube_short",
        "processing_class": "youtube_short",
    })
    conn = registry.connect()
    creator = conn.execute("SELECT * FROM creators WHERE external_id='UC_TEST'").fetchone()
    assert creator["current_total"] == 1
    assert creator["current_total_exact"] == 0
    assert creator["youtube_shorts_total"] == 1
    assert creator["youtube_shorts_total_exact"] == 0
    conn.close()


def test_batch_size_assignment_contract():
    from media2md_types import parse_batch_size_assignments

    assert parse_batch_size_assignments([
        "tiktok_video=100", "instagram_reel=30", "youtube_short=30",
        "youtube_video=5", "youtube_long=1",
    ]) == {
        "tiktok_video": 100,
        "instagram_reel": 30,
        "youtube_short": 30,
        "youtube_video": 5,
        "youtube_long": 1,
    }
