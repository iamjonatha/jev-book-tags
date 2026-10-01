# English demo collection

Run `python3 scripts/download_demo_books.py` from the project root to download all 15 books automatically. Valid existing EPUBs are reused. A one-second pause separates books; download failures are listed in `manifest.json` and produce a nonzero exit status.

Extract `JEVBookTags-demo-books.zip` and add all files in `epubs/` to a separate calibre library in one operation. These are original Project Gutenberg EPUBs; their existing subject metadata has not been removed. Clear the Tags field in the demo library before recording, while preserving titles, authors and other metadata. English plugin categories and real JEV classification will be configured separately.

`manifest.json` records the official source pages, download URLs, and SHA-256 checksums. The ZIP is a local preparation artifact and is not intended to be committed to the plugin repository. Source licensing information is retained inside the original EPUBs. Project Gutenberg identifies these editions as public domain in the United States; check local requirements before distributing them elsewhere.
