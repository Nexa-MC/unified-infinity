"""Exact two-own-mod build. No network, stubs, original-fixture edits or game launch.

A reviewed bundle digest is the trust anchor; validation is integrity checking,
not a claim that a JSON file alone authenticates execution.
"""
from pathlib import Path
import argparse, hashlib, importlib.util, json, os, shutil, struct, subprocess, sys, time, tomllib, zipfile

ROLES = ('forge_probe', 'native_driver')
PARTS = {'forge_probe': 'forge', 'native_driver': 'driver'}
PACKAGES = {'forge_probe': 'dev/infinity/forgeplayprobe/', 'native_driver': 'dev/infinity/forgeplaydriver/'}
ENTRYPOINTS = {'forge_probe': 'dev/infinity/forgeplayprobe/ForgePlayMod.class', 'native_driver': 'dev/infinity/forgeplaydriver/ForgePlayDriver.class'}
METADATA = {'forge_probe': 'META-INF/mods.toml', 'native_driver': 'META-INF/neoforge.mods.toml'}
MODIDS = {'forge_probe': 'unified_forge_play', 'native_driver': 'forge_play_driver'}
SOURCE_LOCK_SHA = '68e2f0a132da33e4e2c02db404e798f162fb1324d767c86ecede38e907188b66'
MISSING = {
 'javafmllanguage-1.21.1-52.1.0.jar': (19235, 'd27e1f3149ea08fc0a80779fe24fa8585692c5042a34bad153e55662486acc15'),
 'fmlcore-1.21.1-52.1.0.jar': (122624, 'be4d001363625d8dccaefaf9bdedc1509e03c3ba452e3319f9d99dc75fa3c93a'),
 'eventbus-6.2.27.jar': (58819, 'd2a7bcecb80b33f90854a003dc295960263d78435d9d6016c427d711510cb999'),
}
FLAGS = ['-J-Xms16m','-J-Xmx256m','-J-XX:MaxMetaspaceSize=128m','-J-XX:ActiveProcessorCount=1','-J-XX:+UseSerialGC','--release','21','-proc:none','-encoding','UTF-8']


def require(ok, message):
    if not ok: raise ValueError(message)


def sha(path): return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def regular(path):
    p = Path(path)
    require(p.is_absolute() and '..' not in p.parts, 'Absolute canonical path required')
    require(not any(q.is_symlink() for q in [p, *p.parents]), 'Redirected path refused')
    require(p.is_file(), 'Missing regular file: ' + str(p))
    return p


def pin(path):
    p = regular(Path(path).absolute())
    return {'path': str(p), 'bytes': p.stat().st_size, 'sha256': sha(p)}


def checked(row):
    require(type(row) is dict and set(row) == {'path','bytes','sha256'}, 'Exact pin required')
    p = regular(row['path'])
    require(pin(p) == row, 'Input changed: ' + str(p))
    return p


def load(path, limit=4*1024*1024):
    p = regular(path); require(p.stat().st_size <= limit, 'JSON bound')
    def pairs(rows):
        d = {}
        for k,v in rows:
            require(k not in d, 'Duplicate JSON key'); d[k] = v
        return d
    return json.loads(p.read_text(), object_pairs_hook=pairs)


def save(path, data):
    with Path(path).open('x') as f: json.dump(data, f, indent=2); f.write('\n')


def source_inventory(source):
    source=Path(source); rows=[]
    for p in sorted(source.rglob('*')):
        require(not p.is_symlink(), 'Redirected source')
        if p.is_file():
            r=pin(p);r['path']=p.relative_to(source).as_posix();rows.append(r)
    return rows


