# Bilibili + XiaoHongShu Integration Plan

## Goal

Add Bilibili and XiaoHongShu/RedNote support to `media2md` in a way that matches the repo's current production direction:

- local-first where possible
- deterministic Markdown output
- resumable artifact handling
- provider-specific fallbacks instead of one brittle universal scraper
- future-safe creator/catalog expansion without destabilizing existing Instagram / YouTube / TikTok paths

This plan is based on a deeper code review of:

- `Panniantong/Agent-Reach`
- `Nemo2011/bilibili-api`
- `JoeanAmier/XHS-Downloader`
- public documentation and current repo design around `OpenCLI`, `xiaohongshu-mcp`, and Bilibili tooling

## What Agent-Reach Gets Right

### 1. Capability routing beats single-backend purity

`Agent-Reach` does not try to make one tool solve everything.

For Bilibili:

- `bili-cli` for search / hot / detail
- `OpenCLI` for subtitles
- raw search API as a zero-dependency fallback

For XiaoHongShu:

- `OpenCLI` on desktop
- `xiaohongshu-mcp` on server
- `xhs-cli` as a legacy fallback

This is a strong design choice for brittle platforms.

### 2. Environment-aware backend choice

`Agent-Reach` encodes a useful split:

- desktop/browser-session tools when a local browser exists
- server/headless tools when it does not

This is especially correct for XiaoHongShu, where browser context and login state matter more than elegant API theory.

### 3. Honest acceptance of platform reality

Two examples matter:

- Bilibili: stop pretending `yt-dlp` is a reliable primary backend when it is 412-blocked
- XiaoHongShu: treat `xsec_token` as first-class reality, not a corner case

That honesty is worth copying.

## Where Agent-Reach Is Not Enough For media2md

`Agent-Reach` is a capability layer. `media2md` is an archival processing system.

We need more than "can read now":

- canonical metadata model
- stable Markdown rendering
- saved assets and transcript provenance
- resumable processing
- creator/catalog lifecycle
- artifact paths and registry state

So we should borrow its routing strategy, but not copy its product shape.

## Best Source Per Platform

## Bilibili

### Best routing idea

Borrow from `Agent-Reach`:

- do not use `yt-dlp` as the primary Bilibili metadata/read path
- treat subtitles and metadata as separate capabilities

### Best codebase for deep integration

Use `Nemo2011/bilibili-api` as the main implementation reference.

Why:

- Python library, not just a CLI wrapper
- rich video/search/user modules
- better fit for direct integration into `media2md`
- easier to normalize into provider contracts than shelling out everywhere

### Best fallback tools

- `bili-cli` for low-friction user machines and CLI parity
- `OpenCLI` for subtitle extraction where browser session helps

### Recommended Bilibili backend order for media2md

For `inspect/read/search`:

1. `bilibili-api`
2. `bili-cli`
3. public search API fallback for search-only

For subtitles/transcript:

1. Bilibili subtitle/caption source via API or browser-backed path
2. `OpenCLI bilibili subtitle`
3. audio extraction + local Whisper fallback

For audio:

1. platform-native audio URL / dedicated downloader if available
2. `bili audio BVxxx` style helper if shell fallback is needed
3. never make `yt-dlp` the default Bilibili path

## XiaoHongShu / RedNote

### Best routing idea

Borrow from `Agent-Reach`:

- desktop/browser-backed read path
- server/headless read path
- legacy CLI fallback only if already present

### Best codebase for asset + note handling

Use `JoeanAmier/XHS-Downloader` as the primary code reference.

Why:

- much deeper note/asset handling than `Agent-Reach`
- real file download pipeline
- note normalization
- download resume / skip / archive behavior
- practical handling of note image/video/livePhoto style assets

### Best server/browser-session reference

Use `xiaohongshu-mcp` conceptually for:

- QR login
- browser-session-backed read access
- server environment routing

But do not make MCP the only implementation dependency for `media2md`.

### What to avoid

Do not make `xhs-cli` the main future-facing backend.

Reason:

- legacy/unmaintained direction
- too fragile for production baseline
- okay as optional fallback, not as architectural center

## Key Design Decision For media2md

We should not launch Bilibili and XiaoHongShu as "full creator sync" on day one.

That would repeat the same mistake we avoided with Instagram post OCR:

- too many surfaces at once
- too much provider-specific catalog complexity too early
- much higher chance of destabilizing the stable core

Instead, use a staged rollout.

## Recommended Architecture

## Shared provider model

