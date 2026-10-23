// SPDX-License-Identifier: MIT
pragma solidity 0.8.28;
import {DeployedTest, IThogAMM} from "./Deployed.t.sol";

// Run with --network monad --isolate; each measured pool call starts cold.
contract GasTest is DeployedTest {
    function measure(bytes memory data) internal returns (bool ok, uint256 cost) {
        uint256 snap = vm.snapshotState();
        vm.txGasPrice(block.basefee);
        vm.prank(CALLER, CALLER);
        (ok,) = PROXY.call(data);
        cost = vm.lastCallGas().gasTotalUsed;
        vm.revertToStateAndDelete(snap);
    }
    function test_captureGas() public {
        string memory file = "../fixtures/gas-v7.jsonl";
        vm.writeFile(file, "");
        for (uint256 i; i < state.tokens.length; ++i) for (uint256 j; j < state.tokens.length; ++j) {
            if (i == j) continue;
            for (uint256 size; size < 3; ++size) {
                uint256 usd = size == 0 ? 1 : size == 1 ? 100 : 5000;
                uint256 amount = usd * 1e18 * 10**state.tokens[i].decimals / price(i);
                (bool ok, uint256 cost) = measure(abi.encodeWithSignature(
                    "makerSwapExactInput(address,address,uint256,uint256,address,uint256)",
                    state.tokens[i].token, state.tokens[j].token, amount, 0, CALLER, block.number));
                vm.serializeString("gas", "method", "makerSwapExactInput");
                vm.serializeUint("gas", "inputIndex", i); vm.serializeUint("gas", "outputIndex", j);
                vm.serializeUint("gas", "usdSize", usd); vm.serializeBool("gas", "success", ok);
                vm.writeLine(file, vm.serializeUint("gas", "gas", cost));
                uint256 target = usd * 1e18 * 10**state.tokens[j].decimals / price(j);
                (ok, cost) = measure(abi.encodeWithSignature("swap(bytes32,address,address,uint8,uint256)",
                    POOL, state.tokens[i].token, state.tokens[j].token, 1, target));
                vm.serializeString("gas", "method", "Buy"); vm.serializeBool("gas", "success", ok);
                vm.writeLine(file, vm.serializeUint("gas", "gas", cost));
            }
        }
        (bool ok, uint256 cost) = measure(abi.encodeCall(IThogAMM.getPoolData, (0, 32)));
        vm.serializeString("snapshot", "method", "getPoolData"); vm.serializeBool("snapshot", "success", ok);
        vm.writeLine(file, vm.serializeUint("snapshot", "gas", cost));
    }
}
