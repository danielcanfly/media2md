from __future__ import annotations

import types

from media2md.bundle.scripts.public_cli_imports import optional_attr, optional_attrs


def test_optional_attr_returns_none_for_missing_module():
    assert optional_attr("definitely_missing_media2md_module", "x") is None


def test_optional_attrs_returns_tuple_of_nones_for_missing_module():
    assert optional_attrs("definitely_missing_media2md_module", "a", "b") == (None, None)


def test_optional_attr_reads_existing_module(monkeypatch):
    fake = types.SimpleNamespace(answer=42)
    monkeypatch.setattr("importlib.import_module", lambda name: fake)
    assert optional_attr("fake_module", "answer") == 42


def test_optional_attrs_reads_multiple_existing_attrs(monkeypatch):
    fake = types.SimpleNamespace(alpha="a", beta="b")
    monkeypatch.setattr("importlib.import_module", lambda name: fake)
    assert optional_attrs("fake_module", "alpha", "beta") == ("a", "b")
