# ThogAMM exact quote reference

This is the pending **schema 8 / wire 8 / model 3** numeric reference. For onboarding,
see the [integration guide](THOGAMM_AGGREGATOR_INTEGRATION.md). The
[shared Rust model](https://github.com/thogard785/thog-amm-poll-sdk/tree/codex/dynamic-maker-defense/model)
is the executable reference for the pending SDK 0.5.0. Verify the pool's model
identity before selecting an SDK; this change does not deploy model 3.
Floating-point approximations cannot reproduce exact integer execution.

The public quote, swap and ERC-7815 selectors and return shapes are unchanged.
The old packed mirror getters are removed. `getPoolData(uint8,uint8)` retains its selector
and retains the v7 tuple shape; its schema, field offsets and inventory semantics change. Use the current ABI. An integration that only
calls the unchanged quote functions does not need to implement these internals.

For a complete bootstrap, subscription and recovery procedure, start with the
[aggregator onboarding guide](THOGAMM_AGGREGATOR_INTEGRATION.md#build-the-schema-8-model-in-memory)
and [registry/metadata guide](THOGAMM_AGGREGATOR_INTEGRATION.md). This specification
supplies the exact numeric and wire rules used by that model.

Storage uses `1 << 255` as a nonzero encoding for empty words. Inventory
words 107–120 use the separate bitmap in slot 121: bit `wordSlot-107` equal
to one means the decoded inventory word is zero. A zero bitmap bit means
read the physical word verbatim, including `1 << 255`. For other slots,
the complete word `1 << 255` decodes to zero. This preserves all 128 bits
of both balances. `getPoolData` already returns decoded logical words.
Do not apply physical-marker decoding to its returned values.

## Snapshot and event synchronization

1. Call `getPoolData(0, 28)` at one pinned block hash. Check `schemaVersion == 8`,
   active counts in `1..28`, and the registry metadata. Decode the returned
   `StorageWord[]` by its explicit slot numbers. Verify layout 8, wire 8 and model 3
   in slot 8 bits 160–215, and require its registry generation to be nonzero. Quote words are slots 2–127. `portfolioBalances` contains **all** registered token balances even
   if metadata pagination is used. `nativeBalance` is separate. Bind the returned
   block number and parent hash to the selected RPC header; the parent hash is
   not the current block hash.
2. Keep policy, prices, native balance, physical token balances and accounted
   token balances at the same block and transaction position. Accounted balances
   are the `uint128` fields in words 107–120. `portfolioBalances` supplies physical
   balances used to preview the two endpoints' reconciliation. A policy event
   alone does not update either balance set.
   Transfers, taker execution, owner transfers, loans and native bid payments
   can change a quote without a maker swap. A reader without a complete
   balance-event mirror must obtain another atomic snapshot or call the quote.
3. `MakerPageUpdated(uint8 indexed lane, bytes payload, uint256 control)` supplies
   the exact included payload and resulting control word. Lanes are price=1,
   risk=2, wrapper=4, inventory caps=8. Apply in block/log order, modify only that
   lane's fields, and verify the resulting control against the event. A
   disagreement requires an authoritative snapshot; it is not permission to
   substitute locally desired policy.
4. `MakerLendingExposureUpdated(uint8 indexed venue, uint8 indexed category,
   uint32 sequence, int64 offset)` supplies the absolute category offset and
   lending sequence after a borrow/repay. Venue 0 is Neverland; 1 is Euler.
   Replace the category's signed low 64 bits and slot 7 bits 160–191. The sequence advances
   by one per lending operation. A gap requires a snapshot. Cash movement and
   this update belong to the same transaction.
5. `MakerTokenAdded` and `MakerTokenRetired` change the registry generation and may change its geometry. Discard a model for the old
   shape and rebuild it from a complete snapshot with the new configuration.
   `MakerTokenAdded` has the expanded bid/ask, volume-rate and inventory-cap
   metadata tuple; derive its signature from the current ABI.
   It does not carry new covariance/pair rows, so the listing event alone cannot
   reconstruct the expanded page. The bot's publisher deliberately requires
   restart to bind that configuration.
6. On a reorg, discard affected event positions and reload the replacement
   fork. A snapshot covers events through its block. Older events may still
   resolve submission/landing attribution but must not rewind canonical state.
7. `Paused(bool)` sets maker pause bit 132. Apply ERC-20 and WMON balance
   movements exactly once, with `MakerWmonBalanceCheckpoint` and
   `NativeBalanceCheckpoint` as absolute replacements at their log positions.
   `MakerSwapExecuted.amountOut` is the actual output debit, including fees
   (a self-payment contributes zero); when consuming transfers,
   do not also apply swap/fee accounting events as balance deltas.
   `MakerInventoryUpdated(uint8 indexed index, address indexed token, uint128 balance)`
   replaces the accounted units absolutely (shares for xStocks); verify its index/address binding.
   Recompute the corresponding slot-121 zero bit if maintaining exact word parity.
   For ordinary tokens, `Transfer` changes physical balances only. For xStocks,
   apply `TransferShares` to physical shares and ignore the accompanying nominal
   `Transfer`. Refresh the issuer multiplier at each published block even without
   logs, since scheduled activations need no transaction. Never apply a swap
   delta to the accounted ledger in addition to its absolute checkpoint.
   `MakerWrapperCostApplied` is accounting only. Complete the transaction before
   publishing a quote state, especially for loans and wrap/unwrap operations.
8. Forced native transfers and nonstandard token balance changes can lack logs.
   Obtain execution/account-state changes or an atomic snapshot where needed;
   ordinary event subscriptions alone cannot guarantee those balances.
   Advance the quote block even when a block has no relevant events.

The old `MakerPriceStateUpdated`, `MakerPricesPushed`, risk-state/params events
and packed category-inventory events remain removed. The new per-wrapper
`MakerInventoryUpdated(uint8,address,uint128)` has its own ABI signature and
must not be decoded as a historical packed-inventory event. `MakerStorageUpdated` remains declared
for historical decoding but is not emitted in v8. See the
[event migration table](THOGAMM_AGGREGATOR_INTEGRATION.md#event-changes-from-the-previous-integration-guide)
for the exact old-to-new mapping. A schema change requires the corresponding ABI
and model; do not decode schema 8 with the retired packed snapshots.

Before quote execution, the version must be 8, maker pause must be false,
prices must be enabled, structural and wrapper readiness must be set. Both endpoint sides must be enabled.
The posting block must be nonzero and no later than the quote block, with age
at most `maxAge`. Identical/unknown endpoints are rejected.

## Word addressing

Words use ordinary 32-byte big-endian ABI serialization. Offsets below count
bits from the least significant bit. Signed packed fields use two's complement.
Every unused tail field in a publication must be zero. Token addresses are
compiled constants and must be taken from the same atomic snapshot’s complete
`tokens` metadata, rather than decoded from storage words. Three 75-bit records
share each token word; bits 225–255 are reserved.

| Slot/field | Encoding |
| --- | --- |
| 2 bits 0–7 | Physical layout version (8) |
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
| 19, offset `6*catalogId`, width 6 | Active token index + 1; zero means inactive |
| `20+i/4`, field `i%4` of 64 bits | Encoded price |
| `27+c/3`, field `c%3` of 85 bits | External/target offset `int64`, category width `uint16`, anchor token index `uint5` |
| `37+j/16`, field `j%16` of 16 bits | Signed covariance coefficient, scaled by `1e9` |
| `63+j/16`, field `j%16` of 16 bits | Unordered pair width, 0.01 bp units |
| `87+i/4`, field `i%4` of 64 bits | Wrapper coefficient, scaled by `1e18` |
| `94+c/4`, field `c%4` of 64 bits | Category target USD, scaled by `1e6` |
| 7 bits 160–191 | Lending sequence |
| 8 bits 160–167 / 168–175 / 176–183 | Physical layout / publication wire / quote model identifiers: 8 / 8 / 3 |
| 8 bits 184–215 | Nonzero registry generation |
| `101+i/10`, offset `24*(i%10)` | Token inventory cap in raw ERC-20 units, packed mantissa/shift |
| `104+c/10`, offset `24*(c%10)` | Category inventory cap in USD-wad, packed mantissa/shift |
| `107+i/2`, offset `128*(i%2)` | Accounted units: xStock shares or ordinary raw amounts, unsigned 128-bit |
| 121 bits 0–13 | Inventory zero-encoding bitmap; see above |
| 122–127 | Reserved; logical zero |

Masked writes preserve bits outside their owning fields, including category
and token-policy spare bits. Price, covariance, pair, coefficient and target
publications replace complete array words and require clean unused tails.
A future wire or model revision need not move the physical layout.

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
a numeric cap and never disables a check. Other encodings require `shift <= 240`
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
reserved. Initialization installs fixed packed constants calculated offchain without a
lane-8 event. The v7-to-v8 migration preserves existing caps. Bootstrap both
cases from the snapshot.
See the [defaults and manual workflow](THOGAMM_AGGREGATOR_INTEGRATION.md#quotes-limits-and-settlement).

Wrapper kind 0 is none, 1 fixed, 2 sliding. None requires zero coefficient and
refund. Fixed requires a coefficient below `1e18` and zero refund. Sliding
allows refund at most 1000 and requires a nonzero category target; a zero
coefficient produces zero friction. Configured active sliding policies use a
positive coefficient. Structural publication preserves wrapper
metadata and category USD targets; wrapper publication changes its policy and targets atomically and preserves token widths and learned pair premiums.

## Wrapper inventory and donation timing

Unwrapped xStocks use immutable shares in words 107–120 and inventory events.
Value them at `floor(shares * currentMultiplier / 1e18)` for the selected block.
Read physical `sharesOf` and the current multiplier at the same pin as the page;
never reconstruct shares from rounded `balanceOf`. Each maker transfer changes
accounted shares by `floor(amount * 1e18 / currentMultiplier)` independently,
including separate recipient and fee transfers. Scheduled rebases change the
valuation without writing the ledger. Zero accounted shares value to zero
without a multiplier call. Ordinary token units and events retain their meaning.


For a quote on `i -> o`, form the raw holdings vector `B` by taking the physical
snapshot balance for `i` and `o`, and the stored accounted balance for every
other wrapper, converting xStock accounted shares with the current multiplier. Native MON stays live and is added only when valuing WMON's
category. Use this same vector for covariance risk, wrapper friction, output
capacity and cap checks. View calls preview reconciliation without writing it.

A successful maker settlement first stores the two physical endpoint balances,
then applies the operation's own input receipt and actual output debits, including
integrator fees. Each changed balance emits an absolute checkpoint. Existing
donations enter before pricing and cannot be mistaken for swap proceeds.
Donations during token or fee callbacks remain outside the ledger until that
wrapper's next reconciliation. No post-transfer balance synchronization occurs.

Taker execution assumes no mid-swap donations. Pool legs and WMON wrapping mark
touched wrappers in a transient bitmap. Once all venue callbacks and settlements
finish, each touched wrapper's final physical balance is read and checkpointed
once, including partial-input and intermediate residue. Reverted attempts roll
back their touched-token bits. Owner withdrawals and Neverland/Euler cash
movements update the same ledger; subsequent FastLane bid funding checkpoints
its own WMON debit. Native MON is never stored as a second wrapper balance.
Reverting pool/route probes omit ledger accounting. Temporary flash principal
is never classified as a donation: Balancer funding is repaid inside its unlock,
and V2/V3/V4 flash quotes revert the whole funding frame with their result.
Neither funding path checkpoints the temporarily borrowed balance. The complete
`quoteExecute` simulation still executes settlement accounting before reverting.
Price, risk and wrapper publications cannot overwrite the ledger.

Stored units (xStock shares or ordinary raw amounts) must fit `uint128` whenever admitted or changed; overflow reverts rather
than truncating. This mechanism assumes the listed tokens' supported exact
transfer semantics. Unrelated physical donations do not affect a quote until
that wrapper becomes an endpoint or another tracked operation reconciles it.
There is no persistent category-balance cache: each valuation uses current
prices and each wrapper's own decimals with the rounding below.

## Exact input

Let `floor(a/b)` denote unsigned integer division, `ceil(a/b)` its upward
counterpart, and `trunc(a/b)` signed division toward zero. Products described
with full precision must use mul-div arithmetic, not overflowing uint256
intermediates. The reference implementations specify the arithmetic domain.

For input token `i`, output token `o`, and categories `a`, `b`:

The default age widening is 50 units (0.5 bp) per elapsed block. The publisher
encodes the configured value in the risk lane; models read the stored value.

1. Add both category widths, the input token’s bid width, the output token’s ask width, the learned pair premium, and `age * widening` into `spread`. Require `spread < 1e6`.
2. Set `d[c] = covariance[a,c] - covariance[b,c]` and
   `v = covariance[a,a] + covariance[b,b] - 2*covariance[a,b]`.
3. For each category with `d[c] != 0`, start exposure USD-wad at
   `trunc(externalOffsetMicro[c] * anchorPriceLower[c] / 1e6)`.
   Add `floor(rawBalance[t] * priceLower[t] / 10^decimals[t])` for every
   registered token in that category, using the reconciled vector `B` above. Add native balance to WMON's raw balance
   before valuation. Positive external collateral excluded by policy is not
   silently reintroduced as spendable inventory.
4. Set `g = sum_c trunc(exposureUSD[c] * d[c] / 1e9)`, preserving the
   **per-category** division order. For `a == b`, both `v` and `g` are zero.
   This removes category risk only; volume and wrapper costs below still apply.
5. For an unwrapped xStock, set `inputDust = max(2, ceil(multiplier / 1e18))`;
   for an ordinary token, use zero. Compute
   `n = floor(max(0, amountIn - inputDust) * priceInLower / inputScale)`
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

Finally compute `rawOut = floor(outputUSD * outputScale / priceOutUpper)` and
`outputDust = max(2, ceil(outputMultiplier / 1e18))` for an xStock, zero otherwise.
The read-only output is `max(0, rawOut - outputDust)`. Direct
`makerSwapExactInput` applies any execution widening to this value. ERC-7815
instead applies widening to `rawOut`, then subtracts `outputDust`. Preserve this
order: the two paths can differ by a raw unit. Settlement adds output dust to
any nonzero recipient payment before converting that transfer to shares.
Do not round a wrapper credit upward. The recipient's guaranteed amount can be
smaller than the actual rounded receipt.
The arithmetic input limit is derived from the signed quadratic range. Public
quotes also apply the inventory rules below after computing exact output.

The exit credit can pay above oracle fair value. That is the configured
inventory-reduction incentive, not an unconditional mark-to-oracle profit
guarantee. The same configured policy is used by the taker friction coster.

## Exact output, marginal prices and settlement

The exact-output solver evaluates the same integer curve. It brackets the
requested output, checks the rising-branch peak if marginal remaining budget
reaches zero, then bisects for the **smallest raw input** attaining the output.
The executable reference is `solveExactOutput`; a rounded inverse fair price
or a floating-point quadratic does not guarantee minimum input.
For ERC-7815 Buy, settlement sets the guaranteed output to the requested target,
then adds output dust before transferring an xStock. Actual recipient credit can
exceed that target. The SDK's execution `Quote.amount_out` is this guarantee, not
an exact balance delta: compare `received >= amount_out` under the same state and
execution context. Funding/forwarding transfers outside Thog round independently;
use the caller's measured newly received input and measure the final recipient.

Marginal prices use `remainingSlopeQ36` and `penaltySlopeWad`, including the
positive-risk clamp's one-sided derivative and the input volume slope above. They divide by the remaining
output marginal value (including the wrapper refund) and convert token units
with the endpoint price ratio. `marginalPrice` returns an integer fraction;
copy its operation and rounding order for bit-exact results. `HardLimits` is
not advertised: every pair has positive volume curvature. The sell limit is
bounded by the arithmetic range and receiving-token quote cap, and is zero
when no output inventory is available. The independent buy limit is the actual
output balance minus output dust, floored at zero. These are upper bounds; the exact quote still enforces category
caps and the nonlinear curve. `priceDerivative` and
`swapToPrice` remain `NotImplemented` and are not advertised capabilities.

Quote functions omit execution defense but include stored age widening.

Execution applies a dynamic output reduction. Evaluate the following rows in
order using the transaction's **effective** gas price and the current block's
base fee; every gas-price comparison is strictly greater-than.

| First matching condition | Raw defense | Defense after a valuation update earlier in this block |
| --- | ---: | ---: |
| FastLane AuctionHandler is already warm | 12 bp | 2 bp |
| `gasPrice > 2.5 * baseFee` | 12 bp | 2 bp |
| `gasPrice > 2 * baseFee` | 8 bp | 1 bp |
| `gasPrice > 1.5 * baseFee` | 6 bp | 0.5 bp |
| Otherwise | 0 bp | 0 bp |

The same-block column applies exactly when the latest accepted valuation's
`postedBlock` equals the execution block: `max(rawDefense / 4 - 1 bp, 0)`.
A risk, wrapper, cap or inventory update alone does not qualify. The raw defense
applies when the latest valuation is from an earlier block. Warmth and gas-price
triggers do not stack. With zero base fee, any positive gas price selects 12 bp;
a cold zero-price transaction selects zero. Fractional thresholds are exact,
including odd base fees; implementations compare differences to avoid overflow.

The configured age widening is **0.5 bp per elapsed block** without a valuation
update (`widen_per_block_bps: 0.50`, encoded as 50 in 0.01 bp units). It adds to
the pair's spread and affects both read-only and execution quotes. Execution
defense is a separate multiplicative output reduction, not another age term.

The SDK's default execution methods assume a cold AuctionHandler; the
`*_with_context` methods accept explicit warmth. For EIP-1559, effective gas price
is `min(maxFeePerGas, baseFee + maxPriorityFeePerGas)`. `at_block(number, base_fee)`
sets both age and the block/base-fee context used by this policy; it cannot predict
an intervening valuation publication, trade or inventory change.

Carry the selected defense in **0.01 bp units** (`friction`), with raw values
0/600/800/1200 and same-block values 0/50/100/200. The output factor is
`(1_000_000 - friction) / 1_000_000`. Direct and extra-fee swaps use
`floor(readOnlyAmountOut * (1_000_000 - friction) / 1_000_000)`;
ERC-7815 Sell/Buy use
`max(0, floor(rawOut * (1_000_000 - friction) / 1_000_000) - outputDust)`.
Apply the same factor to ERC-7815's returned marginal-price numerator.
Exact-output execution solves that ERC-7815 curve for minimum input. Its initial
bracket includes both output and input dust; its independent buy limit is
physical output balance minus dust.
Marginal remaining slope uses `max(0, amountIn - inputDust)` for input notional.
Integrator fees are deducted before checking the caller's minimum output, and
each recipient/fee transfer independently floors to shares. Simulate the actual
call with the same state, effective gas price and account warmth.

The final contract call is authoritative. A mirror's exactness depends on its
complete state and transaction context; matching a quote at an earlier block
does not guarantee the same output at inclusion.

## Inventory admission and final settlement

Capture the reconciled holdings vector before transfers. Read-only admission
adds nominal `amountIn` to the input wrapper and uses `amountOut + outputDust`
for nonzero output. Settlement instead computes each share transfer, updates
the starting physical shares, and values the actual input receipt/output debit
from the difference in pre/post amounts. For the input category, sum
`floor(held[t] * priceLower[t] / 10^decimals[t])` over its registered wrappers.
Start from `B`, add the input receipt, and subtract the actual output debit when
the output belongs to the same category. Include live native MON with WMON before
valuation. Debt, target offsets and lending collateral never reduce these gross
holdings. Singleton categories use the same calculation.

For a configured cap `C > 0`, the ordinary quote threshold is
`Q(C) = ceil(C * 90 / 100) - 1`; `Q(0) = 0`. Use full-precision arithmetic,
including for `uint256.max`. Final settlement uses the full configured cap `C`.
The existing 90% quote threshold remains an admission policy, not a reservation.

Reconciliation, a price change, a taker fill or a manual cap reduction can place
existing holdings over a threshold. Preserve that starting balance. For either
quote or settlement, the effective limit is `max(startingHolding, threshold)`;
for the receiving wrapper also clamp it to the nominal value of `uint128.max` stored units. For xStocks this is `floor(uint128.max * currentMultiplier / 1e18)`; for other tokens it is `uint128.max`. Thus an operation may
reduce an existing category excess but cannot increase it. Configured caps do
not change when excess holdings are admitted. The outgoing wrapper's cap never
prevents selling it down.

Maker settlement applies the full-cap check to its captured starting state plus
actual trade deltas after all transfers and fee callbacks complete. A callback
donation does not become a trade receipt or alter the cap baseline. Exceeding
an effective limit reverts with `maker: balance` and rolls back the whole swap.
The Go `QuotePageExactInput` uses the identical endpoint-reconciliation and
quote-threshold rules. ERC-7815 executable swaps and their `eth_call` simulations
use the final full-cap rule. Taker execution does not enforce maker caps.
