#!/usr/bin/env python3
"""Read-only predecessor to successor Popen. It never launches, edits JARs or changes a profile.

The caller must pin the build receipt SHA in its separately reviewed successor seal.
An arbitrary candidate's bytes/metadata, matching digest or claimed ID do not grant trust.
"""
import argparse, hashlib, io, json, os, pathlib, zipfile
PREFIX='org/sinytra/connector/infinity/inventory/'
FML_REQUIRED={'net/neoforged/fml/loading/FMLLoader.class','net/neoforged/fml/loading/FMLServiceProvider.class','net/neoforged/fml/ModLoader.class'}
GAME_CLASSES={'COMPATIBILITY_GAME':'org/sinytra/connector/mod/FmlGameCompatibilityComponent.class','PRODUCT_GAME':'dev/modcompat/runtime/bundle/RuntimeBundle.class'}
OWNED_SERVICES={'cpw.mods.modlauncher.api.ITransformationService','net.neoforged.neoforgespi.locating.IModFileCandidateLocator','net.neoforged.neoforgespi.locating.IModFileReader','net.neoforged.neoforgespi.locating.IDependencyLocator','net.neoforged.neoforgespi.language.IModLanguageLoader','net.neoforged.neoforgespi.coremod.ICoreMod'}
REQUIRED={'AdmissionSession','BootstrapInstallation','AdmissionInventory','InfrastructurePolicy','TrustedPayloads','AdmissionMetadata','AuditedInfrastructureIds','InventoryDisplay','InventoryReconciler'}
def sha(path):
    h=hashlib.sha256()
    with path.open('rb') as stream:
        for part in iter(lambda:stream.read(65536),b''):h.update(part)
    return h.hexdigest()
def digest_strings(values):
    h=hashlib.sha256()
    for value in values:
        raw=value.encode();h.update((str(len(raw))+'\n').encode('ascii'));h.update(raw)
    return h.hexdigest()
def contained(root,relative):
    rel=pathlib.Path(relative)
    if rel.is_absolute() or '..' in rel.parts: raise ValueError('Uncontained installation path')
    path=(root/rel).resolve(strict=True)
    if not path.is_relative_to(root) or not path.is_file():raise ValueError('Installation path escapes permitted root')
    return path
