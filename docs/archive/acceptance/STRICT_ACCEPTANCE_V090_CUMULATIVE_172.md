# Media2MD v0.8.6 Cumulative Strict Acceptance (1–162)

Date: 2026-06-25
Decision: **PRIVATE PRODUCTION APPROVED; PUBLIC v1.0 MATRIX NOT COMPLETE**

Legend: 🟢 passed; 🟡 requires live/human/external evidence or is superseded; 🔴 historical real failure retained for audit. Historical red items are not active blockers when an explicitly cited later replacement is green.

## A. Core product and early live gates (1–40)

| # | Strict acceptance item | Current status | Evidence / remaining requirement |
|---:|---|---|---|
| 1 | Clean GitHub-ready source repository | 🟢 PASS | Clean source ZIP, license, security policy, CI and release assets exist. Public push is deferred until functional RC validation is complete. |
| 2 | Base package plus optional modules | 🟢 PASS | Base, Instagram, YouTube, TikTok, MLX and OpenClaw extras build successfully. |
| 3 | Agent-controlled daily operations | 🟢 PASS | Status, settings, creator management, sync, batch, scheduler, auth refresh and doctor are CLI/NDJSON controllable. Sensitive or destructive operations remain gated. |
| 4 | Login support for all three platforms | 🟡 LIVE | YouTube 已真機通過；Instagram、TikTok browser-profile 登入仍缺完整真機證據。 |
| 5 | Login-state verification for all three platforms | 🟡 LIVE | YouTube server probe 已通過；Instagram、TikTok valid/expired/revoked/challenge 狀態尚未完整跑。 |
| 6 | Automatic cookie refresh and re-login guidance | 🟡 HUMAN | Cookie 可自動重讀；密碼、2FA、CAPTCHA、challenge 必須真人處理。 |
| 7 | Large-scale processing across all three platforms | 🟡 LIVE | YouTube 與 Instagram 有真實批次；TikTok 已有 Exact 1,159 與零星處理，但尚未完成大規模 processing soak。 |
| 8 | YouTube long-video split, transcribe, resume and merge | 🟡 LIVE | Long-video 選擇與處理路徑存在；仍缺指定 fixture 的 chunk、resume、merged Markdown 實物證據。 |
| 9 | OpenClaw cron scheduling | 🟡 LIVE | Skill 與 scheduler 命令存在；仍缺 OpenClaw 真實 cron 建立、觸發、中斷、恢復。 |
| 10 | Doctor diagnostics for all three platforms | 🟡 LIVE | YouTube Doctor 已通過；Instagram、TikTok Doctor 真機狀態矩陣尚缺。 |
| 11 | GitHub Release update and rollback | 🟡 PENDING-EXTERNAL | 依使用者決定延後 GitHub Release／rollback 發布演練。 |
| 12 | PyPI, npm and Homebrew publication | 🟡 PENDING-EXTERNAL | 依使用者決定延後 PyPI、npm、Homebrew 公開發布。 |
| 13 | View per-creator configuration and state | 🟢 PASS | Creator status and policy show commands work. |
| 14 | View system state and settings | 🟢 PASS | Status, settings, agent status, auth and doctor outputs exist. |
| 15 | Human and agent can modify public settings | 🟢 PASS | Typed batch policies and public settings are editable through CLI. |
| 16 | Process a single YouTube Shorts URL | 🟡 LIVE | 舊流程曾處理 fixture；仍缺現版 classified folder/frontmatter 真機證據。 |
| 17 | Single Short links to the correct creator | 🟡 LIVE | Channel-ID merge 已實作；仍缺現版 Short 不產生重複 Creator 的真機檢查。 |
| 18 | YouTube creator sync includes Videos and Shorts | 🟢 PASS | Live Full Sync found 267 videos and 210 Shorts, total 477. |
| 19 | Separate exact Video and Shorts totals | 🟢 PASS | Live Full Sync returned exact per-surface totals. |
| 20 | Upload/delete changes update totals | 🟡 LIVE | Quick/Full 語意已實作；仍缺真實 upload/delete 事件造成總數變化的觀測。 |
| 21 | TikTok creator exact total | 🟢 PASS-LIVE | StartupBell Cursor Catalog 已真機完成至終端頁，精確總數 1,159；見 #125。 |
| 22 | Instagram exact Reel total | 🟢 PASS | Live status reports `all:85`, `current=true`, and `last_full_total=85`. This validates catalog exactness, not media processing success. |
| 23 | Different batch limits per platform/creator | 🟢 PASS | TikTok 100, Instagram 30 and YouTube typed limits were accepted. |
| 24 | Typed limits within one YouTube creator | 🟢 PASS | Short 30, normal video 5 and long video 1 policies are active. |
| 25 | YouTube long videos occupy a one-item batch | 🟢 PASS | Live output showed `composition={"youtube_long": 1}`. |
| 26 | YouTube classified output folders/frontmatter | 🟡 LIVE | 分類資料夾與 frontmatter 已實作；仍缺實際輸出檔案證據。 |
| 27 | Manual Short keeps creator totals consistent | 🟡 LIVE | 回歸測試通過；仍缺手動 Short 重加後 totals 一致的真機證據。 |
| 28 | Quick/Full exactness transition | 🟢 PASS | Live Full Sync was exact and Quick Sync correctly became non-exact. |
| 29 | Fixed live fixture set | 🟡 LIVE | TikTok Exact 1,159 已補齊；完整固定 fixture matrix 仍缺 YouTube long/Short 與 Auth Doctor/OpenClaw。 |
| 30 | Fail-fast missing archive protection without killing the interactive shell | 🟢 PASS | Strict mode now runs inside a child subshell; missing archive/installer returns a non-zero code and the parent prompt survives. |
| 31 | Installer verifies actual installed version | 🟢 PASS | Installer clears stale bytecode and verifies package version, project script version, and final `media2md 0.8.1`. |
| 32 | TikTok stable identity survives pagination | 🟢 PASS | Live v0.7.6 output recovered one identity from checkpoint items and successfully advanced from item 201 through item 375. |
| 33 | Instagram `/reels/` URL normalization | 🟢 PASS | Live add succeeded for the full Career Cleo URL. |
| 34 | TikTok curl error 35 / TLS is classified correctly | 🟢 PASS | Live v0.7.4 output proved TLS/curl 35 and curl 56 are detected. v0.7.7 prevents this class from triggering an unbounded target sweep. |
| 35 | TikTok transport fallback | 🟢 PASS | Live v0.7.6 output exercised configured Chrome, latest Chrome/Safari, circuit breaking, and direct-plain; multiple pages completed. |
| 36 | TikTok extractor process-tree cleanup | 🟢 PASS | Live v0.7.6 Ctrl+C produced `MEDIA2MD_INTERRUPTED` and returned to the shell while preserving the checkpoint. |
| 37 | TikTok failure returns control to shell | 🟢 PASS | Live v0.7.6 interrupt returned control to the active shell immediately after `MEDIA2MD_INTERRUPTED`. |
| 38 | TikTok page-3 checkpoint is preserved on failure | 🟢 PASS | Regression confirms `next_start=201` is not advanced or deleted. v0.7.7 can also import the already discovered items as a non-exact partial catalog. |
| 39 | TikTok retry/fallback telemetry | 🟢 PASS-LIVE | 後續真機已出現 contextual waiting、attempt result、page/run progress，且不再以舊式洪水輸出。 |
| 40 | Instagram human-mode completion summary | 🟢 PASS | Live output exposed `processed=30 completed=0 failures=30 remaining=85`, proving the summary works and revealing a separate processing failure. |