def source_pins(manifest_pin):
    m=checked(manifest_pin);d=load(m)
    require(set(d)=={'schema','files'} and d['schema']=='forge-play-sources-v1','Source schema')
    root=m.parent/'sources';actual=source_inventory(root)
    require(actual==d['files'],'Complete source inventory changed')
    expected={
      'forge/src/dev/infinity/forgeplayprobe/ForgePlayMod.java',
      'forge/src/dev/infinity/forgeplayprobe/PlayProbe.java',
      'forge/resources/META-INF/mods.toml',
      'driver/src/dev/infinity/forgeplaydriver/ForgePlayDriver.java',
      'driver/src/dev/infinity/forgeplaydriver/ForgePlayClient.java',
      'driver/resources/META-INF/neoforge.mods.toml','LICENSE-Network-Control-Probe-MIT.txt'}
    require({r['path'] for r in actual}==expected,'Unexpected source inventory')
    return root,[manifest_pin,*[pin(root/r['path']) for r in actual]]


def class_inventory(root, role):
    result=[];root=Path(root)
    for p in sorted(root.rglob('*')):
        require(not p.is_symlink(),'Redirected compiler output')
        if p.is_file():
            name=p.relative_to(root).as_posix()
            require(name.startswith(PACKAGES[role]) and name.endswith('.class'), 'Foreign compiled payload')
            raw=p.read_bytes();require(len(raw)>=10 and raw[:4]==b'\xca\xfe\xba\xbe' and struct.unpack('>H',raw[6:8])[0]==65,'Expected Java21 class')
            row=pin(p);row['entry']=name;result.append(row)
    names={r['entry'] for r in result}
    require(ENTRYPOINTS[role] in names,'Complete authentic entrypoint not compiled')
    if role=='forge_probe':
        raw=(root/ENTRYPOINTS[role]).read_bytes()
        require(b'Lnet/minecraftforge/fml/common/Mod;' in raw,'Original Forge @Mod annotation absent')
    else:
        require(b'Lnet/neoforged/fml/common/Mod;' in (root/ENTRYPOINTS[role]).read_bytes(),'Native driver annotation absent')
    return result


def expected_entries(source_root, classes, role):
    entries={r['entry']: checked({k:r[k] for k in ('path','bytes','sha256')}).read_bytes() for r in classes}
    resource=source_root/PARTS[role]/'resources'/METADATA[role]
    data=tomllib.loads(resource.read_text()); require(data['mods'][0]['modId']==MODIDS[role],'Wrong mod ID')
    require(len(data['mods'])==1 and data['modLoader']=='javafml','Wrong mod metadata')
    if role=='forge_probe':
        require(data['loaderVersion']=='[52,53)','Wrong Forge loader range')
    else:
        deps=data['dependencies']['forge_play_driver']
        require(any(x['modId']=='unified_forge_play' and x['type']=='required' and x['ordering']=='AFTER' and x['versionRange']=='[0.1.0]' for x in deps),'Missing original consumer dependency')
    entries[METADATA[role]]=resource.read_bytes()
    entries['META-INF/LICENSE-Network-Control-Probe-MIT.txt']=(source_root/'LICENSE-Network-Control-Probe-MIT.txt').read_bytes()
    return entries


def package(source_root, classes_root, role, destination):
    """Only already-compiled own classes/resources; no dependency JAR contents."""
    classes=class_inventory(classes_root,role);entries=expected_entries(source_root,classes,role)
    with zipfile.ZipFile(destination,'x',compression=zipfile.ZIP_STORED) as z:
        for name,raw in sorted(entries.items()):
            info=zipfile.ZipInfo(name,(1980,1,1,0,0,0));info.compress_type=zipfile.ZIP_STORED
            info.create_system=3;info.external_attr=0o100644<<16;z.writestr(info,raw)
    verify_archive(destination,role,source_root,classes)
    return classes


def verify_archive(path,role,source_root,classes):
    expected=expected_entries(source_root,classes,role)
    with zipfile.ZipFile(regular(path)) as z:
        names=z.namelist();require(len(names)==len(set(names)) and set(names)==set(expected),'Wrong JAR inventory')
        for row in z.infolist():
            require(row.date_time==(1980,1,1,0,0,0) and row.compress_type==zipfile.ZIP_STORED,'Non-deterministic JAR entry')
            require(row.create_system==3 and row.external_attr==0o100644<<16 and not row.extra and not row.comment,'Unexpected JAR metadata')
            require(z.read(row)==expected[row.filename],'Compiled/source JAR bytes differ')


