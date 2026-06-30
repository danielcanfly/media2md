from __future__ import annotations

import importlib.util
import sqlite3
import sys
from pathlib import Path
from types import SimpleNamespace


ROOT = Path(__file__).resolve().parents[1]


def _load_module(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec is not None and spec.loader is not None
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def test_ocr_engine_routing_prefers_vision_on_macos(monkeypatch):
    ocr = _load_module(
        ROOT / "src" / "media2md" / "bundle" / "scripts" / "media2md_ocr.py",
        "test_batch_b_ocr_routing",
    )
    monkeypatch.setattr(ocr, "_platform_key", lambda: "macos")
    assert ocr.preferred_ocr_engine({}) == "vision"
    assert ocr.fallback_ocr_engine({}) == "easyocr"
    assert ocr.ocr_install_extra() == "ocr-mac-os"


def test_ocr_engine_routing_prefers_easyocr_on_linux(monkeypatch):
    ocr = _load_module(
        ROOT / "src" / "media2md" / "bundle" / "scripts" / "media2md_ocr.py",
        "test_batch_b_ocr_routing_linux",
    )
    monkeypatch.setattr(ocr, "_platform_key", lambda: "linux")
    assert ocr.preferred_ocr_engine({}) == "easyocr"
    assert ocr.fallback_ocr_engine({}) is None
    assert ocr.ocr_install_extra() == "ocr-windows-linux"


def test_render_instagram_post_markdown_groups_per_image(monkeypatch, tmp_path: Path):
    generic_media = _load_module(
        ROOT / "src" / "media2md" / "bundle" / "scripts" / "generic_media.py",
        "test_batch_b_generic_media_render",
    )

    image1 = tmp_path / "asset_1.jpg"
    image2 = tmp_path / "asset_2.jpg"
    image1.write_bytes(b"image-1")
    image2.write_bytes(b"image-2")

    monkeypatch.setattr(generic_media, "_instagram_media_assets", lambda metadata, work: [image1, image2])
    monkeypatch.setattr(
        generic_media,
        "perform_ocr",
        lambda image, config=None: {
            "engine": "vision",
            "text": f"text for {image.name}",
            "lines": [f"text for {image.name}"],
            "status": "ok",
        },
    )

    content = generic_media.render_instagram_post_markdown(
        metadata={
            "description": "caption text",
            "source_url": "https://www.instagram.com/p/ABC123xyz9/",
        },
        creator="creator.name",
        external_id="ABC123xyz9",
        media_type="instagram_carousel",
        item_class="instagram_carousel",
        artifact_stem="instagram-ABC123xyz9",
        canonical_source="https://www.instagram.com/p/ABC123xyz9/",
        published_at="2026-06-30T00:00:00+00:00",
        work=tmp_path,
    )

    assert "## Image OCR" in content
    assert "### Image 1" in content
    assert "### Image 2" in content
    assert "text for asset_1.jpg" in content
    assert "text for asset_2.jpg" in content
    assert "## Combined OCR Notes" in content


def test_process_row_instagram_post_uses_ocr_rendering(monkeypatch, tmp_path: Path):
    generic_media = _load_module(
        ROOT / "src" / "media2md" / "bundle" / "scripts" / "generic_media.py",
        "test_batch_b_generic_media_process",
    )

    db = sqlite3.connect(":memory:")
    db.row_factory = sqlite3.Row
    db.execute(
        """
        CREATE TABLE media (
            id INTEGER PRIMARY KEY,
            provider TEXT,
            external_id TEXT,
            creator TEXT,
            title TEXT,
            description TEXT,
            source_url TEXT,
            published_at TEXT,
            duration_seconds REAL,
            media_type TEXT,
            processing_class TEXT,
            status TEXT,
            markdown_path TEXT,
            markdown_sha256 TEXT,
            last_error TEXT,
            created_at TEXT,
            updated_at TEXT,
            completed_at TEXT
        )
        """
    )
    db.execute(
        """
        INSERT INTO media (
            id, provider, external_id, creator, title, description, source_url,
            published_at, duration_seconds, media_type, processing_class, status,
            created_at, updated_at
        ) VALUES (
            1, 'instagram', 'ABC123xyz9', 'creator.name', 'Instagram Post ABC123xyz9',
            'caption text', 'https://www.instagram.com/p/ABC123xyz9/',
            '2026-06-30T00:00:00+00:00', NULL, 'instagram_post', 'instagram_post',
            'pending', '2026-06-30T00:00:00+00:00', '2026-06-30T00:00:00+00:00'
        )
        """
    )
    row = db.execute("SELECT * FROM media WHERE id=1").fetchone()

    monkeypatch.setattr(generic_media, "DOWNLOADS", generic_media.ROOT / "workspace" / "test-downloads")
    monkeypatch.setattr(generic_media, "TRANSCRIPTS", generic_media.ROOT / "workspace" / "test-transcripts")
    monkeypatch.setattr(generic_media, "MARKDOWN", generic_media.ROOT / "markdown-test")
    monkeypatch.setattr(generic_media, "load_config", lambda: {})
    monkeypatch.setattr(
        generic_media,
        "_hydrate_instagram_post_metadata",
        lambda canonical_source, creator=None: {
            "provider": "instagram",
            "external_id": "ABC123xyz9",
            "creator": creator or "creator.name",
            "description": "caption text",
            "source_url": canonical_source,
            "assets": [{"index": 1, "kind": "image", "source_url": "https://cdn.example.com/1.jpg", "ocr_candidate": True}],
        },
    )
    monkeypatch.setattr(
        generic_media,
        "render_instagram_post_markdown",
        lambda **kwargs: (
            "---\n"
            "platform: instagram\n"
            "creator: \"creator.name\"\n"
            "media_id: \"ABC123xyz9\"\n"
            "media_type: \"instagram_post\"\n"
            "---\n\n"
            "# Instagram Post: ABC123xyz9\n\n"
            "## Description\n\n"
            "caption text\n\n"
            "## Image OCR\n\n"
            "### Image 1\n\n"
            "hello world from image\n\n"
            "## Combined OCR Notes\n\n"
            "hello world from image\n"
        ),
    )
    monkeypatch.setattr(generic_media, "canonical_media_source", lambda provider, external_id, source_url, creator: source_url)

    processed = generic_media.process_row(db, row)
    final = Path(processed["final_path"])

    assert final.is_file()
    assert final.read_text(encoding="utf-8").startswith("---\nplatform: instagram")
    saved = db.execute("SELECT status, markdown_path FROM media WHERE id=1").fetchone()
    assert saved["status"] == "completed"
    assert str(saved["markdown_path"]).endswith(".md")
    final.unlink(missing_ok=True)


def test_process_row_commits_completed_state_for_instagram_post(monkeypatch, tmp_path: Path):
    generic_media = _load_module(
        ROOT / "src" / "media2md" / "bundle" / "scripts" / "generic_media.py",
        "test_batch_b_generic_media_commit_state",
    )

    db_path = tmp_path / "media.db"
    db = sqlite3.connect(db_path)
    db.row_factory = sqlite3.Row
    db.execute(
        """
        CREATE TABLE media (
            id INTEGER PRIMARY KEY,
            provider TEXT,
            external_id TEXT,
            creator TEXT,
            title TEXT,
            description TEXT,
            source_url TEXT,
            published_at TEXT,
            duration_seconds REAL,
            media_type TEXT,
            processing_class TEXT,
            status TEXT,
            markdown_path TEXT,
            markdown_sha256 TEXT,
            last_error TEXT,
            created_at TEXT,
            updated_at TEXT,
            completed_at TEXT
        )
        """
    )
    db.execute(
        """
        INSERT INTO media (
            id, provider, external_id, creator, title, description, source_url,
            published_at, duration_seconds, media_type, processing_class, status,
            created_at, updated_at
        ) VALUES (
            1, 'instagram', 'ABC123xyz9', 'creator.name', 'Instagram Post ABC123xyz9',
            'caption text', 'https://www.instagram.com/p/ABC123xyz9/',
            '2026-06-30T00:00:00+00:00', NULL, 'instagram_post', 'instagram_post',
            'pending', '2026-06-30T00:00:00+00:00', '2026-06-30T00:00:00+00:00'
        )
        """
    )
    row = db.execute("SELECT * FROM media WHERE id=1").fetchone()

    monkeypatch.setattr(generic_media, "DOWNLOADS", generic_media.ROOT / "workspace" / "test-downloads")
    monkeypatch.setattr(generic_media, "TRANSCRIPTS", generic_media.ROOT / "workspace" / "test-transcripts")
    monkeypatch.setattr(generic_media, "MARKDOWN", generic_media.ROOT / "markdown-test")
    monkeypatch.setattr(generic_media, "load_config", lambda: {})
    monkeypatch.setattr(
        generic_media,
        "_hydrate_instagram_post_metadata",
        lambda canonical_source, creator=None: {
            "provider": "instagram",
            "external_id": "ABC123xyz9",
            "creator": creator or "creator.name",
            "description": "caption text",
            "source_url": canonical_source,
            "assets": [{"index": 1, "kind": "image", "source_url": "https://cdn.example.com/1.jpg", "ocr_candidate": True}],
        },
    )
    monkeypatch.setattr(
        generic_media,
        "render_instagram_post_markdown",
        lambda **kwargs: (
            "---\n"
            "platform: instagram\n"
            "creator: \"creator.name\"\n"
            "media_id: \"ABC123xyz9\"\n"
            "media_type: \"instagram_post\"\n"
            "---\n\n"
            "# Instagram Post: ABC123xyz9\n\n"
            "## Description\n\n"
            "caption text\n\n"
            "## Image OCR\n\n"
            "### Image 1\n\n"
            "hello world from image\n\n"
            "## Combined OCR Notes\n\n"
            "hello world from image\n"
        ),
    )
    monkeypatch.setattr(generic_media, "canonical_media_source", lambda provider, external_id, source_url, creator: source_url)
    monkeypatch.setattr(generic_media, "sync_registry", lambda provider, external_id, row: None)

    generic_media.process_row(db, row)
    db.close()

    verify = sqlite3.connect(db_path)
    verify.row_factory = sqlite3.Row
    saved = verify.execute("SELECT status, markdown_path, completed_at, last_error FROM media WHERE id=1").fetchone()
    assert saved["status"] == "completed"
    assert str(saved["markdown_path"]).endswith(".md")
    assert saved["completed_at"]
    assert saved["last_error"] is None
    verify.close()
    final = generic_media.ROOT / "markdown-test" / "instagram" / "creator.name" / "posts" / "ABC123xyz9.md"
    final.unlink(missing_ok=True)


def test_easyocr_language_candidates_respect_locale_hints():
    ocr = _load_module(
        ROOT / "src" / "media2md" / "bundle" / "scripts" / "media2md_ocr.py",
        "test_batch_b_easyocr_candidates",
    )
    assert ocr._easyocr_language_candidates({"markdown_language": "zh-TW"})[0] == ["ch_tra", "en"]
    assert ocr._easyocr_language_candidates({"markdown_language": "zh-CN"})[0] == ["ch_sim", "en"]
    assert ocr._easyocr_language_candidates({"markdown_language": "ja"})[0] == ["ja", "en"]


def test_perform_easyocr_tries_compatible_language_sets(monkeypatch, tmp_path: Path):
    ocr = _load_module(
        ROOT / "src" / "media2md" / "bundle" / "scripts" / "media2md_ocr.py",
        "test_batch_b_easyocr_fallbacks",
    )
    image = tmp_path / "asset.jpg"
    image.write_bytes(b"image")
    calls: list[list[str]] = []

    class _Reader:
        def __init__(self, langs, **kwargs):
            calls.append(list(langs))
            if list(langs) == ["ja", "en"]:
                raise RuntimeError("bad combo for this image")

        def readtext(self, path, detail=0, paragraph=False):
            return ["hello world"]

    monkeypatch.setitem(sys.modules, "easyocr", SimpleNamespace(Reader=_Reader))
    monkeypatch.setattr(ocr, "_easyocr_model_paths", lambda: (tmp_path / "model", tmp_path / "user"))

    result = ocr._perform_easyocr(image)

    assert result["engine"] == "easyocr"
    assert result["text"] == "hello world"
    assert calls[0] == ["ja", "en"]
    assert calls[1] == ["ch_tra", "en"]
