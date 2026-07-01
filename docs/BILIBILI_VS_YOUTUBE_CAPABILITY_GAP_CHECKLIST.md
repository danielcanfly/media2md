# Bilibili vs YouTube Capability Gap Checklist

Last updated: 2026-07-02 (post-`68f031b`)

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
- `creator_sync`: mostly there, but still less robust than YouTube under live platform pressure
- `batch_drain`: production-usable, with cached-catalog resilience and chunk-progress visibility
- `doctor / status`: strong enough for automation, with a few intentional single-surface differences
- `configurability`: substantially improved; now has a real Bilibili provider settings surface
- `catalog semantics`: intentionally simpler than YouTube

## What Closed In This Pass

This pass closed a meaningful portion of the old “paper gaps” by landing actual
runtime, doctor, CLI-schema, and regression work:

- Bilibili now has a dedicated provider settings surface:
  - `caption_first`
  - `long_video_threshold_seconds`
  - `chunk_seconds`
  - `chunk_model`
- `settings set`, `settings show`, `agent status`, and the provider capability
  matrix now expose those settings explicitly
- Bilibili transcription settings no longer piggyback silently on YouTube
  thresholds and chunking controls
- Bilibili doctor now reports:
  - caption-first enabled/disabled state
  - provider-specific threshold / chunk / model settings
  - clearer pipeline strategy identity
- creator status already exposes:
  - `surface=videos`
  - `catalog_surfaces=videos`
  - `pagination_backend`
  - `sync_incomplete`
  - `sync_pause_reason`
- creator-run NDJSON summary now includes structured `strategy_summary`
- identity / canonicalization regressions now cover more Bilibili creator/video
  URL variants

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

- [x] Decide whether Bilibili should remain intentionally single-surface
- [x] Add explicit Bilibili surface metadata to catalog persistence and status rendering
- [x] Add tests that enforce the intended Bilibili catalog-surface model
- [ ] Define a richer surface taxonomy only if real product needs emerge later

Current stance:

- Bilibili is intentionally single-surface today: `videos`
- this is a product choice, not an accidental omission

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
- [x] Decide whether cached-catalog mode should become preferred policy for some Bilibili drain modes
- [x] Add stronger structured reasons for Bilibili refresh fallback in machine-readable output
- [ ] Consider a more durable Bilibili creator-sync transport order, not just a single primary plus fallback

Current state:

- `--allow-stale-catalog` plus structured `resilience_policy` is now a real,
  intentional operator path
- exact saved catalogs can skip redundant presync before `creator run`
- the remaining gap is live platform resilience, not CLI policy clarity

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

- [x] Decide which Bilibili settings deserve public support
- [x] Add Bilibili-specific settings only where they unlock real operational control
- [x] Avoid copying YouTube knobs mechanically when Bilibili does not need them
- [ ] Expand public docs only after the supported knobs are stable in more live use

Current supported knobs:

- `caption_first`
- `long_video_threshold_seconds`
- `chunk_seconds`
- `chunk_model`

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

- [x] Surface the final Bilibili transcript strategy more explicitly in machine-readable and doctor output
- [x] Add machine-readable markers for `bilibili_captions` vs `bilibili-api-audio-stream` outcomes
- [ ] Consider whether Bilibili needs transcript filtering or cleanup stages similar to YouTube sponsor filtering

Current state:

- Markdown already preserves `transcription_source`
- doctor now exposes caption-first state and final pipeline strategy
- creator-run summary now exposes structured strategy-summary evidence

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

- [x] Compare the final `doctor youtube-access` and `doctor bilibili-access` payload shapes field by field
- [x] Add missing Bilibili evidence fields that materially help debugging
- [x] Keep schema parity where it improves automation, not just for aesthetics

Current additions:

- `caption_first_enabled`
- `long_video_threshold_seconds`
- `chunk_seconds`
- `chunk_model`
- clearer `pipeline_strategy`

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

- [x] Decide whether Bilibili needs additional totals beyond `all`
- [x] If creator sync fallback path can only provide partial truth, label that explicitly in status
- [x] Keep status schema aligned even if Bilibili stays single-surface

Current stance:

- no extra public totals are needed today beyond the single `videos` surface
- partial truth is now surfaced via `pagination_backend`, `sync_incomplete`,
  and `sync_pause_reason`

## Gap 7: Output / Artifact Observability

Recent progress:

- Bilibili now shows stale-catalog guidance in human output
- Bilibili long-video runs now show chunk progress in the progress bar

Remaining gap versus YouTube maturity:

- some deeper strategy and fallback evidence is still more implicit than explicit

Checklist:

- [x] Decide whether chunk progress should also be emitted as NDJSON progress detail
- [x] Decide whether final run summary should report transcript strategy composition after completion
- [ ] Consider whether long-running drain should emit more explicit per-item strategy summaries after completion

Current state:

- chunk progress is already visible during long runs
- creator-run NDJSON summary now includes structured `strategy_summary`
- per-item final strategy recap could still be expanded later if operators ask for it

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

- [x] Audit Bilibili creator identity persistence paths for remaining ambiguity between display name and `mid`
- [x] Ensure user-visible creator references prefer stable canonical identity where appropriate
- [x] Add regression tests for more Bilibili creator URL and video URL variants

Current state:

- canonical creator identity is still `mid`-first
- this is acceptable and stable for Bilibili

## Gap 9: Automated Regression Breadth

Current Bilibili coverage is much better than before, but still lighter than the accumulated YouTube path.

Checklist:

- [x] Add a dedicated Bilibili first-user-flow regression pack
- [x] Add more creator-sync fallback tests around `412` / `352`
- [x] Add transcript-strategy regression tests for:
  - captions available
  - captions unavailable
  - long chunked transcription
  - stale-catalog creator drain

## Recommended Closing Order

## Remaining Real Gaps

What is still meaningfully behind YouTube is no longer the CLI contract layer.
It is mostly live platform resilience:

1. Bilibili live creator refresh still degrades sooner under `412` / `352`
2. There is still no second durable creator-sync transport with parity to the
   primary API path
3. Surface taxonomy remains intentionally simpler than YouTube
4. Bilibili does not currently need a YouTube-like transcript cleanup stage,
   but that may change if real noisy transcript patterns show up in live use

## Bottom Line

Bilibili is now much closer to YouTube in:

- CLI schema discipline
- settings surface clarity
- doctor/status evidence quality
- creator-run observability
- identity normalization
- regression protection

The remaining differences are now mostly honest platform limitations or
intentional product choices, not missing architecture.

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
