#!/usr/bin/env python3
"""Copy only manifest-verified immutable client inputs; no shared input writes."""
import hashlib, json, pathlib, shutil
ROOT = pathlib.Path(__file__).resolve().parents[2]
PROFILE = ROOT / 'run/quilt-native-client'
CACHE = PROFILE / 'gradle-cache/caches/quilt-loom'
MC = CACHE / '1.21.1'
MC.mkdir(parents=True, exist_ok=True)

def sha(path, algorithm='sha256'):
    h = hashlib.new(algorithm)
    with path.open('rb') as f:
        for b in iter(lambda: f.read(1024 * 1024), b''): h.update(b)
    return h.hexdigest()

def copy_verified(src, dest, digest, algorithm='sha1'):
    if sha(src, algorithm) != digest:
        raise RuntimeError(f'Source checksum mismatch: {src}')
    dest.parent.mkdir(parents=True, exist_ok=True)
    if not dest.exists(): shutil.copy2(src, dest)
    if sha(dest, algorithm) != digest:
        raise RuntimeError(f'Destination checksum mismatch: {dest}')

manifest = ROOT / 'run/client-dev/versions/1.21.1/1.21.1.json'
if sha(manifest,'sha1') != '22a1966494dfa4eeb5ee778c8e6ed5b774839582':
    raise RuntimeError('Minecraft manifest differs from the verified first-party baseline')
copy_verified(manifest, MC/'mojang_minecraft_info.json','22a1966494dfa4eeb5ee778c8e6ed5b774839582')
data = json.loads(manifest.read_text())
assert data['id'] == '1.21.1'
copies = []
for kind, src in [('client', ROOT/'run/client-dev/versions/1.21.1/1.21.1.jar'), ('server', ROOT/'run/client-dev/gradle-cache/caches/neoformruntime/artifacts/minecraft_1.21.1_server.jar')]:
    target = MC / f'minecraft-{kind}.jar'
    copy_verified(src, target, data['downloads'][kind]['sha1'])
    copies.append({'source': str(src.relative_to(ROOT)), 'path': str(target.relative_to(ROOT)), 'sha1': data['downloads'][kind]['sha1'], 'sha256': sha(target), 'url': data['downloads'][kind]['url']})

index = ROOT / f"run/client-dev/assets/indexes/{data['assetIndex']['id']}.json"
copy_verified(index, CACHE/f"assets/indexes/1.21.1-{data['assetIndex']['id']}.json", data['assetIndex']['sha1'])
objects = {v['hash'] for v in json.loads(index.read_text())['objects'].values()}
for h in sorted(objects):
    p = pathlib.Path('objects') / h[:2] / h
    copy_verified(ROOT/'run/client-dev/assets'/p, CACHE/'assets'/p, h)

mods = [
    ('docs/four-loader/quilt/candidates/optab-2.0.0V1.21.1+1.21.jar','6121446645d4521ddb5deae40e506fb02a7d4f06c0ce049fabc6ecaed548c296'),
    ('docs/four-loader/quilt/upstream/qsl_base-alpha5.jar','7eb4ec613f901ef7232f9f84ee91be5576f00682f32ad9c9f7b1a679bcf82465'),
    ('docs/four-loader/quilt/upstream/lifecycle_events-alpha5.jar','1a1f9b72c38e2475b471df1dcff7992d6ae4955e8a2cd8288bb3ba3986768aa4'),
]
fabric = ROOT/'docs/research/upstream/fabric-api-0.116.7+1.21.1.jar'
# Independently matched to the official Fabric Maven SHA256 sidecar.
mods.append((str(fabric.relative_to(ROOT)), '08018cc48c97415a38016a00dbd5a2c7a460ba6b7a051690a8cb3dbb5e8482a4'))
mod_records=[]
for path,h in mods:
    src=ROOT/path; dest=PROFILE/'game/mods'/src.name
    copy_verified(src,dest,h,'sha256')
    mod_records.append({'source':path,'path':str(dest.relative_to(ROOT)),'sha256':h})

report={'minecraft':'1.21.1','gameInputs':copies,'assetIndex':data['assetIndex'],'assetObjects':len(objects),'mods':mod_records,'sharedInputsReadOnly':True,'gameLaunched':False}
(PROFILE/'seed-report.json').write_text(json.dumps(report,indent=2)+'\n')
print(f'Verified/copy-seeded {len(copies)} game JARs, {len(objects)} assets, and {len(mod_records)} exact mod inputs. No game launch.')
