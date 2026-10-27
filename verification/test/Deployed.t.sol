// SPDX-License-Identifier: MIT
pragma solidity 0.8.28;
import {Test} from "forge-std/Test.sol";
import {stdStorage, StdStorage} from "forge-std/StdStorage.sol";
import {Vm} from "forge-std/Vm.sol";
interface IThogAMM {
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


    function getPoolData(uint8 start, uint8 stop) external view returns (PoolData memory);
    function makerSwapExactInput(address tokenIn,address tokenOut,uint256 amountIn,uint256 minimum,address recipient,uint256 deadline) external returns(uint256);
    function swap(bytes32 poolId,address tokenIn,address tokenOut,uint8 side,uint256 amount) external returns(bytes memory);
}
interface IToken {
    function approve(address,uint256) external returns(bool);
    function transfer(address,uint256) external returns(bool);
    function balanceOf(address) external view returns(uint256);
}
contract DeployedTest is Test {
    using stdStorage for StdStorage;

    address constant PROXY=0x80c74517BCC2D67fFE02D3ED886796272F647210;
    address constant AUCTION=0xD32EdF6642D917DbBE7B8BF8e5d6F5df6a9FFF58;
    bytes32 constant POOL=0xce389e78282dedac7b18ba7f775b7602d2ab3ab171bbd6711eb0239be6ef4dcc;
    address constant CALLER=address(0xBEEF);
    string constant OUTPUT="../fixtures/execution-v8.jsonl";
    IThogAMM.PoolData state;
    function setUp() public {
        vm.createSelectFork(vm.envOr("MONAD_RPC",string("https://rpc.monad.xyz")),117074438);
        state=IThogAMM(PROXY).getPoolData(0,28);
        assertEq(state.schemaVersion,8); assertEq(state.tokens.length,13);
        for(uint256 i;i<state.tokens.length;i++) {
            address token=state.tokens[i].token;
            fund(token,1e30);
            vm.prank(CALLER); IToken(token).approve(PROXY,type(uint256).max);
        }
    }
    // Fund only the test caller. AUSD stores a packed balance, so discover
    // its field without changing token code or the pool's inventory.
    function fund(address token,uint256 amount) internal {
        bytes memory query=abi.encodeWithSignature(isStock(token) ? "sharesOf(address)" : "balanceOf(address)",CALLER);
        vm.record(); (bool ok,)=token.staticcall(query); assertTrue(ok);
        (bytes32[] memory slots,)=vm.accesses(token);
        for(uint256 i=slots.length;i>0;i--) {
            bytes32 old=vm.load(token,slots[i-1]);
            for(uint256 shift;shift<=128;shift+=8) {
                vm.store(token,slots[i-1],bytes32(amount<<shift));
                (bool success,bytes memory answer)=token.staticcall(query);
                if(success && answer.length==32 && abi.decode(answer,(uint256))==amount) return;
                vm.store(token,slots[i-1],old);
            }
        }
        revert("cannot fund test caller");
    }
    function price(uint256 i) internal view returns(uint256) {
        uint256 w=state.words[20+i/4-2].value >> (i%4*64);
        uint64 packed=uint64(w);
        return uint256(uint56(packed))*10**(18-uint8(packed>>56));
    }
    function isStock(address token) internal view returns(bool) {
        for(uint256 i=8;i<state.tokens.length;i++) if(state.tokens[i].token==token) return true;
        return false;
    }
    function snapshotJson(string memory key,IThogAMM.PoolData memory p) internal returns(string memory) {
        address[] memory tokens=new address[](p.tokens.length-8);
        uint256[] memory shares=new uint256[](tokens.length);
        uint256[] memory multipliers=new uint256[](tokens.length);
        for(uint256 i;i<tokens.length;i++) {
            tokens[i]=p.tokens[i+8].token;
            (bool ok,bytes memory data)=tokens[i].staticcall(abi.encodeWithSignature("sharesOf(address)",PROXY));
            assertTrue(ok);shares[i]=abi.decode(data,(uint256));
            (ok,data)=tokens[i].staticcall(abi.encodeWithSignature("getCurrentMultiplier()"));
            assertTrue(ok);(multipliers[i],,)=abi.decode(data,(uint256,uint256,uint256));
        }
        vm.serializeAddress(key,"shareTokens",tokens);
        vm.serializeUint(key,"shares",shares);vm.serializeUint(key,"multipliers",multipliers);
        return vm.serializeBytes(key,"snapshot",abi.encode(p));
    }
    // Small integration checks use deployed token/Thog code, not SDK arithmetic.
    function integrationMultiplier(address token,uint256 world) internal {
        uint256 multiplier=world==0?1e18:world==1?1234567890123456789:3100000000000000001;
        vm.store(token,bytes32(uint256(0x10b)),bytes32(multiplier));
        vm.store(token,bytes32(uint256(0x10c)),bytes32(0));
    }
    function test_integrationBuyGuaranteesTargetButCreditsMore() public {
        for(uint256 world;world<3;world++) for(uint256 i=8;i<state.tokens.length;i++) {
            uint256 checkpoint=vm.snapshotState();
            address token=state.tokens[i].token;
            integrationMultiplier(token,world);
            // Some listed stocks have no pool inventory at the capture block.
            vm.prank(CALLER); assertTrue(IToken(token).transfer(PROXY,1e18));
            uint256 beforeOut=IToken(token).balanceOf(CALLER);
            vm.txGasPrice(2*block.basefee); vm.cool(AUCTION);
            vm.prank(CALLER);
            // Buy fixes guaranteed output at one raw unit; it returns input required.
            (bool success,)=PROXY.call(abi.encodeWithSignature(
                "swap(bytes32,address,address,uint8,uint256)",POOL,state.tokens[0].token,token,1,1
            ));
            assertTrue(success);
            uint256 received=IToken(token).balanceOf(CALLER)-beforeOut;
            assertGt(received,1,"actual xStock credit can exceed the Buy target");
            assertTrue(vm.revertToStateAndDelete(checkpoint));
        }
    }
    function test_integrationFundingUsesNewCreditAndPreservesExistingFunds() public {
        address router=address(0xCAFE); address recipient=address(0xD00D);
        uint256 roundedFundingCases;
        for(uint256 world;world<3;world++) for(uint256 i=8;i<state.tokens.length;i++) {
            uint256 checkpoint=vm.snapshotState();
            IToken token=IToken(state.tokens[i].token);
            integrationMultiplier(address(token),world);
            // Isolate transfer semantics from caps exceeded by a synthetic rebase.
            setField(101+i/10,i%10*24,24,0xffffff);
            uint256 category=state.tokens[i].category;
            setField(104+category/10,category%10*24,24,0xffffff);
            // Unrelated input already held by the router must not enter this swap.
            vm.prank(CALLER); assertTrue(token.transfer(router,37));
            uint256 beforeIn=token.balanceOf(router);
            uint256 requestedIn=1e36/price(i)+7;
            vm.prank(CALLER); assertTrue(token.transfer(router,requestedIn));
            uint256 amountIn=token.balanceOf(router)-beforeIn;
            if(amountIn<requestedIn) roundedFundingCases++;
            vm.prank(router); assertTrue(token.approve(PROXY,amountIn));
            IToken output=IToken(state.tokens[0].token);
            uint256 beforeOut=output.balanceOf(recipient);
            vm.txGasPrice(2*block.basefee); vm.cool(AUCTION);
            vm.prank(router);
            uint256 guaranteedOut=IThogAMM(PROXY).makerSwapExactInput(
                address(token),address(output),amountIn,1,recipient,block.number
            );
            assertGe(output.balanceOf(recipient)-beforeOut,guaranteedOut);
            assertGe(token.balanceOf(router),beforeIn,"unrelated input was spent");
            assertTrue(vm.revertToStateAndDelete(checkpoint));
        }
        assertGt(roundedFundingCases,0,"exercise funding below requested amount");
    }
    function test_captureExecution() public {
        vm.writeFile(OUTPUT,"");
        for(uint256 world;world<3;world++) {
            uint256 checkpoint=vm.snapshotState();
            this.captureExecutionWorld(world);
            assertTrue(vm.revertToStateAndDelete(checkpoint));
        }
    }
    function captureExecutionWorld(uint256 world) external {
        if(world!=0) {
            for(uint256 i=8;i<state.tokens.length;i++) {
                address token=state.tokens[i].token;
                vm.store(token,bytes32(uint256(0x10b)),bytes32(world==1?uint256(1234567890123456789):uint256(3100000000000000001)));
                vm.store(token,bytes32(uint256(0x10c)),bytes32(0));
            }
            state=IThogAMM(PROXY).getPoolData(0,28);
        }
        vm.serializeUint("snapshot","world",world);
        string memory json=snapshotJson("snapshot",state);
        vm.writeLine(OUTPUT,json);
        for(uint256 i;i<state.tokens.length;i++) for(uint256 j;j<state.tokens.length;j++) {
            if(i==j) continue;
            for(uint256 context;context<3;context++) {
                for(uint256 a;a<6;a++) {
                    uint256 usd=a==2?1:a==3?100:a==4?1000:5000;
                    uint256 amount=a==0?0:a==1?1:usd*1e18*10**state.tokens[i].decimals/price(i);
                    capture(i,j,amount,context,false);
                }
                for(uint256 a;a<4;a++) {
                    uint256 usd=a==2?1:100;
                    uint256 target=a==0?0:a==1?1:usd*1e18*10**state.tokens[j].decimals/price(j);
                    capture(i,j,target,context,true);
                }
            }
        }
    }
    struct EventSet { bytes beforeState; bytes afterState; Vm.Log[] logs; }
    function capturePublication(bytes memory data) internal returns(EventSet memory e) {
        e.beforeState=abi.encode(IThogAMM(PROXY).getPoolData(0,28));
        vm.roll(block.number+1);vm.recordLogs();
        vm.prank(0xA01E5634faA6242EB079c3D6d1B545d163659234);
        (bool success,bytes memory reason)=PROXY.call(data);if(!success) assembly {revert(add(reason,32),mload(reason))}
        e.logs=vm.getRecordedLogs();e.afterState=abi.encode(IThogAMM(PROXY).getPoolData(0,28));
    }
    function test_capturePublications() public {
        setField(2,134,2,0);setField(27,255,1,1);setField(9,250,1,1);
        uint256 n=state.tokens.length;uint256 c=state.categories.length;
        uint256 catWords=(c+2)/3;uint256 covWords=(c*(c+1)/2+15)/16;
        uint256 policyWords=(n+4)/5;uint256 pairWords=(n*(n-1)/2+15)/16;
        uint256[] memory risk=new uint256[](1+catWords+covWords+policyWords+pairWords);
        uint256 control=state.words[0].value;
        uint256 generation=(state.words[8-2].value>>184)&type(uint32).max;
        uint256 lending=(state.words[7-2].value>>160)&type(uint32).max;
        risk[0]=8|(n<<8)|(c<<16)|(uint256(17)<<24)|(((control>>138)&255)<<56)|(((control>>146)&65535)<<64)|(lending<<112)|(generation<<144);
        uint256 cursor=1;
        for(uint256 i;i<catWords;i++)risk[cursor++]=state.words[27+i-2].value;
        risk[1]=(risk[1]&~(uint256(31)<<80))|(uint256(2)<<80);
        for(uint256 i;i<covWords;i++)risk[cursor++]=state.words[37+i-2].value;
        for(uint256 i;i<n;i++) {
            uint256 token=state.words[9+i/3-2].value>>(i%3*75);
            uint256 policy=((token>>15)&65535)|(((token>>43)&65535)<<16)|(uint256(37+i)<<32);
            risk[cursor+i/5]|=policy<<(i%5*48);
        }
        cursor+=policyWords;
        for(uint256 i;i<pairWords;i++)risk[cursor++]=state.words[63+i-2].value;
        bytes memory packed;for(uint256 i;i<risk.length;i++)packed=bytes.concat(packed,bytes32(risk[i]));
        EventSet[] memory events=new EventSet[](3);
        events[0]=capturePublication(abi.encodeWithSignature("pushRiskParams(bytes)",packed));
        uint256 wrapperWords=(n+2)/3;
        uint256[] memory wrapper=new uint256[](1+wrapperWords+(c+3)/4);wrapper[0]=8|(n<<8)|(c<<16)|(generation<<32);
        for(uint256 i;i<n;i++) {
            uint256 token=state.words[9+i/3-2].value>>(i%3*75);
            uint256 coefficient=(state.words[87+i/4-2].value>>(i%4*64))&type(uint64).max;
            uint256 field=coefficient|(((token>>31)&4095)<<64);
            wrapper[1+i/3]|=field<<(i%3*76);
        }
        for(uint256 i;i<(c+3)/4;i++)wrapper[1+wrapperWords+i]=state.words[94+i-2].value;
        packed="";for(uint256 i;i<wrapper.length;i++)packed=bytes.concat(packed,bytes32(wrapper[i]));
        events[1]=capturePublication(abi.encodeWithSignature("pushWrapperParams(bytes)",packed));
        address[] memory addresses=new address[](3);addresses[0]=state.tokens[1].token;addresses[1]=state.tokens[0].token;addresses[2]=state.tokens[1].token;
        uint256[] memory limits=new uint256[](3);limits[0]=987654321;limits[1]=type(uint256).max;limits[2]=0;
        uint8[] memory categories=new uint8[](2);categories[0]=2;categories[1]=0;
        uint256[] memory catLimits=new uint256[](2);catLimits[0]=0;catLimits[1]=12345678901234567890123456;
        events[2]=capturePublication(abi.encodeWithSignature("setInventoryCaps(address[],uint256[],uint8[],uint256[])",addresses,limits,categories,catLimits));
        vm.writeFileBinary("../fixtures/events-fork-v8.bin",abi.encode(events));
    }
    function setField(uint256 slot,uint256 offset,uint256 width,uint256 value) internal {
        uint256 word=uint256(vm.load(PROXY,bytes32(slot)));if(word==1<<255)word=0;
        uint256 mask=((uint256(1)<<width)-1)<<offset;
        word=(word&~mask)|((value<<offset)&mask);
        vm.store(PROXY,bytes32(slot),bytes32(word==0?1<<255:word));
    }
    function test_captureBoundaries() public {
        string memory file="../fixtures/boundaries-v8.jsonl";vm.writeFile(file,"");
        for(uint256 world;world<14;world++) {
            uint256 checkpoint=vm.snapshotState();
            this.captureBoundaryWorld(file,world);
            assertTrue(vm.revertToStateAndDelete(checkpoint));
        }
    }
    function captureBoundaryWorld(string memory file,uint256 world) external {
            if(world==1) setField(2,162,32,0); // Lambda zero retains volume cost.
            if(world==2) { // Fixed input/output wrappers on USDC/AUSD.
                setField(9,31,12,1);setField(9,75+31,12,1);
                setField(87,0,64,17e14);setField(87,64,64,31e14);
            }
            if(world==3) { // Strong output refund near its positive-slope boundary.
                setField(9,75+31,12,2|(1000<<2));setField(87,64,64,2e18);
            }
            if(world==4) { // Nonpositive wrapper value must fail explicitly.
                setField(9,75+31,12,2|(1000<<2));setField(87,64,64,type(uint64).max);
                setField(94,0,64,1);
            }
            if(world==5) { // Small receiving token cap and infinite category cap.
                setField(101,0,24,(20<<16)|40000);setField(104,0,24,0xffffff);
            }
            if(world==6) { // Zero receiving category cap.
                setField(104,0,24,0);
            }
            if(world==7) { // Maximum accepted age.
                uint256 maxAge=(state.words[0].value>>138)&255;uint256 posted=(state.words[0].value>>36)&type(uint32).max;
                vm.roll(posted+maxAge);
            }
            if(world==8) { // First stale block.
                uint256 maxAge=(state.words[0].value>>138)&255;uint256 posted=(state.words[0].value>>36)&type(uint32).max;
                vm.roll(posted+maxAge+1);
            }
            if(world==9 || world==10) {
                // Exercise transfer-share floors with non-unit multipliers.
                for(uint256 i=8;i<state.tokens.length;i++) {
                    address token=state.tokens[i].token;
                    vm.store(token,bytes32(uint256(0x10b)),bytes32(world==9?uint256(1234567890123456789):uint256(3100000000000000001)));
                    vm.store(token,bytes32(uint256(0x10c)),bytes32(0));
                }
            }
            if(world==11) { // Physical empty stock endpoints.
                for(uint256 i=8;i<state.tokens.length;i++) stdstore.target(state.tokens[i].token).sig("sharesOf(address)").with_key(PROXY).checked_write(uint256(0));
            }
            if(world==12) { // Physical donation stays outside non-endpoint ledger risk.
                for(uint256 i=8;i<state.tokens.length;i++) stdstore.target(state.tokens[i].token).sig("sharesOf(address)").with_key(PROXY).checked_write(uint256(100e18));
            }
            if(world==13) { // Inventory 1<<255 is valid data, not the old empty marker.
                vm.store(PROXY,bytes32(uint256(111)),bytes32(uint256(1)<<255));
                setField(121,4,1,0);
            }
            IThogAMM.PoolData memory p=IThogAMM(PROXY).getPoolData(0,28);
            vm.serializeUint("world","world",world);string memory header=snapshotJson("world",p);vm.writeLine(file,header);
            for(uint256 i;i<state.tokens.length;i++) for(uint256 j;j<state.tokens.length;j++) {
                if(i==j)continue;
                for(uint256 a;a<8;a++) {
                    uint256 usd=a==2?1:a==3?100:a==4?1000:a==5?2500:a==6?5000:25000;
                    uint256 amount=a==0?0:a==1?1:usd*1e18*10**state.tokens[i].decimals/price(i);
                    recordView(file,world,"quote",i,j,amount,abi.encodeWithSignature("makerQuoteExactInput(address,address,uint256)",state.tokens[i].token,state.tokens[j].token,amount));
                    if(a==0||a==4) {
                        uint256[] memory amounts=new uint256[](1);amounts[0]=amount;
                        recordView(file,world,"price",i,j,amount,abi.encodeWithSignature("price(bytes32,address,address,uint256[])",POOL,state.tokens[i].token,state.tokens[j].token,amounts));
                    }
                }
                recordView(file,world,"limits",i,j,0,abi.encodeWithSignature("getLimits(bytes32,address,address)",POOL,state.tokens[i].token,state.tokens[j].token));
            }
    }
    function recordView(string memory file,uint256 world,string memory method,uint256 i,uint256 j,uint256 amount,bytes memory data) internal {
        (bool success,bytes memory result)=PROXY.staticcall(data);
        vm.serializeUint("boundary","world",world);vm.serializeString("boundary","method",method);
        vm.serializeUint("boundary","inputIndex",i);vm.serializeUint("boundary","outputIndex",j);
        vm.serializeString("boundary","amount",vm.toString(bytes32(amount)));vm.serializeBool("boundary","success",success);
        string memory json=vm.serializeBytes("boundary","result",result);vm.writeLine(file,json);
    }
    function capture(uint256 i,uint256 j,uint256 amount,uint256 context,bool buy) internal {
        uint256 checkpoint=vm.snapshotState();
        uint256 gasPrice=context==1?2*block.basefee+1:2*block.basefee;
        vm.txGasPrice(gasPrice);
        vm.cool(AUCTION);
        // vm.cool followed by an account access reproduces the explicit warm context.
        if(context==2) { uint256 size=AUCTION.code.length; assertGt(size,0); }
        bytes memory data=buy?abi.encodeWithSignature("swap(bytes32,address,address,uint8,uint256)",POOL,state.tokens[i].token,state.tokens[j].token,1,amount)
            :abi.encodeWithSelector(IThogAMM.makerSwapExactInput.selector,state.tokens[i].token,state.tokens[j].token,amount,0,CALLER,block.number);
        vm.prank(CALLER);
        uint256 beforeGas=gasleft();
        (bool success,bytes memory result)=PROXY.call(data);
        uint256 used=beforeGas-gasleft();
        assertTrue(vm.revertToStateAndDelete(checkpoint));
        vm.serializeString("case","method",buy?"exactOutput":"execution");
        vm.serializeUint("case","inputIndex",i); vm.serializeUint("case","outputIndex",j);
        vm.serializeString("case","amount",vm.toString(bytes32(amount)));
        vm.serializeString("case","gasPrice",vm.toString(bytes32(gasPrice)));
        vm.serializeBool("case","auctionHandlerWarm",context==2);
        vm.serializeBool("case","success",success);
        vm.serializeUint("case","measuredGas",used);
        string memory json=vm.serializeBytes("case","result",result);
        vm.writeLine(OUTPUT,json);
    }
}
