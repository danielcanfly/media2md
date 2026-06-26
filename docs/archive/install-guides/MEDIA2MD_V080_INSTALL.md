# Media2MD v0.8.0 install and live validation

v0.8.0 replaces resumed TikTok `--playlist-start` deep paging with a persistent cursor backend. Existing config, data, logs, Markdown, downloads, transcripts, and provider checkpoints are preserved.

## Upgrade

Download `media2md-v0.8.0-source.zip` to `~/Downloads`, then run:

```bash
(
  set -euo pipefail
  cd "$HOME/instagram-to-md"
  source .venv/bin/activate
  ZIP="$HOME/Downloads/media2md-v0.8.0-source.zip"
  test -f "$ZIP"
  rm -rf /tmp/media2md-v080
  mkdir -p /tmp/media2md-v080
  unzip -q "$ZIP" -d /tmp/media2md-v080
  python /tmp/media2md-v080/install_media2md_v080.py --target "$HOME/instagram-to-md"
  ./bin/media2md version | grep -F "media2md 0.8.0"
)
rc=$?
echo "upgrade_exit_code=$rc"
```

Expected markers:

```text
MEDIA2MD_V080_INSTALLED
version=0.8.0
media2md 0.8.0
upgrade_exit_code=0
```

## Resume StartupBell

```bash
cd "$HOME/instagram-to-md"
source .venv/bin/activate
export MEDIA2MD_TIKTOK_CURSOR_BACKEND=1
export MEDIA2MD_TIKTOK_CURSOR_PAGE_SIZE=15
export MEDIA2MD_TIKTOK_SYNC_MAX_RUNTIME_SECONDS=1800
export MEDIA2MD_TIKTOK_SYNC_MAX_PAGES_PER_RUN=4
export MEDIA2MD_SYNC_HEARTBEAT_SECONDS=30
./bin/media2md creator sync @startupbell --provider tiktok --force-full
```

Expected first-run migration markers:

```text
SYNC_CURSOR_RECOVERED provider=tiktok source=oldest_known_item
SYNC_CURSOR_MODE provider=tiktok backend=native-curl
```

Each successful API page prints:

```text
SYNC_CURSOR_PAGE_DONE ... cursor_before=... cursor_after=... has_more=true
```

The final page prints:

```text
SYNC_CURSOR_COMPLETE provider=tiktok current_total=... exact=true
```

If TikTok rejects or times out the native cursor request, the command preserves all known items and prints:

```text
SYNC_RUN_PAUSED provider=tiktok reason=cursor_request_failed
```

## Temporary rollback switch

The bounded v0.7.x extractor path remains available for diagnosis only:

```bash
export MEDIA2MD_TIKTOK_CURSOR_BACKEND=0
```

Do not use that switch for normal deep-catalog continuation because it replays earlier TikTok playlist pages.
