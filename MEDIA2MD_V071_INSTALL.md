# Media2MD v0.7.1 Installation

## Upgrade Daniel's existing project

```bash
cd ~/instagram-to-md
source .venv/bin/activate

rm -rf /tmp/media2md-v071
mkdir -p /tmp/media2md-v071
unzip -o ~/Downloads/media2md-v0.7.1-source.zip -d /tmp/media2md-v071
python /tmp/media2md-v071/install_media2md_v071.py \
  --target ~/instagram-to-md

python -m pip install -U -e \
  "$HOME/instagram-to-md[all]"

./bin/media2md version
./bin/media2md doctor all
```

The installer preserves `config/`, `data/`, `logs/`, `workspace/`, `markdown/`, `downloads/`, and `transcripts/`. A rollback archive is created under `~/.cache/media2md/updates/`.

## New installation from PyPI or wheel

Base package:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install media2md
media2md runtime install
media2md init --language zh-TW --markdown-language zh-TW --timezone Asia/Tokyo --non-interactive
```

Optional modules:

```bash
python -m pip install "media2md[instagram]"
python -m pip install "media2md[youtube,mlx]"
python -m pip install "media2md[tiktok]"
python -m pip install "media2md[all]"
```

## Authentication

```bash
media2md auth profiles youtube --browser chrome
media2md auth connect youtube --browser chrome --profile Default
media2md auth verify youtube
```

Use the same flow for `instagram` and `tiktok`.

Media2MD can refresh cookies already renewed by the selected browser profile without opening the browser. It cannot type passwords or bypass 2FA, CAPTCHA, or platform challenges. When those occur, the command returns `required_action` and waits for the user.

## OpenClaw

```bash
media2md openclaw install
media2md openclaw status
media2md scheduler tick --non-interactive --output ndjson
```

## v0.7.1 typed YouTube catalog verification

```bash
./bin/media2md creator add https://www.youtube.com/@TheProductFolks/videos --provider youtube
./bin/media2md creator sync @TheProductFolks --provider youtube --force-full
./bin/media2md creator policy set @TheProductFolks --provider youtube \
  --batch-size-type youtube_short=30 \
  --batch-size-type youtube_video=5 \
  --batch-size-type youtube_long=1
./bin/media2md creator status --provider youtube --creator @TheProductFolks
```

`current_total` is a snapshot. A full sync produces exact per-type totals; a quick sync discovers new items but marks totals non-exact until the next full sync.

## Requested live validation fixtures

```bash
# YouTube Videos + Shorts catalog
./bin/media2md creator add https://www.youtube.com/@TheProductFolks/videos --provider youtube
./bin/media2md creator sync @TheProductFolks --provider youtube --force-full
./bin/media2md creator status --provider youtube --creator @TheProductFolks

# One Short
./bin/media2md media add https://www.youtube.com/shorts/0jttCFj5ZWM --process-now

# Long YouTube video
./bin/media2md media add https://www.youtube.com/watch?v=J92OMF6HUaM --process-now

# TikTok full catalog and batch policy
./bin/media2md creator add https://www.tiktok.com/@startupbell --provider tiktok
./bin/media2md creator policy set @startupbell --provider tiktok --batch-size-type tiktok_video=100

# Instagram full Reels catalog and batch policy
./bin/media2md creator add https://www.instagram.com/career_cleo/reels/ --provider instagram
./bin/media2md creator policy set career_cleo --provider instagram --batch-size-type instagram_reel=30
```

Run platform authentication verification and `doctor` before starting the large processing runs. Items 11 and 12 are intentionally pending.
