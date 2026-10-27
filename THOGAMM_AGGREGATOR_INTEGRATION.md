# ThogAMM aggregator integration

ThogAMM is an inventory-funded liquidity source on Monad mainnet. Use
`makerQuoteExactInput` for a read-only quote and `makerSwapExactInput` for
settlement with a minimum output and block deadline. For local quoting, use the
[polling SDK](https://github.com/thogard785/thog-amm-poll-sdk) or
[event SDK](https://github.com/thogard785/thog-amm-event-sdk), the pending **0.5.0** model-3 release.

This guide describes the pending **schema 8 / wire 8 / model 3** upgrade.
Released SDK 0.4.1 supports model 2 and its historical 10 bp execution policy.
The new implementation and backend must be activated together; use SDK 0.5.0
only after verifying model 3 in the selected snapshot. This PR does not deploy it.

The pool lists **13 tokens**
as of October 27, 2026; the registry capacity is 28. Both SDKs discover the active
registry from `getPoolData(0, 28)`. Share accounting recognizes the contract's
[nine compiled xStock addresses](https://github.com/thogard785/thog-amm-poll-sdk/blob/v0.4.1/model/src/shares.rs).
Listing another of those nine needs no model change; extending the contract's
xStock catalog requires a matching SDK release. Discovery alone cannot recognize
an arbitrary new issuer token.

## Deployment

| Field | Value |
| --- | --- |
| Network / chain ID | Monad mainnet / `143` |
| Proxy | `0x80c74517BCC2D67fFE02D3ED886796272F647210` |
| Pool ID | `0xce389e78282dedac7b18ba7f775b7602d2ab3ab171bbd6711eb0239be6ef4dcc` |
| FastLane AuctionHandler | `0xD32EdF6642D917DbBE7B8BF8e5d6F5df6a9FFF58` |
| Explorer | [Monadscan](https://monadscan.com/address/0x80c74517BCC2D67fFE02D3ED886796272F647210) |

Send calls to the proxy. Display name: `ThogAMM`;
[logo](https://avatars.githubusercontent.com/u/85769984?v=4).

## Listed tokens

| Token | Address | Decimals |
| --- | --- | ---: |
| USDC | `0x754704Bc059F8C67012fEd69BC8A327a5aafb603` | 6 |
| AUSD | `0x00000000eFE302BEAA2b3e6e1b18d08D69a9012a` | 6 |
| USDT0 | `0xe7cd86e13AC4309349F30B3435a9d337750fC82D` | 6 |
| WMON | `0x3bd359C1119dA7Da1D913D1C4D2B7c461115433A` | 18 |
| WETH | `0xEE8c0E9f1BFFb4Eb878d8f15f368A02a35481242` | 18 |
| WBTC | `0x0555E30da8f98308EdB960aa94C0Db47230d2B9c` | 8 |
| cbBTC | `0xd18B7EC58Cdf4876f6AFebd3Ed1730e4Ce10414b` | 8 |
| XAUt0 | `0x01bFF41798a0BcF287b996046Ca68b395DbC1071` | 6 |
| SPYx | `0x90a2a4c76b5d8c0bc892a69ea28aa775a8f2dd48` | 18 |
| QQQx | `0xa753a7395cae905cd615da0b82a53e0560f250af` | 18 |
| EWYx | `0x299c95eb52bfd5bc98d924bce17197b64864589b` | 18 |
| NVDAx | `0xc845b2894dbddd03858fd2d643b4ef725fe0849d` | 18 |
| TSLAx | `0x8ad3c73f833d3f9a523ab01476625f269aeb7cf0` | 18 |

`getTokens(poolId)` is authoritative. Indices, sides, balances and available sizes
can change; read metadata instead of hard-coding indices. Use WMON for native MON
routes. Fee-on-transfer tokens are unsupported.

The five xStocks are **unwrapped tokens**, each with 18 decimals. The separate
wxStock wrapper addresses are not listed here. xStock balances rebase through an
issuer multiplier; a multiplier activation can occur without a transfer or log.

## Smallest integration

1. Discover the tokens, then call `makerQuoteExactInput(tokenIn, tokenOut, amountIn)`.
   All amounts are raw token units. The result is `(amountOut, lastPostedBlock)`.
2. Simulate the actual settlement call with the intended caller, fee fields and
   route context. The caller needs input-token funds and allowance to the proxy.
3. Call `makerSwapExactInput` with your acceptable `minAmountOut`, recipient and
   inclusive `deadlineBlock`. Send zero native value; the proxy pulls input with
   `transferFrom` and sends output to the recipient.

```solidity
interface IThogAMM {
    function makerQuoteExactInput(address tokenIn, address tokenOut, uint256 amountIn)
        external view returns (uint256 amountOut, uint256 lastPostedBlock);
    function makerSwapExactInput(
        address tokenIn, address tokenOut, uint256 amountIn,
        uint256 minAmountOut, address recipient, uint256 deadlineBlock
    ) external returns (uint256 amountOut);
}
```

Use the [complete ABI](abi/ThogAMM.json) for state, events and ERC-7815 calls.

## Funding through an aggregator

The SDK models the Thog call, including its own input/output share rounding.
If a router first pulls xStocks, that funding transfer rounds independently.
Pass the router's **newly received input**, not the requested transfer amount or
its total balance. This fragment uses OpenZeppelin `IERC20` and
`using SafeERC20 for IERC20;` inside your router's guarded swap, with distinct
input/output tokens and an external recipient:

```solidity
uint256 beforeIn = tokenIn.balanceOf(address(this));
tokenIn.safeTransferFrom(msg.sender, address(this), requestedIn);
uint256 amountIn = tokenIn.balanceOf(address(this)) - beforeIn;
tokenIn.forceApprove(address(thog), amountIn);

uint256 beforeOut = tokenOut.balanceOf(recipient);
uint256 guaranteedOut = thog.makerSwapExactInput(
    address(tokenIn), address(tokenOut), amountIn,
    minAmountOut, recipient, deadlineBlock
);
uint256 received = tokenOut.balanceOf(recipient) - beforeOut;
require(received >= guaranteedOut, "Thog output below guarantee");
// Report/use received as this hop's output.
```

Use this measured `amountIn` for the Thog quote as well. Simulate the **whole
route**, including funding and the actual fee/account-warmth context. Existing
router funds must stay outside this trade; reconcile residual input through your
router's refund/accounting policy. Sending Thog output directly to the intended
recipient avoids an extra transfer. If the router forwards it, measure that
recipient's credit again: each forwarding transfer rounds independently.

## Quotes, limits and settlement

- `getCapabilities` advertises Sell, Buy, price functions and marginal prices.
- `getLimits` returns `[sellLimit, buyLimit]`: separate upper bounds, not a promise
  that every smaller amount executes. The buy limit is physical output balance
  less xStock output dust; receiving-token and category caps still apply.
- `price` returns a fraction of raw output units per raw input unit. It is a
  marginal price, not an average quote. Each requested amount uses the same state.
- ERC-7815 `swap(..., Sell, amountIn)` returns output in `Trade.calculatedAmount`;
  `swap(..., Buy, amountOut)` returns the minimum required input. `swap` has no
  minimum-output or expiry parameter. Simulate it, then simulate your chosen
  protected settlement call as well: integer rounding and final inventory can differ.

Read-only quotes use strict 90% inventory-cap thresholds. Settlement uses full
caps and actual transfer deltas. Existing inventory above a cap may decrease but
cannot increase. Debt and risk targets do not offset these gross inventory caps.
Quotes also enforce pause/readiness, enabled directions, price age and arithmetic
bounds. Independent quotes do not simulate successive fills of shared inventory.

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

For xStocks, the contract values `max(0, amountIn - inputDust)`, where each stock's dust
is `max(2, ceil(multiplier / 1e18))`. The direct swap applies friction **after**
subtracting output dust; ERC-7815 applies it **before** subtracting output dust.
Settlement sends the quoted stock output plus dust, then floors that transfer to
shares. The returned output is the guaranteed amount; actual receipt can exceed
it by rounding. The SDK's execution `Quote.amount_out` has the same meaning under
the quoted state/context; for ERC-7815 Buy it equals the requested target. Compare
recipient credit with `received >= amount_out`, not equality, and do not subtract
another xStock rounding tolerance from this guarantee. Read-only quotes omit
execution friction. The settlement return and your `minAmountOut` apply to the
actual execution state. These contract rules are implemented by the matching model-3 SDKs.

Supply fee fields for Monad `eth_call`: an unpriced call can expose a zero base
fee. State reads use `gasPrice: 0x1` to retain the block's base fee; trade simulation
uses the actual transaction fee context. The final execution call is authoritative.

`swapWithExtraFees` takes an integrator fee from gross output:
`fee = floor(grossOutput * extraFeePpm / 1_000_000)`. Its `minAmountOut` protects
net output and `expiry` is an inclusive Unix timestamp. A nonzero fee requires the
integration's collection contract as `feeRecipient`. Simulate this actual call;
the SDK's execution quote assumes an ordinary swap with no extra fee.

## Build the schema-8 model in memory

The SDKs share one integer quote model. A complete snapshot consists of:

1. A canonical header and `getPoolData(0, 28)` at its block hash. Verify schema,
   counts, registry generation, block number, parent hash and base fee.
2. All 126 logical words at slots 2–127, token/category metadata, physical
   `portfolioBalances` and native MON. `getPoolData` already decodes zero markers;
   an inventory word equal to `1 << 255` is valid data.
3. `sharesOf(proxy)` and `getCurrentMultiplier()` for every registered unwrapped
   xStock, pinned to that same hash. The multiplier call returns three words;
   use the first. Check `balanceOf = floor(shares * multiplier / 1e18)`.

Stored inventory is `uint128` units at slots 107–120: shares for xStocks, raw
amounts for ordinary tokens. A quote uses physical holdings for its two endpoints
and stored ledger holdings for every other token. Revalue shares with the current
multiplier. Never reconstruct shares from rounded `balanceOf` values.

Polling refreshes the full image and discovers registry changes. Event updates
apply pool checkpoints and token movements, then read issuer multipliers for each
published finalized block, including blocks without logs. Neither SDK performs
network calls while calculating a quote. `at_block` changes age and execution context;
it does not fetch new trades, policy or issuer state.

See the [exact model specification](REFERENCE.md) for word offsets, packed fields,
curve equations, cap encoding and publication payloads.

## Event changes from the previous integration guide

| Event/input | Apply to |
| --- | --- |
| `MakerPageUpdated` lanes 1 / 2 / 4 / 8 | Prices / risk / wrappers / caps; verify emitted control |
| `MakerInventoryUpdated(uint8,address,uint128)` | Absolute accounted units; validate index/address and update the inventory zero bitmap |
| Ordinary ERC-20 `Transfer` | Physical balances of ordinary tokens |
| xStock `TransferShares` | Physical shares; ignore its accompanying nominal `Transfer` |
| Hash-pinned issuer multiplier | Revalue physical and accounted shares, even without logs |
| `MakerLendingExposureUpdated` | Absolute signed exposure offset and lending sequence |
| `MakerWmonBalanceCheckpoint`, `NativeBalanceCheckpoint` | Absolute physical WMON / native balance |
| `Paused` | Maker pause bit |
| `MakerTokenAdded`, `MakerTokenRetired` | Reload the complete registry and rebuild prepared pairs |
| `Upgraded` | Verify implementation compatibility before reconnecting |

Process logs once in canonical transaction/log order. Swap, fee and wrapper-cost
accounting events are not additional balance deltas. Missing events, malformed
publications or failed issuer reads must not publish a partial snapshot. Reconnect
explicitly after such errors. Forced native transfers need account-state data or a
fresh snapshot; ordinary logs do not cover them.
