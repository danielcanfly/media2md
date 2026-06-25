from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest


def test_safe_artifact_stem_keeps_platform_id_out_of_cli_option_space():
    from media2md_runtime import safe_artifact_stem

    assert safe_artifact_stem("youtube", "-AHFhntQ07k") == "youtube_AHFhntQ07k"
    assert safe_artifact_stem("youtube", "dQw4w9WgXcQ") == "dQw4w9WgXcQ"
    assert not safe_artifact_stem("youtube", "-AHFhntQ07k").startswith("-")


def test_short_whisper_uses_equals_form_and_safe_name(tmp_path, monkeypatch):
    import generic_media

    media = tmp_path / "audio.mp3"
    media.write_bytes(b"audio")
    output = tmp_path / "transcripts"
    monkeypatch.setattr(generic_media, "_duration_seconds", lambda *a, **k: 10.0)
    monkeypatch.setattr(generic_media, "youtube_audio_settings", lambda: {
        "long_video_threshold_seconds": 2700,
        "chunk_seconds": 1800,
        "chunk_model": "test-model",
    })
    monkeypatch.setattr(generic_media, "command", lambda name: name)
    calls = []

    def fake_run(cmd, timeout=0):
        calls.append(cmd)
        value = next(item for item in cmd if item.startswith("--output-name="))
        name = value.split("=", 1)[1]
        out = Path(cmd[cmd.index("--output-dir") + 1])
        out.mkdir(parents=True, exist_ok=True)
        (out / f"{name}.txt").write_text("hello", encoding="utf-8")
        return type("Result", (), {"stdout": "", "stderr": ""})()

    monkeypatch.setattr(generic_media, "run", fake_run)
    result = generic_media.transcribe_audio(media, output, "-AHFhntQ07k", 10)
    assert result["text"] == "hello"
    assert "--output-name=youtube_AHFhntQ07k" in calls[0]
    assert "--output-name" not in calls[0]


def test_invalid_cli_argument_is_non_retryable():
    from media2md_runtime import classify_transcription_exception

    classification = classify_transcription_exception(RuntimeError("argument --output-name: expected one argument"))
    assert classification["error_code"] == "invalid_transcription_argument"
    assert classification["retryable"] is False
    assert classification["action_required"] is True


def test_completed_audio_manifest_is_resumable(tmp_path):
    import generic_media

    work = tmp_path / "work"
    work.mkdir()
    audio = work / "youtube_AHFhntQ07k.mp3"
    audio.write_bytes(b"complete-audio")
    generic_media._write_audio_manifest(
        work, audio,
        source_url="https://www.youtube.com/watch?v=-AHFhntQ07k",
        external_id="-AHFhntQ07k",
        strategy="anonymous_default",
        uses_auth=False,
    )
    cached = generic_media.find_cached_audio(
        work, "https://www.youtube.com/watch?v=-AHFhntQ07k", "-AHFhntQ07k"
    )
    assert cached is not None
    assert cached[0] == audio
    generic_media._cleanup_partial_downloads(work)
    assert audio.exists()


def test_unmanifested_partial_audio_is_removed(tmp_path):
    import generic_media

    work = tmp_path / "work"
    work.mkdir()
    partial = work / "partial.m4a"
    partial.write_bytes(b"partial")
    generic_media._cleanup_partial_downloads(work)
    assert not partial.exists()


def test_chunk_transcripts_resume_without_retranscribing(tmp_path, monkeypatch):
    import generic_media

    media = tmp_path / "long.mp3"
    media.write_bytes(b"audio")
    transcript_dir = tmp_path / "transcripts"
    chunks = []
    for index in range(2):
        chunk = tmp_path / f"chunk_{index:03d}.mp3"
        chunk.write_bytes(b"chunk")
        chunks.append(chunk)
    monkeypatch.setattr(generic_media, "_duration_seconds", lambda *a, **k: 4000.0)
    monkeypatch.setattr(generic_media, "youtube_audio_settings", lambda: {
        "long_video_threshold_seconds": 2700,
        "chunk_seconds": 1800,
        "chunk_model": "test-model",
    })
    monkeypatch.setattr(generic_media, "_split_audio", lambda *a, **k: (chunks, True))
    monkeypatch.setattr(generic_media, "command", lambda name: name)
    outputs = transcript_dir / "chunk_transcripts"
    outputs.mkdir(parents=True)
    (outputs / "chunk_000.txt").write_text("first", encoding="utf-8")
    calls = []

    def fake_run(cmd, timeout=0):
        calls.append(cmd)
        value = next(item for item in cmd if item.startswith("--output-name="))
        name = value.split("=", 1)[1]
        out = Path(cmd[cmd.index("--output-dir") + 1])
        (out / f"{name}.txt").write_text("second", encoding="utf-8")
        return type("Result", (), {"stdout": "", "stderr": ""})()

    monkeypatch.setattr(generic_media, "run", fake_run)
    result = generic_media.transcribe_audio(media, transcript_dir, "long-video", 4000)
    assert result["chunk_count"] == 2
    assert result["reused_chunk_transcripts"] == 1
    assert len(calls) == 1


