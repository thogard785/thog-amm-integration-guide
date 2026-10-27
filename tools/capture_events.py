#!/usr/bin/env python3
"""Capture hash-pinned issuer/pool snapshots and logs for independent replay checks."""
import argparse
from concurrent.futures import ThreadPoolExecutor
import gzip
import json
import subprocess
from pathlib import Path
from capture_quotes import RPC, PROXY, word, decode_snapshot, share_balances


def signature(value):
    return subprocess.check_output([str(Path.home()/'.foundry/bin/cast'), 'keccak', value], text=True).strip()


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--rpc', default='https://rpc.monad.xyz')
    p.add_argument('--start', type=int, required=True)
    p.add_argument('--stop', type=int, required=True)
    p.add_argument('--output', type=Path, default=Path('fixtures/events-v8.json.gz'))
    a = p.parse_args()
    rpc = RPC(a.rpc)
    owner = '0x'+word(int(PROXY, 16))
    transfers = [signature('Transfer(address,address,uint256)'), signature('TransferShares(address,address,uint256)')]
    filters = [{'address':PROXY}, {'topics':[transfers,owner]}, {'topics':[transfers,None,owner]},
        {'address':'0x3bd359c1119da7da1d913d1c4d2b7c461115433a',
         'topics':[[signature('Deposit(address,uint256)'),signature('Withdrawal(address,uint256)')],owner]}]
    logs = {}
    for start in range(a.start+1, a.stop+1, 100):
        for f in filters:
            for log in rpc.call('eth_getLogs', [dict(f, fromBlock=hex(start), toBlock=hex(min(a.stop,start+99)))]):
                logs[(log['blockHash'],log['logIndex'])] = log

    def capture(n):
        h = rpc.call('eth_getBlockByNumber', [hex(n),False])
        selector = {'blockHash':h['hash'], 'requireCanonical':True}
        encoded = rpc.call('eth_call', [{'to':PROXY,'data':'0x6a7373d6'+word(0)+word(28),'gasPrice':'0x1'},selector])
        fields, _, tokens = decode_snapshot(encoded)
        assert fields[1] == n and fields[2] == int(h['baseFeePerGas'],16)
        assert word(fields[3]) == h['parentHash'][2:]
        blocklogs = sorted([l for l in logs.values() if l['blockHash']==h['hash']], key=lambda l:(int(l['transactionIndex'],16),int(l['logIndex'],16)))
        return {'header':{k:h[k] for k in ['number','hash','parentHash','baseFeePerGas']},
                'snapshot':encoded, 'shareBalances':share_balances(rpc,tokens,selector), 'logs':blocklogs}

    with ThreadPoolExecutor(max_workers=4) as workers:
        blocks = list(workers.map(capture, range(a.start,a.stop+1)))
    assert all(b['header']['parentHash'] == a['header']['hash'] for a,b in zip(blocks,blocks[1:]))
    a.output.write_bytes(gzip.compress((json.dumps({'schemaVersion':8,'proxy':PROXY,'blocks':blocks},separators=(',',':'))+'\n').encode(),mtime=0))
    print(f'saved {len(blocks)-1} replay blocks, {len(logs)} logs: {a.output}',flush=True)

if __name__ == '__main__':
    main()
