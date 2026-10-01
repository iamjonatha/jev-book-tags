import json
import os
from pathlib import Path
from calibre.db.legacy import LibraryDatabase
ROOT = Path(__file__).resolve().parents[1]
DEMO = ROOT / 'demo'
assert Path(os.environ['CALIBRE_CONFIG_DIRECTORY']).resolve() == (DEMO / 'calibre-config').resolve()
report = json.loads((DEMO / 'metadata-report.json').read_text())
descriptions = json.loads((DEMO / 'gutenberg-descriptions.json').read_text())
files = sorted((DEMO / 'epubs').glob('*.epub'))
legacy = LibraryDatabase(str(DEMO / 'calibre-library'))
db = legacy.new_api
try:
    for row, path in zip(report, files):
        ident = row['id']
        if row['status'] != 'Online description downloaded' and descriptions.get(path.name):
            db.set_field('comments', {ident: descriptions[path.name]})
            row['status'] = 'Description downloaded from Project Gutenberg (source-generated summary)'
        row['description'] = bool(db.field_for('comments', ident))
    assert len(db.all_book_ids()) == 15
    assert all(not db.field_for('tags', ident) for ident in db.all_book_ids())
    assert all(db.field_for('languages', ident) == ('eng',) for ident in db.all_book_ids())
    assert all('EPUB' in db.formats(ident) for ident in db.all_book_ids())
    assert all(row['description'] for row in report)
    (DEMO / 'metadata-report.json').write_text(json.dumps(report, indent=2) + '\n')
    print('Verified: 15 English books, 15 EPUBs, 15 descriptions, empty Tags')
finally:
    legacy.close()
