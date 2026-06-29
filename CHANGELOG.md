# Changelog

## 0.9.3 - 2026-06-29

- Add `creator refresh-catalog` as the preferred public command name for refreshing creator catalogs while keeping `creator sync` available in the full command surface.
- Improve `creator run` operator feedback with a pip-style single-line stage progress display, plus clearer completion output including the result folder, latest markdown path, and a Finder-friendly open hint.
- Change fresh managed-runtime installs to default under `~/Downloads/media2md`, while preserving older managed locations until explicitly relocated.
- Add `media2md runtime base-path` and `media2md runtime set-base-path <path>`, and make base-path changes migrate the managed tree instead of only updating metadata.
- Make `media2md uninstall` remove the installed Python package by default, with `--dry-run` available for preview-only behavior.
- Fix creator-run progress-loop compatibility for mocked process objects and relax the historical v0.9.1 installer regression so it validates preserved installer artifacts without pinning the active package version.

## 0.9.2 - 2026-06-29

- Update the public README and CLI reference so installation, authentication, and creator workflows match the published PyPI package and current CLI behavior.
- Clarify that Media2MD is designed for both direct terminal use and agent-driven automation workflows, including OpenClaw-aligned scheduling and machine-readable status surfaces.
- Require `--provider` for bare creator handles such as `@creator-name` or `creator-name`, while still auto-detecting the provider from full creator URLs.
- Remove the ambiguous default-to-Instagram behavior from public creator commands and add regression coverage for provider resolution.

## 0.9.1 - 2026-06-25

- Treat HTTP 200 on TikTok's authenticated `/setting` endpoint as authenticated even when generic captcha strings appear in application JavaScript.
- Add deterministic TikTok metadata fallbacks: the bounded live transport cascade remains first, followed by verified local Registry/processing metadata and a direct no-proxy oEmbed fallback.
- Make TikTok Doctor reuse the real processing cascade and report a truthful degraded-ready state when a transient live probe fails but a recent completed Markdown artifact proves end-to-end operation.
- Add live-evidence regressions for TikTok auth, metadata fallback, and degraded Doctor semantics.

## 0.9.0 - 2026-06-25

- Consolidate every product defect found by the complete v0.8.6 one-shot evidence run into one private-production candidate.
- Fix valid Instagram sessions being misclassified as `platform_challenge` when the authenticated `/accounts/edit/` application bundle contains the word `checkpoint`.
- Route TikTok metadata inspection through the same bounded transport/authentication cascade as media processing and persist the winning strategy.
- Treat an absent YouTube Videos, Shorts, or Streams tab as an empty exact surface, allowing Shorts-only channels to Full Sync successfully.
- Prevent resumed TikTok staged checkpoints from publishing partial items and downgrading a proven exact active catalog before cursor continuation.
- Preserve creator exactness when manually reprocessing a media item already present in the current exact catalog.
- Default isolated OpenClaw Cron installation to `--no-deliver`; require an explicit channel and recipient for announcement delivery.
- Make GitHub Release discovery advisory so 404/no-release and transient network errors cannot poison a successful scheduler tick.
- Extend upgrade migration to repair a matching downgraded TikTok exact state and stage resumable cursor checkpoints that already contain items.
- Add evidence-derived regression coverage for all fixes and retain historical v0.8.1, v0.8.3, v0.8.5, and v0.8.6 failures in cumulative acceptance.

## 0.8.5 - 2026-06-25

- Promote the v0.8.4 TikTok staged-rebuild fix after the live StartupBell gate preserved the exact 1,159-item baseline through a 12-page pause and completed a 5/5 Batch.
- Add per-creator Sync and Run locks so duplicate scheduler/manual invocations cannot process the same creator concurrently.
- Add per-media processing locks to prevent direct URL processing and Creator Run from downloading or transcribing the same media simultaneously.
- Add a shared/exclusive maintenance lock: live work may run concurrently across unrelated creators, while backup and destructive maintenance require an idle, consistent state.
- Serialize the shared TikTok cursor-device state writer and increase SQLite busy timeouts for long-running local workloads.
- Add `media2md data backup` and `media2md data verify-backup` with SQLite online snapshots, SHA-256 manifests, integrity checks, atomic archive replacement, and deliberate exclusion of browser/session secrets.
- Add production-safety regressions for lock ownership, duplicate-run rejection, backup verification, database integrity, and secret exclusion.

