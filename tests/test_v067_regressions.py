from __future__ import annotations

import importlib.util
import json
import os
import sqlite3
import sys
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


def test_completed_generic_audio_manifest_is_resumable(tmp_path):
    import generic_media

    work = tmp_path / "work"
    work.mkdir()
    audio = work / "clip.m4a"
    audio.write_bytes(b"complete-audio")
    generic_media._write_audio_manifest(
        work, audio,
        source_url="https://www.tiktok.com/@example/video/123",
        external_id="123",
        strategy="direct-plain",
        uses_auth=False,
    )
    cached = generic_media.find_cached_audio(
        work, "https://www.tiktok.com/@example/video/123", "123"
    )
    assert cached is not None
    assert cached[0] == audio


def test_filter_youtube_sponsor_segments_removes_high_signal_ad_copy():
    import generic_media

    payload = generic_media.filter_youtube_sponsor_segments(
        "\n\n".join([
            "Today we are breaking down the benchmark results and what changed in the release.",
            "This video is sponsored by Acme Cloud. Use code ACME10 at the link in the description for a discount code and affiliate link details.",
            "Now back to the main comparison of latency, throughput, and memory use.",
        ])
    )

    assert payload["filtered"] is True
    assert payload["removed_count"] == 1
    assert "This video is sponsored by Acme Cloud" not in payload["text"]
    assert "benchmark results" in payload["text"]
    assert "Now back to the main comparison" in payload["text"]


def test_filter_youtube_sponsor_segments_keeps_normal_content():
    import generic_media

    text = "\n\n".join([
        "Today we review the architecture changes in the new release.",
        "The next section explains how the queue, retries, and storage layout work.",
    ])
    payload = generic_media.filter_youtube_sponsor_segments(text)

    assert payload["filtered"] is False
    assert payload["removed_count"] == 0
    assert payload["text"] == text


def test_filter_youtube_sponsor_segments_supports_off_and_aggressive_modes():
    import generic_media

    text = "\n\n".join([
        "Today we review the architecture changes in the new release.",
        "Check out Acme Cloud at the link in the description and start your free trial today.",
        "The next section explains how the queue works.",
    ])

    off_payload = generic_media.filter_youtube_sponsor_segments(text, mode="off")
    aggressive_payload = generic_media.filter_youtube_sponsor_segments(text, mode="aggressive")

    assert off_payload["filtered"] is False
    assert off_payload["reason"] == "disabled"
    assert off_payload["text"] == text
    assert aggressive_payload["filtered"] is True
    assert aggressive_payload["removed_count"] == 1
    assert "free trial" not in aggressive_payload["text"]
    assert aggressive_payload["reason"] == "youtube_sponsor_filter_aggressive"


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


