# Media2MD

A local-first CLI for turning creator content into Markdown for humans, agents, and knowledge workflows.

Media2MD collects content from Instagram, YouTube, TikTok, and Bilibili, extracts captions, OCR text, or speech transcripts on your own machine, and writes the result as structured Markdown.

It is built for a different job than a normal downloader: follow creators over time, refresh saved catalogs, process backlogs, and turn platform content into durable local files that can be searched, summarized, archived, or fed into a wiki, RAG pipeline, or agent workflow.

## Why Media2MD

- Local-first: OCR, transcription, and runtime state stay on your own machine
- Creator-oriented: track creators and process saved backlogs, not just one URL at a time
- Markdown-first: output is easy to archive, diff, search, and reuse
- Agent-ready: stable command surfaces and machine-readable `ndjson` output
- Runtime/code separation: installed package code and managed runtime state are kept separate
- Caption-first where possible: prefers captions and subtitles before falling back to local transcription

## Supported Platforms

- Instagram
  - reels
  - posts
  - carousel posts
  - optional local OCR for post images
- YouTube
- TikTok
- Bilibili

## Install

Base install:

```bash
pip install media2md
```

Or install by agent, give it this repo doc and ask it to follow it:

```text
Read https://github.com/danielcanfly/media2md/blob/main/docs/AGENT_INSTALL.md and install, initialize, verify auth, and validate the Media2MD setup on this machine. Do not ask for passwords, do not bypass 2FA/CAPTCHA, and stop if manual login is required.
```

Provider extras:

```bash
pip install "media2md[instagram]"
pip install "media2md[youtube]"
pip install "media2md[tiktok]"
pip install "media2md[bilibili]"
pip install "media2md[all]"
```

Instagram post OCR:

```bash
pip install "media2md[instagram,ocr-mac-os]"
pip install "media2md[instagram,ocr-windows-linux]"
```

Check the installed version:

```bash
media2md version
```

## Quick Start

Initialize the runtime:

```bash
media2md init --language <language> --markdown-language <markdown-language> --timezone <timezone> --non-interactive
```

Connect provider auth:

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

Check status:

```bash
media2md status
media2md doctor all
```

## Common Workflows

Single URL:

```bash
media2md media inspect <media-url>
media2md media add <media-url> --process-now
```

Drain a backlog:

```bash
media2md creator run @creator-name --provider youtube --mode drain --batch-size 1 --max-batches 5
```

Runtime paths:

```bash
media2md runtime status
media2md runtime base-path
media2md runtime path
```

## Docs

- Human setup: [First Run Guide](https://github.com/danielcanfly/media2md/blob/main/docs/FIRST_RUN.md)
- Agent setup: [Agent Install Guide](https://github.com/danielcanfly/media2md/blob/main/docs/AGENT_INSTALL.md)
- Full command reference: [CLI Reference](https://github.com/danielcanfly/media2md/blob/main/docs/CLI_REFERENCE.md)
- Release process: [RELEASE_PROCESS.md](https://github.com/danielcanfly/media2md/blob/main/docs/RELEASE_PROCESS.md)

## Good Fit

Media2MD is a strong fit when you want to:

- follow creators over time instead of manually checking feeds
- build a local Markdown archive from social and video content
- feed normalized Markdown into search, notes, RAG, or agent workflows
- keep processing on your own machine instead of relying on a hosted service

It is a weaker fit when you need:

- a hosted SaaS workflow
- remote browser login automation
- challenge bypasses or account-evasion tooling
- a cloud-managed ingestion service

## Safety

Media2MD does not type passwords, bypass 2FA, solve CAPTCHA, or defeat provider access controls. It works best when the target account session is already healthy in a local browser profile that you explicitly choose.

## Links

- Repository: [danielcanfly/media2md](https://github.com/danielcanfly/media2md)
- PyPI: [media2md](https://pypi.org/project/media2md/)
- First Run Guide: [docs/FIRST_RUN.md](https://github.com/danielcanfly/media2md/blob/main/docs/FIRST_RUN.md)
- Agent Install Guide: [docs/AGENT_INSTALL.md](https://github.com/danielcanfly/media2md/blob/main/docs/AGENT_INSTALL.md)
- CLI Reference: [docs/CLI_REFERENCE.md](https://github.com/danielcanfly/media2md/blob/main/docs/CLI_REFERENCE.md)
- Release Process: [docs/RELEASE_PROCESS.md](https://github.com/danielcanfly/media2md/blob/main/docs/RELEASE_PROCESS.md)
- Changelog: [CHANGELOG.md](https://github.com/danielcanfly/media2md/blob/main/CHANGELOG.md)
- Contributing: [CONTRIBUTING.md](https://github.com/danielcanfly/media2md/blob/main/CONTRIBUTING.md)
