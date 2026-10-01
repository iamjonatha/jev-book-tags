#!/usr/bin/env python3
"""Prepare validated release assets and MobileRead handoff without network calls."""
import argparse
import ast
import hashlib
import json
import os
from pathlib import Path
import re
import runpy
import shutil
import zipfile
ROOT = Path(__file__).resolve().parents[1]

def prepare(repo):
    if not re.fullmatch(r'[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+', repo):
        raise ValueError('Invalid repository name')
    brand = runpy.run_path(str(ROOT / 'plugin/branding.py'))
    version_tuple = brand['VERSION']
    if len(version_tuple) != 3 or any(type(v) is not int or v < 0 for v in version_tuple):
        raise ValueError('Version must be three nonnegative integers')
    version = '.'.join(map(str, version_tuple)); tag = 'v' + version
    tree = ast.parse((ROOT / 'plugin/__init__.py').read_text())
    declared = {node.targets[0].id:ast.literal_eval(node.value)
                for node in ast.walk(tree) if isinstance(node, ast.Assign)
                and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name)
                and node.targets[0].id in ('name','version','minimum_calibre_version')}
    if declared['version'] != version_tuple or declared['name'] != brand['NAME']:
        raise ValueError('Plugin metadata and branding must agree')
    changelog = (ROOT / 'CHANGELOG.md').read_text()
    match = re.search(r'^## ' + re.escape(version) + r' — [0-9-]+\n(.*?)(?=^## |\Z)', changelog, re.M | re.S)
    if not match or not match[1].strip():
        raise ValueError('Add a nonempty changelog section for this version')
    notes = match[1].strip()
    package = ROOT / 'dist' / ('JEVBookTags-' + version + '.zip')
    with zipfile.ZipFile(package) as archive:
        if archive.testzip() is not None:
            raise ValueError('Invalid ZIP')
        if archive.read('__init__.py') != (ROOT / 'plugin/__init__.py').read_bytes():
            raise ValueError('Rebuild the ZIP after modifying the plugin')
    out = ROOT / 'dist/release'; out.mkdir(parents=True, exist_ok=True)
    shutil.copy2(package, out / package.name)
    shutil.copy2(package, out / 'JEVBookTags.zip')
    url = 'https://github.com/' + repo
    release_url = url + '/releases/tag/' + tag
    (out / 'release-notes.md').write_text(notes + '\n\n[Documentation and demo](' + url + '/blob/main/docs/DEMO.md)\n')
    post = f'''[B]JEV Book Tags {version}[/B]

Automatically suggest subject and genre tags for one book, a selection, or an entire calibre library using TypeSafe AI JEV. Keep your own vocabulary and preserve existing tags.

[B]Requirements[/B]
calibre 9.0 or newer; Windows, macOS or Linux; TypeSafe AI API key and sufficient account credits. English and Italian interfaces. This is an independent community plugin.

[B]Usage[/B]
Install the single attached JEVBookTags.zip via Preferences > Plugins > Load plugin from file, then restart calibre. Open JEV Book Tags > Settings, enter your API key, test the connection, and configure your categories. Use the plugin menu to classify books.

Single-book results offer clickable tags. Batch results offer a compact list, status filters, and book details. Each assigned tag must reach its threshold; uncertain suggestions require confirmation. Existing tags are preserved. The metadata-editor button stages tags until you press OK.

Advanced options include model selection, assignment mode, and thresholds. Developer mode is off by default. Successful API evaluations are cached. CSV export and eligible restore are available.

[B]Privacy and costs[/B]
Book metadata and optional partial EPUB excerpts are sent to TypeSafe AI. The complete ebook file is not uploaded. API usage may incur charges. API keys are never included in exported profiles or demo files. Model confidence is not measured accuracy.

[B]Links[/B]
[URL="{url}"]Source, documentation and screenshots[/URL]
[URL="{url}/blob/main/docs/DEMO.md"]Video and GIF demonstration[/URL]
[URL="{release_url}"]GitHub release and checksums[/URL]

[B]Version History[/B]
[SPOILER]
Version {version}
{notes}
[/SPOILER]
'''
    (out / 'MobileRead-post.txt').write_text(post)
    (out / 'MobileRead-index-request.txt').write_text(f'''Hello,

Please add JEV Book Tags to the GUI Plugins index.
Thread: REPLACE_WITH_PUBLISHED_MOBILEREAD_THREAD_URL
Internal plugin name: JEV Book Tags
Description: Suggest subject and genre tags with TypeSafe AI JEV for one book, selected books or an entire calibre library; preserve existing tags and review uncertain suggestions.
History: Yes
Source and releases: {url}
The first post has one plugin ZIP attached and a Version History spoiler.

Proposed index entry:
[*][URL="REPLACE_WITH_PUBLISHED_MOBILEREAD_THREAD_URL"]JEV Book Tags[/URL]
Suggest subject and genre tags with TypeSafe AI JEV; supports single-book and batch classification.
History: Yes;

Thank you.
''')
    (out / 'MobileRead-handoff.md').write_text(f'''## Publish {tag} on MobileRead

GitHub release: {release_url}

1. Create or edit the plugin thread in https://www.mobileread.com/forums/forumdisplay.php?f=237.
2. Use MobileRead-post.txt for the first post and attach **only JEVBookTags.zip**, replacing the previous plugin attachment for updates. Do not attach the media-kit ZIP to that post.
3. Keep Version History followed by a SPOILER block. Reserve a second post for future test builds.
4. For the first registration, fill the thread URL into MobileRead-index-request.txt and send it to an active calibre moderator.
5. After approval, verify the entry and version at https://plugins.calibre-ebook.com/ and in calibre's plugin updater.

No forum post or moderator message is sent by this workflow. The index is updated by MobileRead/calibre, not by GitHub alone.
''')
    media = out / ('JEVBookTags-media-' + version + '.zip')
    with zipfile.ZipFile(media, 'w', compression=zipfile.ZIP_DEFLATED) as archive:
        for path in sorted((ROOT / 'docs/media').glob('*')):
            if path.is_file(): archive.write(path, 'media/' + path.name)
        for name in ('DEMO.md','demo.html'):
            archive.write(ROOT / 'docs' / name, name)
    (out / 'SHA256SUMS').write_text(''.join(hashlib.sha256(p.read_bytes()).hexdigest() + '  ' + p.name + '\n'
                                for p in sorted(out.iterdir()) if p.is_file() and p.name != 'SHA256SUMS'))
    if os.environ.get('GITHUB_OUTPUT'):
        with open(os.environ['GITHUB_OUTPUT'], 'a') as stream:
            stream.write(f'version={version}\ntag={tag}\n')
    print(json.dumps({'version':version,'tag':tag,'assets':str(out)}))
    return out

if __name__ == '__main__':
    parser=argparse.ArgumentParser(); parser.add_argument('--repo',default='iamjonatha/jev-book-tags')
    prepare(parser.parse_args().repo)