## B. Reliability, observability, and bounded execution (41–80)

| # | Strict acceptance item | Current status | Evidence / remaining requirement |
|---:|---|---|---|
| 41 | Instagram unified status imports exact catalog total | 🟢 PASS | Live status shows `all:85`, `EXACT current=true`, `last_full_total=85`, and a Full Sync timestamp. |
| 42 | YouTube batch identifies selected media IDs | 🟢 PASS | Live output identified `selected_media_ids=["-oE_7kDGkZA"]`. The separately specified fixture still needs chunk/merge evidence. |
| 43 | Creator status does not truncate typed batch limits | 🟢 PASS | Live YouTube and Instagram status printed the complete `BATCH_LIMITS` line. |
| 44 | Preserve last exact Full Sync snapshot across Quick Sync | 🟢 PASS | Schema stores last exact total/time and YouTube per-type totals; automated Full→Quick regression passes. |
| 45 | Current and last-exact semantics are visible together | 🟢 PASS-LIVE | 最新真機 status 同時顯示 `EXACT current=true`、`last_full_total=1159`、時間戳。 |
| 46 | No checkpoint regression after transient retry exhaustion | 🟢 PASS | Failed pages do not advance or remove the checkpoint. |
| 47 | No silent infinite retry | 🟢 PASS | Live v0.7.7 output proved one 300-second page deadline, explicit attempt outcomes, checkpoint preservation, and a return to the shell. |
| 48 | Release contains no cookies, creator data, workspaces or backups | 🟢 PASS | Release construction excludes mutable state and compiled caches. |
| 49 | Upgrade removes stale Python bytecode | 🟢 PASS | Regression reproduces the v0.7.2→v0.7.3 stale `.pyc` failure and confirms v0.7.7 purges caches before and after install. |
| 50 | Project CLI cannot execute an older cached package launcher | 🟢 PASS | `./bin/media2md` directly executes `scripts/media2md.py` with `-B`; package/script/CLI versions must agree. |
| 51 | Installer failure leaves the current terminal usable | 🟢 PASS | Upgrade is documented and tested in a child subshell; parent shell prints the exit code and remains interactive. |
| 52 | TikTok quiet-period telemetry is understandable | 🟢 PASS | Live v0.7.7 output used contextual `SYNC_WAITING` with range, candidate, strategy, auth mode, elapsed time, PID, and timeout. |
| 53 | TikTok page and extractor attempts have finite deadlines | 🟢 PASS | Live v0.7.7 output showed per-attempt limits shrinking to the remaining shared 300-second page budget. |
| 54 | TikTok validation commands are paste-safe | 🟢 PASS | Current guide uses single-line commands and never leaves a trailing backslash on the final argument. |
| 55 | Instagram progress distinguishes attempts, successes and failures | 🟢 PASS | Live output showed attempted 3, completed 0 and failed 3 without presenting 100% attempted as success. |
| 56 | Instagram failed items expose a root cause immediately | 🟢 PASS | Live output exposed the exact `--cookies-file` parser mismatch for each shortcode. |
| 57 | Instagram max-failure policy is enforced inside the batch | 🟢 PASS | The worker stops the batch when the configured threshold is reached instead of attempting all remaining items. |
| 58 | Instagram all-failed batches cannot look successful | 🟢 PASS | Completion status becomes `completed_with_errors`, returns exit code 2, and reports completed/failed separately. |
| 59 | Instagram failure report and engine log are surfaced | 🟢 PASS | Live output printed report path, engine log, failure examples and required action. |
| 60 | Progress percentage is not interpreted as success percentage | 🟢 PASS | Acceptance now requires attempted, completed and failed counts; 100% attempted with 0 completed is explicitly a failure. |
| 61 | Legacy exact snapshot is not fabricated | 🟢 PASS | If no prior exact-snapshot field exists, status remains unknown until the next real Full Sync; v0.7.7 does not invent historical certainty. |
| 62 | Instagram cookie path preserves the proven default | 🟢 PASS | Live v0.7.6 processed 30/30 Career Cleo Reels after restoring worker-side managed-file/browser fallback. |
| 63 | Known Instagram contract failures are safely requeued | 🟢 PASS | Installer resets only rows whose stored error is the obsolete `--cookies-file` parser rejection; unrelated failures remain unchanged. |
| 64 | TikTok fallback strategy count is bounded | 🟢 PASS | Automated test confirms no more than four strategies and excludes the v0.7.4 all-target sweep. |
| 65 | Repeated TikTok TLS failures open a circuit breaker | 🟢 PASS | Two matching TLS failures skip remaining impersonation targets and continue directly to the plain isolated strategy. |
| 66 | TikTok direct fallback ignores hidden proxy configuration | 🟢 PASS-LIVE | 真機在 macOS proxy 環境下使用隔離 direct transport 成功完成 Cursor 與媒體下載。 |
| 67 | TikTok transport root cause is not hidden by secUid fallback text | 🟢 PASS | TLS/proxy signatures now bypass the secondary-user-ID wrapper and remain the reported root cause. |
| 68 | TikTok catalog page size is separate from processing batch size | 🟢 PASS | `MEDIA2MD_TIKTOK_SYNC_PAGE_SIZE` controls catalog pagination only; typed `tiktok_video` controls later processing. |
| 69 | Reducing processing batch does not claim to fix catalog transport | 🟢 PASS | Documentation and status semantics distinguish sync-page size, media batch size and network transport failures. |
| 70 | Public `media2md creator run` accepts `--retry-failed` | 🟢 PASS | Parser and forwarding regression tests cover the exact command that v0.7.5 documentation advertised but the public CLI rejected. |
| 71 | Instagram default Batch does not force a cross-script cookie argument | 🟢 PASS | Worker command omits `--cookies-file` by default and restores worker-side managed-file/browser fallback; explicit overrides remain tested. |
| 72 | One real Career Cleo Reel completes through the full public CLI | 🟢 PASS | Live v0.7.6 run completed 30 of 30 Career Cleo Reels with zero failures and produced a completion report. |
| 73 | TikTok direct mode explicitly disables OS/system proxy | 🟢 PASS | Live output reported `direct_strategy_forces_proxy_empty=true`, and a direct-plain attempt completed page 11 despite enabled macOS proxy classes. |
| 74 | macOS system proxy presence is visible without leaking secrets | 🟢 PASS | Live output reported `macos_system_proxy=http,https,socks` without exposing endpoints or credentials. |
| 75 | Old TikTok checkpoint can recover a stable identity from cached media | 🟢 PASS | Live output showed `SYNC_IDENTITY_RECOVERY recovered=1 source=checkpoint_items` before resuming item 201. |
| 76 | TikTok partial catalog survives exact-sync failure and is explicitly usable | 🟢 PASS | Live output showed `SYNC_PARTIAL_CATALOG_SAVED known_items=200 exact=false next_start=201`; later completed pages advanced the checkpoint without losing prior items. |
| 77 | One shared deadline per TikTok page | 🟢 PASS | Live v0.7.7 output showed one `SYNC_PAGE_BUDGET` and later attempts receiving only the remaining 44/64 seconds. |
| 78 | No nested TikTok fallback ladder | 🟢 PASS | `_extract_tiktok_page` calls the low-level extractor directly for at most one stable ID and one handle candidate; the handle path cannot invoke another identifier fallback. |
| 79 | Last successful TikTok strategy is reused first | 🟡 LIVE-RECHECK | 跨同一執行與 checkpoint 持久化已測；仍缺明確的「關閉 CLI 再重開」同步策略真機證據。 |
| 80 | TikTok full-sync invocation has a total runtime budget | 🟡 LIVE-RECHECK | 總 runtime budget 已實作並測試；仍缺刻意耗盡 1,800 秒總預算的真機 gate。 |

