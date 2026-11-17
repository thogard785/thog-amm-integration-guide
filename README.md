# ThogAMM integration

ThogAMM is a market-maker pool on Monad. It swaps ERC-20 tokens using its own
inventory, with prices determined by published valuations and portfolio risk.
An aggregator can query the contract for quotes or calculate them locally with
a Rust SDK, then execute swaps through the pool contract.

Start with the **[integration guide](THOGAMM_AGGREGATOR_INTEGRATION.md)**. It walks
through a quote, transaction construction, token funding, and local state updates.

| Resource | Purpose |
| --- | --- |
| [Integration guide](THOGAMM_AGGREGATOR_INTEGRATION.md) | Contract addresses, token list, quote and swap instructions |
| [Polling SDK](https://github.com/thogard785/thog-amm-poll-sdk) | Read pool state over HTTP and calculate quotes locally |
| [Event SDK](https://github.com/thogard785/thog-amm-event-sdk) | Update the same quote model from finalized block subscriptions |
| [Contract ABI](abi/ThogAMM.json) | Encode calls and decode results and events |
| [Integer reference](REFERENCE.md) | Implement the pricing model and state decoder in another language |
| [Verification](verification/README.md) | Compare an implementation with recorded contract results |

Network: **Monad mainnet, chain ID 143**. Pool contract:
[`0x80c74517BCC2D67fFE02D3ED886796272F647210`](https://monadscan.com/address/0x80c74517BCC2D67fFE02D3ED886796272F647210).

## Verification

Contract comparison results and reproduction commands are in
[verification/README.md](verification/README.md).
