from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path


def test_cursor_summary_uses_command_start_snapshot():
    import media2md_registry as registry

    summary = {
        "current_total": 715,
        "current_total_exact": False,
        "last_full_exact_total": None,
        "last_full_media_type_totals": {},
    }
    result = registry._apply_cursor_run_snapshot(summary, {
        "current_total": 655,
        "current_total_exact": False,
        "media_type_totals": {"tiktok_video": 655},
    })
    assert result["previous_current_total"] == 655
    assert result["current_total"] == 715
    assert result["new_since_last_sync"] == 60
    assert result["removed_since_last_sync"] == 0
    assert result["previous_media_type_totals"] == {"tiktok_video": 655}


def test_cursor_failed_public_attempt_always_emits_result(monkeypatch, capsys):
    import media2md_registry as registry

    monkeypatch.setattr(registry, "command", lambda name: "/usr/bin/curl")
    monkeypatch.setattr(registry, "auth_args", lambda provider: ["--cookies", "/tmp/cookies.txt"])
    monkeypatch.setattr(registry, "_proxy_environment", lambda: ({"PATH": "/usr/bin"}, []))
    calls = {"count": 0}

    def fake_capture(command, timeout, **kwargs):
        calls["count"] += 1
        if calls["count"] == 1:
            return subprocess.CompletedProcess(command, 56, "", "Connection closed abruptly")
        return subprocess.CompletedProcess(command, 0, json.dumps({"itemList": [], "hasMorePrevious": False}), "")

    monkeypatch.setattr(registry, "_capture_process", fake_capture)
    payload, authenticated = registry._run_tiktok_cursor_request(
        "MS4wLjABAAAA_CURSOR_TEST", 1_700_000_000_000, 15,
        "7250000000000000001", "https://www.tiktok.com/@startupbell",
        timeout_seconds=60,
    )
    output = capsys.readouterr().out
    assert payload["hasMorePrevious"] is False
    assert authenticated is True
    assert "authenticated=false status=failed reason=connection_closed" in output
    assert "authenticated=true status=success" in output


def test_partial_tiktok_catalog_skips_legacy_quick_sync(monkeypatch, capsys):
    import social2md

    monkeypatch.setattr(social2md, "refresh_auth", lambda provider: None)
    monkeypatch.setattr(social2md, "effective_policy", lambda provider, creator: {
        "sync": {"quick_window": 100},
        "processing": {
            "mode": "batch", "batch_size": 5, "max_batches": 1,
            "max_runtime_minutes": 60, "max_failures": 1,
            "sleep_between_batches": 0, "stop_on_failure": False,
        },
        "filters": {"order": "newest_first", "since": None, "until": None,
                    "rank_from": None, "rank_to": None},
    })
    monkeypatch.setattr(social2md, "registry_rows", lambda: [{
        "provider": "tiktok", "handle": "startupbell", "tracked": 655,
        "current_total_exact": 0, "last_sync_at": "2026-06-24T00:00:00+00:00",
    }])
    calls = []
    monkeypatch.setattr(social2md, "registry", lambda command: calls.append(command) or 0)
    args = argparse.Namespace(
        provider="tiktok", creator="@startupbell", mode="batch", batch_size=5,
        max_batches=1, max_runtime_minutes=60, max_failures=1,
        sleep_between_batches=0, stop_on_failure=False, since=None, until=None,
        rank_from=None, rank_to=None, order="newest_first", allow_stale_catalog=False,
        output="human",
    )
    assert social2md.creator_run(args) == 0
    output = capsys.readouterr().out
    assert "AUTO_SYNC_SKIPPED provider=tiktok" in output
    assert len(calls) == 1
    assert calls[0][0] == "run"
    assert "sync" not in calls[0]


def test_tiktok_download_cascade_prefers_direct_and_saves_hint(tmp_path, monkeypatch, capsys):
    import generic_media

    work = tmp_path / "work"
    work.mkdir()
    hint = tmp_path / "state" / "tiktok_download_transport.json"
    monkeypatch.setattr(generic_media, "TIKTOK_DOWNLOAD_HINT", hint)
    monkeypatch.setattr(generic_media, "auth_args", lambda provider: ["--cookies", "/tmp/tiktok-cookies.txt"])
    monkeypatch.setattr(generic_media, "impersonation_args", lambda provider: ["--impersonate", "chrome"])
    monkeypatch.setattr(generic_media, "_macos_proxy_types", lambda: ["http", "https", "socks"])
    monkeypatch.setattr(generic_media, "command", lambda name: "/usr/bin/yt-dlp")
    calls = []

    def fake_run(command, timeout=7200):
        calls.append(command)
        if "--cookies" not in command:
            raise RuntimeError("Connection closed abruptly")
        (work / "video.m4a").write_bytes(b"audio")
        return subprocess.CompletedProcess(command, 0, "", "")

    monkeypatch.setattr(generic_media, "run", fake_run)
    media, strategy, used_auth, attempts = generic_media.download_tiktok_audio(
        "https://www.tiktok.com/@startupbell/video/1234567890123456789",
        work, "1234567890123456789", "startupbell", str(work / "video.%(ext)s"),
    )
    output = capsys.readouterr().out
    assert media.name == "video.m4a"
    assert strategy == "direct-plain"
    assert used_auth is True
    assert len(attempts) == 2
    assert all("--proxy" in command and "" in command for command in calls)
    assert not any("--impersonate" in command for command in calls)
    saved = json.loads(hint.read_text())
    assert saved["creators"]["startupbell"]["strategy"] == "direct-plain"
    assert saved["creators"]["startupbell"]["authenticated"] is True
    assert "status=failed reason=connection_closed" in output
    assert "status=success" in output


def test_creator_run_summary_exists_for_max_failure_stop(capsys):
    import media2md_registry as registry

    registry._creator_run_summary(
        provider="tiktok", handle="startupbell", batches=1, processed=5,
        failures=1, status="stopped_max_failures", remaining=646, output="human",
    )
    output = capsys.readouterr().out
    assert "CREATOR_RUN_COMPLETED" in output
    assert "status=stopped_max_failures" in output
    assert "processed=5 completed=4 failures=1 remaining=646" in output


def test_v081_acceptance_covers_batch_network_and_reporting():
    root = Path(__file__).resolve().parents[1]
    text = (root / "docs" / "archive" / "acceptance" / "STRICT_ACCEPTANCE_V081.md").read_text()
    for token in (
        "previous_current_total", "new_since_last_sync", "AUTO_SYNC_SKIPPED",
        "TIKTOK_DOWNLOAD_ATTEMPT", "direct-plain", "CREATOR_RUN_COMPLETED",
    ):
        assert token in text


def test_release_build_excludes_bundled_runtime_database():
    root = Path(__file__).resolve().parents[1]
    build_script = (root / "tools" / "build_release_assets.py").read_text()
    pyproject = (root / "pyproject.toml").read_text()
    assert "('src', 'media2md', 'bundle', 'data')" in build_script
    assert '"src/media2md/bundle/data/**"' in pyproject
    assert '"docs/archive/**"' in pyproject
