# Media2MD v0.7.1 Strict Acceptance

Status legend: `PASS` implemented and covered by package tests, `LIVE` requires the user's real platform account or Apple Silicon runtime, `PENDING` intentionally deferred.

| # | Acceptance item | Status | v0.7.1 result |
|---:|---|---|---|
| 1 | Clean GitHub-downloadable source repository | PASS | Reproducible source ZIP, wheel, sdist, checksums, CI files, license and security docs are present. Public push remains a release operation. |
| 2 | Base package plus optional modules | PASS | Base, Instagram, YouTube, TikTok, MLX, browser-auth, OpenClaw and all extras are defined. |
| 3 | Agent-controlled daily operation | PASS | Read/write operations have stable CLI and NDJSON contracts. Password, 2FA, CAPTCHA, platform challenges and destructive actions remain human-authorized. |
| 4 | Three-platform authentication | LIVE | Unified profile/connect/verify flows exist. YouTube was previously verified live; Instagram and TikTok require live verification. |
| 5 | Three-platform authentication-state detection | LIVE | Auth state, verification time, required action and guidance are implemented; Instagram/TikTok live expiry/challenge cases remain. |
| 6 | Browser-cookie refresh and lost-session guidance | LIVE | Renewed browser cookies are re-read automatically. A truly logged-out session is detected and requires the user to sign in. |
| 7 | Three-platform bulk processing | LIVE | Batch, drain, retry, de-duplication and checkpoint mechanics exist; requested creator-scale runs remain. |
| 8 | YouTube long-video split/transcribe/reassemble | LIVE | Chunking, checkpoint resume and merge are covered by tests; `J92OMF6HUaM` remains the live Apple Silicon E2E fixture. |
| 9 | OpenClaw cron | LIVE | Skill, install/status and scheduler tick exist; real cron creation and trigger remain. |
| 10 | Three-platform Doctor | LIVE | YouTube was previously verified live. Instagram/TikTok need real sessions and downloads. |
| 11 | GitHub Release update/rollback | PENDING | Deferred by user request. |
| 12 | PyPI/npm/Homebrew publication | PENDING | Deferred by user request. Assets are buildable but not publicly published. |
| 13 | Creator settings/status | PASS | Creator state, policy, totals, exactness and processing state are queryable. |
| 14 | System status/settings | PASS | System, runtime, settings, authentication and agent status are queryable. |
| 15 | Agent changes public settings | PASS | Public settings and creator policies can be changed through validated CLI operations. |
| 16 | Single YouTube Shorts URL | LIVE | Parser, identity attachment and typed output are implemented; `0jttCFj5ZWM` is the live fixture. |
| 17 | Short attaches to canonical creator | PASS | Channel identity is canonical; manual Short registration updates the same creator and invalidates stale exact totals. |
| 18 | Creator sync combines `/videos` and `/shorts` | PASS | Both surfaces are enumerated, merged and de-duplicated by Video ID. |
| 19 | Separate video and Shorts totals | PASS | Creator schema stores per-type totals and exactness flags plus combined total. |
| 20 | Upload/delete total refresh | LIVE | Quick sync discovers new items and marks totals non-exact; full sync reconciles removals and restores exact totals. Live fixture: `@TheProductFolks`. |
| 21 | TikTok creator exact total | LIVE | Full pagination is implemented; live fixture: `@startupbell`. |
| 22 | Instagram Reels exact total | LIVE | Full pagination is implemented; live fixture: `career_cleo`. |
| 23 | Per-platform/per-creator batch settings | PASS | Human and agent can set typed batch quotas through CLI. |
| 24 | Typed YouTube batch quotas | PASS | Shorts, normal videos, long videos and streams have independent quotas. |
| 25 | Long YouTube video gets an exclusive batch | PASS | When a pending long video exists, selection returns only the configured long-video quota, default 1. |
| 26 | Typed YouTube Markdown folders | PASS | New output is separated into `videos/`, `shorts/` and `streams/`; frontmatter records media type and processing class. |
| 27 | Manual Short keeps creator totals coherent | PASS | Tracked and Shorts totals update; exactness is set false until the next full catalog sync. |
| 28 | Quick/full exactness transitions | LIVE | State model and tests exist; live upload/removal transition remains. |
| 29 | Fixed requested validation set | LIVE | Fixtures: The Product Folks, StartupBell, Career Cleo, Short `0jttCFj5ZWM`, long video `J92OMF6HUaM`. |

## Default typed batches

| Content class | Default batch size |
|---|---:|
| TikTok video | 100 |
| Instagram Reel | 30 |
| YouTube Short | 30 |
| YouTube normal video | 5 |
| YouTube long video, at least 45 minutes | 1 |
| YouTube stream/archive | 1 |

Items 11 and 12 remain pending and do not block the v0.7.1 functional validation round.
