#!/usr/bin/env python3
"""Pin generated official client inputs only; asset completeness remains a separate launch gate."""
import hashlib,importlib.util,json,os,pathlib,shlex,zipfile
HERE=pathlib.Path(__file__).resolve().parent;ROOT=HERE.parent.parent/'work/api1';PROFILE=ROOT/'run/api1-unified-client-build'
raw=PROFILE/'client-launch-inputs.json';m=json.loads(raw.read_text());assert m['environment']=={} and m['gameLaunched'] is False
files={};empty=[]
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def add(p):
 p=pathlib.Path(p).resolve(strict=True);assert p.is_file() and not p.is_symlink();files[str(p)]={'path':str(p),'sha256':sha(p)};return p
add(raw)
for p in m['classpath']:
 p=pathlib.Path(p)
 if p.is_file():add(p)
 else:
  assert not p.exists() or (p.is_dir() and not any(p.iterdir()));empty.append(str(p.resolve()))
for arg in m['jvmArgs']+m['args']:
 if arg.startswith('@'):add(arg[1:])
java=add(ROOT/'.toolchains/jdk-21.0.12.1+1/bin/java');cwd=pathlib.Path(m['gameDirectory']);cwd.mkdir(parents=True,exist_ok=True)
command=[str(java),*m['jvmArgs'],'-cp',os.pathsep.join(m['classpath']),m['mainClass'],*m['args']]
a_path=ROOT/'source-workspace/fml-unified/tools/assemble_installation.py';spec=importlib.util.spec_from_file_location('official_client_assembler',a_path);a=importlib.util.module_from_spec(spec);spec.loader.exec_module(a)
pins={p:r['sha256'] for p,r in files.items()};tokens=a.flatten(command,pins,cwd)
assert tokens[tokens.index('--launchTarget')+1]=='forgeclientdev'
assert '-Xmx1280M' in tokens and '-XX:ActiveProcessorCount=2' in tokens
assert not any(x in tokens for x in ['--username','--uuid','--accessToken','--server','--quickPlayMultiplayer'])
for i,t in enumerate(tokens):
 if t in ['-p','--module-path']:
  for p in tokens[i+1].split(os.pathsep):add(p)
 if t.startswith('-D') and '=' in t:
  key,value=t[2:].split('=',1)
  if key in ['log4j2.configurationFile','legacyClassPath.file','connector.clean.path']:
   p=add(value)
   if key=='legacyClassPath.file':
    for q in p.read_text().splitlines():
     if q.strip() not in empty:add(q.strip())
  assert key not in ['fml.modFolders','fml.modFoldersFile','java.system.class.loader'] or not value
idx=add(ROOT/'run/client-dev/assets/indexes/17.json');assert hashlib.sha1(idx.read_bytes()).hexdigest()=='9b16298b1dc0697878cec88bb2d96168f5239e4f'
add(PROFILE/'build/moddev/minecraft_assets.properties')
natives=[]
for row in list(files.values()):
 p=pathlib.Path(row['path'])
 if p.suffix=='.jar':
  with zipfile.ZipFile(p) as z:
   native_entries={n:hashlib.sha256(z.read(n)).hexdigest() for n in z.namelist() if n.endswith('.so')}
   if native_entries:natives.append({'jar':row,'entries':native_entries})
records=list(files.values())+[{'path':p,'sha256':None,'kind':'declared-empty-source-output'} for p in empty]
seal={'schema':1,'status':'OFFICIAL_CLIENT_COMMAND_SEALED_ASSETS_AND_PROBE_PENDING','workingDirectory':str(cwd),'command':command,'files':records,'environment':{},'emptyDevelopmentRoots':empty,'manifest':{'path':str(raw),'sha256':sha(raw)},'preparation':'Official ModDevGradle 2.0.140 / NeoForge 21.1.219 binary-only; task prepareClientLaunch, never runClient','gameLaunched':False,'heapMiB':1280,'activeProcessors':2,'assetIndex':{'id':'17','path':str(idx),'sha1':'9b16298b1dc0697878cec88bb2d96168f5239e4f','sha256':sha(idx)},'assetObjectsGate':'Require completed independent original-index object verification before any launch','nativeLibraries':{'status':'Original native resources pinned; extraction/loading not yet executed','jars':natives},'compiledSourceTuple':'portable-bootstrap/manifest-main-candidate/candidate-seal.json'}
out=PROFILE/'official-client-launch-seal.json';assert not out.exists();out.write_text(json.dumps(seal,indent=2)+'\n');print(json.dumps({'path':str(out),'sha256':sha(out),'pinnedFiles':len(files),'emptyRoots':len(empty),'nativeJarInputs':len(natives),'clientLaunched':False}))