## 0.8.4 - 2026-06-25

- Stage TikTok Full rebuilds in the cursor checkpoint while preserving the last exact catalog as the active processing baseline until the rebuild completes.
- Keep `current_total_exact` and `media_type_totals_exact.tiktok_video` true when a rebuild pauses or its first cursor request returns 403.
- Report staged rebuild state with `baseline_preserved`, `rebuild_in_progress`, and `staged_total` instead of publishing a partial replacement.
- Persist the last successful TikTok cursor device ID independently of the transient checkpoint and reuse it after a completed Full Sync removes the checkpoint.
- Migrate v0.8.3 failed-rebuild checkpoints and safely repair matching exact-state regressions during upgrade.
- Count retryable failed media in the actual remaining queue when `--max-failures` stops a Creator Run.
- Add regression tests for zero-page failure, partial staged rebuilds, cursor device reuse, installer migration, and retryable remaining counts.

## 0.8.3 - 2026-06-25

- Preserve a proven TikTok exact catalog across bounded Quick Sync merges instead of downgrading `current_total_exact` to false.
- Skip hidden TikTok pre-run sync for both partial and exact cached catalogs; processing no longer mutates catalog exactness.
- Add registry-backed fresh cursor bootstrap after a completed Full Sync deletes its checkpoint, so the next explicit `--force-full` starts a new cursor rebuild rather than legacy playlist pagination.
- Restore exact state during upgrade only when `current_total == last_full_exact_total` and a completed Full Sync timestamp exists.
- Report `media_type_totals_exact.tiktok_video` and `last_full_media_type_totals.tiktok_video` consistently.
- Add public CLI and registry lifecycle regressions for exact catalog preservation, exact-catalog skip, idempotent cursor rebuild, and safe installer repair.

## 0.8.1 - 2026-06-24

- Preserve the command-start TikTok total before cursor pages update the Registry, so `previous_current_total` and `new_since_last_sync` report the actual run delta.
- Emit `SYNC_CURSOR_ATTEMPT_RESULT` for failed public, authenticated, timeout, invalid-JSON, and API-status attempts.
- Skip the legacy TikTok Quick Sync before Batch while a resumable cursor Full Sync is still incomplete; known catalog items are used directly.
- Add a bounded per-item TikTok download transport cascade with direct no-proxy public/authenticated attempts before curl-cffi impersonation.
- Persist the last successful TikTok media-download strategy separately from the catalog transport hint and load it on later items/runs.
- Share a finite per-item download budget and emit explicit attempt/result telemetry.
- Always emit `CREATOR_RUN_COMPLETED` when `--max-failures` or stop-on-failure ends a batch early.
- Preserve stored TikTok `sec_uid`/`user_id` in Quick and Partial summaries.
- Keep the v0.8.0 native cursor Catalog engine and live-passing Instagram/YouTube paths unchanged.

## 0.8.0 - 2026-06-24

- Replace resumed TikTok `--playlist-start` deep pagination with a persistent `creator/item_list` cursor backend.
- Recover an initial cursor from the oldest normalized checkpoint timestamp and persist `tiktok_cursor` plus a stable `tiktok_device_id` in checkpoint schema 5.
- Fetch one bounded cursor page at a time with native macOS curl, `--noproxy *`, and a proxy-cleared environment.
- Atomically save every successful cursor page before requesting the next page.
- Establish the exact TikTok total when `hasMorePrevious=false`; otherwise pause cleanly on runtime/page-count/request failure.
- Retain the v0.7.x bounded yt-dlp page extractor only as a bootstrap/diagnostic fallback for creators without a recovered secUid.
- Keep the live-passing Instagram, YouTube, typed-batch, and installer paths unchanged.

