from __future__ import annotations

import subprocess

from media2md.probe import ProbeResult, probe_command


def test_probe_result_ok_property():
    assert ProbeResult("ok").ok is True
    assert ProbeResult("error").ok is False


def test_probe_command_missing(monkeypatch):
    monkeypatch.setattr("shutil.which", lambda _cmd: None)
    result = probe_command("yt-dlp")
    assert result.status == "missing"


def test_probe_command_broken_on_exec_error(monkeypatch):
    monkeypatch.setattr("shutil.which", lambda _cmd: "/fake/tool")

    def fake_run(*_args, **_kwargs):
        raise FileNotFoundError()

    monkeypatch.setattr("subprocess.run", fake_run)
    result = probe_command("yt-dlp", package="yt-dlp")
    assert result.status == "broken"
    assert "pip install -U yt-dlp" in result.hint


def test_probe_command_timeout(monkeypatch):
    monkeypatch.setattr("shutil.which", lambda _cmd: "/fake/tool")

    def fake_run(*_args, **_kwargs):
        raise subprocess.TimeoutExpired(cmd=["/fake/tool"], timeout=10)

    monkeypatch.setattr("subprocess.run", fake_run)
    result = probe_command("yt-dlp")
    assert result.status == "timeout"


def test_probe_command_error(monkeypatch):
    monkeypatch.setattr("shutil.which", lambda _cmd: "/fake/tool")
    monkeypatch.setattr(
        "subprocess.run",
        lambda *_args, **_kwargs: subprocess.CompletedProcess(
            ["/fake/tool"], 1, "", "failed"
        ),
    )
    result = probe_command("yt-dlp")
    assert result.status == "error"
    assert result.output == "failed"


def test_probe_command_ok(monkeypatch):
    monkeypatch.setattr("shutil.which", lambda _cmd: "/fake/tool")
    monkeypatch.setattr(
        "subprocess.run",
        lambda *_args, **_kwargs: subprocess.CompletedProcess(
            ["/fake/tool"], 0, "2026.06.29", ""
        ),
    )
    result = probe_command("yt-dlp")
    assert result.status == "ok"
    assert result.output == "2026.06.29"
