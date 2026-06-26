# Media2MD

Media2MD is a local-first command-line tool for downloading supported media from Instagram, YouTube, and TikTok, transcribing speech locally, and turning the results into structured Markdown.

It is built for operator-controlled workflows rather than cloud automation. Media2MD can reuse a browser session you already authenticated locally, but it does not enter passwords, bypass 2FA, solve CAPTCHAs, or defeat platform challenges.

## Why Media2MD

- One CLI for Instagram, YouTube, and TikTok intake
- Local runtime with managed state and repeatable command workflows
- Markdown output that is easy to archive, search, or hand to agents
- Browser-profile-based auth reuse without storing credentials in the package
- Queue, creator sync, processing, runtime, and health-check commands in one tool

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
media2md init --language zh-TW --markdown-language zh-TW --timezone Asia/Taipei --non-interactive
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

A minimal YouTube-oriented setup might look like:

```bash
pip install "media2md[youtube]"
media2md init --language zh-TW --markdown-language zh-TW --timezone Asia/Taipei --non-interactive
media2md auth profiles youtube --browser chrome
media2md auth connect youtube --browser chrome --profile Default
media2md auth verify youtube
media2md creator add https://www.youtube.com/@TheProductFolks/videos --provider youtube
media2md creator sync @TheProductFolks --provider youtube --force-full
media2md creator run @TheProductFolks --provider youtube
```

## Authentication

Media2MD reads cookies from a local browser profile that you explicitly choose.

Typical flow:

```bash
media2md auth profiles youtube --browser chrome
media2md auth connect youtube --browser chrome --profile Default
media2md auth verify youtube
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
media2md creator add https://www.youtube.com/@TheProductFolks/videos --provider youtube
media2md creator sync @TheProductFolks --provider youtube --force-full
media2md creator status --provider youtube --creator @TheProductFolks
```

Process a single media URL:

```bash
media2md media add https://www.youtube.com/shorts/0jttCFj5ZWM --process-now
```

Run queue or creator processing:

```bash
media2md creator run @TheProductFolks --provider youtube
media2md status --output ndjson
```

Import an existing legacy project into the managed runtime:

```bash
media2md runtime import --from-project ~/instagram-to-md
```

Inspect a URL before adding it:

```bash
media2md media inspect https://www.tiktok.com/@startupbell/video/7338632507950189826
```

List tracked media:

```bash
media2md media list --provider tiktok
```

Run a deeper environment and access check:

```bash
media2md doctor all
media2md doctor youtube-access --video-id dQw4w9WgXcQ --transcription-smoke-test
media2md doctor tiktok-access --video-id 7338632507950189826 --creator startupbell
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
media2md creator policy set @TheProductFolks --provider youtube \
  --batch-size-type youtube_short=30 \
  --batch-size-type youtube_video=5 \
  --batch-size-type youtube_long=1 \
  --scheduled-processing
```

Run the scheduler tick manually:

```bash
media2md scheduler tick --non-interactive --output ndjson
```

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
