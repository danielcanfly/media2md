from __future__ import annotations

from media2md.bundle.scripts import media2md_runtime


def test_transcription_exception_contract_uses_known_required_actions():
    invalid = media2md_runtime.classify_transcription_exception(RuntimeError("usage: bad arg"))
    assert invalid["required_action"] == "upgrade_media2md_or_report_internal_bug"

    missing = media2md_runtime.classify_transcription_exception(RuntimeError("mlx_whisper command was not found"))
    assert missing["required_action"] == "install_mlx_whisper"

    output_missing = media2md_runtime.classify_transcription_exception(RuntimeError("expected transcript output"))
    assert output_missing["required_action"] == "inspect_transcription_log"

