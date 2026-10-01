"""Record genuine JEV evaluations in an isolated copy of the demo library."""
import csv
import runpy
import json
import os
import shutil
import time
from datetime import datetime,timezone
from pathlib import Path

from calibre.customize.ui import load_plugin
from calibre.db.legacy import LibraryDatabase

ROOT=Path(__file__).resolve().parents[1]
WORK=ROOT/'demo/media-work'
assert Path(os.environ['CALIBRE_CONFIG_DIRECTORY']).resolve()==(WORK/'config').resolve()
if not (WORK/'library/metadata.db').exists():
    shutil.copytree(ROOT/'demo/calibre-library',WORK/'library')
brand=runpy.run_path(str(ROOT/'plugin/branding.py'))
version='.'.join(map(str,brand['VERSION']))
load_plugin(str(ROOT/'dist'/('JEVBookTags-'+version+'.zip')))
from calibre_plugins.jev_catalog.client import JevClient,JevError
from calibre_plugins.jev_catalog.credentials import CredentialStore
from calibre_plugins.jev_catalog.dialog import book_metadata
from calibre_plugins.jev_catalog.engine import classify
from calibre_plugins.jev_catalog.settings import load_settings
from calibre_plugins.jev_catalog.storage import Store

source_profile=os.environ.get('JEV_SOURCE_CONFIG_DIRECTORY')
if not source_profile:
    raise SystemExit('Set JEV_SOURCE_CONFIG_DIRECTORY to the calibre profile containing the saved key. No API calls performed.')
key=CredentialStore(source_profile).read()
if not key: raise SystemExit('No saved API key available. No API calls performed.')
client=JevClient(key)
key=''
legacy=LibraryDatabase(str(WORK/'library'));db=legacy.new_api
settings=load_settings(db)
store=Store(str(WORK/'cache'),'github-demo-recording-v1')
results=[]; started=datetime.now(timezone.utc).isoformat(); tic=time.monotonic()
try:
    for ident in sorted(db.all_book_ids()):
        metadata=book_metadata(db,ident)
        formats=db.formats(ident) or ()
        loader=(lambda ident=ident: db.format(ident,'EPUB',as_file=True)) if 'EPUB' in formats else None
        try:
            result=classify(metadata,settings,client,store,loader)
            result.update(book_id=ident,title=metadata['title'],metadata=metadata,
                          previous_tags=list(db.field_for('tags',ident) or []))
        except JevError:
            print('API request failed; stopped without revealing service response.',flush=True)
            break
        results.append(result)
        (WORK/'raw-results.json').write_text(json.dumps(results,indent=2))
        print(f"{len(results)}/{len(db.all_book_ids())}: {metadata['title']} | {result['status']} | {', '.join(result.get('tags',[]))}",flush=True)
finally: legacy.close()
public=[]
for r in results:
    public.append({k:r.get(k) for k in ('book_id','title','tags','status','supported','source','tokens_billed','evaluation')})
report={'recorded_at_utc':started,'elapsed_seconds':round(time.monotonic()-tic,2),
        'plugin_version':version,'service':'TypeSafe AI JEV','model':settings['model'],
        'input_mode':settings['mode'],'threshold':settings['threshold'],
        'tag_mode':settings['tag_mode'],'tie_margin':settings['tie_margin'],
        'categories':settings['categories'],'total_books':32,'processed_books':len(public),
        'results':public,'simulated':False}
(ROOT/'docs/media/real-results.json').write_text(json.dumps(report,indent=2)+'\n')
with (ROOT/'docs/media/real-results.csv').open('w',newline='') as stream:
    writer=csv.writer(stream, lineterminator="\n");writer.writerow(['title','suggested_tags','status','source','evidence','new_input_tokens'])
    for r in public:
        writer.writerow([r['title'],'; '.join(r['tags']),r['status'],r['source'],r['evaluation']['probabilities'].get('evidence'),r['tokens_billed']])
print('Completed:',len(public),'genuine evaluations. API key not saved or exported.',flush=True)
