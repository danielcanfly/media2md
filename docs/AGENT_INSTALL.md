# Agent Install Guide

This guide is for an agent that needs to install and initialize Media2MD on a
local machine without guessing hidden setup steps.

Use this document when the goal is:

- install `media2md`
- initialize the managed runtime
- connect provider auth from an existing local browser session
- verify that the system is ready for creator tracking or one-shot processing

## Safety Rules

The agent must follow these rules:

- Never ask for, store, or type a platform password
- Never try to bypass 2FA, CAPTCHA, or account challenges
- Never exfiltrate cookies, tokens, or browser databases
- Prefer machine-readable output such as `--output ndjson` when available
- Stop and ask for human help if the provider session is logged out, challenged,
  or requires manual browser interaction beyond selecting an existing profile

## 1. Install

Install the base package:

```bash
pip install media2md
```

Install provider extras as needed:

```bash
pip install "media2md[youtube]"
pip install "media2md[instagram]"
pip install "media2md[tiktok]"
pip install "media2md[bilibili]"
pip install "media2md[all]"
```

Install Instagram post OCR support only when image OCR is required:

```bash
pip install "media2md[instagram,ocr-mac-os]"
pip install "media2md[instagram,ocr-windows-linux]"
```

## 2. Verify the Installed CLI

Check that the package is installed and callable:

```bash
media2md version
```

Optional machine-readable environment checks:

```bash
media2md agent status --output ndjson
media2md status --output ndjson
```

## 3. Initialize the Managed Runtime

Initialize the runtime:

```bash
media2md init --language <language> --markdown-language <markdown-language> --timezone <timezone> --non-interactive
```

Supported language values:

```text
en
ja
zh-TW
zh-CN
```

Examples:

```bash
media2md init --language ja --markdown-language ja --timezone Asia/Tokyo --non-interactive
media2md init --language zh-TW --markdown-language zh-TW --timezone Asia/Taipei --non-interactive
media2md init --language en --markdown-language en --timezone <timezone> --non-interactive
```

Verify runtime paths:

```bash
media2md runtime base-path
media2md runtime path
media2md runtime status
```

For a new install, the default managed base path is typically:

```text
~/Downloads/media2md
```

## 4. Connect Provider Auth

Media2MD reuses cookies from an existing browser profile that the human user has
already authenticated in.

Typical YouTube flow:

```bash
media2md auth profiles youtube --browser chrome
media2md auth connect youtube --browser chrome --profile Default
media2md auth verify youtube --output ndjson
```

Typical Instagram flow:

```bash
media2md auth profiles instagram --browser chrome
media2md auth connect instagram --browser chrome --profile Default
media2md auth verify instagram --output ndjson
```

Typical TikTok flow:

```bash
media2md auth profiles tiktok --browser chrome
media2md auth connect tiktok --browser chrome --profile Default
media2md auth verify tiktok --output ndjson
```

If verify indicates the session is logged out or challenged:

- stop
- ask the human user to log in manually in the browser
- rerun `auth verify`

## 5. Validate Readiness

Check broad system readiness:

```bash
media2md status --output ndjson
media2md auth status --output ndjson
media2md doctor all
media2md agent status --output ndjson
```

Provider-specific diagnostics:

```bash
media2md doctor youtube-access --video-id <VIDEO_ID>
media2md doctor instagram-backends
media2md doctor tiktok-access --video-id <VIDEO_ID> --creator <CREATOR>
media2md doctor bilibili-access --video-id <BV_VIDEO_ID>
```

## 6. First Useful Action

Add a creator:

```bash
media2md creator add <creator-url> --provider <provider>
```

Refresh the saved catalog:

```bash
media2md creator refresh-catalog <creator> --provider <provider> --force-full
```

Run one processing batch:

```bash
media2md creator run <creator> --provider <provider> --mode batch
```

For a single URL:

```bash
media2md media inspect <media-url>
media2md media add <media-url> --process-now
```

## 7. Success Markers

The install and initialization can be treated as successful when:

- `media2md version` returns the expected installed version
- `media2md runtime status` reports the managed runtime path
- `media2md auth status --output ndjson` shows the intended provider auth state
- `media2md status --output ndjson` reports a valid system summary
- at least one creator or media workflow can be executed without setup errors

After successful processing, Media2MD usually prints output hints such as:

```text
latest_markdown_path=...
result_folder=...
open_in_finder_hint=open "..."
```

## 8. When the Agent Should Stop

Stop and return control to a human if:

- the browser session is logged out
- the provider requires password entry
- 2FA or CAPTCHA appears
- a platform challenge blocks normal verification
- a destructive command would be needed without explicit approval

## 9. Related Docs

- [README](https://github.com/danielcanfly/media2md/blob/main/README.md)
- [First Run Guide](https://github.com/danielcanfly/media2md/blob/main/docs/FIRST_RUN.md)
- [CLI Reference](https://github.com/danielcanfly/media2md/blob/main/docs/CLI_REFERENCE.md)