def _configure_auth_session(tmp_path, monkeypatch, cookie_expiry: int):
    import media2md_youtube_session as session

    auth = tmp_path / "auth_profiles.json"
    auth.write_text(json.dumps({"schema_version": 4, "providers": {"youtube": {
        "mode": "browser_profile", "browser": "chrome", "profile": "Default",
        "profile_display_name": "Primary Profile",
    }}}), encoding="utf-8")
    root = tmp_path / "Chrome"
    (root / "Default" / "Network").mkdir(parents=True)
    (root / "Default" / "Network" / "Cookies").write_bytes(b"db")
    monkeypatch.setattr(session, "AUTH_PROFILES", auth)
    monkeypatch.setitem(session._BROWSER_ROOTS, "chrome", root)
    monkeypatch.setattr(session, "_command", lambda name: "yt-dlp")

    def fake_run(cmd, timeout=0):
        cookie_path = Path(cmd[cmd.index("--cookies") + 1])
        cookie_path.write_text(
            "# Netscape HTTP Cookie File\n"
            f".youtube.com\tTRUE\t/\tTRUE\t{cookie_expiry}\tSAPISID\tsecret\n",
            encoding="utf-8",
        )
        return type("Result", (), {"returncode": 0, "stdout": '{"id":"-AHFhntQ07k"}', "stderr": ""})()

    monkeypatch.setattr(session, "_run", fake_run)
    return session


def test_expired_cookie_is_detected_and_guided(tmp_path, monkeypatch):
    session = _configure_auth_session(tmp_path, monkeypatch, 1)
    payload = session.verify_youtube_session("-AHFhntQ07k")
    assert payload["authenticated"] is False
    assert payload["auth_state"] == "cookie_expired"
    assert payload["required_action"] == "reauthenticate_youtube_in_selected_profile"
    assert payload["guidance"]


def test_server_authenticated_cookie_is_strictly_verified(tmp_path, monkeypatch):
    session = _configure_auth_session(tmp_path, monkeypatch, 2147483647)
    monkeypatch.setattr(session, "_youtube_account_probe", lambda path: {
        "state": "authenticated", "authenticated": True, "error": None, "status": 200,
    })
    payload = session.verify_youtube_session("-AHFhntQ07k")
    assert payload["authenticated"] is True
    assert payload["auth_state"] == "authenticated"


def test_authenticated_download_fallback_requires_preflight(tmp_path, monkeypatch):
    import generic_media

    work = tmp_path / "work"
    work.mkdir()
    monkeypatch.setattr(generic_media, "youtube_audio_settings", lambda: {"audio_format": "mp3"})
    monkeypatch.setattr(generic_media, "auth_args", lambda provider: ["--cookies-from-browser", "chrome:Default"])
    monkeypatch.setattr(generic_media, "youtube_download_strategies", lambda *a, **k: [
        {"name": "anonymous_default", "client": "default", "uses_auth": False, "args": [], "auth_args": [], "format": "ba/b"},
        {"name": "authenticated_default", "client": "default", "uses_auth": True, "args": [], "auth_args": ["--cookies-from-browser", "chrome:Default"], "format": "ba/b"},
    ])
    monkeypatch.setattr(generic_media, "command", lambda name: name)
    monkeypatch.setattr(generic_media, "run", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("HTTP Error 403")))
    monkeypatch.setattr(generic_media, "verify_youtube_session", lambda *a, **k: {
        "authenticated": False, "auth_state": "cookie_expired",
        "required_action": "reauthenticate_youtube_in_selected_profile", "error": "expired",
    })
    with pytest.raises(generic_media.StageError) as caught:
        generic_media.download_youtube_audio(
            "https://www.youtube.com/watch?v=-AHFhntQ07k", work, "-AHFhntQ07k"
        )
    assert caught.value.error_code == "youtube_session_expired"
    assert caught.value.retryable is False


