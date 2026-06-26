# Media2MD v0.8.3 install and live validation

v0.8.3 fixes the post-Full-Sync exact-state regression and the next-Full-Sync checkpoint lifecycle. Existing config, data, logs, Markdown, downloads, transcripts, completed media, cursor state, and download transport hints are preserved.

## Install

Download `media2md-v0.8.3-source.zip` to `~/Downloads`, then run:

```bash
(
  set -euo pipefail
  cd "$HOME/instagram-to-md"
  source .venv/bin/activate
  ZIP="$HOME/Downloads/media2md-v0.8.3-source.zip"
  test -f "$ZIP"
  rm -rf /tmp/media2md-v083
  mkdir -p /tmp/media2md-v083
  unzip -q "$ZIP" -d /tmp/media2md-v083
  python /tmp/media2md-v083/install_media2md_v083.py --target "$HOME/instagram-to-md"
  ./bin/media2md version | grep -F "media2md 0.8.3"
)
```

Expected installer markers include:

```text
MEDIA2MD_V083_INSTALLED
version=0.8.3
tiktok_exact_state_repaired=0|1
```

## Validate repaired exact state

```bash
./bin/media2md creator status --provider tiktok --creator startupbell
```

When v0.8.2 only downgraded the flag and did not change the total, expect `EXACT current=true` with the existing `last_full_total`.

## Validate processing does not mutate Catalog

```bash
./bin/media2md creator run @startupbell --provider tiktok --mode batch \
  --batch-size-type tiktok_video=5 --max-batches 1 --max-failures 1
```

Expect `AUTO_SYNC_SKIPPED reason=exact_catalog_available`, followed directly by `BATCH_START`. No Quick Sync JSON should appear.

## Validate a new explicit Full Sync

```bash
export MEDIA2MD_TIKTOK_SYNC_MAX_PAGES_PER_RUN=12
./bin/media2md creator sync @startupbell --provider tiktok --force-full
```

Because the completed checkpoint was removed, expect `SYNC_CURSOR_BOOTSTRAP source=registry` and `SYNC_CURSOR_MODE`. The legacy playlist offset path must not run. Continue until `SYNC_CURSOR_COMPLETE`.
