# Media2MD OpenClaw Skill v0.9.1

Use `media2md` as a non-interactive CLI. Prefer `--output ndjson` whenever available.

## Safety contract
- Never request, store, or type platform passwords.
- Never try to bypass CAPTCHA, 2FA, or platform challenges.
- Normal commands must not launch a browser.
- Stop and surface `required_action` when `action_required=true`.
- Require explicit user approval for update install/rollback, delete operations, drain mode, and stale-catalog processing.

## Authentication
```bash
media2md auth profiles <provider> --browser <browser>
media2md auth connect <provider> --browser <browser> --profile <profile>
media2md auth verify <provider> --output ndjson

```
Cookies are refreshed from the selected browser profile without opening the browser. If a session is genuinely logged out or challenged, ask the user to log in manually, then rerun verify.

## Daily automation
```bash
media2md scheduler tick --non-interactive --output ndjson
```
Install the OpenClaw job with:
```bash
media2md openclaw install
```

## Diagnostics
```bash
media2md doctor all
media2md auth status --output ndjson
media2md agent status --output ndjson
media2md status --output ndjson
```

## YouTube videos and Shorts
A creator sync covers both `/videos` and `/shorts` and reports separate totals. Configure type-aware batches through the public CLI:
```bash
media2md creator policy set <creator> --provider youtube \
  --batch-size-type youtube_short=<short-limit> \
  --batch-size-type youtube_video=<video-limit> \
  --batch-size-type youtube_long=1
```
Long videos are isolated into single-item batches. Do not edit policy JSON directly.
