from __future__ import annotations

from media2md.cli_result_types import cli_result


def test_cli_result_wraps_event_schema_status_and_section():
    payload = cli_result(
        event="update_available",
        section="update",
        status="warn",
        message="A newer Media2MD release is available",
        data={"latest_version": "0.9.6"},
    )
    assert payload["event"] == "update_available"
    assert payload["schema"] == "media2md.cli.update_available/v1"
    assert payload["status"] == "warn"
    assert payload["sections"][0]["name"] == "update"
    assert payload["latest_version"] == "0.9.6"
