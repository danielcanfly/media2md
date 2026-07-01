from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from pathlib import Path

from media2md.bundle.scripts import media2md as public_cli
from media2md.bundle.scripts.public_cli_creator_service import creator_run_catalog_preflight
from media2md.bundle.scripts.public_cli_state_service import print_system_status, system_status_payload


class _FakeArgs:
    def __init__(self, **kwargs):
        self.__dict__.update(kwargs)


class _FakeTimeModule:
    def __init__(self):
        self.value = 0.0

    def monotonic(self):
        self.value += 1.0
        return self.value

    def sleep(self, seconds):
        self.value += float(seconds)


def _load_module(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def _load_auth_module():
    root = Path(__file__).resolve().parents[1]
    path = root / "src" / "media2md" / "bundle" / "scripts" / "media2md_auth.py"
    spec = importlib.util.spec_from_file_location("media2md_auth_first_user_test", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


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


def test_first_user_status_human_output_includes_primary_paths_and_auth_tip(capsys, tmp_path):
    payload = system_status_payload(
        config={"timezone": "UTC", "updates": {"check_every_minutes": 1440}},
        auth_data={},
        providers=("instagram", "youtube", "tiktok"),
        version="0.9.4",
        root=tmp_path,
        repository="danielcanfly/media2md",
        creator_count=1,
        registry_db=tmp_path / "media2md.db",
    )
    print_system_status(payload)
    out = capsys.readouterr().out
    assert "MEDIA2MD_STATUS" in out
    assert f"primary_markdown_root={tmp_path}/markdown" in out
    assert f"primary_workspace_root={tmp_path}/workspace" in out
    assert "media2md auth status --output ndjson" in out


def test_first_user_auth_status_ndjson_is_single_summary_payload(monkeypatch, capsys):
    monkeypatch.setattr(public_cli, "auth", lambda args: 0)
    auth_mod = _load_auth_module()
    monkeypatch.setattr(auth_mod, "load", lambda: {"providers": {}})

    result = auth_mod.status("ndjson")
    out = capsys.readouterr().out.strip().splitlines()
    assert result == 0
    assert len(out) == 1
    assert '"event": "auth_status"' in out[0]
    assert '"schema": "media2md.cli.auth_status/v1"' in out[0]


def test_first_user_auth_connect_human_prints_next_verify_command(monkeypatch, capsys):
    auth_mod = _load_auth_module()
    monkeypatch.setattr(auth_mod, "validate_profile", lambda browser, profile: {"display_name": "Primary Profile", "path": "/tmp/profile"})
    monkeypatch.setattr(auth_mod, "load", lambda: {"schema_version": 1, "providers": {}})
    monkeypatch.setattr(auth_mod, "save", lambda payload: None)
    monkeypatch.setattr(auth_mod, "refresh_if_configured", lambda provider: {"refreshed": True})

    result = auth_mod.connect("instagram", "chrome", "Default", "human")
    out = capsys.readouterr().out
    assert result == 0
    assert "AUTH_CONNECTED" in out
    assert "next_command=media2md auth verify instagram" in out


def test_first_user_auth_connect_ndjson_emits_single_payload(monkeypatch, capsys):
    auth_mod = _load_auth_module()
    monkeypatch.setattr(auth_mod, "validate_profile", lambda browser, profile: {"display_name": "Primary Profile", "path": "/tmp/profile"})
    monkeypatch.setattr(auth_mod, "load", lambda: {"schema_version": 1, "providers": {}})
    monkeypatch.setattr(auth_mod, "save", lambda payload: None)
    monkeypatch.setattr(auth_mod, "refresh_if_configured", lambda provider: {"refreshed": True})

    result = auth_mod.connect("tiktok", "chrome", "Default", "ndjson")
    out = capsys.readouterr().out.strip().splitlines()
    assert result == 0
    assert len(out) == 1
    assert '"event": "auth_connected"' in out[0]
    assert '"schema": "media2md.cli.auth_connected/v1"' in out[0]
    assert '"provider": "tiktok"' in out[0]


def test_first_user_auth_verify_human_reports_authenticated_state(monkeypatch, capsys):
    auth_mod = _load_auth_module()
    monkeypatch.setattr(
        auth_mod,
        "verify_web",
        lambda provider, persist=True: {
            "event": "auth_verify",
            "provider": provider,
            "authenticated": True,
            "auth_state": "authenticated",
            "required_action": None,
            "guidance": [],
        },
    )
    result = auth_mod.verify("instagram", None, "human")
    out = capsys.readouterr().out
    assert result == 0
    assert "INSTAGRAM_AUTH_VERIFY" in out
    assert "auth_state=authenticated" in out


def test_first_user_auth_verify_ndjson_emits_authenticated_payload(monkeypatch, capsys):
    auth_mod = _load_auth_module()
    monkeypatch.setattr(
        auth_mod,
        "verify_youtube_session",
        lambda video_id=None, persist=True: {
            "event": "youtube_auth_verify",
            "provider": "youtube",
            "authenticated": True,
            "auth_state": "authenticated",
            "required_action": None,
            "guidance": [],
        },
    )
    result = auth_mod.verify("youtube", "0lJKucu6HJc", "ndjson")
    out = capsys.readouterr().out.strip().splitlines()
    assert result == 0
    assert len(out) == 1
    assert '"schema": "media2md.cli.auth_verify/v1"' in out[0]
    assert '"provider": "youtube"' in out[0]
    assert '"authenticated": true' in out[0]


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


def test_first_user_creator_add_runs_initial_full_sync_and_reports_creator(monkeypatch, capsys):
    monkeypatch.setattr(public_cli, "refresh_auth", lambda provider: None)
    monkeypatch.setattr(public_cli, "normalize_creator", lambda provider, value: "creator-name")
    recorded: list[list[str]] = []
    monkeypatch.setattr(public_cli, "registry", lambda args: recorded.append(args) or 0)
    monkeypatch.setattr(
        public_cli,
        "registry_rows",
        lambda: [{
            "provider": "youtube",
            "handle": "creator-name",
            "source_url": "https://www.youtube.com/@creator-name/shorts",
        }],
    )

    args = _FakeArgs(creator="@creator-name", provider="youtube")
    result = public_cli.add_creator(args)
    out = capsys.readouterr().out
    assert result == 0
    assert recorded == [["sync", "youtube", "@creator-name", "--mode", "full"]]
    assert "CREATOR_ADDED provider=youtube creator=creator-name sync_enabled=false" in out
    assert "catalog_surface=shorts" in out
    assert "catalog_surfaces=videos,shorts" in out
    assert "catalog_url=https://www.youtube.com/@creator-name/shorts" in out


def test_first_user_instagram_creator_add_runs_migration_and_reports_creator(monkeypatch, capsys):
    monkeypatch.setattr(public_cli, "refresh_auth", lambda provider: None)
    monkeypatch.setattr(public_cli, "normalize_creator", lambda provider, value: "creator.name")
    monkeypatch.setattr(public_cli, "add_creator_instagram_service", None, raising=False)
    monkeypatch.setattr("subprocess.run", lambda *args, **kwargs: type("Result", (), {"returncode": 0})())
    monkeypatch.setattr(public_cli, "registry", lambda args: 0)
    real_import = __import__

    def fake_import(name, *args, **kwargs):
        if name == "yaml":
            return object()
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr("builtins.__import__", fake_import)

    args = _FakeArgs(creator="@creator.name", provider="instagram")
    result = public_cli.add_creator(args)
    out = capsys.readouterr().out
    assert result == 0
    assert "CREATOR_ADDED provider=instagram creator=creator.name sync_enabled=false" in out


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
        youtube_catalog_surfaces=lambda: ("videos", "shorts"),
    )
    assert existing_row == rows[0]
    assert result is None
    assert emitted
    assert emitted[0]["event"] == "creator_run_catalog_context"
    assert emitted[1]["event"] == "sync_warning"
    assert emitted[1]["using_cached_catalog"] is True


def test_first_user_creator_run_builds_registry_command_with_saved_policy_defaults(monkeypatch):
    monkeypatch.setattr(public_cli, "resolve_creator_provider", lambda creator, provider, command_name: "youtube")
    monkeypatch.setattr(public_cli, "refresh_auth", lambda provider: None)
    monkeypatch.setattr(public_cli, "normalize_creator", lambda provider, value: "creator-name")
    monkeypatch.setattr(
        public_cli,
        "effective_policy",
        lambda provider, creator: {
            "sync": {"quick_window": 100},
            "processing": {
                "mode": "batch",
                "batch_size": 2,
                "batch_sizes": {"youtube_long": 1},
                "max_batches": 3,
                "max_runtime_minutes": 15,
                "max_failures": 4,
                "sleep_between_batches": 5,
                "stop_on_failure": False,
            },
            "filters": {"order": "newest_first", "since": None, "until": None, "rank_from": None, "rank_to": None},
        },
    )
    monkeypatch.setattr(public_cli, "registry_rows", lambda: [])
    monkeypatch.setattr(public_cli, "prepare_catalog_for_creator_run", lambda **kwargs: 0)
    recorded: list[list[str]] = []
    monkeypatch.setattr(public_cli, "registry", lambda args: recorded.append(args) or 0)

    args = _FakeArgs(
        creator="@creator-name",
        provider="youtube",
        mode=None,
        batch_size=None,
        batch_size_type=[],
        max_batches=None,
        max_runtime_minutes=None,
        max_failures=None,
        stop_on_failure=False,
        retry_failed=False,
        sleep_between_batches=None,
        since=None,
        until=None,
        rank_from=None,
        rank_to=None,
        order=None,
        allow_stale_catalog=False,
        output="ndjson",
    )
    result = public_cli.creator_run(args)
    assert result == 0
    assert recorded[0][0:6] == ["run", "youtube", "@creator-name", "--mode", "batch", "--batch-size"]
    assert "--batch-sizes-json" in recorded[0]
    payload = json.loads(recorded[0][recorded[0].index("--batch-sizes-json") + 1])
    assert payload["youtube_long"] == 1
    assert payload["youtube_video"] == 5
    assert payload["youtube_short"] == 30
    assert recorded[0][-2:] == ["--output", "ndjson"]


def test_first_user_instagram_creator_run_forwards_typed_batch_sizes(monkeypatch):
    monkeypatch.setattr(public_cli, "resolve_creator_provider", lambda creator, provider, command_name: "instagram")
    monkeypatch.setattr(public_cli, "refresh_auth", lambda provider: None)
    monkeypatch.setattr(public_cli, "normalize_creator", lambda provider, value: "creator.name")
    monkeypatch.setattr(
        public_cli,
        "effective_policy",
        lambda provider, creator: {
            "sync": {"quick_window": 100},
            "processing": {
                "mode": "batch",
                "batch_size": 10,
                "batch_sizes": {"instagram_reel": 2, "instagram_post": 3, "instagram_carousel": 1},
                "max_batches": 1,
                "max_runtime_minutes": 10,
                "max_failures": 1,
                "sleep_between_batches": 0,
                "stop_on_failure": False,
            },
            "filters": {"order": "newest_first", "since": None, "until": None, "rank_from": None, "rank_to": None},
        },
    )
    recorded: list[list[str]] = []
    monkeypatch.setattr(public_cli, "core", lambda args: recorded.append(list(args)) or 0)
    monkeypatch.setattr(public_cli, "refresh_registry_legacy", lambda: None)

    args = _FakeArgs(
        creator="@creator.name",
        provider="instagram",
        mode=None,
        batch_size=None,
        batch_size_type=[],
        max_batches=None,
        max_runtime_minutes=None,
        max_failures=None,
        stop_on_failure=False,
        retry_failed=False,
        sleep_between_batches=None,
        since=None,
        until=None,
        rank_from=None,
        rank_to=None,
        order=None,
        allow_stale_catalog=False,
        output="human",
        catalog_surface="mixed",
    )
    result = public_cli.creator_run(args)
    assert result == 0
    assert "--batch-sizes-json" in recorded[0]
    payload = json.loads(recorded[0][recorded[0].index("--batch-sizes-json") + 1])
    assert payload["instagram_reel"] == 2
    assert payload["instagram_post"] == 3
    assert payload["instagram_carousel"] == 1
    assert recorded[0][-2:] == ["--catalog-surface", "mixed"]


def test_first_user_creator_run_summary_includes_result_folder_and_finder_hint(capsys):
    registry_mod = __import__("media2md.bundle.scripts.media2md_registry", fromlist=["_creator_run_summary"])
    markdown_root = Path("/tmp/media2md/markdown/youtube/creator-name")
    registry_mod._creator_run_summary(
        provider="youtube",
        handle="creator-name",
        batches=1,
        processed=1,
        failures=0,
        status="completed",
        remaining=0,
        output="human",
        markdown_root=markdown_root,
        latest_markdown_path=str(markdown_root / "video.md"),
    )
    out = capsys.readouterr().out
    assert "CREATOR_RUN_COMPLETED provider=youtube creator=creator-name status=completed" in out
    assert "primary_output_surface=creator-name" not in out
    assert f"result_folder={markdown_root}" in out
    assert f'open_in_finder_hint=open "{markdown_root}"' in out


def test_first_user_instagram_drain_runs_multiple_batches(monkeypatch):
    social2md = _load_module(
        Path(__file__).resolve().parents[1] / "src" / "media2md" / "bundle" / "scripts" / "social2md_core.py",
        "first_user_social2md_drain",
    )

    emitted: list[dict[str, object]] = []
    commands: list[list[str]] = []
    remaining = {"value": 3}

    monkeypatch.setattr(social2md, "normalize_creator", lambda value: "career_cleo")
    monkeypatch.setattr(social2md, "load_config", lambda: {"timezone": "UTC"})
    monkeypatch.setattr(
        social2md,
        "effective_policy",
        lambda creator: {
            "processing": {
                "mode": "drain",
                "batch_size": 1,
                "max_batches": 0,
                "max_runtime_minutes": 360,
                "max_failures": 10,
                "stop_on_failure": False,
                "sleep_between_batches": 0,
            },
            "filters": {"since": None, "until": None, "rank_from": None, "rank_to": None, "order": "newest_first"},
            "sync": {"full_every_minutes": 1440, "quick_window": 100},
        },
    )
    monkeypatch.setattr(social2md, "ui_locale", lambda non_interactive: "en")
    monkeypatch.setattr(social2md, "resolve_boundary", lambda value, timezone_name, inclusive_end: value)
    monkeypatch.setattr(social2md, "load_performance_samples", lambda username: [])
    monkeypatch.setattr(social2md, "save_performance_samples", lambda username, samples: None)
    monkeypatch.setattr(social2md, "time", _FakeTimeModule())
    monkeypatch.setattr(social2md, "sync_once", lambda *args, **kwargs: (0, {}))

    def fake_remaining(*args, **kwargs):
        return remaining["value"]

    def fake_stream(command, **kwargs):
        commands.append(list(command))
        remaining["value"] -= 1
        batch_number = kwargs.get("batch_number", 1)
        return 0, {
            "completed": 1,
            "failed": 0,
            "report": f"/tmp/report-{batch_number}.json",
            "log": f"/tmp/log-{batch_number}.txt",
        }

    monkeypatch.setattr(social2md, "filtered_candidate_count", fake_remaining)
    monkeypatch.setattr(social2md, "stream_engine", fake_stream)
    monkeypatch.setattr(social2md, "engine_command", lambda *parts: list(parts))
    monkeypatch.setattr(social2md, "emit_cli_event", lambda **payload: emitted.append(payload))

    args = argparse.Namespace(
        creator="career_cleo",
        mode="drain",
        batch_size=1,
        max_batches=None,
        max_runtime_minutes=None,
        max_failures=None,
        stop_on_failure=False,
        sleep_between_batches=0,
        retry_failed=False,
        since=None,
        until=None,
        rank_from=None,
        rank_to=None,
        order=None,
        output="ndjson",
        non_interactive=True,
        force_full_sync=False,
        pause_seconds=0,
        batch_sizes_json=None,
        catalog_surface="posts",
        skip_sync=False,
    )

    result = social2md.run_creator(args)

    assert result == 0
    assert len(commands) == 3
    assert all("--catalog-surface" in command for command in commands)
    completed = [payload for payload in emitted if payload.get("event") == "run_completed"]
    assert completed
    assert completed[-1]["data"]["status"] == "completed"


def test_first_user_public_cli_refresh_catalog_alias_exists():
    parser = public_cli.parser()
    args = parser.parse_args(["creator", "refresh-catalog", "@creator-name", "--provider", "youtube"])
    assert args.command == "creator"
    assert args.creator_command == "refresh-catalog"
    assert args.provider == "youtube"


def test_first_user_creator_status_human_output_includes_youtube_source_and_surfaces(monkeypatch, capsys):
    monkeypatch.setattr(
        public_cli,
        "registry_rows",
        lambda: [{
            "provider": "youtube",
            "handle": "creator-name",
            "source_url": "https://www.youtube.com/@creator-name/shorts",
            "current_total": 12,
            "current_total_exact": 1,
            "youtube_video_total": 5,
            "youtube_video_total_exact": 1,
            "youtube_shorts_total": 7,
            "youtube_shorts_total_exact": 1,
            "youtube_streams_total": 0,
            "youtube_streams_total_exact": 0,
            "tracked": 12,
            "completed": 3,
            "remaining": 9,
            "last_sync_mode": "full",
            "last_sync_at": "2026-06-30T00:00:00+00:00",
            "last_full_sync_at": "2026-06-30T00:00:00+00:00",
            "last_full_exact_total": 12,
            "last_full_exact_at": "2026-06-30T00:00:00+00:00",
            "last_full_youtube_video_total": 5,
            "last_full_youtube_shorts_total": 7,
            "last_full_youtube_streams_total": 0,
        }],
    )
    monkeypatch.setattr(
        public_cli,
        "effective_policy",
        lambda provider, creator: {
            "sync": {"enabled": True, "every_minutes": 60, "full_every_minutes": 1440},
            "processing": {"mode": "batch", "batch_sizes": {"youtube_short": 30}},
            "filters": {},
        },
    )

    args = _FakeArgs(provider="youtube", creator="@creator-name", output="human")
    result = public_cli.creator_status(args)
    out = capsys.readouterr().out
    assert result == 0
    assert "SOURCE surface=shorts catalog_surfaces=videos,shorts" in out
    assert "url=https://www.youtube.com/@creator-name/shorts" in out


def test_first_user_runtime_status_reports_managed_paths(monkeypatch, tmp_path, capsys):
    monkeypatch.setenv("HOME", str(tmp_path))
    from media2md import cli

    result = cli.runtime_command(["status"])
    out = capsys.readouterr().out
    payload = json.loads(out)
    assert result == 0
    assert payload["event"] == "runtime_status"
    assert payload["schema"] == "media2md.cli.runtime_status/v1"
    assert payload["status"] == "ok"
    assert payload["managed"] is True
    assert payload["managed_base"].endswith("/Downloads/media2md")
    assert payload["runtime_root"].endswith("/runtime/0.9.5")


def test_first_user_runtime_install_reports_installed_path(monkeypatch, tmp_path, capsys):
    monkeypatch.setenv("HOME", str(tmp_path))
    from media2md import cli

    result = cli.runtime_command(["install", "--force"])
    out = capsys.readouterr().out
    assert result == 0
    assert "MEDIA2MD_RUNTIME_INSTALLED" in out
    assert "version=0.9.5" in out


def test_first_user_public_cli_main_answers_version_without_runtime_delegate(monkeypatch, tmp_path, capsys):
    monkeypatch.setenv("HOME", str(tmp_path))
    from media2md import cli

    calls: list[tuple[list[str], str]] = []
    monkeypatch.setattr(
        cli.subprocess,
        "call",
        lambda cmd, cwd=None, env=None: calls.append((cmd, cwd)) or 0,
    )
    monkeypatch.setattr(sys, "argv", ["media2md", "version"])
    result = cli.main()
    out = capsys.readouterr().out
    assert result == 0
    assert out.strip() == "media2md 0.9.5"
    assert calls == []


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


def test_first_user_uninstall_executes_package_removal_when_not_dry_run(monkeypatch, capsys):
    from media2md.bundle.scripts.public_cli_tail_service import uninstall_common

    monkeypatch.setattr("shutil.rmtree", lambda path: None)
    monkeypatch.setattr(Path, "home", lambda: Path("/tmp/home"))
    calls: list[list[str]] = []

    result = uninstall_common(
        argparse.Namespace(purge_data=False, yes=False, confirm=None, dry_run=False),
        data_delete_all=lambda _args: 0,
        remove_openclaw_cron=lambda: (0, []),
        run=lambda cmd, check=False: calls.append(cmd) or 0,
    )
    out = capsys.readouterr().out
    assert result == 0
    assert "package_uninstalled=true" in out
    assert calls
    assert calls[0][-2:] == ["media2md", "social2md"]
