from __future__ import annotations

import io
import json
from contextlib import redirect_stdout

from media2md.bundle.scripts import social2md_core as core


def test_social2md_emit_cli_event_uses_shared_contract():
    stream = io.StringIO()
    with redirect_stdout(stream):
        core.emit_cli_event(
            event="provider_list_completed",
            section="provider",
            status="ok",
            message="Provider listing completed",
            data={"count": 3},
            output="ndjson",
        )
    payload = json.loads(stream.getvalue().strip())
    assert payload["event"] == "provider_list_completed"
    assert payload["schema"] == "media2md.cli.provider_list_completed/v1"
    assert payload["status"] == "ok"
    assert payload["sections"][0]["name"] == "provider"
    assert payload["count"] == 3
