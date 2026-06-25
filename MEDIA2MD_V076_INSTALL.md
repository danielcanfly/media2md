# Media2MD v0.7.6 Installation and Live Regression Validation

## Why v0.7.6 exists

The v0.7.5 Instagram worker fix was present, but the public `media2md creator run` parser did not expose the documented `--retry-failed` flag, so the live command stopped before reaching the worker. v0.7.6 fixes the public CLI and also restores the proven v0.6.x default cookie path: the worker selects the managed cookie file itself, then falls back to browser cookies. The caller no longer injects a cookie-file argument unless a human explicitly asks for an override.

TikTok v0.7.5 removed proxy environment variables but did not explicitly disable macOS/system proxy resolution inside yt-dlp. v0.7.6 adds `--proxy ""` to the direct strategy, reports enabled macOS proxy classes without exposing endpoints, recovers a stable user ID from the existing checkpoint when possible, and imports already discovered checkpoint items as a non-exact partial catalog.

## Upgrade an existing `~/instagram-to-md` project

Download `media2md-v0.7.6-source.zip` to `~/Downloads`, then paste the complete block:

```bash
(
  set -euo pipefail

  cd "$HOME/instagram-to-md"
  source .venv/bin/activate

  ZIP="$HOME/Downloads/media2md-v0.7.6-source.zip"
  test -f "$ZIP" || { echo "ERROR: missing $ZIP"; exit 1; }

  rm -rf /tmp/media2md-v076
  mkdir -p /tmp/media2md-v076
  unzip -q "$ZIP" -d /tmp/media2md-v076

  test -f /tmp/media2md-v076/install_media2md_v076.py || {
    echo "ERROR: installer missing"
    exit 1
  }

  python /tmp/media2md-v076/install_media2md_v076.py \
    --target "$HOME/instagram-to-md"

  ./bin/media2md version | grep -F "media2md 0.7.6"
)

rc=$?
echo "upgrade_exit_code=$rc"
```

Expected markers:

```text
MEDIA2MD_V076_INSTALLED
version=0.7.6
media2md 0.7.6
upgrade_exit_code=0
```

The installer preserves `config`, `data`, `logs`, `workspace`, `markdown`, `downloads`, `transcripts`, and the TikTok checkpoint. It creates a rollback archive under `~/.cache/media2md/updates/`.

## Verify the public CLI regression is fixed

```bash
./bin/media2md creator run --help | grep -F -- "--retry-failed"
```

This must print the flag instead of failing.

## Instagram: run exactly one Reel first

```bash
./bin/media2md creator run career_cleo --provider instagram --mode batch --batch-size 1 --max-batches 1 --max-failures 1 --retry-failed
```

Required evidence:

```text
COOKIE_SOURCE file=...
STAGE downloading
completed=1
failures=0
```

The default command must not pass a forced `--cookies-file` argument between scripts. The worker must select the managed file itself, as the stable v0.6.x worker did. If the managed file is unavailable, it may fall back to browser cookies.

Do not restore the Instagram batch to 30 until one real Reel completes and a Markdown file exists.

## TikTok: resume item 201 with explicit direct-proxy bypass

```bash
export MEDIA2MD_TIKTOK_SYNC_PAGE_SIZE=25
export MEDIA2MD_TIKTOK_EXTRACT_TIMEOUT_SECONDS=120
./bin/media2md creator sync @startupbell --provider tiktok --force-full
```

Expected new telemetry may include:

```text
SYNC_IDENTITY_RECOVERY provider=tiktok ...
SYNC_PARTIAL_CATALOG_SAVED provider=tiktok known_items=200 exact=false next_start=201
SYNC_NETWORK_CONTEXT ... macos_system_proxy=... direct_strategy_forces_proxy_empty=true
```

The direct strategy uses yt-dlp `--proxy ""`, so it explicitly requests a direct connection even when macOS has HTTP/HTTPS/SOCKS proxy classes enabled.

If exact sync still fails, the error must retain:

```text
partial_catalog_saved=200
retry_from=201
```

The first 200 known items are then usable only with explicit stale-catalog authorization:

```bash
./bin/media2md creator run @startupbell --provider tiktok --mode batch --batch-size-type tiktok_video=20 --max-batches 1 --allow-stale-catalog
```

This processes a known lower-bound catalog. It does not claim the creator total is exact.

## Validate state

```bash
./bin/media2md creator status --provider instagram --creator career_cleo
./bin/media2md creator status --provider tiktok --creator @startupbell
```

Instagram must show real completed items after processing. TikTok may show a non-exact lower-bound total until a Full Sync reaches the final page.

## Deferred items

GitHub Release update/rollback and PyPI/npm/Homebrew publication remain intentionally Pending.
