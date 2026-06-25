#!/bin/sh
set -eu
EXTRAS="${MEDIA2MD_EXTRAS:-all}"
python3 -m venv .venv
. .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install ".[${EXTRAS}]"
media2md runtime install
echo "Installed. Run: . .venv/bin/activate && media2md init"