Each new provider should plug into existing layers:

1. target parsing / canonicalization
2. inspect/read metadata
3. optional assets resolution
4. transcript/caption pipeline
5. Markdown rendering
6. registry/catalog integration

Use the existing direction already present in `media2md`:

- provider parsing and canonical URLs
- `generic_media.process_row`
- provider-specific metadata hydration
- normalized Markdown output
- registry-backed creator flows

## Bilibili provider shape

### Phase B1: single-video read path

Support:

- `https://www.bilibili.com/video/BV...`
- short links that can be normalized to BV URLs

Output:

- title
- description
- uploader
- publish time
- duration
- source URL
- media type
- subtitle availability

Transcript strategy:

- if subtitles exist, use them first
- else audio fallback

### Phase B2: subtitle/audio artifact path

Add:

- `transcription_source = "bilibili_captions"` when direct subtitles exist
- `caption_language`
- `caption_probe_result`
- local audio fallback metadata

### Phase B3: search / creator metadata

Add:

- search helper
- creator/channel normalization
- limited creator add/read before full sync

### Phase B4: creator catalog

Only after single-item and transcript paths are proven:

- creator video catalog
- backlog processing
- batch policy

## XiaoHongShu provider shape

### Phase X1: single-note read path

Support only single note URLs first:

- `xiaohongshu.com/explore/...`
- `xiaohongshu.com/discovery/item/...`
- `rednote.com/...`
- share links resolved to canonical note URLs

Do not start with creator profile sync.

### Phase X2: note asset extraction

Borrow ideas from `XHS-Downloader`:

- normalize note metadata
- resolve image/video asset URLs
- support multi-image note assets
- support separate saved asset manifests
- preserve note source identifiers and author identifiers

### Phase X3: Markdown rendering

For text/image notes:

- original title
- original description
- asset list
- optional OCR path later

For video notes:

- metadata
- assets
- subtitle if any
- audio fallback if needed

### Phase X4: creator/profile expansion

Only after note read path is stable:

- public profile note listing
- backlog processing policy
- mixed content handling

## Backend Strategy Recommendation

## Bilibili

Default:

- `bilibili-api`

Fallbacks:

- `bili-cli`
- `OpenCLI`

Optional config ideas:

- `--bilibili-backend api|bili-cli|opencli|auto`
- `--bilibili-caption-first`

## XiaoHongShu

Default:

- desktop: `OpenCLI`
- server/headless: dedicated browser-backed backend

Fallbacks:

- `XHS-Downloader`-inspired direct note fetch / asset resolution
- optional `xhs-cli` only if already installed

Optional config ideas:

- `--xiaohongshu-backend auto|opencli|mcp|direct|xhs-cli`
- `--xiaohongshu-note-assets`

## What We Should Reuse Conceptually From XHS-Downloader

Not the whole app, but these ideas are high value:

1. note metadata normalization
2. asset type classification
3. resumable downloads
4. archive/path naming strategy
5. download record / skip-existing logic
6. API-mode separation from UI/TUI concerns

What not to copy:

- TUI-heavy structure
- giant monolithic config surface
- app-level clipboard/interactive affordances

## What We Should Reuse Conceptually From bilibili-api

1. typed video/search/user modules
2. direct BV/AID canonicalization
3. structured metadata access over shell parsing
4. easier mapping into provider result contracts

What not to copy:

- overly broad initial scope
- every Bilibili feature before validating the minimal media2md flow

## Best Final Strategy

If the goal is "best production path for media2md", the answer is:

### Bilibili

- architecture idea from `Agent-Reach`
- implementation depth from `bilibili-api`
- subtitle fallback from `OpenCLI`
- local ASR fallback from existing `media2md` transcription pipeline

### XiaoHongShu

- routing idea from `Agent-Reach`
- note/asset extraction ideas from `XHS-Downloader`
- server/browser-session option inspired by `xiaohongshu-mcp`
- creator/catalog expansion deferred until note read path is stable

## Implementation Phases

## Phase 1: Bilibili single-item support

- add target parser + canonicalizer
- add inspect/read metadata path
- add subtitle-first transcript path
- add audio fallback
- add Markdown rendering
- add focused contract tests

## Phase 2: XiaoHongShu single-note support

- add note URL parser + canonicalizer
- add note metadata extractor
- add asset manifest generation
- add Markdown rendering
- no creator sync yet

## Phase 3: Bilibili polish

- search helper
- uploader/channel metadata
- better subtitle source selection
- fallback diagnostics

