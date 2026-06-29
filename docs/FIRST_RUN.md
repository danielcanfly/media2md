# First Run Guide

This guide is for a first-time Media2MD user starting from a normal `pip install`.

## 1. Install

Install the package:

```bash
pip install media2md
```

Install provider extras when needed:

```bash
pip install "media2md[youtube]"
pip install "media2md[instagram]"
pip install "media2md[tiktok]"
pip install "media2md[all]"
```

Check the installed version:

```bash
media2md version
```

## 2. Initialize the runtime

Media2MD keeps managed runtime state separately from the package code.

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

For a new install, the default managed base path is:

```text
~/Downloads/media2md
```

Check it:

```bash
media2md runtime base-path
media2md runtime path
media2md runtime status
```

## 3. Connect authentication

Media2MD reads cookies from a browser profile that you explicitly choose.

Typical YouTube flow:

```bash
media2md auth profiles youtube --browser chrome
media2md auth connect youtube --browser chrome --profile Default
media2md auth verify youtube
```

Instagram flow:

```bash
media2md auth profiles instagram --browser chrome
media2md auth connect instagram --browser chrome --profile Default
media2md auth verify instagram
```

TikTok flow:

```bash
media2md auth profiles tiktok --browser chrome
media2md auth connect tiktok --browser chrome --profile Default
media2md auth verify tiktok
```

## 4. Add a creator

Add a creator with a full URL:

```bash
media2md creator add https://www.youtube.com/@creator-name --provider youtube
```

You can also use a bare handle such as `@creator-name` or `creator-name`, but then you must pass `--provider`.

## 5. Refresh the creator catalog

Refreshing the catalog updates Media2MD's view of what content exists for that creator.

```bash
media2md creator refresh-catalog @creator-name --provider youtube --force-full
```

`creator refresh-catalog` is the preferred public command name. `creator sync` remains available in the full CLI surface.

## 6. Run processing

Running processing downloads, transcribes, and writes Markdown for queued items.

```bash
media2md creator run @creator-name --provider youtube
```

In practice:

- `creator refresh-catalog` updates what exists
- `creator run` processes what should turn into Markdown

For single URLs:

```bash
media2md media inspect <media-url>
media2md media add <media-url> --process-now
```

## 7. Find the output

Typical Markdown output paths:

```text
markdown/youtube/<creator>/videos/
markdown/youtube/<creator>/shorts/
markdown/instagram/<creator>/
markdown/tiktok/<creator>/
```

Useful commands:

```bash
media2md status
media2md status --output ndjson
media2md runtime path
```

Recent `creator run` output also prints:

- the result folder
- the latest markdown path
- an `open` command hint you can paste into Terminal

## 8. Health checks and diagnostics

Run a broad environment check:

```bash
media2md doctor all
```

Target a specific access path:

```bash
media2md doctor youtube-access --video-id <video-id> --transcription-smoke-test
media2md doctor tiktok-access --video-id <video-id> --creator <creator>
```

## 9. Backup your state

```bash
media2md data backup --destination ~/media2md-backups
media2md data verify-backup ~/media2md-backups/media2md-state-YYYYMMDDTHHMMSSZ.zip
```

## 10. Move the runtime if needed

To relocate the managed base path:

```bash
media2md runtime set-base-path <path>
```

Then confirm:

```bash
media2md runtime base-path
media2md runtime path
```

## 11. Uninstall

Preview:

```bash
media2md uninstall --dry-run
```

Remove the installed package:

```bash
media2md uninstall
```

Purge managed data as well:

```bash
media2md uninstall --purge-data --yes --confirm DELETE-ALL-DATA
```
