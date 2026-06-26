# Media2MD v0.8.2 Strict Acceptance

Status legend:

- **PASS**: implemented and verified by automated or prior live validation.
- **LIVE**: implemented but still needs the specified real-account or real-network validation.
- **FIXED-LIVE**: a bug found in the latest live test has been fixed and regression-tested, but the exact live scenario must be rerun.
- **PENDING**: intentionally deferred.
- **HUMAN**: cannot be fully automated because the platform may require password, 2FA, CAPTCHA, or account challenge.

| # | Acceptance item | Status | Current evidence / remaining requirement |
|---:|---|---|---|
| 1 | Clean GitHub-ready source repository | PASS | Clean source ZIP, license, security policy, CI and release assets exist. Public push is deferred until functional RC validation is complete. |
| 2 | Base package plus optional modules | PASS | Base, Instagram, YouTube, TikTok, MLX and OpenClaw extras build successfully. |
| 3 | Agent-controlled daily operations | PASS | Status, settings, creator management, sync, batch, scheduler, auth refresh and doctor are CLI/NDJSON controllable. Sensitive or destructive operations remain gated. |
| 4 | Login support for all three platforms | LIVE | YouTube live verification passed. Instagram and TikTok browser-profile verification still require live evidence. |
| 5 | Login-state verification for all three platforms | LIVE | YouTube server probe passed. Instagram and TikTok valid/expired/revoked/challenge states still need live validation. |
| 6 | Automatic cookie refresh and re-login guidance | HUMAN | Updated browser cookies can be reread automatically. Password, 2FA, CAPTCHA and platform challenge require the user. |
| 7 | Large-scale processing across all three platforms | LIVE | YouTube processed real batches. Instagram completed 30 real Career Cleo Reels with zero failures. TikTok advanced from item 200 to item 375 but exact enumeration remains incomplete. |
| 8 | YouTube long-video split, transcribe, resume and merge | LIVE | Long-video exclusive selection and successful processing passed. The specified long video still needs selected-ID, chunk and merged-Markdown evidence. |
| 9 | OpenClaw cron scheduling | LIVE | Skill and scheduler commands exist. Real cron creation, trigger, interruption and recovery remain unverified. |
| 10 | Doctor diagnostics for all three platforms | LIVE | YouTube Doctor passed. Instagram and TikTok Doctor live checks remain. |
| 11 | GitHub Release update and rollback | PENDING | Deferred by user. |
| 12 | PyPI, npm and Homebrew publication | PENDING | Deferred by user. |
| 13 | View per-creator configuration and state | PASS | Creator status and policy show commands work. |
| 14 | View system state and settings | PASS | Status, settings, agent status, auth and doctor outputs exist. |
| 15 | Human and agent can modify public settings | PASS | Typed batch policies and public settings are editable through CLI. |
| 16 | Process a single YouTube Shorts URL | LIVE | Old pipeline completed the fixture. v0.7.7 classified folder/frontmatter output still needs live evidence. |
| 17 | Single Short links to the correct creator | LIVE | Channel-ID merge is implemented; live v0.7.7 duplicate-creator check remains. |
| 18 | YouTube creator sync includes Videos and Shorts | PASS | Live Full Sync found 267 videos and 210 Shorts, total 477. |
| 19 | Separate exact Video and Shorts totals | PASS | Live Full Sync returned exact per-surface totals. |
| 20 | Upload/delete changes update totals | LIVE | Full/Quick semantics work, but an actual upload/delete transition has not been observed. |
| 21 | TikTok creator exact total | FIXED-LIVE | Live v0.7.6 progressed from 200 to 375 items, proving pagination works, but the invocation was impractically long. v0.7.7 adds page and run budgets; exact completion still needs live evidence. |
| 22 | Instagram exact Reel total | PASS | Live status reports `all:85`, `current=true`, and `last_full_total=85`. This validates catalog exactness, not media processing success. |
| 23 | Different batch limits per platform/creator | PASS | TikTok 100, Instagram 30 and YouTube typed limits were accepted. |
| 24 | Typed limits within one YouTube creator | PASS | Short 30, normal video 5 and long video 1 policies are active. |
| 25 | YouTube long videos occupy a one-item batch | PASS | Live output showed `composition={"youtube_long": 1}`. |
| 26 | YouTube classified output folders/frontmatter | LIVE | Implementation exists. File path and frontmatter evidence still required. |
| 27 | Manual Short keeps creator totals consistent | LIVE | Automated regression passes; live v0.7.7 Short re-add/status evidence remains. |
| 28 | Quick/Full exactness transition | PASS | Live Full Sync was exact and Quick Sync correctly became non-exact. |
| 29 | Fixed live fixture set | LIVE | YouTube catalog passed. Instagram completed a 30-item real batch. TikTok reached 375 known items and now requires bounded resume to the final short page. |
| 30 | Fail-fast missing archive protection without killing the interactive shell | PASS | Strict mode now runs inside a child subshell; missing archive/installer returns a non-zero code and the parent prompt survives. |
| 31 | Installer verifies actual installed version | PASS | Installer clears stale bytecode and verifies package version, project script version, and final `media2md 0.8.1`. |
| 32 | TikTok stable identity survives pagination | PASS | Live v0.7.6 output recovered one identity from checkpoint items and successfully advanced from item 201 through item 375. |
| 33 | Instagram `/reels/` URL normalization | PASS | Live add succeeded for the full Career Cleo URL. |
| 34 | TikTok curl error 35 / TLS is classified correctly | PASS | Live v0.7.4 output proved TLS/curl 35 and curl 56 are detected. v0.7.7 prevents this class from triggering an unbounded target sweep. |
| 35 | TikTok transport fallback | PASS | Live v0.7.6 output exercised configured Chrome, latest Chrome/Safari, circuit breaking, and direct-plain; multiple pages completed. |
| 36 | TikTok extractor process-tree cleanup | PASS | Live v0.7.6 Ctrl+C produced `MEDIA2MD_INTERRUPTED` and returned to the shell while preserving the checkpoint. |
| 37 | TikTok failure returns control to shell | PASS | Live v0.7.6 interrupt returned control to the active shell immediately after `MEDIA2MD_INTERRUPTED`. |
| 38 | TikTok page-3 checkpoint is preserved on failure | PASS | Regression confirms `next_start=201` is not advanced or deleted. v0.7.7 can also import the already discovered items as a non-exact partial catalog. |
| 39 | TikTok retry/fallback telemetry | FIXED-LIVE | v0.7.6 telemetry exposed progress but restarted elapsed counters for every subprocess and flooded the terminal. v0.7.7 replaces it with contextual waiting, attempt-result, page-budget, and run-progress events. |
| 40 | Instagram human-mode completion summary | PASS | Live output exposed `processed=30 completed=0 failures=30 remaining=85`, proving the summary works and revealing a separate processing failure. |
| 41 | Instagram unified status imports exact catalog total | PASS | Live status shows `all:85`, `EXACT current=true`, `last_full_total=85`, and a Full Sync timestamp. |
| 42 | YouTube batch identifies selected media IDs | PASS | Live output identified `selected_media_ids=["-oE_7kDGkZA"]`. The separately specified fixture still needs chunk/merge evidence. |
| 43 | Creator status does not truncate typed batch limits | PASS | Live YouTube and Instagram status printed the complete `BATCH_LIMITS` line. |
| 44 | Preserve last exact Full Sync snapshot across Quick Sync | PASS | Schema stores last exact total/time and YouTube per-type totals; automated Full→Quick regression passes. |
| 45 | Current and last-exact semantics are visible together | FIXED-LIVE | `creator status` prints current exactness plus last Full exact total/time. Live output required. |
| 46 | No checkpoint regression after transient retry exhaustion | PASS | Failed pages do not advance or remove the checkpoint. |
| 47 | No silent infinite retry | PASS | Live v0.7.7 output proved one 300-second page deadline, explicit attempt outcomes, checkpoint preservation, and a return to the shell. |
| 48 | Release contains no cookies, creator data, workspaces or backups | PASS | Release construction excludes mutable state and compiled caches. |
| 49 | Upgrade removes stale Python bytecode | PASS | Regression reproduces the v0.7.2→v0.7.3 stale `.pyc` failure and confirms v0.7.7 purges caches before and after install. |
| 50 | Project CLI cannot execute an older cached package launcher | PASS | `./bin/media2md` directly executes `scripts/media2md.py` with `-B`; package/script/CLI versions must agree. |
| 51 | Installer failure leaves the current terminal usable | PASS | Upgrade is documented and tested in a child subshell; parent shell prints the exit code and remains interactive. |
| 52 | TikTok quiet-period telemetry is understandable | PASS | Live v0.7.7 output used contextual `SYNC_WAITING` with range, candidate, strategy, auth mode, elapsed time, PID, and timeout. |
| 53 | TikTok page and extractor attempts have finite deadlines | PASS | Live v0.7.7 output showed per-attempt limits shrinking to the remaining shared 300-second page budget. |
| 54 | TikTok validation commands are paste-safe | PASS | Current guide uses single-line commands and never leaves a trailing backslash on the final argument. |
| 55 | Instagram progress distinguishes attempts, successes and failures | PASS | Live output showed attempted 3, completed 0 and failed 3 without presenting 100% attempted as success. |
| 56 | Instagram failed items expose a root cause immediately | PASS | Live output exposed the exact `--cookies-file` parser mismatch for each shortcode. |
| 57 | Instagram max-failure policy is enforced inside the batch | PASS | The worker stops the batch when the configured threshold is reached instead of attempting all remaining items. |
| 58 | Instagram all-failed batches cannot look successful | PASS | Completion status becomes `completed_with_errors`, returns exit code 2, and reports completed/failed separately. |
| 59 | Instagram failure report and engine log are surfaced | PASS | Live output printed report path, engine log, failure examples and required action. |
| 60 | Progress percentage is not interpreted as success percentage | PASS | Acceptance now requires attempted, completed and failed counts; 100% attempted with 0 completed is explicitly a failure. |
| 61 | Legacy exact snapshot is not fabricated | PASS | If no prior exact-snapshot field exists, status remains unknown until the next real Full Sync; v0.7.7 does not invent historical certainty. |
| 62 | Instagram cookie path preserves the proven default | PASS | Live v0.7.6 processed 30/30 Career Cleo Reels after restoring worker-side managed-file/browser fallback. |
| 63 | Known Instagram contract failures are safely requeued | PASS | Installer resets only rows whose stored error is the obsolete `--cookies-file` parser rejection; unrelated failures remain unchanged. |
| 64 | TikTok fallback strategy count is bounded | PASS | Automated test confirms no more than four strategies and excludes the v0.7.4 all-target sweep. |
| 65 | Repeated TikTok TLS failures open a circuit breaker | PASS | Two matching TLS failures skip remaining impersonation targets and continue directly to the plain isolated strategy. |
| 66 | TikTok direct fallback ignores hidden proxy configuration | FIXED-LIVE | Direct mode now combines `--ignore-config`, cleared proxy environment variables, and the official `--proxy ""` direct-connection option. Live validation remains. |
| 67 | TikTok transport root cause is not hidden by secUid fallback text | PASS | TLS/proxy signatures now bypass the secondary-user-ID wrapper and remain the reported root cause. |
| 68 | TikTok catalog page size is separate from processing batch size | PASS | `MEDIA2MD_TIKTOK_SYNC_PAGE_SIZE` controls catalog pagination only; typed `tiktok_video` controls later processing. |
| 69 | Reducing processing batch does not claim to fix catalog transport | PASS | Documentation and status semantics distinguish sync-page size, media batch size and network transport failures. |
| 70 | Public `media2md creator run` accepts `--retry-failed` | PASS | Parser and forwarding regression tests cover the exact command that v0.7.5 documentation advertised but the public CLI rejected. |
| 71 | Instagram default Batch does not force a cross-script cookie argument | PASS | Worker command omits `--cookies-file` by default and restores worker-side managed-file/browser fallback; explicit overrides remain tested. |
| 72 | One real Career Cleo Reel completes through the full public CLI | PASS | Live v0.7.6 run completed 30 of 30 Career Cleo Reels with zero failures and produced a completion report. |
| 73 | TikTok direct mode explicitly disables OS/system proxy | PASS | Live output reported `direct_strategy_forces_proxy_empty=true`, and a direct-plain attempt completed page 11 despite enabled macOS proxy classes. |
| 74 | macOS system proxy presence is visible without leaking secrets | PASS | Live output reported `macos_system_proxy=http,https,socks` without exposing endpoints or credentials. |
| 75 | Old TikTok checkpoint can recover a stable identity from cached media | PASS | Live output showed `SYNC_IDENTITY_RECOVERY recovered=1 source=checkpoint_items` before resuming item 201. |
| 76 | TikTok partial catalog survives exact-sync failure and is explicitly usable | PASS | Live output showed `SYNC_PARTIAL_CATALOG_SAVED known_items=200 exact=false next_start=201`; later completed pages advanced the checkpoint without losing prior items. |
| 77 | One shared deadline per TikTok page | PASS | Live v0.7.7 output showed one `SYNC_PAGE_BUDGET` and later attempts receiving only the remaining 44/64 seconds. |
| 78 | No nested TikTok fallback ladder | PASS | `_extract_tiktok_page` calls the low-level extractor directly for at most one stable ID and one handle candidate; the handle path cannot invoke another identifier fallback. |
| 79 | Last successful TikTok strategy is reused first | FIXED-LIVE | v0.7.8 reused the hint only within one process. v0.7.9 persists `preferred_transport` and `preferred_authenticated` in the checkpoint and reloads them on the next CLI invocation. |
| 80 | TikTok full-sync invocation has a total runtime budget | FIXED-LIVE | `MEDIA2MD_TIKTOK_SYNC_MAX_RUNTIME_SECONDS` defaults to 1800 seconds. Reaching it pauses cleanly with a saved checkpoint. |
| 81 | TikTok sync can limit pages per invocation | PASS | `MEDIA2MD_TIKTOK_SYNC_MAX_PAGES_PER_RUN` provides a deterministic cap for manual or agent runs; zero means unlimited within the runtime budget. |
| 82 | Budget exhaustion pauses instead of failing or running forever | PASS | Live v0.7.8 stopped after 304 seconds, preserved 475 items, returned `SYNC_RUN_PAUSED reason=page_budget_exhausted`, and returned to the shell. |
| 83 | TikTok attempt outcomes are explicit | PASS | Live v0.7.7 output showed success, timeout and elapsed seconds for every transport attempt. |
| 84 | TikTok run progress is visible across pages | PASS | Live v0.7.8 advanced 375→475 across four pages and printed `SYNC_RUN_PROGRESS` after every completed page. |

