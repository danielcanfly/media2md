# Agent Task Prompts

This file contains copy-paste prompts that a human operator can give to an
agent.

These prompts are designed to reduce guessing by telling the agent which Media2MD
docs to read first and which safety rules to follow.

## 1. Install and Initialize

```text
Read the Media2MD docs at:
- docs/AGENT_INSTALL.md
- docs/AGENT_OPERATIONS.md
- docs/AGENT_DECISION_MAP.md

Install media2md on this machine, initialize the runtime, verify provider auth readiness, and validate that the system is ready for use. Do not ask for passwords, do not bypass 2FA/CAPTCHA, and stop if manual login is required. Prefer ndjson output when available.
```

## 2. Connect Provider Auth

```text
Read docs/AGENT_INSTALL.md and docs/AGENT_DECISION_MAP.md. Connect and verify Media2MD auth for <provider> using an existing local browser profile on this machine. Do not ask for passwords, do not bypass 2FA/CAPTCHA, and stop if manual login is required. Return the exact commands you ran and the final auth status.
```

## 3. Add a Creator and Run One Batch

```text
Read docs/AGENT_OPERATIONS.md and docs/AGENT_DECISION_MAP.md. Add this creator to Media2MD, refresh the saved catalog, and run one processing batch:

<creator-url-or-handle>

If the input is a bare handle, make sure you pass the correct --provider. Prefer ndjson output when available. Return the exact commands you ran, whether catalog refresh succeeded, whether processing succeeded, and where the Markdown output was saved.
```

## 4. Refresh a Creator Catalog Only

```text
Read docs/AGENT_OPERATIONS.md and docs/AGENT_DECISION_MAP.md. Refresh the Media2MD catalog for this creator without processing any downloads or transcription yet:

<creator-url-or-handle>

Return whether the refresh succeeded, what provider was used, and the current creator status summary.
```

## 5. Drain a Backlog

```text
Read docs/AGENT_OPERATIONS.md and docs/AGENT_DECISION_MAP.md. Drain the Media2MD backlog for this creator:

<creator-url-or-handle>

Use the safest command path, prefer ndjson output when available, and stop if auth is invalid or the provider is challenged. Return the exact commands you ran, how many batches were processed, and where the output was saved.
```

## 6. Process a Single URL

```text
Read docs/AGENT_OPERATIONS.md and docs/AGENT_DECISION_MAP.md. Inspect and then process this single media URL with Media2MD:

<media-url>

Return the provider, whether processing succeeded, and the exact saved Markdown path or result folder.
```

## 7. Diagnose a Failure

```text
Read docs/AGENT_INSTALL.md, docs/AGENT_OPERATIONS.md, and docs/AGENT_DECISION_MAP.md. Diagnose why this Media2MD task is failing:

<task-description>

Use status, auth status, auth verify, and doctor commands as appropriate. Prefer ndjson output when available. Do not perform destructive actions. Return the exact commands you ran, the failure you found, and the next safe remediation step.
```

## 8. Find the Output

```text
Read docs/AGENT_OPERATIONS.md. Find where Media2MD saved the output for the most recent successful run. Use runtime path commands and any command output hints such as latest_markdown_path, result_folder, or open_in_finder_hint. Return the exact path.
```

## 9. Move the Runtime

```text
Read docs/AGENT_INSTALL.md and docs/AGENT_DECISION_MAP.md. Move the Media2MD managed runtime base path to this destination:

<path>

Return the exact command you ran and the final runtime base path and runtime path.
```
