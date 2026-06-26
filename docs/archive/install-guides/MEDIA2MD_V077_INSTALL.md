# Media2MD v0.7.7 Upgrade and Live Validation

This release fixes the TikTok sync behavior observed during the v0.7.6 live run. The old implementation applied a fresh per-process timeout to several transports, then repeated the complete transport plan for both a stable-ID target and the handle URL. The visible `SYNC_HEARTBEAT` counter restarted for every subprocess, making a finite but multiplicative retry plan look endless.

## Upgrade an existing project

Download `media2md-v0.7.7-source.zip` to `~/Downloads`, then run:

```bash
(
  set -euo pipefail

  cd "$HOME/instagram-to-md"
  source .venv/bin/activate

  ZIP="$HOME/Downloads/media2md-v0.7.7-source.zip"
  test -f "$ZIP" || { echo "ERROR: missing $ZIP"; exit 1; }

  rm -rf /tmp/media2md-v077
  mkdir -p /tmp/media2md-v077
  unzip -q "$ZIP" -d /tmp/media2md-v077

  test -f /tmp/media2md-v077/install_media2md_v077.py || {
    echo "ERROR: installer missing"
    exit 1
  }

  python /tmp/media2md-v077/install_media2md_v077.py \
    --target "$HOME/instagram-to-md"

  ./bin/media2md version | grep -F "media2md 0.7.7"
)

rc=$?
echo "upgrade_exit_code=$rc"
```

Expected:

```text
MEDIA2MD_V077_INSTALLED
version=0.7.7
media2md 0.7.7
upgrade_exit_code=0
```

The installer preserves `config`, `data`, `logs`, `workspace`, `markdown`, `downloads`, `transcripts`, and the existing TikTok checkpoint.

## Bounded TikTok validation

The following validation processes at most four pages in one invocation. With page size 25, it can add at most 100 catalog items before pausing cleanly.

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

Expected telemetry:

```text
SYNC_RUN_BUDGET ... max_runtime_seconds=1800 max_pages_per_run=4
SYNC_PAGE_BUDGET ... budget_seconds=300 candidates=1|2
SYNC_TRANSPORT_ATTEMPT ... page_budget_remaining_seconds=...
SYNC_WAITING ... range=... candidate=... elapsed_seconds=30
SYNC_ATTEMPT_RESULT ... status=success|failed reason=...
SYNC_PAGE_DONE ...
SYNC_RUN_PROGRESS ...
```

If four pages or 30 minutes are reached before the catalog ends:

```text
SYNC_RUN_PAUSED ... resume_from=... exact=false
```

This is a controlled partial result, not an error. Run the same command again to resume from the saved checkpoint.

### Important behavior changes

- One page has one shared deadline. Fallbacks cannot restart a fresh page timeout.
- Only one recovered stable ID and the handle URL may be attempted.
- The handle path no longer starts a nested ID-fallback transport ladder.
- The last successful transport/auth mode is tried first on the next page.
- `SYNC_HEARTBEAT` was replaced by contextual `SYNC_WAITING`, emitted every 30 seconds by default.
- A whole invocation has a maximum runtime and optional maximum-page limit.
- Ctrl+C still terminates the extractor process group and preserves the checkpoint.

## Instagram regression confirmation

Instagram succeeded in the v0.7.6 live run with 30 completed and zero failed. No Instagram processing behavior is changed in v0.7.7.

Confirm status:

```bash
./bin/media2md creator status --provider instagram --creator career_cleo
```

## Publication status

GitHub Release update/rollback and PyPI/npm/Homebrew publication remain Pending.
