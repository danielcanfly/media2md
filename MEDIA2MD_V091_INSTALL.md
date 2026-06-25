# Media2MD v0.9.1 installation and TikTok final closure

v0.9.1 is the targeted TikTok convergence candidate built from the signed
v0.8.6 one-shot evidence and v0.9.0 closure evidence. It preserves every gate
that already passed and fixes the final three TikTok closure failures together.

## Fixed in this release

1. TikTok HTTP 200 on the authenticated `/setting` endpoint is treated as an
   authenticated session even when ordinary application JavaScript contains
   generic captcha or challenge strings.
2. TikTok `media inspect` still tries the bounded live transport/authentication
   cascade first. If every live route is temporarily unavailable, it can return
   verified local Registry/processing metadata or direct no-proxy oEmbed metadata,
   and explicitly reports the fallback source.
3. TikTok Doctor reuses the production metadata/download paths. If a transient
   live probe fails but a recent real completed Markdown artifact proves the
   pipeline, Doctor returns a transparent degraded-ready state rather than a
   false red or a false fully-ready result.
4. All v0.9.0 live-passing behavior remains unchanged: Instagram auth, Shorts-only
   YouTube catalogs, controlled Short upload/delete, Exact TikTok 1,159 staging,
   OpenClaw no-delivery recovery, and consistent backups.

## Install

Run installation only while no Media2MD Sync, Batch, direct media process,
backup, or OpenClaw Media2MD job is active.

```bash
(
  set -euo pipefail

  cd "$HOME/instagram-to-md"
  source .venv/bin/activate

  ZIP="$HOME/Downloads/media2md-v0.9.1-source.zip"
  SHA_FILE="$ZIP.sha256"

  test -f "$ZIP"
  test -f "$SHA_FILE"

  EXPECTED_SHA="$(awk '{print $1}' "$SHA_FILE")"
  ACTUAL_SHA="$(shasum -a 256 "$ZIP" | awk '{print $1}')"

  echo "expected_sha256=$EXPECTED_SHA"
  echo "actual_sha256=$ACTUAL_SHA"
  test "$EXPECTED_SHA" = "$ACTUAL_SHA"

  rm -rf /tmp/media2md-v091
  mkdir -p /tmp/media2md-v091
  unzip -q "$ZIP" -d /tmp/media2md-v091

  python /tmp/media2md-v091/install_media2md_v091.py \
    --target "$HOME/instagram-to-md"

  ./bin/media2md version | grep -F "media2md 0.9.1"
  echo "MEDIA2MD_V091_INSTALL_GATE_PASSED"
)
```

Expected installer markers:

```text
MEDIA2MD_V091_INSTALLED
version=0.9.1
data_preserved=config,data,logs,workspace,markdown,downloads,transcripts
MEDIA2MD_V091_INSTALL_GATE_PASSED
```

## Targeted final closure

After installation, run `media2md-v091-tiktok-closure-acceptance.zip`. It reruns
only:

- three-platform final auth status, including TikTok `/setting`;
- TikTok metadata live cascade plus explicit fallback source;
- three-platform Doctor with truthful TikTok degraded semantics;
- StartupBell Exact 1,159 final status;
- consistent backup creation and verification.

Expensive gates already signed in earlier evidence are carried forward by SHA-256
and are not repeated.
