# Media2MD v0.7.3 Installation and Live Regression Validation

v0.7.3 addresses the issues found in the v0.7.2 live validation:

- TikTok page 3 failed with curl error 35 / TLS errors.
- The TikTok sync process could remain alive after the error and resist Ctrl+C.
- Instagram completed a 30-item batch without a final completion summary.
- YouTube batch output did not identify the selected media IDs.
- Creator status truncated typed batch limits.
- Quick Sync replaced the visible exactness flag without preserving the last exact Full Sync snapshot.

## Safe in-place upgrade

Download `media2md-v0.7.3-source.zip`, then run:

```bash
set -euo pipefail

cd "$HOME/instagram-to-md"
source .venv/bin/activate

ZIP="$HOME/Downloads/media2md-v0.7.3-source.zip"
test -f "$ZIP" || {
  echo "ERROR: missing $ZIP"
  echo "請先下載 media2md-v0.7.3-source.zip"
  exit 1
}

rm -rf /tmp/media2md-v073
mkdir -p /tmp/media2md-v073
unzip -q "$ZIP" -d /tmp/media2md-v073

test -f /tmp/media2md-v073/install_media2md_v073.py || {
  echo "ERROR: installer missing from ZIP"
  exit 1
}

python /tmp/media2md-v073/install_media2md_v073.py \
  --target "$HOME/instagram-to-md"

./bin/media2md version | grep -F "media2md 0.7.3"
```

The installer preserves `config`, `data`, `logs`, `workspace`, `markdown`, `downloads`, and `transcripts`, and creates a rollback archive under `~/.cache/media2md/updates/`.

## Re-run the live validation

### YouTube status and batch observability

```bash
./bin/media2md creator status \
  --provider youtube \
  --creator @TheProductFolks

./bin/media2md creator run \
  @TheProductFolks \
  --provider youtube \
  --mode batch \
  --max-batches 1
```

Expected:

- `BATCH_LIMITS` shows complete names and values.
- `EXACT` shows both current exactness and the last Full Sync snapshot.
- `BATCH_START` includes `selected_media_ids=[...]`.

### TikTok resume from the existing checkpoint

Do not delete `data/provider_catalog_checkpoints/tiktok-startupbell.json`.

```bash
./bin/media2md creator sync \
  @startupbell \
  --provider tiktok \
  --force-full
```

Expected:

- Resume starts at page 3 / range 201-300.
- TLS failures produce `SYNC_RETRY` and `SYNC_TRANSPORT_ATTEMPT` lines.
- The system can fall back to another available transport.
- If every strategy fails, the command exits to the shell with code 2.
- Pressing Ctrl+C exits with code 130 and preserves the checkpoint.

### Instagram completion and exact total

```bash
./bin/media2md creator run \
  career_cleo \
  --provider instagram \
  --mode batch \
  --max-batches 1

./bin/media2md creator status \
  --provider instagram \
  --creator career_cleo
```

Expected:

- Final line starts with `CREATOR_RUN_COMPLETED provider=instagram`.
- It includes `processed`, `completed`, `failures`, and `remaining`.
- Status shows the imported catalog total and last exact Full Sync snapshot when the Instagram catalog is exact.

Items 11 and 12 remain explicitly Pending.