def test_youtube_captions_skip_audio_download_and_transcription(tmp_path, monkeypatch):
    import generic_media

    downloads = tmp_path / "downloads"
    transcripts = tmp_path / "transcripts"
    markdown = tmp_path / "markdown"
    monkeypatch.setattr(generic_media, "ROOT", tmp_path)
    monkeypatch.setattr(generic_media, "DOWNLOADS", downloads)
    monkeypatch.setattr(generic_media, "TRANSCRIPTS", transcripts)
    monkeypatch.setattr(generic_media, "MARKDOWN", markdown)
    monkeypatch.setattr(generic_media, "REGISTRY_DB", tmp_path / "missing-registry.db")
    monkeypatch.setattr(generic_media, "youtube_sponsor_filter_mode", lambda: "conservative")
    monkeypatch.setattr(
        generic_media,
        "try_youtube_captions",
        lambda *a, **k: ("caption line 1\ncaption line 2", "en"),
    )
    monkeypatch.setattr(generic_media, "youtube_access_args", lambda **k: [])
    monkeypatch.setattr(
        generic_media,
        "download_youtube_audio",
        lambda *a, **k: (_ for _ in ()).throw(AssertionError("audio download should not run when captions exist")),
    )
    monkeypatch.setattr(
        generic_media,
        "transcribe_audio",
        lambda *a, **k: (_ for _ in ()).throw(AssertionError("transcription should not run when captions exist")),
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
        ) VALUES(1, 'youtube', 'dQw4w9WgXcQ', 'creator-name',
                 'captioned video', 'description',
                 'https://www.youtube.com/watch?v=dQw4w9WgXcQ',
                 '', 213, 'pending', '')
    """)
    conn.commit()
    row = conn.execute("SELECT * FROM media WHERE id=1").fetchone()

    result = generic_media.process_row(conn, row)
    final = Path(result["final_path"])

    assert final.is_file()
    content = final.read_text(encoding="utf-8")
    assert 'transcription_source: "youtube_captions"' in content
    assert 'caption_language: "en"' in content
    assert 'caption_probe_result: "hit"' in content
    assert 'transcript_filter_reason: "no_sponsor_segments_detected"' in content
    assert 'sponsor_filter_applied: false' in content
    assert 'sponsor_segments_filtered: 0' in content
    assert "caption line 1" in content
    assert "caption line 2" in content
    assert not (downloads / "youtube" / "creator-name" / "dQw4w9WgXcQ").exists()
    assert not (transcripts / "youtube" / "creator-name" / "dQw4w9WgXcQ").exists()


def test_youtube_captions_render_filtered_sponsor_appendix(tmp_path, monkeypatch):
    import generic_media

    downloads = tmp_path / "downloads"
    transcripts = tmp_path / "transcripts"
    markdown = tmp_path / "markdown"
    monkeypatch.setattr(generic_media, "ROOT", tmp_path)
    monkeypatch.setattr(generic_media, "DOWNLOADS", downloads)
    monkeypatch.setattr(generic_media, "TRANSCRIPTS", transcripts)
    monkeypatch.setattr(generic_media, "MARKDOWN", markdown)
    monkeypatch.setattr(generic_media, "REGISTRY_DB", tmp_path / "missing-registry.db")
    monkeypatch.setattr(generic_media, "youtube_sponsor_filter_mode", lambda: "conservative")
    monkeypatch.setattr(
        generic_media,
        "try_youtube_captions",
        lambda *a, **k: (
            "\n\n".join([
                "Today we are covering the benchmark results.",
                "This video is sponsored by Acme Cloud. Use code ACME10 at the link in the description for a discount code.",
                "Now back to the performance analysis.",
            ]),
            "en",
        ),
    )
    monkeypatch.setattr(generic_media, "youtube_access_args", lambda **k: [])

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
        ) VALUES(1, 'youtube', 'dQw4w9WgXcQ', 'creator-name',
                 'captioned video', 'description',
                 'https://www.youtube.com/watch?v=dQw4w9WgXcQ',
                 '', 213, 'pending', '')
    """)
    conn.commit()
    row = conn.execute("SELECT * FROM media WHERE id=1").fetchone()

    result = generic_media.process_row(conn, row)
    final = Path(result["final_path"])
    content = final.read_text(encoding="utf-8")

    assert 'sponsor_filter_applied: true' in content
    assert 'caption_probe_result: "hit"' in content
    assert 'transcript_filter_reason: "youtube_sponsor_filter_conservative"' in content
    assert 'sponsor_segments_filtered: 1' in content
    assert "Today we are covering the benchmark results." in content
    assert "Now back to the performance analysis." in content
    transcript_section = content.split("## Transcript", 1)[1].split("## Filtered Sponsor Segments", 1)[0]
    assert "This video is sponsored by Acme Cloud" not in transcript_section
    assert "This video is sponsored by Acme Cloud" in content.split("## Filtered Sponsor Segments", 1)[1]


