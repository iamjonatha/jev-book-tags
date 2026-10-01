import json,os,runpy
from pathlib import Path
from calibre.db.legacy import LibraryDatabase
ROOT=Path(__file__).resolve().parents[1]; DEMO=ROOT/'demo'
assert Path(os.environ['CALIBRE_CONFIG_DIRECTORY']).resolve()==(DEMO/'calibre-config').resolve()
legacy=LibraryDatabase(str(DEMO/'calibre-library')); db=legacy.new_api
try:
 old=db.pref('jev_catalog_settings',default=None)
 backup=DEMO/'categories-before-english-import.json'
 if not backup.exists(): backup.write_text(json.dumps(old,indent=2)+'\n')
 core=runpy.run_path(str(ROOT/'plugin/core.py'))
 settings=core['DEFAULTS'].copy(); settings.update(old or {})
 settings['categories']=json.loads((DEMO/'JEVBookTags-categories-en.json').read_text())['categories']
 core['validate_settings'](settings); db.set_pref('jev_catalog_settings',settings)
 print('Demo categories configured:', ', '.join(c['name'] for c in settings['categories']))
finally: legacy.close()
