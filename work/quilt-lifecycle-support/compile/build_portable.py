#!/usr/bin/env python3
"""Portable offline compile-only runner. Caller must supply an independently reviewed contract hash."""
import argparse,fcntl,hashlib,importlib.util,json,math,os,pathlib,signal,time,zipfile,datetime
from portable_io import canonical,consumer_path,no_aliases,load as load_json,loads as loads_json
T=canonical(pathlib.Path(__file__).absolute().parent,kind='directory')
sha=lambda p:hashlib.sha256(pathlib.Path(p).read_bytes()).hexdigest()
def require(v,m):
 if not v:raise ValueError(m)
def main():
 a=argparse.ArgumentParser();a.add_argument('--consumer-root',required=True,type=pathlib.Path);a.add_argument('--config',required=True,type=pathlib.Path);a.add_argument('--contract',required=True,type=pathlib.Path);a.add_argument('--contract-sha256',required=True);a.add_argument('--output',required=True,type=pathlib.Path);a.add_argument('--deadline-epoch',required=True,type=float);args=a.parse_args()
 args.contract=canonical(args.contract);require(sha(args.contract)==args.contract_sha256,'independently reviewed contract hash mismatch');contract=load_json(args.contract);require(contract['schema']==1 and contract['scope']=='COMPILE_ABI_ONLY_DIAGNOSTIC','contract scope')
 for row in contract['tools']:
  p=canonical(T/row['path']);require(p.is_file() and sha(p)==row['sha256'] and p.stat().st_size==row['bytes'],'reviewed tool mismatch '+row['path'])
 spec=importlib.util.spec_from_file_location('owned_compile',T/'build_recovery.py');b=importlib.util.module_from_spec(spec);spec.loader.exec_module(b)
 root=canonical(args.consumer_root,kind='directory');args.config=canonical(args.config,root);config=load_json(args.config);require(set(config)=={'schema','paths'} and type(config['schema']) is int and config['schema']==1,'path config schema');require(set(config['paths'])==set(contract['inputs'])|{'jdk_root'},'exact configured input roles')
 inputs={key:consumer_path(root,value,'directory' if key=='jdk_root' else 'file') for key,value in config['paths'].items()};no_aliases(inputs.values())
 for key,row in contract['inputs'].items():b.verify(inputs[key],row['sha256'],row['bytes'])
 source_manifest=inputs['source_manifest'];source_root=source_manifest.parent;source=load_json(source_manifest);require(source['files']==contract['source_files'],'exact original nine-file manifest')
 for row in source['files']:b.verify(canonical(source_root/row['path'],root),row['sha256'],row['bytes'])
 fixture=source_root/'four-loader/quilt-probe';require({str(p.relative_to(source_root)) for p in fixture.rglob('*') if p.is_file()}=={r['path'] for r in source['files']},'unlisted source tree bytes')
 with zipfile.ZipFile(inputs['source_archive']) as z:
  for row in source['files']:require(hashlib.sha256(z.read(row['path'])).hexdigest()==row['sha256'],'original archive source binding')
 jdk=inputs['jdk_root'];jdk_files=load_json(inputs['jdk_manifest'])['files'];require(jdk_files==contract['jdk_files'],'canonical JDK manifest changed')
 for row in jdk_files:b.verify(canonical(jdk/pathlib.PurePosixPath(row['path']).relative_to('jdk-21.0.12.1+1'),root),row['sha256'],row['bytes'])
 require(math.isfinite(args.deadline_epoch) and args.deadline_epoch>time.time(),'expired/nonfinite deadline');deadline=time.monotonic()+min(360,args.deadline_epoch-time.time())
 out=canonical(args.output,root,missing=True);require(not out.exists(),'fresh output within consumer root');out.mkdir(parents=True)
 for n in ['tmp','empty','tools']:(out/n).mkdir()
 b.adopt_owned_descendants()
 for number in [signal.SIGINT,signal.SIGTERM,signal.SIGHUP]:signal.signal(number,lambda n,f:b.STOP.append(n))
 result={'schema':1,'portableVersion':1,'consumerRoot':str(root),'status':'INCOMPLETE','diagnosticOnly':True,'runtimeAcceptance':False,'baselineAcceptance':False,'gameLaunched':False,'ciStarted':False,'originalArtifactLocksChanged':False,'serialJvmOnly':True,'limits':b.LIMITS,'sourceArchive':b.pin(inputs['source_archive']),'sourceManifest':b.pin(source_manifest),'sourceFiles':source['files'],'historicalBuildReport':b.pin(fixture/'build/build-report.json',notFreshProof=True),'jdkManifest':b.pin(inputs['jdk_manifest']),'jdkCanonicalFilesVerified':len(jdk_files),'jdkRoot':str(jdk),'builder':b.pin(__file__),'reviewedContract':b.pin(args.contract),'portableConfig':b.pin(args.config),'phases':[],'startedAt':datetime.datetime.now(datetime.timezone.utc).isoformat(),'callerDeadlineEpoch':args.deadline_epoch,'sourceInputRoles':{k:b.pin(v) for k,v in inputs.items() if k!='jdk_root'}}
 try:
  with zipfile.ZipFile(inputs['mapping_owner']) as z:mapping_bytes=z.read('mappings/mappings.tiny')
  require(hashlib.sha256(mapping_bytes).hexdigest()==contract['mappingSha256'],'original mapping');mapping=out/'mappings.tiny';mapping.write_bytes(mapping_bytes)
  embedded=[];libraries=[];original_server=None
  with zipfile.ZipFile(inputs['server_bundle']) as z:
   for category in ['versions','libraries']:
    for line in z.read('META-INF/'+category+'.list').decode().splitlines():
     expected,coordinate,relative=line.split('\t');require('..' not in pathlib.PurePosixPath(relative).parts and not relative.startswith('/'),'embedded path')
     entry='META-INF/'+category+'/'+relative;data=z.read(entry);require(hashlib.sha256(data).hexdigest()==expected,'embedded hash');p=out/'official-inputs'/category/relative;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(data)
     embedded.append(b.pin(p,archiveEntry=entry,coordinate=coordinate,origin='hash-verified embedded official Mojang server bundle'))
     if category=='libraries':libraries.append(p)
     else:require(original_server is None,'one real server');original_server=p
  libraries += [inputs['annotations'],inputs['jsr305']]
  remap_tools=[inputs['loader'],*[inputs[n] for n in contract['asmRoles']]];art=inputs['art'];result.update(remapperInputs=[b.pin(p) for p in remap_tools],abiVerifierInputs=[b.pin(art)],embeddedOfficialInputs=embedded)
  liblist=out/'remap-libraries.txt';liblist.write_text(''.join(str(p)+'\n' for p in libraries))
  javac=[str(jdk/'bin/javac'),*['-J'+x for x in b.LIMITS],'-proc:none','--release','21','-encoding','UTF-8','-implicit:none','-sourcepath',str(out/'empty')];java=[str(jdk/'bin/java'),*b.LIMITS]
  result['phases'].append(b.phase('compile-tools',[*javac,'-cp',os.pathsep.join(map(str,[art,*remap_tools])),'-d',str(out/'tools'),str(T/'RemapServer.java'),str(T/'AbiCheck.java')],out,deadline))
  derived=out/'server-intermediary-derived-not-historical.jar';result['phases'].append(b.phase('derive-real-server',[*java,'-cp',os.pathsep.join(map(str,[out/'tools',*remap_tools])),'RemapServer',str(mapping),str(original_server),str(derived),str(liblist)],out,deadline))
  with zipfile.ZipFile(derived) as z:game_classes=[{'path':n,'bytes':len(z.read(n)),'sha256':hashlib.sha256(z.read(n)).hexdigest()} for n in sorted(z.namelist()) if n.endswith('.class')]
  require(len(game_classes)==6148 and hashlib.sha256(json.dumps(game_classes,sort_keys=True,separators=(',',':')).encode()).hexdigest()==contract['derivedGameClassContentSha256'],'real derived game content changed')
  result['derivedGame']=b.pin(derived,notHistorical=True,gameClassCount=6148,classContentSha256=contract['derivedGameClassContentSha256'],parentServerBundle=b.pin(inputs['server_bundle']),embeddedEntry=next(x for x in embedded if x['path']==str(original_server)),mappingOwner=b.pin(inputs['mapping_owner']),mappingSha256=b.digest(mapping),mapping=b.pin(mapping),remapper=b.pin(inputs['loader']),resourcesIntentionallyExcluded=True,runnableGameArchive=False,provenance='Original locked Quilt TinyRemapper, conflicts=false; full genuine official server class inventory only, NOT historical or runnable game bytes')
  closure=[inputs['loader'],inputs['qsl_base'],inputs['qsl_lifecycle'],derived,inputs['mixin'],*libraries];require(len(closure)==len(set(closure)),'duplicate classpath')
  for p in closure:
   with zipfile.ZipFile(p) as z:
    if 'META-INF/MANIFEST.MF' in z.namelist():require(not any(line.lower().startswith('class-path:') for line in z.read('META-INF/MANIFEST.MF').decode().splitlines()),'implicit manifest classpath')
  result['compileInputs']=[b.pin(p,origin='derived real game' if p==derived else 'verified original dependency') for p in closure];cp=os.pathsep.join(map(str,closure));sources=sorted((fixture/'src').rglob('*.java'));require(len(sources)==3,'three original sources')
  artifacts=[]
  for iteration in [1,2]:
   classes=out/('classes-'+str(iteration));classes.mkdir();result['phases'].append(b.phase('compile-fixture-'+str(iteration),[*javac,'-verbose','-cp',cp,'-d',str(classes),*map(str,sources)],out,deadline))
   entries={str(p.relative_to(classes)):p.read_bytes() for p in sorted(classes.rglob('*.class'))};require(len(entries)==5,'five compiled classes')
   entries.update({str(p.relative_to(fixture/'resources')):p.read_bytes() for p in sorted((fixture/'resources').rglob('*')) if p.is_file()});jar=out/('unified-native-quilt-probe-0.1.0'+('' if iteration==1 else '-rebuild')+'.jar');b.pack(jar,entries);artifacts.append(jar)
   require(b.digest(jar)==contract['artifact']['sha256'] and jar.stat().st_size==contract['artifact']['bytes'],'reviewed fixture bytecode changed')
  cp_list=out/'compile-classpath.txt';cp_list.write_text(''.join(str(p)+'\n' for p in closure));result['phases'].append(b.phase('actual-abi',[*java,'-cp',str(out/'tools')+os.pathsep+str(art),'AbiCheck',str(artifacts[0]),str(cp_list)],out,deadline));abi=(out/'actual-abi.log').read_text();checks=[s for s in abi.splitlines() if s.startswith(('METHOD ','FIELD '))];require(checks==contract['abiChecks'],'reviewed real ABI binding changed')
  result['negativeControls']=[]
  for case,dependency in [('missing-dependency',{'id':'native_quilt_missing_dependency','versions':'=9.9.9'}),('loader-version',{'id':'quilt_loader','versions':'>=0.31.0'})]:
   meta=loads_json(entries['quilt.mod.json']);meta['quilt_loader']['depends']=[d for d in meta['quilt_loader']['depends'] if d['id']!=dependency['id']]+[dependency];payload={**entries,'quilt.mod.json':(json.dumps(meta,indent=2)+'\n').encode()};jar=out/('unified-native-quilt-probe-'+case+'.jar');b.pack(jar,payload)
   require(b.digest(jar)==contract['negativeControls'][case]['sha256'],'reviewed negative bytes changed');result['negativeControls'].append(b.pin(jar,case=case,expectedDependency=dependency,runtimeRejectionNotRun=True))
  for key,row in contract['inputs'].items():b.verify(inputs[key],row['sha256'],row['bytes'])
  for row in source['files']:b.verify(canonical(source_root/row['path'],root),row['sha256'],row['bytes'])
  result.update(status='PASS_COMPILE_ABI_ONLY',artifact=b.pin(artifacts[0],namespace='intermediary'),deterministicRecompile=True,rebuildArtifact=b.pin(artifacts[1]),classFiles=contract['classFiles'],jarEntries=contract['jarEntries'],nativeDescriptorOnly=True,foreignLoaderApiReferences=False,abiChecks=checks,tools=[b.pin(T/n) for n in ['RemapServer.java','AbiCheck.java','build_recovery.py','portable_io.py']],historicalArtifactReproduced=False,runtimeStatus='NOT RUN; no lifecycle/Mixin/SavedData/reopen acceptance',finishedAt=datetime.datetime.now(datetime.timezone.utc).isoformat())
 except BaseException as exc:
  result['failure']={'type':type(exc).__name__,'message':str(exc)};raise
 finally:b.write_json(out/'result.json',result)
 print(json.dumps({'status':result['status'],'artifact':result['artifact'],'result':b.pin(out/'result.json')},indent=2))
if __name__=='__main__':
 with (T/'compile-owner.lock').open('a') as owner:
  fcntl.flock(owner,fcntl.LOCK_EX|fcntl.LOCK_NB);main()
