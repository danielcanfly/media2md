from __future__ import annotations

from media2md.cli_output_service import make_event_payload, make_output_model, make_section


def test_make_section_normalizes_status_and_category():
    section = make_section("providers", status="warn", message="needs setup", data={"count": 3})
    assert section.status == "warn"
    assert section.category == "action_required"
    assert section.data == {"count": 3}


def test_make_output_model_summarizes_sections():
    payload = make_output_model(
        event="system_status",
        schema="media2md.cli.system_status/v1",
        sections=(
            make_section("providers", status="ok", message="ready"),
            make_section("auth", status="warn", message="needs setup"),
        ),
        summary="summary",
        data={"version": "0.9.4"},
    ).as_dict()
    assert payload["event"] == "system_status"
    assert payload["schema"] == "media2md.cli.system_status/v1"
    assert payload["status"] == "warn"
    assert payload["category"] == "action_required"
    assert len(payload["sections"]) == 2
    assert payload["version"] == "0.9.4"


def test_make_event_payload_adds_schema_and_data():
    payload = make_event_payload(
        event="creator_policy",
        schema="media2md.cli.creator_policy/v1",
        data={"provider": "youtube"},
    )
    assert payload == {
        "event": "creator_policy",
        "schema": "media2md.cli.creator_policy/v1",
        "provider": "youtube",
    }
