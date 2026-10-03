#!/usr/bin/env python3
"""Fail-closed byte validation of the isolated native client control."""
import argparse, hashlib, json, pathlib, zipfile
ROOT = pathlib.Path(__file__).resolve().parents[2]
PROFILE = ROOT / 'run/quilt-native-client'
LOADER_SHA = 'a561a9fe9abb45556c696095a29e81477618bf2408b86c36db5aecdcd6a86fdb'
PINNED_MODS = {
    'optab-2.0.0V1.21.1+1.21.jar': '6121446645d4521ddb5deae40e506fb02a7d4f06c0ce049fabc6ecaed548c296',
    'qsl_base-alpha5.jar': '7eb4ec613f901ef7232f9f84ee91be5576f00682f32ad9c9f7b1a679bcf82465',
    'lifecycle_events-alpha5.jar': '1a1f9b72c38e2475b471df1dcff7992d6ae4955e8a2cd8288bb3ba3986768aa4',
    'fabric-api-0.116.7+1.21.1.jar': '08018cc48c97415a38016a00dbd5a2c7a460ba6b7a051690a8cb3dbb5e8482a4',
}

def digest(path):
    h = hashlib.sha256()
    with path.open('rb') as f:
        for b in iter(lambda: f.read(1048576), b''): h.update(b)
    return h.hexdigest()

def checked(path, expected):
    if not path.is_file() or digest(path) != expected:
        raise RuntimeError(f'Frozen input absent or changed: {path}')

def verify_mods():
    seed = json.loads((PROFILE/'seed-report.json').read_text())
    named = seed.get('profileMode')=='loom_named_classpath'
    mod_root = PROFILE/'original-mods' if named else PROFILE/'game/mods'
    if named and list((PROFILE/'game/mods').glob('*.jar')):raise RuntimeError('Original and named mod inputs would load together')
    actual = sorted(p.name for p in mod_root.glob('*.jar'))
    expected = sorted(pathlib.Path(m['path']).name for m in seed['mods'])
    if actual != expected or actual != sorted(PINNED_MODS): raise RuntimeError(f'Unexpected mod set: {actual}')
    for m in seed['mods']:
        name=pathlib.Path(m['path']).name
        if m['sha256'] != PINNED_MODS[name]: raise RuntimeError(f'Mod lock digest changed: {name}')
        if (ROOT/m['path']).resolve() != (mod_root/name).resolve(): raise RuntimeError('Mod path outside isolated profile')
        checked(ROOT/m['path'], m['sha256'])
        checked(ROOT/m['source'], m['sha256'])
    if named:
        originals=json.loads((ROOT/'four-loader/quilt-native-client/provenance/mod-closure.json').read_text())
        if sorted(r['sha256'] for r in seed['loomInputClosure'])!=sorted(r['sha256'] for r in originals):raise RuntimeError('Loom source closure changed')
        for r in seed['loomInputClosure']:checked(ROOT/r['path'],r['sha256'])
    return seed['mods']

def metadata(path):
    with zipfile.ZipFile(path) as z:
        if 'quilt.mod.json' in z.namelist():
            raw=json.loads(z.read('quilt.mod.json'));m=raw['quilt_loader'];return {'id':m['id'],'version':m['version'],'format':'quilt','nested':m.get('jars',[])}
        if 'fabric.mod.json' in z.namelist():
            m=json.loads(z.read('fabric.mod.json'));return {'id':m['id'],'version':m['version'],'format':'fabric','nested':m.get('jars',[])}
    return None

def verify_runtime():
    manifest=json.loads((PROFILE/'client-launch-inputs.json').read_text())
    seed=json.loads((PROFILE/'seed-report.json').read_text())
    for original in seed['gameInputs']:
        checked(ROOT/original['source'],original['sha256'])
        checked(ROOT/original['path'],original['sha256'])
    if manifest['mainClass'] != 'net.fabricmc.devlaunchinjector.Main':
        raise RuntimeError('Unexpected developer launch main class')
    jars=[p for p in manifest['classpath'] if p['sha256']]
    for entry in jars: checked(pathlib.Path(entry['path']),entry['sha256'])
    loader=[p for p in jars if pathlib.Path(p['path']).name=='quilt-loader-0.30.1.jar']
    if len(loader)!=1 or loader[0]['sha256']!=LOADER_SHA:
        raise RuntimeError('Genuine Quilt Loader identity mismatch')
    args=' '.join(manifest['jvmArgs'])
    if '-Dfabric.dli.main=org.quiltmc.loader.impl.launch.knot.KnotClient' not in args:
        raise RuntimeError('Expected genuine Quilt KnotClient target missing')
    if '-Dfabric.dli.env=client' not in args:
        raise RuntimeError('Expected client side missing')
    for forbidden in ('--accessToken','--username','--uuid','--server','--quickPlayMultiplayer'):
        if forbidden in json.dumps(manifest): raise RuntimeError(f'Unexpected auth/server argument: {forbidden}')
    if any('neoforge' in pathlib.Path(p['path']).name.lower() or 'connector' in pathlib.Path(p['path']).name.lower() for p in jars):
        raise RuntimeError('Unified/NeoForge input leaked into genuine Quilt classpath')
    if any(pathlib.Path(p['path']).name.startswith('fabric-loader-') for p in jars):
        raise RuntimeError('An independent Fabric Loader leaked into the Quilt classpath')
    launch=ROOT/'four-loader/quilt-native-client/development/.gradle/quilt-loom-cache/launch.cfg'
    cfg=launch.read_text()
    if 'loader.development=true' not in cfg: raise RuntimeError('Official development mode absent')
    if str(ROOT/'run/client-dev') in cfg: raise RuntimeError('Shared NeoForge resources configured writable')
    result={'classpathJars':len(jars),'genuineQuiltLoaderSha256':LOADER_SHA,'mainClass':manifest['mainClass'],'launchConfigSha256':digest(launch),'gameLaunched':False}
    if seed.get('profileMode')=='loom_named_classpath':
        expected={r['id']:r for r in json.loads((ROOT/'four-loader/quilt-native-client/provenance/mod-closure.json').read_text())}
        derived=[];seen=set()
        for entry in jars:
            path=pathlib.Path(entry['path']);m=metadata(path)
            if not m:continue
            if m['id'] not in expected:
                if m['id']=='quilt_loader' and m['version']=='0.30.1' and entry['sha256']==LOADER_SHA:continue
                if m['id']=='mixinextras' and m['version']=='0.5.4':continue
                raise RuntimeError(f'Unapproved additional mod on runtime classpath: {m}')
            if m['id'] in seen:raise RuntimeError(f'Duplicate runtime mod ID: {m["id"]}')
            seen.add(m['id'])
            if m['version']!=expected[m['id']]['version'] or m['format']!=expected[m['id']]['format']:raise RuntimeError(f'Mod identity changed: {m}')
            if m['nested']:raise RuntimeError('Official Loom has not flattened nested runtime inputs')
            if 'remapped_mods' not in str(path):raise RuntimeError(f'Expected official Loom derived mod: {path}')
            derived.append({**m,'path':str(path),'sha256':entry['sha256'],'originalSha256':expected[m['id']]['sha256']})
        if seen!=set(expected):raise RuntimeError(f'Named runtime closure differs: missing={set(expected)-seen}')
        result['derivedNamedMods']=derived
    return result

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--runtime',action='store_true');args=parser.parse_args()
    result={'mods':verify_mods(),'gameLaunched':False}
    if args.runtime:result.update(verify_runtime())
    print(json.dumps(result,indent=2))

if __name__=='__main__': main()
