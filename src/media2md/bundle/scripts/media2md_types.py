#!/usr/bin/env python3
from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Iterable
from urllib.parse import urlsplit, urlunsplit

MEDIA_TYPES = (
    "instagram_reel",
    "youtube_video",
    "youtube_short",
    "youtube_stream",
    "tiktok_video",
)

PROCESSING_CLASSES = (*MEDIA_TYPES, "youtube_long")

DEFAULT_BATCH_SIZES: dict[str, int] = {
    "instagram_reel": 30,
    "tiktok_video": 100,
    "youtube_short": 30,
    "youtube_video": 5,
    "youtube_long": 1,
    "youtube_stream": 1,
}

YOUTUBE_SURFACE_TYPES = {
    "videos": "youtube_video",
    "shorts": "youtube_short",
    "streams": "youtube_stream",
}

_TYPE_PRIORITY = {
    "youtube_short": 30,
    "youtube_stream": 20,
    "youtube_video": 10,
    "instagram_reel": 10,
    "tiktok_video": 10,
}


def infer_media_type(
    provider: str,
    source_url: str | None = None,
    *,
    hinted: str | None = None,
) -> str:
    if hinted in MEDIA_TYPES:
        return str(hinted)
    provider = str(provider).lower()
    url = str(source_url or "").lower()
    if provider == "instagram":
        return "instagram_reel"
    if provider == "tiktok":
        return "tiktok_video"
    if provider == "youtube":
        if "/shorts/" in url or url.rstrip("/").endswith("/shorts"):
            return "youtube_short"
        if "/live/" in url or url.rstrip("/").endswith(("/streams", "/live")):
            return "youtube_stream"
        return "youtube_video"
    raise ValueError(f"Unsupported provider: {provider}")


def processing_class(
    media_type: str,
    duration_seconds: Any = None,
    *,
    long_threshold_seconds: int = 2700,
) -> str:
    media_type = str(media_type)
    if media_type == "youtube_video":
        try:
            duration = float(duration_seconds)
        except (TypeError, ValueError):
            duration = 0.0
        if duration >= max(60, int(long_threshold_seconds)):
            return "youtube_long"
    return media_type if media_type in PROCESSING_CLASSES else "youtube_video"


def output_bucket(media_type: str) -> str:
    return {
        "youtube_video": "videos",
        "youtube_long": "videos",
        "youtube_short": "shorts",
        "youtube_stream": "streams",
        "instagram_reel": "reels",
        "tiktok_video": "videos",
    }.get(str(media_type), "media")


def youtube_channel_base(source_url: str) -> str:
    text = str(source_url).strip()
    parts = urlsplit(text)
    path = parts.path.rstrip("/")
    path = re.sub(r"/(videos|shorts|streams|featured)$", "", path, flags=re.I)
    if not path:
        raise ValueError(f"Could not determine YouTube channel path: {source_url}")
    return urlunsplit((parts.scheme or "https", parts.netloc or "www.youtube.com", path, "", ""))


def youtube_surface_urls(source_url: str, surfaces: Iterable[str] = ("videos", "shorts")) -> dict[str, str]:
    base = youtube_channel_base(source_url)
    result: dict[str, str] = {}
    for surface in surfaces:
        surface = str(surface).lower()
        if surface not in YOUTUBE_SURFACE_TYPES:
            raise ValueError(f"Unsupported YouTube surface: {surface}")
        result[surface] = f"{base}/{surface}"
    return result


def media_type_for_youtube_surface(surface: str) -> str:
    try:
        return YOUTUBE_SURFACE_TYPES[str(surface).lower()]
    except KeyError as exc:
        raise ValueError(f"Unsupported YouTube surface: {surface}") from exc


def youtube_surface_from_url(source_url: str) -> str:
    path = urlsplit(str(source_url)).path.rstrip("/").lower()
    for surface in YOUTUBE_SURFACE_TYPES:
        if path.endswith(f"/{surface}"):
            return surface
    return "videos"


def merge_catalog_items(items: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    by_id: dict[str, dict[str, Any]] = {}
    for raw in items:
        item = dict(raw)
        external_id = str(item.get("external_id") or "").strip()
        if not external_id:
            continue
        current = by_id.get(external_id)
        if current is None:
            by_id[external_id] = item
            continue
        new_type = str(item.get("media_type") or "")
        old_type = str(current.get("media_type") or "")
        if _TYPE_PRIORITY.get(new_type, 0) > _TYPE_PRIORITY.get(old_type, 0):
            preferred, other = item, current
        else:
            preferred, other = current, item
        merged = dict(other)
        merged.update({key: value for key, value in preferred.items() if value not in (None, "")})
        by_id[external_id] = merged
    return sorted(
        by_id.values(),
        key=lambda item: (str(item.get("published_at") or ""), str(item.get("external_id") or "")),
        reverse=True,
    )


def normalize_batch_sizes(value: dict[str, Any] | None) -> dict[str, int]:
    merged = dict(DEFAULT_BATCH_SIZES)
    for key, raw in (value or {}).items():
        if key not in PROCESSING_CLASSES:
            continue
        try:
            size = int(raw)
        except (TypeError, ValueError):
            continue
        merged[key] = max(0, size)
    return merged


def parse_batch_size_assignments(values: Iterable[str] | None) -> dict[str, int]:
    result: dict[str, int] = {}
    for value in values or []:
        key, sep, raw = str(value).partition("=")
        key = key.strip()
        if not sep or key not in PROCESSING_CLASSES:
            raise ValueError(
                "Batch size must use MEDIA_TYPE=COUNT; supported types: "
                + ", ".join(PROCESSING_CLASSES)
            )
        try:
            size = int(raw)
        except ValueError as exc:
            raise ValueError(f"Invalid batch size: {value}") from exc
        if size < 0:
            raise ValueError(f"Batch size cannot be negative: {value}")
        result[key] = size
    return result
