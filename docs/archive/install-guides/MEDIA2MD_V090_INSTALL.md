# Media2MD v0.9.0 installation and final live closure

v0.9.0 is the consolidated private-production candidate built from the complete
`media2md-one-shot-evidence-20260625T151508.zip` run. It fixes the product defects
found in that run without rewriting the already-passing Instagram, TikTok batch,
backup, and two-hour YouTube transcription paths.

## Fixed in this release

1. Instagram `/accounts/edit/` with valid session cookies is authenticated, even
   when the normal application bundle contains the word `checkpoint`.
2. TikTok `media inspect` uses the same bounded transport/authentication cascade
   as real processing and persists the successful strategy.
3. YouTube channels containing Shorts but no Videos tab are accepted as exact
   multi-surface catalogs with an empty exact Videos surface.
4. A resumed TikTok staged rebuild can never publish its checkpoint items as a
   non-exact active catalog before entering the cursor backend.
5. Reprocessing an existing current media item preserves an exact creator catalog;
   only a genuinely new manual item invalidates exactness.
6. OpenClaw isolated Cron installation defaults to `--no-deliver`. Announcements
   require an explicit channel and recipient.
7. GitHub update discovery is advisory. A repository without a Release, or a
   temporary update-check network failure, cannot fail a successful scheduler run.
8. The installer repairs a matching downgraded TikTok exact state and marks a
   resumable cursor checkpoint as a staged exact rebuild, including checkpoints
   that already contain discovered items.

## Install

Run installation only while no Media2MD Sync, Batch, direct media process, backup,
or OpenClaw Media2MD job is active.

```bash
(
  set -euo pipefail

  cd "$HOME/instagram-to-md"
  source .venv/bin/activate

  ZIP="$HOME/Downloads/media2md-v0.9.0-source.zip"
  SHA_FILE="$ZIP.sha256"

  test -f "$ZIP"
  test -f "$SHA_FILE"

  EXPECTED_SHA="$(awk '{print $1}' "$SHA_FILE")"
  ACTUAL_SHA="$(shasum -a 256 "$ZIP" | awk '{print $1}')"

  echo "expected_sha256=$EXPECTED_SHA"
  echo "actual_sha256=$ACTUAL_SHA"
  test "$EXPECTED_SHA" = "$ACTUAL_SHA"

  rm -rf /tmp/media2md-v090
  mkdir -p /tmp/media2md-v090
  unzip -q "$ZIP" -d /tmp/media2md-v090

  python /tmp/media2md-v090/install_media2md_v090.py \
    --target "$HOME/instagram-to-md"

  ./bin/media2md version | grep -F "media2md 0.9.0"
  echo "MEDIA2MD_V090_INSTALL_GATE_PASSED"
)
```

Expected installer markers include:

```text
MEDIA2MD_V090_INSTALLED
version=0.9.0
tiktok_exact_state_repaired=0-or-more
tiktok_exact_rebuild_checkpoints_staged=0-or-more
data_preserved=config,data,logs,workspace,markdown,downloads,transcripts
MEDIA2MD_V090_INSTALL_GATE_PASSED
```

## Final closure gate

After installation, run the separate
`media2md-v090-final-closure-acceptance.zip`. It reruns only the live gates that
failed or were blocked in the complete v0.8.6 evidence package, plus final exact
state and backup integrity. The already-passing two-hour long-video and large batch
evidence is carried forward by SHA-256 rather than needlessly repeated.
