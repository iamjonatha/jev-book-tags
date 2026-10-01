# English demo collection

Run `python3 scripts/download_demo_books.py` from the project root to download all 15 books automatically. Valid existing EPUBs are reused. A one-second pause separates books; download failures are listed in `manifest.json` and produce a nonzero exit status.

Extract `JEVBookTags-demo-books.zip` and add all files in `epubs/` to a separate calibre library in one operation. These are original Project Gutenberg EPUBs; their existing subject metadata has not been removed. Clear the Tags field in the demo library before recording, while preserving titles, authors and other metadata. English plugin categories and real JEV classification will be configured separately.

`manifest.json` records the official source pages, download URLs, and SHA-256 checksums. The ZIP is a local preparation artifact and is not intended to be committed to the plugin repository. Source licensing information is retained inside the original EPUBs. Project Gutenberg identifies these editions as public domain in the United States; check local requirements before distributing them elsewhere.

## Extended collection and English categories

The collection now contains 30 Project Gutenberg classics plus two freely licensed technical books: Pro Git (EPUB, CC BY-NC-SA 3.0) and The Linux Command Line, Seventh Internet Edition (PDF, CC BY-NC-ND 3.0). Technical books are not public-domain works. Their official download URLs and license notes are in `technical/sources.json`; preserve the originals and source attribution.

Import `JEVBookTags-categories-en.json` from the JEV Book Tags settings using Import categories, then save. It contains 18 enabled English categories with English definitions and the default confidence threshold. Computing and Programming intentionally overlap for multi-tag classification; Fiction and Essays & Nonfiction are defined as fallback subjects rather than universal umbrella categories. AI and Data Science are provided for future technical additions.

The PDF technical book is classified using its title, authors and supplied English description; the plugin does not extract PDF content. Pro Git supports the EPUB extraction path. No JEV calls or simulated classifications were performed during library preparation.
