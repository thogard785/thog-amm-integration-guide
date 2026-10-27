#!/usr/bin/env python3
"""Capture the pending model-3 implementation on a local Monad fork; never broadcast.

Usage: python3 tools/capture_model3.py /path/to/takerbot
Requires Monad Foundry. Preserves the historical model-2 fixture archives.
"""
import gzip
import hashlib
import json
from pathlib import Path
import subprocess
import re
import sys

root = Path(__file__).resolve().parent.parent
checkout = Path(sys.argv[1]).resolve()
output = root / 'fixtures/execution-model3.jsonl'
source = (root / 'verification/test/Deployed.t.sol').read_text()
source = source.replace('contract DeployedTest is Test', 'contract Model3CaptureTest is Test')
source = source.replace('import {Test}', '''import {TakerExecutor} from "../../src/TakerExecutor.sol";
import {ProxyAdmin} from "@openzeppelin/contracts/proxy/transparent/ProxyAdmin.sol";
import {ITransparentUpgradeableProxy} from "@openzeppelin/contracts/proxy/transparent/TransparentUpgradeableProxy.sol";
import {Test}''', 1)
source = source.replace('"../fixtures/execution-v8.jsonl"', json.dumps(str(output)))
source = source.replace('        state=IThogAMM(PROXY).getPoolData(0,28);', '''        // Upgrade only this local fork. The real pool is never mutated.
        bytes32 adminSlot=bytes32(uint256(keccak256("eip1967.proxy.admin"))-1);
        ProxyAdmin admin=ProxyAdmin(address(uint160(uint256(vm.load(PROXY,adminSlot)))));
        bytes32 nativeWord=vm.load(PROXY,bytes32(uint256(1)));
        bytes32 controlWord=vm.load(PROXY,bytes32(uint256(2)));
        setField(1,0,1,1);setField(2,132,1,1);
        TakerExecutor implementation=new TakerExecutor();
        vm.prank(admin.owner());
        admin.upgradeAndCall(ITransparentUpgradeableProxy(PROXY),address(implementation),
            abi.encodeWithSignature("migrateOnePage()"));
        vm.store(PROXY,bytes32(uint256(1)),nativeWord);
        vm.store(PROXY,bytes32(uint256(2)),controlWord);
        setField(2,146,16,50); // 0.50 bp per elapsed block.
        state=IThogAMM(PROXY).getPoolData(0,28);
        // Publish unchanged valuations through the real writer, before execution.
        uint256 control=state.words[0].value;
        uint16 sequence=uint16(control>>20)+1;if(sequence==0)sequence=1;
        uint256 header=uint256(sequence)|(((control>>133)&1)<<16)
            |(uint256(uint64(control>>68))<<17)|(uint256(state.tokenCount)<<81)
            |(uint256(8)<<89)|(((state.words[6].value>>184)&type(uint32).max)<<97);
        bytes memory prices=abi.encodePacked(header);
        for(uint256 i;i<(state.tokens.length+3)/4;i++) prices=bytes.concat(prices,bytes32(state.words[18+i].value));
        vm.prank(0xA01E5634faA6242EB079c3D6d1B545d163659234);
        (bool published,bytes memory reason)=PROXY.call(abi.encodeWithSignature("pushPrices(bytes)",prices));
        if(!published) assembly {revert(add(reason,32),mload(reason))}
        state=IThogAMM(PROXY).getPoolData(0,28);
        assertEq(uint8(state.words[6].value>>176),3);''', 1)
# Keep the existing settlement/funding helpers and capture code, excluding unrelated tests.
a=source.index('    // Small integration checks');b=source.index('    function test_captureExecution()')
source=source[:a]+source[b:]
source=source.replace('world<3','world<6').replace('        if(world!=0) {','        if(world>=3) vm.roll(block.number+1);\n        uint256 multiplierWorld=world%3;\n        if(multiplierWorld!=0) {')
source=source.replace('world==1?uint256(1234567890123456789)', 'multiplierWorld==1?uint256(1234567890123456789)')
source=source.replace('        vm.serializeUint("snapshot","world",world);', '        state=IThogAMM(PROXY).getPoolData(0,28);\n        vm.serializeUint("snapshot","blockNumber",block.number);\n        vm.serializeUint("snapshot","world",world);')
source=source.replace('context<3','context<7').replace('a<6','a<3').replace('a<4','a<2')
source=source.replace('uint256 target=a==0?0:a==1?1:usd*1e18*10**state.tokens[j].decimals/price(j);','uint256 target=a==0?1:1e18*10**state.tokens[j].decimals/price(j);')
a=source.index('    struct EventSet');b=source.index('    function setField(',a)
source=source[:a]+source[b:]
a=source.index('    function test_captureBoundaries');b=source.index('    function capture(',a)
source=source[:a]+source[b:]
source=source.replace('uint256 gasPrice=context==1?2*block.basefee+1:2*block.basefee;', '''uint256 gasPrice=context<2?block.basefee+block.basefee/2+context
            :context<4?2*block.basefee+(context-2)
            :context<6?2*block.basefee+block.basefee/2+(context-4):block.basefee;''')
