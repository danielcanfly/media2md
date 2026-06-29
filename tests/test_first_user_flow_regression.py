from __future__ import annotations

import argparse
from pathlib import Path

from media2md.bundle.scripts import media2md as public_cli
from media2md.bundle.scripts.public_cli_creator_service import creator_run_catalog_preflight
from media2md.bundle.scripts.public_cli_state_service import system_status_payload


class _FakeArgs:
    def __init__(self, **kwargs):
        self.__dict__.update(kwargs)


def test_first_user_init_forwards_non_interactive_locale_and_timezone(monkeypatch):
    recorded: list[list[str]] = []
    monkeypatch.setattr(public_cli, "core", lambda args: recorded.append(args) or 0)

    args = _FakeArgs(
        language="ja",
        markdown_language="ja",
        timezone="Asia/Tokyo",
        non_interactive=True,
    )
    result = public_cli.init_command(args)
    assert result == 0
    assert recorded == [[
        "init",
        "--language",
        "ja",
        "--markdown-language",
        "ja",
        "--timezone",
        "Asia/Tokyo",
        "--non-interactive",
    ]]


def test_first_user_status_payload_includes_paths_and_provider_summary(tmp_path):
    payload = system_status_payload(
        config={"timezone": "UTC", "updates": {"check_every_minutes": 1440}},
        auth_data={},
        providers=("instagram", "youtube", "tiktok"),
        version="0.9.4",
        root=tmp_path,
        repository="danielcanfly/media2md",
        creator_count=0,
        registry_db=tmp_path / "media2md.db",
    )
    assert payload["event"] == "system_status"
    assert payload["schema"] == "media2md.cli.system_status/v1"
    assert payload["project_root"] == str(tmp_path)
    assert payload["registry_db"] == str(tmp_path / "media2md.db")
    assert "providers" in payload
    assert "provider_health" in payload


def test_first_user_auth_status_ndjson_is_single_summary_payload(monkeypatch, capsys):
    monkeypatch.setattr(public_cli, "auth", lambda args: 0)
    auth_mod = __import__("media2md.bundle.scripts.media2md_auth", fromlist=["status"])
    monkeypatch.setattr(auth_mod, "load", lambda: {"providers": {}})

    result = auth_mod.status("ndjson")
    out = capsys.readouterr().out.strip().splitlines()
    assert result == 0
    assert len(out) == 1
    assert '"event": "auth_status"' in out[0]
    assert '"schema": "media2md.cli.auth_status/v1"' in out[0]


def test_first_user_creator_add_requires_provider_for_bare_handle():
    try:
        public_cli.resolve_creator_provider("@creator-name", None, command_name="creator add")
    except RuntimeError as exc:
        message = str(exc)
    else:
        raise AssertionError("expected RuntimeError")
    assert "creator add" in message
    assert "--provider" in message


def test_first_user_refresh_catalog_prefers_refresh_alias(monkeypatch):
    recorded: list[dict[str, object]] = []
    monkeypatch.setattr(
        public_cli,
        "prepare_catalog_for_creator_run",
        lambda **kwargs: recorded.append(kwargs) or 0,
    )
    monkeypatch.setattr(public_cli, "registry_rows", lambda: [])
    monkeypatch.setattr(public_cli, "refresh_auth", lambda provider: None)
    monkeypatch.setattr(public_cli, "effective_policy", lambda provider, creator: {"sync": {"quick_window": 100}})
    monkeypatch.setattr(public_cli, "registry", lambda args: 0)

    args = _FakeArgs(creator="@creator-name", provider="youtube", force_full=False)
    result = public_cli.creator_sync(args)
    assert result == 0


def test_first_user_creator_run_uses_stale_catalog_guardrail(monkeypatch):
    rows = [{"provider": "youtube", "handle": "creator-name", "tracked": 3, "last_sync_at": "2026-06-30T00:00:00+00:00"}]
    emitted: list[dict[str, object]] = []

    args = _FakeArgs(
        creator="@creator-name",
        provider="youtube",
        output="ndjson",
        allow_stale_catalog=True,
    )
    existing_row, result = creator_run_catalog_preflight(
        args=args,
        provider="youtube",
        creator="creator-name",
        policy={
            "sync": {"quick_window": 100},
            "processing": {"mode": "batch", "batch_size": 1, "batch_sizes": {}, "max_batches": 1, "max_runtime_minutes": 10, "max_failures": 1, "sleep_between_batches": 0, "stop_on_failure": False},
            "filters": {"order": "newest_first", "since": None, "until": None, "rank_from": None, "rank_to": None},
        },
        registry_rows=rows,
        prepare_catalog_for_creator_run=lambda **kwargs: 1,
        registry_call=lambda args: 0,
        emit_call=lambda payload, output: emitted.append(payload),
    )
    assert existing_row == rows[0]
    assert result is None
    assert emitted
    assert emitted[0]["event"] == "sync_warning"
    assert emitted[0]["using_cached_catalog"] is True


def test_first_user_uninstall_dry_run_prepares_package_removal(monkeypatch, capsys):
    from media2md.bundle.scripts.public_cli_tail_service import uninstall_common

    monkeypatch.setattr("shutil.rmtree", lambda path: None)
    monkeypatch.setattr(Path, "home", lambda: Path("/tmp/home"))

    result = uninstall_common(
        argparse.Namespace(purge_data=False, yes=False, confirm=None, dry_run=True),
        data_delete_all=lambda _args: 0,
        remove_openclaw_cron=lambda: (0, []),
        run=lambda cmd, check=False: 0,
    )
    out = capsys.readouterr().out
    assert result == 0
    assert "MEDIA2MD_UNINSTALL_PREPARED" in out
    assert "package_uninstalled=false" in out
    assert "next_step=run `media2md uninstall`" in out
