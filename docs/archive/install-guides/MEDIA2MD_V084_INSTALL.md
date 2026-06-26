# Media2MD v0.8.4 install and live validation

v0.8.4 fixes the TikTok exact-catalog rebuild lifecycle. A new explicit Full rebuild is staged in its cursor checkpoint and cannot downgrade the active exact catalog until the rebuild reaches the terminal cursor page. Existing config, data, logs, Markdown, downloads, transcripts, completed media, cursor state, and download hints are preserved.

## Install over v0.8.3

Download `media2md-v0.8.4-source.zip` to `~/Downloads`, then run:

```bash
(
  set -euo pipefail

  cd "$HOME/instagram-to-md"
  source .venv/bin/activate

  ZIP="$HOME/Downloads/media2md-v0.8.4-source.zip"
  test -f "$ZIP" || { echo "ERROR: missing $ZIP"; exit 1; }

  rm -rf /tmp/media2md-v084
  mkdir -p /tmp/media2md-v084
  unzip -q "$ZIP" -d /tmp/media2md-v084

  python /tmp/media2md-v084/install_media2md_v084.py \
    --target "$HOME/instagram-to-md"

  ./bin/media2md version | grep -F "media2md 0.8.4"
)

rc=$?
echo "upgrade_exit_code=$rc"
```

Expected markers include:

```text
MEDIA2MD_V084_INSTALLED
version=0.8.4
tiktok_exact_state_repaired=1
tiktok_cursor_devices_migrated=1
tiktok_exact_rebuild_checkpoints_staged=1
media2md 0.8.4
upgrade_exit_code=0
```

The three TikTok migration counts may be `0` on projects that do not have the corresponding v0.8.3 state.

## Verify the active exact catalog

```bash
./bin/media2md creator status --provider tiktok --creator startupbell
```

For the StartupBell state produced on 2026-06-24, expect:

```text
TRACKED 1159
EXACT current=true
last_full_total=1159
```

## Retry the staged Full rebuild

```bash
export MEDIA2MD_TIKTOK_SYNC_MAX_PAGES_PER_RUN=12
./bin/media2md creator sync @startupbell --provider tiktok --force-full
```

The existing failed checkpoint should resume. While the refresh is incomplete or unavailable, the result must retain the exact baseline and include:

```text
SYNC_CURSOR_MODE ... staged_rebuild=true
SYNC_RUN_PAUSED ... exact=true baseline_preserved=true
```

The JSON payload must include:

```json
{
  "current_total": 1159,
  "current_total_exact": true,
  "baseline_preserved": true,
  "rebuild_in_progress": true,
  "staged_total": 0
}
```

If cursor pages succeed but the page-count limit pauses the run, `staged_total` may increase while `current_total` remains the active exact baseline. Only `SYNC_CURSOR_COMPLETE` may atomically publish the rebuilt catalog and reconcile additions/removals.

## Verify Batch remains usable during a staged rebuild

```bash
./bin/media2md creator run \
  @startupbell \
  --provider tiktok \
  --mode batch \
  --batch-size-type tiktok_video=5 \
  --max-batches 1 \
  --max-failures 1
```

Expect `AUTO_SYNC_SKIPPED reason=exact_catalog_available` followed by `BATCH_START`. A retryable item failure remains in the real remaining queue.
