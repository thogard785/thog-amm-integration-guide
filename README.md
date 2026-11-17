# ThogAMM integration

Integrate the **17-token ThogAMM pool on Monad**, including all nine unwrapped
xStocks. Start with the [integration guide](THOGAMM_AGGREGATOR_INTEGRATION.md)
for addresses, quoting, funding and settlement.

| Resource | Use |
| --- | --- |
| [Polling SDK 0.6.1](https://github.com/thogard785/thog-amm-poll-sdk/tree/v0.6.1) | Refresh state, then quote locally |
| [Event SDK 0.6.1](https://github.com/thogard785/thog-amm-event-sdk/tree/v0.6.1) | Maintain quotes through finalized events |
| [ABI](abi/ThogAMM.json) · [Numeric reference](REFERENCE.md) | Implement another language or transport |

Proxy: `0x80c74517BCC2D67fFE02D3ED886796272F647210`. Chain ID: **143**.
Implementation: `0xb108a1daf3c9ba52778b97a15ebdfa3f6f59b506`.
Both SDKs use `storedMultiplier(token)` on the pool; do not substitute the
issuer's multiplier. Version 0.5.0 is incompatible. Version 0.6.0 already
supports stored multipliers; 0.6.1 adds expanded-registry validation and
corrects integration and capture instructions, with unchanged quote APIs.

## Verification

Both SDKs check **61,920 contract comparisons**. Successful outputs must match
exactly; errors must match acceptance/rejection, not Solidity revert bytes.
Expected values are captured from contract calls independently of the SDK.

| Corpus | Cases | Exact successes | Matching rejections |
| --- | ---: | ---: | ---: |
| [Current 17-token mainnet state](fixtures/deployed-stored-multipliers.json.gz), 272 directed pairs | 3,264 | 2,033 | 1,231 |
| [Historical mainnet state](fixtures/deployed-v8.json.gz), 156 directed pairs | 1,872 | 954 | 918 |
| [Model-3 fork settlement](fixtures/execution-model3.json.gz), direct input and ERC-7815 Buy | 32,760 | 16,428 | 16,332 |
| [Historical fork boundaries](fixtures/boundaries-v8.json.gz), 14 policy/inventory contexts | 24,024 | 9,982 | 14,042 |
| **Total** | **61,920** | **29,397** | **32,523** |

The current capture is from block **122916130**. It reads all nine multipliers
from the pool. [Current event replay](fixtures/events-stored-multipliers.json.gz)
checks 50 consecutive blocks and 505 logs, including a perpetual exposure
update, against independently read quote state. All quote inputs, physical
shares and stored multipliers must match. Perpetual account/position words
122–127 are snapshot-only operational data, excluded from quote-state equality;
tests also compare every pair's quotes before discarding those fields.

The historical read-only and 200-block event fixtures keep their original
model-2 bytes; tests migrate only the model identifier. The model-3 settlement
fixture records a local fork with its original source hashes. These are
historical arithmetic checks, not new live executions.

Additional checks cover all nine multiplier getters and finalized updates,
log-free blocks, invalid values, reorgs and no event-SDK RPC reads after
initialization. All ten deployed [implementation/library runtime hashes](fixtures/deployment.json)
were rechecked at block **122917283**.

See [reproduction instructions](verification/README.md). The stored-multiplier
[upgrade record](fixtures/upgrade-stored-multipliers.json) is historical;
read current pool state for availability.
