# Media2MD v0.8.6 install and backup regression gate

v0.8.6 is a focused production-safety correction. The v0.8.5 live run proved the exact 1,159-item TikTok baseline and macOS duplicate-run lock, but exposed a backup verifier defect for zero-byte files. v0.8.6 fixes that defect and excludes operational lock artifacts from portable state backups.

Do not install while a Media2MD Sync, Batch, manual media process, or OpenClaw Media2MD job is running.

## Upgrade

Place these files in `~/Downloads`:

- `media2md-v0.8.6-source.zip`
- `media2md-v0.8.6-source.zip.sha256`

Then run:

```bash
(
  set -euo pipefail
  cd "$HOME/instagram-to-md"
  source .venv/bin/activate

  ZIP="$HOME/Downloads/media2md-v0.8.6-source.zip"
  SHA_FILE="$ZIP.sha256"
  test -f "$ZIP"
  test -f "$SHA_FILE"

  EXPECTED_SHA="$(awk '{print $1}' "$SHA_FILE")"
  ACTUAL_SHA="$(shasum -a 256 "$ZIP" | awk '{print $1}')"
  echo "source_zip_sha256=$ACTUAL_SHA"
  test "$ACTUAL_SHA" = "$EXPECTED_SHA"

  rm -rf /tmp/media2md-v086
  mkdir -p /tmp/media2md-v086
  unzip -q "$ZIP" -d /tmp/media2md-v086

  python /tmp/media2md-v086/install_media2md_v086.py \
    --target "$HOME/instagram-to-md"

  ./bin/media2md version | grep -F "media2md 0.8.6"
)
```

Required installer markers:

```text
MEDIA2MD_V086_INSTALLED
version=0.8.6
data_preserved=config,data,logs,workspace,markdown,downloads,transcripts
```

## Gate A: exact baseline remains intact

```bash
./bin/media2md creator status \
  --provider tiktok \
  --creator startupbell \
  2>&1 | tee "$HOME/Desktop/media2md-v086-status.log"
```

Required:

```text
TRACKED  1159
EXACT current=true
last_full_total=1159
```

## Gate B: backup and verification regression

```bash
mkdir -p "$HOME/media2md-backups"

./bin/media2md data backup \
  --destination "$HOME/media2md-backups" \
  2>&1 | tee "$HOME/Desktop/media2md-v086-backup.log"

BACKUP_PATH="$(awk -F= '/^path=/{print $2}' "$HOME/Desktop/media2md-v086-backup.log" | tail -1)"
test -n "$BACKUP_PATH"
test -f "$BACKUP_PATH"

./bin/media2md data verify-backup "$BACKUP_PATH" \
  2>&1 | tee "$HOME/Desktop/media2md-v086-backup-verify.log"
```

Required:

```text
MEDIA2MD_BACKUP_CREATED
secrets_included=false
MEDIA2MD_BACKUP_VERIFIED
```

The archive must not contain `.creators.lock`, other `*.lock`/`*.pid` files, partial files, browser secrets, downloaded media, transcripts, Markdown, workspace files, or logs.

## Gate C: one real TikTok item

Run this only after Gate B has printed `MEDIA2MD_BACKUP_VERIFIED`. Gate B takes the exclusive maintenance lock, so a successful Gate B also proves that no old Creator Run test lock is still active at that point.

```bash
./bin/media2md creator run \
  @startupbell \
  --provider tiktok \
  --mode batch \
  --batch-size-type tiktok_video=1 \
  --max-batches 1 \
  --max-failures 1 \
  2>&1 | tee "$HOME/Desktop/media2md-v086-one-item.log"
```

Required:

```text
AUTO_SYNC_SKIPPED provider=tiktok reason=exact_catalog_available
BATCH_START
CREATOR_RUN_COMPLETED
completed=1
failures=0
```

After all three gates pass, the backup regression is closed and the private-production promotion decision can be revisited. Public v1.0.0 remains a separate platform-matrix gate.
