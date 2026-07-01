# Bilibili vs YouTube Capability Gap Checklist

Last updated: 2026-07-02

This checklist captures the remaining capability and UX gaps between the current
`bilibili` implementation and the more mature `youtube` path in Media2MD.

It is not a statement that Bilibili is broken. The current Bilibili pipeline is
already production-usable for:

- single media ingest
- creator add / refresh-catalog / run
- creator drain with cached-catalog fallback
- caption-first processing when subtitles are available
- audio download + local transcription fallback
- long-video chunk progress visibility in `creator run`

The purpose of this file is to make the remaining non-parity visible so we can
close them deliberately.

## Current Parity Snapshot

Status summary:

- `single_media`: parity is good enough
- `creator_sync`: mostly there, but less robust than YouTube
- `batch_drain`: usable, but less resilient under live platform pressure
- `doctor / status`: present, but less detailed than YouTube in a few places
- `configurability`: clearly behind YouTube
- `catalog semantics`: clearly behind YouTube

## Gap 1: Multi-Surface Catalog Model

YouTube today:

- has explicit catalog surfaces: `videos`, `shorts`, `streams`
- stores per-surface totals
- carries per-surface exactness
- exposes surface-aware status output
- supports multi-surface creator sync checkpoints

Bilibili today:

- has only one effective surface: `videos`
- surfaces are exposed in status output, but only as a single synthetic surface
- there is no richer content taxonomy beyond `bilibili_video`

Impact:

- users get less expressive catalog semantics than YouTube
- future Bilibili expansion has no obvious place to land

Checklist:

- [ ] Decide whether Bilibili should remain intentionally single-surface
- [ ] If not, define the target Bilibili surface taxonomy
- [ ] Add explicit Bilibili surface metadata to catalog persistence, not just status rendering
- [ ] Add tests that enforce the intended Bilibili catalog-surface model

## Gap 2: Live Creator Sync Resilience

YouTube today:

- has more mature sync branching
- supports per-surface sync behavior
- has better-authenticated fallback handling
- has richer long-lived sync checkpoint behavior

Bilibili today:

- primary creator sync uses `bilibili-api`
- fallback on creator space sync can use `yt-dlp --flat-playlist`
- live refresh is more vulnerable to `412` / `352` platform blocking
- `--allow-stale-catalog` is now a good UX escape hatch, but still a workaround

Impact:

- live creator refresh reliability is weaker than YouTube
- long-running automated drain flows are more likely to rely on cached state

Checklist:

- [ ] Measure how often `bilibili-api` creator refresh fails in live use
- [ ] Decide whether cached-catalog mode should become default policy for some Bilibili drain modes
- [ ] Add stronger structured reasons for Bilibili refresh fallback in machine-readable output
- [ ] Consider a more durable Bilibili creator-sync transport order, not just a single primary plus fallback

## Gap 3: Configurability and Settings Surface

YouTube today has dedicated settings for:

- caption-first behavior
- caption language preferences
- sponsor filtering
- audio download strategies
- long-video threshold
- chunk duration
- chunk model
- JS runtime / PO token related access controls

Bilibili today:

- has effectively no equivalent user-facing provider-specific settings surface
- uses the shared long-video / chunk logic, but without Bilibili-specific knobs

Impact:

- Bilibili is less tunable for operators
- YouTube has a much more mature “production control panel” feel

Checklist:

- [ ] Decide which Bilibili settings deserve public support
- [ ] Add Bilibili-specific settings only where they unlock real operational control
- [ ] Avoid copying YouTube knobs mechanically when Bilibili does not need them
- [ ] Add settings docs only after the supported knobs are stable

## Gap 4: Transcript Strategy Transparency

YouTube today:

- exposes a clearer strategy ladder:
  - caption-first
  - authenticated/public audio strategy cascade
  - sponsor filtering on transcript text
- has more transcript strategy detail in code and settings

Bilibili today:

- has caption-first plus audio fallback
- now exposes chunk-level progress in live drain
- does not yet expose as rich a “strategy identity” surface to users as YouTube