## 0.7.9

- Persist the last successful TikTok transport/auth pair in checkpoint schema 4 and reload it across CLI invocations.
- Prefer isolated direct transport when an old checkpoint has no hint and macOS system proxies are enabled.
- Share one TLS circuit breaker across stable-ID and handle candidates for the entire page.
- Stop before launching another extractor when less than five seconds remain in the page budget.
- Preserve `creator_identifiers.sec_uid` in partial, paused, and completed TikTok summaries.
- Report `max_pages_per_run` when the configured page-count cap pauses a run.
- Keep Instagram and YouTube execution paths unchanged.


## 0.7.8

- Fix TikTok stable-ID catalog pages that successfully return JSON but omit a human-readable handle. The existing normalized creator handle is now reused as metadata context.
- Stop the duplicate handle-profile fetch after a stable-ID page succeeds.
- Add `SYNC_STABLE_ID_HANDLE_REUSED ... second_profile_fetch=false` evidence.
- Convert bounded TikTok page exhaustion from a hard error into a clean resumable `SYNC_RUN_PAUSED reason=page_budget_exhausted`.
- Preserve checkpoint item count and `next_start` exactly on clean pause.
- Remove a duplicate set of yt-dlp flat-playlist flags.
- Add live-regression tests for the item 376–400 StartupBell failure.

## 0.7.7 - 2026-06-24

- Replaced per-transport TikTok timeout multiplication with one shared deadline per catalog page.
- Removed nested TikTok fallback: a handle candidate no longer invokes a second stable-ID fallback ladder.
- Limited each page to at most one recovered stable ID plus the human handle.
- Remember the last successful transport and authentication mode and try it first on the next page.
- Replaced the repeatedly restarting `SYNC_HEARTBEAT` label with contextual `SYNC_WAITING` output, defaulting to 30-second intervals.
- Added `SYNC_ATTEMPT_RESULT`, per-page budget telemetry, and overall sync progress.
- Added a total TikTok sync runtime budget and optional page-count budget; exhaustion pauses cleanly with an exact-false checkpoint instead of running indefinitely.
- Added regression tests for shared deadlines, absence of nested fallback, resumable run budgets, and concise waiting telemetry.
- Preserved the v0.7.6 Instagram path, which completed 30 real Reels with zero failures.

## 0.7.6 - 2026-06-24

- Restored the proven Instagram worker-side cookie resolution path used by v0.6.x. Creator Batch no longer forces `--cookies-file` unless a human explicitly supplies an override.
- Added `--retry-failed` to the public `media2md creator run` CLI and forwards it to the Instagram engine, fixing the v0.7.5 documentation/CLI mismatch.
- Added end-to-end regression tests covering the public CLI, creator caller, worker command and optional cookie override.
- TikTok direct fallback now passes the official yt-dlp direct-connection form `--proxy ""`, in addition to ignoring config and removing proxy environment variables.
- Added safe macOS system-proxy detection that reports only enabled proxy classes, never proxy hosts or credentials.
- Recover missing TikTok secUid/user IDs from existing checkpoint media before requesting the next page.
- Persist checkpoint-discovered TikTok media as a non-exact partial catalog, so later page failures do not make the first 200 known items unusable.
- Preserve retry position and expose an explicit `--allow-stale-catalog` processing path for known TikTok items when exact enumeration remains blocked.

## 0.7.5 - 2026-06-24

- Restored the Instagram caller/worker cookie contract by adding supported `--cookies-file` handling to `process_worker.py` and passing the selected file to gallery-dl.
- Automatically requeue only items that failed because of the historical `--cookies-file` argument mismatch; unrelated failures remain untouched.
- Replaced TikTok's unbounded all-target curl-cffi sweep with at most four strategies: configured, latest Chrome, latest Safari, and direct plain.
- Added a repeated-TLS circuit breaker that skips remaining impersonation strategies after two matching TLS failures.
- Added a direct TikTok fallback that ignores user yt-dlp config and removes inherited proxy environment variables.
- Surface proxy presence without printing proxy secrets, preserve transport root causes, and prevent secUid fallback text from hiding TLS/proxy errors.
- Separated TikTok catalog page size (`MEDIA2MD_TIKTOK_SYNC_PAGE_SIZE`) from media processing batch size.
- Added regression tests for the Instagram CLI contract, installer requeue migration, bounded TikTok fallback, circuit breaking, direct proxy isolation, and sync-page sizing.

