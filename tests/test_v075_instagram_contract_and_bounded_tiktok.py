from __future__ import annotations

import importlib.util
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "src" / "media2md" / "bundle" / "scripts"


def load(module_name: str, path: Path):
    spec = importlib.util.spec_from_file_location(module_name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


def test_instagram_worker_accepts_cookies_file_contract():
    worker = load("process_worker_impl_v075_contract", SCRIPTS / "process_worker_impl.py")
    args = worker.parser().parse_args(
        ["--shortcode", "ABC123", "--limit", "1", "--cookies-file", "/tmp/ig-cookies.txt"]
    )
    assert args.shortcode == "ABC123"
    assert args.cookies_file == Path("/tmp/ig-cookies.txt")


def test_instagram_caller_and_worker_share_cookie_argument():
    bulk = (SCRIPTS / "creator_bulk.py").read_text(encoding="utf-8")
    worker = (SCRIPTS / "process_worker_impl.py").read_text(encoding="utf-8")
    assert '"--cookies-file"' in bulk
    assert '"--cookies-file"' in worker
    assert "selected_cookie_file" in worker


def test_installer_requeues_only_known_cookie_contract_failures(tmp_path):
    installer = load("install_media2md_v075_test", ROOT / "install_media2md_v075.py")
    db = tmp_path / "data" / "state.db"
    db.parent.mkdir(parents=True)
    connection = sqlite3.connect(db)
    connection.execute(
        "CREATE TABLE videos(id INTEGER PRIMARY KEY, status TEXT, attempt_count INTEGER, "
        "next_retry_at TEXT, last_error TEXT, updated_at TEXT)"
    )
    connection.execute(
        "INSERT INTO videos VALUES(1,'retry_wait',3,'later',?, 'old')",
        ("process_worker.py: error: unrecognized arguments: --cookies-file /tmp/c.txt",),
    )
    connection.execute(
        "INSERT INTO videos VALUES(2,'failed',2,NULL,'some unrelated network error','old')"
    )
    connection.commit()
    connection.close()

    assert installer.repair_known_regressions(tmp_path) == 1
    connection = sqlite3.connect(db)
    rows = connection.execute(
        "SELECT id,status,attempt_count,next_retry_at,last_error FROM videos ORDER BY id"
    ).fetchall()
    connection.close()
    assert rows[0] == (1, "pending", 0, None, None)
    assert rows[1][1:] == ("failed", 2, None, "some unrelated network error")


def test_tiktok_transport_plan_is_bounded(monkeypatch):
    registry = load("media2md_registry_v075_plan", SCRIPTS / "media2md_registry.py")
    monkeypatch.setattr(registry, "impersonation_args", lambda provider: ["--impersonate", "chrome"])
    monkeypatch.setattr(
        registry,
        "impersonation_targets",
        lambda: {"targets": ["Chrome-99", "Chrome-146", "Safari-17.0", "Safari-26.0", "Edge-101"]},
    )
    strategies = registry._tiktok_transport_strategies()
    assert len(strategies) <= 4
    names = [item[0] for item in strategies]
    assert names == ["configured:chrome", "latest:Chrome-146", "latest:Safari-26.0", "direct-plain"]
    assert strategies[-1][2] is True


def test_tiktok_repeated_tls_opens_circuit_and_runs_direct(monkeypatch, capsys):
    registry = load("media2md_registry_v075_breaker", SCRIPTS / "media2md_registry.py")
    monkeypatch.setattr(
        registry,
        "_tiktok_transport_strategies",
        lambda: [
            ("configured:chrome", ["--ignore-config", "--impersonate", "chrome"], False),
            ("latest:Chrome-146", ["--ignore-config", "--impersonate", "Chrome-146"], False),
            ("latest:Safari-26.0", ["--ignore-config", "--impersonate", "Safari-26.0"], False),
            ("direct-plain", ["--ignore-config"], True),
        ],
    )
    monkeypatch.setattr(registry, "auth_args", lambda provider: ["--cookies", "/tmp/cookies.txt"])
    calls: list[str] = []

    def fake_run_json(command_line, **kwargs):
        strategy = kwargs["strategy"]
        calls.append(strategy)
        if strategy.startswith("configured:"):
            raise RuntimeError("curl: (35) TLS connect error OPENSSL_internal")
        if strategy == "direct-plain":
            return {"entries": []}
        raise AssertionError(f"impersonation should have been skipped after breaker: {strategy}")

    monkeypatch.setattr(registry, "run_json", fake_run_json)
    payload, strategy, authenticated = registry._run_tiktok_catalog(["yt-dlp", "--dump-single-json"], "u")
    assert payload == {"entries": []}
    assert strategy == "direct-plain"
    assert authenticated is False
    assert calls == ["configured:chrome", "configured:chrome+auth", "direct-plain"]
    err = capsys.readouterr().err
    assert "SYNC_CIRCUIT_BREAKER" in err
    assert "SYNC_TRANSPORT_SKIPPED" in err


def test_tiktok_direct_strategy_removes_proxy_environment(monkeypatch):
    registry = load("media2md_registry_v075_proxy", SCRIPTS / "media2md_registry.py")
    monkeypatch.setenv("HTTPS_PROXY", "http://secret-proxy.invalid:1234")
    monkeypatch.setattr(registry, "_tiktok_transport_strategies", lambda: [("direct-plain", ["--ignore-config"], True)])
    monkeypatch.setattr(registry, "auth_args", lambda provider: [])

    def fake_run_json(command_line, **kwargs):
        assert "HTTPS_PROXY" not in kwargs["env"]
        assert "https_proxy" not in kwargs["env"]
        return {"entries": []}

    monkeypatch.setattr(registry, "run_json", fake_run_json)
    payload, strategy, authenticated = registry._run_tiktok_catalog(["yt-dlp"], "u")
    assert payload == {"entries": []}
    assert strategy == "direct-plain"
    assert authenticated is False


def test_tiktok_page_size_is_separate_and_configurable():
    text = (SCRIPTS / "media2md_registry.py").read_text(encoding="utf-8")
    assert "MEDIA2MD_TIKTOK_SYNC_PAGE_SIZE" in text
    assert "processing_batch_size_is_separate=true" in text