def compiler_log_runtime_pins(row):
    """Only a checked empty compiler log is receipt evidence, not runtime input.

    Preserve its real zero bytes/hash; never pad the log or loosen file_pin.
    """
    checked(row)
    return [] if row['bytes'] == 0 else [row]


def validate_compile(config_pin, receipt_pin):
    config=load(checked(config_pin));receipt=load(checked(receipt_pin));allpins=[config_pin,receipt_pin]
    require(receipt['schema']=='forge-play-compile-v1' and receipt['status']=='COMPILED' and receipt['complete_entrypoint'] is True,'Partial compile cannot qualify')
    require(receipt['config']==config_pin and receipt['source_manifest']==config['source_manifest'],'Compile/config/source mismatch')
    source,srcpins=source_pins(config['source_manifest']);allpins+=srcpins
    allpins+=validate_config(config)
    require(set(receipt['classes'])==set(ROLES) and len(receipt['steps'])==2,'Two compile steps required')
    for role,step in zip(ROLES,receipt['steps']):
        require(step['role']==role and step['exit_code']==0 and step['cleanup'].get('qualified') is True and step['cleanup'].get('reason')=='EXACT_LIVE_OWNER_JOURNAL','Unqualified compiler completion')
        journal=load(checked(step['owner']));allpins.append(step['owner']);allpins+=compiler_log_runtime_pins(step['log'])
        require(step['cleanup']['observedSha256']==step['owner']['sha256'] and step['cleanup']['observedBytes']==step['owner']['bytes'],'Live-owner receipt binding changed')
        require(step['cleanup']['ownerIdentity']=={k:journal[k] for k in ('runId','ownerPid','childPid','ownedProcessGroup','ownedSession')},'Live-owner identity changed')
        require(journal['status']=='CHILD_EXITED' and journal['childSpawned'] is True and not journal.get('stopRequested',False) and journal['terminal'] is True and journal['commandSucceeded'] is True and journal['cleanupQualified'] is True and journal['childReturnCode']==0 and journal['remainingOwnedMembers']==[],'Compiler owner incomplete')
        require(step['log']['path']==str(Path(receipt['output_root'])/(role+'.log')) and step['owner']['path']==str(Path(receipt['output_root'])/(role+'-owner.json')),'Exact compiler evidence locations required')
        cmd=compile_command(config,source,role,Path(receipt['output_root']))
        require(step['command']==cmd and journal['command']==cmd and journal['timeoutSeconds']<=60,'Compiler dispatch mismatch')
        root=Path(receipt['output_root'])/'classes'/role
        require(receipt['classes'][role]==class_inventory(root,role),'Compiled class inventory changed')
        for r in receipt['classes'][role]:allpins.append({k:r[k] for k in ('path','bytes','sha256')})
    return source,receipt,allpins


def validate_bundle(bundle_path, expected_sha256):
    bpin=pin(bundle_path);require(bpin['sha256']==expected_sha256,'Reviewed Forge bundle digest mismatch')
    doc=load(bundle_path)
    require(set(doc)=={'schema','status','diagnostic_only','baseline_acceptance','source_manifest','compile_receipt','config','artifacts'},'Forge bundle keys')
    require(doc['schema']=='forge-play-artifacts-v1' and doc['status']=='BUILT' and doc['diagnostic_only'] is True and doc['baseline_acceptance'] is False,'Forge bundle status')
    require(set(doc['artifacts'])==set(ROLES),'Both original Forge consumer and native driver required')
    source,receipt,inputs=validate_compile(doc['config'],doc['compile_receipt'])
    require(doc['source_manifest']==receipt['source_manifest'],'Bundle source mismatch')
    paths=set()
    for role in ROLES:
        p=checked(doc['artifacts'][role]);require(p not in paths and p.suffix=='.jar','Distinct JAR outputs required');paths.add(p)
        verify_archive(p,role,source,receipt['classes'][role]);inputs.append(doc['artifacts'][role])
    inputs.append(bpin);unique={}
    for row in inputs:
        require(row['path'] not in unique or unique[row['path']]==row,'Conflicting input pin');unique[row['path']]=row
    return {'bundle':doc,'input_pins':list(unique.values())}