## C. Cursor catalog and public CLI convergence (81–120)

| # | Strict acceptance item | Current status | Evidence / remaining requirement |
|---:|---|---|---|
| 81 | TikTok sync can limit pages per invocation | 🟢 PASS | `MEDIA2MD_TIKTOK_SYNC_MAX_PAGES_PER_RUN` provides a deterministic cap for manual or agent runs; zero means unlimited within the runtime budget. |
| 82 | Budget exhaustion pauses instead of failing or running forever | 🟢 PASS | Live v0.7.8 stopped after 304 seconds, preserved 475 items, returned `SYNC_RUN_PAUSED reason=page_budget_exhausted`, and returned to the shell. |
| 83 | TikTok attempt outcomes are explicit | 🟢 PASS | Live v0.7.7 output showed success, timeout and elapsed seconds for every transport attempt. |
| 84 | TikTok run progress is visible across pages | 🟢 PASS | Live v0.7.8 advanced 375→475 across four pages and printed `SYNC_RUN_PROGRESS` after every completed page. |
| 85 | Stable-ID catalog payload may reuse the already-known human handle | 🟢 PASS | Live v0.7.8 repeatedly printed `SYNC_STABLE_ID_HANDLE_REUSED handle=startupbell` and completed pages 376–475. |
| 86 | Stable-ID success must not trigger a second handle-profile fetch | 🟢 PASS | Live v0.7.8 showed `second_profile_fetch=false` followed directly by `SYNC_PAGE_DONE` for four pages. |
| 87 | Page-budget exhaustion returns a resumable partial result, not a hard error | 🟢 PASS | Live v0.7.8 preserved 475 items, kept `resume_from=476`, returned a partial JSON summary, and did not end with a hard error. |
| 88 | Clean pause cannot advance or truncate the checkpoint | 🟢 PASS | Regression test verifies `next_start` and cached items remain unchanged when a page deadline expires. |
| 89 | TikTok stable-ID metadata fallback does not spend the remaining page budget on duplicate discovery | 🟢 PASS | Regression test reproduces a handle-less stable payload and confirms only one extractor invocation occurs. |
| 90 | Successful TikTok transport persists across CLI invocations | 🟡 LIVE-RECHECK | Checkpoint schema 會保存 transport/auth；仍缺明確跨 CLI 重啟後優先命中的真機 log。 |
| 91 | TikTok page-wide circuit breaker | 🟢 PASS | Regression confirms stable-ID TLS failures keep the breaker open when the handle candidate starts, preventing a second impersonation ladder. |
| 92 | No extractor starts when remaining page budget is below five seconds | 🟢 PASS | Regression verifies the subprocess is not launched and the page pauses immediately. |
| 93 | Page deadline cannot be extended by a forced five-second minimum | 🟢 PASS | v0.7.9 removes the `max(5, ...)` overrun that produced a 304-second run from a 300-second page budget. |
| 94 | `creator_identifiers.sec_uid` remains visible in paused summaries | 🟢 PASS | Stable identifiers are merged into TikTok metadata before partial/full upsert and exposed in the JSON summary. |
| 95 | Maximum-page pause reason is semantically correct | 🟢 PASS | Reaching `MEDIA2MD_TIKTOK_SYNC_MAX_PAGES_PER_RUN` now reports `max_pages_per_run`, not `page_budget`. |
| 96 | v0.7.9 does not change live-passing Instagram or YouTube paths | 🟢 PASS | The patch is isolated to TikTok checkpoint strategy memory, page state, deadline handling, identity metadata, and pause labeling. |
| 97 | Old checkpoints under enabled macOS proxies prefer isolated direct transport | 🟢 PASS | With no persisted hint, v0.7.9 selects `direct-plain` first when macOS reports HTTP/HTTPS/SOCKS proxy classes; the first real success then replaces this bootstrap hint in checkpoint. |
| 98 | Resumed TikTok sync must not use `--playlist-start` as the primary deep-pagination mechanism | 🟢 PASS | v0.8.1 routes checkpoints with a valid secUid to the cursor API backend; regression fails if `_extract_tiktok_page` is invoked. |
| 99 | TikTok cursor is recovered from the oldest known checkpoint item | 🟢 PASS | ISO timestamps from schema 3/4 checkpoints are converted to the millisecond cursor used by the official TikTok user extractor. |
| 100 | TikTok cursor and device ID persist across CLI invocations | 🟢 PASS | Checkpoint schema 5 stores `tiktok_cursor`, `tiktok_device_id`, and `pagination_backend=cursor_api`. |
| 101 | One cursor response is normalized and checkpointed before the next request | 🟢 PASS | `SYNC_CURSOR_PAGE_DONE` is emitted only after atomic checkpoint persistence and partial-registry upsert. |
| 102 | Cursor backend bypasses macOS system proxy | 🟢 PASS | Native curl uses `--noproxy *` and a proxy-cleared environment; unit test inspects the exact command. |
| 103 | Cursor API completion establishes an exact TikTok total | 🟢 PASS-LIVE | StartupBell 真機到達 `has_more=false`，建立 Exact 1,159；見 #125。 |
| 104 | Cursor request failure returns a resumable partial result | 🟢 PASS | Failure keeps the previous cursor/items, emits `SYNC_RUN_PAUSED reason=cursor_request_failed`, and returns to the shell. |
| 105 | Legacy bounded yt-dlp paging remains a fallback, not the default resume engine | 🟢 PASS | New/identity-less creators can still bootstrap through the bounded extractor, while known secUid checkpoints switch to cursor mode. |
| 106 | Cursor summary preserves the command-start total | 🟢 PASS | Unit regression forces 655→715 and requires `previous_current_total=655`. |
| 107 | Cursor run delta is accurate | 🟢 PASS | `new_since_last_sync` is computed from the command-start snapshot, not the post-upsert Registry. |
| 108 | Every native cursor attempt emits a result | 🟢 PASS | Public failure and authenticated success both emit `SYNC_CURSOR_ATTEMPT_RESULT` with a reason and elapsed time. |
| 109 | Partial TikTok Full Sync skips legacy Quick Sync before Batch | 🔴 FAIL-HISTORICAL | v0.8.1 public CLI 曾錯跑 legacy Quick Sync；歷史失敗保留，現行修復由 #118–124 真機證明。 |
| 110 | TikTok media download tries isolated direct transport first under macOS proxies | 🟢 PASS | Download-cascade test requires `--ignore-config --proxy ""` and succeeds without invoking impersonation. |
| 111 | TikTok media-download transport success persists across items/runs | 🟢 PASS | Separate state records strategy plus auth mode; no cookies or proxy credentials are stored. |
| 112 | TikTok per-item transport cascade is bounded | 🟢 PASS | `MEDIA2MD_TIKTOK_DOWNLOAD_ITEM_BUDGET_SECONDS` and per-attempt timeout prevent one item from running indefinitely. |
| 113 | Transport fallback does not count as an item failure | 🟢 PASS | Item failure is raised only after all bounded strategies are exhausted. |
| 114 | Early max-failure stop prints a final summary | 🟢 PASS | `CREATOR_RUN_COMPLETED status=stopped_max_failures` includes processed/completed/failures/remaining. |
| 115 | Stored TikTok identities survive Quick/Partial summaries | 🟢 PASS | `sec_uid` and `user_id` are merged from the Registry when incoming metadata omits them. |
| 116 | v0.8.1 does not replace the v0.8.0 cursor Catalog engine | 🟢 PASS | Cursor checkpoint schema, native curl backend, and exact-completion logic are unchanged. |
| 117 | Source, wheel, and release kit contain no bundled runtime database | 🟢 PASS | `src/media2md/bundle/data` is excluded and the inherited empty `media2md.db` fixture was removed. |
| 118 | Both public Creator Run surfaces use a single shared implementation | 🟢 PASS | `media2md.py` and `social2md.py` both call `prepare_catalog_for_creator_run`; duplicated partial-catalog branching is forbidden by regression. |
| 119 | The real public `./bin/media2md` skips Quick Sync for a partial TikTok cursor Catalog | 🟢 PASS-LIVE | v0.8.2 真機 public CLI 已在 partial Catalog 下直接進 Batch；見 #124。 |
| 120 | Public CLI regression cannot silently invoke Registry sync | 🟢 PASS | The fake Registry exits 91 and prints `LEGACY_QUICK_SYNC_CALLED` if `sync` is invoked; the shipped entrypoint test must still complete Batch with exit 0. |

