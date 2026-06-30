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


def _surface_for_post(post: Any) -> str:
    typename = str(getattr(post, "typename", "") or "").strip()
    if typename == "GraphImage":
        return "post"
    if typename == "GraphSidecar":
        return "post"
    if bool(getattr(post, "is_video", False)):
        return "reel"
    return "post"


def _assets_for_post(post: Any) -> list[dict[str, Any]]:
    assets: list[dict[str, Any]] = []
    sidecar = getattr(post, "get_sidecar_nodes", None)
    if callable(sidecar):
        try:
            for index, node in enumerate(sidecar(), start=1):
                is_video = bool(getattr(node, "is_video", False))
                display_url = str(getattr(node, "display_url", None) or "")
                video_url = str(getattr(node, "video_url", None) or "")
                asset_url = video_url if is_video and video_url else display_url
                if not asset_url:
                    continue
                width = getattr(node, "display_width", None)
                height = getattr(node, "display_height", None)
                assets.append(
                    {
                        "index": index,
                        "kind": "video" if is_video else "image",
                        "source_url": asset_url,
                        "display_url": display_url or asset_url,
                        "width": int(width) if width else None,
                        "height": int(height) if height else None,
                        "ocr_candidate": not is_video,
                    }
                )
        except Exception:
            assets = []
    if assets:
        return assets
    is_video = bool(getattr(post, "is_video", False))
    display_url = str(getattr(post, "url", None) or getattr(post, "display_url", None) or "")
    video_url = str(getattr(post, "video_url", None) or "")
    asset_url = video_url if is_video and video_url else display_url
    if asset_url:
        assets.append(
            {
                "index": 1,
                "kind": "video" if is_video else "image",
                "source_url": asset_url,
                "display_url": display_url or asset_url,
                "ocr_candidate": not is_video,
            }
        )
    return assets



def inspect_post(shortcode: str) -> dict[str, Any]:
    import instaloader
    loader = loader_context()
    try:
        post = instaloader.Post.from_shortcode(loader.context, shortcode)
    except Exception as exc:
        raise RuntimeError(f"Instaloader could not inspect shortcode {shortcode}: {exc}") from exc
    owner = getattr(post, "owner_profile", None)
    if owner is None:
        raise RuntimeError(
            "Instaloader returned a post without owner metadata. "
            "This usually means Instagram rejected anonymous metadata access for this reel."
        )
    username = str(getattr(owner, "username", None) or "unknown")
    owner_id = str(getattr(owner, "userid", None) or username)
    surface = _surface_for_post(post)
    assets = _assets_for_post(post)
    has_multiple_assets = len(assets) > 1
    if surface == "reel":
        media_type = "instagram_reel"
    elif has_multiple_assets:
        media_type = "instagram_carousel"
    else:
        media_type = "instagram_post"
    return {
        "provider": "instagram",
        "external_id": str(post.shortcode),
        "creator": username,
        "creator_external_id": owner_id,
        "creator_display_name": str(getattr(owner, "full_name", None) or username),
        "title": f"Instagram {'Reel' if media_type == 'instagram_reel' else 'Post'} {post.shortcode}",
        "description": str(getattr(post, "caption", None) or ""),
        "published_at": iso(getattr(post, "date_utc", None)),
        "duration_seconds": getattr(post, "video_duration", None) if media_type == "instagram_reel" else None,
        "source_url": f"https://www.instagram.com/{'reel' if surface == 'reel' else 'p'}/{post.shortcode}/",
        "backend_used": "instaloader",
        "surface": surface,
        "media_type": media_type,
        "processing_class": media_type,
        "assets": assets,
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
