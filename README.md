# Media2MD

Media2MD is a local-first command-line tool that collects supported media from Instagram, YouTube, and TikTok, transcribes speech locally, and turns the results into structured Markdown.

It is built for both people working directly in the terminal and agents that need stable commands, schedulable workflows, and machine-readable output. Media2MD can reuse a browser session you already authenticated locally, but it does not enter passwords, bypass 2FA, solve CAPTCHAs, or defeat platform challenges.

## Highlights

- One CLI for Instagram, YouTube, and TikTok intake
- Local runtime and local transcription workflows
- Markdown output that is easy to archive, search, summarize, or import into a knowledge base
- Creator tracking, catalog refresh, queue processing, diagnostics, and backup commands in one tool
- Human-friendly terminal usage plus stable surfaces for automation and agent orchestration

## What It Is For

Media2MD is useful when you want to:

- track specific creators over time instead of checking them manually
- let an agent run scheduled collection and follow-up workflows
- turn media output into Markdown that can later be organized into a wiki or knowledge base
- process content on your own machine instead of depending on a hosted external service

The current agent-oriented scheduling and adaptation work is primarily aligned with OpenClaw-based workflows.

## Install

Install the base package:

```bash
pip install media2md
```

Install provider extras when needed:

```bash
pip install "media2md[instagram]"
pip install "media2md[youtube]"
pip install "media2md[tiktok]"
pip install "media2md[all]"
```

Check the installed version:

```bash
media2md version
```

## Quick Start

Initialize the managed runtime:

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

Connect and verify provider auth:

```bash
media2md auth profiles youtube --browser chrome
media2md auth connect youtube --browser chrome --profile Default
media2md auth verify youtube
```

Track a creator and process content:

```bash
media2md creator add https://www.youtube.com/@creator-name --provider youtube
media2md creator refresh-catalog @creator-name --provider youtube --force-full
media2md creator run @creator-name --provider youtube
```

Inspect your runtime and health status:

```bash
media2md status
media2md doctor all
media2md runtime base-path
media2md runtime path
```

## Common Workflows

Add a creator and refresh the creator catalog:

```bash
media2md creator add https://www.youtube.com/@creator-name --provider youtube
media2md creator refresh-catalog @creator-name --provider youtube --force-full
media2md creator status --provider youtube --creator @creator-name
```

Process a creator queue into Markdown:

```bash
media2md creator run @creator-name --provider youtube
media2md status --output ndjson
```

Process a single media URL immediately:

```bash
media2md media inspect <media-url>
media2md media add <media-url> --process-now
```

Create and verify a state backup:

```bash
media2md data backup --destination ~/media2md-backups
media2md data verify-backup ~/media2md-backups/media2md-state-YYYYMMDDTHHMMSSZ.zip
```

Creator inputs can be either full creator URLs or provider-qualified handles. For bare handles such as `@creator-name` or `creator-name`, pass `--provider` explicitly so the CLI knows which platform to target.

`media2md creator refresh-catalog` is the preferred public command name for refreshing a creator catalog. `media2md creator sync` still exists in the full CLI surface for lower-level use.

## Output and Runtime

New installs default to `~/Downloads/media2md`. Existing installs that already use an older managed location keep that location until you explicitly move them.

Useful runtime commands:

```bash
media2md runtime status
media2md runtime base-path
media2md runtime path
media2md runtime set-base-path <path>
media2md runtime install --force
```

Typical Markdown output paths:

```text
markdown/youtube/<creator>/videos/
markdown/youtube/<creator>/shorts/
markdown/instagram/<creator>/
markdown/tiktok/<creator>/
```

## Documentation

- [First Run Guide](docs/FIRST_RUN.md)
- [CLI Reference](docs/CLI_REFERENCE.md)
- [Release Process](docs/RELEASE_PROCESS.md)
- [Changelog](CHANGELOG.md)

## CLI Areas

- `auth`: browser profile discovery, connection, verification, refresh, and status
- `creator`: add creators, refresh catalogs, inspect status, set policies, and run processing
- `media`: inspect URLs, add media, process registered items, and list tracked entries
- `doctor`: environment, provider, and access diagnostics
- `data`: backup, backup verification, and destructive data operations
- `runtime`: managed runtime install, import, and path/status helpers
- `scheduler`: scheduled processing entrypoints
- `update`: package update and rollback helpers

For machine-readable integrations, many commands support `--output ndjson`.

## Example Commands

Check system-wide status:

```bash
media2md status
media2md status --output ndjson
```

Show or change settings:

```bash
media2md settings show
media2md settings set --instagram-backend auto --youtube-caption-first --update-check-on-use
```

Set creator policy:

```bash
media2md creator policy set <creator> --provider <provider> \
  --batch-size-type <type-a>=<limit-a> \
  --batch-size-type <type-b>=<limit-b> \
  --batch-size-type <type-c>=<limit-c> \
  --scheduled-processing
```

Run the scheduler tick manually:

```bash
media2md scheduler tick --non-interactive --output ndjson
```

See the full command reference in [docs/CLI_REFERENCE.md](./docs/CLI_REFERENCE.md).

## Typical Use Cases

Media2MD is a good fit when you want to:

- archive creator output into Markdown on your own machine
- build a personal or team knowledge base from social/video content
- inspect or process specific URLs without building your own scraping pipeline
- feed normalized Markdown artifacts into downstream agent or search workflows

It is a weaker fit when you need:

- a hosted SaaS workflow
- remote browser automation for account login
- bypasses for provider auth or challenge mechanisms
- a fully managed cloud ingestion service

## What It Does Not Do

Media2MD does not:

- type passwords for you
- bypass 2FA, CAPTCHA, or account challenges
- turn private platform access into public access
- remove the need to follow platform terms, copyright rules, privacy rules, or local law

## Notes

- Some providers require their corresponding extra dependencies.
- Browser-backed auth works best when the target session is already healthy in the browser.
- The managed runtime separates code from state to make local upgrades and recovery easier.
- The package is published on PyPI, but your actual media processing happens locally.

## Project Status

Current published version: `0.9.3`

Recent release themes in `0.9.x` include:

- stronger TikTok transport and metadata fallback handling
- more truthful health and degraded-ready reporting
- safer backup and runtime integrity behavior
- tighter regression coverage for acceptance-derived failures

See the [Changelog](https://github.com/danielcanfly/media2md/blob/main/CHANGELOG.md) for version-by-version details.

## Contributing

See [CONTRIBUTING.md](https://github.com/danielcanfly/media2md/blob/main/CONTRIBUTING.md).

## Links

- Repository: [danielcanfly/media2md](https://github.com/danielcanfly/media2md)
- PyPI: [media2md](https://pypi.org/project/media2md/)
- Issues: [GitHub Issues](https://github.com/danielcanfly/media2md/issues)
- Changelog: [CHANGELOG.md](https://github.com/danielcanfly/media2md/blob/main/CHANGELOG.md)

## Responsible Use

Only download content you own, are authorized to process, or may lawfully archive. Platform terms, copyright, privacy, and local laws still apply.
