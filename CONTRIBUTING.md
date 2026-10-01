# Contributing

Thanks for helping improve JEV Book Tags. Bug reports, code, documentation, and interface translations are welcome. All source code, code comments, and project documentation should be written in English so maintainers can review them consistently. Translations are the exception: keep the source keys in English and translate only their values.

## Before you start

1. Search existing issues and pull requests for related work.
2. For a substantial change, open an issue first so the proposed behavior can be discussed.
3. Never include API keys, calibre library databases, private book files, or personal data in an issue, commit, or test fixture.

## Code and documentation changes

1. Create a focused branch from the project's default branch.
2. Keep changes small and explain user-visible behavior in English.
3. Mark every new interface string with calibre's `_()` translation function and use the English source text in the code.
4. Add or update tests for behavior changes.
5. Run the checks listed below and report any platform-specific checks you could not run.
6. Open a pull request with a clear summary, the reason for the change, and test results.

Pull requests require maintainer review and approval before merge. A passing build is not approval. Do not merge your own contribution unless a maintainer explicitly asks you to.

## Add or update an interface translation

Translations are stored as JSON maps under `translations/`. The English source string is each key, and the translated interface string is its value.

1. Copy `translations/it.json` to `translations/<locale>.json`, using the locale code calibre uses for the language (for example, `es.json` or `pt_BR.json`).
2. Keep every English key unchanged and translate its value. Keep formatting placeholders such as `{count}`, `{name}`, `{processed}`, and `{total}` exactly as written. Do not translate product names, API identifiers, or values that are code/configuration tokens.
3. Keep the JSON valid, UTF-8 encoded, and complete. Every source key must have a non-empty translation. Do not edit generated `.mo` files; the build creates them.
4. Build the plugin and run the unit tests. If you have calibre installed, also test with that interface locale.
5. Submit a pull request containing the new or updated JSON file. In the description, name the locale and mention whether a native speaker reviewed it.

The English source strings are collected in `translations/messages.pot`. When changing interface text in code, run the build to refresh the gettext template and Italian catalog. Translate only strings that are wrapped in `_()`; ordinary code messages and logs should remain clear English.

Maintainers review that keys are complete, placeholders are preserved, wording is consistent, and the translated controls fit the interface. A translation becomes part of the project only after maintainer approval and merge. Maintainers may request changes or help find a native-speaker reviewer before approving it.

## Build and checks

Build the installable ZIP and compile all available translations:

```sh
python3 scripts/build.py
```

Run the unit tests:

```sh
python3 -m unittest discover -s tests -v
```

The native integration check requires calibre's `calibre-debug` and `calibre-customize` commands. It creates an isolated temporary configuration and library, installs the generated ZIP, and uses simulated service responses:

```sh
python3 scripts/build.py
python3 scripts/test_calibre.py --language en
python3 scripts/test_calibre.py --language it
```

These checks do not call TypeSafe AI with real books or keys and do not modify a user's library. The `dist/` directory contains local build artifacts and is not committed.

## Pull request review

Maintainers will review correctness, compatibility, documentation, and tests. Translation pull requests should include only the translation catalog unless the interface source text or gettext template also changed. A pull request is merged only after maintainer approval; submitting it does not guarantee acceptance.
