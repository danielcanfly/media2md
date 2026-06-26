from __future__ import annotations

import os
import shutil
import sqlite3
import subprocess
import sys
from pathlib import Path


def _write_executable(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    path.chmod(0o755)


def _create_partial_registry(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    try:
        conn.executescript(
            """
            CREATE TABLE creators (
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
            );
            CREATE TABLE media (
                id INTEGER PRIMARY KEY,
                creator_id INTEGER NOT NULL,
                status TEXT NOT NULL,
                is_current INTEGER NOT NULL
            );
            INSERT INTO creators (
                id, provider, handle, source_url, current_total, current_total_exact,
                youtube_video_total, youtube_video_total_exact,
                youtube_shorts_total, youtube_shorts_total_exact,
                youtube_streams_total, youtube_streams_total_exact,
                last_sync_mode, last_sync_at
            ) VALUES (
                1, 'tiktok', 'startupbell', 'https://www.tiktok.com/@startupbell',
                835, 0, 0, 0, 0, 0, 0, 0, 'partial', '2026-06-24T00:00:00+00:00'
            );
            INSERT INTO media (id, creator_id, status, is_current)
            VALUES (1, 1, 'pending', 1);
            """
        )
        conn.commit()
    finally:
        conn.close()


def test_public_bin_media2md_skips_quick_sync_for_partial_tiktok_catalog(tmp_path: Path):
    source_root = Path(__file__).resolve().parents[1]
    project = tmp_path / "project"
    scripts = project / "scripts"
    bin_dir = project / "bin"
    scripts.mkdir(parents=True)
    bin_dir.mkdir(parents=True)

    for name in (
        "media2md.py",
        "creator_run_shared.py",
        "media2md_urls.py",
        "media2md_types.py",
    ):
        shutil.copy2(source_root / "src" / "media2md" / "bundle" / "scripts" / name, scripts / name)
    shutil.copy2(source_root / "bin" / "media2md", bin_dir / "media2md")
    (bin_dir / "media2md").chmod(0o755)

    _write_executable(
        scripts / "media2md_auth.py",
        "#!/usr/bin/env python3\nraise SystemExit(0)\n",
    )
    _write_executable(
        scripts / "media2md_update.py",
        "#!/usr/bin/env python3\nraise SystemExit(0)\n",
    )
    _write_executable(
        scripts / "media2md_registry.py",
        """#!/usr/bin/env python3
import sys

def refresh_legacy():
    return None

if __name__ == '__main__':
    if sys.argv[1:2] == ['sync']:
        print('LEGACY_QUICK_SYNC_CALLED')
        raise SystemExit(91)
    if sys.argv[1:2] == ['run']:
        print('BATCH_START provider=tiktok creator=startupbell batch=1/1 selected=1')
        print('CREATOR_RUN_COMPLETED provider=tiktok creator=startupbell status=completed batches=1 processed=1 completed=1 failures=0 remaining=0')
        raise SystemExit(0)
    raise SystemExit(0)
""",
    )
    for name in ("social2md_core.py", "generic_media.py", "media2md_doctor.py"):
        _write_executable(scripts / name, "#!/usr/bin/env python3\nraise SystemExit(0)\n")

    _create_partial_registry(project / "data" / "media2md.db")
    (project / "config").mkdir(parents=True)

    env = os.environ.copy()
    env["PYTHON"] = sys.executable
    env["MEDIA2MD_UPDATE_CHECK_ON_USE"] = "0"
    result = subprocess.run(
        [
            str(bin_dir / "media2md"),
            "creator", "run", "@startupbell",
            "--provider", "tiktok",
            "--mode", "batch",
            "--batch-size-type", "tiktok_video=1",
            "--max-batches", "1",
            "--max-failures", "1",
        ],
        cwd=project,
        env=env,
        text=True,
        capture_output=True,
        timeout=30,
        check=False,
    )
    combined = result.stdout + result.stderr
    assert result.returncode == 0, combined
    assert "AUTO_SYNC_SKIPPED provider=tiktok" in combined
    assert "reason=full_catalog_in_progress" in combined
    assert "BATCH_START provider=tiktok" in combined
    assert "CREATOR_RUN_COMPLETED provider=tiktok" in combined
    assert "LEGACY_QUICK_SYNC_CALLED" not in combined
    assert "SYNC_NETWORK_CONTEXT" not in combined
    assert '"sync_mode": "quick"' not in combined


def test_both_public_surfaces_use_shared_creator_run_decision():
    root = Path(__file__).resolve().parents[1]
    scripts = root / "src" / "media2md" / "bundle" / "scripts"
    for name in ("media2md.py", "social2md.py"):
        text = (scripts / name).read_text(encoding="utf-8")
        assert "from creator_run_shared import prepare_catalog_for_creator_run" in text
        assert "sync_code = prepare_catalog_for_creator_run(" in text
        assert "partial_tiktok_catalog = bool(" not in text
        creator_run_body = text.split('def creator_run', 1)[1].split('def add_creator', 1)[0]
        assert 'registry(["sync",provider,args.creator' not in creator_run_body


def test_v081_acceptance_records_live_failure_instead_of_false_pass():
    root = Path(__file__).resolve().parents[1]
    text = (root / "docs" / "archive" / "acceptance" / "STRICT_ACCEPTANCE_V081.md").read_text(encoding="utf-8")
    row = next(line for line in text.splitlines() if "Partial TikTok Full Sync skips legacy Quick Sync before Batch" in line)
    assert "| FAIL |" in row
    assert "public `./bin/media2md creator run`" in row


def test_v082_acceptance_requires_public_cli_e2e():
    root = Path(__file__).resolve().parents[1]
    text = (root / "docs" / "archive" / "acceptance" / "STRICT_ACCEPTANCE_V082.md").read_text(encoding="utf-8")
    for token in (
        "public `./bin/media2md`",
        "AUTO_SYNC_SKIPPED",
        "LEGACY_QUICK_SYNC_CALLED",
        "single shared implementation",
    ):
        assert token in text


def test_public_bin_media2md_skips_quick_sync_for_exact_tiktok_catalog(tmp_path: Path):
    source_root = Path(__file__).resolve().parents[1]
    project = tmp_path / "project"
    scripts = project / "scripts"
    bin_dir = project / "bin"
    scripts.mkdir(parents=True)
    bin_dir.mkdir(parents=True)
    for name in ("media2md.py", "creator_run_shared.py", "media2md_urls.py", "media2md_types.py"):
        shutil.copy2(source_root / "src" / "media2md" / "bundle" / "scripts" / name, scripts / name)
    shutil.copy2(source_root / "bin" / "media2md", bin_dir / "media2md")
    (bin_dir / "media2md").chmod(0o755)
    _write_executable(scripts / "media2md_auth.py", "#!/usr/bin/env python3\nraise SystemExit(0)\n")
    _write_executable(scripts / "media2md_update.py", "#!/usr/bin/env python3\nraise SystemExit(0)\n")
    _write_executable(
        scripts / "media2md_registry.py",
        """#!/usr/bin/env python3
import sys

def refresh_legacy():
    return None

if __name__ == '__main__':
    if sys.argv[1:2] == ['sync']:
        print('LEGACY_QUICK_SYNC_CALLED')
        raise SystemExit(91)
    if sys.argv[1:2] == ['run']:
        print('BATCH_START provider=tiktok creator=startupbell batch=1/1 selected=1')
        print('CREATOR_RUN_COMPLETED provider=tiktok creator=startupbell status=completed batches=1 processed=1 completed=1 failures=0 remaining=0')
        raise SystemExit(0)
    raise SystemExit(0)
""",
    )
    for name in ("social2md_core.py", "generic_media.py", "media2md_doctor.py"):
        _write_executable(scripts / name, "#!/usr/bin/env python3\nraise SystemExit(0)\n")
    _create_partial_registry(project / "data" / "media2md.db")
    conn = sqlite3.connect(project / "data" / "media2md.db")
    conn.execute(
        "UPDATE creators SET current_total=1159,current_total_exact=1,last_full_exact_total=1159,last_full_exact_at='2026-06-24T17:31:01+00:00'"
    )
    conn.commit()
    conn.close()
    (project / "config").mkdir(parents=True)
    env = os.environ.copy()
    env["PYTHON"] = sys.executable
    env["MEDIA2MD_UPDATE_CHECK_ON_USE"] = "0"
    result = subprocess.run(
        [
            str(bin_dir / "media2md"), "creator", "run", "@startupbell",
            "--provider", "tiktok", "--mode", "batch", "--batch-size-type", "tiktok_video=1",
            "--max-batches", "1", "--max-failures", "1",
        ],
        cwd=project, env=env, text=True, capture_output=True, timeout=30, check=False,
    )
    combined = result.stdout + result.stderr
    assert result.returncode == 0, combined
    assert "AUTO_SYNC_SKIPPED provider=tiktok" in combined
    assert "reason=exact_catalog_available" in combined
    assert "current_total_exact=true" in combined
    assert "BATCH_START provider=tiktok" in combined
    assert "LEGACY_QUICK_SYNC_CALLED" not in combined
    assert "SYNC_NETWORK_CONTEXT" not in combined
