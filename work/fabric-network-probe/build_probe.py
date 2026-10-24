"""Compile against hash-pinned genuine game/API inputs and remap only this diagnostic probe.
No downloads, no Gradle, no game entrypoint, no implicit manifest classpath, no fake classes.
Caller must coordinate exclusive JVM admission before invoking this bounded script.
"""
import argparse, hashlib, json, math, os, pathlib, selectors, signal, subprocess, time, zipfile
from contextlib import contextmanager
R=pathlib.Path(__file__).resolve().parent;W=R.parent
sha=lambda p:hashlib.sha256(pathlib.Path(p).read_bytes()).hexdigest()
def require(x,s):
 if not x:raise ValueError(s)
def pin(p):
 p=pathlib.Path(p).resolve();return {'path':str(p),'bytes':p.stat().st_size,'sha256':sha(p)}
def verify(row):
 p=pathlib.Path(row['path']).resolve(strict=True);require(p.is_file() and p.stat().st_size>0,'nonempty input required');require(sha(p)==row['sha256'],'input hash mismatch');
 if 'bytes' in row:require(p.stat().st_size==row['bytes'],'input size mismatch')
 return p

def pack(path,entries):
 require(not path.exists(),'refusing artifact overwrite')
 with zipfile.ZipFile(path,'w',zipfile.ZIP_DEFLATED,compresslevel=9) as z:
  for n,b in sorted(entries.items()):
   i=zipfile.ZipInfo(n,(1980,1,1,0,0,0));i.compress_type=zipfile.ZIP_DEFLATED;i.external_attr=0o100644<<16;z.writestr(i,b)
_pending_stop=[]
def check_stop():
 if _pending_stop:raise InterruptedError('builder stopped by '+signal.Signals(_pending_stop[0]).name)
@contextmanager
def owned_stops():
 previous={}
 def record(number,frame):
  if not _pending_stop:_pending_stop.append(number)
 try:
  for number in (signal.SIGTERM,signal.SIGINT,signal.SIGHUP):
   old=signal.getsignal(number)
   if old!=signal.SIG_IGN:previous[number]=old;signal.signal(number,record)
  yield
  check_stop()
 finally:
  for number,handler in previous.items():signal.signal(number,handler)
def source_inventory(root,source):
 rows=source['files'];names=[row['path'] for row in rows]
 require(len(names)==len(set(names)),'duplicate source manifest path')
 for name in names:
  rel=pathlib.PurePosixPath(name);require(not rel.is_absolute() and '..' not in rel.parts,'invalid source path')
  path=root/rel;require(path.is_file() and not path.is_symlink(),'nonregular source input')
 actual={str(p.relative_to(root)) for p in (root/'src').rglob('*') if p.is_file()}
 expected={name for name in names if name.startswith('src/')}
 require(actual==expected,'source inventory differs before compiler')
 require(not any(p.is_symlink() for p in (root/'src').rglob('*')),'source symlink')
 java={str(p.relative_to(root)) for p in root.rglob('*.java')}
 # The clean publication tree must contain exactly the listed Java, including tool source.
 require(java=={name for name in names if name.endswith('.java')},'unlisted Java source')
 return ([root/name for name in sorted(names) if name.startswith('src/main/java/') and name.endswith('.java')],
         [root/name for name in sorted(names) if name.startswith('src/test/java/') and name.endswith('.java')])
