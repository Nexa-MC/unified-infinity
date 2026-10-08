#!/usr/bin/env python3
"""Consumer-local full-module/PRODUCT sequence using the preserved source build recipe."""
import argparse
import datetime
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import time
import zipfile
import bounded_process

VERSION='2.0.0-beta.17+1.21.1+infinity-source+api1-emi-render-integration'
IDENTITY='54e5f302c1bad0de54a6845a50b128d6a2aa9f4fb9d44ec14c84c754d7fb21f6'
EXTRA='24a5d2d162cfad2a1a574c4d552e99dc6c6303a49d1e68b43a7b638f3b0930fd'
ORIGINALS={'sophisticatedcore-1.21.1-1.4.11.1553.jar':'acafbe72eb161b0b763feb61eba06584e97e48f563de75f767611ee520dfcad7',
           'sophisticatedbackpacks-1.21.1-3.25.34.1604.jar':'889fb2af58e9f7951d0553033a856078b28fcdf802ca13eb432336b2b7b9780c'}
EXPECTED={'service':'7fbabf5eb18b590bd5a30410d076fd814f11d03e8842e3327b4468217e275aa7',
          'game':'9dc29ac8a8030f629dd7afea8b744114504a552c4fce022c6199b23a1024e162',
          'fml':'0281b9389e92c7f560fd1921f86ece8203e23ff7ebbbd2240f10c911e6546c26',
          'product':'b20903f821455682ff5fee62491483e833252dc1a4f4caaa15bef51a356f1409'}

def require(value,message):
    if not value:raise ValueError(message)

def sha(path):
    with Path(path).open('rb') as stream:return hashlib.file_digest(stream,'sha256').hexdigest()

def save(path,value):
    require(not path.exists(),'Refusing overwrite: '+str(path));path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(value,indent=2)+'\n')

def layout(consumer):
    root=Path(consumer).resolve(strict=True);api=root/'work/api1';candidate=root/'work/emi-render-integration';core=api/'source-workspace/connector-four-loader'
    return root,api,candidate,core

def plan(consumer):
    root,api,candidate,core=layout(consumer)
    init=candidate/'bounded-build.init.gradle'
    common=[str(api/'.toolchains/gradle-8.11.1/bin/gradle'),'--offline','--no-daemon','--no-parallel','--max-workers=1',
            '--no-build-cache','--no-configuration-cache','--console=plain','--dependency-verification=strict',
            '-Dorg.gradle.jvmargs=-Xmx512m -XX:ActiveProcessorCount=1 -Dfile.encoding=UTF-8',
            '-Dorg.gradle.java.installations.auto-download=false','--init-script',str(init),
            '--init-script',str(candidate/'cold-repositories.init.gradle')]
    mods=root/'complex-mod-research'
    arguments=['-PemiCoreJar='+str(mods/next(n for n in ORIGINALS if 'core' in n)),
               '-PemiBackpackJar='+str(mods/next(n for n in ORIGINALS if 'backpacks' in n)),
               ':fml-unified:jar',':fml-unified:sourcesJar','fullJar','check','writeProductCompileInputs']
    return {'schema':1,'consumerRoot':str(root),'apiRoot':str(api),'candidateRoot':str(candidate),
            'coreCommand':[*common,'--project-cache-dir',str(candidate/'cold-core-cache'),'-p',str(core),*arguments],
            'productCommandPrefix':[*common,'--project-cache-dir',str(candidate/'cold-product-cache'),'-p',str(api/'runtime-bundle')],
            'perJvmHeapMiB':512,'processorsPerBuildJvm':1,'workers':1,'gameTask':False,
            'expectedCandidateIdentity':IDENTITY,'expectedArtifacts':EXPECTED}

def prepare(consumer):
    root,api,candidate,core=layout(consumer)
    mirror=api/'ci/runtime-maven'
    # A consumer-local repository substitution, never a source/dependency pin change.
    script='''def mirror = new File(System.getenv('PAIR_MAVEN_MIRROR')).toURI()
def coreMirror = new File(System.getenv('PAIR_CORE_MAVEN')).toURI()
settingsEvaluated { settings ->
    // Keep the original pinned SNAPSHOT exclusiveContent owner intact.
    // Gradle --offline prohibits remote fallback requests; both added mirrors
    // contain only separately verified bytes from the published locks.
    settings.pluginManagement.repositories.maven { url = coreMirror }
    settings.pluginManagement.repositories.maven { url = mirror }
}
allprojects {
    buildscript.repositories.maven { url = coreMirror }
    buildscript.repositories.maven { url = mirror }
    afterEvaluate {
        repositories.maven { url = coreMirror }
        repositories.maven { url = mirror }
    }
    tasks.withType(JavaCompile).configureEach {
        options.forkOptions.memoryMaximumSize='512m'
        options.forkOptions.jvmArgs=['-XX:ActiveProcessorCount=1']
    }
    tasks.withType(JavaExec).configureEach { maxHeapSize='512m'; jvmArgs '-XX:ActiveProcessorCount=1' }
    tasks.withType(Test).configureEach { maxHeapSize='512m'; maxParallelForks=1; jvmArgs '-XX:ActiveProcessorCount=1' }
}
'''
    p=candidate/'cold-repositories.init.gradle';require(not p.exists(),'Repository adapter already exists');p.write_text(script)
    result=plan(consumer);result['status']='BUILD_PLAN_PREPARED_NOT_EXECUTED';result['repositoryAdapterSha256']=sha(p)
    save(candidate/'cold-build-plan.json',result)
    return result

