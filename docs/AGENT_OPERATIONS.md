# Agent Operations Guide

This guide is for an agent that already completed installation and readiness
checks and now needs to operate Media2MD with minimal guessing.

Read this after
[AGENT_INSTALL.md](https://github.com/danielcanfly/media2md/blob/main/docs/AGENT_INSTALL.md).
Treat this file as the main usage guide for day-to-day operation.

## Operating Rules

- Prefer `--output ndjson` when a command supports it
- Prefer full creator URLs when adding a creator
- If using a bare handle such as `@creator-name` or `creator-name`, always pass
  `--provider`
- Never ask for passwords or try to bypass 2FA, CAPTCHA, or platform challenges
- Stop and return control to a human if auth is logged out or challenged
- Do not use destructive commands without explicit human approval

## Core Mental Model

Media2MD has two main working modes:

1. Single media processing
2. Creator tracking and backlog processing

The most important distinction is:

- `creator refresh-catalog` updates Media2MD's saved view of what exists
- `creator run` processes saved items into Markdown

In other words:

- catalog commands discover content
- run commands turn content into artifacts

## Before Doing Work

Check the current system state:

```bash
media2md status --output ndjson
media2md auth status --output ndjson
```

If the task depends on a specific provider, verify auth or readiness first:

```bash
media2md auth verify <provider> --output ndjson
media2md doctor all
```

## Operation Patterns

### 1. Process a Single URL

Use this when the task is:

- one YouTube video or Short
- one TikTok video
- one Instagram reel or post
- one Bilibili video

Inspect first if the task asks for diagnosis or classification:

```bash
media2md media inspect <media-url>
```

Process immediately when the goal is to produce Markdown:

```bash
media2md media add <media-url> --process-now
```

Use `media inspect` when you need to understand the target first.
Use `media add --process-now` when you want the actual artifact.

### 2. Track a Creator

Use this when the task is:

- follow a creator over time
- maintain a saved catalog
- repeatedly process new content

Add the creator once:

```bash
media2md creator add <creator-url> --provider <provider>
```

Refresh the saved catalog:

```bash
media2md creator refresh-catalog <creator> --provider <provider> --force-full
```

Process one batch:

```bash
media2md creator run <creator> --provider <provider> --mode batch
```

Drain more backlog:

```bash
media2md creator run <creator> --provider <provider> --mode drain --max-batches <n>
```

### 3. Refresh Catalog Without Processing

Use this when the task is:

- update saved creator state
- measure backlog size
- inspect whether new content exists
- avoid starting downloads or transcription yet

```bash
media2md creator refresh-catalog <creator> --provider <provider> --force-full
media2md creator status --provider <provider> --creator <creator>
```

### 4. Process Existing Backlog Without Refreshing First

Use this when the task is:

- continue work from an already refreshed catalog
- retry items already discovered earlier
- avoid refreshing because the catalog is already known-good

```bash
media2md creator run <creator> --provider <provider>
```

If stale catalog behavior is acceptable and explicitly intended:

```bash
media2md creator run <creator> --provider <provider> --allow-stale-catalog
```

### 5. Diagnose a Provider or Runtime Problem

Use this when auth or access looks broken:

```bash
media2md doctor all
media2md auth status --output ndjson
```

Provider-specific examples:

```bash
media2md doctor youtube-access --video-id <video-id>
media2md doctor instagram-backends
media2md doctor tiktok-access --video-id <video-id> --creator <creator>
media2md doctor bilibili-access --video-id <BV_VIDEO_ID>
```

## Output Discovery

After successful processing, Media2MD commonly prints:

```text
latest_markdown_path=...
result_folder=...
open_in_finder_hint=open "..."
```

Use these fields as the primary answer when a human asks where the result was
saved.

To inspect runtime paths:

```bash
media2md runtime base-path
media2md runtime path
media2md runtime status
```

Typical output folders are under the managed runtime, for example:

```text
markdown/youtube/<creator>/videos/
markdown/youtube/<creator>/shorts/
markdown/instagram/<creator>/
markdown/tiktok/<creator>/
markdown/bilibili/<creator>/
```

## Provider Notes

### YouTube

- Creator URLs can use `@creator-name`
- Caption-first behavior is preferred where available
- Long videos are often best processed in smaller batches

### Instagram

- Single-media processing supports reels, posts, carousel posts, and legacy
  `/tv/` URLs
- Post and carousel OCR depends on the matching OCR extra being installed

### TikTok

- Auth and transport conditions may vary over time
- If access looks degraded, use `doctor tiktok-access` before assuming a hard
  failure

### Bilibili

- Supports single-media and creator workflows
- Auth is not always required for the same paths as other providers

## When to Stop and Return Control

Stop and return control to a human when:

- a provider session is logged out
- manual browser login is required
- 2FA, CAPTCHA, or a platform challenge appears
- the task requires deleting data or uninstalling without explicit approval
- the agent cannot identify the provider from the input and no provider was
  supplied

## Related Docs

- [AGENT_INSTALL.md](https://github.com/danielcanfly/media2md/blob/main/docs/AGENT_INSTALL.md)
- [AGENT_DECISION_MAP.md](https://github.com/danielcanfly/media2md/blob/main/docs/AGENT_DECISION_MAP.md)
- [AGENT_TASK_PROMPTS.md](https://github.com/danielcanfly/media2md/blob/main/docs/AGENT_TASK_PROMPTS.md)
- [CLI_REFERENCE.md](https://github.com/danielcanfly/media2md/blob/main/docs/CLI_REFERENCE.md)
