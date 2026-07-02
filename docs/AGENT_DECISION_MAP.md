# Agent Decision Map

This file tells an agent which Media2MD command path to choose for common
requests.

Read this after
[AGENT_INSTALL.md](https://github.com/danielcanfly/media2md/blob/main/docs/AGENT_INSTALL.md).
Use it together with
[AGENT_OPERATIONS.md](https://github.com/danielcanfly/media2md/blob/main/docs/AGENT_OPERATIONS.md).

## Default Decision Order

When a new task arrives:

1. Identify whether the target is a single media item or a creator
2. Identify the provider
3. Check whether auth or provider readiness is required
4. Decide whether the task is discovery, processing, diagnosis, or maintenance
5. Choose the smallest command path that completes the task

## Decision Tree

### A. The input is a single media URL

Use:

```bash
media2md media inspect <media-url>
```

if the goal is:

- classify the URL
- inspect provider or media identity
- diagnose before processing

Use:

```bash
media2md media add <media-url> --process-now
```

if the goal is:

- produce Markdown now
- download or transcribe now
- get a saved artifact now

### B. The input is a creator URL or handle

If the creator is new:

```bash
media2md creator add <creator-url> --provider <provider>
```

Then decide:

- need to discover what exists -> `creator refresh-catalog`
- need to process saved items -> `creator run`
- need both -> `creator refresh-catalog` then `creator run`

### C. The user says "sync", "refresh", "update catalog", or "check for new posts"

Use:

```bash
media2md creator refresh-catalog <creator> --provider <provider> --force-full
```

This updates the saved catalog and does not mean processing has happened yet.

### D. The user says "run", "process", "download", "turn into Markdown", or "drain backlog"

Use:

```bash
media2md creator run <creator> --provider <provider>
```

For longer backlog draining:

```bash
media2md creator run <creator> --provider <provider> --mode drain --max-batches <n>
```

### E. The user says "something is broken", "check health", "why is this failing"

Start with:

```bash
media2md status --output ndjson
media2md auth status --output ndjson
media2md doctor all
```

Then narrow by provider:

```bash
media2md auth verify <provider> --output ndjson
media2md doctor <provider-specific-check>
```

### F. The user asks where files are stored

Use:

```bash
media2md runtime base-path
media2md runtime path
media2md runtime status
```

After processing, also inspect command output for:

```text
latest_markdown_path=...
result_folder=...
open_in_finder_hint=...
```

### G. The user wants to move the runtime location

Use:

```bash
media2md runtime set-base-path <path>
```

### H. The user asks for cleanup, destructive reset, or uninstall

Do not execute immediately.
First confirm that destructive action is explicitly intended.

## Provider Resolution Rules

- If the input is a full creator URL, Media2MD can often infer the provider
- If the input is a bare handle such as `@creator-name` or `creator-name`, pass
  `--provider`
- If the provider is ambiguous and not supplied, stop and ask for the provider

## Command Selection Table

| Task | Preferred command |
| --- | --- |
| Inspect one media item | `media2md media inspect <media-url>` |
| Process one media item | `media2md media add <media-url> --process-now` |
| Add creator | `media2md creator add <creator-url> --provider <provider>` |
| Refresh creator catalog | `media2md creator refresh-catalog <creator> --provider <provider> --force-full` |
| Process creator backlog | `media2md creator run <creator> --provider <provider>` |
| Drain multiple batches | `media2md creator run <creator> --provider <provider> --mode drain --max-batches <n>` |
| Check global health | `media2md doctor all` |
| Check auth state | `media2md auth status --output ndjson` |
| Verify provider auth | `media2md auth verify <provider> --output ndjson` |
| Show runtime location | `media2md runtime path` |
| Move runtime location | `media2md runtime set-base-path <path>` |

## Safe Fallback Rule

If the agent is unsure which creator workflow command to use:

1. check `status` and `auth status`
2. use `creator refresh-catalog` to update the saved view
3. use `creator run` only after catalog context is known

This is safer than guessing from stale local state.

## Related Docs

- [AGENT_INSTALL.md](https://github.com/danielcanfly/media2md/blob/main/docs/AGENT_INSTALL.md)
- [AGENT_OPERATIONS.md](https://github.com/danielcanfly/media2md/blob/main/docs/AGENT_OPERATIONS.md)
- [AGENT_TASK_PROMPTS.md](https://github.com/danielcanfly/media2md/blob/main/docs/AGENT_TASK_PROMPTS.md)
