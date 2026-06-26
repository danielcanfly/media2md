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

## Authentication

Media2MD reads cookies from a local browser profile that you explicitly choose.

Typical flow:

```bash
media2md auth profiles youtube --browser chrome
media2md auth connect youtube --browser chrome --profile Default
media2md auth verify youtube
```

The same `profiles`, `connect`, and `verify` flow is available for Instagram and TikTok.

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

## What It Does Not Do

Media2MD does not:

- type passwords for you
- bypass 2FA, CAPTCHA, or account challenges
- turn private platform access into public access
- remove the need to follow platform terms, copyright rules, privacy rules, or local law

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
