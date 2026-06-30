from __future__ import annotations

import argparse
import sqlite3
from pathlib import Path

import pytest

from media2md.bundle.scripts.public_cli_maintenance_service import repair_active_states_common, repair_workspace_common


def test_repair_active_states_requires_yes(tmp_path):
    with pytest.raises(RuntimeError):
        repair_active_states_common(argparse.Namespace(yes=False), root=tmp_path, iso_now=lambda: "now", registry=lambda args: 0)


def test_repair_active_states_updates_matching_rows(tmp_path, capsys):
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    db = data_dir / "media2md.db"
    conn = sqlite3.connect(db)
    conn.executescript(
        """
        CREATE TABLE media (id INTEGER PRIMARY KEY, status TEXT, last_error TEXT, updated_at TEXT);
        INSERT INTO media (status, last_error, updated_at) VALUES ('downloading', NULL, NULL);
        """
    )
    conn.commit()
    conn.close()
    result = repair_active_states_common(
        argparse.Namespace(yes=True),
        root=tmp_path,
        iso_now=lambda: "2026-06-30T00:00:00+00:00",
        registry=lambda args: 0,
    )
    out = capsys.readouterr().out
    assert result == 0
    assert "ACTIVE_STATES_REPAIRED" in out
    payload = out.splitlines()[1:]
    assert '"event": "repair_active_states"' in "\n".join(payload)
    assert '"schema": "media2md.cli.repair_active_states/v1"' in "\n".join(payload)


def test_repair_workspace_requires_yes(tmp_path):
    with pytest.raises(RuntimeError):
        repair_workspace_common(argparse.Namespace(yes=False), root=tmp_path)


def test_repair_workspace_cleans_files_when_no_active_rows(tmp_path, capsys):
    target = tmp_path / "workspace" / "downloads"
    target.mkdir(parents=True)
    (target / "sample.txt").write_text("ok", encoding="utf-8")
    result = repair_workspace_common(argparse.Namespace(yes=True), root=tmp_path)
    out = capsys.readouterr().out
    assert result == 0
    assert "WORKSPACE_REPAIRED" in out
    payload = out.splitlines()[1:]
    assert '"event": "repair_workspace"' in "\n".join(payload)
    assert '"schema": "media2md.cli.repair_workspace/v1"' in "\n".join(payload)
    assert target.exists()
