#!/usr/bin/env python3
"""Fresh core producer -> original Forge probe/native driver, all in one consumer.

This compiles source; it does not package the full core runtime or qualify an old
runtime profile. The caller first restores and verifies the unchanged official
runtime in this consumer using the existing approved CI stage.
"""
from pathlib import Path
import hashlib, importlib.util, json, os, shutil, subprocess, sys, tarfile, time, zipfile
HERE=Path(__file__).resolve().parent
CORE_ARCHIVE='forge-play-compile-qualified-core-sources-v2.zip'
CORE_SHA='fcd8aba206abb28ba92d7e9ae8611c716cb9a6592a7080457706018015a4b838'
BASE_SHA='f22095224db189603b74ef4b147a5c8eae0caed5c2abdeaf1ae02e3b2215f111'
CORE_LOCK_SHA='43ac0ce038cb00da23f0ae625f64c4b1bb83251c82ee2269b6ae698f50d4389b'
NATIVE_SHA='6faad7d182a47d66ce28db569e9f4f475d9bf7bc4db452b9f3010b74c050008c'
FALSE_FLAGS={'gameLaunched':False,'networkAcceptance':False,'fullApiCompatibility':False,'readyRuntimeBundle':False}

def require(ok,msg):
    if not ok:raise ValueError(msg)
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def pin(p):
    p=Path(p).absolute();require(p.is_file() and not any(q.is_symlink() for q in [p,*p.parents]),'Regular canonical file required: '+str(p))
    return {'path':str(p),'bytes':p.stat().st_size,'sha256':sha(p)}
def write(p,obj):
    p=Path(p);p.parent.mkdir(parents=True,exist_ok=True)
    with p.open('x') as f:json.dump(obj,f,indent=2);f.write('\n')
def load(p):return json.loads(Path(p).read_text())
def module(name,p):
    spec=importlib.util.spec_from_file_location(name,p);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m

def verify_stage(stage):
    manifest=load(Path(stage)/'input-manifest.json')
    require(manifest['schema']=='same-root-stage-inputs-v1','Stage manifest schema')
    for row in manifest['files']:
        rel=Path(row['path']);require(not rel.is_absolute() and '..' not in rel.parts,'Unsafe stage input path')
        actual=pin(Path(stage)/rel)
        require((actual['bytes'],actual['sha256'])==(row['bytes'],row['sha256']),'Stage materialized input drift: '+row['path'])
    return manifest

