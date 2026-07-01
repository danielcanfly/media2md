from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _load_module(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec is not None and spec.loader is not None
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def test_shared_instagram_media_normalization_preserves_surface():
    from media2md.urls import normalize_media

    post = normalize_media("instagram", "https://www.instagram.com/p/ABC123xyz9/")
    shared_post = normalize_media("instagram", "https://www.instagram.com/creator.name/p/ABC123xyz9/?img_index=2")
    reel = normalize_media("instagram", "https://www.instagram.com/reel/ABC123xyz9/")
    tv = normalize_media("instagram", "https://www.instagram.com/tv/ABC123xyz9/")

    assert post.canonical_url == "https://www.instagram.com/p/ABC123xyz9/"
    assert post.surface == "post"
    assert shared_post.canonical_url == "https://www.instagram.com/p/ABC123xyz9/"
    assert shared_post.surface == "post"
    assert reel.canonical_url == "https://www.instagram.com/reel/ABC123xyz9/"
    assert reel.surface == "reel"
    assert tv.canonical_url == "https://www.instagram.com/tv/ABC123xyz9/"
    assert tv.surface == "tv"


def test_bundled_instagram_media_normalization_preserves_surface():
    bundled_urls = _load_module(
        ROOT / "src" / "media2md" / "bundle" / "scripts" / "media2md_urls.py",
        "test_batch_a_media2md_urls",
    )

    post = bundled_urls.normalize_media("instagram", "https://www.instagram.com/p/ABC123xyz9/")
    shared_post = bundled_urls.normalize_media("instagram", "https://www.instagram.com/creator.name/p/ABC123xyz9/?img_index=2")
    carousel = bundled_urls.normalize_media("instagram", "https://www.instagram.com/p/CAROUSEL12/")

    assert post.canonical_url == "https://www.instagram.com/p/ABC123xyz9/"
    assert post.surface == "post"
    assert shared_post.canonical_url == "https://www.instagram.com/p/ABC123xyz9/"
    assert shared_post.surface == "post"
    assert carousel.surface == "post"


def test_instagram_media_types_include_post_and_carousel():
    media_types = _load_module(
        ROOT / "src" / "media2md" / "bundle" / "scripts" / "media2md_types.py",
        "test_batch_a_media2md_types",
    )

    assert media_types.infer_media_type("instagram", "https://www.instagram.com/p/ABC123xyz9/") == "instagram_post"
    assert media_types.infer_media_type("instagram", "https://www.instagram.com/reel/ABC123xyz9/") == "instagram_reel"
    assert media_types.output_bucket("instagram_post") == "posts"
    assert media_types.output_bucket("instagram_carousel") == "posts"


def test_bilibili_media_normalization_and_type_support():
    from media2md.urls import detect_provider, normalize_media

    target = normalize_media("bilibili", "https://www.bilibili.com/video/BV1xx411c7mD/?spm_id_from=333.1007.tianma.1-1-1.click")
    bare = normalize_media("bilibili", "BV1xx411c7mD")

    assert detect_provider("BV1xx411c7mD") == "bilibili"
    assert target.canonical_url == "https://www.bilibili.com/video/BV1xx411c7mD"
    assert target.media_id == "BV1xx411c7mD"
    assert bare.canonical_url == "https://www.bilibili.com/video/BV1xx411c7mD"


def test_bilibili_creator_normalization_supports_space_url_and_mid():
    from media2md.urls import normalize_creator

    space = normalize_creator("bilibili", "https://space.bilibili.com/2")
    bare = normalize_creator("bilibili", "2")

    assert space.canonical_url == "https://space.bilibili.com/2"
    assert space.creator == "2"
    assert bare.canonical_url == "https://space.bilibili.com/2"
    assert bare.creator == "2"


def test_bundled_bilibili_media_type_support():
    media_types = _load_module(
        ROOT / "src" / "media2md" / "bundle" / "scripts" / "media2md_types.py",
        "test_batch_b_bilibili_media2md_types",
    )

    assert media_types.infer_media_type("bilibili", "https://www.bilibili.com/video/BV1xx411c7mD") == "bilibili_video"
    assert media_types.output_bucket("bilibili_video") == "videos"


def test_generic_media_instagram_instaloader_post_payload_is_classified(monkeypatch):
    generic_media = _load_module(
        ROOT / "src" / "media2md" / "bundle" / "scripts" / "generic_media.py",
        "test_batch_a_generic_media",
    )

    payload = {
        "provider": "instagram",
        "external_id": "ABC123xyz9",
        "creator": "creator.name",
        "creator_external_id": "12345",
        "creator_display_name": "Creator Name",
        "title": "Instagram Post ABC123xyz9",
        "description": "caption",
        "published_at": "2026-06-30T00:00:00+00:00",
        "duration_seconds": None,
        "source_url": "https://www.instagram.com/p/ABC123xyz9/",
        "backend_used": "instaloader",
        "surface": "post",
        "assets": [
            {"index": 1, "kind": "image", "source_url": "https://cdn.example.com/1.jpg", "ocr_candidate": True},
            {"index": 2, "kind": "image", "source_url": "https://cdn.example.com/2.jpg", "ocr_candidate": True},
        ],
    }

    monkeypatch.setattr(generic_media, "_inspect_instagram_instaloader", lambda shortcode: dict(payload))
    monkeypatch.setattr(generic_media, "instagram_backend", lambda: "instaloader")

    result = generic_media.inspect("https://www.instagram.com/p/ABC123xyz9/", provider="instagram")

    assert result["surface"] == "post"
    assert result["source_url"] == "https://www.instagram.com/p/ABC123xyz9/"
    assert result["media_type"] == "instagram_carousel"
    assert result["processing_class"] == "instagram_carousel"
    assert len(result["assets"]) == 2


def test_instagram_gallery_metadata_classifies_single_post_and_preserves_surface(monkeypatch):
    generic_media = _load_module(
        ROOT / "src" / "media2md" / "bundle" / "scripts" / "generic_media.py",
        "test_batch_a_generic_media_gallery",
    )
    target = type("Target", (), {"media_id": "ABC123xyz9", "surface": "post"})()

    metadata = [
        [
            1,
            "url",
            {
                "post_shortcode": "ABC123xyz9",
                "username": "creator.name",
                "description": "caption",
                "post_date": "2026-06-30T00:00:00+00:00",
                "image_count": 1,
            },
        ]
    ]

    monkeypatch.setattr(generic_media, "command", lambda name: "/usr/bin/gallery-dl")
    monkeypatch.setattr(
        generic_media,
        "run",
        lambda cmd, timeout=300: type("Result", (), {"stdout": json.dumps(metadata)})(),
    )

    result = generic_media._inspect_instagram_gallery(
        "https://www.instagram.com/p/ABC123xyz9/",
        target,
        "creator.name",
    )

    assert result["surface"] == "post"
    assert result["media_type"] == "instagram_post"
    assert result["processing_class"] == "instagram_post"
    assert result["source_url"] == "https://www.instagram.com/p/ABC123xyz9/"


def test_instagram_gallery_metadata_builds_assets_for_carousel(monkeypatch):
    generic_media = _load_module(
        ROOT / "src" / "media2md" / "bundle" / "scripts" / "generic_media.py",
        "test_batch_a_generic_media_gallery_assets",
    )
    target = type("Target", (), {"media_id": "ABC123xyz9", "surface": "post"})()

    metadata = [
        [2, {"post_shortcode": "ABC123xyz9", "username": "creator.name", "description": "caption", "post_date": "2026-06-30T00:00:00+00:00", "count": 2}],
        [3, "https://cdn.example.com/1.jpg", {"num": 1, "display_url": "https://cdn.example.com/1.jpg", "extension": "jpg", "width": 1000, "height": 1200}],
        [3, "https://cdn.example.com/2.mp4", {"num": 2, "display_url": "https://cdn.example.com/2.jpg", "video_url": "https://cdn.example.com/2.mp4", "extension": "mp4", "width": 1000, "height": 1200}],
    ]

    monkeypatch.setattr(generic_media, "command", lambda name: "/usr/bin/gallery-dl")
    monkeypatch.setattr(
        generic_media,
        "run",
        lambda cmd, timeout=300: type("Result", (), {"stdout": json.dumps(metadata)})(),
    )

    result = generic_media._inspect_instagram_gallery(
        "https://www.instagram.com/p/ABC123xyz9/",
        target,
        "creator.name",
    )

    assert result["media_type"] == "instagram_carousel"
    assert len(result["assets"]) == 2
    assert result["assets"][0]["kind"] == "image"
    assert result["assets"][1]["kind"] == "video"
    assert result["assets"][1]["source_url"] == "https://cdn.example.com/2.mp4"


def test_generic_media_inspect_preserves_post_surface_with_query(monkeypatch):
    generic_media = _load_module(
        ROOT / "src" / "media2md" / "bundle" / "scripts" / "generic_media.py",
        "test_batch_a_generic_media_query_surface",
    )

    monkeypatch.setattr(generic_media, "instagram_backend", lambda: "gallery-dl")
    monkeypatch.setattr(
        generic_media,
        "_inspect_instagram_gallery",
        lambda url, target, creator: {
            "provider": "instagram",
            "external_id": "DZ-Inv7mJE2",
            "creator": "sifuyik",
            "creator_external_id": "74431679764",
            "creator_identifiers": {"user_id": "74431679764"},
            "creator_display_name": "sifuyik",
            "title": "Instagram Post DZ-Inv7mJE2",
            "description": "caption",
            "published_at": "2026-06-24 13:47:48",
            "duration_seconds": None,
            "source_url": "https://www.instagram.com/p/DZ-Inv7mJE2/",
            "surface": "post",
            "media_type": "instagram_carousel",
            "processing_class": "instagram_carousel",
            "assets": [
                {"index": 1, "kind": "image", "source_url": "https://cdn.example.com/1.jpg", "ocr_candidate": True},
                {"index": 2, "kind": "image", "source_url": "https://cdn.example.com/2.jpg", "ocr_candidate": True},
            ],
            "backend_used": "gallery-dl",
        },
    )

    result = generic_media.inspect("https://www.instagram.com/p/DZ-Inv7mJE2/?img_index=1", provider="instagram")

    assert result["source_url"] == "https://www.instagram.com/p/DZ-Inv7mJE2/"
    assert result["media_type"] == "instagram_carousel"
    assert result["processing_class"] == "instagram_carousel"


def test_instagram_instaloader_catalog_can_emit_posts_surface(monkeypatch):
    module = _load_module(
        ROOT / "src" / "media2md" / "bundle" / "scripts" / "instagram_instaloader.py",
        "test_batch_a_instagram_instaloader_catalog_posts",
    )

    class _Post:
        def __init__(self, shortcode: str, typename: str, is_video: bool = False):
            self.shortcode = shortcode
            self.typename = typename
            self.is_video = is_video
            self.caption = "caption"
            self.mediaid = 123
            self.date_utc = None

        def get_sidecar_nodes(self):
            return []

    class _Profile:
        def get_posts(self):
            return [
                _Post("REEL001", "GraphVideo", True),
                _Post("POST001", "GraphImage", False),
                _Post("POST002", "GraphSidecar", False),
            ]

    class _ProfileLoader:
        @staticmethod
        def from_username(context, username):
            return _Profile()

    monkeypatch.setattr(module, "loader_context", lambda: type("Loader", (), {"context": object()})())
    monkeypatch.setitem(sys.modules, "instaloader", type("InstaloaderModule", (), {"Profile": _ProfileLoader})())

    items = module.catalog("creator.name", 1, 5, "posts")
    assert [item["shortcode"] for item in items] == ["POST001", "POST002"]
    assert all(item["surface"] == "post" for item in items)
    assert all(item["source_url"].startswith("https://www.instagram.com/p/") for item in items)


def test_instagram_instaloader_catalog_can_emit_mixed_surface(monkeypatch):
    module = _load_module(
        ROOT / "src" / "media2md" / "bundle" / "scripts" / "instagram_instaloader.py",
        "test_batch_a_instagram_instaloader_catalog_mixed",
    )

    class _Post:
        def __init__(self, shortcode: str, typename: str, is_video: bool = False):
            self.shortcode = shortcode
            self.typename = typename
            self.is_video = is_video
            self.caption = "caption"
            self.mediaid = 123
            self.date_utc = None

        def get_sidecar_nodes(self):
            return []

    class _Profile:
        def get_posts(self):
            return [
                _Post("REEL001", "GraphVideo", True),
                _Post("POST001", "GraphImage", False),
            ]

    class _ProfileLoader:
        @staticmethod
        def from_username(context, username):
            return _Profile()

    monkeypatch.setattr(module, "loader_context", lambda: type("Loader", (), {"context": object()})())
    monkeypatch.setitem(sys.modules, "instaloader", type("InstaloaderModule", (), {"Profile": _ProfileLoader})())

    items = module.catalog("creator.name", 1, 5, "mixed")
    assert [item["shortcode"] for item in items] == ["REEL001", "POST001"]
    assert items[0]["surface"] == "reel"
    assert items[1]["surface"] == "post"
