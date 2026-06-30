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
    script = f'''
use framework "Foundation"
use framework "Vision"
use framework "AppKit"
use scripting additions

set imagePath to "{str(image_path)}"
set imageURL to current application's |NSURL|'s fileURLWithPath:imagePath
set imageData to current application's NSData's dataWithContentsOfURL:imageURL
if imageData is missing value then error "Could not read image data"
set imageRep to current application's NSBitmapImageRep's imageRepWithData:imageData
if imageRep is missing value then error "Could not decode image"
set ciImage to current application's CIImage's imageWithBitmapImageRep:imageRep
set handler to current application's VNImageRequestHandler's alloc()'s initWithCIImage:ciImage options:(current application's NSDictionary's dictionary())
set request to current application's VNRecognizeTextRequest's alloc()'s init()
request's setRecognitionLevel:(current application's VNRequestTextRecognitionLevelAccurate)
request's setUsesLanguageCorrection:true
handler's performRequests:{{request}} |error|:(missing value)
set observations to request's results()
set collected to current application's NSMutableArray's array()
repeat with obs in observations
    set candidates to obs's topCandidates:1
    if (candidates's |count|()) > 0 then
        set recognized to (candidates's objectAtIndex:0)'s string()
        if recognized is not missing value then (collected's addObject:recognized)
    end if
end repeat
set output to current application's NSJSONSerialization's dataWithJSONObject:{{lines:collected}} options:0 |error|:(missing value)
set textOut to current application's NSString's alloc()'s initWithData:output encoding:(current application's NSUTF8StringEncoding)
return textOut as text
'''
    result = subprocess.run(
        ["osascript", "-l", "AppleScript", "-e", script],
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


def _perform_easyocr(image_path: Path) -> dict[str, Any]:
    try:
        import easyocr  # type: ignore
    except ImportError as exc:
        raise RuntimeError("EasyOCR is not installed.") from exc
    reader = easyocr.Reader(["en", "ja", "ch_sim", "ch_tra"], gpu=False)
    results = reader.readtext(str(image_path), detail=0, paragraph=False)
    lines = [str(item).strip() for item in results if str(item).strip()]
    return {
        "engine": "easyocr",
        "text": "\n".join(lines).strip(),
        "lines": lines,
        "status": "ok",
    }

