# Media2MD v0.8.5 Strict Acceptance

Status legend:

- **PASS**: implemented and verified by automated, package, or isolated-install tests.
- **PASS-LIVE**: verified on Daniel's real Mac, account, network, and existing data.
- **LIVE**: implemented but requires the stated real-Mac validation.
- **PENDING**: intentionally deferred.

| # | Acceptance item | Status | Evidence / remaining requirement |
|---:|---|---|---|
| 140 | A paused or failed TikTok Full rebuild preserves the active exact baseline | PASS-LIVE | v0.8.4 live gate kept `TRACKED 1159`, `EXACT current=true`, and `last_full_total=1159` after 12 staged cursor pages; summary reported `baseline_preserved=true`, `rebuild_in_progress=true`, and `staged_total=173`. |
| 141 | Batch remains usable after staged rebuild pause | PASS-LIVE | The immediately following real StartupBell Batch processed 5/5 with zero failures and advanced `DONE` from 92 to 97. |
| 142 | Duplicate Creator Run for the same provider/creator is rejected before work starts | PASS | Per-creator `creator-run` lock and regression test verify owner metadata and no call into the unlocked runner. |
| 143 | Duplicate Full Sync for the same provider/creator is rejected | PASS | Per-creator `creator-sync` lock wraps every Registry sync path. |
| 144 | Different creators and Sync versus Run are not globally serialized | PASS | Operation locks are scoped; live work shares the maintenance lock and unrelated scopes may coexist. |
| 145 | Direct media processing cannot race Creator Run for the same media ID | PASS | `media-process` lock wraps `process-registered` by provider/external ID. |
| 146 | Backup cannot run while a live mutation is active | PASS | Shared/exclusive maintenance lock regression rejects an exclusive backup while a live operation holds a shared lock. |
| 147 | State backup is consistent and independently verifiable | PASS | SQLite online backup, ZIP CRC, SHA-256 manifest, file sizes, and `PRAGMA integrity_check` are verified in regression tests. |
| 148 | Backup excludes browser/session secrets and bulky derived media | PASS | Manifest and archive tests exclude `data/secrets`, workspace, downloads, transcripts, Markdown, and logs. |
| 149 | Existing v0.8.4 state and exact TikTok catalog survive upgrade | LIVE | Install on Daniel's current project, verify backup, confirm `EXACT current=true`, and run one real item. |
| 150 | Duplicate-run lock behaves on macOS `fcntl` | LIVE | Run the deterministic lock-holder gate in `MEDIA2MD_V085_INSTALL.md`; the second Creator Run must exit 2 before `BATCH_START`. |
| 151 | Public package publication | PENDING | GitHub Release, PyPI, npm, and Homebrew remain user-authorized release steps. |
| 152 | Public v1.0.0 platform matrix | PENDING | Instagram/TikTok auth Doctor, YouTube long-video chunk evidence, Shorts output, and OpenClaw scheduling still require the full matrix. |

## Release decision

v0.8.5 is a **private-production release candidate**. It may be promoted to v0.9.0 private production only after items 149 and 150 pass on the existing Mac project. Public v1.0.0 remains blocked by item 152.
