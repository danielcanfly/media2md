from __future__ import annotations

PROVIDERS = {
    "instagram": {
        "single_media": True,
        "creator_sync": True,
        "batch_drain": True,
        "backends": ["gallery-dl", "instaloader"],
        "default_backend": "auto",
        "extra": "instagram",
    },
    "youtube": {
        "single_media": True,
        "creator_sync": True,
        "batch_drain": True,
        "backends": ["yt-dlp", "yt-dlp-ejs"],
        "extra": "youtube",
    },
    "tiktok": {
        "single_media": True,
        "creator_sync": True,
        "batch_drain": True,
        "backends": ["yt-dlp"],
        "extra": "tiktok",
    },
}