def validate_producer_closure(config, producer):
    closure=config['producer_closure'];rows=[]
    require(set(closure)=={'owner','log','source_materialization','toolchain_receipt','outputs','source_files'},'Producer closure fields')
    for name, digest in [('owner',producer['liveOwnerValidation']['observedSha256']),('log',producer['logSha256']),('source_materialization',producer['sourceMaterializationSha256']),('toolchain_receipt',producer['toolchainReceiptSha256'])]:
        row=closure[name];checked(row);require(row['sha256']==digest,'Producer evidence binding changed');rows.append(row)
    journal=load(closure['owner']['path'])
    require(journal['terminal'] is True and journal['commandSucceeded'] is True and journal['cleanupQualified'] is True and journal['remainingOwnedMembers']==[] and journal['childReturnCode']==0,'Producer cleanup changed')
    require(journal['command']==producer['command'],'Producer command binding changed')
    require(len(closure['outputs'])==len(producer['outputs']),'Producer output inventory')
    producer_root=Path(config['producer_receipt']['path']).parent.parent
    for row,old in zip(closure['outputs'],producer['outputs']):
        require(old['exists'] is True and row=={'path':str(producer_root/old['path']),'bytes':old['bytes'],'sha256':old['sha256']},'Producer output binding')
        checked(row);rows.append(row)
    sources=load(closure['source_materialization']['path'])['sourceFilesCopiedWithExactHashes']
    require(len(closure['source_files'])==len(sources),'Producer source inventory')
    for row,old in zip(closure['source_files'],sources):
        require(row['path']==str(producer_root/old['path']) and row['sha256']==old['sha256'],'Producer source binding')
        checked(row);rows.append(row)
    return rows


def validate_config(config):
    require(config['schema']=='forge-play-build-config-v1','Build config schema')
    inputs=[]
    for row in config['provenance']:
        checked(row);inputs.append(row)
    lock=next((r for r in config['provenance'] if r['sha256']==SOURCE_LOCK_SHA),None)
    require(lock is not None,'Original Forge source lock absent')
    require(set(config['classpath'])==set(ROLES),'Exact classpath roles')
    allforge={Path(r['path']).name:r for r in config['classpath']['forge_probe']}
    for name,(size,digest) in MISSING.items():
        require(name in allforge and allforge[name]['bytes']==size and allforge[name]['sha256']==digest,'Original Forge FML pin missing')
    for role in ROLES:
        require(len({r['path'] for r in config['classpath'][role]})==len(config['classpath'][role]),'Duplicate classpath')
        for row in config['classpath'][role]:checked(row);inputs.append(row)
    for row in config['jdk_files']:checked(row);inputs.append(row)
    require(config['javac'] in [r['path'] for r in config['jdk_files']],'Pinned javac missing')
    require(any(Path(r['path']).name=='modules' for r in config['jdk_files']),'Complete JDK modules required')
    producer=load(checked(config['producer_receipt']));inputs.append(config['producer_receipt'])
    require(producer['successfulCompilePostconditions'] is True and producer['exitCode']==0,'Real game compile producer missing')
    require(producer['liveOwnerValidation']['qualified'] is True,'Game compile owner unqualified')
    inputs+=validate_producer_closure(config,producer)
    generated=checked(config['generated_native_jar']);inputs.append(config['generated_native_jar'])
    require(any(r==config['generated_native_jar'] for r in config['classpath']['native_driver']),'Generated type absent')
    require(generated.name=='neoforge-21.1.219.jar' and sha(generated)=='6faad7d182a47d66ce28db569e9f4f475d9bf7bc4db452b9f3010b74c050008c','Unexpected generated type producer')
    for row in config['owner_support']:checked(row);inputs.append(row)
    return inputs