| 85 | Stable-ID catalog payload may reuse the already-known human handle | PASS | Live v0.7.8 repeatedly printed `SYNC_STABLE_ID_HANDLE_REUSED handle=startupbell` and completed pages 376–475. |
| 86 | Stable-ID success must not trigger a second handle-profile fetch | PASS | Live v0.7.8 showed `second_profile_fetch=false` followed directly by `SYNC_PAGE_DONE` for four pages. |
| 87 | Page-budget exhaustion returns a resumable partial result, not a hard error | PASS | Live v0.7.8 preserved 475 items, kept `resume_from=476`, returned a partial JSON summary, and did not end with a hard error. |
| 88 | Clean pause cannot advance or truncate the checkpoint | PASS | Regression test verifies `next_start` and cached items remain unchanged when a page deadline expires. |
| 89 | TikTok stable-ID metadata fallback does not spend the remaining page budget on duplicate discovery | PASS | Regression test reproduces a handle-less stable payload and confirms only one extractor invocation occurs. |

| 90 | Successful TikTok transport persists across CLI invocations | FIXED-LIVE | v0.7.9 stores `preferred_transport` and `preferred_authenticated` in checkpoint schema 4 and reloads them before the next page. |
| 91 | TikTok page-wide circuit breaker | PASS | Regression confirms stable-ID TLS failures keep the breaker open when the handle candidate starts, preventing a second impersonation ladder. |
| 92 | No extractor starts when remaining page budget is below five seconds | PASS | Regression verifies the subprocess is not launched and the page pauses immediately. |
| 93 | Page deadline cannot be extended by a forced five-second minimum | PASS | v0.7.9 removes the `max(5, ...)` overrun that produced a 304-second run from a 300-second page budget. |
| 94 | `creator_identifiers.sec_uid` remains visible in paused summaries | PASS | Stable identifiers are merged into TikTok metadata before partial/full upsert and exposed in the JSON summary. |
| 95 | Maximum-page pause reason is semantically correct | PASS | Reaching `MEDIA2MD_TIKTOK_SYNC_MAX_PAGES_PER_RUN` now reports `max_pages_per_run`, not `page_budget`. |
| 96 | v0.7.9 does not change live-passing Instagram or YouTube paths | PASS | The patch is isolated to TikTok checkpoint strategy memory, page state, deadline handling, identity metadata, and pause labeling. |
| 97 | Old checkpoints under enabled macOS proxies prefer isolated direct transport | PASS | With no persisted hint, v0.7.9 selects `direct-plain` first when macOS reports HTTP/HTTPS/SOCKS proxy classes; the first real success then replaces this bootstrap hint in checkpoint. |