source=source.replace('context==2','context==6')
source=source.replace('        vm.serializeBool("case","success",success);','        vm.serializeUint("case","context",context);\n        vm.serializeBool("case","success",success);')
source=source.replace('state=IThogAMM(PROXY).getPoolData(0,28);', '_setState(IThogAMM(PROXY).getPoolData(0,28));')
# The production compiler uses the legacy pipeline; copy nested arrays explicitly.
source=source.replace('    function setUp() public {', '''    function _setState(IThogAMM.PoolData memory p) internal {
        delete state;
        state.schemaVersion=p.schemaVersion;state.blockNumber=p.blockNumber;
        state.baseFeePerGas=p.baseFeePerGas;state.parentBlockHash=p.parentBlockHash;
        state.tokenCount=p.tokenCount;state.categoryCount=p.categoryCount;
        state.startTokenIndex=p.startTokenIndex;state.nativeBalance=p.nativeBalance;
        state.balances=p.balances;state.portfolioBalances=p.portfolioBalances;
        for(uint256 i;i<p.tokens.length;i++)state.tokens.push(p.tokens[i]);
        for(uint256 i;i<p.categories.length;i++)state.categories.push(p.categories[i]);
        for(uint256 i;i<p.words.length;i++)state.words.push(p.words[i]);
    }
    function setUp() public {''')
generated=checkout/'sol/test/generated/Model3Capture.t.sol'
generated.parent.mkdir(parents=True,exist_ok=True)
generated.write_text(source)
config=checkout/'sol/test/generated/model3-capture/foundry.toml'
config.parent.mkdir(parents=True,exist_ok=True)
settings=(checkout/'sol/foundry.toml').read_text()
settings=settings.replace('[profile.default]', '[profile.default]\ntest = '+json.dumps(str(checkout/'sol/test'))+'\nscript = '+json.dumps(str(checkout/'sol/script'))+'\ncache_path = '+json.dumps(str(checkout/'sol/cache')))
for key, path in [('src','src'),('out','out')]:
    settings=settings.replace(key+' = "'+path+'"', key+' = '+json.dumps(str(checkout/'sol'/path)),1)
settings=settings.replace('libs = ["lib"]', 'libs = ['+json.dumps(str(checkout/'sol/lib'))+']')
settings=settings.replace('maker-catalog/=src/', 'maker-catalog/='+str(checkout/'sol/src')+'/')
settings=re.sub(r'^fs_permissions = .*$',
    'fs_permissions = [{ access = "read-write", path = '+json.dumps(str(root/'fixtures'))+' }]',settings,flags=re.MULTILINE)
remappings=['maker-catalog/='+str(checkout/'sol/src')+'/']
for line in (checkout/'sol/remappings.txt').read_text().splitlines():
    if line.strip() and not line.startswith('#'):
        name,target=line.split('=',1)
        remappings.append(name+'='+str(checkout/'sol'/target)+'/')
settings=re.sub(r'^remappings = .*$', 'remappings = '+json.dumps(remappings),settings,count=1,flags=re.MULTILINE)
config.write_text(settings)
try:
    subprocess.run(['forge','test','--root',str(checkout/'sol'),'--config-path',str(config),'--network','monad','--match-contract','^Model3CaptureTest$',
                    '--match-test','test_captureExecution','--gas-limit','100000000000','-vv'],cwd=checkout/'sol',check=True)
finally:
    generated.unlink(missing_ok=True)
    config.unlink(missing_ok=True)
    config.parent.rmdir()
worlds=[]
for line in output.read_text().splitlines():
    row=json.loads(line)
    if 'snapshot' in row:
        row['shareBalances']={a.lower():{'shares':hex(int(b)),'multiplier':hex(int(m))}
            for a,b,m in zip(row.pop('shareTokens'),row.pop('shares'),row.pop('multipliers'))}
        row['cases']=[];worlds.append(row)
    else: worlds[-1]['cases'].append(row)
fixture={'schemaVersion':8,'modelVersion':3,'chainId':143,'proxy':'0x80c74517bcc2d67ffe02d3ed886796272f647210',
    'fork':True,'network':'monad','forkBlock':117074438,
    'implementation':'locally compiled and upgraded pending model 3; not deployed mainnet bytecode',
    'snapshots':worlds,
    'sourceSha256':{name:hashlib.sha256((checkout/name).read_bytes()).hexdigest() for name in [
        'sol/src/TakerExecutor.sol','sol/src/MakerQuotes.sol','sol/src/libraries/MakerRoutingMath.sol',
        'sol/src/libraries/ExecutorStorage.sol','sol/src/libraries/OnePageMigration.sol','sol/foundry.toml']}}
(root/'fixtures/execution-model3.json.gz').write_bytes(gzip.compress((json.dumps(fixture,separators=(',',':'))+'\n').encode(),mtime=0))
print(sum(len(w['cases']) for w in worlds),'execution cases;',sum(c['success'] for w in worlds for c in w['cases']),'successes')