def test_doctor_does_not_claim_end_to_end_without_smoke(monkeypatch):
    import media2md_doctor

    monkeypatch.setattr(media2md_doctor, "command", lambda name: name)
    monkeypatch.setattr(media2md_doctor, "youtube_access_args", lambda **kwargs: [])
    monkeypatch.setattr(media2md_doctor, "auth_args", lambda provider: [])
    monkeypatch.setattr(media2md_doctor, "configured_youtube_profile", lambda: {})
    monkeypatch.setattr(media2md_doctor, "browser_safety_payload", lambda: {"browser_launch_allowed": False})
    monkeypatch.setattr(media2md_doctor, "_youtube_caption_probe", lambda *a, **k: {
        "caption_ready": False, "caption_files": [], "caption_probe_error": None,
    })
    monkeypatch.setattr(media2md_doctor, "youtube_download_strategies", lambda *a, **k: [{
        "name": "anonymous_default", "client": "default", "uses_auth": False,
        "args": [], "auth_args": [], "format": "ba/b",
    }])
    monkeypatch.setattr(media2md_doctor, "youtube_audio_settings", lambda: {
        "long_video_threshold_seconds": 2700, "chunk_seconds": 1800, "chunk_model": "test-model",
    })

    def fake_run(cmd, timeout=0):
        stdout = json.dumps({"duration": 596}) if "--dump-single-json" in cmd else ""
        return type("Result", (), {"returncode": 0, "stdout": stdout, "stderr": ""})()

    monkeypatch.setattr(media2md_doctor, "_run", fake_run)
    payload = media2md_doctor._access_probe(
        "youtube", "https://www.youtube.com/watch?v=-AHFhntQ07k"
    )
    assert payload["pipeline_ready"] is True
    assert payload["pipeline_readiness"] == "probable_not_end_to_end_verified"
    assert payload["fully_ready"] is False
    assert payload["pipeline_end_to_end_verified"] is False


def test_failed_transcription_preserves_completed_audio_checkpoint(tmp_path, monkeypatch):
    import generic_media

    downloads = tmp_path / "downloads"
    transcripts = tmp_path / "transcripts"
    markdown = tmp_path / "markdown"
    monkeypatch.setattr(generic_media, "DOWNLOADS", downloads)
    monkeypatch.setattr(generic_media, "TRANSCRIPTS", transcripts)
    monkeypatch.setattr(generic_media, "MARKDOWN", markdown)
    monkeypatch.setattr(generic_media, "REGISTRY_DB", tmp_path / "missing-registry.db")
    monkeypatch.setattr(generic_media, "try_youtube_captions", lambda *a, **k: (None, None))
    monkeypatch.setattr(generic_media, "youtube_access_args", lambda **k: [])

    def fake_download(source_url, work, external_id):
        media = work / "youtube_AHFhntQ07k.mp3"
        media.write_bytes(b"complete-audio")
        generic_media._write_audio_manifest(
            work, media, source_url=source_url, external_id=external_id,
            strategy="anonymous_default", uses_auth=False,
        )
        return media, "anonymous_default", False, [{
            "strategy": "anonymous_default", "client": "default",
            "uses_auth": False, "ok": True, "error": None,
        }]

    monkeypatch.setattr(generic_media, "download_youtube_audio", fake_download)
    monkeypatch.setattr(
        generic_media, "transcribe_audio",
        lambda *a, **k: (_ for _ in ()).throw(
            RuntimeError("argument --output-name: expected one argument")
        ),
    )

    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute("""
        CREATE TABLE media (
            id INTEGER PRIMARY KEY, provider TEXT, external_id TEXT,
            creator TEXT, title TEXT, description TEXT, source_url TEXT,
            published_at TEXT, duration_seconds REAL, status TEXT,
            markdown_path TEXT, markdown_sha256 TEXT, last_error TEXT,
            completed_at TEXT, updated_at TEXT
        )
    """)
    conn.execute("""
        INSERT INTO media(
            id, provider, external_id, creator, title, description,
            source_url, published_at, duration_seconds, status, updated_at
        ) VALUES(1, 'youtube', '-AHFhntQ07k', 'garytalksstuff',
                 'test', '', 'https://www.youtube.com/watch?v=-AHFhntQ07k',
                 '', 596, 'pending', '')
    """)
    conn.commit()
    row = conn.execute("SELECT * FROM media WHERE id=1").fetchone()

    with pytest.raises(generic_media.StageError) as caught:
        generic_media.process_row(conn, row)

    assert caught.value.error_code == "invalid_transcription_argument"
    assert caught.value.retryable is False
    work = downloads / "youtube" / "garytalksstuff" / "youtube_AHFhntQ07k"
    assert (work / "youtube_AHFhntQ07k.mp3").is_file()
    assert (work / "audio-manifest.json").is_file()


