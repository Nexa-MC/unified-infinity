#!/usr/bin/env python3
"""Compile recovered probe0.1.1 against the genuine prepared client API; no game."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import time
import zipfile
import bounded_process

SOURCE_SHA='72120ff803ecda74f6d363702afb303d6d053ce22f9e9a7f3ade7782cf5db0ca'
REFERENCE_JAR_SHA='791f6c303475ad9d32baaacc98f0350c027d6efe826dcd5aa9dc99a81da2918a'
SOURCE_RELATIVE='work/api1/four-loader/network-control-probe-0.1.1'
OUTPUT_RELATIVE='work/api1/ci/nonce-probe-0.1.1'
ARTIFACT_NAME='network-control-probe-0.1.1.jar'
REFERENCE_ENTRIES=Path(__file__).resolve().parent/'probe011-reference-entries.json'
REFERENCE_ENTRIES_SHA='b24a51fd2589999b853754a35251fd16ae9667fe629b76a907149755afd98daa'
TOOLS={'bin/java':'2a207f5e7d075afa01d97f8048389a64432a44c4a5af0f5e77d6e286ec5f401d',
       'bin/javac':'55859b80e7a9c4c4736be19ad3addeb35112ca6d17a30c4e0e116afc0a499bdb'}

def require(value,message):
    if not value:raise ValueError(message)

def sha(path):
    with Path(path).open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()

def record(path):return {'path':str(path),'bytes':path.stat().st_size,'sha256':sha(path)}

def save(path,value):
    require(not path.exists(),'Refusing overwrite');path.write_text(json.dumps(value,indent=2)+'\n')

def verify_source(source):
    require(sha(source/'source-manifest.json')==SOURCE_SHA,'Unchanged probe manifest required')
    manifest=json.loads((source/'source-manifest.json').read_text())
    for row in manifest['files']:
        path=source/row['path'];require(path.is_file() and not path.is_symlink() and path.stat().st_size==row['bytes'] and sha(path)==row['sha256'],'Changed probe source/resource')
    expected={row['path'] for row in manifest['files']}|{'source-manifest.json'}
    actual={str(p.relative_to(source)) for p in source.rglob('*') if p.is_file()}
    require(actual==expected,'Probe source/resource closure differs')
    return manifest

def verify_reference(entries,jar_sha):
    require(sha(REFERENCE_ENTRIES)==REFERENCE_ENTRIES_SHA,'Probe reference entry manifest changed')
    require(entries==json.loads(REFERENCE_ENTRIES.read_text()),'Probe compiled entry payload differs from accepted0.1.1')
    require(jar_sha==REFERENCE_JAR_SHA,'Probe0.1.1 output differs; retain entries and stop for comparison')

def prepare(repo_root,consumer_root):
    repo=Path(repo_root).resolve(strict=True);consumer=Path(consumer_root).resolve(strict=True)
    source=repo/'work/network-ci-native-probe011';manifest=verify_source(source)
    target=consumer/SOURCE_RELATIVE;require(not target.exists(),'Probe source already staged')
    target.mkdir(parents=True)
    for row in manifest['files']:
        dest=target/row['path'];dest.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(source/row['path'],dest)
    shutil.copyfile(source/'source-manifest.json',target/'source-manifest.json');verify_source(target)
    return {'status':'EXACT_PROBE_SOURCE_STAGED_NO_JVM','source':str(target),'sourceManifestSha256':SOURCE_SHA,'files':len(manifest['files']),
            'output':str(consumer/OUTPUT_RELATIVE),'gameLaunched':False}

def inputs(api):
    source=api.parents[1]/SOURCE_RELATIVE;verify_source(source)
    runtime_path=api/'ci/runtime-restore/runtime-result.json';runtime=json.loads(runtime_path.read_text())
    require(runtime['status']=='OFFICIAL_RUNTIME_PREPARED_GAME_UNRUN' and runtime['nativeServerFiles']==95 and runtime['assetObjectsVerified']==3888,'Completed official runtime preparation required')
    export_path=Path(runtime['clientExport']['path']);require(sha(export_path)==runtime['clientExport']['sha256'],'Changed genuine client export')
    export=json.loads(export_path.read_text());require(len(export['inputs'])==95 and export['environment']=={},'Expected official95-input export')
    rows=[];classpath=[]
    for row in export['inputs']:
        path=Path(row['path']);require(path.resolve()==path and path.is_relative_to(api) and path.suffix=='.jar','Unexpected compile input')
        current=record(path);require(current['sha256']==row['sha256'],'Compile input changed');rows.append(current);classpath.append(str(path))
        with zipfile.ZipFile(path) as z:
            if 'META-INF/MANIFEST.MF' in z.namelist():
                require(not any(x.lower().startswith('class-path:') for x in z.read('META-INF/MANIFEST.MF').decode(errors='replace').splitlines()),'Implicit manifest classpath')
    jdk=api/'.toolchains/jdk-21.0.12.1+1'
    for name,digest in TOOLS.items():require(sha(jdk/name)==digest,'Approved compiler/runtime changed')
    return source,jdk,classpath,rows,record(runtime_path)

def execute(consumer_root,deadline=None):
    require(os.environ.get('GITHUB_ACTIONS')=='true' and os.environ.get('GITHUB_REPOSITORY')=='Nexa-MC/unified-infinity'
            and os.environ.get('GITHUB_REF')=='refs/heads/diagnostic/network-pair-20261006-a','Requires separately reviewed future pair CI')
    api=Path(consumer_root).resolve(strict=True)/'work/api1';source,jdk,classpath,rows,runtime_pin=inputs(api)
    output=Path(consumer_root).resolve(strict=True)/OUTPUT_RELATIVE;require(not output.exists(),'Fresh nonce build output required');output.mkdir()
    main=output/'main-classes';test=output/'test-classes';empty=output/'empty-sourcepath'
    for path in (main,test,empty):path.mkdir()
    limits=['-Xms16m','-Xmx192m','-XX:MaxMetaspaceSize=64m','-XX:ReservedCodeCacheSize=32m','-XX:MaxDirectMemorySize=16m','-XX:ActiveProcessorCount=1','-XX:+UseSerialGC']
    options=['-proc:none','--release','21','-g','-encoding','UTF-8','-implicit:none','-sourcepath',str(empty)]
    sources=sorted(source.glob('src/main/java/dev/infinity/networkcontrol/*.java'));require(len(sources)==4,'Expected unchanged four production classes')
    cp=os.pathsep.join(classpath)
    commands=[('compile-main',[str(jdk/'bin/javac'),*['-J'+x for x in limits],*options,'-cp',cp,'-d',str(main),*map(str,sources)]),
              ('compile-test',[str(jdk/'bin/javac'),*['-J'+x for x in limits],*options,'-cp',str(main)+os.pathsep+cp,'-d',str(test),str(source/'src/test/java/dev/infinity/networkcontrol/PreparedCodecTest.java')]),
              ('codec-test',[str(jdk/'bin/java'),*limits,'-cp',os.pathsep.join([str(test),str(main),cp]),'dev.infinity.networkcontrol.PreparedCodecTest'])]
    env={'PATH':str(jdk/'bin')+':/usr/bin:/bin','JAVA_HOME':str(jdk),'HOME':str(api/'ci/build-home'),'LANG':'C.UTF-8','LC_ALL':'C.UTF-8','TZ':'UTC'}
    phases=[]
    for name,command in commands:
        log=output/(name+'.log')
        timeout=120
        if deadline is not None:
            require(deadline>time.monotonic(),'Overall deadline expired before probe phase')
            timeout=min(timeout,deadline-time.monotonic())
        with log.open('w') as stream:r=bounded_process.run(command,cwd=output,env=env,stdout=stream,stderr=subprocess.STDOUT,timeout=timeout)
        phases.append({'name':name,'exitCode':r.returncode,'command':command,'log':record(log),'heapMiB':192,'processors':1})
        if r.returncode!=0:print(log.read_text(errors='replace')[-24000:],flush=True)
        require(r.returncode==0,'Probe compile/test failed: '+name)
    text=(output/'codec-test.log').read_text();require(text.splitlines().count('Prepared codec/input checks: 46; no network or game acceptance')==1,'Original46 assertions did not finish')
    require(inputs(api)[2:]==(classpath,rows,runtime_pin),'Official source/runtime inputs changed during probe build')
    members={'META-INF/MANIFEST.MF':b'Manifest-Version: 1.0\r\n\r\n','LICENSE':(source/'LICENSE').read_bytes(),
             'META-INF/neoforge.mods.toml':(source/'src/main/resources/META-INF/neoforge.mods.toml').read_bytes()}
    for path in sorted(main.rglob('*.class')):
        name=str(path.relative_to(main));require(name.startswith('dev/infinity/networkcontrol/'),'Foreign compiled class');members[name]=path.read_bytes()
    jar=output/ARTIFACT_NAME
    with zipfile.ZipFile(jar,'w',zipfile.ZIP_DEFLATED,compresslevel=9) as archive:
        for name,data in sorted(members.items()):
            info=zipfile.ZipInfo(name,(1980,1,1,0,0,0));info.compress_type=zipfile.ZIP_DEFLATED;info.external_attr=0o100644<<16;archive.writestr(info,data)
    entries={name:hashlib.sha256(data).hexdigest() for name,data in members.items()}
    save(output/'entry-manifest.json',entries)
    verify_reference(entries,sha(jar))
    result={'schema':1,'status':'PASS_COMPILE_REAL_CODEC_ONLY','checks':46,'version':'0.1.1','sourceManifestSha256':SOURCE_SHA,
            'probeJar':{'bytes':jar.stat().st_size,'sha256':sha(jar)},'artifactPath':str(jar),'runtimeInputReceipt':runtime_pin,
            'classpathInputs':rows,'phases':phases,'gameLaunched':False,'networkAcceptance':False,'classLoadingInGame':False,
            'publicInputClosureVerifiedBeforeAndAfter':True,'packaging':'Same deterministic ZIP recipe and192MiB directjavac commands as the reviewed local reference'}
    save(output/'result.json',result)
    save(output/'probe-build-binding.json',{'schema':1,'status':'BUILT','source_manifest_sha256':SOURCE_SHA,
                                         'artifact_path':str(jar),'artifact_sha256':sha(jar),'artifact_bytes':jar.stat().st_size})
    return result

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('action',choices=['prepare','execute']);p.add_argument('--repo-root',type=Path);p.add_argument('--consumer',type=Path,required=True);a=p.parse_args()
    print(json.dumps(prepare(a.repo_root,a.consumer) if a.action=='prepare' else execute(a.consumer),indent=2))
