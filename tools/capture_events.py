#!/usr/bin/env python3
"""Capture historical headers, logs and complete snapshots for independent replay checks."""
import argparse, gzip, json, subprocess, time
from pathlib import Path
from capture_quotes import RPC, PROXY, word


def signature(value):
    return subprocess.check_output([str(Path.home()/'.foundry/bin/cast'), 'keccak', value], text=True).strip()


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--rpc',default='https://rpc.monad.xyz')
    p.add_argument('--start',type=int,default=115786825)
    p.add_argument('--stop',type=int,default=115787025)
    p.add_argument('--output',type=Path,required=True,help='new output file; existing files are never overwritten')
    a=p.parse_args()
    if a.output.exists(): p.error('output already exists; choose a new capture path')
    rpc=RPC(a.rpc)
    owner='0x'+word(int(PROXY,16))
    transfer=signature('Transfer(address,address,uint256)')
    filters=[{'address':PROXY},{'topics':[transfer,owner]},{'topics':[transfer,None,owner]},
        {'address':'0x3bd359c1119da7da1d913d1c4d2b7c461115433a','topics':[[signature('Deposit(address,uint256)'),signature('Withdrawal(address,uint256)')],owner]}]
    logs={}
    for start in range(a.start+1,a.stop+1,100):
        for f in filters:
            for log in rpc.call('eth_getLogs',[dict(f,fromBlock=hex(start),toBlock=hex(min(a.stop,start+99)))]):
                logs[(log['blockHash'],log['logIndex'])]=log
            time.sleep(.1)
    calls=[]
    for n in range(a.start,a.stop+1):
        calls.extend([('eth_getBlockByNumber',[hex(n),False]),('eth_call',[{'to':PROXY,'data':'0x6a7373d6'+word(0)+word(32),'gasPrice':'0x1'},hex(n)])])
    result=[]
    for start in range(0,len(calls),8):
        time.sleep(.3)
        batch=[{'jsonrpc':'2.0','id':i,'method':m,'params':p} for i,(m,p) in enumerate(calls[start:start+8])]
        responses=rpc.send(batch); by_id={r['id']:r for r in responses}
        for i in range(len(batch)):
            if 'error' in by_id[i]: raise RuntimeError(by_id[i]['error'])
            result.append(by_id[i]['result'])
    blocks=[]
    for j,n in enumerate(range(a.start,a.stop+1)):
        h=result[2*j]
        blocklogs=sorted([l for l in logs.values() if l['blockHash']==h['hash']],key=lambda l:(int(l['transactionIndex'],16),int(l['logIndex'],16)))
        blocks.append({'header':{k:h[k] for k in ['number','hash','parentHash','baseFeePerGas','timestamp']},'snapshot':result[2*j+1],'logs':blocklogs})
    assert rpc.call('eth_getBlockByNumber',[hex(a.stop),False])['hash']==blocks[-1]['header']['hash']
    a.output.parent.mkdir(parents=True,exist_ok=True)
    with a.output.open('xb') as output:
        output.write(gzip.compress((json.dumps({'proxy':PROXY,'rpc':a.rpc,'blocks':blocks},separators=(',',':'))+'\n').encode(),mtime=0))
    print(f'saved {len(blocks)-1} replay blocks, {len(logs)} logs: {a.output}',flush=True)

if __name__=='__main__': main()