def prepare(repo,consumer):
    """Verify baseline then apply only exact reviewed source delta; no JVM/network."""
    repo=Path(repo).resolve(strict=True);consumer=Path(consumer).resolve(strict=True)
    sys.path.insert(0,str(repo/'work/network-pair-cold-glue'));import ffapi_sources
    ffapi_sources.verify_sources(consumer)
    stage=consumer/'work/forge-same-root';require(not stage.exists(),'Fresh same-root stage required')
    manifest=verify_stage(HERE)
    require(sha(HERE/CORE_ARCHIVE)==CORE_SHA,'Candidate archive drift')
    baseline=repo/'work/emi-render-integration/candidate-complete-core-sources.zip';require(sha(baseline)==BASE_SHA,'Baseline source archive drift')
    delta=load(HERE/'core-delta.json');require(delta['candidateSha256']==CORE_SHA and delta['baselineSha256']==BASE_SHA,'Delta binding drift')
    with zipfile.ZipFile(baseline) as before,zipfile.ZipFile(HERE/CORE_ARCHIVE) as after:
        old=[i.filename for i in before.infolist() if not i.is_dir()];new=[i.filename for i in after.infolist() if not i.is_dir()];require(len(old)==len(set(old)) and len(new)==len(set(new)),'Duplicate source archive entries')
        require(set(old)<=set(new) and len(set(new)-set(old))==5,'Unexpected source removal/addition')
        differences={n for n in new if n not in old or before.read(n)!=after.read(n)}
        require(differences=={r['path'] for r in delta['exactDelta']} and len(differences)==7,'Exact seven-file core delta required')
        core=consumer/'work/api1/source-workspace/connector-four-loader'
        payloads=[]
        for row in delta['exactDelta']:
            rel=Path(row['path']);require(not rel.is_absolute() and '..' not in rel.parts,'Unsafe source destination')
            dest=core/rel;raw=after.read(row['path']);require(hashlib.sha256(raw).hexdigest()==row['candidateSha256'],'Candidate source pin')
            if row['baselineSha256'] is None:require(not dest.exists(),'Added source already exists')
            else:require(sha(dest)==row['baselineSha256'],'Original source changed')
            payloads.append((dest,raw))
    # Stage code and sources become part of consumer closure, not external refs.
    for row in manifest['files']:
        src=HERE/row['path'];dest=stage/row['path'];dest.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(src,dest)
    shutil.copyfile(HERE/'input-manifest.json',stage/'input-manifest.json')
    for dest,raw in payloads:
        dest.parent.mkdir(parents=True,exist_ok=True);dest.write_bytes(raw)
    original=load(repo/'work/network-pair-cold-glue/source-manifest.json')
    paths={r['destination'] for r in original['files']}
    paths.update(str(p.relative_to(consumer)) for p,_ in payloads)
    rows=[]
    for rel in sorted(paths):
        p=consumer/rel;rows.append({'path':rel,'bytes':p.stat().st_size,'sha256':sha(p)})
    proof={'schema':1,'status':'FORGE_SOURCE_DERIVATIVE_MATERIALIZED_NOT_COMPILED','baselineSourceReceipt':pin(consumer/'source-materialization.json'),'baselineSourceArchive':{'sha256':BASE_SHA},'candidateSourceArchive':pin(stage/CORE_ARCHIVE),'delta':pin(stage/'core-delta.json'),'sourceFilesCopiedWithExactHashes':rows,**FALSE_FLAGS}
    write(consumer/'evidence/source-materialization.json',proof)
    for rel in ['work/network-pair-cold-glue/profiles/ffapi-core-dependency-lock.json','work/fabric-network-probe/jdk-input-verification.json']:
        src=repo/rel;dst=stage/Path(rel).name;shutil.copyfile(src,dst)
    return proof

def verify_toolchains(api,evidence):
    """Compare all extracted regular members against original pinned archives."""
    archives=[];toolchains=api/'.toolchains';lock=load(api/'ci/runtime-restore/input-lock.json')
    for row in lock['artifacts']:
        if row.get('phase')!='toolchains':continue
        archive=api/row['path'];require(archive.stat().st_size==row['bytes'] and sha(archive)==row['sha256'],'Toolchain archive mismatch')
        record={'archive':pin(archive),'members':[]};archives.append(record)
        if archive.suffix=='.zip':
            with zipfile.ZipFile(archive) as z:
                for info in z.infolist():
                    if info.is_dir():continue
                    p=toolchains/info.filename;require(p.resolve().is_relative_to(toolchains),'Toolchain path escape')
                    digest=hashlib.sha256(z.read(info)).hexdigest();require(p.is_file() and p.stat().st_size==info.file_size and sha(p)==digest,'Toolchain extracted member differs')
                    record['members'].append(pin(p))
        else:
            with tarfile.open(archive,'r:gz') as z:
                for info in z:
                    p=toolchains/info.name;require(p.resolve().is_relative_to(toolchains),'Toolchain path escape')
                    if info.isfile():
                        digest=hashlib.file_digest(z.extractfile(info),'sha256').hexdigest();require(p.is_file() and p.stat().st_size==info.size and sha(p)==digest,'Toolchain extracted member differs');record['members'].append(pin(p))
                    elif info.issym():require(p.is_symlink() and str(p.readlink())==info.linkname,'Toolchain symbolic member differs')
    require(len(archives)==2,'Expected exact JDK and Gradle archives')
    result={'schema':1,'archives':archives,'allRegularArchiveMembersMatchExistingExtractedBytes':True,**FALSE_FLAGS};write(evidence/'toolchains.json',result);return result