def validate(receipt_path, expected_receipt_sha, java_arguments, actual_environment):
    if sha(receipt_path)!=expected_receipt_sha:raise ValueError('Unreviewed build receipt')
    receipt=json.loads(receipt_path.read_text());owner=pathlib.Path(receipt['artifact']).resolve(strict=True)
    if sha(owner)!=receipt['sha256']:raise ValueError('Source-built BOOT owner changed')
    with zipfile.ZipFile(owner) as archive:
        raw=archive.read('META-INF/unified-admission/installation.json')
        if hashlib.sha256(raw).hexdigest()!=receipt['installationPolicySha256']:raise ValueError('Installation policy differs from build receipt')
        policy=json.loads(raw)
    if policy.get('schema')!=1 or policy.get('approved') is not True:raise ValueError('Source candidate has no approved installation')
    if digest_strings(java_arguments)!=policy['processArgumentsSha256']:raise ValueError('Launch arguments differ from source-sealed installation')
    for key in ('MOD_CLASSES','JAVA_TOOL_OPTIONS','JDK_JAVA_OPTIONS','_JAVA_OPTIONS'):
        if actual_environment.get(key,'')!=policy['environment'][key]:raise ValueError('Launch environment changed: '+key)
    if actual_environment.get('MOD_CLASSES',''):raise ValueError('Grouped development paths unsupported')
    if any(actual_environment.get(key,'').strip() for key in ('JAVA_TOOL_OPTIONS','JDK_JAVA_OPTIONS','_JAVA_OPTIONS')):raise ValueError('Opaque environment JVM options unsupported')
    root=pathlib.Path(policy['installationDirectory']).resolve(strict=True)
    artifacts={}
    for item in policy['artifacts']:
        path=contained(root,item['path'])
        if path in artifacts:raise ValueError('Duplicate installation origin')
        if item['role']=='BOOT_OWNER':
            if path!=owner or item['sha256']!='SELF':raise ValueError('Wrong BOOT owner')
        elif item['role'] not in ('PLATFORM','MANAGED_ROOT','ADMISSION_CONSUMER','COMPATIBILITY_GAME','PRODUCT_GAME') or sha(path)!=item['sha256']:raise ValueError('Invalid pinned artifact')
        if item['role']=='ADMISSION_CONSUMER':
            with zipfile.ZipFile(path) as consumer_jar:
                if 'org/sinytra/connector/infinity/FmlCompatibilityComponent.class' not in consumer_jar.namelist():raise ValueError('Pinned SERVICE component lacks explicit FML entry')
                for service in OWNED_SERVICES:
                    name='META-INF/services/'+service
                    if name in consumer_jar.namelist() and any(line.split('#',1)[0].strip() for line in consumer_jar.read(name).decode().splitlines()):raise ValueError('Autonomous compatibility SPI remains')
                raw=consumer_jar.read('META-INF/unified-admission/consumer-v1.json')
                if len(raw)>8192:raise ValueError('Oversized consumer capability')
                capability=json.loads(raw)
                if capability.get('protocol')!=1 or capability.get('runtimeModelOwner')!='fml_loader' or not {'ConnectorLocator','FabricModsDiscoverer','OrdinaryAdmissionGate','ManagedQuiltModules'} <= set(capability.get('consumers',[])):raise ValueError('Incompatible pinned consumer')
        if item['role'] in GAME_CLASSES:
            with zipfile.ZipFile(path) as game_jar:
                if GAME_CLASSES[item['role']] not in game_jar.namelist() or 'META-INF/neoforge.mods.toml' not in game_jar.namelist():raise ValueError('Installed GAME implementation/capability metadata missing')
        if item['role'] in {'ADMISSION_CONSUMER',*GAME_CLASSES} and path.is_relative_to(pathlib.Path(policy['gameDirectory']).resolve()/'mods'):raise ValueError('Internal components must be outside user mods')
        artifacts[path]=item
    if any(sum(x['role']==role for x in artifacts.values())!=1 for role in ('BOOT_OWNER','ADMISSION_CONSUMER','COMPATIBILITY_GAME','PRODUCT_GAME')):raise ValueError('Exactly one BOOT/SERVICE/GAME/product owner required')
    # Every module/classpath input is already immutable installation policy data. JVM @files are sealed independently.
    for property_name in ('java.class.path','jdk.module.path','legacyClassPath'):
        value=policy['properties'][property_name]
        for item in value.split(os.pathsep) if value else []:
            if not item or '*' in item:raise ValueError('Empty/wildcard launch root unsupported')
            path=pathlib.Path(item).resolve(strict=True)
            if path not in artifacts:raise ValueError('Unpinned JVM input')
            if artifacts[path]['role'] in {'ADMISSION_CONSUMER',*GAME_CLASSES}:raise ValueError('Internal layer component also placed on raw JVM/legacy classpath')
    files={}
    for item in policy['argumentFiles']:
        path=pathlib.Path(item['path']).resolve(strict=True)
        if sha(path)!=item['sha256']:raise ValueError('Java argument file changed')
        if path.stat().st_size>1024*1024:raise ValueError('Oversized Java argument file')
        contents=path.read_text()
        if any(word in contents for word in ('--fml.mods','--fml.modLists','-javaagent','-agentlib','-agentpath','--patch-module')):raise ValueError('Unsupported code/discovery input in Java argument file')
        files[path]=item
    legacy_file=policy['properties'].get('legacyClassPath.file','')
    if legacy_file and pathlib.Path(legacy_file).resolve(strict=True) not in files:raise ValueError('Unpinned legacy classpath descriptor file')
    for item in java_arguments:
        if item.startswith(('-javaagent','-agentlib','-agentpath','--patch-module')):raise ValueError('Unsupported pre-BOOT code injection')
        if item.startswith('@') and not item.startswith('@@') and pathlib.Path(item[1:]).resolve(strict=True) not in files:raise ValueError('Unpinned Java argument file')
        if item.split('=',1)[0] in ('--fml.mods','--fml.modLists'):raise ValueError('Additive mod inputs unsupported')
    total_nested_bytes=0
    for pin in policy['embedded']:
        root_path=contained(root,pin['root'])
        if root_path not in artifacts or not pin['entries'] or len(pin['entries'])>8:raise ValueError('Unknown managed embedded origin')
        data=None
        for index,name in enumerate(pin['entries']):
            if name.startswith('/') or '\\' in name or '..' in pathlib.PurePosixPath(name).parts:raise ValueError('Invalid embedded entry chain')
            with zipfile.ZipFile(root_path if index==0 else io.BytesIO(data)) as nested:
                entry=nested.getinfo(name)
                if entry.file_size>32*1024*1024:raise ValueError('Managed child exceeds source bound')
                with nested.open(entry) as stream:data=stream.read(32*1024*1024+1)
                total_nested_bytes+=len(data)
                if len(data)>32*1024*1024 or total_nested_bytes>256*1024*1024:raise ValueError('Managed embedded byte bound exceeded')
        if hashlib.sha256(data).hexdigest()!=pin['sha256']:raise ValueError('Managed nested provenance pin differs')
    class_owners={name:[] for name in REQUIRED}
    fml_owners={name:[] for name in FML_REQUIRED}
    for path in artifacts:
        with zipfile.ZipFile(path) as archive:
            names=archive.namelist()
            found={name for name in names if name.startswith(PREFIX) and name.endswith('.class')}
            if found and path!=owner:raise ValueError('Split BOOT admission package: '+str(path))
            for name in FML_REQUIRED:
                if name in names:fml_owners[name].append(path)
            for name in REQUIRED:
                if PREFIX+name+'.class' in found:class_owners[name].append(path)
    if any(paths!=[owner] for paths in class_owners.values()) or any(paths!=[owner] for paths in fml_owners.values()):raise ValueError('Missing/duplicate FML/admission class owner')
    # This result is a launch validation receipt, not authorization to start or an admission metadata scan.
    return {'status':'validated-before-jvm','artifactSha256':receipt['sha256'],'installationPolicySha256':receipt['installationPolicySha256'],'argumentsSha256':policy['processArgumentsSha256'],'classOwnerCount':1,'gameLaunched':False}
def main():
    p=argparse.ArgumentParser();p.add_argument('--receipt',type=pathlib.Path,required=True);p.add_argument('--expected-receipt-sha256',required=True);p.add_argument('--java-arguments-json',type=pathlib.Path,required=True)
    a=p.parse_args();print(json.dumps(validate(a.receipt,a.expected_receipt_sha256,json.loads(a.java_arguments_json.read_text()),dict(os.environ)),sort_keys=True))
if __name__=='__main__':main()
