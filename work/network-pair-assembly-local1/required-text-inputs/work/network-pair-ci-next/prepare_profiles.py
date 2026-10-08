#!/usr/bin/env python3
"""Build fresh four-mod fixtures after genuine probe compilation; never launch Java."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import tomllib
import zipfile

SOURCE_MANIFEST = '65cf1c852d6e07226fcd7d2f66df8d202f3a6e70cd4d8f963c6dc40b28554909'
CONFIG_SHA = '680abc46fe86fca345f0762bc2e822123376b76eb7f6844a79e1f0d3065d20c7'
SHARED = {'sophisticatedbackpacks-1.21.1-3.25.34.1604.jar': '889fb2af58e9f7951d0553033a856078b28fcdf802ca13eb432336b2b7b9780c',
          'sophisticatedcore-1.21.1-1.4.11.1553.jar': 'acafbe72eb161b0b763feb61eba06584e97e48f563de75f767611ee520dfcad7'}
EMI = {'native-neoforge': ('emi-1.1.24+1.21.1+neoforge.jar', 'b68691f94f0727fc517cac2ab55bd6658d1179cc8cc715fe610b60c37469bc4c'),
       'unified': ('emi-1.1.24+1.21.1+fabric.jar', '56ecd418e988cba23dd653d498309fd7b886265708253d5ca7a8fb621dcc5db4')}
NAME = 'APILocal'
UUID = 'dd29b97d-cafa-3d53-94e1-f85f75bcf1f6'

def require(ok, message):
    if not ok: raise ValueError(message)

def sha(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1048576), b''): h.update(block)
    return h.hexdigest()

def pin(path):
    p = Path(path)
    require(p.is_file() and not p.is_symlink() and p.resolve() == p, 'Expected canonical regular input')
    return {'path': str(p), 'bytes': p.stat().st_size, 'sha256': sha(p)}

def load(path, expected):
    record = pin(path)
    require(record['sha256'] == expected and record['bytes'] <= 4*1024*1024, 'Input receipt identity/size mismatch')
    return json.loads(Path(path).read_text())

def probe_inputs(source, jar, result_path, result_sha):
    require(sha(source/'source-manifest.json') == SOURCE_MANIFEST, 'Original probe source seal changed')
    manifest = json.loads((source/'source-manifest.json').read_text())
    require(manifest['schema'] == 1 and manifest['status'] == 'SOURCE_ONLY_NOT_RUNTIME_ACCEPTANCE', 'Unexpected original source state')
    for row in manifest['files']:
        record = pin(source/row['path'])
        require({k: record[k] for k in ('bytes', 'sha256')} == {k: row[k] for k in ('bytes', 'sha256')}, 'Changed probe source/resource')
    result = load(result_path, result_sha)
    require(result['status'] == 'PASS_COMPILE_REAL_CODEC_ONLY' and result['checks'] == 46 and
            result['sourceManifestSha256'] == SOURCE_MANIFEST and result['gameLaunched'] is False and
            result['networkAcceptance'] is False and result['publicInputClosureVerifiedBeforeAndAfter'] is True,
            'A genuine reviewed compile/codec result is required')
    record = pin(jar)
    require({k: record[k] for k in ('bytes', 'sha256')} == result['probeJar'], 'Probe output differs from successful build')
    require(record['bytes'] <= 262144, 'Own probe archive size ceiling')
    with zipfile.ZipFile(jar) as archive:
        names = archive.namelist()
        require(len(names) == len(set(names)) and len(names) <= 64 and sum(x.file_size for x in archive.infolist()) <= 1048576,
                'Unexpected own probe archive closure')
        allowed_resources = {'META-INF/MANIFEST.MF', 'META-INF/neoforge.mods.toml', 'LICENSE'}
        for name in names:
            p = Path(name)
            require(not p.is_absolute() and '..' not in p.parts, 'Unsafe own probe member')
            require(name.endswith('/') or name in allowed_resources or
                    (name.startswith('dev/infinity/networkcontrol/') and name.endswith('.class')), 'Foreign probe member')
        for name in ['NonceProbe', 'NonceProbeClient', 'NonceRequest', 'NonceReply']:
            require('dev/infinity/networkcontrol/' + name + '.class' in names, 'Missing real probe class')
        require(archive.read('LICENSE') == (source/'LICENSE').read_bytes(), 'Probe license differs')
        require(archive.read('META-INF/neoforge.mods.toml') == (source/'src/main/resources/META-INF/neoforge.mods.toml').read_bytes(), 'Probe mod metadata differs')
    return record

def properties(port):
    return {'server-ip': '127.0.0.1', 'server-port': str(port), 'online-mode': 'false',
            'enforce-secure-profile': 'false', 'white-list': 'true', 'enforce-whitelist': 'true',
            'enable-rcon': 'false', 'enable-query': 'false', 'enable-status': 'false',
            'max-players': '1', 'level-name': 'world', 'level-seed': '414822',
            'level-type': 'minecraft:flat', 'generate-structures': 'false', 'difficulty': 'peaceful',
            'gamemode': 'survival', 'view-distance': '2', 'simulation-distance': '2',
            'sync-chunk-writes': 'true', 'max-tick-time': '60000', 'spawn-protection': '0'}

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--target', required=True, choices=tuple(EMI))
    for key in ('source', 'probe', 'compile-result', 'compile-result-sha256', 'mods', 'config', 'output',
                'offline-identity-reference', 'eula-reference'):
        parser.add_argument('--' + key, required=True)
    parser.add_argument('--prepare', action='store_true')
    args = parser.parse_args()
    for reference in (args.offline_identity_reference, args.eula_reference):
        require(0 < len(reference) <= 512 and '\n' not in reference, 'Existing bounded authorization reference required')
    source = Path(args.source).resolve(strict=True)
    jar = Path(args.probe).resolve(strict=True)
    require(jar.name == 'network-control-probe-0.1.0.jar', 'Unexpected own probe filename')
    probe = probe_inputs(source, jar, Path(args.compile_result).resolve(strict=True), args.compile_result_sha256)
    mods = Path(args.mods).resolve(strict=True)
    originals = dict(SHARED, **dict([EMI[args.target]]))
    for name, digest in originals.items(): require(pin(mods/name)['sha256'] == digest, 'Original mod changed: ' + name)
    config = Path(args.config).resolve(strict=True)
    require(pin(config)['sha256'] == CONFIG_SHA and tomllib.loads(config.read_text()).get('advertiseDedicatedServerToLan') is False,
            'Complete accepted NeoForge server config required')
    output = Path(args.output)
    require(output.is_absolute() and not output.is_symlink() and output.resolve() == output and not output.exists(),
            'Fresh canonical output root required')
    port = 25631 if args.target == 'native-neoforge' else 25632
    prefix = 'native' if args.target == 'native-neoforge' else 'unified'
    result = {'schema': 1, 'status': 'SOURCE_INPUTS_VERIFIED_NOT_PREPARED', 'target': args.target,
              'probe': probe, 'compileResult': pin(Path(args.compile_result).resolve(strict=True)),
              'sourceManifestSha256': SOURCE_MANIFEST, 'port': port, 'profiles': {}, 'gameLaunched': False,
              'authorization': {'offlineIdentity': args.offline_identity_reference, 'eula': args.eula_reference},
              'remaining': ['Official consumer-local launch export', 'Complete assets/native/graphics closure',
                            'Actual measured graphics preflight', 'Reviewed supervisor pair seal and fresh capacity gate']}
    if args.target == 'unified': result['remaining'].append('Full-source-built current tuple and existing FML admission assembly/validation')
    if args.prepare:
        output.mkdir(parents=True)
        for side in ('server', 'client'):
            profile = output/(prefix + '-' + side)
            (profile/'mods').mkdir(parents=True)
            for name in originals: shutil.copyfile(mods/name, profile/'mods'/name)
            shutil.copyfile(jar, profile/'mods'/jar.name)
            for folder in ('config', 'defaultconfigs'):
                (profile/folder).mkdir(); shutil.copyfile(config, profile/folder/'neoforge-server.toml')
            if side == 'server':
                (profile/'server.properties').write_text(''.join(k+'='+v+'\n' for k,v in properties(port).items()))
                (profile/'whitelist.json').write_text(json.dumps([{'uuid': UUID, 'name': NAME}], indent=2)+'\n')
                (profile/'ops.json').write_text('[]\n')
                (profile/'eula.txt').write_text('eula=true\n')
            else:
                (profile/'options.txt').write_text('renderDistance:4\nsimulationDistance:6\nmaxFps:30\nenableVsync:false\nguiScale:2\n')
            result['profiles'][side] = {'workingDirectory': str(profile), 'original_mods': [str(profile/'mods'/n) for n in originals],
                                       'probe_path': str(profile/'mods'/jar.name),
                                       'files': [pin(p) for p in sorted(profile.rglob('*')) if p.is_file()]}
        result['status'] = 'FRESH_PROFILES_PREPARED_NO_LAUNCH'
        (output/'profile-preparation.json').write_text(json.dumps(result, indent=2)+'\n')
    print(json.dumps(result, indent=2))

if __name__ == '__main__': main()
