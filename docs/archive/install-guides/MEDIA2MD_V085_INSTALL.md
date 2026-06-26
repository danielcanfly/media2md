# Media2MD v0.8.5 install and private-production gate

v0.8.5 keeps the live-passing v0.8.4 TikTok staged-rebuild behavior and adds production safety around duplicate operations and state backup.

Do not install while a Media2MD Sync, Batch, manual media process, or OpenClaw Media2MD job is running.

## Upgrade

Place `media2md-v0.8.5-source.zip` in `~/Downloads`, then run the whole block:

```bash
(
  set -euo pipefail

  cd "$HOME/instagram-to-md"
  source .venv/bin/activate

  ZIP="$HOME/Downloads/media2md-v0.8.5-source.zip"
  SHA_FILE="$ZIP.sha256"

  test -f "$ZIP"
  test -f "$SHA_FILE"
  EXPECTED_SHA="$(awk '{print $1}' "$SHA_FILE")"
  ACTUAL_SHA="$(shasum -a 256 "$ZIP" | awk '{print $1}')"
  echo "source_zip_sha256=$ACTUAL_SHA"
  test "$ACTUAL_SHA" = "$EXPECTED_SHA"

  rm -rf /tmp/media2md-v085
  mkdir -p /tmp/media2md-v085
  unzip -q "$ZIP" -d /tmp/media2md-v085

  python /tmp/media2md-v085/install_media2md_v085.py \
    --target "$HOME/instagram-to-md"

  ./bin/media2md version | grep -F "media2md 0.8.5"
)
```

Expected installer markers:

```text
MEDIA2MD_V085_INSTALLED
version=0.8.5
data_preserved=config,data,logs,workspace,markdown,downloads,transcripts
```

## Gate A: exact baseline survives upgrade

```bash
cd ~/instagram-to-md
source .venv/bin/activate

./bin/media2md creator status \
  --provider tiktok \
  --creator startupbell
```

Required:

```text
TRACKED  1159
EXACT current=true
last_full_total=1159
```

## Gate B: create and verify a consistent state backup

```bash
cd ~/instagram-to-md
source .venv/bin/activate

./bin/media2md data backup \
  --destination "$HOME/media2md-backups" \
  | tee "$HOME/Desktop/media2md-v085-backup.log"

BACKUP_PATH="$(awk -F= '/^path=/{print $2}' "$HOME/Desktop/media2md-v085-backup.log" | tail -1)"
test -n "$BACKUP_PATH"

./bin/media2md data verify-backup "$BACKUP_PATH"
```

Required:

```text
MEDIA2MD_BACKUP_CREATED
secrets_included=false
MEDIA2MD_BACKUP_VERIFIED
```

The archive contains databases, config, Catalog checkpoints, and state hints. It deliberately does not contain cookies, browser secrets, downloaded media, transcripts, Markdown, workspace files, or logs.

## Gate C: deterministic duplicate-run rejection

This gate holds the exact Creator Run lock without downloading media, then proves a second invocation is rejected before `BATCH_START`.

```bash
cd ~/instagram-to-md
source .venv/bin/activate

python - <<'PY' &
import sys, time
from pathlib import Path
root = Path.home() / "instagram-to-md"
sys.path.insert(0, str(root / "scripts"))
from media2md_runtime import operation_lock
with operation_lock(
    "creator-run",
    "tiktok-startupbell",
    metadata={"provider": "tiktok", "creator": "startupbell", "gate": "v085"},
):
    print("V085_TEST_LOCK_HELD", flush=True)
    time.sleep(15)
PY
LOCK_PID=$!
sleep 2

set +e
./bin/media2md creator run \
  @startupbell \
  --provider tiktok \
  --mode batch \
  --batch-size-type tiktok_video=1 \
  --max-batches 1 \
  --max-failures 1 \
  2>&1 | tee "$HOME/Desktop/media2md-v085-lock-gate.log"
RUN_RC=${PIPESTATUS[0]}
set -e

wait "$LOCK_PID"
echo "duplicate_run_exit_code=$RUN_RC"
test "$RUN_RC" -eq 2
grep -F "operation already running" "$HOME/Desktop/media2md-v085-lock-gate.log"
! grep -F "BATCH_START" "$HOME/Desktop/media2md-v085-lock-gate.log"
```

## Gate D: one real item after upgrade

```bash
cd ~/instagram-to-md
source .venv/bin/activate

./bin/media2md creator run \
  @startupbell \
  --provider tiktok \
  --mode batch \
  --batch-size-type tiktok_video=1 \
  --max-batches 1 \
  --max-failures 1 \
  2>&1 | tee "$HOME/Desktop/media2md-v085-one-item.log"
```

Required:

```text
AUTO_SYNC_SKIPPED provider=tiktok reason=exact_catalog_available
BATCH_START
CREATOR_RUN_COMPLETED
completed=1
failures=0
```

After all four gates pass, v0.8.5 qualifies for promotion to v0.9.0 private production. It is not yet the public v1.0.0 release.
