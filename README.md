# Media2MD 0.9.1

Media2MD downloads permitted Instagram, YouTube, and TikTok media, transcribes speech locally, and produces structured Markdown. It is CLI-first and exposes stable machine-readable status for agents.

## Install

PyPI publication is intentionally pending. Install the local release wheel or source package for now.

Base CLI from the local wheel:
```bash
python -m pip install ./media2md-0.9.1-py3-none-any.whl
```

Choose optional modules from the local wheel:
```bash
python -m pip install "./media2md-0.9.1-py3-none-any.whl[instagram]"
python -m pip install "./media2md-0.9.1-py3-none-any.whl[youtube,mlx]"
python -m pip install "./media2md-0.9.1-py3-none-any.whl[tiktok]"
python -m pip install "./media2md-0.9.1-py3-none-any.whl[all]"
```

For an existing `~/instagram-to-md` project, use `MEDIA2MD_V091_INSTALL.md`. The documented upgrade runs strict mode inside a subshell, clears stale bytecode, verifies package/script/CLI versions, and never intentionally terminates the caller's interactive shell.

Initialize the managed runtime:
```bash
media2md init --language zh-TW --markdown-language zh-TW --timezone Asia/Tokyo --non-interactive
media2md doctor all
```

Existing project migration:
```bash
media2md runtime import --from-project ~/instagram-to-md
```




## v0.9.1 consolidated private-production candidate

- Creator Sync and Creator Run use separate per-creator locks. Two Batch invocations for the same creator cannot run at once, while a staged catalog rebuild and processing may still coexist safely.
- Individual media processing is locked by provider and media ID, preventing duplicate download/transcription work across direct URL and Creator Run paths.
- Live commands hold a shared maintenance lock. `data backup` and destructive maintenance require an exclusive lock, so snapshots are taken only from an idle, consistent state.
- State backups use SQLite's online backup API, verify every database with `PRAGMA integrity_check`, include Catalog/checkpoint/config state, and intentionally exclude browser/session secrets, Markdown, media, transcripts, workspaces, and logs.
- v0.9.1 retains the live-proven zero-byte backup fix and operational-artifact exclusions from v0.8.6.
- Valid Instagram `/accounts/edit/` sessions no longer false-trigger challenge state.
- Valid TikTok `/setting` sessions no longer false-trigger challenge state because generic captcha strings exist in application JavaScript.
- TikTok metadata inspection falls back to verified local metadata or direct oEmbed only after bounded live transports fail, and reports the selected source.
- TikTok Doctor reuses the production processing cascade and can report a transparent degraded-ready state backed by a recent real completed artifact.
- TikTok metadata inspection now shares the bounded live-processing transport cascade.
- YouTube channels with only Shorts are represented as an exact empty Videos surface plus an exact Shorts surface.
- Resumed exact TikTok rebuild checkpoints remain staged and can never downgrade the active exact baseline.
- OpenClaw isolated Cron jobs default to local no-delivery execution, and advisory GitHub update checks cannot fail scheduler work.

```bash
media2md data backup --destination ~/media2md-backups
media2md data verify-backup ~/media2md-backups/media2md-state-YYYYMMDDTHHMMSSZ.zip
```

The real v0.8.4 StartupBell gate preserved `EXACT current=true` and 1,159 tracked items through a bounded 12-page staged rebuild, then completed the following five-item Batch with zero failures.

## v0.8.4 staged exact rebuilds

- A Full rebuild started from an exact TikTok catalog is now staged entirely in the cursor checkpoint. The active exact catalog remains published and processable until the rebuild reaches `hasMorePrevious=false`.
- Cursor request failure, runtime pause, repeated-page protection, or a zero-page 403 no longer downgrades `current_total_exact` or `media_type_totals_exact`. Pause summaries expose `baseline_preserved=true`, `rebuild_in_progress=true`, and `staged_total`.
- The last successful TikTok cursor `device_id` is persisted independently of the transient checkpoint and reused for later Full rebuilds.
- `stopped_max_failures` summaries now count failed retryable items in the real remaining queue instead of subtracting every processed row.

