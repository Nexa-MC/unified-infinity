#!/usr/bin/env python3
"""Single-JVM-at-a-time actual transformer and real native bus/FileWatcher contracts."""
import datetime,hashlib,json,pathlib,subprocess,tempfile,zipfile,sys
H=pathlib.Path(__file__).resolve().parent;R=H.parents[1];W=R/'source-workspace/forge-config-c1';B=H/'build/real-integrations';B.mkdir(parents=True,exist_ok=True);J=R/'.toolchains/jdk-21.0.12.1+1/bin'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
locks=json.loads((R/'source-workspace/fml-unified/provenance/compile-classpath-lock.json').read_text())['artifacts']
select=['night-config/core/3.8.3','night-config/toml/3.8.3','guava/32.1.2','failureaccess/1.0.1','logging/1.2.7','commons-io/2.15.1','commons-lang3/3.14.0','log4j-api/2.22.1','log4j-core/2.22.1','log4j-slf4j2-impl/2.22.1','slf4j-api/2.0.9','bus/8.0.5','annotations/24.1.0','typetools/0.6.3','maven-artifact/3.8.5','asm/9.8','asm-commons/9.8','asm-tree/9.8','modlauncher/11.0.5','securejarhandler/3.0.8','mergetool/2.0.0']
inputs=[a for a in locks if any(s in a['path'] for s in select)]
for a in inputs:assert sha(R/a['path'])==a['sha256'],a['path']
frozen=R/'source-workspace/fml-unified/build/successor-client-api1/frozen-inputs'
for n,expected in [('fml.jar','0b414ff9ebabf1d91098fd3a36b341c1ac4532184df8c92127504982a9ab5c17'),('service.jar','c3b12c250751cc7f07bfeee487d893d8cde9baf187e0cbbc23b6f913b716194e')]:
 p=frozen/n;assert sha(p)==expected;inputs.append({'path':str(p.relative_to(R)),'sha256':expected})
cp=':'.join(str(R/a['path']) for a in inputs);classes=B/'classes';classes.mkdir(exist_ok=True)
sources=sorted((W/'src/main/java').rglob('*.java'))+sorted(p for p in (H/'integration-src').rglob('*.java') if p.name!='NativeWatchBaselineTest.java')+[H/'stubs/net/neoforged/fml/loading'/n for n in ['FMLPaths.java','FMLConfig.java','FMLEnvironment.java']]
receipt={'startedUtc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'status':'RUNNING','maxHeapMiB':512,'activeProcessors':1,'gameLaunched':False,'networkUsed':False,'actualNativeContainer':True,'actualNativeEventBus':True,'actualNightConfigWatcher':True,'bootstrapStubs':['FMLPaths','FMLConfig','FMLEnvironment'],'inputs':inputs,'sources':{str(p.relative_to(R)):sha(p) for p in sources},'commands':[]}
with zipfile.ZipFile(B/'tested-sources.zip','w',zipfile.ZIP_DEFLATED) as z:
 for p in sources:z.write(p,str(p.relative_to(R)))
def run(name,cmd,timeout=90):
 result=subprocess.run(cmd,cwd=R,text=True,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,timeout=timeout);(B/(name+'.log')).write_text(result.stdout);print(result.stdout)
 receipt['commands'].append({'name':name,'command':cmd,'exitCode':result.returncode});receipt['status']='RUNNING' if result.returncode==0 else 'FAILED';(B/'receipt.json').write_text(json.dumps(receipt,indent=2)+'\n')
 if result.returncode:sys.exit(result.returncode)
run('compile',[str(J/'javac'),'-J-Xmx512m','-J-XX:ActiveProcessorCount=1','-proc:none','--release','21','-cp',cp,'-d',str(classes),*map(str,sources)])
base=[str(J/'java'),'-Xmx512m','-XX:ActiveProcessorCount=1','-Djava.awt.headless=true']
run('transform',base+['-cp',str(classes)+':'+cp,'TransformContractTest',str(H/'build/official-inputs/positive'),str(H/'build/official-inputs/negative')])
with tempfile.TemporaryDirectory(prefix='c1-real-watch-',dir=B) as temp:
 run('watch-bus',base+['-Dc1.test.root='+temp,'-cp',str(classes)+':'+cp,'net.neoforged.fml.config.RealWatchBusContractTest'],60)
receipt['status']='REAL_TRANSFORM_WATCH_BUS_PASS_GAME_UNVERIFIED_UNMERGED';receipt['finishedUtc']=datetime.datetime.now(datetime.timezone.utc).isoformat();(B/'receipt.json').write_text(json.dumps(receipt,indent=2)+'\n')
