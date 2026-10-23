#!/usr/bin/env python3
"""Pack the local Monad-fork capture; no network or live transaction sends."""
import gzip,json
from pathlib import Path
root=Path(__file__).resolve().parent.parent
rows=[json.loads(l) for l in (root/'fixtures/execution-v7.jsonl').read_text().splitlines()]
s=rows[0];s['cases']=rows[1:];s['blockNumber']=115786825
f={'schemaVersion':7,'chainId':143,'proxy':'0x80c74517bcc2d67ffe02d3ed886796272f647210','fork':True,'network':'monad','snapshots':[s]}
(root/'fixtures/execution-v7.json.gz').write_bytes(gzip.compress((json.dumps(f,separators=(',',':'))+'\n').encode(),mtime=0))
print(f"{len(rows)-1} execution cases; {sum(c['success'] for c in rows[1:])} successful")