def command(consumer,argv,name,timeout,deadline=None):
    root,api,candidate,core=layout(consumer);jdk=api/'.toolchains/jdk-21.0.12.1+1'
    env={'PATH':str(jdk/'bin')+':/usr/bin:/bin','JAVA_HOME':str(jdk),'HOME':str(api/'source-workspace/home'),
         'GRADLE_USER_HOME':str(api/'source-workspace/gradle-cache'),'XDG_CACHE_HOME':str(api/'source-workspace/xdg-cache'),
         'XDG_CONFIG_HOME':str(api/'source-workspace/xdg-config'),'LANG':'C.UTF-8','LC_ALL':'C.UTF-8','TZ':'UTC',
         'CI':'true','PUBLISH_RELEASE_TYPE':'alpha','PAIR_MAVEN_MIRROR':str(api/'ci/runtime-maven'),
         'PAIR_CORE_MAVEN':str(api/'source-workspace/pinned-build-maven'),
         'FORGE_FACADE_HOST_LIBRARIES':str(api/'run/neoforge-native/libraries'),
         '_JAVA_OPTIONS':'-Xmx512m -XX:ActiveProcessorCount=1 -Dfile.encoding=UTF-8',
         'JAVA_TOOL_OPTIONS':'-Duser.home='+str(api/'source-workspace/home')}
    for name_ in ('HOME','GRADLE_USER_HOME','XDG_CACHE_HOME','XDG_CONFIG_HOME'):Path(env[name_]).mkdir(parents=True,exist_ok=True)
    evidence=candidate/'cold-evidence';evidence.mkdir(exist_ok=True);log=evidence/(name+'.log');receipt=evidence/(name+'.json')
    require(not log.exists() and not receipt.exists(),'Refusing repeated cold build receipt')
    started=datetime.datetime.now(datetime.timezone.utc).isoformat()
    if deadline is not None:
        require(deadline>time.monotonic(),'Overall deadline expired before build')
        timeout=min(timeout,deadline-time.monotonic())
    with log.open('w') as output:
        result=bounded_process.run(argv,cwd=api,env=env,stdout=output,stderr=subprocess.STDOUT,timeout=timeout)
    value={'schema':1,'status':'PASS' if result.returncode==0 else 'FAILED','exitCode':result.returncode,'startedUtc':started,
           'finishedUtc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'command':argv,'log':str(log),'logSha256':sha(log),
           'perJvmHeapMiB':512,'activeProcessors':1,'workers':1,'gameTask':False}
    save(receipt,value)
    if result.returncode!=0:print(log.read_text(errors='replace')[-48000:],flush=True)
    require(result.returncode==0,'Cold build failed; preserved log '+str(log))
    return receipt

def capture_core(consumer):
    root,api,candidate,core=layout(consumer)
    expected=json.loads((candidate/'build-identity.json').read_text())
    generated=json.loads((core/'components/infinity-core/build/generated/resources/infinity/META-INF/unified-infinity/build-identity.json').read_text())
    require(generated==expected and generated['identity_sha256']==IDENTITY,'Cold build changed source/dependency/compiler identity')
    paths={'service':core/f'build/libs/connector-{VERSION}-full.jar','game':core/f'build/libs/connector-{VERSION}-mod.jar',
           'fml':api/'source-workspace/fml-unified/build/libs/fml-loader-4.0.42-unified-source.jar'}
    rows={role:{'path':str(path),'sha256':sha(path)} for role,path in paths.items()}
    for role,row in rows.items():require(row['sha256']==EXPECTED[role],'Cold output differs; compare archive entries before accepting: '+role)
    # Preserve original historical receipt; only a separately named fresh receipt is produced.
    save(candidate/'cold-built-core-artifacts.json',rows)
    return rows