def compile_command(config,source,role,output):
    cp=[r['path'] for r in config['classpath'][role]]
    if role=='native_driver':cp.insert(0,str(output/'classes'/'forge_probe'))
    sources=sorted((source/PARTS[role]/'src').rglob('*.java'))
    return [config['javac'],*FLAGS,'-cp',':'.join(cp),'-d',str(output/'classes'/role),*map(str,sources)]


def build(config_path, expected_sha256, output, deadline_epoch):
    config_pin=pin(config_path);require(config_pin['sha256']==expected_sha256,'Build config digest mismatch')
    config=load(config_path);source,_=source_pins(config['source_manifest']);validate_config(config)
    output=Path(output).absolute();require(not output.exists(),'Fresh output directory required')
    require(time.time()+2<deadline_epoch<=time.time()+180,'Bounded build deadline required')
    # Import only the exact pinned owner closure, not an ambient module of that name.
    support=Path(config['owner_support'][0]['path']).parent
    sys.path.insert(0,str(support))
    import owned_compile_process_v3 as owner
    require(pin(Path(owner.__file__)) in config['owner_support'],'Unpinned imported owner')
    output.mkdir();(output/'classes').mkdir();steps=[];classrows={}
    for role in ROLES:
        (output/'classes'/role).mkdir();cmd=compile_command(config,source,role,output)
        log=output/(role+'.log');journal=output/(role+'-owner.json')
        timeout=min(60,deadline_epoch-time.time()-25);require(timeout>0,'Build deadline expired')
        env={'PATH':str(Path(config['javac']).parent)+':/usr/bin:/bin','LANG':'C.UTF-8','LC_ALL':'C.UTF-8','HOME':str(output)}
        with log.open('x') as stream:
            result=owner.run(cmd,cwd=output,env=env,stdout=stream,stderr=subprocess.STDOUT,timeout=timeout,cancel_file=output/'cancel',owner_receipt=journal)
        completion=owner.validate_completion(journal,result,cmd)
        step={'role':role,'command':cmd,'exit_code':result.returncode,'cleanup':completion,'owner':pin(journal),'log':pin(log)}
        steps.append(step)
        if result.returncode or not completion['qualified']:
            save(output/'failed-build.json',{'status':'FAILED','steps':steps,'gameLaunched':False})
            raise ValueError('Real compiler failed or cleanup unqualified: '+role)
        classrows[role]=class_inventory(output/'classes'/role,role)
    source_pins(config['source_manifest']);validate_config(config)
    receipt={'schema':'forge-play-compile-v1','status':'COMPILED','complete_entrypoint':True,'config':config_pin,'source_manifest':config['source_manifest'],'output_root':str(output),'steps':steps,'classes':classrows}
    receipt_path=output/'compile-receipt.json';save(receipt_path,receipt)
    artifacts={}
    for role in ROLES:
        destination=output/(MODIDS[role]+'-0.1.0.jar');package(source,output/'classes'/role,role,destination);artifacts[role]=pin(destination)
    bundle={'schema':'forge-play-artifacts-v1','status':'BUILT','diagnostic_only':True,'baseline_acceptance':False,'source_manifest':config['source_manifest'],'compile_receipt':pin(receipt_path),'config':config_pin,'artifacts':artifacts}
    path=output/'bundle.json';save(path,bundle);validate_bundle(path,sha(path));return pin(path)


def main():
    p=argparse.ArgumentParser();p.add_argument('--config',type=Path,required=True);p.add_argument('--sha256',required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--deadline-epoch',type=float,required=True)
    a=p.parse_args();print(json.dumps(build(a.config,a.sha256,a.output,a.deadline_epoch),indent=2))

if __name__=='__main__':main()
