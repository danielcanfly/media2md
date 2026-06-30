from __future__ import annotations

import argparse

from media2md.bundle.scripts import media2md_update as update


def test_update_payload_wraps_schema_and_sections():
    payload = update.update_payload(
        event="update_check_failed",
        status="warn",
        summary="Update check failed; retry later",
        data={"error": "boom", "retry_after_hours": 24},
    )
    assert payload["event"] == "update_check_failed"
    assert payload["schema"] == "media2md.cli.update_check_failed/v1"
    assert payload["status"] == "warn"
    assert payload["sections"][0]["name"] == "update"
    assert payload["error"] == "boom"


def test_update_check_if_due_skipped_emits_schema(monkeypatch, capsys):
    monkeypatch.setattr(update, "due_for_check", lambda: False)
    monkeypatch.setattr(update.sys, "argv", ["media2md_update.py", "check-if-due", "--output", "ndjson"])
    assert update.main() == 0
    out = capsys.readouterr().out
    assert '"event": "update_check_skipped"' in out
    assert '"schema": "media2md.cli.update_check_skipped/v1"' in out


def test_update_check_raw_payload_uses_release_status_not_top_level_status(monkeypatch):
    monkeypatch.setattr(update, "github_release", lambda repo: {"status": "no_release_published"})
    payload = update.check("danielcanfly/media2md", persist=False)
    assert "status" not in payload
    assert payload["release_status"] == "no_release_published"
