from __future__ import annotations

from media2md.bundle.scripts.public_cli_state_service import agent_status_payload


def test_agent_status_payload_exposes_bilibili_doctor_command_and_capability() -> None:
    payload = agent_status_payload({"agent": {"mode": "strict"}}, schema_version=13)

    assert "bilibili" in payload["provider_commands"]
    assert "doctor bilibili-access" in payload["provider_commands"]["bilibili"]["read"]
    assert payload["provider_capabilities"]["bilibili"]["extra"] == "bilibili"
