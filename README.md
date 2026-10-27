# ThogAMM integration

Integrate the **13-token ThogAMM pool on Monad**, including SPYx, QQQx, EWYx,
NVDAx and TSLAx. Start with the [integration guide](THOGAMM_AGGREGATOR_INTEGRATION.md)
for addresses, quoting and settlement. Routers that pull input first should use
the [funding example](THOGAMM_AGGREGATOR_INTEGRATION.md#funding-through-an-aggregator);
execution output is a guarantee, so compare `received >= amount_out`.

| Resource | Use |
| --- | --- |
| [Polling SDK v0.4.1](https://github.com/thogard785/thog-amm-poll-sdk) | Refresh complete state, then quote locally |
| [Event SDK v0.4.1](https://github.com/thogard785/thog-amm-event-sdk) | Replay pool/share events and refresh issuer multipliers |
| [ABI](abi/ThogAMM.json) · [Numeric reference](REFERENCE.md) | Implement another language or transport |

Proxy: `0x80c74517BCC2D67fFE02D3ED886796272F647210`. Chain ID: **143**.
State format: **schema 8 / wire 8 / model 2**, capacity 28 tokens.
Read `getPoolData(0, 28)` and the listed xStocks’ share/multiplier state at one
block hash. SDK **0.4.1** replaces the incompatible schema-7 release.

## Verification

Both Rust SDKs pass **39,936 contract comparisons** with exact integer results.
Expected values come from contract calls, independently of the SDK.

| Corpus | Cases | Exact successes | Matching rejections |
| --- | ---: | ---: | ---: |
| [Mainnet reads](fixtures/deployed-v8.json.gz), all 156 directed pairs | 1,872 | 954 | 918 |
| [Fork settlement](fixtures/execution-v8.json.gz), direct input and ERC-7815 Buy, three multiplier states and three friction contexts | 14,040 | 7,954 | 6,086 |
| [Fork boundaries](fixtures/boundaries-v8.json.gz), 14 policy/inventory contexts | 24,024 | 9,982 | 14,042 |
| **Total** | **39,936** | **18,890** | **21,046** |

[Event replay](fixtures/events-v8.json.gz) matches 200 consecutive mainnet
snapshots and 220 logs, including all words, metadata, physical shares, balances,
issuer multipliers and native MON. [Publication fixtures](fixtures/events-fork-v8.bin.gz)
cover readiness, anchor changes, spare bits and caps.
[Runtime evidence](fixtures/deployment.json) records the implementation and eight
linked libraries, checked byte-for-byte against compiled artifacts.

See [verification instructions](verification/README.md) to reproduce the captures.
All fork tests are local. Error parity means matching acceptance/rejection;
SDK errors do not reproduce Solidity revert bytes.
