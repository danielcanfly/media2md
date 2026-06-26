# Media2MD v0.7.2 Strict Acceptance

Status legend: `PASS` implemented and covered by package tests, `LIVE` requires the user's real platform account or Apple Silicon runtime, `PENDING` intentionally deferred.

| # | Acceptance item | Status | v0.7.2 result |
|---:|---|---|---|
| 1 | Clean GitHub-downloadable source repository | PASS | Reproducible source ZIP, wheel, sdist, checksums, CI, license and security files are present. Public push is still a release operation. |
| 2 | Base package plus optional modules | PASS | Base, Instagram, YouTube, TikTok, MLX, browser-auth, OpenClaw and `all` extras are defined. |
| 3 | Agent-controlled daily operation | PASS | Stable CLI and NDJSON contracts exist. Password, 2FA, CAPTCHA, platform challenges and destructive actions remain human-authorized. |
| 4 | Three-platform authentication | LIVE | YouTube previously passed live verification. Instagram and TikTok still require live profile/connect/verify. |
| 5 | Three-platform authentication-state detection | LIVE | State, verification time, required action and guidance exist; Instagram/TikTok live expiry/challenge cases remain. |
| 6 | Browser-cookie refresh and lost-session guidance | LIVE | Browser-renewed cookies are re-read. Fully logged-out sessions require user login. |
| 7 | Three-platform bulk processing | LIVE | Batch, retry, de-duplication and checkpoints exist. Requested large creator runs remain. |
| 8 | YouTube long-video split/transcribe/reassemble | LIVE | Chunking and merge are tested; `J92OMF6HUaM` remains the live Apple Silicon E2E fixture. |
| 9 | OpenClaw cron | LIVE | Skill and scheduler commands exist; real cron creation and trigger remain. |
| 10 | Three-platform Doctor | LIVE | YouTube passed previously; Instagram and TikTok need real sessions. |
| 11 | GitHub Release update/rollback | PENDING | Deferred by user request. |
| 12 | PyPI/npm/Homebrew publication | PENDING | Deferred by user request. |
| 13 | Creator settings/status | PASS | Creator policy, totals, exactness and processing state are queryable. |
| 14 | System status/settings | PASS | Runtime, settings, authentication and agent status are queryable. |
| 15 | Agent changes public settings | PASS | Public settings and creator policies are changed through validated CLI operations. |
| 16 | Single YouTube Shorts URL | LIVE | The old v0.6.7 pipeline processed the fixture, but v0.7.2 typed folder/frontmatter output still requires live re-test. |
| 17 | Short attaches to canonical creator | PASS | Canonical channel identity and count invalidation are implemented. |
| 18 | Creator sync combines `/videos` and `/shorts` | PASS | Both surfaces are enumerated, merged and de-duplicated by video ID. |
| 19 | Separate video and Shorts totals | PASS | Per-type totals and exactness flags are stored. |
| 20 | Upload/delete total refresh | LIVE | Quick/full state transitions exist; live creator change remains. |
| 21 | TikTok creator exact total | LIVE | v0.7.2 now carries the first-page secUid/user ID into later pages; `@startupbell` must be re-run live. |
| 22 | Instagram Reels exact total | LIVE | `/reels/` URL normalization is fixed; `career_cleo` must be re-run live. |
| 23 | Per-platform/per-creator batch settings | PASS | Typed batch policies are accepted once v0.7.2 is actually installed. |
| 24 | Typed YouTube batch quotas | PASS | Shorts, normal, long and stream quotas are independent. |
| 25 | Long YouTube video gets an exclusive batch | PASS | Pending long video selection is exclusive, default 1. |
| 26 | Typed YouTube Markdown folders | PASS | New output separates `videos/`, `shorts/`, and `streams/`. |
| 27 | Manual Short keeps creator totals coherent | PASS | Counts update and exactness is invalidated until full sync. |
| 28 | Quick/full exactness transitions | LIVE | State model is tested; live upload/removal remains. |
| 29 | Fixed requested validation set | LIVE | The Product Folks, StartupBell, Career Cleo, Short `0jttCFj5ZWM`, long video `J92OMF6HUaM`. |
| 30 | Upgrade aborts when archive is missing | PASS | Installation instructions use `set -euo pipefail` and `test -f`; old-version reinstall cannot continue silently. |
| 31 | Installer verifies actual installed version | PASS | Source version and post-install `media2md 0.7.2` are checked. |
| 32 | TikTok pagination retains stable identity | PASS | secUid/user ID is checkpointed and used as `tiktokuser:<id>` after page one. |
| 33 | Instagram creator URL crosses legacy boundary safely | PASS | Full profile and `/reels/` URLs are normalized to username first. |

Items 11 and 12 remain pending and do not block the v0.7.2 functional validation round.