## Phase 4: XiaoHongShu polish

- desktop/server backend routing
- note image/video variants
- better note normalization
- optional OCR for image notes later

## Phase 5: creator/catalog experiments

- Bilibili creator catalog prototype
- XiaoHongShu profile note listing prototype
- no public release until live evidence is stable

## Acceptance Criteria

Before either provider is called production-ready:

1. single-item read path is deterministic
2. metadata shape matches provider contracts
3. Markdown output is stable and provenance-rich
4. subtitle/audio fallback behavior is explicit
5. assets save to predictable paths
6. regressions cover parsing, metadata shape, transcript source, and fallback routing
7. no existing YouTube / Instagram / TikTok path regresses

## Recommendation

Do Bilibili first.

Reason:

- cleaner library integration path
- clearer subtitle/audio model
- lower `xsec_token` / browser-state complexity than XiaoHongShu
- easier to land without destabilizing the repo

Then do XiaoHongShu note read path.

Do not start with creator sync for either provider.

## Current Status

### Bilibili

Bilibili is no longer a greenfield provider in `media2md`.

Already landed in the repo:

- single-media inspect/read path
- caption-first processing with local audio fallback
- audio download via `bilibili-api`
- canonical creator normalization for `space/<mid>`
- creator refresh-catalog / run support
- `doctor bilibili-access`
- provider contract registration
- creator identity merge hardening
- legacy creator repair into canonical `mid` / `space` rows
- creator status accounting aligned to current catalog rows

That means the next Bilibili work should focus on parity, diagnostics, and UX polish rather than redoing the core pipeline.

### XiaoHongShu

XiaoHongShu / RedNote is still in planning / reference-study mode.

That is actually a good place to be:

- no legacy behavior to preserve yet
- we can design a clean single-note-first path
- we can wire it into the existing provider contracts from day one

## Next Task Backlog

### Bilibili Task 01: Doctor / remediation / evidence parity

Goal:

- make Bilibili failures as actionable as YouTube / TikTok failures

Scope:

- install guidance
- doctor guidance
- repair guidance
- stronger first-user troubleshooting messages

Acceptance:

- dependency failures mention the correct install command
- pipeline failures mention `media2md doctor bilibili-access`
- identity/canonicalization issues can point at `media2md repair identities`
- focused regression tests cover these hints

### Bilibili Task 02: Creator UX polish

Goal:

- make creator flows easier to reason about during backlog runs

Scope:

- clearer human output around catalog vs backlog state
- stronger NDJSON catalog context for machine consumers
- output-path hints after creator processing where useful
- longer live drain validation on larger creators

Acceptance:

- first-user flow shows enough context to understand what is happening
- status output distinguishes current catalog work from historical rows
- machine-readable output stays stable across provider-specific paths

### Bilibili Task 03: Creator lookup and metadata helper

Goal:

- reduce friction between single-media reads and creator onboarding

Scope:

- safer transitions from single media -> canonical creator
- optional metadata-based creator lookup helper
- lighter-weight creator discovery path before full sync

Acceptance:

- adding or learning a creator from a known BV can converge to canonical `mid`
- no regression to current `creator refresh-catalog` semantics

### XiaoHongShu Task 01: Single-note foundation

Goal:

- land one clean note pipeline before any creator/catalog work

Scope:

- note URL parsing / canonicalization
- note metadata extraction
- asset manifest extraction
- deterministic Markdown rendering
- local-first artifact layout

Acceptance:

- a public note can be inspected and rendered to Markdown
- note text and asset inventory are preserved
- failure output points toward the correct browser-backed remediation path

### XiaoHongShu Task 02: Desktop/browser-backed reader

Goal:

- establish a reliable authenticated route for notes that need browser/session state

Scope:

- desktop/browser-backed note reader
- backend routing based on environment and auth state
- remediation text for login / QR / invalid session paths

Acceptance:

- when public extraction fails, the next browser-backed path is explicit
- provider contract clearly exposes which backend was used

## Suggested Execution Order

1. Bilibili Task 01
2. Bilibili Task 02
3. Bilibili Task 03
4. XiaoHongShu Task 01
5. XiaoHongShu Task 02

This order keeps the highest leverage path:

- finish parity on the provider that already exists
- only then open a new provider surface

## Evidence Checklist Per Task

Every task should close with:

- commands run
- exit codes
- focused tests
- live probe or live provider evidence when applicable
- whether runtime reinstall was needed
- whether any repair command changed canonical rows
