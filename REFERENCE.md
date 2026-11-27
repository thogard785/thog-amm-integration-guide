# ThogAMM reference

Everything needed to reproduce ThogAMM's quotes and swaps outside the chain:
what state to read, how it is laid out, the arithmetic, and how to keep the
state current. The [integration guide](THOGAMM_AGGREGATOR_INTEGRATION.md)
explains how to use the pool; this document specifies it.

A working implementation of this document is the
[`model` crate](https://github.com/thogard785/thog-amm-poll-sdk/tree/main/model/src)
of the Rust SDK. Its files follow the sections below: `layout.rs`,
`snapshot.rs`, `curve.rs`, `pool.rs`, `events.rs`.

## Conventions

- All values are integers. `floor(a / b)` and `ceil(a / b)` divide unsigned
  integers. `trunc(a / b)` divides signed integers and rounds toward zero.
- A product inside one division is computed in full before dividing, even
  when it exceeds 256 bits. Where a result does not fit 256 bits, or a
  subtraction would go below zero, the contract reverts.
- **USD** amounts are scaled by `1e18`.
- **Spreads** and the **surcharge** are in units of 0.01 bp: `1,000,000` is 100%.
- Token amounts are raw units. `scale(t) = 10^decimals(t)`.
- Tokens are numbered in listing order from zero. Each token belongs to one
  **category**: a group of tokens that track the same asset, such as USDC,
  AUSD and USDT0. Categories are numbered from zero.
- Bit offsets count from the least significant bit of a 256-bit word.

## Reading a snapshot

A snapshot is the pool's complete state at one block. Read it with a single
`eth_call` to [Multicall3](https://www.multicall3.com)
(`0xcA11bde05977b3631167028862bE2a173976CA11`), `aggregate3`, with these calls:

| Call | Target | May fail |
| --- | --- | --- |
| `getPoolData(0, 28)` | pool | no |
| `storedMultiplier(token)` for each listed token | pool | no |
| `sharesOf(pool)` for each listed token | the token | yes |

`storedMultiplier` returns zero for an ordinary token and the multiplier for an
xStock. Use a token's `sharesOf` result only when its multiplier is nonzero;
ordinary tokens revert or return nothing. The token list comes from
`getTokens(poolId)` or an earlier snapshot. If the tokens in the returned pool
data differ from the list you asked about, read again with the returned list.

Send the `eth_call` with `gasPrice` set, for example `0x1`. Without it a Monad
node reports a base fee of zero, and `baseFeePerGas` in the result is wrong.

`getPoolData` returns:

| Field | Use |
| --- | --- |
| `schemaVersion` | Must be 8. |
| `blockNumber`, `baseFeePerGas`, `parentBlockHash` | The block the snapshot was read at. |
| `tokens[i].token` | The listed tokens in order. The other fields of each entry say where that token's values are stored; they match the [state layout](#state-layout). |
| `balances[i]` | The pool's balance of token `i`. For an xStock this is `floor(shares × multiplier / 1e18)` with the stored multiplier. |
| `nativeBalance` | The pool's native MON balance. |
| `words` | Storage words 2 to 127 as `(slot, value)` pairs. |

Read storage through `getPoolData`, not `eth_getStorageAt`: the contract keeps
empty words in an encoded form that `getPoolData` decodes.

Check the snapshot before using it:

- slot 2 bits 0–7 equal 8, and slot 8 bits 160–183 equal `8 | 8 << 8 | 3 << 16`
  (see [format](#format-and-upgrades));
- the token and category counts in slot 2 match the returned arrays;
- for every xStock, `floor(shares × multiplier / 1e18)` equals its balance.
  A mismatch means the reads came from different blocks.

## State layout

`slot` is the storage word. Arrays pack equal-width fields from the low bits
upward; "`n` per word" means field `k` is at word `first + floor(k / n)`, bit
offset `(k mod n) × width`.

**Slot 2: counts, switches and pool-wide parameters**

| Bits | Field |
| --- | --- |
| 0–7 | Storage layout version: 8 |
| 8–13, 14–19 | Token count, category count |
| 20–35 | Price update counter |
| 36–67 | `priceBlock`: block of the latest price update |
| 68–131 | Two switches per token: bit `68 + 2i` lets token `i` be input, bit `69 + 2i` lets it be output |
| 132 | Paused |
| 133 | Prices enabled |
| 134, 135 | Parameters published: risk, token costs |
| 138–145 | `maxPriceAge` in blocks |
| 146–161 | `spreadPerBlock`, in 0.01 bp |
| 162–193 | `riskAversion`, scaled by 1e6 |

**Other slots**

| Slots | Layout | Field |
| --- | --- | --- |
| 7, bits 160–191 | | Counter of category offset changes |
| 8, bits 160–183 | | Format identifiers; see [format](#format-and-upgrades) |
| 8, bits 184–215 | | Registry generation: increases when a token is listed or retired |
| 9–18 | 75 bits, 3 per word | Token record, below |
| 19 | 6 bits, 32 per word | For each entry of the contract's built-in address table: the token's listing position plus one, or zero if it is not listed |
| 20–26 | 64 bits, 4 per word | Token [price](#prices) |
| 27–36 | 85 bits, 3 per word | Category record, below |
| 37–62 | 16 bits, 16 per word | Covariance between categories `a ≤ b`, signed, scaled by 1e9, at field `b (b + 1) / 2 + a` |
| 63–86 | 16 bits, 16 per word | Extra spread for the token pair `a < b`, at field `b (b − 1) / 2 + a` |
| 87–93 | 64 bits, 4 per word | Token cost coefficient, scaled by 1e18 |
| 94–100 | 64 bits, 4 per word | Category target holding in USD, scaled by 1e6 |
| 101–103 | 24 bits, 10 per word | Token [cap](#caps), raw units |
| 104–106 | 24 bits, 10 per word | Category cap, USD scaled by 1e18 |
| 107–120 | 128 bits, 2 per word | Recorded units per token: raw units, or shares for an xStock |
| 121 | bit `w` | Set while word `107 + w` is zero |
| 122–127 | | The operator's own account configuration. Not a pricing input. |

**Token record** (75 bits)

| Bits | Field |
| --- | --- |
| 0–4 | Index in the contract's built-in address table |
| 5–9, 10–14 | Decimals, category |
| 15–30 | `spreadIn`: spread when the token is input |
| 31–32 | Token cost kind: 0 none, 1 fixed, 2 inventory-based |
| 33–42 | `refund`: share of an inventory-based cost credited on the way out, in 1/1000 |
| 43–58 | `spreadOut`: spread when the token is output |
| 59–74 | `sizeRate`: size charge when the token is input, in 0.01 bp per $1,000 (zero is valid) |

**Category record** (85 bits)

| Bits | Field |
| --- | --- |
| 0–63 | `offset`: signed. A position the operator holds outside the pool, in millionths of the reference token |
| 64–79 | `categorySpread` |
| 80–84 | Reference token: the token whose price values `offset` |

### Prices

A price field holds a mantissa `m` in bits 0–55 and an exponent `e` in bits
56–63. The price of one whole token lies between

```text
priceLow  = m × 10^(18 − e)
priceHigh = (m + 1) × 10^(18 − e)
```

in USD scaled by 1e18. The pool values what it receives and holds at
`priceLow`, and what it pays at `priceHigh`. A field with `m < 2,000,000` or
`e > 18` is not a price; both values are zero.

### Caps

A cap field holds a mantissa in bits 0–15 and a shift in bits 16–23:
`cap = mantissa << shift`. The value `0xffffff` means no cap (`2^256 − 1`).
To encode an amount as the contract does, rounding down: `shift = max(0,
bitLength(amount) − 16)` and `mantissa = amount >> shift`.

### Format and upgrades

Slot 8 bits 160–167, 168–175 and 176–183 identify the storage layout (8), the
format of update payloads (8) and the pricing arithmetic (3). This document
describes exactly that combination. Refuse any other.

The pool is an upgradeable proxy. An upgrade emits `Upgraded(address)` and can
change behaviour without changing the identifiers, so on that event stop
quoting until you have checked the new implementation against your model.

## Balances

A swap from token `i` to token `o` uses one balance per token:

```text
B[t] = actual balance of t          for t = i and t = o
B[t] = recorded balance of t        for every other token
```

The actual balance is `balances[t]` from the snapshot. The recorded balance is
the token's recorded units from slots 107–120: raw units for an ordinary
token, `floor(units × multiplier / 1e18)` for an xStock. The two differ when
tokens reached the pool without a swap.

An xStock's own unit is the share. `units(t, amount) = floor(amount × 1e18 /
multiplier)` and `amount(t, units) = floor(units × multiplier / 1e18)`. For an
ordinary token both are the identity.

An xStock transfer can deliver slightly less than the amount requested. The
pool's allowance for that is

```text
dust(t) = max(2, ceil(multiplier / 1e18))     for an xStock
dust(t) = 0                                   otherwise
```

Where the pool values holdings in USD it counts its native MON as WMON:

```text
usd(t, x) = floor(x × priceLow[t] / scale(t))
held(t)   = B[t] + nativeBalance      if t is WMON
held(t)   = B[t]                      otherwise
```

## Exact-input quote

For input token `i` in category `a`, output token `o` in category `b`, at
block `N`.

**1. Availability.** The quote is refused, in this order, if:

- `i = o`, or either token is not listed;
- the actual units of `i` or `o` exceed `2^128 − 1`;
- the pool is paused or prices are not enabled;
- either "parameters published" bit is clear;
- `i` is switched off as input, or `o` as output;
- `priceBlock` is zero or above `N`, `maxPriceAge` is zero, or
  `N − priceBlock > maxPriceAge`;
- `priceLow[i]` or `priceHigh[o]` is zero.

**2. Spread.**

```text
spread = spreadIn[i] + spreadOut[o] + categorySpread[a] + categorySpread[b]
       + pairSpread[i, o] + (N − priceBlock) × spreadPerBlock
```

Refused if `spread ≥ 1,000,000`.

**3. Value in.**

```text
n      = floor(max(0, amountIn − dust(i)) × priceLow[i] / scale(i))
budget = floor(n × (1,000,000 − spread) / 1,000,000)
```

If `n = 0` the output is zero.

**4. Risk charge.** Zero when `riskAversion = 0` or `a = b`. Otherwise, with
`cov` the covariance matrix:

```text
v    = cov[a][a] + cov[b][b] − 2 × cov[a][b]
d[c] = cov[a][c] − cov[b][c]                              for each category c

E[c] = trunc(offset[c] × priceLow[reference token of c] / 1,000,000)
     + Σ usd(t, held(t))  over tokens t in category c       where d[c] ≠ 0

g      = Σ trunc(E[c] × d[c] / 1e9)                        over categories with d[c] ≠ 0
change = trunc(n × n × v / 1e27) + sign(g) × floor(n × |g| / 5e17)
risk   = floor(change × riskAversion / 1,000,000)          if change > 0, else 0
```

Each `usd(t, held(t))` must be at most `2^128 − 1`.

**5. Size charge.**

```text
size = ceil(n × n × sizeRate[i] / 1e27)
```

**6. Cost of the input token.** By the token cost kind of `i`:

```text
none              entry = 0
fixed             entry = ceil(n × coefficient[i] / 1e18)
inventory-based   entry = ceil(k × n × (2 × I + n) / 2e54)
                  k = ceil(coefficient[i] × 1e36 / T)
```

where `T = categoryTarget[a] × 1e12` must be nonzero and `I = usd(i, B[i])`,
without native MON, must be at most `2^128 − 1`.

**7. Deduct.** Subtract `risk`, then `size`, then `entry` from `budget`. If any
of them is greater than or equal to what remains, the output is zero.

**8. Cost of the output token.** By the token cost kind of `o`, the USD value
`y` paid out:

```text
none              y = budget
fixed             y = floor(budget × 1e18 / (1e18 + coefficient[o]))
inventory-based   the largest y with  y − credit(y) ≤ budget
```

For the inventory-based kind, with `T = categoryTarget[b] × 1e12` nonzero,
`I = usd(o, B[o])` and `k = floor(coefficient[o] × refund[o] × 1e36 / (T ×
1000))`:

```text
credit(y) = floor(k × z × (2 × I − z) / 2e54),   z = min(y, I)
```

It is refused if `k ≠ 0` and `I > floor((1e54 − 1) / k)`. Compute `y` as:

```text
if k = 0:                 y = budget
full = floor(k × I × I / 2e54)
if budget ≥ I − full:     y = budget + full
otherwise:
    b = 1e54 − k × I
    r = ceil(sqrt(b × b + 2e54 × k × budget))
    y = floor(2e54 × budget / (b + r))
    if (y + 1) − floor(k × (y + 1) × (2 × I − (y + 1)) / 2e54) ≤ budget:  y = y + 1
```

**9. Amount out.**

```text
rawOut = floor(y × scale(o) / priceHigh[o])
quoted = max(0, rawOut − dust(o))
```

`makerQuoteExactInput` returns `(quoted, priceBlock)`. It reverts if `amountIn`
is zero, if `amountIn > maxAmountIn`, if `quoted` is zero, or if the swap fails
the [inventory check](#inventory-check) at the quote threshold with `received =
amountIn` and `paid = quoted + dust(o)`.

```text
maxAmountIn = ceil((664619068552888026590626425199190042 + 1) × scale(i) / priceLow[i]) − 1
```

## Inventory check

Given `received` of token `i` and `paid` of token `o`:

```text
threshold(C) = C                               at settlement
threshold(C) = ceil(C × 90 / 100) − 1          for a quote, when C > 0; else 0

unitsMax    = amount(i, 2^128 − 1)
tokenLimit  = min(unitsMax, max(B[i], threshold(tokenCap[i])))
```

Refused unless `paid ≤ B[o]`, `B[i] ≤ tokenLimit` and `received ≤ tokenLimit −
B[i]`. Then, over the tokens `t` of the input token's category `a`:

```text
value(r, p) = Σ usd(t, h[t]),   h[t] = held(t), plus r for t = i, minus p for t = o
```

Refused unless `value(received, paid) ≤ max(threshold(categoryCap[a]),
value(0, 0))`. A holding that is already above a cap can shrink but not grow.

## Settlement

**Execution surcharge.** With `gasPrice` the transaction's effective gas
price, `baseFee` the block's base fee, and `tip = gasPrice − baseFee` when
`gasPrice > baseFee`:

```text
s = 1200    if the AuctionHandler is warm
else s = 1200   if tip > baseFee and tip − baseFee > floor(baseFee / 2)
else s = 800    if tip > baseFee
else s = 600    if tip > floor(baseFee / 2)
else s = 0

if priceBlock = N and s ≠ 0:   s = s / 4 − 100

cut(x) = floor(x × (1,000,000 − s) / 1,000,000)
```

The AuctionHandler (`0xD32EdF6642D917DbBE7B8BF8e5d6F5df6a9FFF58`) is warm if
the transaction called it earlier or names it in its
[access list](https://eips.ethereum.org/EIPS/eip-2930). The pool decides this
once per transaction, at its first swap, by checking that an empty call to the
AuctionHandler costs less than Monad's
[cold-access cost](https://docs.monad.xyz/developer-essentials/opcode-pricing#cold-access-cost)
of 10,100 gas. Every later swap in the transaction uses the same answer.

**The four swaps.** `quoted` and `rawOut` are from the [exact-input
quote](#exact-input-quote) evaluated at the block the swap executes in.

| Call | Output | Reverts if |
| --- | --- | --- |
| `makerSwapExactInput` | `out = cut(quoted)` | `out = 0`, `out < minAmountOut`, past `deadlineBlock` |
| `swapWithExtraFees` | `gross = cut(quoted)`, `fee = floor(gross × extraFeePpm / 1,000,000)`, `out = gross − fee` | `gross = 0`, `out < minAmountOut`, past `expiry`, `extraFeePpm > 1,000,000` |
| ERC-7815 `swap`, sell | `out = max(0, cut(rawOut) − dust(o))` | `out = 0` |
| ERC-7815 `swap`, buy | `out = target`; input is found by the [search](#exact-output) | `target > B[o] − dust(o)`, or no input reaches it |

The two ERC-7815 swaps take the surcharge before removing `dust(o)`; the other
two take it after. For an xStock output the results can differ by a raw unit.
An ERC-7815 swap of zero succeeds and moves nothing.

**Transfers.** The pool pulls `amountIn` from the caller. If `out > 0` it sends
`out + dust(o)` to the recipient. If `fee > 0` it calls the fee contract and
sends it `fee`. Each transfer moves `units(t, amount)` of its token, rounded
down on its own:

```text
toRecipient = out + dust(o)   if out > 0, else 0
unitsIn'    = unitsIn  + units(i, amountIn)
unitsOut'   = unitsOut − units(o, toRecipient) − units(o, fee)
received    = amount(i, unitsIn')  − B[i]
paid        = B[o] − amount(o, unitsOut')
```

where `unitsIn` and `unitsOut` are the actual units before the swap. `out` is
zero only in a `swapWithExtraFees` with `extraFeePpm = 1,000,000`: the whole
output is the fee, and `dust(o)` stays in the pool.

The swap reverts if `unitsIn' > 2^128 − 1`, or if it fails the [inventory
check](#inventory-check) at the settlement threshold with `received` and
`paid`. For an xStock the pool also checks that the token moved exactly the
shares computed here, and reverts with `xstock: multiplier stale` otherwise.

**State afterwards.** For both tokens the actual units and the recorded units
equal `unitsIn'` and `unitsOut'`. Nothing else changes. To quote a second swap
of the same route, apply this change first.

An ERC-7815 swap of zero returns before all of this. It transfers nothing and
leaves the recorded units as they were, even where they differ from the actual
units.

## Exact output

ERC-7815 `swap` with the buy side returns the input found by this search, where
`sell(x) = max(0, cut(rawOut(x)) − dust(o))`:

```text
targetUsd = ceil((target + dust(o)) × priceHigh[o] / scale(o))
high = min(maxAmountIn, max(1, ceil(targetUsd × scale(i) / priceLow[i]) + dust(i)))
low  = 0

while sell(high) < target:
    if marginalBudget(high) = 0:
        find adjacent x, x + 1 in [low, high] by bisection with
            marginalBudget(x) > 0 and marginalBudget(x + 1) = 0
        high = x + 1 if sell(x + 1) > sell(x), else x
        revert if sell(high) < target
        stop this loop
    revert if high = maxAmountIn
    low  = high
    high = maxAmountIn if high > floor(maxAmountIn / 2), else 2 × high

while high − low > 1:
    mid = low + floor((high − low) / 2)
    if sell(mid) ≥ target: high = mid   else: low = mid

amountIn = high
```

Both bisections start from the `low` and `high` in hand and halve the interval
with `mid = low + floor((high − low) / 2)`.

## Marginal price and limits

`marginalBudget(x)` is the USD that one more unit of input value adds to the
budget, scaled by 1e36. With `n` from step 3 for `amountIn = x`:

```text
slope     = trunc((trunc(2 × n × v / 1e9) + 2 × g) × riskAversion / 1,000,000)
riskSlope = slope   if change ≥ 0 and slope > 0, else 0       (0 if risk is not charged)

cost = riskSlope × 1e18
     + coefficient[i] × 1e18                                   (fixed input cost only)
     + sizeRate[i] × n × 2e9
     + ceil(k × (I + n) / 1e18)                                (inventory-based input cost only)

marginalBudget(x) = max(0, floor((1,000,000 − spread) × 1e36 / 1,000,000) − cost)
```

ERC-7815 `price` returns, for each amount `x`:

```text
revert if x > maxAmountIn, or if the quote of x fails the inventory check
m = marginalBudget(x);  if m = 0 the price is 0 / 1
outUsd = floor(quoted(x) × priceHigh[o] / scale(o))
den    = 1e36 + coefficient[o] × 1e18                          (fixed output cost only)
den    = den − floor(k × (I − outUsd) / 1e18)                  (inventory-based output cost, when outUsd < I)
numerator   = floor(floor(priceLow[i] × 1e36 / priceHigh[o]) × m / den)
denominator = 1e36 × scale(i) / scale(o)     if scale(i) ≥ scale(o)
            = 1e36 / (scale(o) / scale(i))   otherwise
```

A zero numerator is returned as `0 / 1`. `swap` returns the same fraction for
the amount it traded, with the numerator passed through `cut`.

ERC-7815 `getLimits` returns `[sellLimit, buyLimit]`:

```text
L         = min(unitsMax, threshold(tokenCap[i]))     with the quote threshold
sellLimit = min(maxAmountIn, L − B[i])                if B[o] > 0 and B[i] < L, else 0
buyLimit  = max(0, B[o] − dust(o))
```

## Keeping state current from events

Every change to the state above emits a log. Collect, for each block, all logs
matching these four filters:

| Filter | Carries |
| --- | --- |
| address = pool | Everything the pool emits |
| topic 0 ∈ {`Transfer`, `TransferShares`}, topic 1 = pool | Tokens leaving the pool |
| topic 0 ∈ {`Transfer`, `TransferShares`}, topic 2 = pool | Tokens reaching the pool |
| address = WMON, topic 0 ∈ {`Deposit`, `Withdrawal`}, topic 1 = pool | The pool wrapping and unwrapping MON |

Apply a block's logs in order of transaction index, then log index. Apply only
blocks that are final and whose logs you hold completely. Advance the model's
block number for every block, including blocks without logs: price age depends
on it.

| Event | From | Effect |
| --- | --- | --- |
| `MakerPageUpdated(lane, payload, control)` | pool | A parameter or price update; see [update payloads](#update-payloads). |
| `MakerInventoryUpdated(index, token, balance)` | pool | Recorded units of token `index` become `balance`. Then set bit `w` of slot 121 if word `107 + w` is now zero, and clear it otherwise. |
| `MakerLendingExposureUpdated(venue, category, sequence, offset)` | pool | The category's `offset` becomes `offset`. `sequence` must be one above slot 7 bits 160–191, and replaces it. |
| `MakerMultiplierUpdated(token, multiplier)` | pool | The stored multiplier of `token` becomes `multiplier`. Ignore it for a token that is not listed. |
| `MakerWmonBalanceCheckpoint(balance)` | pool | The actual WMON balance becomes `balance`. |
| `NativeBalanceCheckpoint(balance)` | pool | `nativeBalance` becomes `balance`. |
| `Paused(paused)` | pool | Slot 2 bit 132 becomes `paused`. |
| `Transfer(from, to, value)` | an ordinary token | Actual balance plus `value` if `to` is the pool, minus `value` if `from` is. |
| `TransferShares(from, to, value)` | an xStock | Actual shares plus `value` if `to` is the pool, minus `value` if `from` is. |
| `Deposit(dst, wad)`, `Withdrawal(src, wad)` | WMON | Actual WMON balance plus `wad` if `dst` is the pool; minus `wad` if `src` is. |
| `MakerTokenAdded`, `MakerTokenRetired` | pool | The token list changed. Read a new snapshot. |
| `Upgraded(implementation)` | pool | See [format and upgrades](#format-and-upgrades). |

An xStock emits both `Transfer` and `TransferShares` for one movement. Apply
only `TransferShares`, then, at the end of the block, set each xStock's balance
to `floor(shares × multiplier / 1e18)`. A transfer from the pool to itself
changes nothing. Other pool events, such as `MakerSwapExecuted`, describe
changes the events above already carry; applying them too would count a swap
twice.

Native MON can be forced into the pool without a log. The model's native
balance is then too low until the pool next emits `NativeBalanceCheckpoint`.
Read a new snapshot from time to time, and whenever a log does not fit the
state you hold.

### Update payloads

`MakerPageUpdated.payload` is a sequence of 32-byte big-endian words: a header
followed by the new values, packed as in storage. `lane` says which kind. After
applying an update, slot 2 must equal `control`; if it does not, read a new
snapshot.

Every header repeats the token count, the category count and the registry
generation it was built for; they must match the state.

**Lane 1: prices.** Header: counter in bits 0–15, prices enabled in bit 16, the
64 token switches in bits 17–80, token count in 81–88, the value 8 in 89–96,
registry generation in 97–128. Then `ceil(tokens / 4)` words that replace the
price words from slot 20. Set the price update counter, the enabled bit and the
switches from the header, and `priceBlock` to the block of the event.

**Lane 2: risk.** Header: the value 8 in bits 0–7, token count in 8–15,
category count in 16–23, `riskAversion` in 24–55, `maxPriceAge` in 56–63,
`spreadPerBlock` in 64–79, zero in 80–111, the offset counter (slot 7 bits
160–191) in 112–143, registry generation in 144–175. Then, in order:

- `ceil(categories / 3)` words of category records, each replacing bits 0–254
  of its word from slot 27 (bits 0–84 for slot 36);
- `ceil(categories × (categories + 1) / 32)` words replacing the covariance
  words from slot 37;
- `ceil(tokens / 5)` words of 48-bit entries, five per word: `spreadIn` in bits
  0–15, `spreadOut` in 16–31, `sizeRate` in 32–47, each replacing that field of
  its token record;
- `ceil(tokens × (tokens − 1) / 32)` words replacing the pair spread words from
  slot 63.

Set `riskAversion`, `maxPriceAge` and `spreadPerBlock` from the header and set
bit 134.

**Lane 4: token costs.** Header: the value 8 in bits 0–7, token count in 8–15,
category count in 16–23, zero in 24–31, registry generation in 32–63. Then
`ceil(tokens / 3)` words of 76-bit entries, three per word: coefficient in bits
0–63, kind in 64–65, `refund` in 66–75. Each replaces its token's coefficient
and the kind and `refund` fields of its token record. Then `ceil(categories /
4)` words replacing the category target words from slot 94. Set bit 135.

**Lane 8: caps.** The payload is the ABI encoding of `(address[] tokens,
uint256[] tokenCaps, uint8[] categories, uint256[] categoryCaps)`. Store each
named cap in its [encoded form](#caps); the others keep their values.