def test_command_failure_keeps_full_log_and_surfaces_root_cause(tmp_path, monkeypatch):
    import sys
    import media2md_runtime as runtime

    monkeypatch.setattr(runtime, "COMMAND_LOG_DIR", tmp_path / "logs")
    with pytest.raises(runtime.CommandExecutionError) as caught:
        runtime.run_logged([
            sys.executable, "-c",
            "import sys; print('usage: mlx_whisper ...'); "
            "print('error: argument --output-name: expected one argument', file=sys.stderr); "
            "raise SystemExit(2)",
        ], cwd=tmp_path, timeout=30, label="whisper-test")

    assert "expected one argument" in caught.value.root_cause
    assert caught.value.log_path.is_file()
    log = caught.value.log_path.read_text(encoding="utf-8")
    assert "usage: mlx_whisper" in log
    assert "error: argument --output-name: expected one argument" in log


def test_successful_leading_hyphen_video_writes_safe_markdown_and_keeps_original_id(tmp_path, monkeypatch):
    import generic_media

    downloads = tmp_path / "downloads"
    transcripts = tmp_path / "transcripts"
    markdown = tmp_path / "markdown"
    monkeypatch.setattr(generic_media, "ROOT", tmp_path)
    monkeypatch.setattr(generic_media, "DOWNLOADS", downloads)
    monkeypatch.setattr(generic_media, "TRANSCRIPTS", transcripts)
    monkeypatch.setattr(generic_media, "MARKDOWN", markdown)
    monkeypatch.setattr(generic_media, "REGISTRY_DB", tmp_path / "missing-registry.db")
    monkeypatch.setattr(generic_media, "try_youtube_captions", lambda *a, **k: (None, None))
    monkeypatch.setattr(generic_media, "youtube_access_args", lambda **k: [])

    def fake_download(source_url, work, external_id):
        media = work / "youtube_AHFhntQ07k.mp3"
        media.write_bytes(b"complete-audio")
        generic_media._write_audio_manifest(
            work, media, source_url=source_url, external_id=external_id,
            strategy="anonymous_default", uses_auth=False,
        )
        return media, "anonymous_default", False, [{
            "strategy": "anonymous_default", "client": "default",
            "uses_auth": False, "ok": True, "error": None,
        }]

    monkeypatch.setattr(generic_media, "download_youtube_audio", fake_download)
    monkeypatch.setattr(generic_media, "transcribe_audio", lambda *a, **k: {
        "text": "transcript text", "source": "local_whisper",
        "model": "test-model", "duration_seconds": 596.0,
        "chunk_count": 1, "chunk_seconds": None,
        "resumed_from_checkpoint": False,
    })

    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute("""
        CREATE TABLE media (
            id INTEGER PRIMARY KEY, provider TEXT, external_id TEXT,
            creator TEXT, title TEXT, description TEXT, source_url TEXT,
            published_at TEXT, duration_seconds REAL, status TEXT,
            markdown_path TEXT, markdown_sha256 TEXT, last_error TEXT,
            completed_at TEXT, updated_at TEXT
        )
    """)
    conn.execute("""
        INSERT INTO media(
            id, provider, external_id, creator, title, description,
            source_url, published_at, duration_seconds, status, updated_at
        ) VALUES(1, 'youtube', '-AHFhntQ07k', 'garytalksstuff',
                 'test', 'description',
                 'https://www.youtube.com/watch?v=-AHFhntQ07k',
                 '', 596, 'pending', '')
    """)
    conn.commit()
    row = conn.execute("SELECT * FROM media WHERE id=1").fetchone()
    final = generic_media.process_row(conn, row)

    assert final.name == "youtube_AHFhntQ07k.md"
    content = final.read_text(encoding="utf-8")
    assert 'media_id: "-AHFhntQ07k"' in content
    assert 'artifact_stem: "youtube_AHFhntQ07k"' in content
    assert "transcript text" in content
    assert not (downloads / "youtube" / "garytalksstuff" / "youtube_AHFhntQ07k").exists()
    assert not (transcripts / "youtube" / "garytalksstuff" / "youtube_AHFhntQ07k").exists()