def phase(name,argv,out,deadline):
 check_stop();remaining=min(90,deadline-time.monotonic());require(remaining>0,'overall build deadline')
 log=out/(name+'.log');begin=time.monotonic();count=0;proc=None;sel=None
 env={'PATH':'/usr/bin:/bin','HOME':str(out),'LANG':'C.UTF-8','LC_ALL':'C.UTF-8','TZ':'UTC'}
 try:
  # The outer bounded_process owner created this builder's session. Never escape it.
  proc=subprocess.Popen(argv,cwd=out,env=env,stdin=subprocess.DEVNULL,stdout=subprocess.PIPE,stderr=subprocess.STDOUT)
  check_stop();sel=selectors.DefaultSelector();sel.register(proc.stdout,selectors.EVENT_READ)
  with log.open('xb') as f:
   while sel.get_map():
    check_stop();require(time.monotonic()-begin<remaining,'phase timeout '+name)
    for key,_ in sel.select(min(.1,max(.001,remaining-(time.monotonic()-begin)))):
     b=os.read(key.fd,65536)
     if not b:sel.unregister(key.fileobj);continue
     count+=len(b);require(count<=1048576,'phase output cap '+name);f.write(b)
   while proc.poll() is None:
    check_stop();require(time.monotonic()-begin<remaining,'phase timeout '+name)
    time.sleep(.02)
   code=proc.returncode
 finally:
  if sel is not None:sel.close()
  if proc is not None:
   if proc.stdout is not None:proc.stdout.close()
   # Retained direct-child handle only. Whole-group cleanup belongs to the outer owner.
   if proc.poll() is None:proc.terminate()
   try:proc.wait(timeout=3)
   except subprocess.TimeoutExpired:proc.kill();proc.wait(timeout=3)
 check_stop();require(code==0,'phase failed '+name+'; read '+str(log))
 return {'name':name,'argv':argv,'exitCode':code,'log':pin(log) if log.stat().st_size else {'path':str(log),'bytes':0,'sha256':sha(log)},'elapsedSeconds':round(time.monotonic()-begin,3)}
