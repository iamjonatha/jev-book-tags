"""Run with calibre-debug -e, using the isolated demo profile."""
import json
import os
import subprocess
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from calibre.db.legacy import LibraryDatabase
from calibre.ebooks.metadata.meta import get_metadata
from calibre.ebooks.metadata.opf2 import OPF

ROOT = Path(__file__).resolve().parents[1]
DEMO = ROOT / 'demo'
LIBRARY = DEMO / 'calibre-library'
assert Path(os.environ['CALIBRE_CONFIG_DIRECTORY']).resolve() == (DEMO / 'calibre-config').resolve()
if (LIBRARY / 'metadata.db').exists():
    raise SystemExit('Demo library already exists; refusing to replace it.')

books = []
for path in sorted((DEMO / 'epubs').glob('*.epub')):
    with path.open('rb') as stream:
        mi = get_metadata(stream, 'epub')
    books.append((path, mi))

def download(item):
    path, original = item
    opf = DEMO / 'metadata' / (path.stem + '.opf')
    args = ['/Applications/calibre.app/Contents/MacOS/fetch-ebook-metadata',
            '--title', original.title, '--authors', ' & '.join(original.authors),
            '--allowed-plugin', 'Google', '--allowed-plugin', 'Open Library',
            '--timeout', '20', '--opf']
    try:
        proc = subprocess.run(args, capture_output=True, timeout=35)
        data = proc.stdout
        start = data.find(b'<?xml')
        if start >= 0:
            data = data[start:]
        candidate = OPF(__import__('io').BytesIO(data), str(DEMO / 'metadata')).to_book_metadata()
        # Retain the edition's identity and language; enrich description only.
        if proc.returncode == 0 and candidate.comments:
            opf.write_bytes(data)
            original.comments = candidate.comments
            status = 'Online description downloaded'
        else:
            status = 'Original EPUB metadata retained; no online description available'
    except Exception:
        status = 'Original EPUB metadata retained; online lookup unavailable'
    original.tags = []
    original.languages = ['eng']
    print(original.title + ': ' + status, flush=True)
    return path, original, status

with ThreadPoolExecutor(max_workers=3) as pool:
    enriched = list(pool.map(download, books))
legacy = LibraryDatabase(str(LIBRARY))
db = legacy.new_api
report = []
try:
    for path, mi, status in enriched:
        added, duplicates = db.add_books([(mi, {'EPUB': str(path)})])
        report.append({'title': mi.title, 'authors': mi.authors, 'status': status,
                       'id': next(iter(added)), 'description': bool(mi.comments)})
    (DEMO / 'metadata-report.json').write_text(json.dumps(report, indent=2) + '\n')
    print(f'Prepared {len(report)} books in {LIBRARY}', flush=True)
finally:
    legacy.close()