def execute(consumer,deadline=None):
    require(os.environ.get('GITHUB_ACTIONS')=='true' and os.environ.get('GITHUB_REPOSITORY')=='Nexa-MC/unified-infinity'
            and os.environ.get('GITHUB_REF')=='refs/heads/diagnostic/network-pair-20261006-a',
            'Actual execution requires the separately reviewed future pair diagnostic branch')
    root,api,candidate,core=layout(consumer);recipe=json.loads((candidate/'cold-build-plan.json').read_text())
    require(recipe['repositoryAdapterSha256']==sha(candidate/'cold-repositories.init.gradle'),'Repository adapter changed')
    for name,digest in ORIGINALS.items():require(sha(root/'complex-mod-research'/name)==digest,'Changed original regression fixture')
    relative=Path('libraries/net/minecraft/server/1.21.1-20240808.144430/server-1.21.1-20240808.144430-extra.jar')
    official=api/'run/neoforge-native'/relative;require(sha(official)==EXTRA,'Server manifest regression input differs')
    fixture=api/'run/api1-unified-server-2'/relative;require(not fixture.exists(),'Refusing fixture overwrite');fixture.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(official,fixture)
    core_receipt=command(consumer,recipe['coreCommand'],'core',1200,deadline);rows=capture_core(consumer)
    manifest=api/'run/client-dev/development-build/moddev/client-launch-inputs.json';data=json.loads(manifest.read_text())
    for row in data['inputs']:require(sha(Path(row['path']))==row['sha256'],'PRODUCT compile manifest input differs')
    args=[*recipe['productCommandPrefix'],'-PmanagedCoreJar='+rows['service']['path'],'-PmanagedCoreSha256='+rows['service']['sha256'],
          '-PunifiedFmlJar='+rows['fml']['path'],'-PffapiJar='+str(api/'docs/research/upstream/ffapi-baseline.jar'),
          '-PqslInventory='+str(api/'docs/four-loader/quilt/bundled-tooltip.json'),'-PclientClasspathManifest='+str(manifest),'jar','sourcesJar','check']
    product_receipt=command(consumer,args,'product',600,deadline)
    paths={role:Path(row['path']) for role,row in rows.items()};paths['product']=api/'runtime-bundle/build/libs/unified-infinity-0.1.0-dev.jar'
    artifacts={};entries={};owners={};packages={}
    for role,path in paths.items():
        require(sha(path)==EXPECTED[role],'Cold artifact identity differs; no automatic relaxation: '+role)
        dest=candidate/'cold-artifacts'/(role+'.jar');dest.parent.mkdir(exist_ok=True);shutil.copyfile(path,dest)
        artifacts[role]={'path':str(dest),'sha256':sha(dest)}
        with zipfile.ZipFile(dest) as z:
            names=[n for n in z.namelist() if not n.endswith('/')];require(len(names)==len(set(names)),'Duplicate archive entry')
            entries[role]={n:hashlib.sha256(z.read(n)).hexdigest() for n in names}
            for name in names:
                if name.endswith('.class'):
                    require(name not in owners,'Duplicate top-level class owner');owners[name]=role;packages.setdefault(name.rsplit('/',1)[0],set()).add(role)
    require(all(len(value)==1 for value in packages.values()),'Split top-level package')
    base=json.loads((candidate/'fml-base-build-receipt.json').read_text())
    for name,digest in base['sources'].items():require(sha(api/'source-workspace'/name)==digest,'FML receipt source differs')
    require(base['sha256']==artifacts['fml']['sha256'],'Compiled FML base differs')
    base.update(artifact=artifacts['fml']['path'],sourceBuildReceipt=str(core_receipt),buildKind='Cold consumer full-source build, original candidate identity and artifact bytes verified; game unrun')
    save(candidate/'cold-fml-base-build-receipt.json',base)
    save(candidate/'cold-built-tuple-artifacts.json',artifacts);save(candidate/'cold-artifact-entry-manifests.json',entries)
    result={'schema':1,'status':'COLD_TUPLE_BUILT_CHECKED_GAME_UNRUN','sourceIdentity':IDENTITY,'artifacts':artifacts,
            'coreBuildReceipt':str(core_receipt),'productBuildReceipt':str(product_receipt),'sourceRecords':670,'dependencyRecords':169,
            'duplicateClasses':0,'splitPackages':0,'gameLaunched':False}
    save(candidate/'cold-build-result.json',result);return result

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('action',choices=['prepare','execute']);parser.add_argument('--consumer',type=Path,required=True);args=parser.parse_args()
    print(json.dumps(prepare(args.consumer) if args.action=='prepare' else execute(args.consumer),indent=2))
