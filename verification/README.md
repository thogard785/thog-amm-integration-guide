# Verify a ThogAMM integration

Compare the adapter with contract calls using the same state, input amount, and
transaction context. Successful outputs must match exactly; rejected requests
must agree on acceptance or rejection. Solidity revert bytes and SDK error types
need not be identical. Expected values in the supplied fixtures come from EVM
calls independently of the SDK's arithmetic.

## Run the SDK comparisons

Check out tag `v0.6.1` of the
[polling SDK](https://github.com/thogard785/thog-amm-poll-sdk/tree/v0.6.1) or
[event SDK](https://github.com/thogard785/thog-amm-event-sdk/tree/v0.6.1).
The fixtures are included in each repository. These tests run offline:

```sh
# From the polling SDK directory:
cargo test --locked --release --workspace --all-targets

# From the event SDK directory:
cargo test --locked --release --all-targets
```

Both SDKs check the following 61,920 contract observations:

| Fixture | Cases | Exact successes | Matching rejections |
| --- | ---: | ---: | ---: |
| [17-token deployment](../fixtures/deployed-stored-multipliers.json.gz), all 272 directed pairs | 3,264 | 2,033 | 1,231 |
| [13-token read-only snapshot](../fixtures/deployed-v8.json.gz), all 156 directed pairs | 1,872 | 954 | 918 |
| [Fork settlement cases](../fixtures/execution-model3.json.gz), exact input and ERC-7815 Buy | 32,760 | 16,428 | 16,332 |
| [Fork boundary cases](../fixtures/boundaries-v8.json.gz), 14 pricing/inventory configurations | 24,024 | 9,982 | 14,042 |
| **Total** | **61,920** | **29,397** | **32,523** |

The 17-token fixture was captured from implementation
`0xb108a1daf3c9ba52778b97a15ebdfa3f6f59b506` at block **122916130**.
Its 3,264 cases include 2,033 exact successes and 1,231 matching rejections.
The other files exercise arithmetic and settlement under their recorded
contract and registry configurations. Each fixture identifies its capture
state and source; the SDK test code defines how that fixture is loaded.
They do not establish present liquidity or trade availability.

Additional tests exercise snapshot decoding, all nine xStock multiplier reads,
share rounding, finalized-event replay, registry changes, reorg handling, and
invalid inputs. The event SDK also checks that updates perform no RPC reads
after the initial snapshot.

## Compare a custom model

Start with `deployed-stored-multipliers.json.gz`. It contains a complete
ABI-encoded pool snapshot, its block context, xStock share balances and
multipliers, and cases with raw request arguments and contract return bytes.

1. Decode the snapshot and build the model at the recorded block.
2. Use each case's method, token indices, input amount, and execution context.
3. Compare successful return values exactly. Do not introduce a rounding
   tolerance. Compare whether failures reject the same request.
4. For execution cases, reproduce the effective gas price, base fee,
   AuctionHandler warmth, and price publication block.

The [integer reference](../REFERENCE.md) defines the operations and rounding.
The SDK's [contract comparison tests](https://github.com/thogard785/thog-amm-poll-sdk/blob/v0.6.1/model/tests/contract_parity.rs)
show fixture decoding and assertions. Run the other regression datasets through
the SDK test harness, which supplies their fixture-specific setup.

## Reproduce the 17-token capture

Use an archive-capable Monad RPC endpoint that serves the recorded blocks. From
the integration-guide repository:

```sh
python3 tools/verify_runtime.py --rpc "$MONAD_RPC"
python3 tools/capture_quotes.py --rpc "$MONAD_RPC" \
  --blocks 122916130 --output /tmp/thog-quotes.json.gz
python3 tools/capture_events.py --rpc "$MONAD_RPC" \
  --start 122916204 --stop 122916254 --output /tmp/thog-events.json.gz
```

The runtime verifier compares deployed implementation and linked-library code
with [deployment.json](../fixtures/deployment.json). All ten runtime hashes
matched at block **122917283**; running it performs another comparison against
the endpoint's current state.

The capture tools pin reads to a canonical block hash. They read
`getPoolData(0, 28)`, each listed stock's `sharesOf(proxy)`, and the pool's
`storedMultiplier(token)` in that state. Capture scripts make read-only RPC
calls and broadcast no transactions.

## Verify event replay

The [event fixture](../fixtures/events-stored-multipliers.json.gz) contains
50 consecutive blocks and 505 logs. Replay each complete block from the starting
snapshot and compare the result with the independently captured snapshot for
that block. Include blocks with no relevant logs so price age advances.

Compare all quote inputs, physical shares, and stored multipliers. The fixture
includes a perpetual-position exposure update, carried by
`MakerLendingExposureUpdated`. The event model tracks the exposure used by
pricing. Storage words 122–127 describe perpetual-account operations and are
snapshot-only data, so tests exclude those fields from state equality **after**
checking every pair's quotes against the independent snapshot.

For router settlement tests, separately check funding received by the router,
allowances, caller/recipient selection, extra fees, minimum output, deadline,
and final recipient credit. xStock assertions use `received >= amountOut` for
execution guarantees. Simulate routes with repeated visits to ThogAMM as one
transaction; independently simulated visits do not share state.