## D. Exact lifecycle, production safety, and release gates (121–162)

| # | Strict acceptance item | Current status | Evidence / remaining requirement |
|---:|---|---|---|
| 121 | Batch starts without legacy transport telemetry | 🟢 PASS | Public CLI subprocess test rejects `SYNC_NETWORK_CONTEXT`, `SYNC_TRANSPORT_ATTEMPT`, and `sync_mode=quick` before `BATCH_START`. |
| 122 | Historical false-green acceptance is corrected | 🟢 PASS | v0.8.1 requirement 109 is recorded as FAIL with the exact live public-CLI cause instead of retaining the unit-only PASS. |
| 123 | Live-passing Cursor and media-download engines remain unchanged | 🟢 PASS | v0.8.2 changes only the shared Creator Run pre-sync decision, tests, versioning, and release documentation. |
| 124 | v0.8.2 public CLI skips legacy Quick Sync while Full Sync is partial | 🟢 PASS-LIVE | Live v0.8.2 run emitted `AUTO_SYNC_SKIPPED reason=full_catalog_in_progress`, entered Batch directly, and completed 5/5 without legacy Quick Sync output. |
| 125 | StartupBell Full Cursor catalog reaches an exact terminal state | 🟢 PASS-LIVE | Live total 1,159; final page fetched 9 with `has_more=false`; `SYNC_CURSOR_COMPLETE exact=true`. |
| 126 | Full exact snapshot is persisted | 🟢 PASS-LIVE | `last_full_exact_total=1159`, non-empty `last_full_exact_at`, and `last_full_media_type_totals.tiktok_video=1159`. |
| 127 | Quick Sync must not downgrade a proven TikTok exact catalog | 🟢 PASS | Registry regression preserves exactness for a bounded Quick merge. Live v0.8.2 exposed the prior failure. |
| 128 | Exact TikTok Catalog skips hidden pre-run Quick Sync | 🟢 PASS | Shared decision and shipped public CLI subprocess test require `reason=exact_catalog_available` and reject Registry sync calls. |
| 129 | Upgrade repairs only a safely matching downgraded exact state | 🟢 PASS | Installer repair requires TikTok, a non-null exact snapshot, and `current_total == last_full_exact_total`. |
| 130 | A new Full Sync after checkpoint deletion uses Registry-backed Cursor bootstrap | 🟢 PASS | Regression requires `SYNC_CURSOR_BOOTSTRAP`, forbids legacy extraction, and completes an idempotent exact scan. |
| 131 | TikTok type-level exactness is visible | 🟢 PASS | `media_type_totals_exact.tiktok_video` follows catalog exactness. |
| 132 | TikTok last-full type total remains visible after Quick summaries | 🟢 PASS | `last_full_media_type_totals.tiktok_video` is sourced from the last exact total. |
| 133 | v0.8.3 exact lifecycle requires live verification | 🔴 FAIL-HISTORICAL | v0.8.3 fresh Full rebuild 遇零頁 403 時曾降級 Exact Catalog；歷史失敗保留，現行修復由 #134–140 真機證明。 |
| 134 | A zero-page Full rebuild failure cannot downgrade the active exact TikTok catalog | 🟢 PASS | Regression forces public/auth cursor failure before page one and requires `current_total_exact=true`, unchanged current IDs, and `baseline_preserved=true`. |
| 135 | Partial Full rebuild pages remain staged until terminal completion | 🟢 PASS | Regression fetches one cursor page, pauses at the page cap, and verifies the active exact IDs are unchanged while the new item exists only in checkpoint staging. |
| 136 | Rebuild pause telemetry distinguishes active baseline from staged items | 🟢 PASS | Paused summaries include `rebuild_in_progress`, `baseline_preserved`, and `staged_total`; `SYNC_RUN_PAUSED` reports the active exact flag. |
| 137 | Completed Full Sync cursor device ID survives checkpoint deletion | 🟢 PASS | Cursor transport state is persisted separately and reused by the next Registry-backed rebuild. |
| 138 | Upgrade migrates a v0.8.3 failed rebuild safely | 🟢 PASS | Installer repairs exactness only when the total matches the last exact snapshot, saves the checkpoint device ID, and marks the empty checkpoint as `rebuild_from_exact`. |
| 139 | Retryable failed items remain counted in the real processing queue | 🟢 PASS | Creator Run now queries actual Registry state for `stopped_max_failures`; failed items remain eligible because only completed/skipped rows are excluded. |
| 140 | A paused or failed TikTok Full rebuild preserves the active exact baseline | 🟢 PASS-LIVE | v0.8.4 真機跑 12 頁後暫停，仍保留 Exact 1,159，且後續 Batch 5/5 成功。 |
| 141 | Batch remains usable after staged rebuild pause | 🟢 PASS-LIVE | v0.8.4 真機 staged rebuild 暫停後 Batch 5/5，DONE 92→97。 |
| 142 | Duplicate Creator Run for the same provider/creator is rejected before work starts | 🟢 PASS | Per-creator `creator-run` lock and regression test verify owner metadata and no call into the unlocked runner. |
| 143 | Duplicate Full Sync for the same provider/creator is rejected | 🟢 PASS | Per-creator `creator-sync` lock wraps every Registry sync path. |
| 144 | Different creators and Sync versus Run are not globally serialized | 🟢 PASS | Operation locks are scoped; live work shares the maintenance lock and unrelated scopes may coexist. |
| 145 | Direct media processing cannot race Creator Run for the same media ID | 🟢 PASS | `media-process` lock wraps `process-registered` by provider/external ID. |
| 146 | Backup cannot run while a live mutation is active | 🟢 PASS | Shared/exclusive maintenance lock regression rejects an exclusive backup while a live operation holds a shared lock. |
| 147 | State backup is consistent and independently verifiable | 🟢 PASS | SQLite online backup, ZIP CRC, SHA-256 manifest, file sizes, and `PRAGMA integrity_check` are verified in regression tests. |
| 148 | Backup excludes browser/session secrets and bulky derived media | 🟢 PASS | Manifest and archive tests exclude `data/secrets`, workspace, downloads, transcripts, Markdown, and logs. |
| 149 | Existing v0.8.4 state and exact TikTok catalog survive upgrade | 🟡 SUPERSEDED | v0.8.5 的 Exact 狀態與 lock 已通過，但 backup verify 失敗、單支未跑；由 v0.8.6 #159–160 完整取代。 |
| 150 | Duplicate-run lock behaves on macOS `fcntl` | 🟢 PASS-LIVE | macOS `fcntl` 真機拒絕第二個 Creator Run，未進入 `BATCH_START`。 |
| 151 | Public package publication | 🟡 PENDING-EXTERNAL | 公開發布步驟仍需使用者授權；不阻擋 private production。 |
| 152 | Public v1.0.0 platform matrix | 🟡 PENDING-EXTERNAL | Public v1.0 平台矩陣仍未完成；由 #162 統一追蹤。 |
| 153 | v0.8.5 portable backup verifies on the real project | 🔴 FAIL-HISTORICAL | v0.8.5 真機 backup verify 因合法 0-byte `.creators.lock` 被誤判而失敗；已由 #154、#155、#159 修復。 |
| 154 | Backup verification accepts legitimate zero-byte files | 🟢 PASS | Regression includes a zero-byte state marker and requires successful hash, size, ZIP CRC, and SQLite verification. |
| 155 | Operational lock and partial files are excluded from portable backups | 🟢 PASS-LIVE | v0.8.6 真機備份 25 檔、三個 SQLite DB，未再包含 operational lock，verify 成功。 |
| 156 | Source release contains no bundled runtime lock artifacts | 🟢 PASS | The source tree and release manifest exclude `src/media2md/bundle/logs/locks`. |
| 157 | Exact StartupBell baseline survived the v0.8.5 upgrade | 🟢 PASS-LIVE | 真機升級前後皆為 TRACKED 1,159、EXACT true；處理後 DONE 98、LEFT 1,061。 |
| 158 | Duplicate Creator Run lock works on macOS | 🟢 PASS-LIVE | A real second invocation was rejected before `BATCH_START` with active owner PID and exit-path telemetry. |
| 159 | v0.8.6 backup creation and verification pass on the real project | 🟢 PASS-LIVE | 真機 `MEDIA2MD_BACKUP_CREATED` 與 `MEDIA2MD_BACKUP_VERIFIED` 均成功，SHA-256 一致，secrets=false。 |
| 160 | One real TikTok item completes after the v0.8.6 upgrade | 🟢 PASS-LIVE | 真機一支 TikTok 完成，`completed=1 failures=0`，DONE 97→98，Exact 1,159 保持。 |
| 161 | Public package publication | 🟡 PENDING-EXTERNAL | GitHub Release、PyPI、npm、Homebrew 需使用者明確授權；不阻擋 private production。 |
| 162 | Public v1.0.0 platform matrix | 🟡 PENDING-EXTERNAL | 仍缺 Instagram/TikTok Auth Doctor 狀態矩陣、YouTube 長影片 chunk/merge、Short classified output、OpenClaw cron 真機矩陣。 |

