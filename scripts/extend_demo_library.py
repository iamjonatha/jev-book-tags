"""Add missing demonstration books to the isolated demo library only."""
import json
import os
import sqlite3
from pathlib import Path
from calibre.db.legacy import LibraryDatabase
from calibre.ebooks.metadata.meta import get_metadata
from calibre.ebooks.metadata.book.base import Metadata
ROOT = Path(__file__).resolve().parents[1]
DEMO = ROOT / 'demo'
LIBRARY = DEMO / 'calibre-library'
assert Path(os.environ['CALIBRE_CONFIG_DIRECTORY']).resolve() == (DEMO / 'calibre-config').resolve()
# Recoverable snapshot of demo metadata before adding anything.
with sqlite3.connect(str(LIBRARY / 'metadata.db')) as source:
    with sqlite3.connect(str(DEMO / 'metadata-before-extension.db')) as target:
        source.backup(target)
legacy = LibraryDatabase(str(LIBRARY))
db = legacy.new_api
report = []
try:
    existing = {(db.field_for('title', i), tuple(db.field_for('authors', i))) for i in db.all_book_ids()}
    descriptions = json.loads((DEMO / 'gutenberg-descriptions.json').read_text())
    for book in json.loads((DEMO / 'manifest.json').read_text())['books']:
        path = DEMO / 'epubs' / book['file']
        with path.open('rb') as stream:
            mi = get_metadata(stream, 'epub')
        if (mi.title, tuple(mi.authors)) in existing: continue
        mi.tags = []; mi.languages = ['eng']
        if descriptions.get(path.name): mi.comments = descriptions[path.name]
        added, duplicates = db.add_books([(mi, {'EPUB': str(path)})])
        report.append({'title': mi.title, 'id': next(iter(added)), 'file': path.name})
    for book in json.loads((DEMO / 'technical/sources.json').read_text()):
        if (book['title'], tuple(book['authors'])) in existing: continue
        mi = Metadata(book['title'], book['authors']); mi.tags = []; mi.languages = ['eng']
        mi.comments = '<p>' + book['description'] + '</p><p>Source: ' + book['page'] + '. License: ' + book['license'] + '.</p>'
        added, duplicates = db.add_books([(mi, {book['format']: str(DEMO / 'technical' / book['file'])})])
        report.append({'title': mi.title, 'id': next(iter(added)), 'file': book['file']})
    ids = db.all_book_ids()
    assert len(ids) == 32, len(ids)
    assert all(db.field_for('languages', i) == ('eng',) for i in ids)
    print('Verified 32 English books. Added:', len(report))
    (DEMO / 'extension-report.json').write_text(json.dumps(report, indent=2)+'\n')
finally:
    legacy.close()
