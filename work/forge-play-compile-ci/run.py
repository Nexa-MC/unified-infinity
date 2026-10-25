#!/usr/bin/env python3
"""Exact original Forge entrypoint / native trigger compilation. No game launch.

Runs only the approved standard Ubuntu diagnostic CI. Restores original public
pins in its own consumer; never transports historical generated artifacts or
pretends this compile-only proof is the full runtime bundle.
"""
from pathlib import Path
import argparse, hashlib, importlib.util, json, os, signal, subprocess, sys, time
HERE=Path(__file__).resolve().parent
REPO='Nexa-MC/unified-infinity'; BRANCH='refs/heads/diagnostic/network-pair-20261006-a'
ORIGINAL_FORGE_LOCK='68e2f0a132da33e4e2c02db404e798f162fb1324d767c86ecede38e907188b66'
FORGE_NAMES={'forge-1.21.1-52.1.0-universal.jar','javafmllanguage-1.21.1-52.1.0.jar','fmlcore-1.21.1-52.1.0.jar','eventbus-6.2.27.jar'}
FALSE_FLAGS={'gameLaunched':False,'networkAcceptance':False,'fullApiCompatibility':False,'readyRuntimeBundle':False}

def require(value,message):
    if not value:raise ValueError(message)
def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def pin(path):
    p=Path(path).absolute();require(p.is_file() and not any(x.is_symlink() for x in [p,*p.parents]),'Regular canonical input required')
    return {'path':str(p),'bytes':p.stat().st_size,'sha256':sha(p)}
def write(path,value):
    with Path(path).open('x') as f:json.dump(value,f,indent=2);f.write('\n')
def validate_source(repo,manifest_sha):
    p=HERE/'source-manifest.json';require(sha(p)==manifest_sha,'Reviewed source manifest changed');m=json.loads(p.read_text())
    require(m['schema']=='forge-compile-ci-source-v1','Wrong source manifest')
    seen=set()
    for r in m['files']:
        rel=Path(r['path']);require(not rel.is_absolute() and '..' not in rel.parts and r['path'] not in seen,'Invalid duplicate source path');seen.add(r['path'])
        actual=pin(repo/rel);require(actual['bytes']==r['bytes'] and actual['sha256']==r['sha256'],'Source changed: '+r['path'])
    require(str(HERE.relative_to(repo)/'run.py') in seen,'Owner source missing')
    return m

def forge_records():
    p=HERE/'original-forge-source-lock.json';require(sha(p)==ORIGINAL_FORGE_LOCK,'Original Forge lock changed')
    rows=[]
    for row in json.loads(p.read_text())['artifacts']:
        name=Path(row['path']).name
        if name in FORGE_NAMES:
            require(row['url'].startswith('https://maven.minecraftforge.net/'),'Wrong original Forge host')
            rows.append({'path':'forge-inputs/'+name,'bytes':row['size'],'sha256':row['sha256'],'urls':[row['url']]})
    require({Path(r['path']).name for r in rows}==FORGE_NAMES and len(rows)==4,'Incomplete original Forge pins')
    return rows

def budget(anchor,now=None,wall=None):
    import first_step_anchor as a
    now=time.monotonic() if now is None else now;wall=time.time() if wall is None else wall
    # All owned build steps stop by first-step+17min; remaining 3min is cleanup.
    remaining=min(anchor['capturedMonotonic']+17*60-now,a.utc(a.CUTOFF_UTC)-180-wall)
    require(remaining>=60,'Insufficient remaining compile budget')
    return now+remaining

def within(function,*args,deadline):
    def expired(_n,_f):raise TimeoutError('Pinned restoration deadline expired')
    left=deadline-time.monotonic();require(left>0,'Deadline expired')
    previous=signal.signal(signal.SIGALRM,expired);signal.setitimer(signal.ITIMER_REAL,left)
    try:return function(*args)
    finally:signal.setitimer(signal.ITIMER_REAL,0);signal.signal(signal.SIGALRM,previous)

def run_step(command,cwd,env,evidence,name,deadline,limit):
    import owned_compile_process_v3 as owner
    left=min(limit,deadline-time.monotonic());require(left>0,'Deadline expired before owned spawn')
    log=evidence/(name+'.log');journal=evidence/(name+'-owner.json');record={'name':name,'command':command,'timeoutSeconds':left,**FALSE_FLAGS}
    try:
        with log.open('x') as stream:
            result=owner.run(command,cwd=cwd,env=env,stdout=stream,stderr=subprocess.STDOUT,timeout=left,cancel_file=evidence/'cancel',owner_receipt=journal)
        record['exitCode']=result.returncode;record['ownerValidation']=owner.validate_completion(journal,result,command)
        require(result.returncode==0 and record['ownerValidation']['qualified'],'Owned compile/setup did not finish successfully')
    except BaseException as error:
        record['error']=type(error).__name__+': '+str(error)
        if log.exists():print(log.read_text(errors='replace')[-16000:],flush=True)
        raise
    finally:
        if log.exists():record['log']=pin(log)
        if journal.exists():record['ownerJournal']=pin(journal)
        write(evidence/(name+'.json'),record)
        print('FORGE_COMPILE_STEP '+json.dumps(record),flush=True)
    return record

