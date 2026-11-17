# Integrate ThogAMM into an aggregator

ThogAMM swaps ERC-20 tokens from a market maker's inventory on Monad. The maker
publishes valuations and pricing parameters; the contract uses them together
with its portfolio holdings to calculate each trade. A quote can therefore
change when another token's inventory changes, even if neither token in your
pair has traded.

An integration needs to discover the supported tokens, quote a trade, fund the
account calling ThogAMM, and execute the swap with a minimum output. Start with
the contract calls below. For route searches that need many quotes, the
[polling and event SDKs](#calculate-quotes-locally) run the pricing model in memory.

## Connect to the pool

| Field | Value |
| --- | --- |
| Network | Monad mainnet, chain ID **143** |
| Pool contract — send all calls here | `0x80c74517BCC2D67fFE02D3ED886796272F647210` |
| Pool ID — used by discovery and ERC-7815 calls | `0xce389e78282dedac7b18ba7f775b7602d2ab3ab171bbd6711eb0239be6ef4dcc` |
| Implementation behind the proxy | `0xb108a1daf3c9ba52778b97a15ebdfa3f6f59b506` |

Use the [contract ABI](abi/ThogAMM.json) to encode calls. The implementation
address identifies the code; send ThogAMM calls to the pool contract. Token
approvals are calls to the input ERC-20 contract, with the pool as spender.
For display, use **ThogAMM** and this [logo](https://avatars.githubusercontent.com/u/85769984?v=4).

`getPoolIds()` returns the pool ID. `getTokens(poolId)` returns its active token
addresses. The [token table](#listed-tokens) supplies addresses and decimals;
use discovery for current membership and ordering. Use WMON for native MON
routes and send zero native value to ThogAMM.

## Get an exact-input quote

All amounts are integers in the token's smallest units. For example, **100 USDC
is `100_000_000`** because USDC has six decimals. A WETH output uses 18 decimals.

```solidity
interface IThogAMM {
    function makerQuoteExactInput(
        address tokenIn, address tokenOut, uint256 amountIn
    ) external view returns (uint256 amountOut, uint256 lastPostedBlock);

    function makerSwapExactInput(
        address tokenIn, address tokenOut, uint256 amountIn,
        uint256 minAmountOut, address recipient, uint256 deadlineBlock
    ) external returns (uint256 amountOut);
}
```

With Foundry's `cast` installed, query 100 USDC → WETH:

```sh
# Set MONAD_RPC to your Monad HTTP RPC URL.
THOGAMM=0x80c74517BCC2D67fFE02D3ED886796272F647210
USDC=0x754704Bc059F8C67012fEd69BC8A327a5aafb603
WETH=0xEE8c0E9f1BFFb4Eb878d8f15f368A02a35481242

cast call "$THOGAMM" \
  'makerQuoteExactInput(address,address,uint256)(uint256,uint256)' \
  "$USDC" "$WETH" 100000000 --rpc-url "$MONAD_RPC" --legacy --gas-price 1
```

The first result is raw WETH output. The second is the block in which the maker
published the prices used by the quote. It is **not a transaction deadline**.
The call needs no token balance or allowance. It can revert when the pair or
amount is unavailable. A successful read does not reserve inventory.

This read-only quote includes price-age widening and inventory limits. Settlement
also applies an execution adjustment determined by the transaction; account for
it as described in [quotes, limits and settlement](#quotes-limits-and-settlement).

## Construct and execute the swap

Call `makerSwapExactInput` when the input amount is fixed and your router needs
a recipient, minimum output, and deadline.

| Argument | Meaning |
| --- | --- |
| `tokenIn`, `tokenOut` | Addresses from the active registry |
| `amountIn` | Raw input available to the account that calls ThogAMM |
| `minAmountOut` | Minimum raw output the recipient must receive, chosen using your route's slippage policy |
| `recipient` | Nonzero user or router address receiving the output token |
| `deadlineBlock` | Last block in which the call may execute, inclusive |

1. Fund the caller with `amountIn`. If the caller is your router, follow the
   [funding rules](#funding-through-an-aggregator) below.
2. From that account, approve the **pool contract** to spend the input token.
   ThogAMM pulls input with `transferFrom`; do not pre-transfer input to the pool.
3. Encode the call using the ABI. Set the transaction destination to the pool
   and native value to zero.
4. Simulate the complete route with its actual sender, funding, allowances,
   recipient, minimum output, deadline, and transaction fees. Estimate gas from
   this route.
5. Submit the transaction through your router. The call reverts atomically if
   its deadline, minimum output, transfer, or inventory checks fail.

The return value is the recipient's guaranteed raw output. For tokens that round
transfers, its actual balance increase can be larger. Check
`received >= amountOut`. If the router receives output and forwards it, enforce
the route's minimum on the final recipient's balance increase.

## Funding through an aggregator

The listed **xStocks** are tokenized equities. Their contracts record balances
as integer **shares** and use a **multiplier** to convert shares into ERC-20 token
amounts. The multiplier is scaled by `1e18`:

```text
token amount = floor(shares × multiplier / 1e18)
shares moved by a transfer = floor(token amount × 1e18 / multiplier)
```

These floors mean that a requested transfer and the recipient's balance increase
can differ by a few raw units. Each transfer rounds independently, including
user → router, router → ThogAMM, and router → final recipient.

If your router first pulls funds from a user, measure only what that transfer
adds to the router:

```text
before = tokenIn.balanceOf(router)
transferFrom(user, router, requestedAmount)
amountIn = tokenIn.balanceOf(router) - before
```

Use this `amountIn` for the ThogAMM leg. During route construction, simulate the
funding transfer to determine it; during execution, measure it. Do not include
funds the router held before this trade. Refund residual input through the
router's normal refund mechanism.

The contract and SDK execution quotes include the rounding for ThogAMM's own
transfers and provide the output guarantee described above. Do not subtract an
additional rounding allowance from that guarantee. Sending output directly to
the final recipient avoids a forwarding transfer.

## Quotes, limits and settlement

**Price age.** The pool stores a price publication block, a maximum age, and a
spread increase per elapsed block. Quotes use the requested evaluation block:
older prices widen the spread, and prices beyond the configured maximum age
are unavailable. Read these parameters from pool state. Keeping a snapshot in
memory does not stop its prices from aging.

**Execution adjustment.** Settlement can reduce output according to the
transaction's effective gas price, the block's base fee, whether prices were
published in that block, and whether the FastLane AuctionHandler account is
warm. An account is warm when the transaction has already accessed it or included
it in its access list. The AuctionHandler address is
`0xD32EdF6642D917DbBE7B8BF8e5d6F5df6a9FFF58`.

For EIP-1559, effective gas price is
`min(maxFeePerGas, baseFee + maxPriorityFeePerGas)`. Supply the intended transaction
fees when simulating settlement. For state reads, use `gasPrice: 0x1` so Monad
RPC preserves the block's base fee. The [integer reference](REFERENCE.md#exact-output-marginal-prices-and-settlement)
specifies the execution adjustment and its rounding.

**Inventory limits.** Read-only quotes apply 90% thresholds to configured
inventory caps. Settlement checks full caps using actual transfer deltas.
`getLimits(poolId, tokenIn, tokenOut)` returns `[sellLimit, buyLimit]` in raw input
and output units respectively. These are separate upper bounds; an amount below
a limit must also satisfy the quote's price, direction, and portfolio checks.

A quote models one trade against one state. Independently quoting two trades
against that state does not model their sequential execution. If a route visits
ThogAMM more than once, simulate the complete route so each visit sees the effects
of the preceding visits.

## Calculate quotes locally

Both Rust SDKs calculate quotes without network calls. Use **SDK 0.6.1** with
the deployment listed above; Rust 1.88 or later is required.

| SDK | How it obtains state |
| --- | --- |
| [Polling SDK](https://github.com/thogard785/thog-amm-poll-sdk) | Reads a complete snapshot over HTTP on each refresh |
| [Event SDK](https://github.com/thogard785/thog-amm-event-sdk) | Loads one snapshot, then applies complete finalized blocks from a Monad WebSocket subscription |

A minimal Cargo manifest for the polling SDK is:

```toml
[package]
name = "thogamm-adapter"
version = "0.1.0"
edition = "2024"
rust-version = "1.88"

[dependencies]
state-poll-sdk = { git = "https://github.com/thogard785/thog-amm-poll-sdk", tag = "v0.6.1" }
tokio = { version = "1", features = ["macros", "rt-multi-thread"] }
```

Edition 2024 uses Cargo resolver 3. For an application in an existing workspace,
set `resolver = "3"` at the workspace root and declare the application's
`rust-version`. Commit `Cargo.lock` to keep dependency versions reproducible.

Save this as `src/main.rs`. It reads the pool and prints an execution quote for
100 USDC → WETH; it does not submit a transaction. Set `MONAD_RPC` and
`EFFECTIVE_GAS_PRICE_WEI` to your endpoint and intended effective gas price in wei,
then run `cargo run --release`.

```rust
use state_poll_sdk::{Config, StatePollSdk, U256};

#[tokio::main]
async fn main() -> Result<(), Box<dyn std::error::Error>> {
    let rpc = std::env::var("MONAD_RPC")?;
    let gas_price: U256 = std::env::var("EFFECTIVE_GAS_PRICE_WEI")?.parse()?;
    let proxy = "0x80c74517BCC2D67fFE02D3ED886796272F647210".parse()?;
    let usdc = "0x754704Bc059F8C67012fEd69BC8A327a5aafb603".parse()?;
    let weth = "0xEE8c0E9f1BFFb4Eb878d8f15f368A02a35481242".parse()?;

    let sdk = StatePollSdk::connect(rpc, proxy, Config::default()).await?;
    let model = sdk.model();
    let quote = model.quote_execution_exact_input(
        usdc, weth, U256::from(100_000_000u64), gas_price,
    )?;
    println!("block={} amount_out={}", model.state().block.number, quote.amount_out);
    Ok(())
}
```

In your aggregator, keep the client for subsequent quotes. With a mutable client,
`refresh()` reads immediately; `next_update()` waits for the configured interval,
500 ms by default, then reads. A [runnable polling example](https://github.com/thogard785/thog-amm-poll-sdk/blob/v0.6.1/examples/poll.rs)
and [event subscription example](https://github.com/thogard785/thog-amm-event-sdk/blob/v0.6.1/examples/subscribe.rs)
show application setup and environment variables.

| Method on `sdk.model()` | Result |
| --- | --- |
| `quote_exact_input(in, out, amount)` | Matches the read-only contract quote |
| `quote_execution_exact_input(in, out, amount, gasPrice)` | Models direct `makerSwapExactInput` settlement |
| `quote_exact_output(in, out, target, gasPrice)` | Required input for an ERC-7815 Buy |
| `limits(in, out)` | Separate sell and buy upper bounds |
| `marginal_price(in, out, amount)` | Fraction of raw output units per raw input unit at that size |

Execution methods assume a cold AuctionHandler and no integrator fee. The
`*_with_context` variants take `auction_handler_warm` as their final argument.
`model.at_block(number, baseFee)` evaluates age and execution fees at a chosen
block while holding the snapshot's inventory, prices, and parameters fixed; it
does not fetch or predict intervening state changes.

For several sizes of the same pair, call `model.prepare(tokenIn, tokenOut)` once
and quote the returned pair. Rebuild it after a state update. Keep the snapshot's
`model.state().block.number` and `.hash` with quotes so the router knows which
state they used. A refresh or stream error leaves the last snapshot in memory;
handle the error and obtain current state before serving it as a fresh quote.

## Read a complete snapshot

This section is for a custom reader or a pricing model in another language. The
SDKs perform these reads for you.

1. Read a block header and select its hash.
2. At that hash, call `getPoolData(0, 28)`. Decode the returned token metadata,
   category metadata, logical storage words, physical balances, and native MON
   balance using the ABI. Check the returned block number and parent hash against
   the header. The parent hash is not the selected block's hash.
3. For every listed xStock, read `sharesOf(proxy)` on the **token contract** and
   `storedMultiplier(token)` on the **ThogAMM pool**, at the same block hash. The
   pool getter returns a single `uint256`.
4. Build the quote model from this complete state, including tokens outside the
   requested pair. Validate schema 8, wire format 8, model 3, and the active
   registry using the [integer reference](REFERENCE.md).

ThogAMM uses its stored multiplier to value xStock shares. This value belongs to
the pool's pricing state; an issuer's current multiplier or `balanceOf(proxy)`
is not a substitute. The pool's `syncMultipliers` operation records a multiplier
and emits `MakerMultiplierUpdated`. Settlement checks that each stock transfer
moves the shares implied by the stored multiplier; a mismatch reverts with
`xstock: multiplier stale`.

## Maintain state from events

The event SDK subscribes to `logs` and `monadNewHeads`, loads a snapshot at a
finalized block hash, and publishes a model after each complete finalized block.
Use one ordered Monad subscription connection. Include all commitment stages so
the SDK can determine when each block's log stream is complete; generic Ethereum
`newHeads` does not provide that ordering information.

Apply xStock `TransferShares` events to physical shares and
`MakerMultiplierUpdated` to the pool's conversion value. The accompanying ERC-20
`Transfer` event must not apply the same stock movement a second time. Policy,
inventory, lending/perpetual exposure, WMON, and native-balance checkpoints are
also quote inputs. The [event rules](REFERENCE.md#snapshot-and-event-synchronization)
cover their ordering and accounting.

Advance the evaluation block even when there are no relevant logs. If the SDK reports a
stream disconnect or synchronization error, reconnect and load a complete snapshot. A
registry change requires a snapshot and rebuilt prepared pairs. An implementation
change requires checking that the chosen model supports that implementation.
Forced native transfers can lack logs; a custom reader needs account-state data
or a fresh snapshot to include them.

## Other settlement interfaces

### Collect an integrator fee

`swapWithExtraFees(tokenIn, tokenOut, amountIn, minAmountOut, expiry,
extraFeePpm, feeRecipient)` sends net output to **the caller**. `expiry` is an
inclusive Unix timestamp. The fee is
`floor(grossOutput × extraFeePpm / 1_000_000)`, with `extraFeePpm` in `0..1_000_000`.
`minAmountOut` protects net
output after that fee. SDK quotes exclude this integrator fee; simulate this
specific call when using it.

For a nonzero fee, `feeRecipient` must be a collection contract implementing:

```solidity
interface IFeeFundHolder {
    function checkSetFeeToken(address feeToken) external;
    function confirmFee(
        address feeToken, uint256 feeTokenAmount, uint256 feeUsdValueWad
    ) external;
}
```

ThogAMM calls these methods before transferring the fee, with gas limits of
150,000 and 25,000 respectively. `feeUsdValueWad` is the fee's USD value scaled
by `1e18`. A failed callback reverts the swap.

### ERC-7815 Sell and Buy

`swap(poolId, sellToken, buyToken, side, specifiedAmount)` pulls tokens from the
caller and sends output back to that caller. `side=0` is Sell: the specified
amount is input and `Trade.calculatedAmount` is output. `side=1` is Buy: the
specified amount is the output guarantee and `Trade.calculatedAmount` is required
input. The [ABI](abi/ThogAMM.json) includes the complete `Trade` return structure.

This call performs settlement even under `eth_call`, so the simulated caller
needs funds and allowance. It has no minimum-output, maximum-input, or deadline
argument. Your enclosing router must enforce those protections. Direct swap and
ERC-7815 rounding differ; use the [exact settlement rules](REFERENCE.md#exact-output-marginal-prices-and-settlement)
for a custom model.

`price` returns marginal prices for its requested input sizes, not average
execution prices. `priceDerivative` and `swapToPrice` are unsupported.

## Listed tokens

The deployment has the following 17 tokens. Read `getTokens(poolId)` to confirm
current membership. The nine xStocks below are unwrapped tokens; their wrapped
counterparts are separate assets. Fee-on-transfer tokens are unsupported.

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


## Verify the adapter

Compare quote outputs against contract calls at the same block, with the same
input amounts and execution fees. Check exact integer outputs and agreement on
which requests revert. Test both directions for each supported pair, xStock
funding and output rounding, price-age expiry, and routes with multiple visits
to the pool.

The [verification guide](verification/README.md) provides captured contract
results, SDK test commands, and capture scripts. The [integer reference](REFERENCE.md)
defines the arithmetic and event rules for a custom implementation.