def test_youtube_audio_fallback_marks_caption_probe_result(tmp_path, monkeypatch):
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
    monkeypatch.setattr(generic_media, "youtube_sponsor_filter_mode", lambda: "off")

    def fake_download(source_url, work, external_id):
        media = work / "sample.mp3"
        media.write_bytes(b"audio")
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
        "text": "spoken content only",
        "source": "local_whisper",
        "model": "test-model",
        "duration_seconds": 120.0,
        "chunk_count": 1,
        "chunk_seconds": None,
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
        ) VALUES(1, 'youtube', 'abc123xyz00', 'creator-name',
                 'audio fallback video', 'description',
                 'https://www.youtube.com/watch?v=abc123xyz00',
                 '', 120, 'pending', '')
    """)
    conn.commit()
    row = conn.execute("SELECT * FROM media WHERE id=1").fetchone()

    result = generic_media.process_row(conn, row)
    final = Path(result["final_path"])
    content = final.read_text(encoding="utf-8")

    assert 'caption_probe_result: "fallback_to_audio"' in content
    assert 'transcription_source: "local_whisper"' in content
    assert 'transcript_filter_reason: "disabled"' in content
    assert 'sponsor_filter_mode: "off"' in content


def test_bilibili_captions_skip_audio_download_and_transcription(tmp_path, monkeypatch):
    import generic_media

    downloads = tmp_path / "downloads"
    transcripts = tmp_path / "transcripts"
    markdown = tmp_path / "markdown"
    monkeypatch.setattr(generic_media, "ROOT", tmp_path)
    monkeypatch.setattr(generic_media, "DOWNLOADS", downloads)
    monkeypatch.setattr(generic_media, "TRANSCRIPTS", transcripts)
    monkeypatch.setattr(generic_media, "MARKDOWN", markdown)
    monkeypatch.setattr(generic_media, "REGISTRY_DB", tmp_path / "missing-registry.db")
    monkeypatch.setattr(
        generic_media,
        "try_bilibili_captions",
        lambda *a, **k: ("字幕第一行\n字幕第二行", "zh-CN"),
    )
    monkeypatch.setattr(
        generic_media,
        "download_bilibili_audio",
        lambda *a, **k: (_ for _ in ()).throw(AssertionError("audio download should not run when bilibili captions exist")),
    )
    monkeypatch.setattr(
        generic_media,
        "transcribe_audio",
        lambda *a, **k: (_ for _ in ()).throw(AssertionError("transcription should not run when bilibili captions exist")),
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
        ) VALUES(1, 'bilibili', 'BV1xx411c7mD', 'creator-name',
                 'captioned bilibili video', 'description',
                 'https://www.bilibili.com/video/BV1xx411c7mD',
                 '', 213, 'pending', '')
    """)
    conn.commit()
    row = conn.execute("SELECT * FROM media WHERE id=1").fetchone()

    result = generic_media.process_row(conn, row)
    final = Path(result["final_path"])

    assert final.is_file()
    content = final.read_text(encoding="utf-8")
    assert 'transcription_source: "bilibili_captions"' in content
    assert 'caption_language: "zh-CN"' in content
    assert 'caption_probe_result: "hit"' in content
    assert "字幕第一行" in content
    assert "字幕第二行" in content
    assert not (downloads / "bilibili" / "creator-name" / "BV1xx411c7mD").exists()
    assert not (transcripts / "bilibili" / "creator-name" / "BV1xx411c7mD").exists()