Impact:

- the pipeline works, but user understanding is thinner

Checklist:

- [ ] Surface the final Bilibili transcript strategy more explicitly in human output where useful
- [ ] Add machine-readable markers for `bilibili_captions` vs `bilibili-api-audio-stream` outcomes
- [ ] Consider whether Bilibili needs transcript filtering or cleanup stages similar to YouTube sponsor filtering

## Gap 5: Doctor Depth

YouTube doctor is stronger because it checks:

- access transport concerns
- transcription tooling
- auth-sensitive paths
- more nuanced fallback/readiness cases

Bilibili doctor today:

- validates video ID shape
- checks ffmpeg / mlx_whisper readiness
- checks metadata access
- checks captions
- checks audio download
- can do transcription smoke test

This is already solid, but still simpler than YouTube.

Checklist:

- [ ] Compare the final `doctor youtube-access` and `doctor bilibili-access` payload shapes field by field
- [ ] Add any missing Bilibili evidence fields that materially help debugging
- [ ] Keep schema parity where it improves automation, not just for aesthetics

## Gap 6: Status / Totals Richness

YouTube status today includes:

- per-surface totals
- streams visibility
- exactness details tied to multiple surfaces

Bilibili status today includes:

- creator totals
- exact current total flag
- synthetic `surface=videos`

Impact:

- good enough for operation
- not yet as informative as YouTube

Checklist:

- [ ] Decide whether Bilibili needs additional totals beyond `all`
- [ ] If creator sync fallback path can only provide partial truth, label that explicitly in status
- [ ] Keep status schema aligned even if Bilibili stays single-surface

## Gap 7: Output / Artifact Observability

Recent progress:

- Bilibili now shows stale-catalog guidance in human output
- Bilibili long-video runs now show chunk progress in the progress bar

Remaining gap versus YouTube maturity:

- some deeper strategy and fallback evidence is still more implicit than explicit

Checklist:

- [ ] Decide whether chunk progress should also be emitted as NDJSON progress detail
- [ ] Decide whether final run summary should report transcript strategy composition by item type
- [ ] Consider whether long-running drain should emit more explicit per-item strategy summaries after completion

## Gap 8: Identity and Canonicalization Maturity

YouTube today has stronger creator identity normalization because of:

- channel base handling
- surface-aware URLs
- richer handle/channel semantics

Bilibili today:

- canonical creator identity is mostly anchored on `mid`
- canonical media identity is BV-based
- video URL to creator resolution works, but identity semantics are simpler

This is not necessarily bad, but it is less developed.

Checklist:

- [ ] Audit Bilibili creator identity persistence paths for any remaining ambiguity between display name and `mid`
- [ ] Ensure all user-visible creator references prefer stable canonical identity where appropriate
- [ ] Add regression tests for more Bilibili creator URL and video URL variants

## Gap 9: Automated Regression Breadth

Current Bilibili coverage is much better than before, but still lighter than the accumulated YouTube path.

Checklist:

- [ ] Add a dedicated Bilibili first-user-flow regression pack
- [ ] Add more creator-sync fallback tests around `412` / `352`
- [ ] Add transcript-strategy regression tests for:
  - captions available
  - captions unavailable
  - long chunked transcription
  - stale-catalog creator drain

## Recommended Closing Order

High value next:

1. Bilibili live creator sync resilience policy
2. Bilibili doctor/status schema parity audit
3. Bilibili regression breadth expansion

Second wave:

4. Bilibili transcript strategy observability
5. Bilibili settings surface design
6. Bilibili identity/canonicalization hardening

Later, only if we need it:

7. richer Bilibili surface taxonomy

## Honest Bottom Line

Current Bilibili is:

- production-usable
- much better than the earlier implementation
- close enough to YouTube in the core operator workflow

Current Bilibili is not yet:

- as configurable as YouTube
- as sync-resilient as YouTube
- as catalog-rich as YouTube
- as regression-protected as YouTube

That is the gap we should close next.
