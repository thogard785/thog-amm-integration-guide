#!/usr/bin/env python3
"""Pack local Monad-fork execution captures. No live transaction sends."""
import gzip, json
from pathlib import Path
root=Path(__file__).resolve().parent.parent
worlds=[]
for line in (root/'fixtures/execution-v8.jsonl').read_text().splitlines():
    r=json.loads(line)
    if 'snapshot' in r:
        r['shareBalances']={a.lower():{'shares':hex(int(b)), 'multiplier':hex(int(m))} for a,b,m in zip(r.pop('shareTokens'),r.pop('shares'),r.pop('multipliers'))}
        r['cases']=[];r['blockNumber']=117074438;worlds.append(r)
    else:
        worlds[-1]['cases'].append(r)
f={'schemaVersion':8,'chainId':143,'proxy':'0x80c74517bcc2d67ffe02d3ed886796272f647210','fork':True,'network':'monad','snapshots':worlds}
(root/'fixtures/execution-v8.json.gz').write_bytes(gzip.compress((json.dumps(f,separators=(',',':'))+'\n').encode(),mtime=0))
print(sum(len(w['cases']) for w in worlds),'execution cases;',sum(c['success'] for w in worlds for c in w['cases']),'successes')