def test_bilibili_audio_fallback_marks_caption_probe_result(tmp_path, monkeypatch):
    import generic_media

    downloads = tmp_path / "downloads"
    transcripts = tmp_path / "transcripts"
    markdown = tmp_path / "markdown"
    monkeypatch.setattr(generic_media, "ROOT", tmp_path)
    monkeypatch.setattr(generic_media, "DOWNLOADS", downloads)
    monkeypatch.setattr(generic_media, "TRANSCRIPTS", transcripts)
    monkeypatch.setattr(generic_media, "MARKDOWN", markdown)
    monkeypatch.setattr(generic_media, "REGISTRY_DB", tmp_path / "missing-registry.db")
    monkeypatch.setattr(generic_media, "try_bilibili_captions", lambda *a, **k: (None, None))

    def fake_download(source_url, work, external_id):
        media = work / "sample.m4a"
        media.write_bytes(b"audio")
        generic_media._write_audio_manifest(
            work, media, source_url=source_url, external_id=external_id,
            strategy="bilibili-api-audio-stream", uses_auth=False,
        )
        return media, "bilibili-api-audio-stream", False, [{
            "strategy": "bilibili-api-audio-stream", "client": "bilibili-api",
            "uses_auth": False, "ok": True, "error": None,
        }]

    monkeypatch.setattr(generic_media, "download_bilibili_audio", fake_download)
    monkeypatch.setattr(generic_media, "transcribe_audio", lambda *a, **k: {
        "text": "spoken bilibili content",
        "source": "local_whisper",
        "model": "test-model",
        "duration_seconds": 120.0,
        "chunk_count": 1,
        "chunk_seconds": None,
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
        ) VALUES(1, 'bilibili', 'BV1xx411c7mD', 'creator-name',
                 'audio fallback bilibili video', 'description',
                 'https://www.bilibili.com/video/BV1xx411c7mD',
                 '', 120, 'pending', '')
    """)
    conn.commit()
    row = conn.execute("SELECT * FROM media WHERE id=1").fetchone()

    result = generic_media.process_row(conn, row)
    final = Path(result["final_path"])
    content = final.read_text(encoding="utf-8")

    assert 'caption_probe_result: "fallback_to_audio"' in content
    assert 'transcription_source: "local_whisper"' in content
    assert "spoken bilibili content" in content


def test_bilibili_creator_catalog_412_falls_back_to_ytdlp(tmp_path, monkeypatch):
    import media2md_registry as registry

    monkeypatch.setattr(registry, "DB", tmp_path / "media2md.db")
    monkeypatch.setattr(registry, "CHECKPOINT_DIR", tmp_path / "checkpoints")
    monkeypatch.setattr(registry, "CONFIG", tmp_path / "config.json")
    (tmp_path / "config.json").write_text("{}", encoding="utf-8")

    class _User:
        def __init__(self, mid: int):
            self.mid = mid

        async def get_user_info(self):
            raise RuntimeError("ERROR: Request is blocked by server (412), please wait and try later.")

        async def get_videos(self, ps=30, pn=1):
            raise AssertionError("official API page fetch should not run after 412 user info failure")

    payload = {
        "id": "2",
        "entries": [
            {
                "id": "BV172421f7Km",
                "url": "https://www.bilibili.com/video/BV172421f7Km?spm_id_from=333.1007",
                "title": "BV172421f7Km",
            },
            {
                "id": "BV1xx411c7mD",
                "url": "https://www.bilibili.com/video/BV1xx411c7mD",
                "title": "BV1xx411c7mD",
                "timestamp": 1252458549,
            },
        ],
    }

    def fake_run_json(command_line, timeout, **kwargs):
        assert command_line[-1] == "https://space.bilibili.com/2"
        assert "--flat-playlist" in command_line
        assert "--dump-single-json" in command_line
        assert kwargs.get("strategy") == "bilibili-space-fallback"
        return payload

    monkeypatch.setitem(sys.modules, "bilibili_api.user", type("user_module", (), {"User": _User})())
    monkeypatch.setattr(registry, "command", lambda name: name)
    monkeypatch.setattr(registry, "run_json", fake_run_json)

    meta, items = registry._extract_bilibili_catalog("https://space.bilibili.com/2", limit=100, start=1)

    assert meta["external_id"] == "2"
    assert meta["handle"] == "2"
    assert meta["source_url"] == "https://space.bilibili.com/2"
    assert meta["identifiers"] == {"mid": "2"}
    assert [item["external_id"] for item in items] == ["BV1xx411c7mD", "BV172421f7Km"]
    assert items[0]["source_url"] == "https://www.bilibili.com/video/BV1xx411c7mD"
    assert items[0]["published_at"] == "2009-09-09T01:09:09+00:00"
    assert items[1]["source_url"] == "https://www.bilibili.com/video/BV172421f7Km"
    assert items[1]["media_type"] == "bilibili_video"
    assert items[1]["processing_class"] == "bilibili_video"


def test_social2md_uses_source_root_for_scripts_when_project_root_is_external(tmp_path, monkeypatch):
    root = Path(__file__).resolve().parents[1]
    script_path = root / "src" / "media2md" / "bundle" / "scripts" / "social2md.py"
    module_name = "social2md_source_root_regression"
    spec = importlib.util.spec_from_file_location(module_name, script_path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    original = os.environ.get("MEDIA2MD_PROJECT_ROOT")
    monkeypatch.setenv("MEDIA2MD_PROJECT_ROOT", str(tmp_path / "external-project-root"))
    sys.modules[module_name] = module
    spec.loader.exec_module(module)

    try:
        assert module.ROOT == (tmp_path / "external-project-root").resolve()
        assert module.SOURCE_ROOT == root / "src" / "media2md" / "bundle"
        assert module.CORE == module.SOURCE_ROOT / "scripts" / "social2md_core.py"
        assert module.REGISTRY == module.SOURCE_ROOT / "scripts" / "media2md_registry.py"
        assert module.GENERIC == module.SOURCE_ROOT / "scripts" / "generic_media.py"
        assert module.CONFIG == module.ROOT / "config" / "social2md.json"
        assert not str(module.CORE).startswith(str(module.ROOT / "scripts"))
        assert not str(module.REGISTRY).startswith(str(module.ROOT / "scripts"))
    finally:
        sys.modules.pop(module_name, None)
        if original is None:
            os.environ.pop("MEDIA2MD_PROJECT_ROOT", None)
        else:
            os.environ["MEDIA2MD_PROJECT_ROOT"] = original


def test_media2md_uses_source_root_for_scripts_when_project_root_is_external(tmp_path, monkeypatch):
    root = Path(__file__).resolve().parents[1]
    script_path = root / "src" / "media2md" / "bundle" / "scripts" / "media2md.py"
    module_name = "media2md_source_root_regression"
    spec = importlib.util.spec_from_file_location(module_name, script_path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    original = os.environ.get("MEDIA2MD_PROJECT_ROOT")
    monkeypatch.setenv("MEDIA2MD_PROJECT_ROOT", str(tmp_path / "external-project-root"))
    sys.modules[module_name] = module
    spec.loader.exec_module(module)

    try:
        assert module.ROOT == (tmp_path / "external-project-root").resolve()
        assert module.SOURCE_ROOT == root / "src" / "media2md" / "bundle"
        assert module.CORE == module.SOURCE_ROOT / "scripts" / "social2md_core.py"
        assert module.REGISTRY == module.SOURCE_ROOT / "scripts" / "media2md_registry.py"
        assert module.GENERIC == module.SOURCE_ROOT / "scripts" / "generic_media.py"
        assert module.CONFIG == module.ROOT / "config" / "social2md.json"
        assert not str(module.CORE).startswith(str(module.ROOT / "scripts"))
        assert not str(module.REGISTRY).startswith(str(module.ROOT / "scripts"))
    finally:
        sys.modules.pop(module_name, None)
        if original is None:
            os.environ.pop("MEDIA2MD_PROJECT_ROOT", None)
        else:
            os.environ["MEDIA2MD_PROJECT_ROOT"] = original


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


def test_worker_commands_stay_in_current_process_group(monkeypatch):
    import generic_media
    import process_worker_impl as worker
    import media2md_runtime as runtime

    calls: list[dict[str, object]] = []

    def fake_run_logged(command, **kwargs):
        calls.append({
            "command": command,
            "start_new_session": kwargs.get("start_new_session"),
            "cwd": kwargs.get("cwd"),
        })
        return runtime.subprocess.CompletedProcess(command, 0, "", "")

    monkeypatch.setattr(generic_media, "run_logged", fake_run_logged)
    monkeypatch.setattr(worker, "run_logged", fake_run_logged)

    generic_media.run(["yt-dlp", "--version"], timeout=30)
    worker.run_command(["gallery-dl", "--version"], timeout=30)

    assert [call["start_new_session"] for call in calls] == [False, False]


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
    result = generic_media.process_row(conn, row)
    final = Path(result["final_path"])

    assert final.name == "youtube_AHFhntQ07k.md"
    content = final.read_text(encoding="utf-8")
    assert 'media_id: "-AHFhntQ07k"' in content
    assert 'artifact_stem: "youtube_AHFhntQ07k"' in content
    assert "transcript text" in content
    assert not (downloads / "youtube" / "garytalksstuff" / "youtube_AHFhntQ07k").exists()
    assert not (transcripts / "youtube" / "garytalksstuff" / "youtube_AHFhntQ07k").exists()
