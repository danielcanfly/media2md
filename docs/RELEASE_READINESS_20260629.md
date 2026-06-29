# Media2MD Release Readiness 2026-06-29

This document captures the current release state after the package-first,
managed-runtime, and real-home smoke passes completed on June 29, 2026.

## Decision Summary

Media2MD is now in a state where a production PyPI release is reasonable.

The main reasons are:

- source repo is clean and committed on `main`
- build artifacts pass `python -m build` and `twine check`
- package-first managed runtime bootstrap was exercised
- legacy project config seeding into the managed runtime was exercised
- TikTok package-first creator flow was exercised
- Instagram real-home auth and `media add --process-now` were exercised
- YouTube doctor/public-first pipeline was exercised

## Repository State

- Branch: `main`
- Working tree: clean
- HEAD commit: `17f5954aed1b2dba18db5d94ee6aba0e66a2eb93`

Recent stabilization commits:

- `6de0d29c62fbf359c87138b1c44894bd3d28461f`
- `64c45292ce6f41c3331458b2b8d5264ba9448b19`
- `19fa72e6aad281d08a6be49c8352f22976d1ada5`
- `905543640b30f0302ee982e21618dcba3f2f635d`
- `17f5954aed1b2dba18db5d94ee6aba0e66a2eb93`

## Artifact State

Current local artifacts:

- `dist/media2md-0.9.1.tar.gz`
- `dist/media2md-0.9.1-py3-none-any.whl`

Current SHA256:

- sdist: `27ebab25bd511f5dfc9cf5751f3c53f67d55422f94759d31dbe6b7761d7fb15a`
- wheel: `9a92575aab1af2e2bb8ed79c57ce96e4b079f219a5597973a82aa0f361d00dd2`

## Validation Completed

### Automated checks

- `pytest` targeted release/stability suite: passed
- `python -m compileall src/media2md`: passed
- `python -m build`: passed
- `python -m twine check dist/*.whl dist/*.tar.gz`: passed

### Fresh package smoke

Fresh isolated wheel install completed successfully.

Validated:

- `media2md version`
- managed runtime bootstrap
- `media2md runtime status`
- `media2md auth status --output ndjson`

### Managed runtime migration behavior

Validated:

- legacy project registry can seed managed runtime config
- package-first startup can inherit prior auth/config intent

Important caveat:

- isolated `HOME` environments can still fail live browser-cookie verification
  because decryption depends on the real OS/browser environment

That caveat is expected and documented in `docs/RELEASE_PROCESS.md`.

### TikTok checks

Validated:

- package-first creator flow runs
- runtime-budget exhaustion now reports `paused_runtime_limit` instead of a fake failure
- authenticated/real-home flow can complete once runtime dependencies are present

### Instagram checks

Validated:

- real-home `auth verify instagram` succeeded
- real-home `media add <reel> --process-now` succeeded
- reels without audio streams no longer fail the whole pipeline
- metadata fallback failures now produce actionable guidance instead of opaque backend crashes

### YouTube checks

Validated:

- `doctor youtube-access --video-id 0lJKucu6HJc` succeeded
- public-first pipeline remains viable even when auth is not required

## Known Non-Blocking Debt

These items remain non-blocking unless release policy changes:

- `ruff` debt remains
- `mypy` debt remains
- not every cross-provider long-tail scenario was re-run in one single monolithic sweep

## Remaining Recommended Steps Before Clicking Publish

These are recommended, not currently hard blockers:

1. Re-read README from a new-user perspective one last time
2. Confirm PyPI trusted publishing settings still match:
   - workflow name
   - repo
   - environment
3. Trigger the production publish workflow intentionally
4. Run one post-publish install smoke from production PyPI

## Publish Recommendation

Recommendation: `go`

Reason:

- the package path is no longer obviously brittle
- real-home Instagram flow was repaired and verified
- TikTok and YouTube core paths were already exercised
- release/process documentation now reflects the real managed-runtime and auth behavior
