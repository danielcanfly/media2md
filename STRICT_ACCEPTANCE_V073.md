# Media2MD v0.7.3 Strict Acceptance

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
| 7 | Large-scale processing across all three platforms | LIVE | YouTube and Instagram processed real batches. TikTok catalog must complete beyond item 200 before its large-batch run. |
| 8 | YouTube long-video split, transcribe, resume and merge | LIVE | Long-video exclusive selection and successful processing passed. The specified long video still needs selected-ID, chunk and merged-Markdown evidence. |
| 9 | OpenClaw cron scheduling | LIVE | Skill and scheduler commands exist. Real cron creation, trigger, interruption and recovery remain unverified. |
| 10 | Doctor diagnostics for all three platforms | LIVE | YouTube Doctor passed. Instagram and TikTok Doctor live checks remain. |
| 11 | GitHub Release update and rollback | PENDING | Deferred by user. |
| 12 | PyPI, npm and Homebrew publication | PENDING | Deferred by user. |
| 13 | View per-creator configuration and state | PASS | Creator status and policy show commands work. |
| 14 | View system state and settings | PASS | Status, settings, agent status, auth and doctor outputs exist. |
| 15 | Human and agent can modify public settings | PASS | Typed batch policies and public settings are editable through CLI. |
| 16 | Process a single YouTube Shorts URL | LIVE | Old pipeline completed the fixture. v0.7.3 classified folder/frontmatter output still needs live evidence. |
| 17 | Single Short links to the correct creator | LIVE | Channel-ID merge is implemented; live v0.7.3 duplicate-creator check remains. |
| 18 | YouTube creator sync includes Videos and Shorts | PASS | Live Full Sync found 267 videos and 210 Shorts, total 477. |
| 19 | Separate exact Video and Shorts totals | PASS | Live Full Sync returned exact per-surface totals. |
| 20 | Upload/delete changes update totals | LIVE | Full/Quick semantics work, but an actual upload/delete transition has not been observed. |
| 21 | TikTok creator exact total | FIXED-LIVE | Stable-ID resume reached page 3. TLS transport fix must now complete `@startupbell`. |
| 22 | Instagram exact Reel total | FIXED-LIVE | 85 items were discovered and 30 processed. v0.7.3 now imports catalog exactness into unified status; rerun status. |
| 23 | Different batch limits per platform/creator | PASS | TikTok 100, Instagram 30 and YouTube typed limits were accepted. |
| 24 | Typed limits within one YouTube creator | PASS | Short 30, normal video 5 and long video 1 policies are active. |
| 25 | YouTube long videos occupy a one-item batch | PASS | Live output showed `composition={"youtube_long": 1}`. |
| 26 | YouTube classified output folders/frontmatter | LIVE | Implementation exists. File path and frontmatter evidence still required. |
| 27 | Manual Short keeps creator totals consistent | LIVE | Automated regression passes; live v0.7.3 Short re-add/status evidence remains. |
| 28 | Quick/Full exactness transition | PASS | Live Full Sync was exact and Quick Sync correctly became non-exact. |
| 29 | Fixed live fixture set | LIVE | YouTube catalog passed, Instagram mostly passed, TikTok remains blocked by network transport validation. |
| 30 | Fail-fast missing archive protection | PASS | Installer guide uses `set -euo pipefail` and verifies archive/installer. |
| 31 | Installer verifies actual installed version | PASS | Installer verifies source version and final `media2md 0.7.3`. |
| 32 | TikTok stable identity survives pagination | PASS | Resume started directly at page 3 without losing secUid/user ID. |
| 33 | Instagram `/reels/` URL normalization | PASS | Live add succeeded for the full Career Cleo URL. |
| 34 | TikTok curl error 35 / TLS is retryable | FIXED-LIVE | TLS, SSL and OpenSSL error signatures are now transient and use 10/30/90 retry on the primary strategy. |
| 35 | TikTok transport fallback | FIXED-LIVE | Configured impersonation, available Chrome/Safari/Edge targets and plain yt-dlp are tried deterministically. Live fallback evidence required. |
| 36 | TikTok extractor process-tree cleanup | FIXED-LIVE | Catalog extraction now runs in a new process group with SIGINT, SIGTERM and SIGKILL escalation. Live Ctrl+C required. |
| 37 | TikTok failure returns control to shell | FIXED-LIVE | Exhausted strategies return exit code 2; interrupt returns 130. Live terminal confirmation required. |
| 38 | TikTok page-3 checkpoint is preserved on failure | PASS | Regression test confirms `next_start=201` and stable identifiers remain. Do not delete the checkpoint before retest. |
| 39 | TikTok retry/fallback telemetry | FIXED-LIVE | `SYNC_RETRY` and `SYNC_TRANSPORT_ATTEMPT` identify delay, strategy and auth usage. Live output required. |
| 40 | Instagram human-mode completion summary | FIXED-LIVE | v0.7.3 prints batches, processed, completed, failures and remaining. Live rerun required. |
| 41 | Instagram unified status imports exact catalog total | FIXED-LIVE | Registry refresh now reads `creator_catalogs/<creator>.json` exactness and last Full Sync snapshot. Live status required. |
| 42 | YouTube batch identifies selected media IDs | FIXED-LIVE | Human and NDJSON batch-start events include `selected_media_ids`. Live long-video rerun required. |
| 43 | Creator status does not truncate typed batch limits | FIXED-LIVE | Full `BATCH_LIMITS` is printed on a separate line. Live status required. |
| 44 | Preserve last exact Full Sync snapshot across Quick Sync | PASS | Schema stores last exact total/time and YouTube per-type totals; automated Full→Quick regression passes. |
| 45 | Current and last-exact semantics are visible together | FIXED-LIVE | `creator status` prints current exactness plus last Full exact total/time. Live output required. |
| 46 | No checkpoint regression after transient retry exhaustion | PASS | Failed pages do not advance or remove the checkpoint. |
| 47 | No silent infinite retry | PASS | Retry attempts and transport strategies are finite and return an explicit exit code. |
| 48 | Release contains no cookies, creator data, workspaces or backups | PASS | Release construction excludes mutable state and compiled caches. |

## Required live rerun before v0.7.3 can be called functionally complete

1. Resume `@startupbell` from page 3 and confirm either successful fallback or a clean exit.
2. Press Ctrl+C during a TikTok extraction and confirm return code 130 with checkpoint intact.
3. Run another 30-item Career Cleo batch and confirm the completion summary and exact status.
4. Run one The Product Folks batch and confirm full `BATCH_LIMITS`, `EXACT`, and `selected_media_ids`.
5. Confirm the specified long video creates multiple chunks and one merged Markdown artifact.
6. Confirm a v0.7.3 single Short lands under `shorts/`, contains `media_type: youtube_short`, and links to the existing creator.
7. Complete Instagram and TikTok auth verify/Doctor tests.
8. Complete a real OpenClaw cron trigger.
