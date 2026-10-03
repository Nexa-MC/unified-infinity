#!/usr/bin/env python3
"""Pinned public-input restoration and pure JVM diagnostics; no game or publication."""
import argparse, hashlib, json, os, pathlib, shutil, subprocess, tarfile, tempfile, urllib.error, urllib.parse, urllib.request

ROOT=pathlib.Path(__file__).resolve().parents[1]
CI=ROOT/'ci'
LOCK=json.loads((CI/'dependency-lock.json').read_text())
REPORT=ROOT/'diagnostic-output'
MAX_BYTES=512*1024*1024

def sha(path):
    digest=hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda:stream.read(1024*1024),b''): digest.update(block)
    return digest.hexdigest()

def destination(name,root=ROOT):
    part=pathlib.PurePosixPath(name)
    if part.is_absolute() or '..' in part.parts or not part.parts: raise ValueError('Unsafe path')
    path=root.joinpath(*part.parts)
    for parent in [path,*path.parents]:
        if parent==root.parent: break
        if parent.is_symlink(): raise ValueError('Symlink destination is not accepted')
    return path

def validate_url(url):
    parsed=urllib.parse.urlsplit(url)
    if parsed.scheme!='https' or parsed.hostname not in LOCK['allowedDownloadHosts'] or parsed.username or parsed.password or parsed.port not in (None,443):
        raise ValueError('Non-allowlisted HTTPS download or redirect')
    return url

class SafeRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self,req,fp,code,msg,headers,newurl):
        validate_url(newurl)
        return super().redirect_request(req,fp,code,msg,headers,newurl)

def verify(row,path):
    if path.stat().st_size!=row['bytes'] or sha(path)!=row['sha256']:
        raise ValueError('Pinned size/SHA-256 mismatch: '+row['path'])

def restore(row,fetch):
    path=destination(row['path'])
    if path.exists(): verify(row,path); return path
    if not fetch: raise FileNotFoundError('Missing pinned input: '+row['path'])
    if not 0<row['bytes']<=MAX_BYTES: raise ValueError('Input size exceeds bounded download')
    path.parent.mkdir(parents=True,exist_ok=True)
    opener=urllib.request.build_opener(SafeRedirect())
    last=None
    for url in row['urls']:
        validate_url(url)
        try:
            with opener.open(urllib.request.Request(url,headers={'User-Agent':'Unified-Infinity-bounded-CI/1'}),timeout=45) as response:
                with tempfile.NamedTemporaryFile(dir=path.parent,prefix='.download-',delete=False) as output:
                    temporary=pathlib.Path(output.name)
                    try:
                        count=0
                        while True:
                            data=response.read(1024*1024)
                            if not data:break
                            count+=len(data)
                            if count>row['bytes']:raise ValueError('Response exceeds pinned size')
                            output.write(data)
                        output.flush()
                        verify(row,temporary)
                        temporary.replace(path)
                    finally:
                        temporary.unlink(missing_ok=True)
            return path
        except urllib.error.HTTPError as error:
            if error.code not in (404,410):raise
            last=error
    raise RuntimeError('No pinned official URL supplied the input: '+row['path']) from last

def check_sources():
    manifest=json.loads((CI/'input-source-manifest.json').read_text())
    for name,digest in manifest['files'].items():
        if sha(destination(name))!=digest:raise ValueError('Source checksum mismatch: '+name)
    changed=json.loads((ROOT/'source-workspace/forge-config-c1/proposed-source-changes.json').read_text())['files']
    if len(changed)!=11:raise ValueError('C1 source slice changed')
    for row in changed:
        if sha(destination(row['candidate']))!=row['sha256']:raise ValueError('Exact C1 candidate source changed')
    return manifest

def run(name,command,receipt):
    result=subprocess.run(list(map(str,command)),cwd=ROOT,text=True,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,timeout=180)
    (REPORT/(name+'.log')).write_text(result.stdout)
    print(result.stdout,flush=True)
    receipt['steps'].append({'name':name,'exitCode':result.returncode,'command':list(map(str,command))})
    (REPORT/'receipt.json').write_text(json.dumps(receipt,indent=2)+'\n')
    if result.returncode:raise RuntimeError(name+' failed; see captured log')

