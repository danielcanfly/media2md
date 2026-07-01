#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any

import process_worker_impl as impl

ROOT = Path(__file__).resolve().parents[1]
CONFIG_PATH = ROOT / "config" / "social2md.json"

PACKS = {
    "en": {
        "title": "Instagram Reel",
        "caption": "Original Caption",
        "transcript": "Transcript",
        "part": "Part",
        "source_media": "Source media",
        "no_caption": "_No caption provided._",
        "no_speech": "_No speech detected._",
    },
    "zh-TW": {
        "title": "Instagram Reel",
        "caption": "原始 Caption",
        "transcript": "語音逐字稿",
        "part": "部分",
        "source_media": "來源媒體",
        "no_caption": "_沒有 Caption。_",
        "no_speech": "_未偵測到語音。_",
    },
    "zh-CN": {
        "title": "Instagram Reel",
        "caption": "原始 Caption",
        "transcript": "语音转录",
        "part": "部分",
        "source_media": "来源媒体",
        "no_caption": "_没有 Caption。_",
        "no_speech": "_未检测到语音。_",
    },
    "ja": {
        "title": "Instagram Reel",
        "caption": "元のキャプション",
        "transcript": "文字起こし",
        "part": "パート",
        "source_media": "ソースメディア",
        "no_caption": "_キャプションはありません。_",
        "no_speech": "_音声は検出されませんでした。_",
    },
}


def markdown_locale() -> str:
    explicit = os.getenv("SOCIAL2MD_MARKDOWN_LOCALE")
    if explicit in PACKS:
        return explicit
    try:
        payload = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
        value = payload.get("markdown_locale")
        if value in PACKS:
            return value
    except (OSError, json.JSONDecodeError):
        pass
    return "en"


def render_markdown(video, transcripts, model, temp_dir, final_path):
    media_type = str(video["media_type"] if "media_type" in video.keys() and video["media_type"] else "instagram_reel")
    bucket = "posts" if media_type in {"instagram_post", "instagram_carousel"} else "reels"
    final_path = ROOT / "markdown" / "instagram" / video["username"] / bucket / f"{video['shortcode']}.md"
    locale = markdown_locale()
    pack = PACKS[locale]
    temp_dir.mkdir(parents=True, exist_ok=True)
    final_path.parent.mkdir(parents=True, exist_ok=True)
    caption = (video["caption"] or "").strip()
    lines = [
        "---",
        "platform: instagram",
        f"creator: {impl.yaml_value(video['username'])}",
        f"shortcode: {impl.yaml_value(video['shortcode'])}",
        f"source_url: {impl.yaml_value(video['source_url'])}",
        f"published_at: {impl.yaml_value(video['published_at'])}",
        f"processed_at: {impl.yaml_value(impl.iso_now())}",
        f"transcription_model: {impl.yaml_value(model)}",
        f"document_locale: {impl.yaml_value(locale)}",
        "---",
        "",
        f"# {pack['title']}: {video['shortcode']}",
        "",
        f"## {pack['caption']}",
        "<!-- compatibility: ## 原始 Caption -->",
        "",
        caption or pack["no_caption"],
        "",
        f"## {pack['transcript']}",
        "<!-- compatibility: ## 語音逐字稿 -->",
        "",
    ]
    for index, (media, text) in enumerate(transcripts, start=1):
        if len(transcripts) > 1:
            lines.extend([
                f"### {pack['part']} {index}",
                "",
                f"{pack['source_media']}: `{media.name}`",
                "",
            ])
        lines.extend([text or pack["no_speech"], ""])
    content = "\n".join(lines).rstrip() + "\n"
    temp_path = temp_dir / f".{video['shortcode']}.md.tmp"
    temp_path.write_text(content, encoding="utf-8")
    required = (
        video["shortcode"],
        video["source_url"],
        "## 原始 Caption",
        "## 語音逐字稿",
    )
    if temp_path.stat().st_size < 150 or any(token not in content for token in required):
        raise RuntimeError("Rendered Markdown failed validation")
    os.replace(temp_path, final_path)
    return final_path, impl.sha256_file(final_path)


impl.render_markdown = render_markdown

def reset_interrupted_shortcode() -> None:
    shortcode = None
    for index, value in enumerate(sys.argv):
        if value == "--shortcode" and index + 1 < len(sys.argv):
            shortcode = sys.argv[index + 1]
            break
    if not shortcode:
        return
    try:
        connection = impl.connect()
        connection.execute(
            """
            UPDATE videos
            SET status = 'pending',
                next_retry_at = NULL,
                last_error = 'Interrupted by user; safe to resume',
                updated_at = ?
            WHERE shortcode = ?
              AND status IN ('downloading','downloaded','transcribing','transcribed','rendering','validating','cleaning')
            """,
            (impl.iso_now(), shortcode),
        )
        connection.commit()
        connection.close()
    except Exception as exc:
        print(f"WARNING: Could not requeue interrupted item: {exc}", file=sys.stderr)


if __name__ == "__main__":
    try:
        raise SystemExit(impl.main())
    except KeyboardInterrupt:
        reset_interrupted_shortcode()
        print("WORKER_INTERRUPTED", file=sys.stderr)
        raise SystemExit(130)
