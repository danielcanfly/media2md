# Media2MD v0.7.2 Installation and Live Regression Validation

v0.7.2 is a corrective release for three issues found in the first v0.7.1 live attempt:

1. The v0.7.1 archive was not present in `~/Downloads`, but the shell continued and silently reinstalled v0.6.7.
2. TikTok full sync could lose the secUid/user ID after the first pages and fail around page 3.
3. Instagram `/reels/` creator URLs were passed to a legacy username-only manager.

## Upgrade an existing project safely

Download **`media2md-v0.7.2-source.zip`** first, then run this block exactly. It is fail-fast: if the archive is missing or the version is wrong, later commands do not run.

```bash
set -euo pipefail

cd "$HOME/instagram-to-md"
source .venv/bin/activate

ZIP="$HOME/Downloads/media2md-v0.7.2-source.zip"
test -f "$ZIP" || {
  echo "ERROR: missing $ZIP"
  echo "Download media2md-v0.7.2-source.zip before continuing."
  exit 1
}

rm -rf /tmp/media2md-v072
mkdir -p /tmp/media2md-v072
unzip -q "$ZIP" -d /tmp/media2md-v072

test -f /tmp/media2md-v072/install_media2md_v072.py || {
  echo "ERROR: archive does not contain install_media2md_v072.py"
  exit 1
}

python /tmp/media2md-v072/install_media2md_v072.py \
  --target "$HOME/instagram-to-md"

./bin/media2md version | grep -F "media2md 0.7.2"
```

The installer performs the editable package installation itself, creates `TARGET/.venv` when absent, and verifies the installed CLI version. Do not run a separate `pip install -e` command unless the installer reports an error.

The following directories are preserved:

```text
config/
data/
logs/
workspace/
markdown/
downloads/
transcripts/
```

A rollback archive is created under:

```text
~/.cache/media2md/updates/rollback-before-v072-*.zip
```

## New installation from a local wheel

PyPI publication remains pending. Install the local wheel instead:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install \
  "$HOME/Downloads/media2md-0.7.2-py3-none-any.whl[all]"
media2md runtime install
media2md init \
  --language zh-TW \
  --markdown-language zh-TW \
  --timezone Asia/Tokyo \
  --non-interactive
media2md version
```

## Authentication

```bash
./bin/media2md auth profiles youtube --browser chrome
./bin/media2md auth connect youtube --browser chrome --profile Default
./bin/media2md auth verify youtube
```

Use the same profile/connect/verify flow for Instagram and TikTok. Browser-renewed cookies are re-read automatically. Password, 2FA, CAPTCHA and platform challenges still require the user.

## Typed batch policies

These commands only work after `./bin/media2md version` reports `0.7.2`:

```bash
./bin/media2md creator policy set \
  @TheProductFolks \
  --provider youtube \
  --batch-size-type youtube_short=30 \
  --batch-size-type youtube_video=5 \
  --batch-size-type youtube_long=1

./bin/media2md creator policy set \
  @startupbell \
  --provider tiktok \
  --batch-size-type tiktok_video=100

./bin/media2md creator policy set \
  career_cleo \
  --provider instagram \
  --batch-size-type instagram_reel=30
```

## Live regression sequence

### 1. YouTube Videos + Shorts

```bash
./bin/media2md creator add \
  "https://www.youtube.com/@TheProductFolks/videos" \
  --provider youtube

./bin/media2md creator sync \
  @TheProductFolks \
  --provider youtube \
  --force-full

./bin/media2md creator status \
  --provider youtube \
  --creator @TheProductFolks
```

Expected: separate `videos` and `shorts` totals, exact flags after full sync, and a combined de-duplicated total.

### 2. Single YouTube Short

```bash
./bin/media2md media add \
  "https://www.youtube.com/shorts/0jttCFj5ZWM" \
  --process-now
```

Expected output path includes `markdown/youtube/<creator>/shorts/`.

### 3. Long YouTube video

```bash
./bin/media2md media add \
  "https://www.youtube.com/watch?v=J92OMF6HUaM" \
  --process-now
```

Expected: long-video classification, chunk checkpointing when duration exceeds the configured threshold, and a merged Markdown result.

### 4. TikTok full pagination

```bash
./bin/media2md creator add \
  "https://www.tiktok.com/@startupbell" \
  --provider tiktok
```

Expected: page 2 and later use a stable `tiktokuser:<secUid/user_id>` catalog source learned from the first successful page. The sync must not fail merely because the handle endpoint stops exposing a secondary user ID.

### 5. Instagram creator URL

```bash
./bin/media2md creator add \
  "https://www.instagram.com/career_cleo/reels/" \
  --provider instagram
```

Expected: the URL is normalized to `career_cleo` before entering the legacy Instagram manager.

## OpenClaw

```bash
./bin/media2md openclaw install
./bin/media2md openclaw status
./bin/media2md scheduler tick --non-interactive --output ndjson
```

Items 11 and 12 in the strict acceptance table remain intentionally pending.
