# Media2MD v0.8.2 install and live validation

v0.8.2 removes the duplicate public Creator Run pre-sync implementation. It preserves existing config, data, logs, Markdown, downloads, transcripts, TikTok cursor checkpoint, completed media state, and download transport hints.

## Install

Download `media2md-v0.8.2-source.zip` to `~/Downloads`, then run:

```bash
(
  set -euo pipefail
  cd "$HOME/instagram-to-md"
  source .venv/bin/activate
  ZIP="$HOME/Downloads/media2md-v0.8.2-source.zip"
  test -f "$ZIP" || { echo "ERROR: missing $ZIP"; exit 1; }
  rm -rf /tmp/media2md-v082
  mkdir -p /tmp/media2md-v082
  unzip -q "$ZIP" -d /tmp/media2md-v082
  python /tmp/media2md-v082/install_media2md_v082.py --target "$HOME/instagram-to-md"
  ./bin/media2md version | grep -F "media2md 0.8.2"
)
rc=$?
echo "upgrade_exit_code=$rc"
```

Expected:

```text
MEDIA2MD_V082_INSTALLED
version=0.8.2
media2md 0.8.2
upgrade_exit_code=0
```

## Public CLI regression rerun

Run a five-item Batch while the StartupBell cursor Full Sync remains partial:

```bash
./bin/media2md creator run \
  @startupbell \
  --provider tiktok \
  --mode batch \
  --batch-size-type tiktok_video=5 \
  --max-batches 1 \
  --max-failures 1
```

The first relevant event must be:

```text
AUTO_SYNC_SKIPPED provider=tiktok reason=full_catalog_in_progress using_cached_catalog=true
```

Before `BATCH_START`, the command must not emit `SYNC_NETWORK_CONTEXT`, `SYNC_TRANSPORT_ATTEMPT`, or a JSON summary with `sync_mode=quick`. TikTok item download attempts remain visible and bounded.

Continue the exact Catalog independently with:

```bash
./bin/media2md creator sync @startupbell --provider tiktok --force-full
```
