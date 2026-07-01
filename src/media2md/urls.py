#!/usr/bin/env python3
from __future__ import annotations

import re
from dataclasses import dataclass
from urllib.parse import parse_qs, urlencode, urlsplit, urlunsplit

PROVIDERS = ("instagram", "youtube", "tiktok", "bilibili")
YOUTUBE_ID_RE = re.compile(r"^[A-Za-z0-9_-]{11}$")
TIKTOK_ID_RE = re.compile(r"^\d{8,24}$")
INSTAGRAM_CODE_RE = re.compile(r"^[A-Za-z0-9_-]{5,30}$")
BILIBILI_BVID_RE = re.compile(r"^BV[A-Za-z0-9]{10}$")
HANDLE_RE = re.compile(r"^[A-Za-z0-9._-]+$")
INSTAGRAM_MEDIA_SURFACES = ("reel", "post", "tv")
BILIBILI_UID_RE = re.compile(r"^\d{1,20}$")


@dataclass(frozen=True)
class NormalizedTarget:
    provider: str
    kind: str
    canonical_url: str
    creator: str | None = None
    media_id: str | None = None
    surface: str | None = None


YOUTUBE_CREATOR_SURFACES = ("videos", "shorts", "streams")


def detect_provider(value: str) -> str | None:
    lower = value.strip().lower()
    if "instagram.com" in lower:
        return "instagram"
    if "youtube.com" in lower or "youtu.be" in lower:
        return "youtube"
    if "tiktok.com" in lower:
        return "tiktok"
    if "bilibili.com" in lower or "b23.tv" in lower or BILIBILI_BVID_RE.fullmatch(value.strip()):
        return "bilibili"
    return None


def _strip_query_fragment(value: str) -> str:
    parts = urlsplit(value)
    return urlunsplit((parts.scheme or "https", parts.netloc, parts.path, "", ""))


def _clean_handle(value: str) -> str:
    handle = value.strip().lstrip("@").strip("/")
    if not HANDLE_RE.fullmatch(handle):
        raise ValueError(f"Unsupported creator handle: {value}")
    return handle


def _youtube_surface_for_path(path: str) -> str:
    lowered = str(path).rstrip("/").lower()
    for surface in YOUTUBE_CREATOR_SURFACES:
        if lowered.endswith(f"/{surface}"):
            return surface
    return "videos"


def _youtube_creator_target(path: str, *, scheme: str = "https", netloc: str = "www.youtube.com") -> NormalizedTarget:
    cleaned_path = str(path).rstrip("/")
    surface = _youtube_surface_for_path(cleaned_path)
    base_path = re.sub(r"/(videos|shorts|streams)$", "", cleaned_path, flags=re.I)
    canonical_url = urlunsplit((scheme or "https", netloc or "www.youtube.com", f"{base_path}/{surface}", "", ""))
    creator = base_path.split("/")[-1].lstrip("@") or "youtube-channel"
    return NormalizedTarget("youtube", "creator", canonical_url, creator=creator, surface=surface)


def _instagram_surface_and_code(text: str) -> tuple[str, str] | None:
    match = re.search(
        r"instagram\.com/(?:[A-Za-z0-9._]+/)?(reel|reels|p|tv)/([A-Za-z0-9_-]+)",
        text,
        re.I,
    )
    if not match:
        return None
    raw_surface = match.group(1).lower()
    code = match.group(2)
    if raw_surface in {"reel", "reels"}:
        return "reel", code
    if raw_surface == "p":
        return "post", code
    return "tv", code


def normalize_creator(provider: str, value: str) -> NormalizedTarget:
    provider = provider.lower()
    text = value.strip()
    if provider == "instagram":
        match = re.search(r"instagram\.com/([A-Za-z0-9._]+)", text, re.I)
        handle = _clean_handle(match.group(1) if match else text)
        if handle.lower() in {"reel", "reels", "p", "tv", "explore", "accounts"}:
            raise ValueError("Expected an Instagram creator, not a post URL.")
        return NormalizedTarget(provider, "creator", f"https://www.instagram.com/{handle}/reels/", creator=handle)

    if provider == "tiktok":
        match = re.search(r"tiktok\.com/@([A-Za-z0-9._-]+)", text, re.I)
        handle = _clean_handle(match.group(1) if match else text)
        return NormalizedTarget(provider, "creator", f"https://www.tiktok.com/@{handle}", creator=handle)

    if provider == "youtube":
        if text.startswith("@") and "/" not in text:
            handle = _clean_handle(text)
            return NormalizedTarget(provider, "creator", f"https://www.youtube.com/@{handle}/videos", creator=handle, surface="videos")
        match = re.search(r"youtube\.com/@([^/?#]+)", text, re.I)
        if match:
            path = urlsplit(text).path or f"/@{match.group(1)}"
            return _youtube_creator_target(path, scheme=urlsplit(text).scheme or "https", netloc=urlsplit(text).netloc or "www.youtube.com")
        channel = re.search(r"youtube\.com/channel/([^/?#]+)", text, re.I)
        if channel:
            path = urlsplit(text).path or f"/channel/{channel.group(1)}"
            return _youtube_creator_target(path, scheme=urlsplit(text).scheme or "https", netloc=urlsplit(text).netloc or "www.youtube.com")
        if "youtube.com" not in text and "youtu.be" not in text:
            handle = _clean_handle(text)
            return NormalizedTarget(provider, "creator", f"https://www.youtube.com/@{handle}/videos", creator=handle, surface="videos")
        parts = urlsplit(text)
        path = parts.path.rstrip("/")
        if any(token in path for token in ("/watch", "/shorts/", "/live/")) or parts.netloc.lower().endswith("youtu.be"):
            raise ValueError("Expected a YouTube channel, not a media URL.")
        return _youtube_creator_target(path, scheme=parts.scheme or "https", netloc=parts.netloc or "www.youtube.com")

    if provider == "bilibili":
        if BILIBILI_UID_RE.fullmatch(text):
            uid = text
            return NormalizedTarget(provider, "creator", f"https://space.bilibili.com/{uid}", creator=uid)
        match = re.search(r"space\.bilibili\.com/(\d+)", text, re.I)
        if match:
            uid = match.group(1)
            return NormalizedTarget(provider, "creator", f"https://space.bilibili.com/{uid}", creator=uid)
        raise ValueError("Expected a Bilibili space URL or numeric creator ID.")

    raise ValueError(f"Unsupported provider: {provider}")