def main():
 global R
 a=argparse.ArgumentParser();a.add_argument('--owned-session',action='store_true',required=True);a.add_argument('--source-root',type=pathlib.Path,required=True);a.add_argument('--config',type=pathlib.Path,required=True);a.add_argument('--config-sha256',required=True);a.add_argument('--output',type=pathlib.Path,required=True);a.add_argument('--deadline-epoch',type=float,required=True);a.add_argument('--source-manifest-sha256',required=True);args=a.parse_args()
 require(args.owned_session and os.getsid(0)==os.getpid()==os.getpgrp(),'outer owner must provide fresh builder session/group')
 check_stop();R=args.source_root.resolve(strict=True)
 require(math.isfinite(args.deadline_epoch) and args.deadline_epoch>time.time(),'expired/nonfinite caller deadline')
 deadline=time.monotonic()+min(360,args.deadline_epoch-time.time())
 require(sha(args.config)==args.config_sha256,'caller config changed')
 config=json.loads(args.config.read_text());require(set(config)=={'classpath_export','jdk_root','jdk_manifest','art','extra_inputs'},'config schema')
 export=verify(config['classpath_export']);document=json.loads(export.read_text());rows=document['inputs'];require(len(rows)==95 and document['environment']=={},'genuine95-input empty-environment export required')
 paths=[verify(r) for r in rows]
 require(any(sha(p)=='28ad092c1c1ec388dcb051bb60b89a9ba7e443ce27ca7dba6dc99a5d2c54c57a' for p in paths),'original genuine named game hash required')
 required={'networking':(169809,'8752ba0c80491dc56c51ecd037339ec015f73869db5d488eda7189a1a0f45888'),'lifecycle':(88814,'b316ff8cb3c7739143e713a1654c1072123079d0e3a07e76c18f94820c0ba767'),'base':(34806,'55845058007a954f8ffc2dc313731faf391f48ed52b1b7d31a752a887173ac23'),'ffloader':(3459840,'dc8829a0d9b5fa19eb0c50d54c981445fb21cba2abd2a39c5ff0b58ff7d5c1e1')}
 require(set(config['extra_inputs'])==set(required),'four extra inputs required')
 extra={}
 for name,(size,digest) in required.items():
  row=config['extra_inputs'][name];require(row['bytes']==size and row['sha256']==digest,'original extra pin required');extra[name]=verify(row);paths.append(extra[name])
 paths=list(dict.fromkeys(paths));require(len(paths)<=99,'full classpath bound')
 for p in paths:
  require(p.suffix=='.jar','only declared JAR inputs')
  with zipfile.ZipFile(p) as z:
   if 'META-INF/MANIFEST.MF' in z.namelist():require(not any(line.lower().startswith('class-path:') for line in z.read('META-INF/MANIFEST.MF').decode(errors='strict').splitlines()),'implicit manifest classpath')
 # Require a genuine named game and public APIs, not a smaller ad-hoc stub compilation.
 supplied=set()
 for p in paths:
  with zipfile.ZipFile(p) as z:supplied.update(z.namelist())
 for n in ['net/minecraft/client/Minecraft.class','net/minecraft/server/MinecraftServer.class','net/minecraft/network/RegistryFriendlyByteBuf.class','net/fabricmc/api/ModInitializer.class','net/fabricmc/fabric/api/event/Event.class','net/fabricmc/fabric/api/networking/v1/ServerPlayNetworking.class']:
  require(n in supplied,'missing genuine classpath member '+n)
 J=pathlib.Path(config['jdk_root']).resolve(strict=True);jmanifest=verify(config['jdk_manifest'])
 require(sha(jmanifest)=='f01898929ae478e4bdb546eae2b056ef87e9d91232713f1568070fc53ba9de71','original canonical JDK manifest pin')
 v=json.loads(jmanifest.read_text());require(len(v['files'])==249,'JDK canonical file count')
 for row in v['files']:verify({**row,'path':str(J.parent/row['path'])})
 require(config['art']['bytes']==751270 and config['art']['sha256']=='e977ee4422efb51eb54cc99f939833cef769de8b4aa1043294ce5400c60f3b1f','original ART all pin')
 art=verify(config['art']);loader=extra['ffloader']
 with zipfile.ZipFile(loader) as z:mapping_bytes=z.read('mappings.tsrg')
 require(hashlib.sha256(mapping_bytes).hexdigest()=='b4f0963e90d433f03d3597252da42ff1e38ce9928777c4ce65c779aae71ecdfa','original embedded mapping pin')
 manifest=R/'source-manifest.json';source_sha=sha(manifest);require(source_sha==args.source_manifest_sha256,'source manifest review pin');source=json.loads(manifest.read_text())
 require(set(source)=={'schema','status','files'} and source['schema']==1 and source['status']=='SOURCE_ONLY_NOT_RUNTIME_ACCEPTANCE','source contract')
 for row in source['files']:verify({**row,'path':str(R/row['path'])})
 main_sources,test_sources=source_inventory(R,source)
 out=args.output.resolve();require(not out.exists(),'fresh build directory required');out.mkdir(parents=True)
 mapping=out/'mappings.tsrg';mapping.write_bytes(mapping_bytes)
 for n in ['main','test','tools','empty']:(out/n).mkdir()
 cp=os.pathsep.join(map(str,paths));limits=['-Xms16m','-Xmx384m','-XX:MaxMetaspaceSize=128m','-XX:ActiveProcessorCount=1','-XX:+UseSerialGC'];opts=['-proc:none','--release','21','-g','-encoding','UTF-8','-implicit:none','-sourcepath',str(out/'empty')]
 commands=[('compile-main',[str(J/'bin/javac'),*['-J'+s for s in limits],*opts,'-cp',cp,'-d',str(out/'main'),*map(str,main_sources)]),('compile-test',[str(J/'bin/javac'),*['-J'+s for s in limits],*opts,'-cp',str(out/'main')+os.pathsep+cp,'-d',str(out/'test'),*map(str,test_sources)]),('actual-game-codecs',[str(J/'bin/java'),*limits,'-cp',os.pathsep.join([str(out/'test'),str(out/'main'),cp]),'dev.infinity.fabricnetworkcontrol.PreparedCodecTest']),('shared-wire',[str(J/'bin/java'),*limits,'-cp',os.pathsep.join([str(out/'test'),str(out/'main')]),'dev.infinity.fabricnetworkcontrol.NonceWireTest']),('compile-remapper',[str(J/'bin/javac'),*['-J'+s for s in limits],*opts,'-cp',str(art),'-d',str(out/'tools'),str(R/'tools/RemapProbe.java')])]
 phases=[];result={'schema':1,'status':'INCOMPLETE','gameLaunched':False,'networkAcceptance':False,'baselineAcceptance':False,'processOwnership':{'mode':'outer-owned-builder-session','builderPid':os.getpid(),'builderPgrp':os.getpgrp(),'builderSession':os.getsid(0),'childCreatesSession':False},'sourceManifestSha256':source_sha,'sourceManifest':pin(manifest),'builder':pin(pathlib.Path(__file__)), 'compilerInputs':[pin(J.parent/row['path']) for row in v['files']], 'callerDeadlineEpoch':args.deadline_epoch,'classpathInputs':[pin(p) for p in paths],'classpathSourceManifest':pin(export),'callerConfig':pin(args.config),'jdkVerificationManifest':pin(jmanifest),'phases':phases}
 try:
  for name,cmd in commands:phases.append(phase(name,cmd,out,deadline))
  require((out/'actual-game-codecs.log').read_text().count('Prepared codec/input checks: 46; no network or game acceptance')==1,'actual codec checks absent')
  require((out/'shared-wire.log').read_text().count('ACTUAL_SHARED_NONCE_WIRE assertions=138 PASS')==1,'shared wire checks absent')
  members={'META-INF/MANIFEST.MF':b'Manifest-Version: 1.0\r\nFabric-Mapping-Namespace: mojang\r\n\r\n','fabric.mod.json':(R/'src/main/resources/fabric.mod.json').read_bytes(),'LICENSE':(R/'LICENSE').read_bytes()}
  for p in sorted((out/'main').rglob('*.class')):members[str(p.relative_to(out/'main'))]=p.read_bytes()
  pack(out/'probe-named.jar',members);(out/'libraries.txt').write_text(''.join(str(p)+'\n' for p in paths))
  phases.append(phase('actual-remap-roundtrip',[str(J/'bin/java'),*limits,'-cp',str(out/'tools')+os.pathsep+str(art),'net.neoforged.art.internal.RemapProbe',str(mapping),str(out/'probe-named.jar'),str(out/'probe-intermediary-raw.jar'),str(out/'probe-roundtrip.jar'),str(out/'libraries.txt')],out,deadline))
  require('ACTUAL_ART_PROBE_ROUNDTRIP ' in (out/'actual-remap-roundtrip.log').read_text(),'roundtrip checks absent')
  with zipfile.ZipFile(out/'probe-intermediary-raw.jar') as z:
   remapped={n:z.read(n) for n in z.namelist() if not n.endswith('/')}
  require(set(remapped)==set(members),'remapper changed member inventory')
  require(all(remapped[n]==members[n] for n in members if not n.endswith('.class')),'remapper changed resource payload')
  remapped['META-INF/MANIFEST.MF']=b'Manifest-Version: 1.0\r\nFabric-Mapping-Namespace: intermediary\r\n\r\n'
  artifact=out/'fabric-network-control-0.1.0.jar';pack(artifact,remapped)
  for row in result['classpathInputs']:verify(row)
  require(sha(manifest)==source_sha,'source manifest changed')
  for row in source['files']:verify({**row,'path':str(R/row['path'])})
  result.update(status='PASS_COMPILE_REAL_CODEC_REMAP_ONLY',checks=184,artifact=pin(artifact),mapping=pin(mapping),mappingOwner=pin(loader),remapper=pin(art),remapperUtility=pin(R/'tools/RemapProbe.java'))
  (out/'probe-build-binding.json').write_text(json.dumps({'schema':1,'status':'BUILT','source_manifest_sha256':source_sha,'artifact_path':str(artifact),'artifact_sha256':sha(artifact),'artifact_bytes':artifact.stat().st_size},indent=2)+'\n')
 finally:(out/'result.json').write_text(json.dumps(result,indent=2)+'\n')
 print(json.dumps(result,indent=2))
if __name__=='__main__':
 with owned_stops():main()
