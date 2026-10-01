#!/usr/bin/env python3
"""Download a reusable English demo collection from official ebook pages."""
import argparse
import hashlib
import json
import time
import urllib.request
import zipfile
from pathlib import Path
from urllib.parse import urlparse

BOOKS = [
    (1342, 'pride-and-prejudice'), (1260, 'jane-eyre'),
    (730, 'oliver-twist'), (2852, 'the-hound-of-the-baskervilles'),
    (155, 'the-moonstone'), (204, 'the-innocence-of-father-brown'),
    (11, 'alices-adventures-in-wonderland'), (325, 'phantastes'),
    (55, 'the-wonderful-wizard-of-oz'), (35, 'the-time-machine'),
    (36, 'the-war-of-the-worlds'), (84, 'frankenstein'),
    (2376, 'up-from-slavery'), (1228, 'on-the-origin-of-species'),
    (3420, 'a-vindication-of-the-rights-of-woman'),
    (2701, 'moby-dick'), (1661, 'the-adventures-of-sherlock-holmes'),
    (174, 'the-picture-of-dorian-gray'), (120, 'treasure-island'),
    (219, 'heart-of-darkness'), (1400, 'great-expectations'),
    (76, 'adventures-of-huckleberry-finn'), (74, 'the-adventures-of-tom-sawyer'),
    (161, 'sense-and-sensibility'), (1322, 'leaves-of-grass'),
    (345, 'dracula'), (43, 'dr-jekyll-and-mr-hyde'),
    (17396, 'the-secret-garden'), (205, 'walden'), (3207, 'leviathan'),
]


def fetch(url):
    if urlparse(url).hostname not in ('www.gutenberg.org', 'gutenberg.org'):
        raise ValueError('Unexpected download host')
    req = urllib.request.Request(url, headers={'User-Agent': 'JEVBookTags-Demo/1.0'})
    with urllib.request.urlopen(req, timeout=45) as response:
        return response.read()

def valid_epub(path):
    try:
        with zipfile.ZipFile(path) as z:
            return z.read('mimetype') == b'application/epub+zip' and 'META-INF/container.xml' in z.namelist() and z.testzip() is None
    except (OSError, KeyError, zipfile.BadZipFile):
        return False

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=Path(__file__).resolve().parents[1] / 'demo')
    args = parser.parse_args()
    target = args.output / 'epubs'
    target.mkdir(parents=True, exist_ok=True)
    results, failures = [], []
    for book_id, slug in BOOKS:
        page = f'https://www.gutenberg.org/ebooks/{book_id}'
        path = target / (slug.replace('/', '_') + '.epub')
        try:
            download = f'https://www.gutenberg.org/cache/epub/{book_id}/pg{book_id}-images-3.epub'
            if not valid_epub(path):
                temp = path.with_suffix('.part')
                try:
                    try:
                        payload = fetch(download)
                    except Exception:
                        download = f'https://www.gutenberg.org/cache/epub/{book_id}/pg{book_id}.epub'
                        payload = fetch(download)
                    temp.write_bytes(payload)
                    if not valid_epub(temp):
                        raise ValueError('Invalid EPUB')
                    temp.replace(path)
                finally:
                    temp.unlink(missing_ok=True)
            results.append({'page': page, 'download': download, 'file': path.name,
                            'sha256': hashlib.sha256(path.read_bytes()).hexdigest()})
            print('OK ' + path.name, flush=True)
        except Exception as exc:
            failures.append({'page': page, 'error': str(exc)})
            print('FAILED ' + page + ': ' + str(exc), flush=True)
        time.sleep(1)
    manifest = {'source': 'Project Gutenberg', 'language': 'English', 'books': results, 'failures': failures}
    (args.output / 'manifest.json').write_text(json.dumps(manifest, indent=2) + '\n', encoding='utf-8')
    archive = args.output / 'JEVBookTags-demo-books.zip'
    with zipfile.ZipFile(archive, 'w', zipfile.ZIP_DEFLATED) as z:
        for book in results:
            z.write(target / book['file'], 'epubs/' + book['file'])
        z.write(args.output / 'manifest.json', 'manifest.json')
    print(f'{len(results)}/{len(BOOKS)} books: {archive}', flush=True)
    return 1 if failures else 0

if __name__ == '__main__':
    raise SystemExit(main())
