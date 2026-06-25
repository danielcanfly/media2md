# Acceptance Audit Snapshot

This snapshot distinguishes what is currently backed by source/tests in the reconstructed repo from what still relies on previously signed live evidence.

| ID | Current acceptance row | Audit classification | Notes |
|---:|---|---|---|
| 1 | Clean GitHub-ready source repository | source/test backed | Can be evaluated from source tree, packaging artifacts, or automated tests. |
| 2 | Base package plus optional modules | source/test backed | Can be evaluated from source tree, packaging artifacts, or automated tests. |
| 3 | Agent-controlled daily operations | source/test backed | Can be evaluated from source tree, packaging artifacts, or automated tests. |
| 4 | Login support for all three platforms | existing live evidence required | Not fully re-run this turn; relies on signed closure/preflight unless separately tested. |
| 5 | Login-state verification for all three platforms | existing live evidence required | Not fully re-run this turn; relies on signed closure/preflight unless separately tested. |
| 6 | Automatic cookie refresh and re-login guidance | existing live evidence required | Not fully re-run this turn; relies on signed closure/preflight unless separately tested. |
| 7 | Large-scale processing across all three platforms | existing live evidence required | Not fully re-run this turn; relies on signed closure/preflight unless separately tested. |
| 8 | YouTube long-video split, transcribe, resume and merge | existing live evidence required | Not fully re-run this turn; relies on signed closure/preflight unless separately tested. |
| 9 | OpenClaw cron scheduling | existing live evidence required | Not fully re-run this turn; relies on signed closure/preflight unless separately tested. |
| 10 | Doctor diagnostics for all three platforms | existing live evidence required | Not fully re-run this turn; relies on signed closure/preflight unless separately tested. |
| 11 | GitHub Release update and rollback | source/test backed | Can be evaluated from source tree, packaging artifacts, or automated tests. |
| 12 | PyPI, npm and Homebrew publication | source/test backed | Can be evaluated from source tree, packaging artifacts, or automated tests. |
| 13 | View per-creator configuration and state | source/test backed | Can be evaluated from source tree, packaging artifacts, or automated tests. |
| 14 | View system state and settings | source/test backed | Can be evaluated from source tree, packaging artifacts, or automated tests. |
| 15 | Human and agent can modify public settings | source/test backed | Can be evaluated from source tree, packaging artifacts, or automated tests. |
| 16 | Process a single YouTube Shorts URL | existing live evidence required | Not fully re-run this turn; relies on signed closure/preflight unless separately tested. |
| 17 | Single Short links to the correct creator | existing live evidence required | Not fully re-run this turn; relies on signed closure/preflight unless separately tested. |
| 18 | YouTube creator sync includes Videos and Shorts | source/test backed | Can be evaluated from source tree, packaging artifacts, or automated tests. |
| 19 | Separate exact Video and Shorts totals | source/test backed | Can be evaluated from source tree, packaging artifacts, or automated tests. |
| 20 | Upload/delete changes update totals | existing live evidence required | Not fully re-run this turn; relies on signed closure/preflight unless separately tested. |
| 21 | TikTok creator exact total | existing live evidence required | Not fully re-run this turn; relies on signed closure/preflight unless separately tested. |
| 22 | Instagram exact Reel total | source/test backed | Can be evaluated from source tree, packaging artifacts, or automated tests. |
| 23 | Different batch limits per platform/creator | source/test backed | Can be evaluated from source tree, packaging artifacts, or automated tests. |
| 24 | Typed limits within one YouTube creator | source/test backed | Can be evaluated from source tree, packaging artifacts, or automated tests. |
| 25 | YouTube long videos occupy a one-item batch | source/test backed | Can be evaluated from source tree, packaging artifacts, or automated tests. |
| 26 | YouTube classified output folders/frontmatter | existing live evidence required | Not fully re-run this turn; relies on signed closure/preflight unless separately tested. |
| 27 | Manual Short keeps creator totals consistent | existing live evidence required | Not fully re-run this turn; relies on signed closure/preflight unless separately tested. |
| 28 | Quick/Full exactness transition | source/test backed | Can be evaluated from source tree, packaging artifacts, or automated tests. |
| 29 | Fixed live fixture set | existing live evidence required | Not fully re-run this turn; relies on signed closure/preflight unless separately tested. |
| 30 | Fail-fast missing archive protection without killing the interactive shell | source/test backed | Can be evaluated from source tree, packaging artifacts, or automated tests. |
| 31 | Installer verifies actual installed version | source/test backed | Can be evaluated from source tree, packaging artifacts, or automated tests. |
| 32 | TikTok stable identity survives pagination | source/test backed | Can be evaluated from source tree, packaging artifacts, or automated tests. |
| 33 | Instagram `/reels/` URL normalization | source/test backed | Can be evaluated from source tree, packaging artifacts, or automated tests. |
| 34 | TikTok curl error 35 / TLS is classified correctly | source/test backed | Can be evaluated from source tree, packaging artifacts, or automated tests. |
| 35 | TikTok transport fallback | source/test backed | Can be evaluated from source tree, packaging artifacts, or automated tests. |
| 36 | TikTok extractor process-tree cleanup | source/test backed | Can be evaluated from source tree, packaging artifacts, or automated tests. |
| 37 | TikTok failure returns control to shell | source/test backed | Can be evaluated from source tree, packaging artifacts, or automated tests. |
| 38 | TikTok page-3 checkpoint is preserved on failure | source/test backed | Can be evaluated from source tree, packaging artifacts, or automated tests. |
| 39 | TikTok retry/fallback telemetry | existing live evidence required | Not fully re-run this turn; relies on signed closure/preflight unless separately tested. |
| 40 | Instagram human-mode completion summary | source/test backed | Can be evaluated from source tree, packaging artifacts, or automated tests. |
| 41 | Instagram unified status imports exact catalog total | source/test backed | Can be evaluated from source tree, packaging artifacts, or automated tests. |
| 42 | YouTube batch identifies selected media IDs | source/test backed | Can be evaluated from source tree, packaging artifacts, or automated tests. |
| 43 | Creator status does not truncate typed batch limits | source/test backed | Can be evaluated from source tree, packaging artifacts, or automated tests. |
| 44 | Preserve last exact Full Sync snapshot across Quick Sync | source/test backed | Can be evaluated from source tree, packaging artifacts, or automated tests. |
| 45 | Current and last-exact semantics are visible together | existing live evidence required | Not fully re-run this turn; relies on signed closure/preflight unless separately tested. |
| 46 | No checkpoint regression after transient retry exhaustion | source/test backed | Can be evaluated from source tree, packaging artifacts, or automated tests. |
| 47 | No silent infinite retry | source/test backed | Can be evaluated from source tree, packaging artifacts, or automated tests. |
| 48 | Release contains no cookies, creator data, workspaces or backups | source/test backed | Can be evaluated from source tree, packaging artifacts, or automated tests. |
| 49 | Upgrade removes stale Python bytecode | source/test backed | Can be evaluated from source tree, packaging artifacts, or automated tests. |
| 50 | Project CLI cannot execute an older cached package launcher | source/test backed | Can be evaluated from source tree, packaging artifacts, or automated tests. |
| 51 | Installer failure leaves the current terminal usable | source/test backed | Can be evaluated from source tree, packaging artifacts, or automated tests. |
| 52 | TikTok quiet-period telemetry is understandable | source/test backed | Can be evaluated from source tree, packaging artifacts, or automated tests. |
| 53 | TikTok page and extractor attempts have finite deadlines | source/test backed | Can be evaluated from source tree, packaging artifacts, or automated tests. |
| 54 | TikTok validation commands are paste-safe | source/test backed | Can be evaluated from source tree, packaging artifacts, or automated tests. |
| 55 | Instagram progress distinguishes attempts, successes and failures | source/test backed | Can be evaluated from source tree, packaging artifacts, or automated tests. |
| 56 | Instagram failed items expose a root cause immediately | source/test backed | Can be evaluated from source tree, packaging artifacts, or automated tests. |
| 57 | Instagram max-failure policy is enforced inside the batch | source/test backed | Can be evaluated from source tree, packaging artifacts, or automated tests. |
| 58 | Instagram all-failed batches cannot look successful | source/test backed | Can be evaluated from source tree, packaging artifacts, or automated tests. |
| 59 | Instagram failure report and engine log are surfaced | source/test backed | Can be evaluated from source tree, packaging artifacts, or automated tests. |
| 60 | Progress percentage is not interpreted as success percentage | source/test backed | Can be evaluated from source tree, packaging artifacts, or automated tests. |
| 61 | Legacy exact snapshot is not fabricated | source/test backed | Can be evaluated from source tree, packaging artifacts, or automated tests. |
| 62 | Instagram cookie path preserves the proven default | source/test backed | Can be evaluated from source tree, packaging artifacts, or automated tests. |
| 63 | Known Instagram contract failures are safely requeued | source/test backed | Can be evaluated from source tree, packaging artifacts, or automated tests. |
| 64 | TikTok fallback strategy count is bounded | source/test backed | Can be evaluated from source tree, packaging artifacts, or automated tests. |
| 65 | Repeated TikTok TLS failures open a circuit breaker | source/test backed | Can be evaluated from source tree, packaging artifacts, or automated tests. |
| 66 | TikTok direct fallback ignores hidden proxy configuration | existing live evidence required | Not fully re-run this turn; relies on signed closure/preflight unless separately tested. |
| 67 | TikTok transport root cause is not hidden by secUid fallback text | source/test backed | Can be evaluated from source tree, packaging artifacts, or automated tests. |
| 68 | TikTok catalog page size is separate from processing batch size | source/test backed | Can be evaluated from source tree, packaging artifacts, or automated tests. |
| 69 | Reducing processing batch does not claim to fix catalog transport | source/test backed | Can be evaluated from source tree, packaging artifacts, or automated tests. |
| 70 | Public `media2md creator run` accepts `--retry-failed` | source/test backed | Can be evaluated from source tree, packaging artifacts, or automated tests. |
| 71 | Instagram default Batch does not force a cross-script cookie argument | source/test backed | Can be evaluated from source tree, packaging artifacts, or automated tests. |
| 72 | One real Career Cleo Reel completes through the full public CLI | source/test backed | Can be evaluated from source tree, packaging artifacts, or automated tests. |
| 73 | TikTok direct mode explicitly disables OS/system proxy | source/test backed | Can be evaluated from source tree, packaging artifacts, or automated tests. |
| 74 | macOS system proxy presence is visible without leaking secrets | source/test backed | Can be evaluated from source tree, packaging artifacts, or automated tests. |
| 75 | Old TikTok checkpoint can recover a stable identity from cached media | source/test backed | Can be evaluated from source tree, packaging artifacts, or automated tests. |
| 76 | TikTok partial catalog survives exact-sync failure and is explicitly usable | source/test backed | Can be evaluated from source tree, packaging artifacts, or automated tests. |
| 77 | One shared deadline per TikTok page | source/test backed | Can be evaluated from source tree, packaging artifacts, or automated tests. |
| 78 | No nested TikTok fallback ladder | source/test backed | Can be evaluated from source tree, packaging artifacts, or automated tests. |
| 79 | Last successful TikTok strategy is reused first | existing live evidence required | Not fully re-run this turn; relies on signed closure/preflight unless separately tested. |
| 80 | TikTok full-sync invocation has a total runtime budget | existing live evidence required | Not fully re-run this turn; relies on signed closure/preflight unless separately tested. |
| 81 | TikTok sync can limit pages per invocation | source/test backed | Can be evaluated from source tree, packaging artifacts, or automated tests. |
| 82 | Budget exhaustion pauses instead of failing or running forever | source/test backed | Can be evaluated from source tree, packaging artifacts, or automated tests. |
| 83 | TikTok attempt outcomes are explicit | source/test backed | Can be evaluated from source tree, packaging artifacts, or automated tests. |
| 84 | TikTok run progress is visible across pages | source/test backed | Can be evaluated from source tree, packaging artifacts, or automated tests. |
| 85 | Stable-ID catalog payload may reuse the already-known human handle | source/test backed | Can be evaluated from source tree, packaging artifacts, or automated tests. |
| 86 | Stable-ID success must not trigger a second handle-profile fetch | source/test backed | Can be evaluated from source tree, packaging artifacts, or automated tests. |
| 87 | Page-budget exhaustion returns a resumable partial result, not a hard error | source/test backed | Can be evaluated from source tree, packaging artifacts, or automated tests. |
| 88 | Clean pause cannot advance or truncate the checkpoint | source/test backed | Can be evaluated from source tree, packaging artifacts, or automated tests. |
| 89 | TikTok stable-ID metadata fallback does not spend the remaining page budget on duplicate discovery | source/test backed | Can be evaluated from source tree, packaging artifacts, or automated tests. |
| 90 | Successful TikTok transport persists across CLI invocations | existing live evidence required | Not fully re-run this turn; relies on signed closure/preflight unless separately tested. |
| 91 | TikTok page-wide circuit breaker | source/test backed | Can be evaluated from source tree, packaging artifacts, or automated tests. |
| 92 | No extractor starts when remaining page budget is below five seconds | source/test backed | Can be evaluated from source tree, packaging artifacts, or automated tests. |
| 93 | Page deadline cannot be extended by a forced five-second minimum | source/test backed | Can be evaluated from source tree, packaging artifacts, or automated tests. |
| 94 | `creator_identifiers.sec_uid` remains visible in paused summaries | source/test backed | Can be evaluated from source tree, packaging artifacts, or automated tests. |
| 95 | Maximum-page pause reason is semantically correct | source/test backed | Can be evaluated from source tree, packaging artifacts, or automated tests. |
| 96 | v0.7.9 does not change live-passing Instagram or YouTube paths | source/test backed | Can be evaluated from source tree, packaging artifacts, or automated tests. |
| 97 | Old checkpoints under enabled macOS proxies prefer isolated direct transport | source/test backed | Can be evaluated from source tree, packaging artifacts, or automated tests. |
| 98 | Resumed TikTok sync must not use `--playlist-start` as the primary deep-pagination mechanism | source/test backed | Can be evaluated from source tree, packaging artifacts, or automated tests. |
| 99 | TikTok cursor is recovered from the oldest known checkpoint item | source/test backed | Can be evaluated from source tree, packaging artifacts, or automated tests. |
| 100 | TikTok cursor and device ID persist across CLI invocations | source/test backed | Can be evaluated from source tree, packaging artifacts, or automated tests. |
| 101 | One cursor response is normalized and checkpointed before the next request | source/test backed | Can be evaluated from source tree, packaging artifacts, or automated tests. |
| 102 | Cursor backend bypasses macOS system proxy | source/test backed | Can be evaluated from source tree, packaging artifacts, or automated tests. |
| 103 | Cursor API completion establishes an exact TikTok total | existing live evidence required | Not fully re-run this turn; relies on signed closure/preflight unless separately tested. |
| 104 | Cursor request failure returns a resumable partial result | source/test backed | Can be evaluated from source tree, packaging artifacts, or automated tests. |
| 105 | Legacy bounded yt-dlp paging remains a fallback, not the default resume engine | source/test backed | Can be evaluated from source tree, packaging artifacts, or automated tests. |
| 106 | Cursor summary preserves the command-start total | source/test backed | Can be evaluated from source tree, packaging artifacts, or automated tests. |
| 107 | Cursor run delta is accurate | source/test backed | Can be evaluated from source tree, packaging artifacts, or automated tests. |
| 108 | Every native cursor attempt emits a result | source/test backed | Can be evaluated from source tree, packaging artifacts, or automated tests. |
| 109 | Partial TikTok Full Sync skips legacy Quick Sync before Batch | historical failure retained | Audit item preserved by design; not an active blocker if replaced by later green gate. |
| 110 | TikTok media download tries isolated direct transport first under macOS proxies | source/test backed | Can be evaluated from source tree, packaging artifacts, or automated tests. |
| 111 | TikTok media-download transport success persists across items/runs | source/test backed | Can be evaluated from source tree, packaging artifacts, or automated tests. |
| 112 | TikTok per-item transport cascade is bounded | source/test backed | Can be evaluated from source tree, packaging artifacts, or automated tests. |
| 113 | Transport fallback does not count as an item failure | source/test backed | Can be evaluated from source tree, packaging artifacts, or automated tests. |
| 114 | Early max-failure stop prints a final summary | source/test backed | Can be evaluated from source tree, packaging artifacts, or automated tests. |
| 115 | Stored TikTok identities survive Quick/Partial summaries | source/test backed | Can be evaluated from source tree, packaging artifacts, or automated tests. |
| 116 | v0.8.1 does not replace the v0.8.0 cursor Catalog engine | source/test backed | Can be evaluated from source tree, packaging artifacts, or automated tests. |
| 117 | Source, wheel, and release kit contain no bundled runtime database | source/test backed | Can be evaluated from source tree, packaging artifacts, or automated tests. |
| 118 | Both public Creator Run surfaces use a single shared implementation | source/test backed | Can be evaluated from source tree, packaging artifacts, or automated tests. |
| 119 | The real public `./bin/media2md` skips Quick Sync for a partial TikTok cursor Catalog | existing live evidence required | Not fully re-run this turn; relies on signed closure/preflight unless separately tested. |
| 120 | Public CLI regression cannot silently invoke Registry sync | source/test backed | Can be evaluated from source tree, packaging artifacts, or automated tests. |
| 121 | Batch starts without legacy transport telemetry | source/test backed | Can be evaluated from source tree, packaging artifacts, or automated tests. |
| 122 | Historical false-green acceptance is corrected | source/test backed | Can be evaluated from source tree, packaging artifacts, or automated tests. |
| 123 | Live-passing Cursor and media-download engines remain unchanged | source/test backed | Can be evaluated from source tree, packaging artifacts, or automated tests. |
| 124 | v0.8.2 public CLI skips legacy Quick Sync while Full Sync is partial | existing live evidence required | Not fully re-run this turn; relies on signed closure/preflight unless separately tested. |
| 125 | StartupBell Full Cursor catalog reaches an exact terminal state | existing live evidence required | Not fully re-run this turn; relies on signed closure/preflight unless separately tested. |
| 126 | Full exact snapshot is persisted | existing live evidence required | Not fully re-run this turn; relies on signed closure/preflight unless separately tested. |
| 127 | Quick Sync must not downgrade a proven TikTok exact catalog | source/test backed | Can be evaluated from source tree, packaging artifacts, or automated tests. |
| 128 | Exact TikTok Catalog skips hidden pre-run Quick Sync | source/test backed | Can be evaluated from source tree, packaging artifacts, or automated tests. |
| 129 | Upgrade repairs only a safely matching downgraded exact state | source/test backed | Can be evaluated from source tree, packaging artifacts, or automated tests. |
| 130 | A new Full Sync after checkpoint deletion uses Registry-backed Cursor bootstrap | source/test backed | Can be evaluated from source tree, packaging artifacts, or automated tests. |
| 131 | TikTok type-level exactness is visible | source/test backed | Can be evaluated from source tree, packaging artifacts, or automated tests. |
| 132 | TikTok last-full type total remains visible after Quick summaries | source/test backed | Can be evaluated from source tree, packaging artifacts, or automated tests. |
| 133 | v0.8.3 exact lifecycle requires live verification | historical failure retained | Audit item preserved by design; not an active blocker if replaced by later green gate. |
| 134 | A zero-page Full rebuild failure cannot downgrade the active exact TikTok catalog | source/test backed | Can be evaluated from source tree, packaging artifacts, or automated tests. |
| 135 | Partial Full rebuild pages remain staged until terminal completion | source/test backed | Can be evaluated from source tree, packaging artifacts, or automated tests. |
| 136 | Rebuild pause telemetry distinguishes active baseline from staged items | source/test backed | Can be evaluated from source tree, packaging artifacts, or automated tests. |
| 137 | Completed Full Sync cursor device ID survives checkpoint deletion | source/test backed | Can be evaluated from source tree, packaging artifacts, or automated tests. |
| 138 | Upgrade migrates a v0.8.3 failed rebuild safely | source/test backed | Can be evaluated from source tree, packaging artifacts, or automated tests. |
| 139 | Retryable failed items remain counted in the real processing queue | source/test backed | Can be evaluated from source tree, packaging artifacts, or automated tests. |
| 140 | A paused or failed TikTok Full rebuild preserves the active exact baseline | existing live evidence required | Not fully re-run this turn; relies on signed closure/preflight unless separately tested. |
| 141 | Batch remains usable after staged rebuild pause | existing live evidence required | Not fully re-run this turn; relies on signed closure/preflight unless separately tested. |
| 142 | Duplicate Creator Run for the same provider/creator is rejected before work starts | source/test backed | Can be evaluated from source tree, packaging artifacts, or automated tests. |
| 143 | Duplicate Full Sync for the same provider/creator is rejected | source/test backed | Can be evaluated from source tree, packaging artifacts, or automated tests. |
| 144 | Different creators and Sync versus Run are not globally serialized | source/test backed | Can be evaluated from source tree, packaging artifacts, or automated tests. |
| 145 | Direct media processing cannot race Creator Run for the same media ID | source/test backed | Can be evaluated from source tree, packaging artifacts, or automated tests. |
| 146 | Backup cannot run while a live mutation is active | source/test backed | Can be evaluated from source tree, packaging artifacts, or automated tests. |
| 147 | State backup is consistent and independently verifiable | source/test backed | Can be evaluated from source tree, packaging artifacts, or automated tests. |
| 148 | Backup excludes browser/session secrets and bulky derived media | source/test backed | Can be evaluated from source tree, packaging artifacts, or automated tests. |
| 149 | Existing v0.8.4 state and exact TikTok catalog survive upgrade | source/test backed | Can be evaluated from source tree, packaging artifacts, or automated tests. |
| 150 | Duplicate-run lock behaves on macOS `fcntl` | existing live evidence required | Not fully re-run this turn; relies on signed closure/preflight unless separately tested. |
| 151 | Public package publication | source/test backed | Can be evaluated from source tree, packaging artifacts, or automated tests. |
| 152 | Public v1.0.0 platform matrix | source/test backed | Can be evaluated from source tree, packaging artifacts, or automated tests. |
| 153 | v0.8.5 portable backup verifies on the real project | historical failure retained | Audit item preserved by design; not an active blocker if replaced by later green gate. |
| 154 | Backup verification accepts legitimate zero-byte files | source/test backed | Can be evaluated from source tree, packaging artifacts, or automated tests. |
| 155 | Operational lock and partial files are excluded from portable backups | existing live evidence required | Not fully re-run this turn; relies on signed closure/preflight unless separately tested. |
| 156 | Source release contains no bundled runtime lock artifacts | source/test backed | Can be evaluated from source tree, packaging artifacts, or automated tests. |
| 157 | Exact StartupBell baseline survived the v0.8.5 upgrade | existing live evidence required | Not fully re-run this turn; relies on signed closure/preflight unless separately tested. |
| 158 | Duplicate Creator Run lock works on macOS | existing live evidence required | Not fully re-run this turn; relies on signed closure/preflight unless separately tested. |
| 159 | v0.8.6 backup creation and verification pass on the real project | existing live evidence required | Not fully re-run this turn; relies on signed closure/preflight unless separately tested. |
| 160 | One real TikTok item completes after the v0.8.6 upgrade | existing live evidence required | Not fully re-run this turn; relies on signed closure/preflight unless separately tested. |
| 161 | Public package publication | source/test backed | Can be evaluated from source tree, packaging artifacts, or automated tests. |
| 162 | Public v1.0.0 platform matrix | source/test backed | Can be evaluated from source tree, packaging artifacts, or automated tests. |
| 163 | The complete one-shot evidence ZIP and SHA are verified before diagnosis | source/test backed | Can be evaluated from source tree, packaging artifacts, or automated tests. |
| 164 | Authenticated Instagram `/accounts/edit/` cannot be classified as challenge because application JavaScript contains `checkpoint` | existing live evidence required | Not fully re-run this turn; relies on signed closure/preflight unless separately tested. |
| 165 | TikTok `media inspect` uses bounded processing transports and remains useful during transient transport failure | historical failure retained | Audit item preserved by design; not an active blocker if replaced by later green gate. |
| 166 | A YouTube channel with no Videos tab but Shorts completes exact Full Sync | existing live evidence required | Not fully re-run this turn; relies on signed closure/preflight unless separately tested. |
| 167 | Resuming staged TikTok exact rebuild cannot publish partial active Catalog | existing live evidence required | Not fully re-run this turn; relies on signed closure/preflight unless separately tested. |
| 168 | Reprocessing an existing current media item preserves Creator exactness | existing live evidence required | Not fully re-run this turn; relies on signed closure/preflight unless separately tested. |
| 169 | OpenClaw isolated Cron does not fail for missing delivery recipient | existing live evidence required | Not fully re-run this turn; relies on signed closure/preflight unless separately tested. |
| 170 | Advisory GitHub update discovery cannot fail a successful Scheduler tick | existing live evidence required | Not fully re-run this turn; relies on signed closure/preflight unless separately tested. |
| 171 | Closure tooling avoids false reds from absent dev pytest, blank Short URL, and variable bounded pause reasons | existing live evidence required | Not fully re-run this turn; relies on signed closure/preflight unless separately tested. |
| 172 | v0.9.0 closes every product failure from the v0.8.6 one-shot evidence | historical failure retained | Audit item preserved by design; not an active blocker if replaced by later green gate. |
| 173 | HTTP 200 on TikTok authenticated `/setting` is not a challenge merely because bundled JavaScript contains captcha strings | existing live evidence required | Not fully re-run this turn; relies on signed closure/preflight unless separately tested. |
| 174 | TikTok metadata inspection remains successful after bounded live transports are exhausted when verified local metadata exists | existing live evidence required | Not fully re-run this turn; relies on signed closure/preflight unless separately tested. |
| 175 | TikTok Doctor distinguishes transient live-probe failure from an operational pipeline proven by a recent real completion | existing live evidence required | Not fully re-run this turn; relies on signed closure/preflight unless separately tested. |
| 176 | v0.9.1 closes all remaining v0.9.0 closure failures without regressing exact state, backup, YouTube, Instagram, or OpenClaw | existing live evidence required | Not fully re-run this turn; relies on signed closure/preflight unless separately tested. |
