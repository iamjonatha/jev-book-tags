# JEV Book Tags

JEV Book Tags is a calibre plugin that uses TypeSafe AI JEV to suggest subject and genre tags for books in a calibre library. It preserves existing tags and lets you review suggestions before applying them.

> A short demo video or GIF is planned for a follow-up update. It is not included yet.

## Features

- Classify the current book, selected books, or the entire open library.
- Review and edit suggested tags, probabilities, evidence status, and the exact request input before applying results.
- Keep successful evaluations cached, retry failed books, and resume interrupted work.
- Export results as CSV and restore the most recent application when books have not changed since then.
- Configure tag categories, assignment thresholds, input mode, and single-tag or multi-tag behavior.
- Import and export tag vocabularies and complete profiles. Profiles never include API keys.
- Add a classification button to calibre's metadata editor.
- Follow calibre's interface language when a translation is installed; untranslated strings use the English source text.

## Install

1. Download the latest plugin ZIP from the project's GitHub Releases page.
2. In calibre, open **Preferences → Plugins → Load plugin from file**, choose the ZIP, and restart calibre.
3. Open **JEV Book Tags → Settings**, enter your TypeSafe AI API key, and use **Test connection**.
4. Select a model and configure the categories and input mode. The built-in starter categories are in English; you can edit or replace them.

The repository includes an optional expanded example vocabulary in [`jev-categories.json`](jev-categories.json). Import it from the plugin settings if you want to use those categories; importing replaces the current category list.

The plugin requires calibre 9.0 or newer. The ZIP is built from the files under `plugin/` by `python3 scripts/build.py`.

## Use

Choose **Classify current book**, **Classify selected books**, or **Classify entire library** from the plugin menu. The entire-library option includes books hidden by the current search or virtual library.

The preview shows existing tags, editable suggestions, probabilities, evidence sufficiency, input source, and status. Automatic application is disabled by default. Select the rows to apply, then choose **Apply checked rows**. Existing manual tags are preserved and duplicates are ignored.

The metadata editor button can appear beside the Tags field, in a dedicated row, or in the bottom button bar. It uses the metadata currently shown in the editor. Suggested tags are saved only when you confirm the metadata dialog with **OK**; **Cancel** discards them.

### Assignment modes

- **One tag:** suggest the highest-probability candidate. A near tie requires review.
- **Multiple tags:** suggest candidates above their category threshold and candidates close to the best score. The default closeness margin is 8 percentage points. Close candidates at or below 0.5 are not added just because they are close.

The default threshold is 0.85 and can be changed globally or per category. Low evidence and uncertain results require review. Probabilities do not guarantee correctness.

### Book data sent to TypeSafe AI

- **Metadata only:** title, authors, description without HTML, language, and series. Existing tags are not sent.
- **Metadata and EPUB excerpts:** adds the table of contents and up to eight samples distributed through the EPUB, up to the configured character limit. The full book file is not sent.
- **Automatic:** includes excerpts immediately when the description has fewer than 200 characters; otherwise it tries metadata first and adds excerpts when review is needed.

EPUB 2 and EPUB 3 are supported for text extraction. PDF, MOBI, and other formats use metadata only. OCR and DRM decryption are not supported. Descriptions are limited to 8,000 characters. Excerpts are read from the saved EPUB, even when metadata has been edited in the open dialog.

Each configured tag is evaluated independently, along with a check for sufficient evidence. Clear inclusion and exclusion rules help classification. Categories may overlap.

### Cache, export, and restore

Successful evaluations are cached per library. Changing the model, input, or category descriptions creates a distinct request; changing thresholds or assignment mode recalculates decisions without another request. Retry failed rows without repeating successful evaluations.

The CSV export includes suggestions, probabilities, input source, effective model, and newly used input tokens. A cached response uses zero new tokens; this does not mean its original request was free. The result summary counts ready, review, insufficient-evidence, and error rows.

Use **View sent input** to inspect the request payload, including partial EPUB excerpts. If book metadata or the EPUB changed after classification, classify it again before inspecting the corresponding input.

**Cancel processing** prevents new requests; the in-flight request completes within its timeout. **Restore last application** restores previous tags only when the book has not changed since the application. Stale previews are blocked when the library or metadata changes.

The local cache and journal are stored in calibre's configuration directory under `plugins/jev_catalog_data/`. They contain book identifiers, tags, and probabilities, but not API keys or book text. Keep the journal if you may need to restore changes. External EPUB edits made during processing are not monitored.

## Demo book collection

The repository includes `demo/manifest.json` and `scripts/download_demo_books.py` for preparing a separate test library from Project Gutenberg. Downloaded EPUB files and the generated archive are local artifacts and are excluded from Git. See [demo/README.md](demo/README.md) for details. Project Gutenberg identifies these editions as public domain in the United States; check local requirements before distributing the books elsewhere.

## Contributing

Bug reports, code changes, documentation improvements, and translations are welcome. Read [CONTRIBUTING.md](CONTRIBUTING.md) before opening an issue or pull request. Contributions are reviewed and approved by a maintainer before they are merged.

## Development

Build the installable plugin ZIP:

```sh
python3 scripts/build.py
```

Run the unit tests:

```sh
python3 -m unittest discover -s tests -v
```

The native calibre integration check requires `calibre-debug` and uses a temporary configuration and library. Its service responses are simulated; it does not send books or API keys to TypeSafe AI or modify a user's library. See [CONTRIBUTING.md](CONTRIBUTING.md) for the native check commands.

The project targets calibre 9.0 or newer. Native verification has been performed with calibre 9.13 on macOS; Windows, Linux, and other calibre versions still need platform-specific verification.

## License

This project is licensed under the GNU General Public License v3.0 or later. See [LICENSE](LICENSE).
