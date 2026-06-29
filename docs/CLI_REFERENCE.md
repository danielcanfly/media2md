# CLI Reference

This document lists the current public command surfaces for `media2md`.

For everyday use, start with the shorter examples in the main [README](https://github.com/danielcanfly/media2md/blob/main/README.md). This file is the fuller command map.

## Top-Level Commands

```text
media2md version
media2md status
media2md settings
media2md agent
media2md init
media2md providers
media2md auth
media2md media
media2md creator
media2md scheduler
media2md update
media2md doctor
media2md openclaw
media2md repair
media2md data
media2md uninstall
```

## Daily Essentials

```bash
media2md init --language <language> --markdown-language <markdown-language> --timezone <timezone> --non-interactive
media2md auth connect youtube --browser chrome --profile Default
media2md creator add https://www.youtube.com/@creator-name --provider youtube
media2md creator refresh-catalog @creator-name --provider youtube --force-full
media2md creator run @creator-name --provider youtube
media2md media add <media-url> --process-now
media2md status --output ndjson
media2md doctor all
media2md data backup --destination <backup-dir>
```

## `media2md auth`

```text
media2md auth login
media2md auth profiles
media2md auth connect
media2md auth verify
media2md auth refresh
media2md auth status
media2md auth logout
media2md auth disconnect
media2md auth capabilities
```

Typical uses:

```bash
media2md auth profiles youtube --browser chrome
media2md auth connect youtube --browser chrome --profile Default
media2md auth verify youtube
media2md auth status --output ndjson
```

## `media2md media`

```text
media2md media inspect
media2md media add
media2md media process-registered
media2md media list
```

Typical uses:

```bash
media2md media inspect <media-url>
media2md media add <media-url> --process-now
media2md media process-registered <provider> <external-id>
media2md media list --provider <provider>
```

## `media2md creator`

```text
media2md creator add
media2md creator status
media2md creator list
media2md creator sync-enable
media2md creator sync-disable
media2md creator sync
media2md creator refresh-catalog
media2md creator policy-set
media2md creator policy-show
media2md creator policy set
media2md creator policy show
media2md creator run
media2md creator delete
```

Typical uses:

```bash
media2md creator add https://www.youtube.com/@creator-name --provider youtube
media2md creator status --provider youtube --creator @creator-name
media2md creator refresh-catalog @creator-name --provider youtube --force-full
media2md creator run @creator-name --provider youtube
```

Policy examples:

```bash
media2md creator policy set <creator> --provider <provider> \
  --mode batch \
  --batch-size <batch-size> \
  --max-batches <max-batches> \
  --max-runtime-minutes <minutes>

media2md creator policy set <creator> --provider youtube \
  --batch-size-type youtube_short=<short-limit> \
  --batch-size-type youtube_video=<video-limit> \
  --batch-size-type youtube_long=1
```

Notes:

- Per-type batch limits are supported.
- Long YouTube videos are best treated as `youtube_long=1` when you want one long-form item per batch.
- `creator run` also supports `--retry-failed`, `--allow-stale-catalog`, date filters, rank filters, and ordering.
- Creator inputs can be full URLs or bare handles. Bare handles such as `@creator-name` or `creator-name` require `--provider`.
- `creator refresh-catalog` is the preferred public name for refreshing a creator catalog. `creator sync` remains available as the lower-level command name.

## `media2md settings`

```text
media2md settings show
media2md settings set
```

Example:

```bash
media2md settings show
media2md settings set --instagram-backend auto --youtube-caption-first --update-check-on-use
```

## `media2md doctor`

```text
media2md doctor youtube
media2md doctor instagram-backends
media2md doctor impersonation
media2md doctor browser-safety
media2md doctor youtube-access
media2md doctor tiktok-access
media2md doctor all
```

Examples:

```bash
media2md doctor all
media2md doctor youtube-access --video-id <video-id> --transcription-smoke-test
media2md doctor tiktok-access --video-id <video-id> --creator <creator>
```

## `media2md runtime`

The packaged CLI also supports:

```text
media2md runtime status
media2md runtime path
media2md runtime install
media2md runtime import
```

Examples:

```bash
media2md runtime status
media2md runtime path
media2md runtime install --force
media2md runtime import --from-project <legacy-project-path>
```

## `media2md scheduler`

```text
media2md scheduler tick
```

Example:

```bash
media2md scheduler tick --non-interactive --output ndjson
```

## `media2md update`

```text
media2md update status
media2md update check
media2md update download
media2md update install
media2md update rollback
```

## `media2md repair`

```text
media2md repair active-states
media2md repair identities
media2md repair workspace
```

## `media2md data`

```text
media2md data backup
media2md data verify-backup
media2md data delete-all
```

Examples:

```bash
media2md data backup --destination <backup-dir>
media2md data verify-backup <backup-zip-path>
```

## `media2md uninstall`

`media2md uninstall` removes the installed Python package by default.

Use:

```bash
media2md uninstall
media2md uninstall --dry-run
media2md uninstall --purge-data --yes --confirm DELETE-ALL-DATA
```

## `media2md openclaw`

`media2md openclaw ...` delegates to the OpenClaw-oriented integration surface bundled with the runtime.

This is the main agent-adaptation path in the current project and is where scheduled agent-oriented workflows are primarily aligned today.

## Output Modes

Many commands support:

```bash
--output human
--output ndjson
```

Use `ndjson` when another tool or agent will read command output programmatically.
