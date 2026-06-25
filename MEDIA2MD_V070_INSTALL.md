# Media2MD v0.7.0 Installation

## Upgrade Daniel's existing project

```bash
cd ~/instagram-to-md
source .venv/bin/activate

unzip -o ~/Downloads/media2md-v0.7.0-source.zip -d /tmp/media2md-v070
python /tmp/media2md-v070/install_media2md_v070.py \
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
