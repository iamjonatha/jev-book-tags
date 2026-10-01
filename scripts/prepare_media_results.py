"""Re-evaluate unmodified real API scores for current UI; no network or library writes."""
import copy
import csv
import json
import runpy
from datetime import datetime, timezone
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'docs/media'
WORK = ROOT / 'demo/media-work'
archive = OUT / 'real-results-1.0.3.json'
if not archive.exists():
    archive.write_bytes((OUT / 'real-results.json').read_bytes())
original = json.loads(archive.read_text())
core = runpy.run_path(str(ROOT / 'plugin/core.py'))
brand = runpy.run_path(str(ROOT / 'plugin/branding.py'))
settings = copy.deepcopy(core['DEFAULTS'])
settings.update({k: original[k] for k in ('model', 'categories', 'threshold', 'tag_mode', 'tie_margin')})
for category in settings['categories']:
    category['threshold'] = .95 if category['name'] == 'Programming' else None
core['validate_settings'](settings)
raw = json.loads((WORK / 'raw-results.json').read_text())
recorded = {r['book_id']:r for r in original['results']}
assert len(raw)==len(recorded)==32
public = []
for result in raw:
    assert result['evaluation']==recorded[result['book_id']]['evaluation'], 'Recorded API response changed'
    has_material = len(core['metadata_state'](result['metadata'])['book']['description']) >= 200 or result['source'] == 'content'
    result.update(core['decide'](result['evaluation'], settings, has_material))
    result['tokens_billed'] = 0
    public.append({k: result.get(k) for k in ('book_id', 'title', 'tags', 'status', 'reason', 'supported', 'source', 'tokens_billed', 'evaluation')})
(WORK / 'current-results.json').write_text(json.dumps(raw, indent=2)+'\n')
(WORK / 'current-settings.json').write_text(json.dumps(settings, indent=2)+'\n')
report = dict(original, plugin_version='.'.join(map(str, brand['VERSION'])),
              categories=settings['categories'], results=public,
              evaluation_origin='Unmodified real JEV responses recorded by version 1.0.3; decisions recalculated with current rules.',
              decisions_updated_at_utc=datetime.now(timezone.utc).isoformat(),
              new_api_calls=0, original_input_tokens=sum(b['tokens_billed'] for b in original['results']))
report['original_api_elapsed_seconds'] = report.pop('elapsed_seconds')
(OUT / 'real-results.json').write_text(json.dumps(report, indent=2)+'\n')
with (OUT / 'real-results.csv').open('w', newline='') as stream:
    writer=csv.writer(stream, lineterminator="\n"); writer.writerow(['title','suggested_tags','status','source','evidence','new_input_tokens','decision_reason'])
    for r in public:
        writer.writerow([r['title'],'; '.join(r['tags']),r['status'],r['source'],r['evaluation']['probabilities']['evidence'],0,r['reason']])
(OUT / 'demo-categories-en.json').write_text(json.dumps({'version':1,'categories':settings['categories']},indent=2)+'\n')
print('Real cached results:',sum(r['status']=='ready' for r in public),'ready;',sum(r['status']=='review' for r in public),'review; no API calls.')
