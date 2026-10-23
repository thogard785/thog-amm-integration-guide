# ThogAMM Aggregator Integration

ThogAMM is an inventory-funded exact-input and exact-output liquidity source on
[Monad Mainnet](https://docs.monad.xyz/developer-essentials/network-information).
It implements the pinned Draft-status
[ERC-7815 Swap Order Routing Interface](https://github.com/ethereum/ERCs/blob/70e96af4539a39ed2bf564ec3559fb45159ff223/ERCS/erc-7815.md)
plus slippage-protected settlement extensions.

Use `makerQuoteExactInput()` and `makerSwapExactInput()` for the shortest
exact-input integration. The routing surface supports discovery, limits, marginal prices, and exact-output
simulation. This guide describes the **deployed schema-7, wire-7, model-1**
implementation on Monad. Its runtime and linked libraries were checked against
the source used for this specification; see [deployment evidence](fixtures/deployment.json).
Always verify the schema and model identifiers of each snapshot.

The maintained integration options are the [polling Rust SDK](https://github.com/thogard785/thog-amm-poll-sdk)
and [event Rust SDK](https://github.com/thogard785/thog-amm-event-sdk). Both use the
same exact integer model. An independent implementation must follow the complete
state, arithmetic and event rules below; preserving only swap selectors does
not preserve an offchain pricing model.

## Deployment

| Field | Value |
|---|---|
| Network | Monad Mainnet |
| Chain ID | `143` |
| Verified implementation | `0x709ba37580a7faf034522163353bd1547d2fb0ba` (upgradeable; integrate the proxy) |
| Proxy | `0x80c74517BCC2D67fFE02D3ED886796272F647210` |
| Pool ID | `0xce389e78282dedac7b18ba7f775b7602d2ab3ab171bbd6711eb0239be6ef4dcc` |
| FastLane AuctionHandler | `0xD32EdF6642D917DbBE7B8BF8e5d6F5df6a9FFF58` |
| Explorer | [Monadscan](https://monadscan.com/address/0x80c74517BCC2D67fFE02D3ED886796272F647210) |

Integrate the proxy address, never its implementation address.

Display name: `ThogAMM`. Canonical logo:
[https://avatars.githubusercontent.com/u/85769984?v=4](https://avatars.githubusercontent.com/u/85769984?v=4).

## Initial token registry

| Token | Address | Decimals |
|---|---|---:|
| USDC | `0x754704Bc059F8C67012fEd69BC8A327a5aafb603` | 6 |
| AUSD | `0x00000000eFE302BEAA2b3e6e1b18d08D69a9012a` | 6 |
| USDT0 | `0xe7cd86e13AC4309349F30B3435a9d337750fC82D` | 6 |
| WMON | `0x3bd359C1119dA7Da1D913D1C4D2B7c461115433A` | 18 |
| WETH | `0xEE8c0E9f1BFFb4Eb878d8f15f368A02a35481242` | 18 |
| WBTC | `0x0555E30da8f98308EdB960aa94C0Db47230d2B9c` | 8 |
| cbBTC | `0xd18B7EC58Cdf4876f6AFebd3Ed1730e4Ce10414b` | 8 |
| XAUt0 | `0x01bFF41798a0BcF287b996046Ca68b395DbC1071` | 6 |

Use WMON rather than native MON. Fee-on-transfer tokens are unsupported.
`getTokens(poolId)` is the authoritative registry; the table is the initial
eight-token configuration, not a fixed capacity. Schema 7 supports up to 32
tokens and 32 risk categories. Discover added tokens and their decimals from
`getPoolData`; directional availability is dynamic.

## Aggregator interface

```solidity
interface IThogAMM {
    enum OrderSide {
        Sell,
        Buy
    }

    enum Capability {
        Unset,
        SellOrder,
        BuyOrder,
        PriceFunction,
        FeeOnTransfer,
        ConstantPrice,
        TokenBalanceIndependent,
        ScaledPrices,
        HardLimits,
        MarginalPrice,
        Derivatives
    }

    struct Fraction {
        uint256 numerator;
        uint256 denominator;
    }

    struct Trade {
        uint256 calculatedAmount;
        uint256 gasUsed;
        Fraction marginalPriceAfterTrade;
    }

    function getPoolIds() external pure returns (bytes32[] memory);
    function getTokens(bytes32 poolId) external view returns (address[] memory);
    function getCapabilities(bytes32 poolId, address sellToken, address buyToken)
        external view returns (Capability[] memory);
    function getLimits(bytes32 poolId, address sellToken, address buyToken)
        external view returns (uint256[] memory);
    function price(
        bytes32 poolId,
        address sellToken,
        address buyToken,
        uint256[] calldata specifiedAmounts
    ) external view returns (Fraction[] memory);

    function makerQuoteExactInput(
        address tokenIn,
        address tokenOut,
        uint256 amountIn
    ) external view returns (uint256 amountOut, uint256 lastPostedBlock);

    function makerSwapExactInput(
        address tokenIn,
        address tokenOut,
        uint256 amountIn,
        uint256 minAmountOut,
        address recipient,
        uint256 deadlineBlock
    ) external returns (uint256 amountOut);

    function swapWithExtraFees(
        address tokenIn,
        address tokenOut,
        uint256 amountIn,
        uint256 minAmountOut,
        uint256 expiry,
        uint256 extraFeePpm,
        address feeRecipient
    ) external returns (uint256 amountOut);

    function swap(
        bytes32 poolId,
        address sellToken,
        address buyToken,
        OrderSide side,
        uint256 specifiedAmount
    ) external returns (Trade memory trade);
}
```

All amounts are raw token units.

## Quote and settlement behavior

`makerQuoteExactInput(tokenIn, tokenOut, amountIn)` returns the direct-path gross
`amountOut`, subject to the read-only quote admission rules, and the shared
full-price publication's `lastPostedBlock`. All registered prices have the same posting block. A revert
applies to that request, not necessarily every size for the pair.

The ERC-7815 behavior is:

- `getCapabilities()` returns `SellOrder`, `BuyOrder`, `PriceFunction`, and
  `MarginalPrice`.
- `getLimits()` returns `[sellLimit, buyLimit]`. The buy limit is the actual
  output-token balance. The sell limit combines the arithmetic input bound
  with the receiving-token quote cap. Category caps are enforced by the exact
  quote and settlement, not solved by this upper-bound getter. The nonlinear curve does not promise execution at every smaller input. `HardLimits` is not advertised; the exact quote remains authoritative.
- `price()` returns the marginal raw buy-token units per raw sell-token unit as
  the exact `numerator / denominator` ratio. The denominator varies with the
  tokens' decimal difference and is not fixed at `1e18`; nonzero prices retain
  36 decimal places in human-token space. Zero is `Fraction(0, 1)`. This is not
  an average execution quote. Each supplied amount is evaluated independently
  against the same pre-trade state; the array is not a sequence of fills.
  **One failing amount reverts the entire array**, including when a category
  cap rejects `price([0])`. Validate each candidate size locally, or query it
  separately; do not treat a grid spanning `sellLimit` as an executable range.
- `swap(..., Sell, amountIn)` returns output in `Trade.calculatedAmount`.
  `swap(..., Buy, amountOut)` returns the minimum required input and transfers
  exactly `amountOut`.

ERC-7815 `swap()` has no slippage or freshness argument. Use it for
block-pinned simulation, then settle through `makerSwapExactInput()` with its
`minAmountOut`, `recipient`, and inclusive `deadlineBlock`. To route an output
target through this protected exact-input method, use the simulated minimum
input and the requested output as `minAmountOut`. Integer rounding can produce
more output than `Buy` would pay, so simulate the actual settlement call too;
its output balance and final category holdings can differ from the `Buy` call.

Simulating `swap()` executes token transfers and final cap checks inside the
call. The simulated caller needs the input-token balance and allowance for the
proxy. The read-only quote and `price()` use the 90% quote thresholds; swap
settlement uses the full caps after transfers and callbacks. These are distinct
contract rules, so a read-only rejection at the quote threshold does not imply
that settlement at the full cap would fail.

### Execution widening

Read-only `makerQuoteExactInput()` and `price()` calls do not include execution
widening. If `tx.gasprice > 2 * block.basefee` or the FastLane AuctionHandler is
already warm when ThogAMM first checks it in the transaction, an exact-input
swap uses:

```text
amountOut = floor(directAmountOut * 9_990 / 10_000)
```

This reduction is applied once, including when both conditions hold, after the
ordinary quote calculation and before any output-token fee. The gas-price
comparison is strict: exactly twice the base fee does not trigger widening on
its own. `tx.gasprice` is the transaction's effective gas price, not its maximum
fee cap. Simulate with the same gas price, block base fee, and warm-account
context as the submitted transaction; an exact-output `Buy` executed in that
context includes the reduction while solving the required input. The returned
ERC-7815 marginal price includes the same reduction. Raw-unit flooring can make
the effective widening slightly greater than 10 bps for small or low-decimal
outputs.

For Monad `eth_call` simulations, provide the transaction's fee fields
explicitly: either `gasPrice`, or `maxFeePerGas` and `maxPriorityFeePerGas`.
Calls that omit these fields can expose both `tx.gasprice = 0` and
`block.basefee = 0`, even when the selected block's header has a nonzero base
fee. This suppresses the gas-price trigger; the warm-AuctionHandler trigger
can still apply. A priced call can fail for insufficient native balance, so
use the intended funded `from` address or a simulation-only balance override
for that address. `eth_call` does not spend the overridden funds.

When using a local EVM, set the simulated block base fee as well as the
transaction gas price. A zero base fee with any positive gas price satisfies
the widening condition. Use `swap()`, `makerSwapExactInput()`, or
`swapWithExtraFees()` to simulate the execution adjustment; the read-only
`makerQuoteExactInput()` and `price()` methods omit it regardless of fee fields.

### Fee-recipient swaps

Use `swapWithExtraFees` when the route should pay an integrator fee from the
gross `tokenOut`:

```text
feeAmount = floor(grossAmountOut * extraFeePpm / 1_000_000)
netAmountOut = grossAmountOut - feeAmount
```

`extraFeePpm` is capped at `1_000_000`; `10_000` is 1%. `minAmountOut` protects
the net output returned to the caller, and `expiry` is an inclusive Unix
timestamp. Use the collection-contract address assigned to the integration; an
EOA, zero address, or the ThogAMM proxy is invalid when `extraFeePpm` is
nonzero. The function returns the caller's net `amountOut`.

## Build the schema-7 model in memory

Use the [published aggregator ABI](abi/ThogAMM.json) and the exact snapshot tuple below.
`getPoolData(uint8,uint8)` retains its selector but its return tuple changed.
The retired `makerSnapshot()`, `makerState()`, `makerStateV3()` and
`makerRiskV3Ready()` selectors are absent from this release. Read all policy and
readiness fields through `getPoolData`. An old eight-token decoder cannot seed
v7, even when only the original eight tokens are registered.

### 1. Bootstrap one consistent state

1. Select a canonical block `H` and record its hash and header. Call
   `getPoolData(0, 32)` at that block hash. With a provider that only accepts a
   block number, verify the block hash around the read and retry if it changed.
2. Require schema 7 and matching block number, parent hash and active counts.
   `parentBlockHash` is the **parent's** hash, not `H`'s hash. The block number
   alone cannot distinguish two forks. Read the base fee and timestamp from
   `H`'s RPC header for execution simulation; an unpriced `eth_call` can return
   zero in `PoolData.baseFeePerGas`.
3. Decode every returned `(slot, value)` into a slot-addressed word array.
   The snapshot supplies **126 decoded words**: slots 2–127, exactly once each.
   Reject missing, duplicate or out-of-range slots. Raw storage uses
   `1 << 255` for a logical empty word; `getPoolData` returns zero for that marker. Do not treat
   array position as a physical slot or omit words because they belong to
   tokens outside the requested pair.
4. Store all token metadata, all category metadata, all `portfolioBalances`,
   and `nativeBalance`. Check token/category counts against control word 2,
   token addresses, decimals, category assignments and anchor references.
   Verify physical layout 7, wire 7 and model 1 in slot 8 bits 160–215, and retain its
   nonzero registry generation with the registry.
   Balances are unsigned raw token units; native balance is raw MON wei.
5. Install the state atomically and replay canonical events only **after** `H`.
   The snapshot already includes every transaction in `H`.

A suitable state shape is:

```text
LocalThogAMM {
    chainId, proxy, implementation
    layoutVersion = 7, wireVersion = 7, modelVersion = 1
    registryGeneration
    appliedThrough { blockNumber, blockHash, transactionPosition }
    words[128]                       // populated by explicit returned slot
    tokensByIndex[]                   // address, decimals, category, field refs
    tokenIndexByAddress              // local lookup; not an onchain mapping
    categories[]                     // anchor and field refs
    rawTokenBalances[tokenCount]      // from portfolioBalances, all tokens
    rawNativeBalance
}
```

A local address lookup is only an index into the discovered registry. No legacy
price words, inventory words, extension pages or fixed-eight-token tables are
part of the model. For metadata pagination, `32` is the end sentinel;
`portfolioBalances`, categories and the complete word set are returned on every
page. Pin all pages to the same block and combine them before installation.
The [registry guide](#snapshot-abi) specifies the full tuple,
reference encoding, field widths and listing behavior.

The snapshot is the complete input to the local model. No estimator, exchange
feed, unpublished target or bot configuration is required. The Rust SDK exposes
`decode_pool_data(proxy, result_bytes, block_selector)` for custom transports and
`PoolModel::prepare(token_in, token_out)` for repeatedly quoting sizes against one
immutable snapshot. Rebuild prepared pairs after every state or quote-block change.

If implementing the decoder in another language, a metadata reference is
`slot = ref >> 16`, `offset = (ref >> 8) & 255`, `width = ref & 255`.
Extract `(words[slot] >> offset) & ((1 << width) - 1)`. Reference zero means
absent; for a signed field of width `w`, subtract `2^w` when bit `w-1` is set.
Use arbitrary-precision integers or equivalent full-precision arithmetic,
not floating-point numbers. The logical word is a big-endian uint256, while
fields are numbered from its least significant bit. `priceTail` is always zero.

### 2. Value actual inventory with the current policy

Category `inventory` references now point to a signed 64-bit **external
exposure minus target** offset, measured in micro units of that category's
anchor token. They are not cached executor inventory. For category `c`:

```text
exposureUSD[c] = trunc(offsetMicro[c] * anchorPriceLower[c] / 1e6)
for each registered token t in category c:
    held = rawTokenBalances[t]
    if t is WMON: held += rawNativeBalance
    exposureUSD[c] += floor(held * tokenPriceLower[t] / 10^decimals[t])
```

Use every registered token in the category, including tokens other than the
swap endpoints. Native MON contributes to WMON's category risk, but it does
**not** increase WMON's ERC-20 output capacity or the inventory used in its
wrapper-friction curve. Output capacity is the actual output-token balance.
Both receiving-inventory caps are separate from risk exposure. Quotes require
the post-trade raw input-wrapper balance and gross input-category USD value to
stay strictly below 90% of their respective caps. Include every wrapper in the
category, including a singleton, and native MON for WMON. Credit the actual
output payout for a same-category swap. Exceeding either quote threshold
returns the same inventory-shortage error as insufficient output balance.
Settlement checks fresh final balances against both full caps after all
transfers and fee callbacks; equality passes. Taker flow bypasses these checks.
See the [exact rules](#inventory-admission-and-final-settlement).

Loans change both cash balances and external exposure; the final quote must
include both changes from the same transaction.

Keep three quantities separate: the signed external-minus-target offset in
risk policy, the unsigned category USD target used as a sliding-wrapper
denominator, and the gross inventory cap. The wrapper publication owns its
USD target. It does not rewrite risk offsets or caps, and a risk publication
does not rewrite wrapper targets. Do not subtract the wrapper target a second
time when valuing exposure.

Risk is the positive part of the value-neutral category covariance change,
scaled by lambda. Same-category trades have zero category-risk change but
still pay configured widths, the input-token volume charge and wrapper costs. Sliding wrapper friction
integrates the input received and output paid against each endpoint's own
ERC-20 inventory and its category USD target. An output refund participates in
the nonlinear solve and can make an inventory-reducing trade pay above oracle
fair value.

Every swap also pays the received token's inventory-independent size charge,
including risk-reducing trades and zero-lambda policies. For input notional
`n` in USD-wad and the token's 16-bit volume-rate coefficient `r`, its cost is
`ceil(r*n*n/1e27)` USD-wad. This cost is outside the positive-risk clamp and
starts at zero on each swap; splitting a trade reduces this component.

Reproduce the integer operations in the
[exact quote specification](#exact-integer-quote-reference),
[the curve implementation](https://github.com/thogard785/thog-amm-poll-sdk/blob/main/model/src/curve.rs), and
[the shared model](https://github.com/thogard785/thog-amm-poll-sdk/blob/main/model/src/model.rs). In particular:

- Prices use a 56-bit mantissa and 8-bit exponent. Use the lower endpoint for
  input and inventory valuation, and the upper endpoint for output conversion.
- Widths use **0.01 bp** units. Covariance is signed 16-bit, scaled by `1e9`;
  lambda is unsigned 32-bit, scaled by `1e6`.
- Charge the input token's bid width and output token's ask width, both category
  widths and the learned unordered pair premium. The volume coefficient uses
  0.01 bp per $1,000 and belongs only to the input token.
- Signed divisions truncate toward zero. Preserve each per-category division
  before summing the risk gradient.
- Entry wrapper charges round up; output refunds round down. Preserve the
  full discriminant precision and adjacent-integer check in the output solve.
- The exact-output solver finds the smallest raw input on the supported rising
  branch. A floating-point inverse or a rounded fair-price ratio is insufficient.

Keep the three public surfaces distinct:

| Surface | Required semantics |
| --- | --- |
| Read-only exact input | Exact integer output plus actual output capacity and both 90% quote caps. No execution widening. |
| Execution exact input/output | The same curve with the actual gas-price/account-warmth adjustment; actual payout and full inventory caps at settlement. |
| Marginal price / limits | Derivatives and independent upper bounds from the same curve; neither is an average-output quote or a promise that every smaller trade is available. |

Build a fresh curve whenever the state or quote block changes. To simulate
sequential fills, copy the state, add the actual input and subtract the actual
gross output, then build the next curve from those new balances. For `Buy`,
subtract exactly the requested output; the forward curve at the minimum input
can round to a larger output. Keep volume cost starting from zero on each swap.
`swap().marginalPriceAfterTrade` evaluates the original pre-trade curve at the
executed input, rather than recomputing a spot curve from the final balances.
Callbacks and native movements still require execution simulation for exact
settlement parity.

### 3. Apply policy and balance events

Consume complete canonical transactions in `(blockNumber, transactionIndex,
logIndex)` order. Deduplicate by `(blockHash, transactionHash, logIndex)` if
subscriptions overlap. Publish an immutable state only after all relevant logs
and balance changes for that position have been applied; intermediate logs of
an unwrap or loan are not a coherent quote state.

Filter policy/checkpoint logs to the proxy address and token movements to the
discovered token contracts. Stage changes on a private copy, then install the
complete transaction or block atomically. Deep-copy mutable balances before simulating a route or publishing a new state,
so prior snapshots and concurrent readers remain unchanged.

The executor emits these schema-7 policy events:

```solidity
event MakerPageUpdated(uint8 indexed lane, bytes payload, uint256 control);
event MakerLendingExposureUpdated(
    uint8 indexed venue, uint8 indexed category, uint32 sequence, int64 offset
);
event Paused(bool paused);
event MakerWmonBalanceCheckpoint(uint256 balance);
event NativeBalanceCheckpoint(uint256 balance);
event MakerWrapperCostApplied(int256 costUsdWad);
```

| Event/source | Model update |
| --- | --- |
| `MakerPageUpdated`, lane 1 | Decode every registered price, side bits and enabled flag; stamp the actual inclusion block and price sequence. |
| `MakerPageUpdated`, lane 2 | Replace category offsets/anchors/widths, covariance, token bid/ask widths and volume rates, learned pair premiums and risk controls; set risk readiness. Preserve wrapper policy, category USD targets and all balances. |
| `MakerPageUpdated`, lane 4 | Replace wrapper kind/refund/coefficient fields and category USD targets atomically; set wrapper readiness. There is no wrapper publication counter. |
| `MakerPageUpdated`, lane 8 | Decode the ABI arrays and replace only the named token/category caps after applying the contract's cap encoding. Control is unchanged; bits 136–137 are reserved. Initial/migration caps come from the snapshot and do not emit this event. |
| `MakerLendingExposureUpdated` | Replace the category's signed offset and slot 7's lending sequence at bits 160–191 with the absolute emitted values. Venue 0 is Neverland; 1 is Euler. Apply the cash movements in the same transaction. |
| `Paused` | Set maker pause bit 132 in control word 2. This owner pause also controls taker execution. |
| Registered token `Transfer` | Subtract when `from` is the proxy and add when `to` is the proxy. A self-transfer nets to zero. Include mint/burn transfers. |
| WMON `Deposit` / `Withdrawal` | Apply actual wrapped-token mint/burn semantics for the supported WMON implementation. Do not count both a deposit event and a mint `Transfer` for the same movement if an implementation emits both. |
| `MakerWmonBalanceCheckpoint` | Compare the absolute WMON balance with replay at that position; a mismatch identifies missing/incorrect WMON events. Later movements still apply. |
| `NativeBalanceCheckpoint` | Replace native MON balance absolutely at that log position. |
| `MakerTokenAdded` / `MakerTokenRetired` | Invalidate the registry generation and reload a complete snapshot; neither event contains the complete replacement policy. Retirement can move existing indices even when replacement leaves the counts unchanged. |
| Proxy implementation upgrade / migration | Verify implementation/schema compatibility and rebuild from a post-upgrade snapshot before using the new model. |

Apply successful publication events using the [publication layouts](#publications)
and use the emitted `MakerPageUpdated.control` as the resulting control word.
The contract already validated the payload. A locally submitted policy is not
a successful event, and reverted transactions produce no successful events.
A risk publication includes the lending sequence it was based on; the contract
rejects a stale debt snapshot. Category anchor metadata must follow the newly
applied category words if a risk publication changes the anchor.

#### Translate publication fields into storage fields

`payload` is not a storage-page image. Price, risk and wrapper payloads consist
of a 32-byte header followed by packed word groups. Decode each word as a
big-endian integer and its fields from low bits upward. Let `T` be the active
token count and `C` the category count; each group starts at a fresh word.

| Lane | Payload groups after the header | Destination |
| --- | --- | --- |
| Price | `ceil(T/4)` words of 64-bit prices | Slots 21 onward, four prices per word. |
| Risk | `ceil(C/3)` category words; `ceil(C*(C+1)/32)` covariance words; `ceil(T/5)` token-policy words; `ceil(T*(T-1)/32)` pair-premium words | Categories at 29, covariance at 40, pair premiums at 73. Repack each 48-bit token policy into the bid/ask/volume fields of its 75-bit token record at slot `9+i/3`. |
| Wrapper | `ceil(T/3)` words of 76-bit wrapper policies; `ceil(C/4)` words of 64-bit category targets | Repack kind/refund into the token record and coefficients four per word at 104. Write the targets four per word at 112 in the same state update. |

Use the [exact header offsets and field layouts](#publications).
Risk token policies carry bid/ask/volume at offsets 0/16/32; storage places them
at 15/43/59 within each token record. Wrapper policies carry coefficient/kind/
refund at 0/64/66; storage places kind/refund at 31/33 and coefficients in their
own array. Mask individual fields to preserve the other lane and reserved bits.
Refresh derived category anchor indices and price references after risk updates.
The current payload lengths, including headers, are 96/256/192 bytes for
price/risk/wrapper with eight tokens and five categories; at 32/32 they are
288/2656/640 bytes.

For lane 8, ABI-decode `(address[], uint256[], uint8[], uint256[])`. Resolve
addresses through the current registry. Encode each supplied limit with
the cap encoding below before writing its 24-bit
field; the event contains the requested amounts, which can exceed the rounded
stored limits. Preserve unspecified caps and process repeated entries in order
(the last value wins). No publication header or registry-generation field is
present in this lane.

Compute each lane's control changes and compare them to the emitted `control`,
then store that complete control word. Price updates change the sequence,
inclusion block, sides and enabled flag; risk changes readiness, max age,
widening and lambda; wrapper sets only its readiness bit; caps change none.
Only price publication refreshes the posting block. Risk and wrapper events
must be replayed independently, including their readiness changes on rollback.

Do not use the price sequence as an event cursor: it wraps at uint16, and other
lanes have no publication counter. Canonical log positions establish ordering.
The lending sequence in a risk header is a validation dependency, not a new
lending mutation; only a lending event changes that sequence during normal
event replay.

#### Reconcile balances exactly once

`MakerSwapExecuted` reports the gross output before any integrator fee.
`MakerExtraFeePaid` and `MakerWrapperCostApplied` are accounting events. When
using token transfers for inventory, **do not apply swap amounts or fee amounts
as a second balance delta**. Transfers cover maker swaps, taker swaps, loans,
owner withdrawals and direct funding. WMON checkpoints validate earlier WMON
movements; they are not additional transfers or checks of other tokens.

Native checkpoints cover the executor's instrumented native movements. Forced
native transfers can bypass `receive()`, and nonstandard tokens can change
balances without ordinary transfer events. An exact mirror must obtain those
changes from execution/account-state updates or another atomic block-pinned
snapshot. An event-only integration must not claim completeness for unsupported
balance semantics. If the available feed cannot provide the required state,
use the authoritative onchain quote for that state.

### 4. Advance time, check availability and recover state

Quote at an explicit block number, including blocks with no relevant events.
For parity with an end-of-block RPC quote, apply every relevant transaction
through that block. Supplying a newer block number to an old state only ages
its prices; it does not discover intervening balance or policy changes.
Age is `quoteBlock - postedBlock`; risk/wrapper/cap updates do not refresh
prices. Availability requires schema 7, maker unpaused, prices enabled,
structural and wrapper readiness set independently,
the input bid and output ask enabled, and age within the nonzero maximum age.
Reject unknown or identical
endpoints, zero direct input/output, invalid arithmetic domains and output
above the actual ERC-20 balance as the contract does.

On a missing publication, inconsistent control word, unsupported upgrade or
unresolved event gap, rebuild from an authoritative snapshot and diagnose the
missing state. On a reorg, roll back the entire affected state to a common
ancestor and replay the replacement fork, or take a fresh snapshot on it.
Never combine prices from one fork with balances from another. A snapshot at
`H` supersedes events through `H`; older confirmations may be useful for
transaction attribution but cannot rewind the model.

On registry replacement, also discard cached address-to-index and category
lookups, pair locations and derived curves, even if counts stay the same.
Historical records must retain their original address/category binding;
old indices cannot identify assets in the replacement registry.

### 5. Verify local parity before enabling routing

Compare integer outputs against `makerQuoteExactInput` at the **same block**
and state. Exercise both directions, same-category wrapper pairs, trades that
increase/reduce inventory, small raw amounts, maximum-age boundaries and
insufficient output balance. For exact output, compare the required input and
verify that one less raw input cannot attain the requested output. Use the [captured deployed-contract corpus](fixtures/deployed-v7.json.gz) and
[read-only capture tool](tools/capture_quotes.py) to reproduce the comparisons.
The SDKs and Kyber adapter test their decoders and integer outputs against this
same corpus. Additional execution and event-replay fixtures exercise settlement
and state transitions; see the verification record in the README.

Also check snapshot → replay → fresh-snapshot parity at the same block after
each publication lane, wrapper-target changes, loans, transfers, native/WMON
movements and cap changes. Exercise risk-ready/wrapper-unready bootstrap and
rollback of either publication independently, plus listing and retirement that
move indices. Compare quote fields and balances, including cap rounding and
same-category payout valuation; a passing arithmetic corpus alone does not
validate an event reducer.

Execution simulation must additionally reproduce gas price, base fee and
AuctionHandler warmth, then include any integrator fee. The final contract call
is authoritative at inclusion. Do not add local slop or safety multipliers to
conceal a model discrepancy; resolve the mismatched state or integer operation.

## Event changes from the previous integration guide

**Yes: the price, risk and packed-inventory event stream changed in v7.**
Update subscriptions and ABI decoding when the proxy migrates.

| Previous event | Schema-7 replacement/status |
| --- | --- |
| `MakerPriceStateUpdated`, `MakerPricesPushed` | Removed; use `MakerPageUpdated` lane 1, including the emitted post-state control word. |
| `MakerRiskParamsPushed`, `MakerRiskStateUpdated`, `MakerRiskStateUpdatedV3`, `MakerRiskStateUpdatedV4` | Removed; use `MakerPageUpdated` lanes 2 and 4 for their independent policy publications. |
| `MakerInventoryUpdated`, `MakerInventoryUpdatedV3` | Removed. Actual holdings come from balances and balance movements; loan offsets come from `MakerLendingExposureUpdated`. |
| `MakerStorageUpdated` | Still declared in the ABI for historical decoding, but the v7 runtime does not emit it. It is not a v7 update stream. |
| `MakerTokenAdded` | Signature includes the expanded bid/ask, volume-rate and inventory-cap metadata; use the current ABI. Field references use v7 locations/widths. It invalidates the local shape and requires a full snapshot. |
| `MakerSwapExecuted`, `MakerExtraFeePaid` | Signatures unchanged; accounting events, not an additional inventory delta. |
| `MakerWmonBalanceCheckpoint`, `NativeBalanceCheckpoint`, `Paused` | Signatures unchanged; keep consuming them. Native balance now affects the exact category-risk quote. |
| `MakerWrapperCostApplied` | New signed USD-wad accounting event for the integrated wrapper cost; it does not mutate the model. |

Historical schema-6 algorithms remain available in Git history.

## Snapshot ABI

The response is **one dynamic tuple**, not thirteen top-level return values.
Use a tuple-aware ABI decoder; dynamic offsets are relative to their enclosing tuple.
The following fields are ordered exactly as the deployed ABI. `balances` covers
the metadata page; `portfolioBalances` always covers the entire registry.

```solidity
struct TokenMetadata {
    address token;
    uint8 decimals;
    uint8 category;
    uint32 price;
    uint32 priceTail;
    uint32 tokenBidSpread;
    uint32 tokenAskSpread;
    uint32 volumeRate;
    uint32 categorySpread;
    uint32 inventory;
    uint32 sides;
    uint32 postedBlock;
    uint32 sequence;
    uint32 pairStart;
    uint32 inventoryCap; // uint24: raw-unit mantissa:16 | binary shift:8; all-one = uint256.max
}

struct CategoryMetadata {
    uint8 anchorTokenIndex;
    uint32 price;
    uint32 priceTail;
    uint32 inventory;
    uint32 spread;
    uint32 postedBlock;
    uint32 inventoryCap; // same encoding, denominated in USD wei
}

// Decoded word: the physical 1<<255 empty marker is returned as zero.
struct StorageWord {
    uint16 slot;
    uint256 value;
}

struct PoolData {
    uint16 schemaVersion;
    uint256 blockNumber;
    uint256 baseFeePerGas;
    // The EVM cannot read the current block's hash. This anchors its parent.
    bytes32 parentBlockHash;
    uint8 tokenCount;
    uint8 categoryCount;
    uint8 startTokenIndex;
    TokenMetadata[] tokens;
    uint256[] balances;
    // Every category is included: quotes depend on the entire portfolio.
    CategoryMetadata[] categories;
    // All 126 quote and configuration words (slots 2..127), regardless of pagination.
    StorageWord[] words;
    // Native MON contributes to WMON category risk, not ERC-20 capacity.
    uint256 nativeBalance;
    // Every registered ERC-20 balance in global token-index order.
    uint256[] portfolioBalances;
}

function getPoolData(uint8 startTokenIndex, uint8 stopTokenIndex)
    external view returns (PoolData memory);
```

## Exact integer quote reference

The following rules specify the state layout and integer calculation independently
of any SDK. All arithmetic must match the contract, including its checked 256-bit
operations, full-precision mul-div intermediates and signed truncation toward zero.

## Word addressing

Words use ordinary 32-byte big-endian ABI serialization. Offsets below count
bits from the least significant bit. Signed packed fields use two's complement.
Every unused tail field in a publication must be zero. Token addresses are
compiled constants and must be taken from the same atomic snapshot’s complete
`tokens` metadata, rather than decoded from storage words. Three 75-bit records
share each token word; bits 225–255 are reserved. The final token word, slot 19,
has two records, so bits 150–255 are reserved there. The final category word,
slot 39, owns only its first two 85-bit fields.

| Slot/field | Encoding |
| --- | --- |
| 2 bits 0–7 | Physical layout version (7) |
| 2 bits 8–13 / 14–19 | Token/category counts |
| 2 bits 20–35 / 36–67 | Price sequence / posting block |
| 2 bits 68–131 | Two side bits per token: bid at `2*i`, ask at `2*i+1` |
| 2 bits 132–135 | Maker paused, price enabled, risk ready, wrapper ready |
| 2 bits 136–137 | Reserved |
| 2 bits 138–145 / 146–161 | Maximum age / widening per block |
| 2 bits 162–193 | Lambda, scaled by `1e6` |
| 2 bits 194–255 | Reserved |
| `9+i/3`, offset `75*(i%3)` + 0–4 | Compiled catalog ID (no stored address) |
| Same record, bits 5–9 / 10–14 | Decimals / category |
| Same record, bits 15–30 / 43–58 | Token bid / ask width in 0.01 bp units |
| Same record, bits 31–32 / 33–42 | Wrapper kind / refund permille |
| Same record, bits 59–74 | Nonzero input volume rate, 0.01 bp per $1,000 |
| 20, offset `6*catalogId`, width 6 | Active token index + 1; zero means inactive |
| `21+i/4`, field `i%4` of 64 bits | Encoded price |
| `29+c/3`, field `c%3` of 85 bits | External/target offset `int64`, category width `uint16`, anchor token index `uint5` |
| `40+j/16`, field `j%16` of 16 bits | Signed covariance coefficient, scaled by `1e9` |
| `73+j/16`, field `j%16` of 16 bits | Unordered pair width, 0.01 bp units |
| `104+i/4`, field `i%4` of 64 bits | Wrapper coefficient, scaled by `1e18` |
| `112+c/4`, field `c%4` of 64 bits | Category target USD, scaled by `1e6` |
| 7 bits 160–191 | Lending sequence |
| 8 bits 160–167 / 168–175 / 176–183 | Physical layout / publication wire / quote model identifiers: 7 / 7 / 1 |
| 8 bits 184–215 | Nonzero registry generation |
| `120+i/10`, offset `24*(i%10)` | Token inventory cap in raw ERC-20 units, packed mantissa/shift |
| `124+c/10`, offset `24*(c%10)` | Category inventory cap in USD-wad, packed mantissa/shift |

Runtime writes preserve bits outside the owning field, including the physical
spare bits listed in the storage layout above. A future wire or
model revision need not move storage or change the physical layout identifier.

For covariance, sort category indices `a <= b` and use `j=b*(b+1)/2+a`.

The publisher verifies that the source covariance is positive semidefinite.
It rounds off-diagonal coefficients to the nearest `1e-9` tick and rounds each
diagonal upward after adding the sum of the actual off-diagonal rounding errors
in that row. The encoding error matrix is symmetric diagonally dominant with
nonnegative diagonal, so the encoded covariance remains positive semidefinite.
Off-diagonal error is at most half a tick; diagonal error is less than
`1 + (categoryCount - 1)/2` ticks. Already encoded matrices round-trip exactly.
This corrects representation error only; it has no inventory or fill dependency.
For pair widths, sort distinct token indices `a < b` and use `j=b*(b-1)/2+a`.
These rules include the original tokens and every appended token equally.

A price field stores mantissa `m` in bits 0–55 and exponent `e` in bits 56–63:
`lower = m * 10^(18-e)`, `upper = (m+1) * 10^(18-e)` in USD-wad.
Valid fields have `m >= 2,000,000` and `e <= 18`. Input prices and inventory
valuation use `lower`; the output conversion uses `upper`. Use integer powers
of ten. Each endpoint interval is at most 0.005 bp; the combined ratio error
is below 0.01 bp.

A cap field uses a 16-bit unsigned mantissa and an 8-bit binary shift:
`value = mantissa << shift`. `0xffffff` decodes to `uint256.max`; it remains
a numeric cap and never disables a check. Canonical finite encodings have `shift <= 240`
and either `shift == 0` or `mantissa >= 32768`. Encode a finite amount by
`shift = max(0, floor(log2(amount)) - 15)` and `mantissa = amount >> shift`.
Encoding rounds down, with relative error below `1/32768` for nonzero shifted
values. Zero is an actual zero cap. Ten fields occupy each storage word; unused
tail and high bits remain reserved. Prices never rescale a token cap.

## Publications

The first word is a header; remaining words contain the arrays below. Field
groups are concatenated in the stated order, with each group beginning at a
new word. Counts and generation refer to the current registry; every automatic publication must match the generation stored in slot 8 bits 184–215.

| Lane | Header offsets | Array groups |
| --- | --- | --- |
| Price | sequence 0:16; enabled 16:1; sides 17:64; tokens 81:8; version 89:8; registry generation 97:32 | Prices: 4 × 64-bit fields/word |
| Risk | version 0:8; tokens 8:8; categories 16:8; lambda 24:32; max age 56:8; widening 64:16; reserved zero 80:32; lending sequence 112:32; registry generation 144:32 | Category policies: 3 × 85-bit; covariance triangle: 16 × 16-bit; token policies: 5 × 48-bit (bid 0:16, ask 16:16, volume rate 32:16; high 16 word bits zero); learned pair premiums: 16 × 16-bit |
| Wrapper | version 0:8; tokens 8:8; categories 16:8; reserved zero 24:8; registry generation 32:32 | 3 × 76-bit fields: coefficient 0:64, kind 64:2, refund 66:10; category USD targets: 4 × 64-bit |


The existing price nonce uses uint16 ordering: zero is invalid; from a nonzero
previous nonce, the modular forward distance must be 1–15. Its posting block is
assigned at inclusion. Risk, wrapper and cap writes are idempotent parameter setters,
with no additional publication counters. Risk and wrapper reserved header fields must be zero.
The publisher serializes parameter updates using its existing transaction and
confirmation machinery. A risk publication's lending sequence must equal slot 7 bits 160–191.
No lane publishes physical executor balances. Manual cap updates use
`setInventoryCaps(address[],uint256[],uint8[],uint256[])`: token addresses and
raw limits, then category IDs and USD-wei limits. It changes only those entries,
has no header or freshness input, and emits lane 8 with the ABI-encoded arrays
of requested limits. Reproduce the downward cap encoding before updating the
24-bit stored fields; preserve unspecified entries and apply duplicates in
order. The cap setter does not change control or readiness; bits 136–137 remain
reserved. Initialization and migration install fixed packed constants calculated
offchain without a lane-8 event, so bootstrap those caps from the snapshot.
See the snapshot caps; consumers do not need to submit cap updates.

Wrapper kind 0 is none, 1 fixed, 2 sliding. None requires zero coefficient and
refund. Fixed requires a coefficient below `1e18` and zero refund. Sliding
allows refund at most 1000 and requires a nonzero category target; a zero
coefficient produces zero friction. Configured active sliding policies use a
positive coefficient. Structural publication preserves wrapper
metadata and category USD targets; wrapper publication changes its policy and targets atomically and preserves token widths and learned pair premiums.

## Exact input

Let `floor(a/b)` denote unsigned integer division, `ceil(a/b)` its upward
counterpart, and `trunc(a/b)` signed division toward zero. Products described
with full precision must use mul-div arithmetic, not overflowing uint256
intermediates. The reference implementations specify the arithmetic domain.

First derive the arithmetic input limit:
`inputLimit = ceil((664619068552888026590626425199190042 + 1) * inputScale / priceInLower) - 1`
using full-precision mul-div. This bound applies even when lambda is zero or the
tokens share a category. Reject input above it. In correlated risk valuation
and sliding-wrapper valuation, each token's inventory USD-wad must fit `uint128`.
This bound does not apply to the separate gross category-cap calculation.

If lambda is zero, skip the risk exposure scan and set the risk penalty to zero;
volume and wrapper charges still apply. If the categories are identical, set
variance and gradient to zero without scanning portfolio risk. Avoid evaluating
unused risk expressions that could overflow when the contract skips them.

For input token `i`, output token `o`, and categories `a`, `b`:

1. Add both category widths, the input token’s bid width, the output token’s ask width, the learned pair premium, and `age * widening` into `spread`. Require `spread < 1e6`.
2. Set `d[c] = covariance[a,c] - covariance[b,c]` and
   `v = covariance[a,a] + covariance[b,b] - 2*covariance[a,b]`.
3. For each category with `d[c] != 0`, start exposure USD-wad at
   `trunc(externalOffsetMicro[c] * anchorPriceLower[c] / 1e6)`.
   Add `floor(rawBalance[t] * priceLower[t] / 10^decimals[t])` for every
   registered token in that category. Add native balance to WMON's raw balance
   before valuation. Positive external collateral excluded by policy is not
   silently reintroduced as spendable inventory.
4. Set `g = sum_c trunc(exposureUSD[c] * d[c] / 1e9)`, preserving the
   **per-category** division order. For `a == b`, both `v` and `g` are zero.
   This removes category risk only; volume and wrapper costs below still apply.
5. For `amountIn`, compute `n = floor(amountIn * priceInLower / inputScale)`
   and `available = floor(n * (1e6-spread) / 1e6)`.
   Set `linear = sign(g) * floor(n * abs(g) / 5e17)` and
   `delta = trunc(n*n*v / 1e27) + linear`.
   The inventory charge is `penalty = floor(max(delta,0) * lambdaQ / 1e6)`.
6. Read `r = volumeRateUnits[inputToken]` and charge
   `volumeCost = ceil(r * n*n / 1e27)` USD-wad. This term is outside the
   positive-risk clamp and applies to every maker swap, including same-category
   and risk-reducing directions, with or without wrapper friction.
   Its marginal slope in Q36 units is exactly `2 * r * n * 1e9`.

For a sliding endpoint, let `I` be its own actual ERC-20 inventory in USD-wad
using the lower price, and let `T = categoryTargetMicroUSD * 1e12`.
The input coefficient is `kIn = ceil(coefficientWad * 1e36 / T)`.
The output coefficient is
`kOut = floor(coefficientWad * refundPermille * 1e36 / (T*1000))`.
Wrapper inventory does not include native MON. The coefficient already encodes
configured target friction divided by target weight.

Entry cost is zero for no friction,
`ceil(n * fixedRateWad / 1e18)` for fixed friction, or
`ceil(kIn * n * (2*I+n) / (2e54))` for sliding friction.
If inventory penalty, volume cost or entry cost exhausts available funds, output
is zero. Otherwise `budget = available - penalty - volumeCost - entry`.
The volume integral starts at zero for each swap. Splitting a trade reduces this
term; no transaction history or rolling-volume accumulator is maintained. The
stateful inventory and sliding-wrapper potentials retain their own integration
properties. `MakerSwapExecuted.inventoryPenaltyUsdWad` still reports the inventory penalty;
volume cost is a separate component in the exact quote model.

For no output friction, `outputUSD=budget`. For fixed output friction,
`outputUSD=floor(budget*1e18/(1e18+fixedRateWad))`.
For sliding output friction, solve the largest admitted integer `y` satisfying
`y - floor(kOut * z * (2*I-z) / (2e54)) <= budget`, where `z=min(y,I)`:

- Require `kOut == 0` or `kOut*I < 1e54`; this is the positive marginal-value
  domain of the invertible curve. If `kOut==0`, use `budget`.
- Let `credit=floor(kOut*I*I/(2e54))`. If `budget >= I-credit`, use
  `outputUSD=budget+credit`.
- Otherwise set `b=1e54-kOut*I`, and compute the **ceiling** integer square root
  of `b*b+2e54*kOut*budget` without discarding the high bits of the discriminant.
  The initial output is `floor(2e54*budget/(b+root))`. Test the adjacent integer
  against the exact integral and increment once if it also fits. The Solidity
  implementation uses exact 512-bit division for the root.

Finally `amountOut=floor(outputUSD * outputScale / priceOutUpper)`.
Do not round a wrapper credit upward. Output must fit the live ERC-20 balance.
The arithmetic input limit is derived from the signed quadratic range. Public
quotes also apply the inventory rules below after computing exact output.

The exit credit can pay above oracle fair value. That is the configured
inventory-reduction incentive, not an unconditional mark-to-oracle profit
guarantee.

## Exact output, marginal prices and settlement

The exact-output solver evaluates the same integer curve. It brackets the
requested output, checks the rising-branch peak if marginal remaining budget
reaches zero, then bisects for the **smallest raw input** attaining the output.
The exact solver below reproduces the deployed `solveExactOutput`; a rounded
inverse fair price or a floating-point quadratic does not guarantee minimum input.

### Exact marginal calculation

All products and additions below are checked 256-bit operations unless written
as `mulDiv`. `mulDiv(a,b,d)` uses a full-width product and rounds down;
`mulDivUp` rounds up. Signed divisions truncate toward zero.

```text
penaltySlopeWad(n):
    if lambdaQ == 0: return 0
    delta = trunc(n*n*v / 1e27) + sign(g)*mulDiv(n,abs(g),5e17)
    slope = trunc((trunc(2*n*v / 1e9) + 2*g) * lambdaQ / 1e6)
    if (delta > 0 or (delta == 0 and slope > 0)) and slope > 0:
        return slope
    return 0

remainingSlopeQ36(amountIn):
    n = mulDiv(amountIn, priceInLower, inputScale)
    base = mulDiv(1e6-spread, 1e36, 1e6)
    cost = penaltySlopeWad(n)*1e18 + entryFixedRateWad*1e18
    cost += volumeRateUnits*n*2e9
    cost += mulDivUp(entrySlopeQ36, entryInventoryUSD+n, 1e18)
    return base-cost if cost < base else 0

marginal(amountIn):
    require amountIn <= inputLimit
    numerator = remainingSlopeQ36(amountIn)
    if numerator == 0: return (0,1)
    q = quoteCurve(amountIn, applyFriction=false)
    outputUSD = mulDiv(q.amountOut, priceOutUpper, outputScale)
    denominator = 1e36 + exitFixedRateWad*1e18
    if exitSlopeQ36 != 0 and outputUSD < exitInventoryUSD:
        refund = mulDiv(exitSlopeQ36, exitInventoryUSD-outputUSD, 1e18)
        require refund < 1e36
        denominator -= refund
    fairRate = mulDiv(priceInLower, 1e36, priceOutUpper)
    numerator = mulDiv(fairRate, numerator, denominator)
    denominator = 1e36*(inputScale/outputScale) if inputScale >= outputScale
                  else 1e36/(outputScale/inputScale)
    return (0,1) if numerator == 0 else (numerator,denominator)
```

`quoteCurve` means the arithmetic curve above, including possible zero output;
it does not apply the direct maker endpoint's positive-input/output requirement.
Public `price()` first applies output capacity and the 90% quote caps to the
forward quote at every requested input, including zero, then returns these
fractions. The quotient for `outputUSD` uses the rounded raw output, not the
unrounded intermediate output budget.

### Exact-output search

Use the same friction flag for every forward-curve evaluation below. `maxInput`
is the arithmetic `inputLimit`, not the read-only sell limit or a local buffer.
The contract checks actual settlement caps only after finding the input.

```text
solveExactOutput(target, applyFriction):
    if target == 0: return 0
    targetUSD = mulDivUp(target, priceOutUpper, outputScale)
    high = min(maxInput, max(1, mulDivUp(targetUSD,inputScale,priceInLower)))
    low = 0
    q = quoteCurve(high,applyFriction)
    while q.amountOut < target:
        if remainingSlopeQ36(high) == 0:
            a,b = low,high
            while b-a > 1:
                mid = a+(b-a)/2
                if remainingSlopeQ36(mid) == 0: b=mid
                else: a=mid
            qa,qb = quoteCurve(a,applyFriction),quoteCurve(b,applyFriction)
            high,q = (b,qb) if qb.amountOut > qa.amountOut else (a,qa)
            require q.amountOut >= target
            break
        require high != maxInput
        low = high
        high = maxInput if high > maxInput/2 else high*2
        q = quoteCurve(high,applyFriction)
    while high-low > 1:
        mid = low+(high-low)/2
        candidate = quoteCurve(mid,applyFriction)
        if candidate.amountOut >= target: high,q = mid,candidate
        else: low=mid
    return high
```

Before this search, require the requested output to fit the actual output-token
balance. For nonzero targets, settle the returned input and **exactly** the
requested output, then test the full receiving-token and category caps. A
zero ERC-7815 `Buy` or `Sell` transfers nothing; direct `makerSwapExactInput`
rejects zero input. The direct maker quote also rejects zero output, while
`price()` may validly return `(0,1)` for an exhausted marginal curve.

Marginal prices use `remainingSlopeQ36` and `penaltySlopeWad`, including the
positive-risk clamp's one-sided derivative and the input volume slope above. They divide by the remaining
output marginal value (including the wrapper refund) and convert token units
with the endpoint price ratio. `marginalPrice` returns an integer fraction;
copy its operation and rounding order for bit-exact results. `HardLimits` is
not advertised: every pair has positive volume curvature. The sell limit is
bounded by the arithmetic range and receiving-token quote cap, and is zero
when no output inventory is available. The independent buy limit is the actual
output balance. These are upper bounds; the exact quote still enforces category
caps and the nonlinear curve. `priceDerivative` and
`swapToPrice` remain `NotImplemented` and are not advertised capabilities.

Quote functions report the ordinary curve. Execution applies the existing
10 bp widening once when gas price exceeds twice base fee or the FastLane
auction is already warm: `floor(ordinaryAmountOut * 9990 / 10000)`, after the
integer output conversion and before integrator fees. Exact-output execution
incorporates that widening inside its minimum-input solve. Integrator fees are deducted from output
before the caller's minimum-output check. A simulation must reproduce the
call's transaction/account-warmth context as well as its state.

The final contract call is authoritative. A mirror's exactness depends on its
complete state and transaction context; matching a quote at an earlier block
does not guarantee the same output at inclusion.

## Inventory admission and final settlement

For the input wrapper, use its raw ERC-20 balance after receiving `amountIn`.
For its category, sum `floor(held[t] * priceLower[t] / 10^decimals[t])` over
every registered wrapper in that category. Include native MON in WMON's
category holdings. Use gross physical holdings: debt, target offsets and
lending collateral do not subtract from these caps. For a same-category
trade, subtract the actual raw output payout from its wrapper before valuing
the category. This applies equally to a one-token category.

`makerQuoteExactInput` and ERC-7815 `price` require both
projected holdings to be strictly below 90% of the decoded cap. For an integer
cap `C > 0`, the maximum admitted integer holding is
`ceil(C * 90 / 100) - 1`; a zero cap admits no positive inventory. Use full
precision multiplication/division, including for `uint256.max`. Failure uses
`maker: balance`, matching an output-inventory shortage. The 10% constant is
part of quote admission only; it is not a reservation or a guarantee that a
later swap will succeed. The Rust `quote_exact_input` and Kyber `State.QuoteExactInput` entry points
apply this same check; their underlying arithmetic curves remain independent
of holdings admission.

All maker settlement entry points check both **full** receiving-inventory caps
using fresh balances after input collection, recipient payment, integrator fee
payment and callbacks. Equality with the full cap is allowed. Either exceeded
cap reverts with `maker: balance` and rolls the entire swap back. Executable
ERC-7815 swaps, including `eth_call` simulation of those swaps, use this final
full-cap rule. Taker execution does not run these checks. An unrelated or
outgoing wrapper already above its cap does not prevent selling it down.

A cap publication, price move or taker fill can make existing holdings exceed a
quote or settlement threshold. Caps are not automatically raised or recomputed;
the next receiving trade is assessed against its actual final holdings.
