from __future__ import annotations

import argparse
import json
import signal
from pathlib import Path

import pytest


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


def test_tls_errors_are_transient():
    import media2md_registry as registry
    from media2md_ytdlp import classify_access_error

    error = "curl: (35) TLS connect error: OPENSSL_internal:invalid library SSLError"
    assert registry._transient_error_text(error) is True
    result = classify_access_error("tiktok", error)
    assert result["error_code"] == "transient_network_error"
    assert result["retryable"] is True


def test_tiktok_transport_falls_back_to_plain(monkeypatch):
    import media2md_registry as registry

    monkeypatch.setattr(registry, "_tiktok_transport_strategies", lambda: [
        ("configured:chrome", ["--impersonate", "chrome"]),
        ("plain", []),
    ])
    monkeypatch.setattr(registry, "auth_args", lambda provider: [])
    calls: list[str] = []

    def fake_run(command, timeout=0, *, delays=None, strategy=None, **kwargs):
        calls.append(str(strategy))
        if strategy == "configured:chrome":
            raise RuntimeError("curl: (35) TLS connect error")
        return {"entries": []}

    monkeypatch.setattr(registry, "run_json", fake_run)
    payload, strategy, authenticated = registry._run_tiktok_catalog(
        ["yt-dlp", "--flat-playlist", "--dump-single-json"],
        "https://www.tiktok.com/@startupbell",
    )
    assert payload == {"entries": []}
    assert strategy == "plain"
    assert authenticated is False
    assert calls == ["configured:chrome", "plain"]


def test_capture_process_kills_group_on_keyboard_interrupt(monkeypatch):
    import media2md_registry as registry

    signals: list[int] = []

    class FakeProcess:
        pid = 43210
        returncode = None

        def communicate(self, timeout=None):
            raise KeyboardInterrupt

        def poll(self):
            return self.returncode

        def wait(self, timeout=None):
            self.returncode = 130
            return self.returncode

    monkeypatch.setattr(registry.subprocess, "Popen", lambda *a, **k: FakeProcess())
    monkeypatch.setattr(registry.os, "killpg", lambda pid, sig: signals.append(sig))
    with pytest.raises(KeyboardInterrupt):
        registry._capture_process(["yt-dlp"], 30)
    assert signals and signals[0] == signal.SIGINT


def test_failed_tiktok_page_keeps_checkpoint(tmp_path, monkeypatch):
    import media2md_registry as registry

    monkeypatch.setattr(registry, "DB", tmp_path / "media2md.db")
    monkeypatch.setattr(registry, "CHECKPOINT_DIR", tmp_path / "checkpoints")
    registry.CHECKPOINT_DIR.mkdir()
    checkpoint = registry.CHECKPOINT_DIR / "tiktok-startupbell.json"
    checkpoint.write_text(json.dumps({
        "schema_version": 3,
        "provider": "tiktok",
        "creator": "startupbell",
        "source_url": "https://www.tiktok.com/@startupbell",
        "mode": "full",
        "meta": {"handle": "startupbell", "external_id": "SECUID"},
        "tiktok_identifiers": ["SECUID"],
        "items": [],
        "next_start": 201,
    }))
    monkeypatch.setattr(
        registry,
        "_extract_tiktok_page",
        lambda *a, **k: (_ for _ in ()).throw(RuntimeError("curl: (35) TLS connect error")),
    )
    with pytest.raises(RuntimeError):
        registry.sync_creator("tiktok", "@startupbell", mode="full")
    saved = json.loads(checkpoint.read_text())
    assert saved["next_start"] == 201
    assert saved["tiktok_identifiers"] == ["SECUID"]


def test_quick_sync_preserves_last_full_exact_snapshot(tmp_path, monkeypatch):
    import media2md_registry as registry

    monkeypatch.setattr(registry, "DB", tmp_path / "media2md.db")
    monkeypatch.setattr(registry, "CHECKPOINT_DIR", tmp_path / "checkpoints")
    monkeypatch.setattr(registry, "CONFIG", tmp_path / "config.json")
    (tmp_path / "config.json").write_text(
        '{"providers":{"youtube":{"catalog_surfaces":["videos","shorts"],"long_video_threshold_seconds":2700}}}'
    )
    meta = {
        "external_id": "UC_TEST",
        "handle": "TheProductFolks",
        "display_name": "The Product Folks",
        "identifiers": {"channel_id": "UC_TEST", "uploader_id": "@TheProductFolks"},
    }

    def full_extract(provider, source_url, limit=None, start=None):
        if source_url.endswith("/videos"):
            return meta, [_yt_item("AAAAAAAAAAA", "youtube_video", "2026-06-24T00:00:00+00:00")]
        return meta, [_yt_item("BBBBBBBBBBB", "youtube_short", "2026-06-23T00:00:00+00:00")]

    monkeypatch.setattr(registry, "extract_catalog", full_extract)
    full = registry.sync_creator("youtube", "@TheProductFolks", mode="full")
    assert full["current_total"] == 2
    assert full["last_full_exact_total"] == 2

    quick = registry.sync_creator("youtube", "@TheProductFolks", mode="quick", quick_window=100)
    assert quick["current_total_exact"] is False
    assert quick["last_full_exact_total"] == 2
    assert quick["last_full_media_type_totals"] == {
        "youtube_video": 1,
        "youtube_short": 1,
        "youtube_stream": 0,
    }


