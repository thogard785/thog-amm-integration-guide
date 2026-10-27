#!/usr/bin/env python3
import gzip,json
from pathlib import Path
root=Path(__file__).resolve().parent.parent
def issuer_state(s):
 s['shareBalances']={a.lower():{'shares':hex(int(b)), 'multiplier':hex(int(m))} for a,b,m in zip(s.pop('shareTokens'),s.pop('shares'),s.pop('multipliers'))}

worlds=[]
for line in (root/'fixtures/boundaries-v8.jsonl').read_text().splitlines():
 r=json.loads(line)
 if 'snapshot' in r:
  issuer_state(r);r['cases']=[];worlds.append(r)
 else:worlds[r['world']]['cases'].append(r)
f={'schemaVersion':8,'chainId':143,'proxy':'0x80c74517bcc2d67ffe02d3ed886796272f647210','fork':True,'network':'monad','snapshots':worlds}
(root/'fixtures/boundaries-v8.json.gz').write_bytes(gzip.compress((json.dumps(f,separators=(',',':'))+'\n').encode(),mtime=0))
print(sum(len(w['cases']) for w in worlds),'cases;',sum(c['success'] for w in worlds for c in w['cases']),'successes')
