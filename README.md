# ThogAMM integration guide

Integrate ThogAMM on Monad using the [complete integration guide](THOGAMM_AGGREGATOR_INTEGRATION.md).
It includes the deployed schema-7 snapshot ABI, exact local quote math, volume charges,
wrapper refunds, inventory caps, event replay and settlement rules.

| Integration | Repository |
| --- | --- |
| One state read per refresh, then local quotes | [Polling Rust SDK](https://github.com/thogard785/thog-amm-poll-sdk), version **0.3.0** |
| Snapshot bootstrap followed by event updates | [Event Rust SDK](https://github.com/thogard785/thog-amm-event-sdk), version **0.3.0** |
| Implement your own model | [This guide](THOGAMM_AGGREGATOR_INTEGRATION.md) and [ABI](abi/ThogAMM.json) |

The proxy is `0x80c74517BCC2D67fFE02D3ED886796272F647210`, on chain ID **143**.
The deployed state format is **schema 7 / wire 7 / model 1**, with up to 32 tokens.
Read `getPoolData(0,32)`. The retired `makerSnapshot()` and schema-6 SDK releases are incompatible.

## Verification

The in-memory specification was checked against the deployed implementation and
all seven linked libraries, whose runtime bytes match the compiled source.
[Deployment evidence](fixtures/deployment.json) records their addresses and SHA-256 hashes.
The independent Rust and Go implementations pass the same **9,240 comparisons**:

| Corpus | Cases | Exact successful results | Matching rejections |
| --- | ---: | ---: | ---: |
| [Mainnet queries](fixtures/deployed-v7.json.gz): three historical blocks, all directed pairs, exact input, marginal price and limits | 2,016 | 1,308 | 708 |
| [Monad-fork execution](fixtures/execution-v7.json.gz): exact input/output and explicit gas-price/warmth context | 1,680 | 1,261 | 419 |
| [Fork boundary states](fixtures/boundaries-v7.json.gz): volume, wrappers, caps and price age | 5,544 | 2,793 | 2,751 |
| **Total per implementation** | **9,240** | **5,362** | **3,878** |

The mainnet corpus is pinned to blocks **115786825, 115786925 and 115787025**.
It includes 879 successful exact-input cases charging volume cost and 222 with
a net wrapper refund. Results are raw contract return bytes, not values generated
by either local model. Error comparisons establish rejection parity; SDK error
objects do not reproduce Solidity revert encodings.

[Event fixtures](fixtures/events-v7.json.gz) contain 200 consecutive mainnet
blocks and 204 relevant logs. Replayed state matches every fresh snapshot:
all 126 words, token metadata, token balances and native MON. Additional
[publication fixtures](fixtures/events-fork-v7.bin.gz) test independent readiness,
anchor changes, spare-bit preservation and exact cap encoding.
[Additional mainnet fixtures](fixtures/events-lending-pause-v7.json.gz) cover
a lending exposure update at block 115772315 and pause/unpause at blocks
115730334 and 115731694. Each one-block replay equals a fresh snapshot.

Reproduce the mainnet reads without sending transactions:

```sh
python3 tools/verify_runtime.py --rpc https://rpc.monad.xyz
python3 tools/capture_quotes.py --rpc https://rpc.monad.xyz --blocks 115786825,115786925,115787025 --output /tmp/thogamm-quotes.json.gz
python3 tools/capture_events.py --rpc https://rpc.monad.xyz --output /tmp/thogamm-events.json.gz
```

See [fork verification instructions](verification/README.md) to reproduce the
settlement and boundary captures. The Rust SDKs and Kyber adapter include copies
of the same compressed quote fixtures and run their comparisons offline.

## Release references

- [Polling SDK v0.3.0](https://github.com/thogard785/thog-amm-poll-sdk/releases/tag/v0.3.0), commit `11635f1df026c1e0ec9dde821546f0fe4729b8bf`.
- [Event SDK v0.3.0](https://github.com/thogard785/thog-amm-event-sdk/releases/tag/v0.3.0), commit `3ae66cce1cd162ca033b478625dd3284699ef8e2`.
- [Kyber adapter PR #1844](https://github.com/KyberNetwork/kyberswap-dex-lib/pull/1844), tested commit `f7c433d656eedd714bca0d73ec9ba7f09f8b1cf6`. Closed while the adapter is reviewed; there is no active upstream submission.

## Versioning and execution context

SDKs and adapters must understand the snapshot's layout, wire and model identifiers.
An implementation upgrade, changed registry generation, missing events or a reorg
requires appropriate state recovery. A matching ABI alone does not establish pricing
compatibility. The guide distinguishes read-only quotes, execution widening and
post-transfer cap checks. Exactness refers to the same complete state, block and
execution context; a later inclusion block can have different prices or inventory.