def compile_core(consumer,deadline):
    root=Path(consumer).resolve(strict=True);api=root/'work/api1';stage=root/'work/forge-same-root';evidence=root/'evidence';source=api/'source-workspace';core=source/'connector-four-loader';jdk=api/'.toolchains/jdk-21.0.12.1+1';gradle=api/'.toolchains/gradle-8.11.1'
    verify_stage(stage)
    # All preceding owned phases must have completed before this handoff.
    # Rebind byte-identical helper modules to their consumer-owned paths.
    for name in ['owned_compile_process_v3','owner_completion_validation','owner_completion_model','bounded_process']:
        old=sys.modules.get(name)
        if old is not None:
            require(sha(Path(old.__file__))==sha(stage/'support'/(name+'.py')),'Unexpected cached owner helper')
            del sys.modules[name]
    sys.path.insert(0,str(stage/'support'));import owned_compile_process_v3 as owner
    require(Path(owner.__file__).resolve()==stage/'support/owned_compile_process_v3.py','Owner import escaped consumer')
    post=module('same_root_postconditions',stage/'compile_postconditions.py')
    materialized=load(evidence/'source-materialization.json');lockpath=stage/'ffapi-core-dependency-lock.json';require(sha(lockpath)==CORE_LOCK_SHA,'Original core lock drift');lock=load(lockpath)
    for row in lock['artifacts']:
        p=api/row['path'];require(p.stat().st_size==row['bytes'] and sha(p)==row['sha256'],'Core dependency mismatch')
    fml=source/'fml-unified/provenance/compile-classpath-lock.json'
    for row in load(fml)['artifacts']:require(sha(api/row['path'])==row['sha256'],'FML dependency mismatch')
    for row in materialized['sourceFilesCopiedWithExactHashes']:require(sha(root/row['path'])==row['sha256'],'Materialized source mismatch')
    require(not (core/'build').exists(),'Core output must be fresh')
    verify_toolchains(api,evidence)
    command=[str(gradle/'bin/gradle'),'--offline','--no-daemon','--no-parallel','--max-workers=1','--no-build-cache','--no-configuration-cache','--console=plain','--dependency-verification=strict','-Dorg.gradle.jvmargs=-Xms32m -Xmx512m -XX:MaxMetaspaceSize=256m -XX:ActiveProcessorCount=1 -XX:+UseSerialGC -Dfile.encoding=UTF-8','-Dorg.gradle.java.installations.auto-download=false','-Dorg.gradle.java.installations.auto-detect=false','-Dorg.gradle.java.installations.paths='+str(jdk),'--gradle-user-home',str(source/'gradle-cache'),'--project-cache-dir',str(stage/'project-cache')]
    for name in ['bounded-build.init.gradle','cold-repositories.init.gradle','verified-repositories.init.gradle','compile-only-guard.init.gradle']:command+=['--init-script',str(stage/'support'/name)]
    command+=['-p',str(core),'compileJava','compileModJava']
    env={'PATH':str(jdk/'bin')+':/usr/bin:/bin','JAVA_HOME':str(jdk),'HOME':str(source/'home'),'GRADLE_USER_HOME':str(source/'gradle-cache'),'XDG_CACHE_HOME':str(source/'xdg-cache'),'XDG_CONFIG_HOME':str(source/'xdg-config'),'LANG':'C.UTF-8','LC_ALL':'C.UTF-8','TZ':'UTC','PUBLISH_RELEASE_TYPE':'alpha','PAIR_API_ROOT':str(api),'PAIR_MAVEN_MIRROR':str(api/'ci/runtime-maven'),'PAIR_CORE_MAVEN':str(source/'pinned-build-maven'),'FORGE_FACADE_HOST_LIBRARIES':str(api/'run/neoforge-native/libraries'),'_JAVA_OPTIONS':'-XX:ActiveProcessorCount=1 -XX:MaxMetaspaceSize=256m -XX:+UseSerialGC','JAVA_TOOL_OPTIONS':'-Xmx2g -Duser.home='+str(source/'home'),'JAVA_OPTS':'-Xms16m -Xmx64m -XX:ActiveProcessorCount=1'}
    for k in ['HOME','GRADLE_USER_HOME','XDG_CACHE_HOME','XDG_CONFIG_HOME']:Path(env[k]).mkdir(parents=True,exist_ok=True)
    timeout=min(1500,deadline-time.monotonic()-180);require(timeout>=60,'Insufficient core budget plus probes/cleanup')
    log=evidence/'core.log';journal=evidence/'core-owner.json';receipt=evidence/'core-producer.json'
    record={'schema':1,'command':command,'environment':env,'timeoutSeconds':timeout,'sourceMaterializationSha256':sha(evidence/'source-materialization.json'),'toolchainReceiptSha256':sha(evidence/'toolchains.json'),'originalCoreLockSha256':sha(lockpath),'originalFmlLockSha256':sha(fml),'successfulCompilePostconditions':False,**FALSE_FLAGS}
    code=1
    try:
        with log.open('x') as out:r=owner.run(command,cwd=api,env=env,stdout=out,stderr=subprocess.STDOUT,timeout=timeout,cancel_file=evidence/'cancel',owner_receipt=journal)
        code=r.returncode;record['exitCode']=code;record['liveOwnerValidation']=owner.validate_completion(journal,r,command)
        record['allSourcePinsUnchanged']=all(sha(root/p['path'])==p['sha256'] for p in materialized['sourceFilesCopiedWithExactHashes'])
        names=['components/infinity-core/build/generated/sources/infinity/java/org/sinytra/connector/infinity/BuildIdentity.java','components/infinity-core/build/generated/resources/infinity/META-INF/unified-infinity/build-identity.json','build/classes/java/mod/org/sinytra/connector/mod/FmlGameCompatibilityComponent.class','build/moddev/artifacts/neoforge-21.1.219.jar']
        record['outputs']=[]
        for name in names:
            p=core/name;row={'path':str(p.relative_to(root)),'exists':p.is_file()}
            if p.is_file():row.update(bytes=p.stat().st_size,sha256=sha(p))
            record['outputs'].append(row)
        record['allExpectedOutputsPresent']=all(x['exists'] for x in record['outputs'])
        require(code==0 and record['liveOwnerValidation']['qualified'] and record['allExpectedOutputsPresent'] and record['allSourcePinsUnchanged'],'Core compile or cleanup/source/output failed')
        record['identityVerification']=post.verify_identity(root,core,materialized,lock,load(stage/'core-delta.json')['exactDelta'],jdk/'release')
        require(record['identityVerification']['identitySha256']=='346c02cb7e638f53c40f476e23ad56ff8939a57b94e43ca2f181651f45cf91a5' and record['identityVerification']['sourceCount']==675 and record['identityVerification']['dependencyCount']==169,'Exact reviewed Forge source/compiler identity mismatch')
        record['hookClassValidation']=post.class_has_install_call((core/names[2]).read_bytes());require(record['hookClassValidation'],'Compiled Forge hook absent')
        require(sha(core/names[3])==NATIVE_SHA,'Strict original core-generated NeoForge artifact mismatch')
        verify_stage(stage)
        record.update(effectiveExitCode=0,successfulCompilePostconditions=True)
    except BaseException as error:
        record.update(error=type(error).__name__+': '+str(error),effectiveExitCode=code or 1);raise
    finally:
        if log.exists():record['logSha256']=sha(log)
        write(receipt,record);print('FORGE_FRESH_CORE_PRODUCER '+json.dumps(record),flush=True)
    return receipt

