#!/usr/bin/env python3
"""Bounded single-JVM-at-a-time C1 contracts. No game, no Gradle, no network."""
import datetime,hashlib,json,pathlib,subprocess,tempfile,sys
HERE=pathlib.Path(__file__).resolve().parent;ROOT=HERE.parents[1];WORK=ROOT/'source-workspace/forge-config-c1';SRC=WORK/'src/main/java';BUILD=HERE/'build';JDK=ROOT/'.toolchains/jdk-21.0.12.1+1/bin'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
 BUILD.mkdir(exist_ok=True)
 locks=json.loads((ROOT/'source-workspace/fml-unified/provenance/compile-classpath-lock.json').read_text())
 selected=['night-config/core/3.8.3','night-config/toml/3.8.3','guava/32.1.2','failureaccess/1.0.1','logging/1.2.7','commons-io/2.15.1','commons-lang3/3.14.0','log4j-api/2.22.1','log4j-core/2.22.1','log4j-slf4j2-impl/2.22.1','slf4j-api/2.0.9','bus/8.0.5','annotations/24.1.0','asm/9.8','asm-commons/9.8']
 artifacts=[x for x in locks['artifacts'] if any(s in x['path'] for s in selected)]
 for item in artifacts:assert sha(ROOT/item['path'])==item['sha256'],item['path']
 frozen=ROOT/'source-workspace/fml-unified/build/successor-client-api1/frozen-inputs/fml.jar';assert sha(frozen)=='0b414ff9ebabf1d91098fd3a36b341c1ac4532184df8c92127504982a9ab5c17'
 cp=':'.join([str(ROOT/x['path']) for x in artifacts]+[str(frozen)])
 classes=BUILD/'classes';classes.mkdir(exist_ok=True)
 sources=sorted(p for p in SRC.rglob('*.java') if p.name!='ModConfigs.java')+sorted((HERE/'stubs').rglob('*.java'))+sorted((HERE/'reference').rglob('*.java'))+sorted((HERE/'src').rglob('*.java'))
 receipt={'status':'RUNNING','startedUtc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'maxHeapMiB':512,'maxWorkers':1,'gameLaunched':False,'networkUsed':False,'runtimeAccepted':False,'compileInputs':artifacts,'commands':[],'sources':{str(p.relative_to(ROOT)):sha(p) for p in sources}}
 def run(name,cmd):
  receipt['commands'].append(cmd)
  result=subprocess.run(cmd,cwd=ROOT,text=True,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,timeout=120)
  (BUILD/(name+'.log')).write_text(result.stdout);print(result.stdout)
  receipt[name]={'exitCode':result.returncode,'log':str((BUILD/(name+'.log')).relative_to(ROOT))}
  receipt['status']='FAILED' if result.returncode else 'RUNNING'
  (BUILD/'receipt.json').write_text(json.dumps(receipt,indent=2)+'\n')
  if result.returncode:raise SystemExit(result.returncode)
 run('compile',[str(JDK/'javac'),'-J-Xmx512m','-J-XX:ActiveProcessorCount=1','-proc:none','--release','21','-encoding','UTF-8','-cp',cp,'-d',str(classes),*map(str,sources)])
 with tempfile.TemporaryDirectory(prefix='c1-common-',dir=BUILD) as tmp:
  run('contracts',[str(JDK/'java'),'-Xmx512m','-XX:ActiveProcessorCount=1','-Djava.awt.headless=true','-Dc1.test.root='+tmp,'-cp',str(classes)+':'+cp,'net.neoforged.fml.config.CommonConfigContractTest'])
  run('failure-order',[str(JDK/'java'),'-Xmx512m','-XX:ActiveProcessorCount=1','-Djava.awt.headless=true','-Dc1.test.root='+tmp,'-cp',str(classes)+':'+cp,'net.neoforged.fml.config.FailureOrderingTest'])
 receipt['status']='PURE_CONTRACT_PASS_GAME_UNVERIFIED_UNMERGED';receipt['finishedUtc']=datetime.datetime.now(datetime.timezone.utc).isoformat();(BUILD/'receipt.json').write_text(json.dumps(receipt,indent=2)+'\n')
if __name__=='__main__':main()
