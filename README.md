# ThogAMM integration

Integrate the **13-token ThogAMM pool on Monad**, including SPYx, QQQx, EWYx,
NVDAx and TSLAx. Start with the [integration guide](THOGAMM_AGGREGATOR_INTEGRATION.md)
for addresses, quoting and settlement. Routers that pull input first should use
the [funding example](THOGAMM_AGGREGATOR_INTEGRATION.md#funding-through-an-aggregator);
execution output is a guarantee, so compare `received >= amount_out`.

| Resource | Use |
| --- | --- |
| [Polling SDK 0.5.0 (pending)](https://github.com/thogard785/thog-amm-poll-sdk) | Refresh complete state, then quote locally |
| [Event SDK 0.5.0 (pending)](https://github.com/thogard785/thog-amm-event-sdk) | Replay pool/share events and refresh issuer multipliers |
| [ABI](abi/ThogAMM.json) · [Numeric reference](REFERENCE.md) | Implement another language or transport |

Proxy: `0x80c74517BCC2D67fFE02D3ED886796272F647210`. Chain ID: **143**.
Pending state format: **schema 8 / wire 8 / model 3**, capacity 28 tokens.
Read `getPoolData(0, 28)` and the listed xStocks’ share/multiplier state at one
block hash. SDK **0.5.0** targets the pending contract upgrade; SDK 0.4.1 remains for model 2.
Verify the model identity at the selected block before choosing an SDK.
This PR does not deploy the contract or publish a v0.5.0 tag.

## Verification

Both Rust SDKs check **58,656 contract comparisons** with exact integer results.
Expected values come from contract calls, independently of the SDK.

| Corpus | Cases | Exact successes | Matching rejections |
| --- | ---: | ---: | ---: |
| [Historical mainnet reads](fixtures/deployed-v8.json.gz), all 156 directed pairs | 1,872 | 954 | 918 |
| [Model-3 fork settlement](fixtures/execution-model3.json.gz), direct input and ERC-7815 Buy | 32,760 | 16,428 | 16,332 |
| [Historical fork boundaries](fixtures/boundaries-v8.json.gz), 14 policy/inventory contexts | 24,024 | 9,982 | 14,042 |
| **Total** | **58,656** | **27,364** | **31,292** |

The model-3 corpus locally upgrades the historical proxy to the newly compiled
implementation, publishes valuations through the actual writer, and tests both
that block and the following block. It spans all 156 directions, three issuer
multiplier states, every strict gas threshold and threshold+1, and explicit
AuctionHandler warmth. Captures record source hashes and raw contract results;
this is fork evidence for pending code, not a claim of a mainnet deployment.

Historical read-only and event fixtures retain their original model-2 bytes.
Tests explicitly migrate only their model identity to exercise unchanged
read-only/event semantics. The old [model-2 execution corpus](fixtures/execution-v8.json.gz)
is preserved as historical evidence and is not used to validate model-3 defense.

[Event replay](fixtures/events-v8.json.gz) matches 200 consecutive mainnet
snapshots and 220 logs, including all words, metadata, physical shares, balances,
issuer multipliers and native MON. [Publication fixtures](fixtures/events-fork-v8.bin.gz)
cover readiness, anchor changes, spare bits and caps.
[Historical runtime evidence](fixtures/deployment.json) records the model-2
implementation and eight linked libraries. It does not describe the pending upgrade.

See [verification instructions](verification/README.md) to reproduce the captures.
All fork tests are local. Error parity means matching acceptance/rejection;
SDK errors do not reproduce Solidity revert bytes.
