#!/usr/bin/env python3
from __future__ import annotations

import json
import platform
import subprocess
import sys
from pathlib import Path
from typing import Any


def _platform_key() -> str:
    system = platform.system().lower()
    if system == "darwin":
        return "macos"
    if system == "windows":
        return "windows"
    return "linux"


def preferred_ocr_engine(config: dict[str, Any] | None = None) -> str:
    provider_cfg = ((config or {}).get("providers") or {}).get("instagram") or {}
    value = str(provider_cfg.get("ocr_engine") or "auto").strip().lower()
    if value in {"vision", "easyocr", "disabled"}:
        return value
    return "vision" if _platform_key() == "macos" else "easyocr"


def fallback_ocr_engine(config: dict[str, Any] | None = None) -> str | None:
    provider_cfg = ((config or {}).get("providers") or {}).get("instagram") or {}
    value = str(provider_cfg.get("ocr_engine") or "auto").strip().lower()
    if value != "auto":
        return None
    return "easyocr" if _platform_key() == "macos" else None


def ocr_install_extra() -> str:
    return "ocr-mac-os" if _platform_key() == "macos" else "ocr-windows-linux"


def perform_ocr(image_path: Path, *, config: dict[str, Any] | None = None) -> dict[str, Any]:
    engine = preferred_ocr_engine(config)
    fallback = fallback_ocr_engine(config)
    errors: list[str] = []
    for candidate in (engine, fallback):
        if not candidate or candidate == "disabled":
            continue
        try:
            if candidate == "vision":
                return _perform_vision_ocr(image_path)
            if candidate == "easyocr":
                return _perform_easyocr(image_path)
        except Exception as exc:
            errors.append(f"{candidate}: {exc}")
    if engine == "disabled":
        return {"engine": "disabled", "text": "", "lines": [], "status": "disabled"}
    raise RuntimeError(
        "OCR failed for all configured engines. "
        + (" | ".join(errors) if errors else f"Install support via media2md[{ocr_install_extra()}].")
    )


def _perform_vision_ocr(image_path: Path) -> dict[str, Any]:
    if _platform_key() != "macos":
        raise RuntimeError("Apple Vision OCR is only available on macOS.")
    if not image_path.is_file():
        raise RuntimeError(f"Image file does not exist: {image_path}")
    script = r'''
import AppKit
import Foundation
import Vision

let imagePath = CommandLine.arguments[1]
guard let image = NSImage(contentsOfFile: imagePath) else {
    fputs("Could not read image data\n", stderr)
    exit(1)
}
var rect = CGRect(origin: .zero, size: image.size)
guard let cgImage = image.cgImage(forProposedRect: &rect, context: nil, hints: nil) else {
    fputs("Could not decode image\n", stderr)
    exit(1)
}

let request = VNRecognizeTextRequest()
request.recognitionLevel = .accurate
request.usesLanguageCorrection = true
let handler = VNImageRequestHandler(cgImage: cgImage, options: [:])

do {
    try handler.perform([request])
} catch {
    fputs("Vision OCR failed: \(error)\n", stderr)
    exit(1)
}

let observations = request.results ?? []
let lines = observations
    .compactMap { $0.topCandidates(1).first?.string }
    .map { $0.trimmingCharacters(in: .whitespacesAndNewlines) }
    .filter { !$0.isEmpty }
let payload: [String: Any] = ["lines": lines]
let data = try JSONSerialization.data(withJSONObject: payload, options: [])
FileHandle.standardOutput.write(data)
'''
    result = subprocess.run(
        ["swift", "-", str(image_path)],
        input=script,
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError((result.stderr or result.stdout or "Vision OCR failed").strip())
    payload = json.loads(result.stdout.strip() or "{}")
    lines = [str(item).strip() for item in payload.get("lines", []) if str(item).strip()]
    return {
        "engine": "vision",
        "text": "\n".join(lines).strip(),
        "lines": lines,
        "status": "ok",
    }


def _easyocr_model_paths() -> tuple[Path, Path]:
    root = Path.home() / ".EasyOCR"
    model_dir = root / "model"
    user_network_dir = root / "user_network"
    model_dir.mkdir(parents=True, exist_ok=True)
    user_network_dir.mkdir(parents=True, exist_ok=True)
    return model_dir, user_network_dir


def _easyocr_language_candidates(config: dict[str, Any] | None = None) -> list[list[str]]:
    provider_cfg = ((config or {}).get("providers") or {}).get("instagram") or {}
    values = [
        str(provider_cfg.get("ocr_language") or "").strip(),
        str((config or {}).get("markdown_language") or "").strip(),
        str((config or {}).get("language") or "").strip(),
    ]
    lowered = [value.lower() for value in values if value]
    if any(value in {"zh-tw", "zh_hant", "zh-hant"} for value in lowered):
        return [["ch_tra", "en"], ["ja", "en"], ["ch_sim", "en"], ["en"]]
    if any(value in {"zh-cn", "zh_hans", "zh-hans"} for value in lowered):
        return [["ch_sim", "en"], ["ja", "en"], ["ch_tra", "en"], ["en"]]
    if any(value == "ja" for value in lowered):
        return [["ja", "en"], ["ch_tra", "en"], ["ch_sim", "en"], ["en"]]
    return [["ja", "en"], ["ch_tra", "en"], ["ch_sim", "en"], ["en"]]


def _perform_easyocr(image_path: Path) -> dict[str, Any]:
    try:
        import easyocr  # type: ignore
    except ImportError as exc:
        raise RuntimeError("EasyOCR is not installed.") from exc
    if not image_path.is_file():
        raise RuntimeError(f"Image file does not exist: {image_path}")
    model_dir, user_network_dir = _easyocr_model_paths()
    errors: list[str] = []
    last_lines: list[str] = []
    for languages in _easyocr_language_candidates():
        try:
            reader = easyocr.Reader(
                languages,
                gpu=False,
                model_storage_directory=str(model_dir),
                user_network_directory=str(user_network_dir),
                download_enabled=True,
            )
            results = reader.readtext(str(image_path), detail=0, paragraph=False)
            lines = [str(item).strip() for item in results if str(item).strip()]
            if lines:
                return {
                    "engine": "easyocr",
                    "text": "\n".join(lines).strip(),
                    "lines": lines,
                    "status": "ok",
                    "languages": languages,
                }
            last_lines = lines
        except Exception as exc:
            errors.append(f"{'+'.join(languages)}: {exc}")
    if errors:
        raise RuntimeError(" ; ".join(errors))
    return {
        "engine": "easyocr",
        "text": "\n".join(last_lines).strip(),
        "lines": last_lines,
        "status": "ok",
        "languages": ["en"],
    }
