#!/usr/bin/env python3
import datetime,hashlib,json,pathlib,subprocess,tempfile,sys
H=pathlib.Path(__file__).resolve().parent;R=H.parents[1];B=H/'build/native-baseline';B.mkdir(exist_ok=True);J=R/'.toolchains/jdk-21.0.12.1+1/bin'
prior=json.loads((H/'build/real-integrations/receipt.json').read_text());inputs=[a for a in prior['inputs'] if not a['path'].endswith('/service.jar')]
for a in inputs:assert hashlib.sha256((R/a['path']).read_bytes()).hexdigest()==a['sha256']
cp=':'.join(str(R/a['path']) for a in inputs);classes=B/'classes';classes.mkdir(exist_ok=True)
sources=[H/'integration-src/net/neoforged/fml/config/NativeWatchBaselineTest.java',H/'reference/net/neoforged/neoforge/common/ModConfigSpec.java']+[H/'stubs/net/neoforged/fml/loading'/n for n in ['FMLPaths.java','FMLConfig.java','FMLEnvironment.java']]
report={'status':'RUNNING','maxHeapMiB':512,'activeProcessors':1,'gameLaunched':False,'owner':'unchanged frozen fml.jar','inputs':inputs,'sources':{str(p.relative_to(R)):hashlib.sha256(p.read_bytes()).hexdigest() for p in sources},'commands':[]}
def run(name,cmd):
 result=subprocess.run(cmd,cwd=R,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,timeout=75);(B/(name+'.log')).write_text(result.stdout);print(result.stdout);report['commands'].append({'name':name,'command':cmd,'exitCode':result.returncode});(B/'receipt.json').write_text(json.dumps(report,indent=2)+'\n')
 if result.returncode:sys.exit(result.returncode)
run('compile',[str(J/'javac'),'-J-Xmx512m','-J-XX:ActiveProcessorCount=1','--release','21','-proc:none','-cp',cp,'-d',str(classes),*map(str,sources)])
for barrier in ['false','true']:
 with tempfile.TemporaryDirectory(prefix='c1-native-',dir=B) as tmp:
  run('barrier-'+barrier,[str(J/'java'),'-Xmx512m','-XX:ActiveProcessorCount=1','-Dc1.test.root='+tmp,'-cp',str(classes)+':'+cp,'net.neoforged.fml.config.NativeWatchBaselineTest',barrier])
report['status']='OBSERVATIONS_COMPLETE';report['finishedUtc']=datetime.datetime.now(datetime.timezone.utc).isoformat();(B/'receipt.json').write_text(json.dumps(report,indent=2)+'\n')
