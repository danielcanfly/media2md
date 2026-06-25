# Media2MD v0.8.1 install and live validation

v0.8.1 keeps the v0.8.0 cursor Catalog engine and fixes TikTok Batch transport, partial-catalog auto-sync overhead, cursor run-delta reporting, and early-stop summaries. Existing config, data, logs, Markdown, downloads, transcripts, and checkpoints are preserved.

## Upgrade

Download `media2md-v0.8.1-source.zip` to `~/Downloads`, then run:

```bash
(
  set -euo pipefail
  cd "$HOME/instagram-to-md"
  source .venv/bin/activate
  ZIP="$HOME/Downloads/media2md-v0.8.1-source.zip"
  test -f "$ZIP"
  rm -rf /tmp/media2md-v081
  mkdir -p /tmp/media2md-v081
  unzip -q "$ZIP" -d /tmp/media2md-v081
  python /tmp/media2md-v081/install_media2md_v081.py --target "$HOME/instagram-to-md"
  ./bin/media2md version | grep -F "media2md 0.8.1"
)
rc=$?
echo "upgrade_exit_code=$rc"
```

Expected markers:

```text
MEDIA2MD_V081_INSTALLED
version=0.8.1
media2md 0.8.1
upgrade_exit_code=0
```

## Continue the bounded cursor Full Sync

```bash
cd "$HOME/instagram-to-md"
source .venv/bin/activate
export MEDIA2MD_TIKTOK_CURSOR_BACKEND=1
export MEDIA2MD_TIKTOK_CURSOR_PAGE_SIZE=15
export MEDIA2MD_TIKTOK_SYNC_MAX_RUNTIME_SECONDS=1800
export MEDIA2MD_TIKTOK_SYNC_MAX_PAGES_PER_RUN=4
./bin/media2md creator sync @startupbell --provider tiktok --force-full
```

A 60-item run must report the command-start snapshot, for example:

```text
previous_current_total=655
current_total=715
new_since_last_sync=60
```

Every cursor attempt must have a corresponding result, including a failed anonymous attempt before cookie fallback.

## Validate a five-item TikTok Batch

While the Full Sync remains partial, `creator run` must skip the old profile Quick Sync:

```bash
export MEDIA2MD_TIKTOK_DOWNLOAD_ITEM_BUDGET_SECONDS=300
export MEDIA2MD_TIKTOK_DOWNLOAD_ATTEMPT_TIMEOUT_SECONDS=120
./bin/media2md creator run @startupbell --provider tiktok --mode batch \
  --batch-size-type tiktok_video=5 --max-batches 1 --max-failures 1
```

Expected markers:

```text
AUTO_SYNC_SKIPPED provider=tiktok reason=full_catalog_in_progress
TIKTOK_DOWNLOAD_ATTEMPT ... strategy=direct-plain
TIKTOK_DOWNLOAD_ATTEMPT_RESULT ... status=success|failed
CREATOR_RUN_COMPLETED ... processed=... completed=... failures=... remaining=...
```

The first failed transport does not count as an item failure. An item fails only after the bounded transport cascade is exhausted.

## Completion criteria

Continue Full Sync until:

```text
SYNC_CURSOR_COMPLETE ... exact=true
```

Then verify:

```bash
./bin/media2md creator status --provider tiktok --creator startupbell
```

The final status must show `EXACT current=true` and a non-empty last Full exact total/time.
