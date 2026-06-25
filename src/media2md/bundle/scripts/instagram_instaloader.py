#!/usr/bin/env python3
from __future__ import annotations

import argparse
import http.cookiejar
import json
import os
import sys
import urllib.request
from datetime import timezone
from pathlib import Path
from typing import Any, Iterable

ROOT = Path(__file__).resolve().parents[1]
COOKIE_FILE = ROOT / "data" / "secrets" / "instagram-cookies.txt"


def iso(value: Any) -> str | None:
    if value is None:
        return None
    try:
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc).isoformat(timespec="seconds")
    except Exception:
        return str(value)


def loader_context():
    try:
        import instaloader
    except ImportError as exc:
        raise RuntimeError("Instaloader is not installed. Install media2md[instagram].") from exc
    loader = instaloader.Instaloader(
        download_pictures=False,
        download_videos=False,
        download_video_thumbnails=False,
        download_geotags=False,
        download_comments=False,
        save_metadata=False,
        compress_json=False,
        quiet=True,
    )
    if COOKIE_FILE.is_file():
        jar = http.cookiejar.MozillaCookieJar(str(COOKIE_FILE))
        try:
            jar.load(ignore_discard=True, ignore_expires=True)
            for cookie in jar:
                loader.context._session.cookies.set(
                    cookie.name,
                    cookie.value,
                    domain=cookie.domain,
                    path=cookie.path or "/",
                )
        except Exception as exc:
            raise RuntimeError(f"Could not load Instagram cookies for Instaloader: {exc}") from exc
    return loader


def reels_iterator(profile: Any) -> Iterable[Any]:
    getter = getattr(profile, "get_reels", None)
    if callable(getter):
        return getter()
    # Compatibility fallback for older Instaloader versions. This can include
    # non-Reel video posts, but is preferable to losing all fallback coverage.
    return (post for post in profile.get_posts() if getattr(post, "is_video", False))


def catalog(username: str, start: int, end: int) -> list[dict[str, Any]]:
    import instaloader
    loader = loader_context()
    profile = instaloader.Profile.from_username(loader.context, username)
    items: list[dict[str, Any]] = []
    for index, post in enumerate(reels_iterator(profile), start=1):
        if index < start:
            continue
        if index > end:
            break
        shortcode = str(post.shortcode)
        items.append({
            "shortcode": shortcode,
            "published_at": iso(getattr(post, "date_utc", None)),
            "source_url": f"https://www.instagram.com/reel/{shortcode}/",
            "caption": str(getattr(post, "caption", None) or ""),
            "media_id": str(getattr(post, "mediaid", None) or ""),
        })
    return items


def media_urls(post: Any) -> list[str]:
    urls: list[str] = []
    video_url = getattr(post, "video_url", None)
    if video_url:
        urls.append(str(video_url))
    sidecar = getattr(post, "get_sidecar_nodes", None)
    if callable(sidecar):
        try:
            for node in sidecar():
                if getattr(node, "is_video", False) and getattr(node, "video_url", None):
                    url = str(node.video_url)
                    if url not in urls:
                        urls.append(url)
        except Exception:
            pass
    return urls



def inspect_post(shortcode: str) -> dict[str, Any]:
    import instaloader
    loader = loader_context()
    post = instaloader.Post.from_shortcode(loader.context, shortcode)
    owner = getattr(post, "owner_profile", None)
    username = str(getattr(owner, "username", None) or "unknown")
    owner_id = str(getattr(owner, "userid", None) or username)
    return {
        "provider": "instagram",
        "external_id": str(post.shortcode),
        "creator": username,
        "creator_external_id": owner_id,
        "creator_display_name": str(getattr(owner, "full_name", None) or username),
        "title": f"Instagram Reel {post.shortcode}",
        "description": str(getattr(post, "caption", None) or ""),
        "published_at": iso(getattr(post, "date_utc", None)),
        "duration_seconds": getattr(post, "video_duration", None),
        "source_url": f"https://www.instagram.com/reel/{post.shortcode}/",
        "backend_used": "instaloader",
    }


def download(shortcode: str, output_dir: Path) -> list[Path]:
    import instaloader
    loader = loader_context()
    post = instaloader.Post.from_shortcode(loader.context, shortcode)
    urls = media_urls(post)
    if not urls:
        raise RuntimeError("Instaloader found the post but no downloadable video URL.")
    output_dir.mkdir(parents=True, exist_ok=True)
    opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(loader.context._session.cookies))
    files: list[Path] = []
    for index, url in enumerate(urls, start=1):
        target = output_dir / f"{shortcode}_{index}.mp4"
        request = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0", "Referer": f"https://www.instagram.com/reel/{shortcode}/"})
        with opener.open(request, timeout=180) as response, target.open("wb") as handle:
            while True:
                chunk = response.read(1024 * 1024)
                if not chunk:
                    break
                handle.write(chunk)
        if target.stat().st_size <= 0:
            target.unlink(missing_ok=True)
            raise RuntimeError("Instaloader fallback created an empty media file.")
        files.append(target)
    return files


def main() -> int:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)
    cat = sub.add_parser("catalog")
    cat.add_argument("username")
    cat.add_argument("--start", type=int, required=True)
    cat.add_argument("--end", type=int, required=True)
    inspect = sub.add_parser("inspect")
    inspect.add_argument("shortcode")
    dl = sub.add_parser("download")
    dl.add_argument("shortcode")
    dl.add_argument("--output-dir", required=True)
    args = parser.parse_args()
    if args.command == "catalog":
        print(json.dumps(catalog(args.username, args.start, args.end), ensure_ascii=False))
        return 0
    if args.command == "inspect":
        print(json.dumps(inspect_post(args.shortcode), ensure_ascii=False))
        return 0
    paths = download(args.shortcode, Path(args.output_dir))
    print(json.dumps([str(path) for path in paths], ensure_ascii=False))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        raise SystemExit(130)
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise SystemExit(1)