def build_probes(consumer,producer,deadline):
    root=Path(consumer).resolve(strict=True);stage=root/'work/forge-same-root';api=root/'work/api1';core=api/'source-workspace/connector-four-loader';jdk=api/'.toolchains/jdk-21.0.12.1+1'
    verify_stage(stage)
    b=module('same_root_probe_bundle',stage/'forge_probe_bundle.py');pr=load(producer);sm=load(root/'evidence/source-materialization.json')
    # Probe consumer sees original Forge only; native driver sees real core-generated types.
    original=[pin(p) for p in sorted((root/'forge-inputs').glob('*.jar'))]
    expected={Path(r['path']).name:r for r in load(stage/'original-forge-source-lock.json')['artifacts'] if Path(r['path']).name in {'forge-1.21.1-52.1.0-universal.jar','eventbus-6.2.27.jar','javafmllanguage-1.21.1-52.1.0.jar','fmlcore-1.21.1-52.1.0.jar'}}
    require(len(original)==len(expected)==4,'Exactly four original Forge inputs required')
    for row in original:
        original_pin=expected.get(Path(row['path']).name)
        require(original_pin is not None and (row['bytes'],row['sha256'])==(original_pin['size'],original_pin['sha256']),'Original Forge input drift before probe compilation')
    cp=original+[pin(core/'build/moddev/artifacts/minecraft-1.21.1-clean.jar')]
    for name in ['io/netty/netty-buffer/4.1.97.Final/netty-buffer-4.1.97.Final.jar','io/netty/netty-common/4.1.97.Final/netty-common-4.1.97.Final.jar','io/netty/netty-transport/4.1.97.Final/netty-transport-4.1.97.Final.jar','org/apache/commons/commons-lang3/3.14.0/commons-lang3-3.14.0.jar']:cp.append(pin(api/'ci/runtime-maven'/name))
    generated=pin(core/'build/moddev/artifacts/neoforge-21.1.219.jar');native=[generated]
    for row in load(stage/'ffapi-core-dependency-lock.json')['artifacts']:
        p=api/row['path']
        if p.suffix=='.jar':native.append(pin(p))
    jdkfiles=[]
    for row in load(stage/'jdk-input-verification.json')['files']:
        p=api/'.toolchains'/row['path'];actual=pin(p);require((actual['bytes'],actual['sha256'])==(row['bytes'],row['sha256']),'JDK manifest mismatch');jdkfiles.append(actual)
    cfg={'schema':'forge-play-build-config-v1','source_manifest':pin(stage/'probe-source-manifest.json'),'provenance':[pin(stage/'original-forge-source-lock.json'),pin(stage/'ffapi-core-dependency-lock.json'),pin(stage/'jdk-input-verification.json'),pin(stage/'core-delta.json')],'classpath':{'forge_probe':cp,'native_driver':native},'jdk_files':jdkfiles,'javac':str(jdk/'bin/javac'),'producer_receipt':pin(producer),'generated_native_jar':generated,'owner_support':[pin(stage/'support'/n) for n in ['owned_compile_process_v3.py','bounded_process.py','owner_completion_model.py','owner_completion_validation.py']],'producer_closure':{'owner':pin(root/'evidence/core-owner.json'),'log':pin(root/'evidence/core.log'),'source_materialization':pin(root/'evidence/source-materialization.json'),'toolchain_receipt':pin(root/'evidence/toolchains.json'),'outputs':[pin(root/r['path']) for r in pr['outputs']],'source_files':[pin(root/r['path']) for r in sm['sourceFilesCopiedWithExactHashes']]}}
    b.validate_config(cfg);config=stage/'build-config.json';write(config,cfg)
    remaining=deadline-time.monotonic();require(remaining>90,'Probe/cleanup budget exhausted')
    bundle=b.build(config,sha(config),stage/'built-probes',time.time()+min(170,remaining-25))
    verified=b.validate_bundle(bundle['path'],bundle['sha256'])
    require(all(Path(r['path']).is_relative_to(root) for r in verified['input_pins']),'Bundle closure escapes same consumer')
    verify_stage(stage)
    result={'schema':'same-root-forge-compile-v1','status':'FRESH_CORE_AND_BOTH_PROBES_COMPILED','producer':pin(producer),'bundle':bundle,'coreIdentity':pr['identityVerification']['identitySha256'],'nextGate':'Explicit Forge derivative profile, full core/product/fml packaging, same core identity binding, runtime artifact/classpath verification required',**FALSE_FLAGS}
    write(root/'evidence/same-root-result.json',result);print('FORGE_SAME_ROOT_RESULT '+json.dumps(result),flush=True);return result

def execute(repo,consumer,deadline):
    """Caller owns absolute monotonic deadline; no external process or CI dispatched here."""
    require(60<deadline-time.monotonic()<=35*60,'Bounded same-root deadline required')
    prepare(repo,consumer)
    restored=module('same_root_restore',Path(consumer)/'work/forge-same-root/restore_core_inputs.py').restore(Path(repo),Path(consumer),deadline)
    write(Path(consumer)/'evidence/core-inputs.json',restored)
    producer=compile_core(consumer,deadline)
    return build_probes(consumer,producer,deadline)
