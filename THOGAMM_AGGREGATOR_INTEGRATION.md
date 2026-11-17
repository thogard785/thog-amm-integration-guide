# ThogAMM aggregator integration

ThogAMM provides inventory-funded swaps on **Monad mainnet (chain ID 143)**.
Use the [polling SDK](https://github.com/thogard785/thog-amm-poll-sdk) or
[event SDK](https://github.com/thogard785/thog-amm-event-sdk), version **0.6.1**,
for local quotes. Both support all 17 listed tokens, including SMHx, SPCXx,
MUx and SKHYx, and use the pool's stored xStock multipliers.

## Deployment

| Field | Value |
| --- | --- |
| Proxy — send all calls here | `0x80c74517BCC2D67fFE02D3ED886796272F647210` |
| Implementation | `0xb108a1daf3c9ba52778b97a15ebdfa3f6f59b506` |
| Pool ID | `0xce389e78282dedac7b18ba7f775b7602d2ab3ab171bbd6711eb0239be6ef4dcc` |
| FastLane AuctionHandler | `0xD32EdF6642D917DbBE7B8BF8e5d6F5df6a9FFF58` |

Display name: **ThogAMM** · [Logo](https://avatars.githubusercontent.com/u/85769984?v=4) ·
[Explorer](https://monadscan.com/address/0x80c74517BCC2D67fFE02D3ED886796272F647210) ·
[Complete ABI](abi/ThogAMM.json)

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
| SMHx | `0x8d512a03600981b8e86556fd5c0fbdd726fe1821` | 18 |
| SPCXx | `0x68fa48b1c2fe52b3d776e1953e0e782b5044ce28` | 18 |
| MUx | `0xf6a873bae4ba1b304e45df52a4b7d176e1c6a8c4` | 18 |
| SKHYx | `0x58100046a4afcd4ee4fadbd4244f3f895a341c56` | 18 |

Read `getTokens(poolId)` for the current registry; do not hard-code indices.
Use WMON for native MON routes. Fee-on-transfer tokens are unsupported.
The nine xStocks are unwrapped tokens with 18 decimals; their wrapped versions
are separate assets and are not listed in this pool.

## Quote and swap

1. Call `makerQuoteExactInput` with raw token units.
2. Approve the proxy to spend the input token. Simulate the complete route with
   the intended caller, recipient and transaction fee fields.
3. Call `makerSwapExactInput` with your minimum output and inclusive block
   deadline. Send zero native value. The proxy pulls input from the caller and
   transfers output to the recipient.

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

## Funding through an aggregator

xStock transfers round to whole shares. If your router first pulls input, quote
and pass its **newly received amount**, measured as the balance increase.
Exclude the router's pre-existing funds and handle residual input through its
normal refund policy. Each subsequent transfer rounds independently.

The swap's returned `amountOut` is guaranteed recipient credit; the actual
credit can be slightly greater. Measure output and check
`received >= amountOut`. Do not subtract another rounding allowance from this
guarantee. Sending output directly to the final recipient avoids another
transfer; if your router forwards it, measure the final recipient's credit too.

## Quotes, limits and settlement

- Read-only quotes exclude the execution output adjustment. Use the SDK's
  `quote_execution_exact_input` for direct settlement and `quote_exact_output`
  for ERC-7815 Buy. Both include the contract's share rounding.
- Execution output depends on the effective gas price, block base fee, whether
  the AuctionHandler account is already warm, and whether prices were updated
  in that block. SDK defaults assume a cold AuctionHandler; `*_with_context`
  accepts its actual warmth. Simulate the full route to reproduce this context.
- Quotes enforce price age, enabled directions, pause status and inventory caps.
  Read-only quotes use 90% cap thresholds; settlement uses full caps and actual
  transfer deltas. Independent quotes do not simulate successive fills.
- `getLimits` returns `[sellLimit, buyLimit]`, separate upper bounds. Smaller
  amounts can still fail other checks. `price` is a marginal fraction of raw
  output units per raw input unit, not an average quote.
- ERC-7815 `swap(..., Sell, amountIn)` returns output in `Trade.calculatedAmount`;
  `swap(..., Buy, amountOut)` returns required input. It has no minimum-output
  or expiry argument; provide slippage protection in your settlement route.
- `swapWithExtraFees` deducts
  `floor(grossOutput * extraFeePpm / 1_000_000)`. Its minimum protects net output;
  expiry is an inclusive Unix timestamp. A nonzero fee requires your collection
  contract as `feeRecipient`. Simulate this call; SDK quotes exclude extra fees.

For EIP-1559 transactions, effective gas price is
`min(maxFeePerGas, baseFee + maxPriorityFeePerGas)`. Supply fee fields to Monad
`eth_call`: use `gasPrice: 0x1` for state reads to preserve the block's base fee,
and the intended fee context for settlement simulation. The final execution
state determines output and whether the minimum is met.

## xStock multipliers and local state

**Read `storedMultiplier(token)` from the ThogAMM proxy, not a multiplier getter
on the xStock.** It returns one `uint256`. Quoting and settlement use this
stored value without calling the issuer's multiplier getter. The pool's
`syncMultipliers` operation updates it and emits
`MakerMultiplierUpdated(address,uint256)`.

For a complete snapshot, read a header, `getPoolData(0, 28)`, each listed
xStock's `sharesOf(proxy)`, and its pool-stored multiplier at the **same block
hash**. Value shares as `floor(shares * storedMultiplier / 1e18)`. Include all
listed xStocks: their inventory affects quotes for other pairs too. The issuer's
`balanceOf` can differ until the stored multiplier is synchronized; settlement
checks share deltas and can revert with `xstock: multiplier stale`.

The polling SDK refreshes the complete snapshot. The event SDK loads one
snapshot, then applies complete finalized blocks, including share transfers
and `MakerMultiplierUpdated`, without further RPC reads. An issuer change by
itself does not update the model. Quote calculations make no network calls.
`at_block` changes quote age and fee context without fetching new state.

Use SDK 0.6.1 for the implementation above. SDK 0.5.0 reads issuer multipliers
and is incompatible; 0.6.0 already uses stored multipliers. The state format
remains schema 8 / wire 8 / model 3, so format numbers alone cannot identify the
implementation. On upgrades, check compatibility; on registry changes, reload
the snapshot and rebuild prepared pairs. After a missing log or stream error,
reconnect before resuming event-based quotes.

For a custom implementation, see the
[model specification](REFERENCE.md) for exact arithmetic, packed state
and event handling, and the
[contract fixtures](https://github.com/thogard785/thog-amm-integration-guide#verification)
for independent comparisons.
