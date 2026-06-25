#!/usr/bin/env python3
from __future__ import annotations

import inspect
import os
from datetime import datetime, timezone

import scan_gallery_impl as implementation


_original_run_gallery_dl = implementation.run_gallery_dl


def _parse_published_at(value):
    if not value:
        return datetime.min.replace(tzinfo=timezone.utc)

    text = str(value).strip()

    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return datetime.min.replace(tzinfo=timezone.utc)

    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)

    return parsed.astimezone(timezone.utc)


def _latest_first_run_gallery_dl(*args, **kwargs):
    signature = inspect.signature(
        _original_run_gallery_dl
    )

    bound = signature.bind_partial(
        *args,
        **kwargs,
    )

    requested_limit = int(
        bound.arguments.get(
            "scan_limit",
            50,
        )
    )

    configured_window = int(
        os.environ.get(
            "INSTAGRAM_DISCOVERY_WINDOW",
            "100",
        )
    )

    fetch_limit = min(
        500,
        max(
            requested_limit,
            configured_window,
            requested_limit * 5,
        ),
    )

    bound.arguments["scan_limit"] = fetch_limit

    reels = _original_run_gallery_dl(
        *bound.args,
        **bound.kwargs,
    )

    deduplicated = {}

    for reel in reels:
        shortcode = reel.get("shortcode")

        if not shortcode:
            continue

        existing = deduplicated.get(
            shortcode
        )

        if existing is None:
            deduplicated[shortcode] = reel
            continue

        if _parse_published_at(
            reel.get("published_at")
        ) > _parse_published_at(
            existing.get("published_at")
        ):
            deduplicated[shortcode] = reel

    ordered = sorted(
        deduplicated.values(),
        key=lambda reel: (
            _parse_published_at(
                reel.get("published_at")
            ),
            str(reel.get("shortcode", "")),
        ),
        reverse=True,
    )

    return ordered[:requested_limit]


implementation.run_gallery_dl = (
    _latest_first_run_gallery_dl
)


if __name__ == "__main__":
    raise SystemExit(
        implementation.main()
    )
