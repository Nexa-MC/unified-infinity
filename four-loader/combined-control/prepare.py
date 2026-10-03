#!/usr/bin/env python3
"""Prepare only: copy approved original archives into an isolated combined profile."""
import argparse
import json
import pathlib
import shutil
from common import HERE, ROOT, PORT, INPUTS, REUSED_FILES, sha, valid_profile

def prepare(name):
    assert valid_profile(name), 'Invalid isolated profile name'
    profile, lock_path = ROOT / 'run' / name, HERE / (name + '-lock.json')
    assert not profile.exists() and not lock_path.exists(), 'Preserve existing profiles/evidence'
    for path, expected in INPUTS.items():
        assert sha(ROOT / path) == expected, 'Original input changed: ' + path
    fixture_sources = {}
    for probe in ('clumps-probe', 'quilt-probe'):
        report_path = ROOT / 'four-loader' / probe / 'build/build-report.json'
        report = json.loads(report_path.read_text())
        assert INPUTS[report['probe']] == report['sha256']
        fixture_sources[str(report_path.relative_to(ROOT))] = sha(report_path)
        for section in ('sources', 'resources'):
            for path, expected in report.get(section, {}).items():
                assert sha(ROOT / path) == expected, 'Companion source changed: ' + path
                fixture_sources[path] = expected
        for path in sorted((ROOT / 'four-loader' / probe / 'resources').rglob('*')):
            if path.is_file():
                fixture_sources[str(path.relative_to(ROOT))] = sha(path)
    base = ROOT / 'run/neoforge-native'
    assert (base / 'eula.txt').read_text().strip() == 'eula=true'
    profile.mkdir()
    (profile / 'mods').mkdir()
    (profile / 'config').mkdir()
    shutil.copytree(base / 'libraries', profile / 'libraries')  # No shared hardlinks or world.
    shutil.copy2(base / 'eula.txt', profile / 'eula.txt')
    for path in INPUTS:
        shutil.copy2(ROOT / path, profile / 'mods' / pathlib.Path(path).name)
    (profile / 'config/neoforge-server.toml').write_text('advertiseDedicatedServerToLan = false\n')
    (profile / 'config/lithium.properties').write_text('# Default Lithium configuration; zero overrides.\n')
    shutil.copy2(ROOT / 'run/source-built-lithium-unified/config/connector.json', profile / 'config/connector.json')
    assert json.loads((profile / 'config/connector.json').read_text())['enableMixinSafeguard'] is True
    props = {'server-ip': '127.0.0.1', 'server-port': PORT, 'online-mode': 'true',
             'enable-rcon': 'false', 'enable-query': 'false', 'enable-status': 'false',
             'white-list': 'true', 'enforce-whitelist': 'true', 'enforce-secure-profile': 'true',
             'max-players': '1', 'level-name': 'world', 'level-seed': '1211',
             'level-type': 'minecraft:normal', 'view-distance': '2', 'simulation-distance': '2',
             'spawn-protection': '0', 'difficulty': 'peaceful', 'generate-structures': 'true',
             'enable-command-block': 'false', 'sync-chunk-writes': 'true', 'max-tick-time': '60000',
             'pause-when-empty-seconds': '-1', 'motd': 'Private combined four-loader server regression'}
    (profile / 'server.properties').write_text(''.join(f'{key}={value}\n' for key, value in props.items()))
    harness = {str(path.relative_to(ROOT)): sha(path) for path in sorted(HERE.glob('*.py'))}
    harness.update({path: sha(ROOT / path) for path in REUSED_FILES})
    lock = {'profile': str(profile.relative_to(ROOT)), 'status_at_preparation': 'NOT LAUNCHED',
            'original_inputs': INPUTS, 'mods': {p.name: sha(p) for p in sorted((profile / 'mods').iterdir())},
            'libraries': {str(p.relative_to(profile / 'libraries')): sha(p) for p in sorted((profile / 'libraries').rglob('*')) if p.is_file()},
            'java_sha256': sha(ROOT / '.toolchains/jdk-21.0.12.1+1/bin/java'),
            'harness_files': harness, 'fixture_sources': fixture_sources, 'server_properties': props,
            'config_files': {name: sha(profile / name) for name in ('config/connector.json', 'config/lithium.properties')},
            'argfile': 'libraries/net/neoforged/neoforge/21.1.219/unix_args.txt',
            'scope': 'Combined server integration; original Fabric Lithium/Chunky, native NeoForge Farmers Delight, original Forge Clumps plus Forge companion, and project-owned native Quilt probe. Not OP Tab or client acceptance.',
            'eula': 'Reuses previously accepted local Minecraft test-server EULA'}
    with lock_path.open('x') as stream:
        stream.write(json.dumps(lock, indent=2) + '\n')
    (ROOT / 'logs' / name).mkdir()
    print(json.dumps({'profile': str(profile), 'lock': str(lock_path), 'lock_sha256': sha(lock_path), 'mods': lock['mods'], 'status': 'PREPARED; NOT LAUNCHED'}, indent=2))
    return lock

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--profile', required=True)
    prepare(parser.parse_args().profile)
