# ThogAMM integration

ThogAMM is a market-maker pool on Monad. It swaps any of its listed tokens for
any other at prices its operator posts on-chain. This repository is for teams
integrating it into an aggregator or router.

Start with the **[integration guide](THOGAMM_AGGREGATOR_INTEGRATION.md)**.

| | |
| --- | --- |
| [Integration guide](THOGAMM_AGGREGATOR_INTEGRATION.md) | How to quote and swap, what makes the pool different, and the common pitfalls |
| [Reference](REFERENCE.md) | The state, arithmetic and events, specified exactly, for building your own model |
| [Polling SDK](https://github.com/thogard785/thog-amm-poll-sdk) | Rust: quote locally from state read over HTTP |
| [Event SDK](https://github.com/thogard785/thog-amm-event-sdk) | Rust: the same, kept current from a WebSocket subscription |
| [Contract ABI](abi/ThogAMM.json) | For encoding calls and decoding events |
| [Verification](verification/README.md) | Recorded contract results to test a model against |

Network: Monad mainnet, chain ID 143. Pool:
[`0x80c74517BCC2D67fFE02D3ED886796272F647210`](https://monadscan.com/address/0x80c74517BCC2D67fFE02D3ED886796272F647210).

To charge an integrator fee you need a fee recipient set up for you first:
message [@thogard](https://t.me/thogard) on Telegram or email
[alex@fastlane.finance](mailto:alex@fastlane.finance).
