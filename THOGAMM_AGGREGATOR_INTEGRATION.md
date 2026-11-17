# Integrate ThogAMM into an aggregator

ThogAMM is a market-maker pool on Monad. It holds an inventory of tokens and
swaps any listed token for any other at prices its operator posts on-chain.

This guide shows how to quote and swap, and how to reproduce the pool's quotes
in your own router. It assumes you know the EVM and how aggregators work, and
nothing about ThogAMM.

## How ThogAMM differs from other pools

- **One pool, every pair.** All listed tokens share one inventory. There are
  no per-pair pools and no LP tokens.
- **Prices are posted, not derived from reserves.** The operator posts a USD
  price for every token, normally every block. A swap pays the posted price
  less spreads and charges.
- **Posted prices expire.** A quote gets slightly worse with every block since
  the last price update, and after a set number of blocks the pool refuses to
  trade until prices are updated. See [price age](#price-age).
- **A quote depends on the whole inventory.** The pool charges for the risk a
  swap adds to its portfolio, so a trade in one pair can move the quote of
  another.
- **Execution can pay less than the quote.** A swap sent with a high priority
  fee receives less. See [execution surcharge](#execution-surcharge).
- **Some tokens are xStocks**, whose balances are kept in shares. Transfers of
  them round. See [xStocks](#xstocks).

## The pool

| | |
| --- | --- |
| Network | Monad mainnet, chain ID **143** |
| Pool contract | `0x80c74517BCC2D67fFE02D3ED886796272F647210` |
| Pool ID | `0xce389e78282dedac7b18ba7f775b7602d2ab3ab171bbd6711eb0239be6ef4dcc` |
| Implementation | `0xb108a1daf3c9ba52778b97a15ebdfa3f6f59b506` |
| ABI | [abi/ThogAMM.json](abi/ThogAMM.json) |

Send every call to the pool contract. It is an upgradeable proxy
([EIP-1967](https://eips.ethereum.org/EIPS/eip-1967)); the implementation
address is listed so you can tell when the code behind it changes. Display
name: **ThogAMM**. [Logo](https://avatars.githubusercontent.com/u/85769984?v=4).

The pool implements three interfaces:

| Interface | Functions | Use it to |
| --- | --- | --- |
| ThogAMM's own | `makerQuoteExactInput`, `makerSwapExactInput`, `swapWithExtraFees` | Quote and swap with a minimum output and a deadline. Start here. |
| [ERC-7815](https://github.com/ethereum/ERCs/blob/70e96af4539a39ed2bf564ec3559fb45159ff223/ERCS/erc-7815.md) (draft) | `getTokens`, `getLimits`, `getCapabilities`, `price`, `swap` | Discover tokens; swap an exact output amount. See [ERC-7815](#erc-7815-interface). |
| State | `getPoolData`, `storedMultiplier` | Read everything a local pricing model needs. See [local quotes](#quote-locally). |

Every amount in every call is an integer in the token's smallest unit: 100 USDC
is `100000000` because USDC has six decimals.

## List the tokens

```solidity
function getPoolIds() external pure returns (bytes32[] memory);
function getTokens(bytes32 poolId) external view returns (address[] memory);
```

`getPoolIds()` returns the single pool ID above and `getTokens(poolId)` returns
the listed tokens. The list changes when a token is listed or retired, so read
it rather than hardcoding the [current table](#listed-tokens).

Any listed token can be swapped for any other, but not at every moment: the
operator can switch a token off as input or as output, and a pair is refused
while the pool has too little of the output token or too much of the input
token. Treat a rejected quote as normal, and ask again later.

Native MON is not listed. Wrap it and trade WMON; send no value with a swap.

## Quote

```solidity
function makerQuoteExactInput(address tokenIn, address tokenOut, uint256 amountIn)
    external view returns (uint256 amountOut, uint256 lastPostedBlock);
```

With [Foundry](https://getfoundry.sh)'s `cast`, quote 100 USDC to WETH:

```sh
cast call 0x80c74517BCC2D67fFE02D3ED886796272F647210 \
  'makerQuoteExactInput(address,address,uint256)(uint256,uint256)' \
  0x754704Bc059F8C67012fEd69BC8A327a5aafb603 \
  0xEE8c0E9f1BFFb4Eb878d8f15f368A02a35481242 \
  100000000 --rpc-url "$MONAD_RPC"
```

```text
55017555532321048    amountOut: 0.055 WETH
123018495            lastPostedBlock: the block of the price update the quote used
```

The call needs no balance or allowance and reserves nothing. It reverts when
the pool would not make the trade; the [revert reasons](#revert-reasons) say why.

`lastPostedBlock` tells you how old the prices are. It is not a deadline.

## Swap

```solidity
function makerSwapExactInput(
    address tokenIn, address tokenOut, uint256 amountIn,
    uint256 minAmountOut, address recipient, uint256 deadlineBlock
) external returns (uint256 amountOut);
```

| Argument | Meaning |
| --- | --- |
| `amountIn` | Pulled from the caller with `transferFrom`. |
| `minAmountOut` | The swap reverts if it would pay less. |
| `recipient` | Receives the output. Must not be the zero address. |
| `deadlineBlock` | Last **block number** the swap may execute in. |

1. The caller holds `amountIn` of `tokenIn` and has approved the **pool
   contract** for it ([ERC-20](https://eips.ethereum.org/EIPS/eip-20)
   `approve`). Do not transfer tokens to the pool yourself; it pulls them.
2. Call `makerSwapExactInput` on the pool with no value attached.
3. The pool pulls the input, sends the output to `recipient`, and returns the
   amount it guarantees the recipient received.

The swap executes fully or reverts. It never fills partially.

Set `minAmountOut` from a quote made for the block you expect to land in, less
your slippage tolerance. Three things can make a swap pay less than a quote you
made earlier: [older prices](#price-age), the [execution
surcharge](#execution-surcharge), and a price update or another trade landing
first.

## Swap with an integrator fee

```solidity
function swapWithExtraFees(
    address tokenIn, address tokenOut, uint256 amountIn,
    uint256 minAmountOut, uint256 expiry, uint256 extraFeePpm, address feeRecipient
) external returns (uint256 amountOut);
```

This is the same swap, with a share of the output diverted to you.

> **Contact us before you use a fee.** `feeRecipient` is not a wallet address.
> It must be a fee collection contract that we deploy for your integration,
> where your fees accrue until they are paid out to you. To have one set up,
> message [@thogard](https://t.me/thogard) on Telegram or email
> [alex@fastlane.finance](mailto:alex@fastlane.finance). A swap with a nonzero
> fee and any other recipient reverts.

**`extraFeePpm` is in parts per million of the output**, not basis points:

| `extraFeePpm` | Fee |
| ---: | --- |
| `1` | 0.0001% (0.01 bp) |
| `100` | 0.01% (1 bp) |
| `1000` | 0.1% (10 bp) |
| `10000` | 1% |
| `1000000` | 100%, the maximum |

To convert, multiply basis points by 100. Passing `30` charges 0.003%, not
0.30%; a 0.30% fee is `3000`.

```text
fee       = floor(output × extraFeePpm / 1,000,000)
amountOut = output − fee
```

Here `output` is what `makerSwapExactInput` would have returned for the same
swap in the same transaction. The fee is paid in `tokenOut`.

It differs from `makerSwapExactInput` in three more ways:

- The output goes to the **caller**. There is no `recipient` argument.
- `expiry` is a **Unix timestamp in seconds**, not a block number.
- `minAmountOut` and the returned `amountOut` are **after** the fee.

With `extraFeePpm` of zero there is no fee and `feeRecipient` is ignored.

Before sending the fee, the pool calls two functions on the fee contract, with
gas limits of 150,000 and 25,000; allow for them in your gas limit. To simulate
a fee swap before your fee contract exists, give `feeRecipient` any code that
accepts every call, using an `eth_call` state override.

## What changes the output

### Price age

The pool stores the block of its latest price update, a maximum age, and a
spread added per block of age. At the time of writing the maximum age is 15
blocks and each block of age adds 0.5 bp; both are pool parameters and can
change.

```text
age = block the swap executes in − block of the latest price update
```

A swap at age 3 pays about 1.5 bp less than at age 0. Once the age exceeds the
maximum, every quote and swap reverts with `maker: stale` until prices are
updated.

State held in memory ages too. If you quote from a cached copy of the pool,
evaluate it at the block you expect to trade in, and stop using it once it is
older than you can tolerate. A pool whose prices have moved since you read it
will quote amounts the chain no longer pays.

### Execution surcharge

When a swap executes, the pool reduces the output by a surcharge that depends
on how far the transaction's gas price is above the block's base fee. The
read-only quote does not include it.

| Effective gas price | Surcharge | If prices were updated in the same block |
| --- | ---: | ---: |
| At most 1.5 × base fee | none | none |
| Above 1.5 × base fee | 6 bp | 0.5 bp |
| Above 2 × base fee | 8 bp | 1 bp |
| Above 2.5 × base fee | 12 bp | 2 bp |

The effective gas price of an
[EIP-1559](https://eips.ethereum.org/EIPS/eip-1559) transaction is
`min(maxFeePerGas, baseFee + maxPriorityFeePerGas)`. **Keep the priority fee at
or below half the base fee and there is no surcharge.**

The pool also applies the highest tier, whatever the gas price, when the
FastLane AuctionHandler (`0xD32EdF6642D917DbBE7B8BF8e5d6F5df6a9FFF58`) is
already warm at the pool's first swap of the transaction. It is warm if the
transaction called it earlier, or if the transaction's
[access list](https://eips.ethereum.org/EIPS/eip-2930) names it.

**Keep the AuctionHandler out of your access list.** An aggregator's
transaction does not normally call that contract. But the pool touches it to
make this check, so an access list generated from a swap, for example by
`eth_createAccessList`, contains its address. Remove that entry before you send
the transaction.

Simulate swaps on a Monad node. The pool tells whether the AuctionHandler is
warm by measuring what a call to it costs, against Monad's
[cold-access cost](https://docs.monad.xyz/developer-essentials/opcode-pricing#cold-access-cost).
A simulator that charges Ethereum's cost reports the highest tier for every
swap. A Monad node ignores the access list of an `eth_call` that sets
`gasPrice`; to simulate a transaction with an access list, set `maxFeePerGas`
and `maxPriorityFeePerGas` instead.

### Inventory caps

The pool caps how much of each token it will hold, and how much of each
**category**: a group of tokens that track the same asset, such as USDC, AUSD
and USDT0. A swap that would take a holding over its cap reverts with
`maker: balance`. It also reverts if the pool does not hold enough of the
output token.

`makerQuoteExactInput` checks against 90% of each cap, so that a swap quoted
near a cap still fits when it executes.

## xStocks

The xStocks in the [token list](#listed-tokens) are tokenized equities. Their
contracts keep balances in **shares** and convert shares to token amounts with
a **multiplier** that changes on dividends and splits; xStocks documents this
in [How xStocks Handles Dividends & Stock Splits](https://docs.xstocks.fi/developers/multipliers).
Three consequences matter to a router.

**Transfers round.** A transfer of `amount` moves a whole number of shares, so
the recipient's balance can rise by a few raw units less than `amount`. The
pool allows for this on its own transfers: it sends slightly more than it
promises, and its return value is a floor on what the recipient receives, not
the exact figure.

```text
received ≥ amountOut          correct check for an xStock output
received == amountOut         can fail
```

**Your own transfers round too.** If your router pulls an xStock from the user
before swapping, swap the amount the router actually received, measured as its
balance change, not the amount it asked for. The same holds if the router
forwards an xStock output to the user: check the user's balance change against
your minimum. Sending the output straight to the user avoids that extra
transfer.

**The pool prices with its own stored multiplier.** It copies each xStock's
multiplier from the issuer when anyone calls `syncMultipliers(address[])`, and
uses the stored value until the next call. If an issuer's multiplier has
changed and the stored one has not yet been synced, swaps of that xStock revert
with `xstock: multiplier stale`. Read the stored value with
`storedMultiplier(token)` on the pool; it is zero for a token that is not an
xStock.

The pool lists the unwrapped xStocks. Their
[wrapped forms](https://docs.xstocks.fi/developers/wrapped-xstocks) are
different tokens and are not listed.

## Common pitfalls

1. **Treating `extraFeePpm` as basis points.** It is parts per million.
   [Scale table](#swap-with-an-integrator-fee).
2. **Using a wallet as `feeRecipient`.** It must be the fee contract we set up
   for you. [Contact us first](#swap-with-an-integrator-fee).
3. **Mixing up the two deadlines.** `makerSwapExactInput` takes a block number;
   `swapWithExtraFees` takes a Unix timestamp.
4. **Expecting the fee swap to pay a recipient.** `swapWithExtraFees` pays the
   caller.
5. **Sending a large priority fee.** Above half the base fee, the pool pays
   less. [Surcharge tiers](#execution-surcharge).
6. **Sending a generated access list unchanged.** It names the AuctionHandler,
   and the swap then pays the highest surcharge.
   [Execution surcharge](#execution-surcharge).
7. **Quoting from old state.** Prices age every block and expire.
   [Price age](#price-age).
8. **Quoting two swaps of one route against the same state.** The second swap
   executes against the inventory the first one left. Quote them in sequence.
9. **Requiring an exact xStock amount.** Check `received ≥ amountOut`.
   [xStocks](#xstocks).
10. **Reading `getLimits` as a tradeable size.** Its values are upper bounds;
    a smaller amount can still be refused. [ERC-7815](#erc-7815-interface).
11. **Simulating with Ethereum gas rules.** The surcharge comes out wrong.
    [Execution surcharge](#execution-surcharge).
12. **Setting a loose gas limit.** Monad charges for the
    [gas limit, not the gas used](https://docs.monad.xyz/developer-essentials/gas-pricing#gas-limit-not-gas-used).
    [Gas](#gas).
13. **Reading the base fee from an `eth_call` without a gas price.** A Monad
    node reports a base fee of zero to such a call. Pass `gasPrice` when a
    call's result depends on the base fee, as `getPoolData` and any simulated
    swap do.

## Quote locally

Calling the contract for every quote is too slow for route search. Two Rust
SDKs reproduce the pool's arithmetic in memory, to the last raw unit:

| SDK | Keeps state current by |
| --- | --- |
| [Polling SDK](https://github.com/thogard785/thog-amm-poll-sdk) | Reading the pool over HTTP, one request per refresh |
| [Event SDK](https://github.com/thogard785/thog-amm-event-sdk) | Reading the pool once, then applying logs from a Monad WebSocket subscription |

Both give you a `Pool`. Its methods have the names of the contract calls they
reproduce and return the same numbers:

| Contract call | SDK |
| --- | --- |
| `makerQuoteExactInput` | `pair.maker_quote_exact_input(amount_in)` |
| `makerSwapExactInput` | `pair.maker_swap_exact_input(amount_in, tx)` |
| `swapWithExtraFees` | `pair.swap_with_extra_fees(amount_in, extra_fee_ppm, tx)` |
| ERC-7815 `swap`, sell side | `pair.swap_sell(amount_in, tx)` |
| ERC-7815 `swap`, buy side | `pair.swap_buy(amount_out, tx)` |
| ERC-7815 `price` | `pair.price(amount_in)` |
| ERC-7815 `getLimits` | `pair.get_limits()` |

```toml
[dependencies]
thogamm-poll = { git = "https://github.com/thogard785/thog-amm-poll-sdk", tag = "v0.7.0" }
tokio = { version = "1", features = ["macros", "rt-multi-thread"] }
```

```rust
//! Read the pool once and price 100 USDC -> WETH three ways.
//!
//!     MONAD_RPC=https://rpc.monad.xyz cargo run --example quote
use thogamm_poll::{Poller, TxContext, U256};

#[tokio::main]
async fn main() -> Result<(), Box<dyn std::error::Error>> {
    let rpc = std::env::var("MONAD_RPC")?;
    let pool_address = "0x80c74517BCC2D67fFE02D3ED886796272F647210".parse()?;
    let usdc = "0x754704Bc059F8C67012fEd69BC8A327a5aafb603".parse()?;
    let weth = "0xEE8c0E9f1BFFb4Eb878d8f15f368A02a35481242".parse()?;
    let amount_in = U256::from(100_000_000u64); // 100 USDC, six decimals

    let poller = Poller::connect(rpc, pool_address).await?;
    let read = poller.pool();
    println!("read at block {}", read.snapshot().block.number);

    // Price the swap in the block it should land in, not the block that was read.
    let pool = read.at_block(read.block_number() + 1, read.base_fee())?;
    let pair = pool.pair(usdc, weth)?;

    // What makerQuoteExactInput returns.
    let quote = pair.maker_quote_exact_input(amount_in)?;
    println!("quote:          {} wei WETH", quote.amount_out);

    // What makerSwapExactInput pays in a transaction with a 10% priority fee.
    let tx = TxContext::with_gas_price(pool.base_fee() * U256::from(11) / U256::from(10));
    let swap = pair.maker_swap_exact_input(amount_in, tx)?;
    println!(
        "swap:           {} wei WETH (surcharge {} x 0.01 bp)",
        swap.amount_out, swap.surcharge
    );

    // What swapWithExtraFees pays with a 0.10% integrator fee: 1,000 parts per million.
    let with_fee = pair.swap_with_extra_fees(amount_in, 1_000, tx)?;
    println!(
        "swap with fee:  {} wei WETH to the caller, {} to the fee recipient",
        with_fee.amount_out, with_fee.fee
    );
    Ok(())
}
```

`pool.pair(a, b)` prepares one direction; reuse it for every amount you try.
`pool.after(&swap)` gives the pool as that swap would leave it, for the next
swap of the same route. A quote that the pool would refuse returns an error
that names the [revert reason](#revert-reasons).

To write your own model in another language, the [reference](REFERENCE.md)
specifies the state, the arithmetic and the events, and the SDK's
[`model`](https://github.com/thogard785/thog-amm-poll-sdk/tree/main/model/src)
crate is a working implementation of it.

### Reading state yourself

One `eth_call` returns everything, from a single block:

- `getPoolData(0, 28)` on the pool: the token list, the pool's balance of each
  token, its native MON balance, and the storage words that hold prices and
  parameters.
- `storedMultiplier(token)` on the pool, for every token. Nonzero means the
  token is an xStock.
- `sharesOf(pool)` on each xStock.

Batch them through [Multicall3](https://www.multicall3.com) so that all three
come from the same block, and pass `gasPrice` so that the pool data carries the
real base fee. The reference lists the [exact
calls](REFERENCE.md#reading-a-snapshot).

### Following state from events

Every change to the pool's state emits a log, so a model can advance block by
block without reading the chain again. The reference gives the [log filters and
the rule for each event](REFERENCE.md#keeping-state-current-from-events). Two
points decide whether this works:

- Apply only **finalized** blocks, each with **all** of its logs, in order.
  Monad's `monadNewHeads` subscription reports each block's
  [commit state](https://docs.monad.xyz/reference/json-rpc/overview#websocket-subscriptions).
- On any gap, on a pool upgrade, or when a token is listed or retired, discard
  the model and read the state again.

## ERC-7815 interface

The pool follows the [ERC-7815 draft at this
revision](https://github.com/ethereum/ERCs/blob/70e96af4539a39ed2bf564ec3559fb45159ff223/ERCS/erc-7815.md).
The draft was not merged into the ERCs repository, so pin that revision.

| Function | Behaviour |
| --- | --- |
| `getTokens(poolId)` | The listed tokens. |
| `getCapabilities(poolId, sell, buy)` | `SellOrder`, `BuyOrder`, `PriceFunction`, `MarginalPrice`. |
| `getLimits(poolId, sell, buy)` | `[sellLimit, buyLimit]`: the largest input and the largest output, in raw units. Each is an upper bound on its own; an amount below both can still be refused. For a token without a cap, `sellLimit` is an arithmetic bound far above anything the pool can pay for. |
| `price(poolId, sell, buy, amounts)` | For each amount, the price of the next unit after selling that amount, as a fraction of raw output units per raw input unit. It is a marginal price, not the average price of the trade. |
| `swap(poolId, sell, buy, side, amount)` | `side = 0` sells exactly `amount` of `sell`; `side = 1` buys exactly `amount` of `buy`. Returns `(calculatedAmount, gasUsed, marginalPriceAfterTrade)`. |
| `priceDerivative`, `swapToPrice` | Not implemented; they revert. |

`swap` is a real swap. It pulls input from the caller and sends output to the
caller, even in an `eth_call`, so the simulated caller needs a balance and an
allowance. It has no minimum output, maximum input or deadline: the contract
that calls it must enforce those.

Use `swap` with `side = 1` when you need an exact output amount. For exact
input, prefer `makerSwapExactInput`, which has the protections built in.

## Revert reasons

| Revert | Meaning | What to do |
| --- | --- | --- |
| `maker: stale` | Prices are older than the maximum age. | Retry after the next price update. |
| `maker: paused` | The operator has paused the pool. | Skip the pool for now. |
| `maker: side off` | The input token is not being accepted, or the output token is not being paid out. | Skip the pair for now. |
| `maker: unknown token` | A token is not listed, or both tokens are the same. | Refresh the token list. |
| `maker: zero fill` | The amount is too small to produce any output. | Use a larger amount. |
| `MakerAmountTooLarge(limit)` | The amount is above the arithmetic limit. | Use a smaller amount. |
| `maker: balance` | Not enough output inventory, or a cap would be exceeded. | Use a smaller amount or another pair. |
| `maker: min out` | The output is below `minAmountOut`. | Requote. |
| `maker: deadline`, `maker: expired` | Past `deadlineBlock` or `expiry`. | Resend with a later deadline. |
| `maker: recipient` | `recipient` is the zero address. | |
| `maker: extra fee` | `extraFeePpm` is above 1,000,000. | |
| `maker: fee recipient`, `MakerFeeTokenSetupFailed()`, `MakerFeeConfirmationFailed()` | `feeRecipient` is not a fee contract set up for this pool. | [Contact us](#swap-with-an-integrator-fee). |
| `xstock: multiplier stale` | An xStock's multiplier changed and has not been synced. | Call `syncMultipliers`, or retry later. |
| `TRANSFER_FROM_FAILED` | The caller lacks the input balance or the allowance. | |
| `maker: risk uninitialized`, `maker: spread`, `maker: migration required` | The pool's parameters are being set up or changed. | Skip the pool for now. |

The ERC-7815 functions report the same conditions as
`Unavailable(string reason)` and `LimitExceeded(uint256 limit)`.

## Gas

`eth_estimateGas` for `makerSwapExactInput` called directly by an account, at
block 123,024,098:

| Swap | Gas |
| --- | ---: |
| WMON to WETH | 436,567 |
| WMON to USDC | 456,853 |
| WMON to an xStock | 504,517 |

A swap between two tokens of the same category, such as USDC to AUSD, costs
less because it skips the portfolio risk calculation. An integrator fee adds two
calls and a transfer. Measure your own route, and set the limit tightly: Monad
charges for the
[gas limit, not the gas used](https://docs.monad.xyz/developer-essentials/gas-pricing#gas-limit-not-gas-used).

## Listed tokens

The list at the time of writing. Read `getTokens(poolId)` for the current one.

| Token | Address | Decimals | Kind |
| --- | --- | ---: | --- |
| USDC | `0x754704Bc059F8C67012fEd69BC8A327a5aafb603` | 6 | |
| AUSD | `0x00000000eFE302BEAA2b3e6e1b18d08D69a9012a` | 6 | |
| USDT0 | `0xe7cd86e13AC4309349F30B3435a9d337750fC82D` | 6 | |
| WMON | `0x3bd359C1119dA7Da1D913D1C4D2B7c461115433A` | 18 | |
| WETH | `0xEE8c0E9f1BFFb4Eb878d8f15f368A02a35481242` | 18 | |
| WBTC | `0x0555E30da8f98308EdB960aa94C0Db47230d2B9c` | 8 | |
| cbBTC | `0xd18B7EC58Cdf4876f6AFebd3Ed1730e4Ce10414b` | 8 | |
| XAUt0 | `0x01bFF41798a0BcF287b996046Ca68b395DbC1071` | 6 | |
| SPYx | `0x90A2a4c76b5D8c0bc892A69EA28Aa775a8f2dD48` | 18 | xStock |
| QQQx | `0xa753A7395cAe905Cd615Da0B82A53E0560f250af` | 18 | xStock |
| EWYx | `0x299c95Eb52BFd5Bc98d924bCE17197b64864589B` | 18 | xStock |
| NVDAx | `0xc845b2894dBddd03858fd2D643B4eF725fE0849d` | 18 | xStock |
| TSLAx | `0x8aD3c73F833d3F9A523aB01476625F269aEB7Cf0` | 18 | xStock |
| SMHx | `0x8D512a03600981B8e86556fd5C0FbDd726Fe1821` | 18 | xStock |
| SPCXx | `0x68fa48B1C2FE52b3D776E1953e0E782b5044Ce28` | 18 | xStock |
| MUx | `0xf6a873BAe4Ba1B304e45dF52A4b7D176E1C6a8c4` | 18 | xStock |
| SKHYx | `0x58100046a4Afcd4eE4faDbD4244f3f895a341c56` | 18 | xStock |

Tokens that charge a fee on transfer are not supported and are not listed.

## Verify your integration

Compare your quotes with the contract at the same block. Results must be equal
to the last raw unit, and a request the contract reverts must be rejected by
your model too. Do not allow a tolerance: a model that is off by one unit is
using different arithmetic and will be off by more elsewhere.

[verification/README.md](verification/README.md) has recorded contract results
to test against and the commands that reproduce them. Before going live, also
check, by simulation on a Monad node:

- both directions of every pair you route, at small and large sizes;
- a swap at each [surcharge tier](#execution-surcharge);
- an xStock as input and as output, through your router's own transfers;
- a fee swap, comparing the fee with `extraFeePpm`;
- a route that visits the pool twice;
- a quote from state that is one block short of expiring, and one block past it.