## v0.8.0 cursor-pagination acceptance additions

| # | Requirement | Status | Evidence |
|---:|---|---|---|
| 98 | Resumed TikTok sync must not use `--playlist-start` as the primary deep-pagination mechanism | PASS | v0.8.1 routes checkpoints with a valid secUid to the cursor API backend; regression fails if `_extract_tiktok_page` is invoked. |
| 99 | TikTok cursor is recovered from the oldest known checkpoint item | PASS | ISO timestamps from schema 3/4 checkpoints are converted to the millisecond cursor used by the official TikTok user extractor. |
| 100 | TikTok cursor and device ID persist across CLI invocations | PASS | Checkpoint schema 5 stores `tiktok_cursor`, `tiktok_device_id`, and `pagination_backend=cursor_api`. |
| 101 | One cursor response is normalized and checkpointed before the next request | PASS | `SYNC_CURSOR_PAGE_DONE` is emitted only after atomic checkpoint persistence and partial-registry upsert. |
| 102 | Cursor backend bypasses macOS system proxy | PASS | Native curl uses `--noproxy *` and a proxy-cleared environment; unit test inspects the exact command. |
| 103 | Cursor API completion establishes an exact TikTok total | FIXED-LIVE | `hasMorePrevious=false` removes the checkpoint, writes a Full Sync, and emits `SYNC_CURSOR_COMPLETE`; live StartupBell validation remains. |
| 104 | Cursor request failure returns a resumable partial result | PASS | Failure keeps the previous cursor/items, emits `SYNC_RUN_PAUSED reason=cursor_request_failed`, and returns to the shell. |
| 105 | Legacy bounded yt-dlp paging remains a fallback, not the default resume engine | PASS | New/identity-less creators can still bootstrap through the bounded extractor, while known secUid checkpoints switch to cursor mode. |

