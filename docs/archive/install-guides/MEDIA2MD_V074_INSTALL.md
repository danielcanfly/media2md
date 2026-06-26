# Media2MD v0.7.4 Installation and Live Regression Validation

## Why the old terminal displayed `[程序完成]`

The previous command ran `set -euo pipefail` inside the interactive shell. When the installer correctly returned non-zero for the version mismatch, `set -e` terminated that shell. The terminal was not running a stuck Media2MD process; it had no shell left to receive Ctrl+C. v0.7.4 runs strict mode inside a child subshell. A failure returns control to the existing prompt.

## Upgrade an existing project

Download `media2md-v0.7.4-source.zip` into `~/Downloads`, then paste the complete block:

```bash
(
  set -euo pipefail
  cd "$HOME/instagram-to-md"
  source .venv/bin/activate
  ZIP="$HOME/Downloads/media2md-v0.7.4-source.zip"
  test -f "$ZIP" || { echo "ERROR: missing $ZIP"; exit 1; }
  rm -rf /tmp/media2md-v074
  mkdir -p /tmp/media2md-v074
  unzip -q "$ZIP" -d /tmp/media2md-v074
  test -f /tmp/media2md-v074/install_media2md_v074.py || { echo "ERROR: installer missing"; exit 1; }
  python /tmp/media2md-v074/install_media2md_v074.py --target "$HOME/instagram-to-md"
  ./bin/media2md version | grep -F "media2md 0.7.4"
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
