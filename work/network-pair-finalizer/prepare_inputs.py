#!/usr/bin/env python3
"""Prepare exact v2 supervisor input bases; actual graphics evidence remains separate."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import tarfile

ROOT=Path(__file__).resolve().parents[2]
API=ROOT/'work/api1'
ASSEMBLY=ROOT/'work/network-pair-assembled-local4'
ASSEMBLY_SHA='b6dc08093e520ebfbc27b3eeec40de0d7fd9dae002f422ad0cf45c5c9efa7496'
VERIFICATION_SHA='34c8572a40029f6e84d48d4bca47c8e064d28a3ac663f1a7e9d0b43ffb4126c3'
PROBE_SOURCE=ROOT/'work/network-ci-native-probe'
SOURCE_SHA='65cf1c852d6e07226fcd7d2f66df8d202f3a6e70cd4d8f963c6dc40b28554909'
PROBE_BUILD=ROOT/'work/nonce-probe-local1/runs/reviewed-vq74a3nj/probe-build-binding.json'
PROBE_BUILD_SHA='d2ea458ea586ad16da9a8a17c117abcb596466563c13785ca709bf31610d028b'
JDK=API/'.toolchains/jdk-21.0.12.1+1'
JDK_ARCHIVE=API/'.toolchains/jdk21.tar.gz'
JDK_ARCHIVE_SHA='ce79869e1307ed8ee1e2baa86a412b1eb5b75d10a01006d788a6f968bcfaee94'

def require(ok,message):
    if not ok:raise ValueError(message)

def digest(path):
    with Path(path).open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()

def pin(path):
    path=Path(path)
    require(path.is_absolute() and path.resolve()==path and not path.is_symlink() and path.is_file(),'Expected canonical regular input')
    return {'path':str(path),'bytes':path.stat().st_size,'sha256':digest(path)}

def load(path,sha):
    require(digest(path)==sha,'Changed pinned document: '+str(path))
    return json.loads(Path(path).read_text())

def save(path,value):
    require(not path.exists(),'Refusing overwrite')
    path.write_text(json.dumps(value,indent=2)+'\n')
    return pin(path)

def jdk_closure():
    require(digest(JDK_ARCHIVE)==JDK_ARCHIVE_SHA,'Approved official JDK distribution archive changed')
    files=[];links=[];expected=set()
    with tarfile.open(JDK_ARCHIVE,mode='r|gz') as archive:
        for member in archive:
            parts=Path(member.name).parts
            require(parts and parts[0]==JDK.name and '..' not in parts and not Path(member.name).is_absolute(),'JDK archive member escaped')
            relative=Path(*parts[1:]);target=JDK/relative
            if member.isdir():continue
            expected.add(str(relative))
            if member.issym():
                require(relative.parts[0]=='legal' and target.is_symlink() and os.readlink(target)==member.linkname,'Changed or nonlegal JDK alias')
                resolved=target.resolve(strict=True)
                require(resolved.is_relative_to(JDK) and resolved.is_file(),'JDK alias escaped official root')
                links.append({'path':str(target),'link_text':member.linkname,'resolved_path':str(resolved),'jdk_root':str(JDK)})
            else:
                require(member.isfile() and target.is_file() and not target.is_symlink(),'Unexpected JDK entry type')
                stream=archive.extractfile(member)
                original=hashlib.file_digest(stream,'sha256').hexdigest()
                record=pin(target)
                require(record['sha256']==original and record['bytes']==member.size,'Installed JDK differs from approved distribution')
                files.append(record)
    actual={str(p.relative_to(JDK)) for p in JDK.rglob('*') if p.is_file() or p.is_symlink()}
    require(actual==expected,'Unexpected or missing JDK tree member')
    canonical={r['path'] for r in files}
    require(all(row['resolved_path'] in canonical for row in links),'Unpinned JDK legal target')
    return files,links,{'officialArchive':pin(JDK_ARCHIVE),'canonicalFiles':len(files),'legalAliases':len(links),'completeArchiveEquivalenceVerified':True,'jvmStarted':False}

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True);args=p.parse_args()
    out=args.output
    require(out.is_absolute() and out.resolve()==out and not out.exists(),'Fresh canonical output directory required')
    assembly=load(ASSEMBLY/'assembly-result.json',ASSEMBLY_SHA)
    verified=load(ASSEMBLY/'input-verification.json',VERIFICATION_SHA)
    source=load(PROBE_SOURCE/'source-manifest.json',SOURCE_SHA)
    build=load(PROBE_BUILD,PROBE_BUILD_SHA)
    common=[pin(PROBE_SOURCE/'source-manifest.json'),pin(PROBE_BUILD),pin(Path(build['artifact_path'])),
            pin(ASSEMBLY/'assembly-result.json'),pin(ASSEMBLY/'input-verification.json')]
    require(common[2]['sha256']==build['artifact_sha256'] and common[2]['bytes']==build['artifact_bytes'],'Built own probe differs')
    for row in source['files']:
        current=pin(PROBE_SOURCE/row['path'])
        require(current['sha256']==row['sha256'] and current['bytes']==row['bytes'],'Own probe source/resource differs')
        common.append(current)
    files,links,jdk_result=jdk_closure();common+=files
    # Asset bytes were rehashed by the pinned final assembly receipt; the final
    # supervisor verifies every byte again immediately before execution.
    common+=verified['assetPins']
    out.mkdir();save(out/'jdk-archive-equivalence.json',jdk_result)
    common.append(pin(out/'jdk-archive-equivalence.json'))
    result={'schema':1,'status':'INPUT_BASES_SEALED_NEEDS_ACTUAL_GRAPHICS','sourceAssembly':pin(ASSEMBLY/'assembly-result.json'),
            'jdk':jdk_result,'groups':{},'gameLaunched':False,'jvmStarted':False,
            'remaining':['Actual reviewed graphics-ready receipt and process identity','Final supervisor source pin and graphics merge','Fresh unchanged aggregate memory gate']}
    for target,group in assembly['groups'].items():
        inputs={r['path']:r for r in common};trees={str(JDK),str(API/'run/client-dev/assets')};roles={};producers=[str(ASSEMBLY/'assembly-result.json'),str(ASSEMBLY/'input-verification.json')]
        for side,record in group['roles'].items():
            role=load(Path(record['path']),record['sha256']);cwd=Path(role['cwd']);seal=pin(Path(record['path']));inputs[seal['path']]=seal;producers.append(seal['path'])
            for row in role['files']:
                # This mutable display preferences file retains its exact
                # initial bytes in the source role seal; it is not code input.
                if row['path']==str(cwd/'options.txt'):continue
                current=pin(Path(row['path']));require(current==row,'Changed prepared role input');inputs[row['path']]=row
            for folder in ('mods','config','defaultconfigs'):
                trees.add(str(cwd/folder))
            for folder in ('installation','libraries'):
                if (cwd/folder).exists():trees.add(str(cwd/folder))
            env={'JAVA_HOME':str(JDK),'PATH':str(JDK/'bin')+':/usr/bin:/bin','LANG':'C.UTF-8','TZ':'UTC',
                 'LIBGL_ALWAYS_SOFTWARE':'true','GALLIUM_DRIVER':'llvmpipe'}
            for name,child in [('HOME','.launch-home'),('XDG_CACHE_HOME','.launch-cache'),('XDG_CONFIG_HOME','.launch-config'),('XDG_DATA_HOME','.launch-data'),('TMPDIR','.launch-tmp')]:env[name]=str(cwd/child)
            roles[side]={'cwd':str(cwd),'command':role['command'],'environment':env,'original_mods':role['original_mods'],'managed_mods':role['managed_mods']}
        require(all(str(Path(row['path']).resolve())==row['path'] for row in inputs.values()),'Noncanonical input inventory')
        prepared={'schema':'prepared-network-ci-pair-v2','status':'NEEDS_ACTUAL_GRAPHICS_NOT_EXECUTABLE',
                  'target':target,'port':group['port'],'inputs':sorted(inputs.values(),key=lambda r:r['path']),
                  'immutable_trees':sorted(trees),'preparation_roots':[str(ROOT)],'jdk_legal_links':links,
                  'probe_path':build['artifact_path'],'probe_source_manifest':str(PROBE_SOURCE/'source-manifest.json'),
                  'probe_build_receipt':str(PROBE_BUILD),'source_receipts':producers,
                  'server':roles['server'],'client':roles['client'],'pair_lock':str(out/'serial-pair.lock'),
                  'authorization':{'offline_identity_reference':'Isolated localhost tests with virtual APILocal identity','eula_reference':'Existing Minecraft EULA acceptance for isolated local tests'},
                  'mutable_client_options_initially_pinned_in_role_receipt':True}
        result['groups'][target]={'inputBase':save(out/(target+'-input-base.json'),prepared),'inputCount':len(inputs),'jdkAliases':len(links)}
    save(out/'preparation-result.json',result)
    print(json.dumps({'result':pin(out/'preparation-result.json'),'groups':result['groups'],'jdk':jdk_result,'gameLaunched':False},indent=2))

if __name__=='__main__':main()