def normalize_media(provider: str, value: str, creator: str | None = None) -> NormalizedTarget:
    provider = provider.lower()
    text = value.strip()

    if provider == "youtube":
        if YOUTUBE_ID_RE.fullmatch(text):
            return NormalizedTarget(provider, "media", f"https://www.youtube.com/watch?v={text}", media_id=text)
        parts = urlsplit(text)
        host = parts.netloc.lower()
        media_id = None
        if host.endswith("youtu.be"):
            media_id = parts.path.strip("/").split("/")[0]
        elif "/shorts/" in parts.path:
            media_id = parts.path.split("/shorts/", 1)[1].split("/", 1)[0]
        elif "/live/" in parts.path:
            media_id = parts.path.split("/live/", 1)[1].split("/", 1)[0]
        else:
            media_id = parse_qs(parts.query).get("v", [None])[0]
        if not media_id or not YOUTUBE_ID_RE.fullmatch(media_id):
            raise ValueError("Could not determine a YouTube video ID.")
        return NormalizedTarget(provider, "media", f"https://www.youtube.com/watch?v={media_id}", media_id=media_id)

    if provider == "tiktok":
        if TIKTOK_ID_RE.fullmatch(text):
            if not creator:
                raise ValueError("A TikTok creator handle is required when using a bare video ID.")
            handle = _clean_handle(creator)
            return NormalizedTarget(provider, "media", f"https://www.tiktok.com/@{handle}/video/{text}", creator=handle, media_id=text)
        match = re.search(r"tiktok\.com/@([A-Za-z0-9._-]+)/video/(\d+)", text, re.I)
        if not match:
            raise ValueError("Could not determine a TikTok creator and video ID.")
        handle, media_id = match.group(1), match.group(2)
        return NormalizedTarget(provider, "media", f"https://www.tiktok.com/@{handle}/video/{media_id}", creator=handle, media_id=media_id)

    if provider == "instagram":
        if INSTAGRAM_CODE_RE.fullmatch(text) and "instagram.com" not in text:
            return NormalizedTarget(provider, "media", f"https://www.instagram.com/reel/{text}/", media_id=text, surface="reel")
        resolved = _instagram_surface_and_code(text)
        if not resolved:
            raise ValueError("Could not determine an Instagram shortcode.")
        surface, code = resolved
        surface_path = "p" if surface == "post" else surface
        return NormalizedTarget(provider, "media", f"https://www.instagram.com/{surface_path}/{code}/", media_id=code, surface=surface)

    if provider == "bilibili":
        if BILIBILI_BVID_RE.fullmatch(text):
            return NormalizedTarget(provider, "media", f"https://www.bilibili.com/video/{text}", media_id=text)
        match = re.search(r"(BV[A-Za-z0-9]{10})", text)
        if not match:
            raise ValueError("Could not determine a Bilibili BV video ID.")
        bvid = match.group(1)
        return NormalizedTarget(provider, "media", f"https://www.bilibili.com/video/{bvid}", media_id=bvid)

    raise ValueError(f"Unsupported provider: {provider}")


def normalize_any(value: str, provider: str | None = None, kind: str | None = None, creator: str | None = None) -> NormalizedTarget:
    chosen = provider or detect_provider(value)
    if not chosen:
        raise ValueError("Provider is required for bare handles or media IDs.")
    if kind == "creator":
        return normalize_creator(chosen, value)
    if kind == "media":
        return normalize_media(chosen, value, creator=creator)
    try:
        return normalize_media(chosen, value, creator=creator)
    except ValueError:
        return normalize_creator(chosen, value)
