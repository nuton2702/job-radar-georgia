"""Generate a consistent, versioned frontend snapshot from working JSON."""
import hashlib,json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];d=ROOT/'dist/data'
def read(n):return json.loads((d/n).read_text())
bundle={'jobs':read('jobs.json'),'platforms':read('platforms.json'),'excluded':read('excluded-platforms.json'),'projects':read('projects.json'),'update':read('update-status.json'),'config':read('search-config.json')}
bundle['version']=hashlib.sha256(json.dumps(bundle,sort_keys=True).encode()).hexdigest()[:16]
encoded=json.dumps(bundle,ensure_ascii=False,separators=(',',':'))
(d/'bundle.json').write_text(encoded)
(ROOT/'dist/data.js').write_text('window.RADAR_DATA='+encoded.replace('</','<\\/')+';')
print('Built',bundle['version'],len(bundle['jobs']),'jobs')