## v0.8.1 Batch transport and reporting additions

| # | Requirement | Status | Evidence |
|---:|---|---|---|
| 106 | Cursor summary preserves the command-start total | PASS | Unit regression forces 655→715 and requires `previous_current_total=655`. |
| 107 | Cursor run delta is accurate | PASS | `new_since_last_sync` is computed from the command-start snapshot, not the post-upsert Registry. |
| 108 | Every native cursor attempt emits a result | PASS | Public failure and authenticated success both emit `SYNC_CURSOR_ATTEMPT_RESULT` with a reason and elapsed time. |
| 109 | Partial TikTok Full Sync skips legacy Quick Sync before Batch | FAIL | Live v0.8.1 public `./bin/media2md creator run` still executed a legacy Quick Sync because only `social2md.py` was patched; fixed by the shared public-CLI implementation in v0.8.2. |
| 110 | TikTok media download tries isolated direct transport first under macOS proxies | PASS | Download-cascade test requires `--ignore-config --proxy ""` and succeeds without invoking impersonation. |
| 111 | TikTok media-download transport success persists across items/runs | PASS | Separate state records strategy plus auth mode; no cookies or proxy credentials are stored. |
| 112 | TikTok per-item transport cascade is bounded | PASS | `MEDIA2MD_TIKTOK_DOWNLOAD_ITEM_BUDGET_SECONDS` and per-attempt timeout prevent one item from running indefinitely. |
| 113 | Transport fallback does not count as an item failure | PASS | Item failure is raised only after all bounded strategies are exhausted. |
| 114 | Early max-failure stop prints a final summary | PASS | `CREATOR_RUN_COMPLETED status=stopped_max_failures` includes processed/completed/failures/remaining. |
| 115 | Stored TikTok identities survive Quick/Partial summaries | PASS | `sec_uid` and `user_id` are merged from the Registry when incoming metadata omits them. |
| 116 | v0.8.1 does not replace the v0.8.0 cursor Catalog engine | PASS | Cursor checkpoint schema, native curl backend, and exact-completion logic are unchanged. |
| 117 | Source, wheel, and release kit contain no bundled runtime database | PASS | `src/media2md/bundle/data` is excluded and the inherited empty `media2md.db` fixture was removed. |

