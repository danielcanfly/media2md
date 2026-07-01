from __future__ import annotations

from .instagram import InstagramAdapter
from .tiktok import TikTokAdapter
from .youtube import YouTubeAdapter


def get_provider_adapters():
    return [
        InstagramAdapter(),
        YouTubeAdapter(),
        TikTokAdapter(),
    ]
from .bilibili import BilibiliAdapter
from .instagram import InstagramAdapter
from .tiktok import TikTokAdapter
from .youtube import YouTubeAdapter


def get_provider_adapters():
    return [
        InstagramAdapter(),
        YouTubeAdapter(),
        TikTokAdapter(),
        BilibiliAdapter(),
    ]