## 0.7.4 - 2026-06-24

- Fixed stale timestamp-based Python bytecode causing a successful 0.7.3 pip install to execute the old 0.7.2 CLI.
- Project wrapper now executes the installed project script directly and upgrade removes all stale `__pycache__`, `.pyc`, `.pyo`, and editable metadata before verification.
- Installation guide runs strict mode in a child subshell so a failed upgrade returns to the existing terminal instead of terminating the interactive shell.
- Added TikTok extractor heartbeat, finite per-strategy timeout, explicit interrupt telemetry, and paste-safe one-line validation commands.
- Instagram progress now distinguishes attempted, completed, and failed items and exposes each failed item root cause.
- Instagram enforces the configured max-failure threshold inside a batch and emits report/log/required-action diagnostics.
- Added regression coverage for v0.7.2→v0.7.4 stale-bytecode upgrade, shell survival, TikTok heartbeat, and Instagram all-failed batches.


## 0.7.3 - 2026-06-24

- Classify curl error 35, TLS handshake failures, `SSLError`, and `OPENSSL_internal` failures as transient TikTok network errors.
- Add deterministic TikTok transport fallback across configured impersonation, available Chrome/Safari/Edge targets, and plain yt-dlp.
- Run catalog extractors in their own process groups and terminate the full process tree on timeout or Ctrl+C.
- Preserve TikTok pagination checkpoints and stable identifiers when a later page fails.
- Print Instagram creator-run completion summaries with processed, completed, failed, and remaining counts.
- Include selected media IDs in YouTube/TikTok batch-start output and NDJSON.
- Display complete typed batch limits in creator status without truncation.
- Preserve the last exact Full Sync total and per-type YouTube totals across Quick Sync runs.
- Import Instagram catalog exact totals into the unified registry.

## 0.7.2 - 2026-06-24

- Make upgrade instructions fail fast when the downloaded source archive is missing, preventing a silent reinstall of the old local version.
- Add installer source-version and post-install CLI-version verification.
- Normalize Instagram profile and `/reels/` URLs before calling the username-only legacy creator manager.
- Preserve TikTok secUid/user ID learned on the first successful catalog page and reuse `tiktokuser:<id>` for later pages and checkpoint resume.
- Add live-regression coverage for the exact failures reported during the first v0.7.1 attempt.

## 0.7.1 - 2026-06-24

- Added YouTube multi-surface catalog sync for `/videos` and `/shorts`.
- Added media type and processing class fields, per-type creator totals, typed output folders, and duplicate-ID reconciliation.
- Added per-type batch policies with defaults: TikTok 100, Instagram Reels 30, YouTube Shorts 30, videos 5, long videos 1.
- Long YouTube videos are isolated into single-item batches; unknown durations are hydrated before selection.
- Manual Shorts now attach to the canonical channel identity and invalidate stale exact totals until the next full sync.

## 0.7.0 - 2026-06-24
- First standalone canonical package with managed runtime and persistent state.
- Clean install from wheel or source archive.
- Base package plus Instagram, YouTube, TikTok, MLX, and OpenClaw extras.
- Unified explicit browser-profile connection and verification for all three platforms.
- Live browser cookie refresh without automatic browser launch.
- Preserved YouTube caption-first, multi-strategy audio, long-video chunking, checkpoint resume, and safe artifact names.
- Secure update extraction and mandatory SHA-256 verification.
- GitHub, PyPI, Homebrew Tap, and optional npm bootstrap release scaffolding.
- Updated OpenClaw agent contract and cron instructions.
