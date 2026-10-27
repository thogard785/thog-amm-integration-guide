#!/usr/bin/env python3
"""Capture read-only, block-pinned ThogAMM contract fixtures. No signing or sends."""
import argparse
import gzip
import hashlib
import json
import subprocess
import time
import urllib.request
from pathlib import Path

PROXY = "0x80c74517bcc2d67ffe02d3ed886796272f647210"
POOL_ID = "ce389e78282dedac7b18ba7f775b7602d2ab3ab171bbd6711eb0239be6ef4dcc"
IMPLEMENTATION_SLOT = "0x360894a13ba1a3210667c828492db98dca3e2076cc3735a920a3ca505d382bbc"


def word(n):
    return f"{n:064x}"


class RPC:
    def __init__(self, url):
        self.url = url

    def send(self, payload):
        data = json.dumps(payload).encode()
        for attempt in range(5):
            try:
                request = urllib.request.Request(self.url, data=data, headers={"Content-Type": "application/json"})
                with urllib.request.urlopen(request, timeout=45) as response:
                    return json.load(response)
            except (OSError, TimeoutError):
                if attempt == 4:
                    raise
                time.sleep(0.5 * (attempt + 1))

    def call(self, method, params):
        response = self.send({"jsonrpc": "2.0", "id": 1, "method": method, "params": params})
        if "error" in response:
            raise RuntimeError(response["error"])
        return response["result"]

    def calls(self, data, block):
        result = []
        for start in range(0, len(data), 8):
            batch = [{"jsonrpc": "2.0", "id": i, "method": "eth_call", "params": [
                {"to": PROXY, "data": value, "gasPrice": "0x1"}, block]}
                for i, value in enumerate(data[start:start + 8])]
            for attempt in range(5):
                time.sleep(0.05 + attempt * 0.5)
                responses = self.send(batch)
                if isinstance(responses, list) and not any(r.get("error", {}).get("code") == -32007 for r in responses):
                    break
            if not isinstance(responses, list) or len(responses) != len(batch):
                raise RuntimeError(f"incomplete batch: {responses}")
            by_id = {r["id"]: r for r in responses}
            for i in range(len(batch)):
                r = by_id[i]
                if "error" in r and r["error"].get("code") != 3:
                    raise RuntimeError(r["error"])
                result.append(r)
        return result


def decode_snapshot(encoded):
    raw = bytes.fromhex(encoded[2:])
    read = lambda position: int.from_bytes(raw[position:position + 32], "big")
    base = read(0)
    fields = [read(base + 32 * i) for i in range(13)]
    if fields[0] != 8:
        raise ValueError(f"expected schema 8, got {fields[0]}")

    def array(index, width):
        offset = base + fields[index]
        return [[read(offset + 32 + (i * width + j) * 32) for j in range(width)]
                for i in range(read(offset))]

    words = dict(array(10, 2))
    tokens = [{"address": "0x" + word(t[0])[-40:], "decimals": t[1], "category": t[2]}
              for t in array(7, 15)]
    if set(words) != set(range(2, 128)) or len(tokens) != fields[4]:
        raise ValueError("incomplete snapshot")
    return fields, words, tokens


XSTOCKS = ['0x90a2a4c76b5d8c0bc892a69ea28aa775a8f2dd48', '0xa753a7395cae905cd615da0b82a53e0560f250af', '0x8d512a03600981b8e86556fd5c0fbdd726fe1821', '0x299c95eb52bfd5bc98d924bce17197b64864589b', '0xc845b2894dbddd03858fd2d643b4ef725fe0849d', '0x8ad3c73f833d3f9a523ab01476625f269aeb7cf0', '0x68fa48b1c2fe52b3d776e1953e0e782b5044ce28', '0xf6a873bae4ba1b304e45df52a4b7d176e1c6a8c4', '0x58100046a4afcd4ee4fadbd4244f3f895a341c56']

def share_balances(rpc, tokens, block):
    selector = lambda sig: subprocess.check_output([str(Path.home()/'.foundry/bin/cast'), 'sig', sig], text=True).strip()
    shares_call = selector('sharesOf(address)') + word(int(PROXY, 16))
    multiplier_call = selector('getCurrentMultiplier()')
    calls = [(t['address'], data) for t in tokens if t['address'] in XSTOCKS for data in [shares_call, multiplier_call]]
    if not calls: return {}
    responses = rpc.send([{'jsonrpc':'2.0','id':i,'method':'eth_call','params':[{'to':to,'data':data,'gasPrice':'0x1'},block]} for i,(to,data) in enumerate(calls)])
    by_id = {r['id']:r for r in responses}
    if any('error' in r for r in responses): raise RuntimeError(responses)
    result = {}
    for i in range(0, len(calls), 2):
        shares, multiplier = by_id[i]['result'], by_id[i+1]['result']
        assert len(shares) == 66 and len(multiplier) == 194
        result[calls[i][0]] = {'shares':hex(int(shares,16)), 'multiplier':hex(int(multiplier[2:66],16))}
    return result