## v0.8.3 public Creator Run convergence

- The public `./bin/media2md creator run` and compatibility `social2md.py` surfaces now call one shared pre-run catalog decision.
- A partial TikTok cursor Full Sync with tracked media emits `AUTO_SYNC_SKIPPED reason=full_catalog_in_progress` and starts Batch immediately, without the legacy profile Quick Sync.
- A subprocess regression executes the real `bin/media2md` entrypoint against a partial TikTok Registry and fails if `registry sync`, `SYNC_NETWORK_CONTEXT`, or `sync_mode=quick` appears.
- The v0.8.1 acceptance record is corrected from a false PASS to a live FAIL; v0.8.3 keeps the proven cursor and bounded per-item download engines unchanged.

## v0.8.1 TikTok Batch transport and reporting

- v0.8.1 introduced the intended partial-catalog skip in the compatibility surface, but live public-CLI validation exposed a duplicate implementation that still ran Quick Sync. v0.8.3 converges both surfaces on the shared decision.
- TikTok media downloads use a bounded transport cascade. On Macs with system proxies enabled, `direct-plain` (`--ignore-config --proxy ""`) is attempted before curl-cffi browser impersonation.
- Public and cookie-authenticated download attempts emit `TIKTOK_DOWNLOAD_ATTEMPT` and `TIKTOK_DOWNLOAD_ATTEMPT_RESULT`; the successful strategy is persisted for subsequent items and runs.
- Cursor summaries now preserve the command-start total, so a 655→715 run reports `previous_current_total=655` and `new_since_last_sync=60`.
- Early `--max-failures` exits always print `CREATOR_RUN_COMPLETED` with processed, completed, failed, and remaining counts.

## v0.8.0 cursor-based TikTok catalog continuation

- Resumed TikTok Full Sync no longer uses `--playlist-start` as its primary deep-pagination mechanism. That option makes each new yt-dlp process replay all earlier API cursor pages before reaching item 476, 501, and beyond.
- Checkpoint schema 5 stores `tiktok_cursor`, `tiktok_device_id`, and `pagination_backend=cursor_api`. Existing schema 3/4 checkpoints are migrated from the oldest known `published_at` timestamp.
- The cursor backend calls TikTok's `creator/item_list` endpoint one bounded page at a time, atomically saves each page, and continues from the stored cursor on the next command.
- Native curl runs with `--noproxy *` and a proxy-cleared environment to avoid the macOS proxy and curl-cffi TLS failures observed during StartupBell validation.
- `hasMorePrevious=false` establishes an exact total and removes the checkpoint. Request failure returns a clean partial result without losing known items.
- Set `MEDIA2MD_TIKTOK_CURSOR_BACKEND=0` only for diagnosis or identity bootstrap; the legacy bounded yt-dlp page path is not intended for normal deep continuation.

## v0.7.8 bounded TikTok pagination

- Every TikTok catalog page now has one shared deadline across stable-ID, handle, transport, and auth fallbacks.
- Nested fallback was removed: the handle candidate no longer launches a second ID-discovery transport ladder.
- The last successful transport/auth mode is tried first on the next page.
- `SYNC_HEARTBEAT` is replaced by contextual `SYNC_WAITING` every 30 seconds by default.
- Full-sync invocations have a total runtime budget and an optional maximum-page limit. Reaching either limit saves the checkpoint, returns a non-exact partial result, and resumes on the next invocation.
- Instagram retains the v0.7.6 worker-side cookie path that completed 30 real Career Cleo Reels with zero failures.

## v0.7.4 terminal, installer, sync-heartbeat and failure-observability fixes

- TikTok curl error 35, TLS handshake, SSL and OpenSSL failures are treated as transient and retried.
- TikTok catalog sync falls back from the configured browser impersonation to other available browser targets and finally plain yt-dlp.
- Catalog extractors run in isolated process groups; timeout and Ctrl+C terminate the full child process tree while preserving checkpoints.
- TikTok full sync retains the secUid/user ID and page checkpoint learned before a later-page failure.
- Instagram runs print a final completion summary, and unified status imports the exact catalog snapshot.
- Batch start output includes selected media IDs. Creator status prints complete typed batch limits and the last exact Full Sync snapshot.

