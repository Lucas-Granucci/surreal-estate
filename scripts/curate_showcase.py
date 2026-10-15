"""Create public report projections after inspecting generated samples locally."""
import json
from pathlib import Path

from surreal_estate.webapp.showcase import public_report

root = Path('showcase')
(root / 'reports').mkdir(exist_ok=True)
entries = []
for item in json.loads((root / 'candidates.json').read_text()):
    if item.get('showcase_status') not in {'recommended', 'qualified'}:
        print('NOT_APPROVED', item['id'])
        continue
    snapshot = item.get('snapshot', f"exports/showcase/{item['id']}.json")
    if not Path(snapshot).exists():
        print('PENDING', item['id'])
        continue
    bench = public_report(snapshot)
    briefs = [r for r in bench['research'] if r.get('brief')]
    mapped = any(e['provider'] == 'openstreetmap' for e in bench['evidence'])
    if len(briefs) != 2 or not mapped:
        print('HOLD', item['id'], 'briefs', len(briefs), 'mapped', mapped)
        continue
    (root / 'reports' / f"{item['id']}.json").write_text(json.dumps(bench, ensure_ascii=False, indent=2) + '\n')
    entries.append({k: item[k] for k in ['id','label','description']} | {
        'address': bench['case']['address'], 'geography': bench['case']['geography'],
        'created_at': bench['case']['as_of'], 'address_source': item['source'],
        'review_note': item.get('review_note', ''),
    })
    print('READY', item['id'], len(bench['evidence']), 'sources')
(root / 'manifest.json').write_text(json.dumps({
    'contact_email': 'lucasgranucci08@gmail.com', 'reports': entries,
}, indent=2) + '\n')
