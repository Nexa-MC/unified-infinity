#!/usr/bin/env python3
"""Prepare first-party Linux client resources; never launch or authenticate."""
import argparse, concurrent.futures, hashlib, json, os, pathlib, platform, re, shutil, subprocess, zipfile
ROOT = pathlib.Path(__file__).resolve().parents[2]
CLIENT = ROOT / 'run/client-dev'
LIBS = CLIENT / 'libraries'

def digest(path):
    h = hashlib.sha1()
    with path.open('rb') as f:
        for block in iter(lambda: f.read(1048576), b''): h.update(block)
    return h.hexdigest()

def matches(a, path):
    return path.is_file() and (not a.get('size') or path.stat().st_size == a['size']) and (not a.get('sha1') or digest(path) == a['sha1'])

def fetch(item):
    a, dest = item
    if matches(a, dest): return 'present'
    dest.parent.mkdir(parents=True, exist_ok=True)
    if a.get('path'):
        src = ROOT / 'run/neoforge-native/libraries' / a['path']
        if matches(a, src): shutil.copy2(src, dest); return 'copied_verified'
    if not a.get('url'): raise RuntimeError(f'Missing generated artifact {dest}')
    part = dest.with_name(dest.name + f'.{os.getpid()}.part')
    subprocess.run(['curl', '--fail', '--silent', '--show-error', '--location', '--retry', '3', '--retry-delay', '1', '--connect-timeout', '30', '--max-time', '180', a['url'], '-o', str(part)], check=True)
    if not matches(a, part): raise RuntimeError(f'Checksum/size mismatch for {dest}')
    part.replace(dest)
    return 'downloaded_verified'

def allowed(library):
    rules = library.get('rules')
    if not rules: return True
    allow = False
    for rule in rules:
        os_rule = rule.get('os', {})
        if os_rule.get('name', 'linux') != 'linux': continue
        if 'arch' in os_rule and not re.fullmatch(os_rule['arch'], platform.machine()): continue
        if 'features' in rule: continue
        allow = rule['action'] == 'allow'
    return allow

def pool(items, label):
    counts = {}
    with concurrent.futures.ThreadPoolExecutor(max_workers=int(os.environ.get('CLIENT_DOWNLOAD_WORKERS', '8'))) as workers:
        for n, result in enumerate(workers.map(fetch, items), 1):
            counts[result] = counts.get(result, 0) + 1
            if n % 100 == 0: print(f'{label}: {n}/{len(items)}', flush=True)
    print(f'{label}: {counts}', flush=True)
    return counts

def main():
    ap = argparse.ArgumentParser(); ap.add_argument('--assets', choices=['all', 'none'], default='all');args=ap.parse_args()
    mc = json.loads((CLIENT/'versions/1.21.1/1.21.1.json').read_text())
    neo = json.loads((CLIENT/'versions/neoforge-21.1.219/neoforge-21.1.219.json').read_text())
    selected = {}
    for entry in mc['libraries'] + neo['libraries']:
        if not allowed(entry): continue
        a = entry.get('downloads', {}).get('artifact')
        if not a: continue
        # NeoForge entries supersede inherited modules by Maven group/artifact/classifier.
        coord = entry['name'].split(':'); key = ':'.join(coord[:2] + coord[3:])
        selected[key] = (entry, a)
    items = [(a, LIBS/a['path']) for _, a in selected.values()]
    report = {'versions': {'minecraft':'1.21.1', 'neoforge':'21.1.219'},'libraries':pool(items, 'Libraries')}
    log = mc['logging']['client']['file']; pool([(log, CLIENT/'assets/log_configs'/log['id'])], 'Log configuration')
    idx = mc['assetIndex']; idx_path = CLIENT/'assets/indexes'/f"{idx['id']}.json"
    pool([(idx,idx_path)], 'Asset index')
    if args.assets == 'all':
        objects = json.loads(idx_path.read_text())['objects']; unique={obj['hash']:obj['size'] for obj in objects.values()}
        report['assets'] = pool([({'sha1':h,'size':s,'url':f'https://resources.download.minecraft.net/{h[:2]}/{h}'}, CLIENT/'assets/objects'/h[:2]/h) for h,s in (reversed(list(unique.items())) if os.environ.get('CLIENT_DOWNLOAD_REVERSE') else unique.items())], 'Assets')
        report['asset_objects'] = len(unique);report['asset_bytes'] = sum(unique.values())
    natives=CLIENT/'natives/linux-x86_64';natives.mkdir(parents=True,exist_ok=True)
    extracted=[]
    for entry,a in selected.values():
        if 'natives-linux' in entry['name']:
            with zipfile.ZipFile(LIBS/a['path']) as jar:
                for name in jar.namelist():
                    if name.endswith('.so'):
                        dest=natives/pathlib.PurePosixPath(name).name; dest.write_bytes(jar.read(name));extracted.append(str(dest.relative_to(CLIENT)))
    classpath=[str(LIBS/a['path']) for _,a in selected.values()] + [str(CLIENT/'versions/1.21.1/1.21.1.jar')]
    (CLIENT/'client-classpath.txt').write_text(os.pathsep.join(classpath)+'\n')
    inventory={'mainClass':neo['mainClass'],'client_root':str(CLIENT),'classpaths':classpath,'native_directory':str(natives),'asset_directory':str(CLIENT/'assets'),'asset_index':idx['id'],'versions':[neo['id'],mc['id']], 'extracted_natives':extracted,'launch_note':'Production version arguments require a legitimate launcher session. Use the separate official ModDevGradle project for authorized no-account local development testing.'}
    (CLIENT/'client-layout.json').write_text(json.dumps(inventory,indent=2)+'\n')
    (ROOT/'logs/client-setup-distribution.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report,indent=2),flush=True)
if __name__=='__main__':main()