## Authentication

Media2MD reads the selected local browser profile without opening the browser. It can refresh cookies that Chrome already renewed. It cannot and will not type passwords, bypass 2FA, CAPTCHA, or platform challenges.

```bash
media2md auth profiles youtube --browser chrome
media2md auth connect youtube --browser chrome --profile Default
media2md auth verify youtube
```
The same `profiles`, `connect`, and `verify` flow is available for Instagram and TikTok.

## YouTube videos and Shorts

A YouTube creator is one identity even when content is exposed through separate tabs. Full sync enumerates both `/videos` and `/shorts`, de-duplicates by Video ID, and stores separate exact totals.

```bash
media2md creator add https://www.youtube.com/@TheProductFolks/videos --provider youtube
media2md creator sync @TheProductFolks --provider youtube --force-full
media2md creator status --provider youtube --creator @TheProductFolks
```

New Markdown is separated by type:

```text
markdown/youtube/TheProductFolks/videos/
markdown/youtube/TheProductFolks/shorts/
markdown/youtube/TheProductFolks/streams/
```

A single Shorts URL is also supported and is attached to the canonical channel identity:

```bash
media2md media add https://www.youtube.com/shorts/0jttCFj5ZWM --process-now
```

## Typed batch policies and scheduling

Default per-type batch sizes are TikTok 100, Instagram Reels 30, YouTube Shorts 30, YouTube videos 5, and YouTube long videos 1. Long YouTube videos are isolated into their own batch.

```bash
media2md creator policy set @TheProductFolks --provider youtube   --batch-size-type youtube_short=30   --batch-size-type youtube_video=5   --batch-size-type youtube_long=1   --scheduled-processing

media2md creator policy set @startupbell --provider tiktok   --batch-size-type tiktok_video=100

media2md creator policy set career_cleo --provider instagram   --batch-size-type instagram_reel=30

media2md scheduler tick --non-interactive --output ndjson
media2md openclaw install
```

## Agent contract
```bash
media2md agent status --output ndjson
media2md status --output ndjson
media2md auth status --output ndjson
media2md creator status --output ndjson
```
Password entry, 2FA, CAPTCHA, account challenges, destructive deletion, and update installation remain human-authorized boundaries.

## Responsible use
Only download content you own, are authorized to process, or may lawfully archive. Platform terms, copyright, privacy, and local laws still apply.

## v0.7.5 Instagram contract restoration and bounded TikTok networking

- `process_worker.py` now formally accepts `--cookies-file`; the creator runner and worker share one tested CLI contract.
- Known rows that failed only because of the old parser mismatch are automatically requeued during upgrade.
- TikTok uses no more than four transport strategies and opens a circuit breaker after repeated TLS failures.
- The final direct strategy ignores user yt-dlp configuration and removes inherited proxy environment variables.
- TikTok catalog page size is controlled separately with `MEDIA2MD_TIKTOK_SYNC_PAGE_SIZE`; it does not change the later media-processing batch.



## v0.7.8 TikTok stable-ID completion

A `tiktokuser:<secUid>` playlist can return valid entries without returning a human-readable handle. Media2MD now reuses the creator handle already known from the registry and completes the page without fetching the same range again through the profile handle. Bounded page exhaustion is a clean resumable pause rather than a hard error.

## v0.8.3 exact catalog lifecycle

- A TikTok Quick Sync can merge recent items into an exact baseline without erasing `current_total_exact`.
- `creator run` uses any existing TikTok catalog directly, whether partial or exact. Explicit `creator sync` remains the catalog mutation command.
- After an exact cursor scan completes and removes its checkpoint, the next `--force-full` bootstraps a new cursor rebuild from Registry identity instead of falling back to deep playlist offsets.
- The installer safely repairs the v0.8.2 downgrade only when the current total still equals the last exact total.

