# Media2MD

Media2MD is a local-first command-line tool for downloading supported media from Instagram, YouTube, and TikTok, transcribing speech locally, and turning the results into structured Markdown.

It is built for operator-controlled workflows rather than cloud automation. Media2MD can reuse a browser session you already authenticated locally, but it does not enter passwords, bypass 2FA, solve CAPTCHAs, or defeat platform challenges.

## Why Media2MD

- One CLI for Instagram, YouTube, and TikTok intake
- Local runtime with managed state and repeatable command workflows
- Markdown output that is easy to archive, search, or hand to agents
- Browser-profile-based auth reuse without storing credentials in the package
- Queue, creator sync, processing, runtime, and health-check commands in one tool

## What It Helps With

Media2MD is aimed at a very practical problem: keeping up with creator output without having to manually watch, sort, and summarize every update yourself.

It is especially useful when you want to:

- track specific creators over time instead of checking them manually
- let an agent run scheduled collection and follow-up workflows
- turn media output into Markdown that can later be organized into a wiki or knowledge base
- process content locally on your own machine instead of relying on a hosted external service

The automation surface is designed for agent use, and current agent-oriented scheduling/adaptation work is primarily aligned with OpenClaw-based workflows.

## Core Capabilities

- Track creators and sync their catalogs across supported providers
- Run batch processing with configurable limits and per-type batch sizing
- Prefer one long YouTube video per batch when long-form processing should stay isolated
- Reuse local browser-backed auth for provider access where supported
- Generate Markdown artifacts that are easier for agents to summarize, tag, transform, or import into a knowledge base
- Run health checks, access diagnostics, backup, and verification from the CLI
- Operate entirely on local machine resources for download, processing, and transcription workflows

## Install

Install from PyPI:

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

Run a health check:

```bash
media2md doctor all
```

Inspect the runtime location:

```bash
media2md runtime status
media2md runtime path
```

## Tutorial

If this is your first run, a practical sequence looks like this:

1. Install the package and the provider extras you need.
2. Initialize the managed runtime with your preferred language and timezone.
3. Connect and verify browser-backed auth for the provider you want to use.
4. Add a creator or inspect a single media URL.
5. Sync the creator catalog or process a single item immediately.
6. Check status, generated Markdown, and health diagnostics.

A minimal setup might look like:

```bash
pip install "media2md[<provider-extra>]"
media2md init --language <language> --markdown-language <markdown-language> --timezone <timezone> --non-interactive
media2md auth profiles <provider> --browser <browser>
media2md auth connect <provider> --browser <browser> --profile <profile>
media2md auth verify <provider>
media2md creator add <creator-url> --provider <provider>
media2md creator sync <creator> --provider <provider> --force-full
media2md creator run <creator> --provider <provider>
```

## Authentication

Media2MD reads cookies from a local browser profile that you explicitly choose.

Typical flow:

```bash
media2md auth profiles <provider> --browser <browser>
media2md auth connect <provider> --browser <browser> --profile <profile>
media2md auth verify <provider>
```

The same `profiles`, `connect`, and `verify` flow is available for Instagram and TikTok.

## Provider Support

Media2MD currently focuses on:

- Instagram creator and media workflows
- YouTube channel, video, and Shorts workflows
- TikTok creator and media workflows

The project is CLI-first and optimized for local execution on a machine that already has access to the browser profiles you want to reuse.

## Common Workflows

Add a creator and run a full sync:

```bash
media2md creator add <creator-url> --provider <provider>
media2md creator sync <creator> --provider <provider> --force-full
media2md creator status --provider <provider> --creator <creator>
```

Process a single media URL:

```bash
media2md media add <media-url> --process-now
```

Run queue or creator processing:

```bash
media2md creator run <creator> --provider <provider>
media2md status --output ndjson
```

Import an existing legacy project into the managed runtime:

```bash
media2md runtime import --from-project <legacy-project-path>
```

Inspect a URL before adding it:

```bash
media2md media inspect <media-url>
```

List tracked media:

```bash
media2md media list --provider tiktok
```

Run a deeper environment and access check:

```bash
media2md doctor all
media2md doctor youtube-access --video-id <video-id> --transcription-smoke-test
media2md doctor tiktok-access --video-id <video-id> --creator <creator>
```

Create and verify a state backup:

```bash
media2md data backup --destination ~/media2md-backups
media2md data verify-backup ~/media2md-backups/media2md-state-YYYYMMDDTHHMMSSZ.zip
```

## Output

Generated output is organized under the local runtime state. Typical Markdown paths look like:

```text
markdown/youtube/<creator>/videos/
markdown/youtube/<creator>/shorts/
markdown/instagram/<creator>/
markdown/tiktok/<creator>/
```

## Runtime Model

Media2MD installs a managed runtime for the current package version and keeps state separately from code. That makes upgrades and runtime recovery more predictable than mixing scripts and user data in one folder.

Useful commands:

```bash
media2md runtime status
media2md runtime install --force
media2md doctor all
```

## CLI Areas

The CLI is organized around a few main areas:

- `auth`: browser profile discovery, connection, verification, refresh, and status
- `creator`: add creators, sync catalogs, inspect status, set policies, and run processing
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

Current published version: `0.9.1`

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