def capture(rpc, block):
    header = rpc.call("eth_getBlockByNumber", [hex(block), False])
    selector = {"blockHash": header["hash"], "requireCanonical": True}
    encoded = rpc.call("eth_call", [{"to": PROXY, "data": "0x6a7373d6" + word(0) + word(28), "gasPrice": "0x1"}, selector])
    fields, words, tokens = decode_snapshot(encoded)
    assert fields[1] == block and fields[2] == int(header["baseFeePerGas"], 16)
    assert word(fields[3]) == header["parentHash"][2:]
    cases = []
    for i, token in enumerate(tokens):
        price = (words[20 + i // 4] >> (64 * (i % 4))) & ((1 << 64) - 1)
        lower = (price & ((1 << 56) - 1)) * 10 ** (18 - (price >> 56))
        amounts = {0, 1, 2}
        amounts.update(max(1, usd * 10**18 * 10**token["decimals"] // lower)
                       for usd in [1, 10, 100, 1000, 5000, 10000])
        for j, output in enumerate(tokens):
            if i == j:
                continue
            pair = word(int(token["address"], 16)) + word(int(output["address"], 16))
            for amount in sorted(amounts):
                cases.append({"method": "quote", "inputIndex": i, "outputIndex": j, "amount": hex(amount),
                              "calldata": "0xa42b1498" + pair + word(amount)})
            for amount in [0, max(amounts - {max(amounts)})]:
                cases.append({"method": "price", "inputIndex": i, "outputIndex": j, "amount": hex(amount),
                              "calldata": "0xaad6e488" + POOL_ID + pair + word(128) + word(1) + word(amount)})
            cases.append({"method": "limits", "inputIndex": i, "outputIndex": j, "amount": "0x0",
                          "calldata": "0xa9270fbe" + POOL_ID + pair})
    results = rpc.calls([c["calldata"] for c in cases], selector)
    for case, response in zip(cases, results):
        case["success"] = "result" in response
        if case["success"]:
            case["result"] = response["result"]
        else:
            case["error"] = response["error"]
    assert rpc.call("eth_getBlockByNumber", [hex(block), False])["hash"] == header["hash"], "reorg during capture"
    print(f"block {block}: {len(cases)} cases, {sum(c['success'] for c in cases)} successes", flush=True)
    return {"blockNumber": block, "blockHash": header["hash"], "parentHash": header["parentHash"],
            "baseFeePerGas": header["baseFeePerGas"], "timestamp": header["timestamp"], "snapshot": encoded,
            "shareBalances": share_balances(rpc, tokens, selector), "cases": cases}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--rpc", default="https://rpc.monad.xyz")
    parser.add_argument("--blocks", help="comma-separated historical block numbers; default is the previous block")
    parser.add_argument("--output", type=Path, default=Path("fixtures/deployed-v8.json.gz"))
    args = parser.parse_args()
    rpc = RPC(args.rpc)
    chain_id = int(rpc.call("eth_chainId", []), 16)
    assert chain_id == 143, "expected Monad mainnet"
    blocks = list(map(int, args.blocks.split(","))) if args.blocks else [int(rpc.call("eth_blockNumber", []), 16) - 1]
    implementation = "0x" + rpc.call("eth_getStorageAt", [PROXY, IMPLEMENTATION_SLOT, hex(blocks[-1])])[-40:]
    code = bytes.fromhex(rpc.call("eth_getCode", [implementation, hex(blocks[-1])])[2:])
    fixture = {"schemaVersion": 8, "chainId": chain_id, "proxy": PROXY, "implementation": implementation,
               "implementationCodeSha256": hashlib.sha256(code).hexdigest(),
               "snapshots": [capture(rpc, block) for block in blocks]}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    data = (json.dumps(fixture, separators=(",", ":")) + "\n").encode()
    args.output.write_bytes(gzip.compress(data, mtime=0))
    print(f"saved {args.output}: {len(data)} bytes before compression")


if __name__ == "__main__":
    main()
