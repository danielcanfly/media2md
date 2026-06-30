from __future__ import annotations

import argparse

from media2md.bundle.scripts.public_cli_creator_service import creator_policy_payload
from media2md.bundle.scripts.public_cli_state_service import settings_payload
from media2md.bundle.scripts.public_cli_tail_service import data_delete_all_common, uninstall_common


def _assert_shared_schema(payload: dict) -> None:
    assert payload["event"]
    assert str(payload["schema"]).startswith("media2md.cli.")
    assert payload["status"] in {"ok", "warn", "missing", "broken", "timeout", "error"}
    assert payload["category"] in {"ready", "action_required", "degraded"}
    assert isinstance(payload["sections"], list)
    assert payload["sections"]


def test_creator_policy_payload_satisfies_shared_schema():
    payload = creator_policy_payload(
        provider="youtube",
        creator="creator-name",
        effective_policy=lambda provider, creator: {"provider": provider, "creator": creator},
    )
    _assert_shared_schema(payload)


def test_settings_payload_satisfies_shared_schema():
    payload = settings_payload({"timezone": "UTC", "ui_locale": "en", "markdown_locale": "en"})
    _assert_shared_schema(payload)


def test_tail_payloads_satisfy_shared_schema(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr("shutil.rmtree", lambda path: None)
    args = argparse.Namespace(purge_data=False, yes=False, confirm=None, dry_run=True)
    assert uninstall_common(
        args,
        data_delete_all=lambda _args: 0,
        remove_openclaw_cron=lambda: (0, []),
        run=lambda cmd, check=False: 0,
    ) == 0
    uninstall_out = capsys.readouterr().out.splitlines()
    uninstall_payload = "\n".join(uninstall_out[1:])
    assert '"schema": "media2md.cli.uninstall_prepared/v1"' in uninstall_payload

    (tmp_path / "data").mkdir(parents=True)
    delete_args = argparse.Namespace(yes=True, confirm="DELETE-ALL-DATA")
    assert data_delete_all_common(delete_args, root=tmp_path) == 0
    delete_out = capsys.readouterr().out.splitlines()
    delete_payload = "\n".join(delete_out[1:])
    assert '"schema": "media2md.cli.data_delete_all/v1"' in delete_payload