## Required live rerun before v0.8.1 can be called functionally complete

1. Upgrade and confirm package, script, and project CLI all report `0.8.1`.
2. Resume one four-page Cursor run and verify `previous_current_total`, `current_total`, and `new_since_last_sync` reflect the actual 60-item delta.
3. Capture a public Cursor failure followed by authenticated success and verify both attempts have result events.
4. Run a five-item TikTok Batch while Full Sync is partial and verify `AUTO_SYNC_SKIPPED` appears before `BATCH_START`.
5. Verify each TikTok media item shows bounded `TIKTOK_DOWNLOAD_ATTEMPT_RESULT` events and that a fallback success does not increment item failures.
6. Verify `CREATOR_RUN_COMPLETED` is printed even when `--max-failures 1` stops the run.
7. Continue Cursor Full Sync until `SYNC_CURSOR_COMPLETE ... exact=true`.
8. Validate five then twenty TikTok media items, followed by Doctor, status, and final artifact/frontmatter checks.


## v0.8.2 public Creator Run convergence additions

| # | Requirement | Status | Evidence |
|---:|---|---|---|
| 118 | Both public Creator Run surfaces use a single shared implementation | PASS | `media2md.py` and `social2md.py` both call `prepare_catalog_for_creator_run`; duplicated partial-catalog branching is forbidden by regression. |
| 119 | The real public `./bin/media2md` skips Quick Sync for a partial TikTok cursor Catalog | FIXED-LIVE | A subprocess test executes the shipped entrypoint against a partial Registry and requires `AUTO_SYNC_SKIPPED`; StartupBell live rerun remains required. |
| 120 | Public CLI regression cannot silently invoke Registry sync | PASS | The fake Registry exits 91 and prints `LEGACY_QUICK_SYNC_CALLED` if `sync` is invoked; the shipped entrypoint test must still complete Batch with exit 0. |
| 121 | Batch starts without legacy transport telemetry | PASS | Public CLI subprocess test rejects `SYNC_NETWORK_CONTEXT`, `SYNC_TRANSPORT_ATTEMPT`, and `sync_mode=quick` before `BATCH_START`. |
| 122 | Historical false-green acceptance is corrected | PASS | v0.8.1 requirement 109 is recorded as FAIL with the exact live public-CLI cause instead of retaining the unit-only PASS. |
| 123 | Live-passing Cursor and media-download engines remain unchanged | PASS | v0.8.2 changes only the shared Creator Run pre-sync decision, tests, versioning, and release documentation. |
| 124 | v0.8.2 requires a public CLI live rerun | FIXED-LIVE | Run five TikTok items while Full Sync is partial and confirm `AUTO_SYNC_SKIPPED` immediately precedes Batch without legacy Quick Sync output. |
