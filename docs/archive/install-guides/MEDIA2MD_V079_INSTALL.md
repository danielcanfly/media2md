# Media2MD v0.7.9 Install and Live Verification

## Upgrade

Download `media2md-v0.7.9-source.zip` to `~/Downloads`, then run:

```bash
(
  set -euo pipefail
  cd "$HOME/instagram-to-md"
  source .venv/bin/activate
  ZIP="$HOME/Downloads/media2md-v0.7.9-source.zip"
  test -f "$ZIP" || { echo "ERROR: missing $ZIP"; exit 1; }
  rm -rf /tmp/media2md-v079
  mkdir -p /tmp/media2md-v079
  unzip -q "$ZIP" -d /tmp/media2md-v079
  python /tmp/media2md-v079/install_media2md_v079.py --target "$HOME/instagram-to-md"
  ./bin/media2md version | grep -F "media2md 0.7.9"
)
rc=$?
echo "upgrade_exit_code=$rc"
```

## TikTok live rerun

The existing 475-item checkpoint is preserved. Resume with:

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

Expected early evidence:

```text
SYNC_TRANSPORT_HINT_LOADED provider=tiktok strategy=... authenticated=... source=checkpoint
```

or, for an older checkpoint without a saved hint while macOS proxies are enabled:

```text
SYNC_TRANSPORT_HINT_SELECTED provider=tiktok strategy=direct-plain authenticated=false reason=macos_system_proxy
```

After a successful page:

```text
SYNC_TRANSPORT_HINT_SAVED provider=tiktok strategy=... authenticated=... source=checkpoint
SYNC_PAGE_DONE ...
```

If repeated TLS failures open the breaker during the stable-ID candidate, the handle candidate must not restart impersonation. It must skip directly to a direct strategy or pause cleanly.

When fewer than five seconds remain in the page budget, no new extractor process may start. The run must pause with the same `resume_from`.

A four-page invocation limit must report:

```text
SYNC_RUN_PAUSED provider=tiktok reason=max_pages_per_run ...
```

The JSON summary must include:

```json
"creator_identifiers": {"sec_uid": "MS4wLjAB..."}
```
