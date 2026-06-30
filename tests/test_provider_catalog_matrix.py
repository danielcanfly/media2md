from __future__ import annotations

from media2md.provider_catalog import provider_capability_matrix, provider_command_matrix


def test_provider_command_matrix_is_projection_of_capability_matrix():
    capability = provider_capability_matrix()
    commands = provider_command_matrix()
    assert set(capability) == set(commands)
    for name, payload in capability.items():
        assert payload["commands"] == commands[name]


def test_provider_capability_matrix_includes_backend_and_capability_metadata():
    payload = provider_capability_matrix()
    assert payload["instagram"]["backends"] == ["gallery-dl", "instaloader"]
    assert payload["instagram"]["default_backend"] == "auto"
    assert payload["youtube"]["extra"] == "youtube"
    assert payload["tiktok"]["capabilities"] == {
        "single_media": True,
        "creator_sync": True,
        "batch_drain": True,
    }
