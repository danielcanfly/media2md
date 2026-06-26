# Media2MD v0.7.5 Installation and Live Regression Validation

## Why the old terminal displayed `[程序完成]`

The previous command ran `set -euo pipefail` inside the interactive shell. When the installer correctly returned non-zero for the version mismatch, `set -e` terminated that shell. The terminal was not running a stuck Media2MD process; it had no shell left to receive Ctrl+C. v0.7.5 runs strict mode inside a child subshell. A failure returns control to the existing prompt.

## Upgrade an existing project

Download `media2md-v0.7.5-source.zip` into `~/Downloads`, then paste the complete block:

```bash
(
  set -euo pipefail
  cd "$HOME/instagram-to-md"
  source .venv/bin/activate
  ZIP="$HOME/Downloads/media2md-v0.7.5-source.zip"
  test -f "$ZIP" || { echo "ERROR: missing $ZIP"; exit 1; }
  rm -rf /tmp/media2md-v075
  mkdir -p /tmp/media2md-v075
  unzip -q "$ZIP" -d /tmp/media2md-v075
  test -f /tmp/media2md-v075/install_media2md_v075.py || { echo "ERROR: installer missing"; exit 1; }
  python /tmp/media2md-v075/install_media2md_v075.py --target "$HOME/instagram-to-md"
  ./bin/media2md version | grep -F "media2md 0.7.5"
)
rc=$?
echo "upgrade_exit_code=$rc"
```

Do not run `set -euo pipefail` by itself in an interactive terminal.

## Paste-safe live commands

Use one-line commands to avoid leaving the shell at the `>` continuation prompt:

```bash
./bin/media2md creator sync @startupbell --provider tiktok --force-full
./bin/media2md creator run career_cleo --provider instagram --mode batch --max-batches 1
./bin/media2md creator status --provider youtube --creator @TheProductFolks
```

TikTok must print a `SYNC_HEARTBEAT` at least every 10 seconds while an extractor is quiet. Ctrl+C must return code 130 and retain the page-3 checkpoint.

Instagram progress must print `completed=` and `failed=`. Failed batches must print `ITEM_FAILED`, `report=`, `engine_log=`, and `required_action=inspect_instagram_failure_report`. The default max-failure threshold is 10, so a systemic failure must not burn through all 30 items.

## v0.7.5 live regression retest

The Instagram failure was a caller/worker CLI contract mismatch, not a batch-size or rate-limit failure. During installation, rows whose stored error contains the obsolete `--cookies-file` parser rejection are automatically returned to `pending` with their attempt counter reset. Unrelated failed rows are not modified. The printed count may be zero when the old caller left those items in `pending` without writing the parser error into SQLite.

Run a one-item Instagram validation first:

```bash
./bin/media2md creator run career_cleo --provider instagram --mode batch --max-batches 1 --max-failures 1 --retry-failed
```

A healthy item must print `COOKIE_SOURCE`, enter `STAGE downloading`, and must not print `unrecognized arguments: --cookies-file`. After one success, restore the desired Reel batch size.

TikTok catalog page size and processing batch size are separate. For a conservative catalog retest:

```bash
export MEDIA2MD_TIKTOK_SYNC_PAGE_SIZE=25
export MEDIA2MD_TIKTOK_EXTRACT_TIMEOUT_SECONDS=120
./bin/media2md creator sync @startupbell --provider tiktok --force-full
```

The transport plan must report `strategy_count` no greater than 4. Repeated TLS failures must print `SYNC_CIRCUIT_BREAKER`, skip the remaining impersonation strategies, and attempt `direct-plain`. Proxy variable names may be shown, but proxy URLs or credentials must never be printed.
