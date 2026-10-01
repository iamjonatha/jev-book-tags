# Releases and calibre's plugin updater

Changes on `main` and pull requests run the build, classification tests, and native English/Italian calibre checks in temporary profiles and libraries. Each successful run uploads a release artifact containing the installable ZIP, changelog, checksums, media kit, and MobileRead text.

To publish a new version:

1. Update the three-part version in both `plugin/branding.py` and `plugin/__init__.py`.
2. Add a nonempty version section to `CHANGELOG.md`. Update documentation/media when behavior changed.
3. Merge and push the validated commit to the `release` branch. No force push is needed.
4. The workflow repeats validation, creates `vX.Y.Z`, prepares a draft with its assets, then publishes it. Existing releases are never overwritten: another push with the same version only produces a new test artifact.
5. Keep the generated MobileRead handoff for future registration. Forum publication is currently deferred.

`JEVBookTags.zip` is the stable download filename; the versioned ZIP contains the same bytes. SHA256SUMS includes package and supplementary asset hashes. Only the plugin ZIP belongs on the first MobileRead post; never attach a second ZIP there. GitHub's source archives and the media-kit ZIP are not installable calibre plugins.

## MobileRead registration

Create a thread titled **[GUI Plugin] JEV Book Tags** in the [calibre Plugins forum](https://www.mobileread.com/forums/forumdisplay.php?f=237). Paste the generated `MobileRead-post.txt`, attach exactly one `JEVBookTags.zip`, and reserve a second post for development builds. Replace the placeholder thread URL in `MobileRead-index-request.txt` and send it to an active calibre moderator.

The [official index instructions](https://www.mobileread.com/forums/showthread.php?t=118764) require the attached ZIP on the first post and a moderator request. Version, minimum calibre, author and platforms are extracted from plugin metadata. `Version History` followed by a spoiler enables history display when the index entry specifies `History: Yes`.

After moderator approval, verify [the calibre plugin index](https://plugins.calibre-ebook.com/) and the update offered by calibre. GitHub publication alone does not register the plugin or activate calibre updates. No forum credentials are stored in GitHub; no unsupported forum automation is implemented. Each release prepares the handoff files without publishing on the forum or opening a reminder issue.

## Local preparation

```sh
python3 scripts/build.py
python3 scripts/prepare_release.py --repo iamjonatha/jev-book-tags
```

Assets are written to ignored `dist/release/`. Native CI tests use simulated responses; documentation uses genuine, unchanged recorded responses and labels cache reuse. No user library or API key is needed by CI.
