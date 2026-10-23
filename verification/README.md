# Reproduce the deployed-bytecode fork checks

Use a Monad-enabled Foundry build supporting `--network monad`. The checked
capture used Foundry 1.7.1-monad, Solidity 0.8.28, and the forge-std revision below.
Run from this repository's root:

```sh
cd verification
forge install foundry-rs/forge-std@c0f966cb111f621bfb283b2a388bc7be18953bba
cd ..
MONAD_RPC=https://rpc.monad.xyz forge test --root verification --network monad -vv
python3 tools/pack_execution.py
python3 tools/pack_boundaries.py
python3 -c 'import gzip,pathlib; p=pathlib.Path("fixtures/events-fork-v7.bin"); p.with_suffix(".bin.gz").write_bytes(gzip.compress(p.read_bytes(),mtime=0))'
```

These are local fork tests. They use the actual proxy, implementation, linked
libraries and token code at block **115786825**. They do not redeploy the pricing
code, sign transactions or broadcast anything to mainnet. Only the test caller's
funds and approvals are supplied for execution. Boundary cases additionally
change local fork policy words, and publication cases call the deployed owner
setters with a local impersonation. No mainnet state changes.

Do **not** add `--isolate`: transaction isolation resets the gas-price/account-
warmth context being tested. Each execution case instead snapshots and reverts
fork state, explicitly sets effective gas price and the AuctionHandler's warmth,
and invokes the deployed settlement function. The cold threshold, threshold+1
and warm-account cases match the local models exactly.

`execution-v7.json.gz` contains 1,680 direct exact-input and ERC-7815 Buy calls,
including zero amounts, tiny raw values, all 56 directed pairs, both successful
settlement and contract reverts. Exact-output results are the returned required
input; token output is exactly the specified target. The measured gas in this
fixture reflects the test harness's shared access context and is not a promise
of cold transaction gas.

`boundaries-v7.json.gz` contains 5,544 calls in nine policy/block contexts:
original state, zero lambda, fixed wrappers, stronger sliding output refund,
nonpositive wrapper value, tight receiving-token cap, zero category cap,
maximum valid price age and the first stale block. Every expected result is
returned by deployed bytecode; none is calculated with the SDK being tested.

`events-fork-v7.bin.gz` is ABI encoding of `EventSet[]` where:

```solidity
struct Log { bytes32[] topics; bytes data; address emitter; }
struct EventSet { bytes beforeState; bytes afterState; Log[] logs; }
```

It proves independent risk/wrapper readiness, category-anchor changes,
preservation of spare storage bits, and cap publications with duplicate entries,
zero caps, infinity and downward rounding. Each state byte string is a complete
ABI `getPoolData(0,32)` result.

## Cold-call gas measurements

Use Foundry 1.8.6 or later with Monad page-storage pricing:

```sh
forge test --network monad --isolate --match-test test_captureGas
```

This writes `fixtures/gas-v7.jsonl`. The compressed `fixtures/gas-v7.json.gz`
records the deployed addresses, block, tool version and measured call costs.
`--isolate` is for this gas benchmark; keep the execution-context parity capture
non-isolated as described above. These pool-call measurements do not replace
estimating the actual router transaction.
