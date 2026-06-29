from __future__ import annotations

from media2md.health_taxonomy import health_category, normalize_health_status, summarize_health
from media2md.results import HealthResult


def test_normalize_health_status_falls_back_to_error():
    assert normalize_health_status("ok") == "ok"
    assert normalize_health_status("BOGUS") == "error"


def test_health_category_maps_expected_groups():
    assert health_category("ok") == "ready"
    assert health_category("warn") == "action_required"
    assert health_category("missing") == "action_required"
    assert health_category("timeout") == "degraded"
    assert health_category("broken") == "degraded"
    assert health_category("error") == "degraded"


def test_summarize_health_uses_worst_status():
    summary = summarize_health(
        [
            HealthResult(status="ok", message="ready", provider="instagram"),
            HealthResult(status="warn", message="needs setup", provider="youtube"),
            HealthResult(status="broken", message="broken", provider="tiktok"),
        ]
    )
    assert summary["status"] == "broken"
    assert summary["category"] == "degraded"
    assert summary["ready_count"] == 1
    assert summary["action_required_count"] == 1
    assert summary["degraded_count"] == 1