def test_batch_start_lists_selected_media_ids(tmp_path, monkeypatch, capsys):
    import media2md_registry as registry

    monkeypatch.setattr(registry, "DB", tmp_path / "media2md.db")
    monkeypatch.setattr(registry, "CONFIG", tmp_path / "config.json")
    (tmp_path / "config.json").write_text('{"providers":{"youtube":{"long_video_threshold_seconds":2700}}}')
    conn = registry.connect()
    now = registry.iso_now()
    conn.execute(
        "INSERT INTO creators(provider,external_id,handle,source_url,created_at,updated_at) VALUES('youtube','UC','typed','https://www.youtube.com/@typed/videos',?,?)",
        (now, now),
    )
    creator_id = conn.execute("SELECT id FROM creators").fetchone()[0]
    conn.execute(
        """INSERT INTO media(provider,creator_id,external_id,source_url,duration_seconds,media_type,processing_class,is_current,status,published_at,created_at,updated_at)
           VALUES('youtube',?,'J92OMF6HUaM','https://www.youtube.com/watch?v=J92OMF6HUaM',4000,'youtube_video','youtube_long',1,'pending','2026-06-24',?,?)""",
        (creator_id, now, now),
    )
    conn.commit(); conn.close()
    monkeypatch.setattr(registry, "hydrate_youtube_duration_classes", lambda *a, **k: 0)
    monkeypatch.setattr(registry, "sync_generic_status_from_legacy", lambda *a, **k: None)

    class FakeProcess:
        returncode = 0
        pid = 99999
        def communicate(self, timeout=None): return "", ""

    monkeypatch.setattr(registry.subprocess, "Popen", lambda *a, **k: FakeProcess())
    code = registry.creator_run(
        "youtube", "typed", "batch", 100, 1, 10, False, 0,
        None, None, None, None, "newest_first", "human", 360,
        {"youtube_long": 1, "youtube_video": 5, "youtube_short": 30},
    )
    assert code == 0
    output = capsys.readouterr().out
    assert 'selected_media_ids=["J92OMF6HUaM"]' in output


def test_instagram_human_run_prints_completion_summary(monkeypatch, capsys):
    import social2md_core as core

    policy = {
        "processing": {"mode": "batch", "batch_size": 30, "max_batches": 0, "max_runtime_minutes": 360, "max_failures": 10, "stop_on_failure": False, "sleep_between_batches": 0},
        "filters": {"since": None, "until": None, "rank_from": None, "rank_to": None, "order": "newest_first"},
        "sync": {"full_every_minutes": 10080, "quick_window": 100},
    }
    monkeypatch.setattr(core, "normalize_creator", lambda value: "career_cleo")
    monkeypatch.setattr(core, "load_config", lambda: {"timezone": "Asia/Tokyo"})
    monkeypatch.setattr(core, "effective_policy", lambda username: policy)
    monkeypatch.setattr(core, "ui_locale", lambda non_interactive: "en")
    monkeypatch.setattr(core, "sync_once", lambda *a, **k: (0, {}))
    counts = iter([30, 0])
    monkeypatch.setattr(core, "filtered_candidate_count", lambda *a, **k: next(counts))
    monkeypatch.setattr(core, "stream_engine", lambda *a, **k: (0, {"completed": "30", "failed": "0"}))
    monkeypatch.setattr(core, "save_performance_samples", lambda *a, **k: None)
    monkeypatch.setattr(core, "load_performance_samples", lambda *a, **k: [])
    args = argparse.Namespace(
        creator="career_cleo", non_interactive=False, output="human", mode="batch", batch_size=30,
        since=None, until=None, rank_from=None, rank_to=None, order=None, max_batches=1,
        max_runtime_minutes=360, max_failures=10, stop_on_failure=False,
        sleep_between_batches=0, skip_sync=False, force_full_sync=False, retry_failed=False,
        pause_seconds=0,
    )
    assert core.run_creator(args) == 0
    output = capsys.readouterr().out
    assert "CREATOR_RUN_COMPLETED provider=instagram creator=career_cleo" in output
    assert "processed=30 completed=30 failures=0 remaining=0" in output

def test_v073_install_guide_is_fail_fast_and_versioned():
    root = Path(__file__).resolve().parents[1]
    guide = (root / "MEDIA2MD_V073_INSTALL.md").read_text()
    assert "set -euo pipefail" in guide
    assert 'test -f "$ZIP"' in guide
    assert "install_media2md_v073.py" in guide
    assert "media2md 0.7.3" in guide