def execute(repo,consumer,manifest_sha):
    import first_step_anchor as anchor
    a=anchor.read_anchor();deadline=budget(a)
    validate_source(repo,manifest_sha)
    require(not consumer.exists() and consumer.is_absolute() and consumer.resolve()==consumer and not consumer.is_relative_to(repo),'Fresh external CI consumer required')
    sys.path.insert(0,str(HERE/'support'));sys.path.insert(0,str(repo/'work/network-pair-cold-glue'))
    import ffapi_sources,runtime_restore
    ffapi_sources.prepare(repo,consumer);plan=runtime_restore.prepare(repo,consumer)
    api=consumer/'work/api1';evidence=consumer/'forge-compile-evidence';evidence.mkdir()
    final={'schema':'forge-original-entrypoint-compile-v1','sourceManifestSha256':manifest_sha,'runId':os.environ['GITHUB_RUN_ID'],'headSha':os.environ['GITHUB_SHA'],'status':'IN_PROGRESS',**FALSE_FLAGS}
    try:
        within(runtime_restore.restore,api,deadline=deadline)
        spec=importlib.util.spec_from_file_location('exact_forge_downloader',api/'ci/runtime-restore/restore_inputs.py');downloader=importlib.util.module_from_spec(spec);spec.loader.exec_module(downloader)
        restored=[]
        for row in forge_records():restored.append(within(downloader.restore,consumer,row,{'maven.minecraftforge.net'},deadline=deadline))
        final['originalForgeInputs']=restored;print('ORIGINAL_FORGE_INPUTS '+json.dumps(restored),flush=True)
        for step in plan['steps']:
            run_step(step['command'],step['cwd'],step['environment'],evidence,step['name'],deadline,step['timeoutSeconds'])
        final['officialRuntime']=runtime_restore.verify(api)
        jdk=Path(plan['javaHome']);javac=jdk/'bin/javac'
        jmeta=json.loads((repo/'work/fabric-network-probe/jdk-input-verification.json').read_text())
        expected=[r for r in jmeta['files'] if r['path'].endswith('/bin/javac')];require(len(expected)==1,'Exact javac identity missing')
        require(pin(javac)['sha256']==expected[0]['sha256'] and pin(javac)['bytes']==expected[0]['bytes'],'javac identity changed')
        clean=api/'run/api1-unified-client-build/build/moddev/artifacts/minecraft-1.21.1-clean.jar'
        cp=[consumer/r['path'] for r in forge_records()]+[clean]
        for rel in ['io/netty/netty-buffer/4.1.97.Final/netty-buffer-4.1.97.Final.jar','io/netty/netty-common/4.1.97.Final/netty-common-4.1.97.Final.jar','io/netty/netty-transport/4.1.97.Final/netty-transport-4.1.97.Final.jar','org/apache/commons/commons-lang3/3.14.0/commons-lang3-3.14.0.jar']:cp.append(api/'ci/runtime-maven'/rel)
        export=json.loads((api/'run/api1-unified-client-build/client-launch-inputs.json').read_text())
        native=list(dict.fromkeys(Path(r['path']) for r in export['inputs'] if Path(r['path']).suffix=='.jar'))
        import forge_probe_bundle as package
        outputs={};classpaths={};sources=HERE/'sources'
        env={'PATH':str(jdk/'bin')+':/usr/bin:/bin','JAVA_HOME':str(jdk),'HOME':str(api/'ci/build-home'),'LANG':'C.UTF-8','LC_ALL':'C.UTF-8'}
        for role,part in package.PARTS.items():
            out=consumer/(role+'-classes');out.mkdir()
            rolecp=cp if role=='forge_probe' else [consumer/'forge_probe-classes',*native]
            classpaths[role]=[pin(p) for p in rolecp if p.is_file()]
            sourcefiles=sorted((sources/part/'src').rglob('*.java'));require(sourcefiles,'No actual probe source')
            cmd=[str(javac),*package.FLAGS,'-cp',os.pathsep.join(map(str,rolecp)),'-d',str(out),*map(str,sourcefiles)]
            run_step(cmd,consumer,env,evidence,'compile-'+role,deadline,120)
            destination=consumer/(role+'.jar');package.package(sources,out,role,destination)
            outputs[role]={'artifact':pin(destination),'classes':package.class_inventory(out,role),'sources':[pin(p) for p in sourcefiles]}
        runtime_restore.verify_inputs(api);validate_source(repo,manifest_sha)
        final.update(status='COMPLETE_ORIGINAL_ENTRYPOINT_AND_NATIVE_DRIVER_COMPILED',javac=pin(javac),outputs=outputs,classpath=classpaths,entrypointCompiled=True)
    except BaseException as error:final.update(status='FAILED',error=type(error).__name__+': '+str(error));raise
    finally:
        final['finishedUtc']=__import__('datetime').datetime.now(__import__('datetime').timezone.utc).isoformat()
        write(evidence/'result.json',final);print('FORGE_COMPILE_RESULT '+json.dumps(final),flush=True)
    return final

def main():
    p=argparse.ArgumentParser();p.add_argument('--repo',type=Path,required=True);p.add_argument('--consumer',type=Path,required=True);p.add_argument('--manifest-sha256',required=True);p.add_argument('--verify-only',action='store_true');a=p.parse_args()
    repo=a.repo.resolve(strict=True)
    if a.verify_only:validate_source(repo,a.manifest_sha256);forge_records();print('FORGE_COMPILE_SOURCE_VERIFIED');return
    execute(repo,a.consumer,a.manifest_sha256)
if __name__=='__main__':main()
