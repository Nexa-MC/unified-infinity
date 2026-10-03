#!/usr/bin/env python3
"""Official-only javac compile: input fixtures never see C1 facade binaries."""
import datetime,hashlib,json,pathlib,subprocess,sys
H=pathlib.Path(__file__).resolve().parent;R=H.parents[1];B=H/'build/official-inputs';B.mkdir(parents=True,exist_ok=True);J=R/'.toolchains/jdk-21.0.12.1+1/bin/javac';U=R/'docs/four-loader/forge/upstream'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
lock=json.loads((R/'docs/four-loader/forge/source-lock.json').read_text());expected={pathlib.Path(a['path']).name:a['sha256'] for a in lock['artifacts']}
names=['forge-1.21.1-52.1.0-universal.jar','fmlcore-1.21.1-52.1.0.jar','javafmllanguage-1.21.1-52.1.0.jar','eventbus-6.2.27.jar']
cp=[]
for n in names:assert sha(U/n)==expected[n];cp.append(U/n)
libs=json.loads((R/'source-workspace/fml-unified/provenance/compile-classpath-lock.json').read_text())['artifacts']
for a in libs:
 if any(s in a['path'] for s in ['night-config/core/3.8.3','annotations/24.1.0']):
  p=R/a['path'];assert sha(p)==a['sha256'];cp.append(p)
receipt={'startedUtc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'heapMiB':512,'workers':1,'gameLaunched':False,'executedFixture':False,'inputs':[{'path':str(p.relative_to(R)),'sha256':sha(p)} for p in cp],'commands':[]}
for label,source in [('positive',H/'official-input/ForgeConfigLifecycleProbe.java'),('negative',H/'boundary/fixtures/NegativeConfigInputs.java')]:
 out=B/label;out.mkdir(exist_ok=True);cmd=[str(J),'-J-Xmx512m','-J-XX:ActiveProcessorCount=1','-proc:none','--release','21','-cp',':'.join(map(str,cp)),'-d',str(out),str(source)]
 result=subprocess.run(cmd,text=True,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,timeout=90)
 receipt['commands'].append({'command':cmd,'exitCode':result.returncode,'sourceSha256':sha(source)});(B/(label+'.log')).write_text(result.stdout);print(result.stdout)
 receipt['status']='COMPILE_PASS' if result.returncode==0 else 'FAILED';(B/'receipt.json').write_text(json.dumps(receipt,indent=2)+'\n')
 if result.returncode:sys.exit(result.returncode)
receipt['finishedUtc']=datetime.datetime.now(datetime.timezone.utc).isoformat();(B/'receipt.json').write_text(json.dumps(receipt,indent=2)+'\n');print('OFFICIAL_POSITIVE_AND_NEGATIVE_COMPILE_PASS')