## Count

- 🟢 Green: 136
- 🟡 Yellow: 23
- 🔴 Historical red: 3
- Active private-production red blockers: 0

## Remaining yellow gates before public v1.0

Items 4, 5, 6, 7, 8, 9, 10, 11, 12, 16, 17, 20, 26, 27, 29, 79, 80, 90, 149, 151, 152, 161, and 162 remain yellow for live, human, external, or superseded-record reasons. Items 149, 151, and 152 are duplicated historical release gates and are not additional engineering defects.

## v0.9.0 consolidated one-shot evidence fixes

| # | Requirement | Status | Evidence / remaining requirement |
|---:|---|---|---|
| 163 | The complete one-shot evidence ZIP and SHA are verified before diagnosis | PASS | `media2md-one-shot-evidence-20260625T151508.zip` matched SHA-256 `2d22adb72f0849b2d56987f2e814cc0573733dbe38b7eeee1d3dad8b102d4e3c`; all gate logs and summaries were present. |
| 164 | An authenticated Instagram `/accounts/edit/` response cannot be classified as a challenge merely because application JavaScript contains `checkpoint` | FIXED-LIVE | v0.8.6 live evidence had active `sessionid` and `ds_user_id`, HTTP 200, and `/accounts/edit/` but false challenge. v0.9.0 uses final authenticated path semantics; exact live rerun remains in the final closure kit. |
| 165 | TikTok `media inspect` uses the bounded processing transport cascade | FIXED-LIVE | v0.8.6 inspect failed on a single curl-35 route while immediate processing succeeded through fallback. v0.9.0 adds bounded inspect attempts, result telemetry, auth fallback, and winning-strategy persistence; live rerun remains. |
| 166 | A YouTube channel with no Videos tab but one or more Shorts completes an exact Full Sync | FIXED-LIVE | v0.8.6 failed on `@huai-syuanhuang5857` because `/videos` did not exist. v0.9.0 treats missing tabs as empty exact surfaces and continues to Shorts; live rerun remains. |
| 167 | Resuming a staged TikTok exact rebuild with checkpoint items cannot publish a partial active catalog | FIXED-LIVE | v0.8.6 emitted `SYNC_PARTIAL_CATALOG_SAVED` for 173 staged items and downgraded Exact 1,159. v0.9.0 skips partial publication whenever `rebuild_from_exact=true`; installer repairs the matching live state. Final live status and bounded continuation remain. |
| 168 | Reprocessing an existing current media item preserves creator exactness | PASS | Regression seeds an exact catalog, re-adds the same item, and requires exactness to remain true; a genuinely new item must still invalidate exactness. |
| 169 | OpenClaw isolated Cron installation cannot fail for lack of a delivery recipient | FIXED-LIVE | v0.8.6 work completed but announcement delivery failed. v0.9.0 defaults to `--no-deliver`; `--announce` requires explicit `--channel` and `--to`. Final OpenClaw live rerun remains. |
| 170 | Advisory GitHub update discovery cannot change a successful Scheduler tick to failure | PASS | HTTP 404 means no published Release; other update-check errors emit a nonfatal warning and do not increment scheduler failures. |
| 171 | Final live acceptance tooling cannot create false reds from missing pytest, blank Short URL input, or an early network pause reason | PASS | The v0.9.0 closure kit does not require pytest in the production venv, reprompts and persists human Short state, tests every auth provider independently, and accepts any bounded resumable TikTok pause only when exactness remains preserved. |
| 172 | v0.9.0 closes every product failure from the complete v0.8.6 one-shot evidence run | LIVE | Requires one final closure execution covering Instagram/TikTok auth, TikTok inspect, Shorts-only YouTube Full Sync, staged exact continuation, controlled Short upload/delete, OpenClaw no-delivery Cron, final exact state, and verified backup. |
