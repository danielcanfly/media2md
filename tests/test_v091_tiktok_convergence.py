from __future__ import annotations

import argparse
import json
import sqlite3
from pathlib import Path


def test_tiktok_setting_is_authenticated_even_if_bundle_mentions_captcha(monkeypatch):
    import media2md_auth as auth

    class Response:
        status = 200
        def geturl(self): return "https://www.tiktok.com/setting"
        def read(self, _limit): return b"window.__bundle='captcha verify to continue';"
        def __enter__(self): return self
        def __exit__(self, *_args): return False

    class Opener:
        def open(self, *_args, **_kwargs): return Response()

    monkeypatch.setattr(auth.urllib.request, "build_opener", lambda *_args: Opener())
    assert auth._probe("tiktok", object()) == (
        "authenticated", 200, "https://www.tiktok.com/setting", None,
    )


def test_tiktok_challenge_redirect_remains_challenge(monkeypatch):
    import media2md_auth as auth

    class Response:
        status = 200
        def geturl(self): return "https://www.tiktok.com/verify/challenge"
        def read(self, _limit): return b"verify to continue"
        def __enter__(self): return self
        def __exit__(self, *_args): return False

    class Opener:
        def open(self, *_args, **_kwargs): return Response()

    monkeypatch.setattr(auth.urllib.request, "build_opener", lambda *_args: Opener())
    assert auth._probe("tiktok", object())[0] == "platform_challenge"


def test_tiktok_inspect_falls_back_to_completed_registry_cache(tmp_path, monkeypatch, capsys):
    import generic_media as media

    registry = tmp_path / "media2md.db"
    conn = sqlite3.connect(registry)
    conn.executescript(
        """
        CREATE TABLE creators (
          id INTEGER PRIMARY KEY, provider TEXT, handle TEXT,
          external_id TEXT, display_name TEXT
        );
        CREATE TABLE media (
          id INTEGER PRIMARY KEY, provider TEXT, creator_id INTEGER,
          external_id TEXT, title TEXT, description TEXT, source_url TEXT,
          published_at TEXT, duration_seconds REAL, status TEXT,
          markdown_path TEXT, completed_at TEXT, updated_at TEXT,
          is_current INTEGER
        );
        INSERT INTO creators VALUES (1,'tiktok','antscreation','SECUID','Ants Creation');
        INSERT INTO media VALUES (
          1,'tiktok',1,'7338632507950189826','Cached title','Cached description',
          'https://www.tiktok.com/@antscreation/video/7338632507950189826',
          '2026-02-23T00:00:00+00:00',54,'completed','markdown/tiktok/item.md',
          '2026-06-25T09:00:00+00:00','2026-06-25T09:00:00+00:00',1
        );
        """
    )
    conn.commit(); conn.close()

    monkeypatch.setattr(media, "REGISTRY_DB", registry)
    monkeypatch.setattr(media, "DB", tmp_path / "missing.db")
    monkeypatch.setattr(media, "_tiktok_download_strategies", lambda _creator: [
        {"name": "direct-plain", "args": [], "authenticated": False, "auth_args": []},
    ])
    monkeypatch.setattr(media, "command", lambda name: name)
    monkeypatch.setattr(media, "run", lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("curl: (35) TLS connect error")))

    result = media.inspect_tiktok_metadata(
        "https://www.tiktok.com/@antscreation/video/7338632507950189826",
        "antscreation", "7338632507950189826",
    )
    output = capsys.readouterr().out
    assert result["id"] == "7338632507950189826"
    assert result["title"] == "Cached title"
    assert result["_media2md_metadata_source"] == "registry_cache"
    assert "TIKTOK_INSPECT_FALLBACK" in output
    assert "source=registry_cache" in output


def test_tiktok_doctor_uses_recent_real_completion_when_live_probe_is_transient(monkeypatch):
    import media2md_doctor as doctor
    import generic_media as media

    base = {
        "event": "tiktok_access_doctor", "provider": "tiktok",
        "metadata_ready": False, "audio_download_ready": False,
        "download_ready": False, "pipeline_ready": False,
        "pipeline_readiness": "not_ready", "pipeline_end_to_end_verified": False,
        "fully_ready": False, "ffmpeg_ready": True,
        "transcription_cli_ready": True, "transcription_smoke_tested": True,
        "transcription_smoke_ready": True,
        "error": "curl: (35) TLS connect error", "error_code": "transient_network_error",
        "retryable": True, "action_required": False, "required_action": None,
    }
    monkeypatch.setattr(doctor, "_access_probe", lambda *_args, **_kwargs: dict(base))
    monkeypatch.setattr(media, "inspect_tiktok_metadata", lambda *_args, **_kwargs: {
        "id": "7338632507950189826", "duration": 54,
        "_media2md_metadata_source": "registry_cache",
    })
    monkeypatch.setattr(media, "download_tiktok_audio", lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("temporary TLS failure")))
    monkeypatch.setattr(media, "tiktok_recent_completion", lambda *_args, **_kwargs: {
        "completed_at": "2026-06-25T09:00:00+00:00",
        "markdown_path": "/tmp/item.md", "markdown_sha256": "abc", "age_hours": 1.0,
    })

    payload = doctor.tiktok_access_payload("7338632507950189826", "antscreation", transcription_smoke_test=True)
    assert payload["pipeline_ready"] is True
    assert payload["fully_ready"] is False
    assert payload["degraded"] is True
    assert payload["live_probe_ready"] is False
    assert payload["pipeline_end_to_end_verified"] is True
    assert payload["metadata_source"] == "registry_cache"
    assert payload["error_code"] == "transient_network_error"


def test_v091_installer_and_active_versions_are_consistent():
    import importlib.util
    import media2md
    import media2md.bootstrap as bootstrap

    root = Path(__file__).resolve().parents[1]
    installer_path = root / "docs" / "archive" / "installers" / "install_media2md_v091.py"
    spec = importlib.util.spec_from_file_location("installer_v091", installer_path)
    assert spec and spec.loader
    installer = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(installer)

    assert installer.VERSION == "0.9.1"
    assert media2md.__version__ == "0.9.1"
    assert bootstrap.VERSION == "0.9.1"
    assert 'VERSION = "0.9.1"' in (root / "src/media2md/bundle/scripts/media2md.py").read_text()
    assert 'VERSION = "0.9.1"' in (root / "src/media2md/bundle/scripts/social2md.py").read_text()
