# Media2MD v0.7.8 Install and Live Verification

## Upgrade

Download `media2md-v0.7.8-source.zip` to `~/Downloads`, then run:

```bash
(
  set -euo pipefail
  cd "$HOME/instagram-to-md"
  source .venv/bin/activate
  ZIP="$HOME/Downloads/media2md-v0.7.8-source.zip"
  test -f "$ZIP" || { echo "ERROR: missing $ZIP"; exit 1; }
  rm -rf /tmp/media2md-v078
  mkdir -p /tmp/media2md-v078
  unzip -q "$ZIP" -d /tmp/media2md-v078
  python /tmp/media2md-v078/install_media2md_v078.py --target "$HOME/instagram-to-md"
  ./bin/media2md version | grep -F "media2md 0.7.8"
)
rc=$?
echo "upgrade_exit_code=$rc"
```

## TikTok live rerun

The existing checkpoint is preserved. Resume with:

```bash
cd "$HOME/instagram-to-md"
source .venv/bin/activate
export MEDIA2MD_TIKTOK_SYNC_PAGE_SIZE=25
export MEDIA2MD_TIKTOK_PAGE_BUDGET_SECONDS=300
export MEDIA2MD_TIKTOK_SYNC_MAX_RUNTIME_SECONDS=1800
export MEDIA2MD_TIKTOK_SYNC_MAX_PAGES_PER_RUN=4
export MEDIA2MD_SYNC_HEARTBEAT_SECONDS=30
./bin/media2md creator sync @startupbell --provider tiktok --force-full
```

When a stable-ID extraction succeeds, expected evidence is:

```text
SYNC_ATTEMPT_RESULT ... status=success
SYNC_STABLE_ID_HANDLE_REUSED provider=tiktok handle=startupbell ... second_profile_fetch=false
SYNC_PAGE_DONE ...
SYNC_RUN_PROGRESS ...
```

There must not be a second handle-profile extraction for the same page.

If the page deadline really expires, expected behavior is:

```text
SYNC_PARTIAL_CATALOG_PRESERVED ... retry_from=...
SYNC_RUN_PAUSED provider=tiktok reason=page_budget_exhausted ... resume_from=...
```

The command must return to the shell without a final `ERROR`, and the next run must resume from the same item.
