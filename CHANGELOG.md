# Changelog

## 1.1.1 — 2026-10-01

First public release of JEV Book Tags.

- Classify one book, selected books, or the entire calibre library with TypeSafe AI JEV.
- Choose clickable tags for a single book; use status filters and per-book details for batch classification.
- Assign only tags reaching their own thresholds; handle close scores explicitly in single-tag mode.
- Preserve existing tags, cache successful evaluations, export CSV results, and restore eligible applications.
- Configure categories, per-category thresholds, input mode, and jev-latest or jev-preview.
- Import and export vocabularies and classification profiles without API keys.
- Add a configurable classification icon to calibre's metadata editor; OK saves staged tags and Cancel discards them.
- Keep technical inspection and token statistics behind optional developer mode; collapse advanced settings by default.
- Provide English and Italian interfaces, following calibre's selected language.
- Include an edited demo using unchanged real JEV responses: 31 of 32 books ready under the current rules, one to review.

Requires calibre 9.0 or newer and a TypeSafe AI API key. Metadata and optional partial EPUB excerpts are sent to TypeSafe AI. This is an independent community plugin.