def contracts(fetch):
    manifest=check_sources()
    rows=[row for row in LOCK['artifacts'] if row['tranche'] in ('toolchains','contracts','official-inputs')]
    restored={row['path']:restore(row,fetch) for row in rows}
    jdk=ROOT/'.toolchains/jdk-21.0.12.1+1'
    if not (jdk/'bin/java').is_file():
        with tarfile.open(restored['.toolchains/jdk21.tar.gz']) as archive:
            members=archive.getmembers()
            if sum(member.size for member in members)>1024*1024*1024:raise ValueError('Oversized JDK archive')
            if any(not pathlib.PurePosixPath(member.name).parts or pathlib.PurePosixPath(member.name).parts[0]!='jdk-21.0.12.1+1' for member in members):raise ValueError('Unexpected JDK root')
            archive.extractall(ROOT/'.toolchains',filter='data')
    java,javac=jdk/'bin/java',jdk/'bin/javac'
    REPORT.mkdir(exist_ok=True)
    receipt={'scope':'Exact C1 source contracts and ASM boundary; deterministic loader/watcher stand-ins; no game/native watcher/module assembly acceptance','sourceManifestSha256':sha(CI/'input-source-manifest.json'),'dependencyLockSha256':sha(CI/'dependency-lock.json'),'maxHeapMiB':512,'activeProcessors':1,'concurrentTestJvms':1,'gameLaunched':False,'sourceFiles':len(manifest['files']),'dependencyJars':20,'steps':[]}
    run('java-version',[java,'-Xmx512m','-XX:ActiveProcessorCount=1','-version'],receipt)
    libs=[restored[row['path']] for row in rows if row['tranche']=='contracts']
    classpath=os.pathsep.join(map(str,libs))
    harness=ROOT/'four-loader/forge-config-c1-tests';candidate=ROOT/'source-workspace/forge-config-c1/src/main/java'
    sources=sorted(p for p in candidate.rglob('*.java') if p.name!='ModConfigs.java')+sorted((harness/'stubs').rglob('*.java'))+sorted((harness/'reference').rglob('*.java'))+sorted((harness/'src').rglob('*.java'))
    sources += [destination(n) for n in manifest['unchangedApi1SupportSources']]
    sources += [harness/'integration-src/TransformContractTest.java']
    classes=REPORT/'classes';classes.mkdir(exist_ok=True)
    run('compile-contracts',[javac,'-J-Xmx512m','-J-XX:ActiveProcessorCount=1','--release','21','-proc:none','-encoding','UTF-8','-cp',classpath,'-d',classes,*sources],receipt)
    vm=[java,'-Xmx512m','-XX:ActiveProcessorCount=1','-Djava.awt.headless=true']
    with tempfile.TemporaryDirectory(prefix='c1-contract-',dir=REPORT) as temporary:
        for name,main in [('owner-contracts','net.neoforged.fml.config.CommonConfigContractTest'),('save-failure-contract','net.neoforged.fml.config.FailureOrderingTest')]:
            run(name,vm+['-Dc1.test.root='+temporary,'-cp',str(classes)+os.pathsep+classpath,main],receipt)
    official=[restored[row['path']] for row in rows if row['tranche']=='official-inputs']
    official += [restored[row['path']] for row in rows if '/night-config/core/' in row['path'] or '/annotations/24.1.0/' in row['path']]
    for kind,source in [('positive',harness/'official-input/ForgeConfigLifecycleProbe.java'),('negative',harness/'boundary/fixtures/NegativeConfigInputs.java')]:
        out=REPORT/kind;out.mkdir(exist_ok=True)
        run('compile-official-'+kind,[javac,'-J-Xmx512m','-J-XX:ActiveProcessorCount=1','--release','21','-proc:none','-cp',os.pathsep.join(map(str,official)),'-d',out,source],receipt)
    run('source-transform-boundary',vm+['-cp',str(classes)+os.pathsep+classpath,'TransformContractTest',REPORT/'positive',REPORT/'negative'],receipt)
    receipt['status']='PASS_SOURCE_CONTRACTS_GAME_AND_FULL_MODULE_CI_UNVERIFIED'
    (REPORT/'receipt.json').write_text(json.dumps(receipt,indent=2)+'\n')
    print(json.dumps(receipt,indent=2))
    if os.environ.get('GITHUB_STEP_SUMMARY'):
        with open(os.environ['GITHUB_STEP_SUMMARY'],'a') as summary:summary.write('C1 diagnostic source contracts passed. Exact source/dependency hashes verified; no full-module rebuild or Minecraft/runtime acceptance claimed.\n')

def main():
    p=argparse.ArgumentParser();p.add_argument('command',choices=['check','contracts']);p.add_argument('--fetch',action='store_true');p.add_argument('--verify-local-input-root',type=pathlib.Path);a=p.parse_args()
    check_sources()
    for row in LOCK['artifacts']:
        destination(row['path'])
        for url in row['urls']:validate_url(url)
        if a.verify_local_input_root:verify(row,destination(row['path'],a.verify_local_input_root.resolve()))
    if a.command=='contracts':contracts(a.fetch)
    else:print('PASS source/manifest/URL validation; no download or JVM performed')

if __name__=='__main__':main()
