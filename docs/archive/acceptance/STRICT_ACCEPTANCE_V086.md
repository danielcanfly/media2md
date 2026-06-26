# Media2MD v0.8.6 Strict Acceptance

Status legend:

- **PASS**: verified by automated, source-package, or isolated-install tests.
- **PASS-LIVE**: verified on Daniel's real Mac, account, network, and existing data.
- **LIVE**: implemented but still requires the stated real-Mac validation.
- **FAIL-LIVE-HISTORICAL**: a real defect found in an older release; retained to prevent false-green history.
- **PENDING**: intentionally deferred.

| # | Acceptance item | Status | Evidence / remaining requirement |
|---:|---|---|---|
| 153 | v0.8.5 portable backup verifies on the real project | FAIL-LIVE-HISTORICAL | Live verification failed with `Backup size mismatch: config/.creators.lock`. The verifier converted a valid zero-byte size to `-1` through a falsy-value fallback. |
| 154 | Backup verification accepts legitimate zero-byte files | PASS | Regression includes a zero-byte state marker and requires successful hash, size, ZIP CRC, and SQLite verification. |
| 155 | Operational lock and partial files are excluded from portable backups | PASS | `*.lock`, `*.pid`, `*.tmp`, `*.part`, `.DS_Store`, and AppleDouble files are excluded; regression specifically forbids `config/.creators.lock`. |
| 156 | Source release contains no bundled runtime lock artifacts | PASS | The source tree and release manifest exclude `src/media2md/bundle/logs/locks`. |
| 157 | Exact StartupBell baseline survived the v0.8.5 upgrade | PASS-LIVE | Live status retained `TRACKED 1159`, `EXACT current=true`, `DONE 97`, and `LEFT 1062`. |
| 158 | Duplicate Creator Run lock works on macOS | PASS-LIVE | A real second invocation was rejected before `BATCH_START` with active owner PID and exit-path telemetry. |
| 159 | v0.8.6 backup creation and verification pass on the real project | LIVE | Run Gate B in `MEDIA2MD_V086_INSTALL.md`; both CREATED and VERIFIED markers are required. |
| 160 | One real TikTok item completes after the v0.8.6 upgrade | LIVE | The prior v0.8.5 attempt was blocked by the intentionally held test lock, so it produced no media-processing evidence. Run Gate C after confirming that PID is gone. |
| 161 | Public package publication | PENDING | GitHub Release, PyPI, npm, and Homebrew remain user-authorized release steps. |
| 162 | Public v1.0.0 platform matrix | PENDING | Instagram/TikTok auth Doctor, YouTube long-video chunks, Shorts output, and OpenClaw scheduling still require the full matrix. |

## Release decision

v0.8.6 remains a **private-production release candidate** until items 159 and 160 pass live. Historical item 153 remains red by design and is closed only by the v0.8.6 replacement evidence, never rewritten as a v0.8.5 pass.
