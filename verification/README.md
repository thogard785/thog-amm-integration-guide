# Verify a ThogAMM model

A model is correct when it gives the contract's result for the same state, the
same amount and the same transaction: equal integers where the contract
succeeds, and a rejection wherever the contract reverts. Do not allow a
tolerance.

This directory and [`fixtures/`](../fixtures) hold contract results recorded
for that comparison. The expected values come from EVM calls, not from any
model.

## Recorded contract results

| Fixture | What it holds | Calls | Succeeded | Reverted |
| --- | --- | ---: | ---: | ---: |
| [deployed-stored-multipliers](../fixtures/deployed-stored-multipliers.json.gz) | The deployed 17-token pool at block 122,916,130: every one of the 272 token pairs | 3,264 | 2,033 | 1,231 |
| [deployed-v8](../fixtures/deployed-v8.json.gz) | The deployed pool when it listed 13 tokens: all 156 pairs | 1,872 | 954 | 918 |
| [boundaries-v8](../fixtures/boundaries-v8.json.gz) | 14 pool configurations on a fork, chosen to reach the edges of the pricing and cap arithmetic | 24,024 | 9,982 | 14,042 |
| [execution-model3](../fixtures/execution-model3.json.gz) | Swaps on a fork: `makerSwapExactInput` and ERC-7815 buys at every surcharge tier | 32,760 | 16,428 | 16,332 |
| **Total** | | **61,920** | **29,397** | **32,523** |

Each fixture is gzipped JSON:

```text
proxy                    the pool address
snapshots[]
  snapshot               return data of getPoolData(0, 28)
  shareBalances          for each xStock: { shares, multiplier }
  cases[]
    method               quote | price | limits | execution | exactOutput
    inputIndex, outputIndex, amount
    gasPrice, auctionHandlerWarm        (execution and exactOutput only)
    success              whether the contract call succeeded
    result               its return data, when it did
```

| `method` | Contract call |
| --- | --- |
| `quote` | `makerQuoteExactInput(tokenIn, tokenOut, amount)` |
| `price` | ERC-7815 `price(poolId, tokenIn, tokenOut, [amount])` |
| `limits` | ERC-7815 `getLimits(poolId, tokenIn, tokenOut)` |
| `execution` | `makerSwapExactInput` with `amount` in; the first word of `result` is `amountOut` |
| `exactOutput` | ERC-7815 `swap`, buy side, for `amount` out; the first word of `result` is the input |

Evaluate each case at the snapshot's own block and base fee. The `deployed-v8`,
`boundaries-v8` and `events-v8` snapshots carry the pricing-model identifier 2
in slot 8. Identifier 3 changed only the execution surcharge, which none of
their cases involve, so set the identifier to 3 before decoding them.

## Recorded blocks

| Fixture | What it holds |
| --- | --- |
| [events-stored-multipliers](../fixtures/events-stored-multipliers.json.gz) | 51 consecutive blocks of the 17-token pool with 505 logs |
| [events-v8](../fixtures/events-v8.json.gz) | 201 consecutive blocks of the 13-token pool with 220 logs |

Each block has its `header`, the `logs` matching the
[reference's filters](../REFERENCE.md#keeping-state-current-from-events), and
the `snapshot` and `shareBalances` read from the chain at that block. Start
from the first block's snapshot, apply each later block's logs, and compare
with that block's snapshot: balances, native balance, xStock shares and
multipliers, and storage words 2 to 121. Words 122 to 127 are not pricing
inputs and no event carries them.

## Run the SDK against them

Both SDKs include these fixtures and run offline:

```sh
# in the polling SDK
cargo test --workspace --release

# in the event SDK
cargo test --release
```

[`contract_parity.rs`](https://github.com/thogard785/thog-amm-poll-sdk/blob/main/model/tests/contract_parity.rs)
is a short, complete example of loading a fixture and asserting on it.

## Compare with the deployed pool

Fixtures show that a model was right when they were recorded. The polling
SDK's live tests compare against the pool as it is now, at one block:

```sh
MONAD_RPC=https://rpc.monad.xyz cargo test --release -p thogamm --test live -- --ignored --nocapture
```

They show how to do the same for another model:

- **Quotes.** Read a snapshot, then call the contract for every pair at that
  snapshot's block number, batched through Multicall3.
- **Swaps.** Simulate `makerSwapExactInput` and `swapWithExtraFees` with
  `eth_call` and a state override that gives the simulated caller a balance, an
  allowance and gas money, and gives the fee recipient code that accepts every
  call. Vary the gas price to reach each surcharge tier.

## Record your own

```sh
python3 tools/verify_runtime.py --rpc "$MONAD_RPC"
python3 tools/capture_quotes.py --rpc "$MONAD_RPC" --blocks <block> --output quotes.json.gz
python3 tools/capture_events.py --rpc "$MONAD_RPC" --start <block> --stop <block> --output events.json.gz
```

`verify_runtime.py` compares the code deployed behind the proxy, and its
linked libraries, with the hashes in
[deployment.json](../fixtures/deployment.json). The capture tools make
read-only calls and need an endpoint that still serves the blocks you name.
