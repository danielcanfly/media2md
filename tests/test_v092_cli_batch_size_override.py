from __future__ import annotations

import argparse
import json


def test_cli_batch_size_without_typed_overrides_disables_default_typed_batch_sizes(monkeypatch):
    import importlib.util
    import sys
    from pathlib import Path

    root = Path(__file__).resolve().parents[1]
    path = root / "src" / "media2md" / "bundle" / "scripts" / "media2md.py"
    spec = importlib.util.spec_from_file_location("media2md_cli_v092", path)
    assert spec and spec.loader
    media2md = importlib.util.module_from_spec(spec)
    sys.modules["media2md_cli_v092"] = media2md
    spec.loader.exec_module(media2md)

    recorded: dict[str, object] = {}

    monkeypatch.setattr(media2md, "refresh_auth", lambda provider: None)
    monkeypatch.setattr(media2md, "normalize_creator", lambda provider, creator: "acta.so")
    monkeypatch.setattr(
        media2md,
        "effective_policy",
        lambda provider, creator: {
            "sync": {"quick_window": 100},
            "filters": {"order": "newest_first"},
            "processing": {
                "mode": "batch",
                "batch_size": 100,
                "batch_sizes": {
                    "tiktok_video": 100,
                    "youtube_video": 5,
                    "youtube_long": 1,
                    "youtube_short": 30,
                    "youtube_stream": 1,
                    "instagram_reel": 30,
                },
                "max_batches": 1,
                "max_runtime_minutes": 10,
                "max_failures": 1,
                "stop_on_failure": False,
                "sleep_between_batches": 0,
            },
        },
    )
    monkeypatch.setattr(media2md, "registry_rows", lambda: [])
    monkeypatch.setattr(media2md, "prepare_catalog_for_creator_run", lambda **kwargs: 0)

    def fake_registry(cmd):
        recorded["cmd"] = list(cmd)
        return 0

    monkeypatch.setattr(media2md, "registry", fake_registry)

    args = argparse.Namespace(
        creator="@acta.so",
        provider="tiktok",
        mode="batch",
        batch_size=1,
        batch_size_type=[],
        max_batches=1,
        max_runtime_minutes=10,
        max_failures=1,
        stop_on_failure=False,
        retry_failed=False,
        sleep_between_batches=0,
        since=None,
        until=None,
        rank_from=None,
        rank_to=None,
        order=None,
        output="ndjson",
        allow_stale_catalog=True,
    )

    assert media2md.creator_run(args) == 0
    cmd = recorded["cmd"]
    batch_sizes = json.loads(cmd[cmd.index("--batch-sizes-json") + 1])
    assert cmd[0:6] == ["run", "tiktok", "@acta.so", "--mode", "batch", "--batch-size"]
    assert batch_sizes == {}
