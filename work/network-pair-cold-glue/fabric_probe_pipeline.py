"""Explicit opt-in Fabric API probe preparation/build, never a baseline acceptance."""
from pathlib import Path
import hashlib,json,shutil,sys,time
import compile_probe
SOURCE='work/fabric-network-probe'
SOURCE_SHA='6a7e1afe7f405a2d6a7075f283067d9efa5b4e72467e31e76240fbe7cadff4bf'
JDK_MANIFEST_SHA='f01898929ae478e4bdb546eae2b056ef87e9d91232713f1568070fc53ba9de71'
OUTPUT='work/fabric-network-probe-build'
EXTRA={'networking':'8752ba0c80491dc56c51ecd037339ec015f73869db5d488eda7189a1a0f45888','lifecycle':'b316ff8cb3c7739143e713a1654c1072123079d0e3a07e76c18f94820c0ba767','base':'55845058007a954f8ffc2dc313731faf391f48ed52b1b7d31a752a887173ac23','ffloader':'dc8829a0d9b5fa19eb0c50d54c981445fb21cba2abd2a39c5ff0b58ff7d5c1e1'}
def require(ok,message):
 if not ok:raise ValueError(message)
def verify_source(root):
 source=Path(root)/SOURCE;manifest=source/'source-manifest.json'
 require(compile_probe.sha(manifest)==SOURCE_SHA,'Reviewed Fabric source manifest changed')
 d=json.loads(manifest.read_text());require(d['schema']==1 and d['status']=='SOURCE_ONLY_NOT_RUNTIME_ACCEPTANCE','Fabric source state')
 expected={r['path'] for r in d['files']}|{'source-manifest.json','jdk-input-verification.json'}
 require(len(expected)==len(d['files'])+2,'Duplicate source inventory')
 actual=set()
 for entry in source.rglob('*'):
  require(not entry.is_symlink(),'Redirected Fabric source inventory')
  if entry.is_file():actual.add(entry.relative_to(source).as_posix())
 require(actual==expected,'Unexpected Fabric source inventory')
 for r in d['files']:
  p=source/r['path'];require(p.resolve().is_relative_to(source.resolve()) and not p.is_symlink(),'Fabric source path')
  require(p.stat().st_size==r['bytes'] and compile_probe.sha(p)==r['sha256'],'Fabric source input changed')
 require(compile_probe.sha(source/'jdk-input-verification.json')==JDK_MANIFEST_SHA,'JDK manifest changed')
 return source

def prepare(repo,consumer):
 source=verify_source(repo);target=Path(consumer)/SOURCE
 require(not target.exists(),'Fresh Fabric source preparation required')
 target.mkdir(parents=True)
 rows=json.loads((source/'source-manifest.json').read_text())['files']
 for relative in [r['path'] for r in rows]+['source-manifest.json','jdk-input-verification.json']:
  dest=target/relative;dest.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(source/relative,dest)
 verify_source(consumer)
 return {'sourceManifest':compile_probe.record(target/'source-manifest.json'),'diagnostic_only':True,'compiled':False}

def configure(consumer):
 root=Path(consumer).resolve(strict=True);source=verify_source(root);api=root/'work/api1'
 # The full runtime remains independently validated by the existing driver.
 export=api/'run/api1-unified-client-build/client-launch-inputs.json'
 core=json.loads((root/'work/network-pair-cold-glue/profiles/ffapi-core-dependency-lock.json').read_text())
 extras={}
 for name,digest in EXTRA.items():
  matches=[r for r in core['artifacts'] if r.get('sha256')==digest and r['path'].endswith('.jar')]
  require(len(matches)==1,'Unique original FFAPI input pin required')
  row=matches[0];p=api/row['path'];require(compile_probe.sha(p)==digest and p.stat().st_size==row['bytes'],'FFAPI input changed');extras[name]=compile_probe.record(p)
 art=api/'ci/runtime-maven/net/neoforged/AutoRenamingTool/2.0.17/AutoRenamingTool-2.0.17-all.jar'
 return {'classpath_export':compile_probe.record(export),'jdk_root':str(api/'.toolchains/jdk-21.0.12.1+1'),'jdk_manifest':compile_probe.record(source/'jdk-input-verification.json'),'art':compile_probe.record(art),'extra_inputs':extras}

def build(consumer,deadline,execute_step):
 root=Path(consumer).resolve(strict=True);source=verify_source(root)
 require(deadline-time.monotonic()>2,'No time for Fabric build')
 config=configure(root);path=root/'work/fabric-network-probe-config.json';require(not path.exists(),'Repeated Fabric build')
 path.write_text(json.dumps(config,indent=2)+'\n')
 # Deliberately subtract one second; never renew the parent deadline.
 epoch=time.time()+deadline-time.monotonic()-1
 step={'name':'fabric-api-probe-build','command':[sys.executable,str(source/'build_probe.py'),'--owned-session','--source-root',str(source),'--config',str(path),'--config-sha256',compile_probe.sha(path),'--source-manifest-sha256',SOURCE_SHA,'--deadline-epoch',str(epoch),'--output',str(root/OUTPUT)],'cwd':str(root),'environment':{'PATH':'/usr/bin:/bin','LANG':'C.UTF-8','LC_ALL':'C.UTF-8','HOME':str(root/'work/api1/ci/build-home')},'timeoutSeconds':360}
 execute_step(root,step,deadline,refreshed=True,diagnostic=True)
 import fabric_probe_build_validation
 return fabric_probe_build_validation.create_bundle(root,source,root/OUTPUT)
