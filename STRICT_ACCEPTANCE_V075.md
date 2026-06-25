# Media2MD v0.7.5 Strict Acceptance

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
| 7 | Large-scale processing across all three platforms | LIVE | YouTube processed real batches. Instagram processing was blocked by a caller/worker cookie argument mismatch and is fixed for live rerun. TikTok catalog must complete beyond item 200 before its large-batch run. |
| 8 | YouTube long-video split, transcribe, resume and merge | LIVE | Long-video exclusive selection and successful processing passed. The specified long video still needs selected-ID, chunk and merged-Markdown evidence. |
| 9 | OpenClaw cron scheduling | LIVE | Skill and scheduler commands exist. Real cron creation, trigger, interruption and recovery remain unverified. |
| 10 | Doctor diagnostics for all three platforms | LIVE | YouTube Doctor passed. Instagram and TikTok Doctor live checks remain. |
| 11 | GitHub Release update and rollback | PENDING | Deferred by user. |
| 12 | PyPI, npm and Homebrew publication | PENDING | Deferred by user. |
| 13 | View per-creator configuration and state | PASS | Creator status and policy show commands work. |
| 14 | View system state and settings | PASS | Status, settings, agent status, auth and doctor outputs exist. |
| 15 | Human and agent can modify public settings | PASS | Typed batch policies and public settings are editable through CLI. |
| 16 | Process a single YouTube Shorts URL | LIVE | Old pipeline completed the fixture. v0.7.5 classified folder/frontmatter output still needs live evidence. |
| 17 | Single Short links to the correct creator | LIVE | Channel-ID merge is implemented; live v0.7.5 duplicate-creator check remains. |
| 18 | YouTube creator sync includes Videos and Shorts | PASS | Live Full Sync found 267 videos and 210 Shorts, total 477. |
| 19 | Separate exact Video and Shorts totals | PASS | Live Full Sync returned exact per-surface totals. |
| 20 | Upload/delete changes update totals | LIVE | Full/Quick semantics work, but an actual upload/delete transition has not been observed. |
| 21 | TikTok creator exact total | FIXED-LIVE | Stable-ID resume reached page 3. v0.7.4 proved the network fault is TLS/proxy-related; v0.7.5 bounded fallback and direct isolation now require a live completion. |
| 22 | Instagram exact Reel total | PASS | Live status reports `all:85`, `current=true`, and `last_full_total=85`. This validates catalog exactness, not media processing success. |
| 23 | Different batch limits per platform/creator | PASS | TikTok 100, Instagram 30 and YouTube typed limits were accepted. |
| 24 | Typed limits within one YouTube creator | PASS | Short 30, normal video 5 and long video 1 policies are active. |
| 25 | YouTube long videos occupy a one-item batch | PASS | Live output showed `composition={"youtube_long": 1}`. |
| 26 | YouTube classified output folders/frontmatter | LIVE | Implementation exists. File path and frontmatter evidence still required. |
| 27 | Manual Short keeps creator totals consistent | LIVE | Automated regression passes; live v0.7.5 Short re-add/status evidence remains. |
| 28 | Quick/Full exactness transition | PASS | Live Full Sync was exact and Quick Sync correctly became non-exact. |
| 29 | Fixed live fixture set | LIVE | YouTube catalog passed, Instagram mostly passed, TikTok remains blocked by network transport validation. |
| 30 | Fail-fast missing archive protection without killing the interactive shell | PASS | Strict mode now runs inside a child subshell; missing archive/installer returns a non-zero code and the parent prompt survives. |
| 31 | Installer verifies actual installed version | PASS | Installer clears stale bytecode and verifies package version, project script version, and final `media2md 0.7.5`. |
| 32 | TikTok stable identity survives pagination | PASS | Resume started directly at page 3 without losing secUid/user ID. |
| 33 | Instagram `/reels/` URL normalization | PASS | Live add succeeded for the full Career Cleo URL. |
| 34 | TikTok curl error 35 / TLS is classified correctly | PASS | Live v0.7.4 output proved TLS/curl 35 and curl 56 are detected. v0.7.5 prevents this class from triggering an unbounded target sweep. |
| 35 | TikTok transport fallback | FIXED-LIVE | v0.7.5 caps fallback at four strategies: configured, latest Chrome, latest Safari and direct plain. Live direct-fallback evidence remains. |
| 36 | TikTok extractor process-tree cleanup | FIXED-LIVE | Catalog extraction now runs in a new process group with SIGINT, SIGTERM and SIGKILL escalation. Live Ctrl+C required. |
| 37 | TikTok failure returns control to shell | FIXED-LIVE | Exhausted strategies return exit code 2; interrupt returns 130. Live terminal confirmation required. |
| 38 | TikTok page-3 checkpoint is preserved on failure | PASS | Regression test confirms `next_start=201` and stable identifiers remain. Do not delete the checkpoint before retest. |
| 39 | TikTok retry/fallback telemetry | PASS | Live v0.7.4 output showed heartbeats and transport attempts. v0.7.5 additionally reports network context, circuit opening and skipped strategies. |
| 40 | Instagram human-mode completion summary | PASS | Live output exposed `processed=30 completed=0 failures=30 remaining=85`, proving the summary works and revealing a separate processing failure. |
| 41 | Instagram unified status imports exact catalog total | PASS | Live status shows `all:85`, `EXACT current=true`, `last_full_total=85`, and a Full Sync timestamp. |
| 42 | YouTube batch identifies selected media IDs | PASS | Live output identified `selected_media_ids=["-oE_7kDGkZA"]`. The separately specified fixture still needs chunk/merge evidence. |
| 43 | Creator status does not truncate typed batch limits | PASS | Live YouTube and Instagram status printed the complete `BATCH_LIMITS` line. |
| 44 | Preserve last exact Full Sync snapshot across Quick Sync | PASS | Schema stores last exact total/time and YouTube per-type totals; automated Full→Quick regression passes. |
| 45 | Current and last-exact semantics are visible together | FIXED-LIVE | `creator status` prints current exactness plus last Full exact total/time. Live output required. |
| 46 | No checkpoint regression after transient retry exhaustion | PASS | Failed pages do not advance or remove the checkpoint. |
| 47 | No silent infinite retry | PASS | Retry attempts are finite; v0.7.5 also caps the complete TikTok transport plan at four strategies. |
| 48 | Release contains no cookies, creator data, workspaces or backups | PASS | Release construction excludes mutable state and compiled caches. |
| 49 | Upgrade removes stale Python bytecode | PASS | Regression reproduces the v0.7.2→v0.7.3 stale `.pyc` failure and confirms v0.7.5 purges caches before and after install. |
| 50 | Project CLI cannot execute an older cached package launcher | PASS | `./bin/media2md` directly executes `scripts/media2md.py` with `-B`; package/script/CLI versions must agree. |
| 51 | Installer failure leaves the current terminal usable | PASS | Upgrade is documented and tested in a child subshell; parent shell prints the exit code and remains interactive. |
| 52 | TikTok sync emits a heartbeat while yt-dlp is quiet | PASS | Live `@startupbell` output repeatedly showed strategy, auth mode, elapsed time, PID and timeout. |
| 53 | TikTok extractor attempts have a finite timeout | PASS | Per-strategy timeout defaults to 300 seconds and is configurable with `MEDIA2MD_TIKTOK_EXTRACT_TIMEOUT_SECONDS`. |
| 54 | TikTok validation commands are paste-safe | PASS | Current guide uses single-line commands and never leaves a trailing backslash on the final argument. |
| 55 | Instagram progress distinguishes attempts, successes and failures | PASS | Live output showed attempted 3, completed 0 and failed 3 without presenting 100% attempted as success. |
| 56 | Instagram failed items expose a root cause immediately | PASS | Live output exposed the exact `--cookies-file` parser mismatch for each shortcode. |
| 57 | Instagram max-failure policy is enforced inside the batch | PASS | The worker stops the batch when the configured threshold is reached instead of attempting all remaining items. |
| 58 | Instagram all-failed batches cannot look successful | PASS | Completion status becomes `completed_with_errors`, returns exit code 2, and reports completed/failed separately. |
| 59 | Instagram failure report and engine log are surfaced | PASS | Live output printed report path, engine log, failure examples and required action. |
| 60 | Progress percentage is not interpreted as success percentage | PASS | Acceptance now requires attempted, completed and failed counts; 100% attempted with 0 completed is explicitly a failure. |
| 61 | Legacy exact snapshot is not fabricated | PASS | If no prior exact-snapshot field exists, status remains unknown until the next real Full Sync; v0.7.5 does not invent historical certainty. |
| 62 | Instagram caller and worker share the `--cookies-file` contract | FIXED-LIVE | Parser, caller and gallery-dl path are now aligned and regression-tested. One real Reel must complete after upgrade. |
| 63 | Known Instagram contract failures are safely requeued | PASS | Installer resets only rows whose stored error is the obsolete `--cookies-file` parser rejection; unrelated failures remain unchanged. |
| 64 | TikTok fallback strategy count is bounded | PASS | Automated test confirms no more than four strategies and excludes the v0.7.4 all-target sweep. |
| 65 | Repeated TikTok TLS failures open a circuit breaker | PASS | Two matching TLS failures skip remaining impersonation targets and continue directly to the plain isolated strategy. |
| 66 | TikTok direct fallback ignores hidden proxy configuration | FIXED-LIVE | Direct mode adds `--ignore-config` and removes inherited proxy environment variables. Live network validation remains. |
| 67 | TikTok transport root cause is not hidden by secUid fallback text | PASS | TLS/proxy signatures now bypass the secondary-user-ID wrapper and remain the reported root cause. |
| 68 | TikTok catalog page size is separate from processing batch size | PASS | `MEDIA2MD_TIKTOK_SYNC_PAGE_SIZE` controls catalog pagination only; typed `tiktok_video` controls later processing. |
| 69 | Reducing processing batch does not claim to fix catalog transport | PASS | Documentation and status semantics distinguish sync-page size, media batch size and network transport failures. |

## Required live rerun before v0.7.5 can be called functionally complete

1. Upgrade and confirm the installer prints `instagram_contract_regression_items_requeued=`. Zero is valid when the affected rows were already left in `pending`; matching stored `retry_wait/failed` rows must be requeued.
2. Run one Career Cleo Reel with `--max-failures 1 --retry-failed`. Confirm `COOKIE_SOURCE`, `STAGE downloading`, and at least one completed Markdown artifact.
3. Run `@startupbell` with `MEDIA2MD_TIKTOK_SYNC_PAGE_SIZE=25`. Confirm `strategy_count<=4`, circuit-breaker behavior when TLS repeats, and a direct-plain attempt without proxy leakage.
4. Press Ctrl+C during a TikTok extraction and confirm return code 130 with the page-3 checkpoint intact.
5. Run one The Product Folks batch and confirm full `BATCH_LIMITS`, `EXACT`, and `selected_media_ids`.
6. Confirm the specified long video creates multiple chunks and one merged Markdown artifact.
7. Confirm a v0.7.5 single Short lands under `shorts/`, contains `media_type: youtube_short`, and links to the existing creator.
8. Complete Instagram and TikTok auth verify/Doctor tests.
9. Complete a real OpenClaw cron trigger.
