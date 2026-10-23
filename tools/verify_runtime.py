#!/usr/bin/env python3
"""Verify the proxy implementation and runtime hashes without sending transactions."""
import argparse,hashlib,json,time
from pathlib import Path
from capture_quotes import RPC,PROXY,IMPLEMENTATION_SLOT
p=argparse.ArgumentParser(description=__doc__);p.add_argument('--rpc',default='https://rpc.monad.xyz');a=p.parse_args()
rpc=RPC(a.rpc);assert int(rpc.call('eth_chainId',[]),16)==143
block=rpc.call('eth_blockNumber',[])
records=json.loads((Path(__file__).resolve().parent.parent/'fixtures/deployment.json').read_text())
implementation='0x'+rpc.call('eth_getStorageAt',[PROXY,IMPLEMENTATION_SLOT,block])[-40:]
assert implementation==next(r['address'] for r in records if r['name']=='TakerExecutor'),'implementation changed'
for record in records:
 code=bytes.fromhex(rpc.call('eth_getCode',[record['address'],block])[2:])
 assert len(code)==record['runtimeBytes'] and hashlib.sha256(code).hexdigest()==record['sha256'],record['name']+' runtime changed'
 time.sleep(.1)
print(f'All {len(records)} runtime hashes match at Monad block {int(block,16)}; implementation {implementation}')
