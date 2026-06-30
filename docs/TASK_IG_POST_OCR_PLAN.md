# Task: Instagram Post + Carousel OCR Support

## Goal

Extend `media2md` so Instagram supports not only Reels, but also:

- single-image posts
- carousel posts with multiple images
- extraction of:
  - original post caption
  - OCR text from post images
  - ordered multi-image aggregation into one Markdown file

This task must preserve the current Instagram Reel pipeline and avoid regressions in existing creator sync / creator run behavior.


## Product Intent

The output should be usable by both humans and agents:

- one Instagram post => one Markdown file
- carousel OCR must remain ordered by image position
- image text should be grouped per image and also readable as a combined note set
- no external OCR API or LLM dependency is required
- computation should run on the user's machine


## Confirmed Decisions

### OCR install strategy

We will expose two OCR installation paths, similar to provider extras:

1. Apple path (macOS)
   - primary: Apple Vision OCR
   - fallback: EasyOCR

2. Windows/Linux path
   - primary: EasyOCR

`all` support should expose both routes conceptually:

- Apple users get Vision + EasyOCR fallback behavior
- Windows/Linux users get EasyOCR

Packaging design should keep OCR dependencies optional instead of forcing them into the default install.


### Extraction layer

Primary extraction layer:

- `Instaloader`

Fallback download layer:

- `gallery-dl`

Rationale:

- `Instaloader` is better for structured Instagram post metadata and sidecar enumeration.
- `gallery-dl` remains useful as a media artifact fallback path.


## Notes on Instagram `/tv/`

`https://www.instagram.com/tv/<code>/` refers to the older IGTV / Instagram TV surface.

Current understanding:

- historically used for long-form Instagram video posts
- the standalone IGTV product was discontinued in 2022
- legacy `/tv/<code>/` URLs may still exist for older content

Implementation guidance:

- keep `/tv/` support in normalization and extraction for compatibility
- treat it as a legacy video surface
- do not make `/tv/` the main product focus


## Architecture Recommendation

### Best integration layer

Primary integration should happen in:

- `src/media2md/bundle/scripts/generic_media.py`

Why:

- it already owns generic metadata ingestion
- it already writes Markdown artifacts
- it already updates registry state
- it is easier to branch by media type there than to mutate the legacy Reel-only worker

This is the safest path for preserving the current Reel workflow.


## Scope Boundary

### In scope for this task line

- single Instagram post URLs
- carousel post URLs
- caption extraction
- image download / retrieval
- local OCR
- one-Markdown-per-post rendering
- media typing and registry support

### Explicitly out of scope for the first implementation wave

- full creator post catalog sync mixed with reels
- generalized OpenCLI Instagram backend integration
- comment extraction
- likes / engagement analytics
- arbitrary story scraping
- external OCR APIs
- LLM post summarization


## Functional Design

### Input surfaces

Support these media URLs:

- `https://www.instagram.com/p/<code>/`
- `https://www.instagram.com/reel/<code>/`
- `https://www.instagram.com/tv/<code>/`


### Media taxonomy changes

Add new media types:

- `instagram_post`
- `instagram_carousel`

Keep existing:

- `instagram_reel`

Suggested output buckets:

- `instagram_reel` -> `reels`
- `instagram_post` -> `posts`
- `instagram_carousel` -> `posts`


### URL normalization changes

Current issue:

- Instagram media normalization accepts `p|reel|tv`
- but canonicalization tends to collapse to Reel URLs

Required change:

- preserve the detected surface during normalization
- keep canonical URL aligned with the real surface

Suggested surface values:

- `post`
- `reel`
- `tv`


### Extraction contract

Expand the Instagram helper to return structured assets for a post.

Suggested item shape:

```json
{
  "provider": "instagram",
  "external_id": "<shortcode>",
  "creator": "<handle>",
  "creator_external_id": "<creator-id>",
  "creator_display_name": "<display-name>",
  "title": "Instagram Post <shortcode>",
  "description": "<caption>",
  "published_at": "<iso8601>",
  "duration_seconds": null,
  "source_url": "https://www.instagram.com/p/<code>/",
  "backend_used": "instaloader",
  "surface": "post",
  "media_type": "instagram_post",
  "processing_class": "instagram_post",
  "assets": [
    {
      "index": 1,
      "kind": "image",
      "source_url": "<image-url>",
      "ocr_candidate": true
    }
  ]
}
```

For carousel:

- `media_type = instagram_carousel`
- `assets` ordered by carousel position


## OCR Strategy

### macOS route

Primary:

- Apple Vision OCR

Fallback:

- EasyOCR

Behavior:

- default `ocr_engine=auto`
- on macOS, `auto` means:
  - try `vision`
  - if unavailable or failed in a recognized recoverable way, try `easyocr` if installed


### Windows/Linux route

Primary:

- EasyOCR

Behavior:

- `ocr_engine=auto` resolves to `easyocr`


### No LLM requirement

This feature does not require an LLM.

OCR responsibilities:

- detect text
- preserve image order
- keep per-image OCR text separate
- optionally combine per-image text into a single readable section


## Config Design

Suggested provider config keys:

```json
{
  "providers": {
    "instagram": {
      "backend": "auto",
      "ocr_engine": "auto",
      "ocr_languages": ["en", "ja", "zh"],
      "ocr_on_posts": true
    }
  }
}
```

Accepted `ocr_engine` values:

- `auto`
- `vision`
- `easyocr`
- `disabled`


## Markdown Design

One Instagram post should produce one Markdown file.

Suggested structure:

```md
---
platform: instagram
creator: "<creator>"
media_id: "<shortcode>"
media_type: "instagram_carousel"
surface: "post"
source_url: "https://www.instagram.com/p/<code>/"
published_at: "<iso8601>"
ocr_engine: "vision"
image_count: 4
---

# Instagram Post: <shortcode>

## Original Caption

<caption text>

## Image OCR

### Image 1

<ocr text for image 1>

### Image 2

<ocr text for image 2>

## Combined OCR Notes

<ordered concatenation / normalized combined text>
```

Rules:

- keep per-image OCR sections
- keep final combined section for agent ingestion
- if an image has no text, record that cleanly instead of failing the whole post


## Implementation Plan

### Batch A: Foundations + single-post path

Goal:

- lay the type / URL / metadata groundwork
- support single post URL ingestion without touching creator full-sync behavior

Work:

1. update shared URL normalization to preserve Instagram surface
2. add new media types and buckets
3. expand Instagram extraction helper for post metadata
4. support single post ingest through generic media path
5. add tests for normalization and metadata typing

Exit criteria:

- a single `instagram.com/p/...` URL is recognized as post, not reel
- metadata persists with correct `media_type`
- no Reel regressions


### Batch B: OCR engine abstraction + Markdown rendering

Goal:

- add OCR engine abstraction and post renderer

Work:

1. create OCR adapter abstraction
2. implement macOS Vision OCR route
3. implement EasyOCR route
4. implement auto-selection logic
5. render OCR-aware Markdown for post/carousel items
6. add tests for OCR pipeline behavior with fixtures/mocks

Exit criteria:

- single-image post generates Markdown with caption + OCR section
- OCR engine selection is deterministic
- missing OCR text does not fail the whole artifact


### Batch C: Carousel support + artifact orchestration

Goal:

- fully support multi-image posts

Work:

1. add ordered asset retrieval for sidecar posts
2. OCR each image in order
3. generate one Markdown file with grouped per-image sections
4. add output path / result reporting
5. add regression tests for ordering and aggregation

Exit criteria:

- one carousel post => one Markdown file
- all images are handled in order
- combined OCR section is stable


### Batch D: Packaging + CLI + docs polish

Goal:

- make the feature installable and user-facing

Work:

1. add optional dependency groups for OCR routes
2. expose provider/help/docs updates
3. document Apple vs Windows/Linux install guidance
4. add doctor/status visibility for OCR capability if needed
5. run full QA

Exit criteria:

- users can clearly choose OCR install route
- docs match actual behavior
- release surface remains coherent


## Recommended Execution Cadence

Do this in **4 batches**, not 8 separate micro-turns and not 3 overly large waves.

Recommended user instruction cadence:

1. Batch A
2. Batch B
3. Batch C
4. Batch D

Why 4:

- smaller than a giant all-in-one implementation
- larger than overly fragmented phase-by-phase coordination
- preserves momentum while keeping risk bounded


## Testing Plan

### Required tests

1. URL normalization
   - `/p/` stays post
   - `/reel/` stays reel
   - `/tv/` stays tv/legacy-video

2. media type inference
   - image post -> `instagram_post`
   - sidecar image post -> `instagram_carousel`

3. extraction contract
   - post metadata shape
   - ordered assets
   - sidecar parsing

4. OCR routing
   - macOS auto prefers Vision
   - macOS fallback to EasyOCR
   - Windows/Linux auto resolves to EasyOCR
   - disabled OCR path behaves cleanly

5. markdown rendering
   - one post -> one Markdown
   - per-image sections preserved
   - combined OCR section present

6. regressions
   - current Instagram Reel path still works
   - creator run / refresh-catalog behavior for reels unchanged


## Risks

1. Instagram upstream instability
   - `Instaloader` is structurally good but upstream can break

2. OCR dependency weight
   - EasyOCR adds Torch and model download overhead

3. Cross-platform behavior differences
   - Apple Vision is macOS-specific

4. Over-coupling posts into the current Reel sync model
   - avoid mixing creator full post sync into first wave


## Risk Controls

1. keep first wave to single-post / carousel media URLs
2. preserve current Reel pipeline as-is
3. keep OCR optional
4. use explicit media types to avoid ambiguous branching
5. mock OCR/extractor behavior in tests instead of requiring live Instagram during CI


## Definition of Done

This task line is done when:

1. `media2md` can ingest an Instagram single-image post URL
2. `media2md` can ingest an Instagram carousel URL
3. caption is preserved
4. image OCR text is extracted locally
5. one post produces one Markdown artifact
6. carousel image text is grouped and ordered correctly
7. Reel behavior remains green
8. packaging/docs clearly describe Apple vs Windows/Linux OCR install paths

