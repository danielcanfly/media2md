from __future__ import annotations

from media2md.bundle.scripts import media2md, social2md


def test_media2md_update_available_event_uses_cli_result_schema():
    payload = media2md.cli_result(
        event="update_available",
        section="update",
        status="warn",
        message="A newer Media2MD release is available",
        data={"latest_version": "0.9.8"},
    )
    assert payload["schema"] == "media2md.cli.update_available/v1"
    assert payload["sections"][0]["name"] == "update"


def test_social2md_update_available_event_uses_cli_result_schema():
    payload = social2md.cli_result(
        event="update_available",
        section="update",
        status="warn",
        message="A newer Media2MD release is available",
        data={"latest_version": "0.9.8"},
    )
    assert payload["schema"] == "media2md.cli.update_available/v1"
    assert payload["sections"][0]["name"] == "update"
