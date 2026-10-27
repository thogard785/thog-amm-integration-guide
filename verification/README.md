# Reproduce schema-8 verification

The fixtures use the deployed ThogAMM proxy, token code and linked libraries at
Monad block **117074438**. Expected results are contract return bytes; the SDK
never generates its own expected values.

## Read-only mainnet captures

```sh
python3 tools/verify_runtime.py --rpc https://rpc.monad.xyz
python3 tools/capture_quotes.py --rpc https://rpc.monad.xyz --blocks 117074438
python3 tools/capture_events.py --rpc https://rpc.monad.xyz --start 117074438 --stop 117074638
```

Historical capture requires an archive-capable endpoint. Pool and issuer reads
use EIP-1898 block hashes. The runtime verifier checks the proxy implementation
and SHA-256 hashes in [deployment.json](../fixtures/deployment.json).

## Local fork captures

Use a Monad-enabled Foundry build supporting `--network monad`, Solidity 0.8.28
and forge-std revision `c0f966cb111f621bfb283b2a388bc7be18953bba`:

```sh
cd verification
forge install foundry-rs/forge-std@c0f966cb111f621bfb283b2a388bc7be18953bba
cd ..
MONAD_RPC=https://rpc.monad.xyz forge test --root verification --network monad -vv
python3 tools/pack_execution.py
python3 tools/pack_boundaries.py
python3 -c 'import gzip,pathlib; p=pathlib.Path("fixtures/events-fork-v8.bin"); p.with_suffix(".bin.gz").write_bytes(gzip.compress(p.read_bytes(),mtime=0))'
```

Tests supply only local caller funds/allowances, impersonate the owner for
publication checks, and change local policy/issuer state for boundary checks.
They do not sign or broadcast transactions. Do not add `--isolate`: it resets
the gas-price/account-warmth context under test. Each case snapshots and restores
fork state; measured harness gas is not a cold-transaction gas estimate.

| Fixture | Coverage |
| --- | --- |
| `deployed-v8.json.gz` | 1,872 read-only calls across all 156 directed pairs |
| `execution-v8.json.gz` | 14,040 direct-input / ERC-7815 Buy calls; live, 1.234567890123456789 and 3.100000000000000001 stock multipliers; cold threshold, threshold+1 and warm AuctionHandler |
| `boundaries-v8.json.gz` | 24,024 calls: baseline, zero lambda, fixed/refund wrappers, invalid wrapper domain, token/category caps, age limits, two non-unit multipliers, empty stocks, physical donations and the valid inventory value `1 << 255` |
| `events-v8.json.gz` | 200 consecutive blocks, 220 logs, plus issuer state at every block |
| `events-fork-v8.bin.gz` | Risk/wrapper readiness, anchor changes, spare bits and cap publications |

The binary publication fixture is ABI encoding of:

```solidity
struct Log { bytes32[] topics; bytes data; address emitter; }
struct EventSet { bytes beforeState; bytes afterState; Log[] logs; }
```

Each state is a complete ABI `getPoolData(0, 28)` return. Publication cases retain
the mainnet seed's physical shares and multipliers. JSON snapshots carry explicit
`shareBalances` for their own state, including modified fork multipliers.
Run `cargo test --workspace --locked` in the polling SDK or `cargo test --locked`
in the event SDK for offline comparisons. See the [result counts](../README.md#verification).
