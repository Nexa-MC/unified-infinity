#!/usr/bin/env python3
"""Prepare a fresh pinned/LAN-disabled native or Unified Clumps behavior profile."""
import argparse
import hashlib
import json
import pathlib
import re
import shutil

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parents[1]
CLUMPS_SHA = 'e1de425ddd6f2b5c195c37a008d9fbc2c00c32fe1e214d76c63ab35446d13c19'
PROVIDER_SHA = '7b549d3725cbf63a529cf543aafa9ce1f9d0d65d3fe3cac93411f429e0955d99'
STAGES = {
    'create': ['constructor', 'server_started', 'post_tick', 'seeded', 'merge', 'nbt_roundtrip', 'world_create', 'ready_to_save'],
    'reopen': ['constructor', 'server_started', 'post_tick', 'world_reopen', 'nbt_roundtrip', 'ready_to_save'],
}
def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def valid_profile(value):
    return re.fullmatch(r'(forge-native-clumps|unified-forge-clumps|clumps-[a-z]+)(-[a-z0-9]+)*', value) is not None

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--profile', required=True)
    parser.add_argument('--loader', choices=['native', 'unified'], required=True)
    parser.add_argument('--probe', required=True)
    parser.add_argument('--probe-sha', required=True)
    parser.add_argument('--marker', required=True)
    parser.add_argument('--core')
    parser.add_argument('--core-sha')
    parser.add_argument('--host')
    parser.add_argument('--host-sha')
    args = parser.parse_args()
    assert valid_profile(args.profile), 'Invalid isolated profile name'
    profile = ROOT / 'run' / args.profile
    lock_path = HERE / (args.profile + '-lock.json')
    assert not profile.exists() and not lock_path.exists(), 'Preserve prior profile/evidence'
    base = ROOT / 'run' / ('forge-native-probe' if args.loader == 'native' else 'neoforge-native')
    clumps = ROOT / 'docs/four-loader/forge/upstream/Clumps-forge-1.21.1-19.0.0.1.jar'
    probe = ROOT / args.probe
    assert sha(clumps) == CLUMPS_SHA and clumps.stat().st_size == 18226
    assert sha(probe) == args.probe_sha
    inputs = [clumps, probe]
    build = json.loads((ROOT / 'four-loader/clumps-probe/build/build-report.json').read_text())
    assert build['sha256'] == sha(probe), 'Companion build report differs'
    fixture_sources = []
    for section in ('sources', 'resources'):
        for name, expected in build[section].items():
            assert sha(ROOT / name) == expected, f'Changed companion {section}: {name}'
            fixture_sources.append({'path': name, 'sha256': expected})
    inherited_lock = None
    if args.loader == 'native':
        inherited_lock = ROOT / 'four-loader/forge-probe/native-environment-lock.json'
        accepted = json.loads(inherited_lock.read_text())
        for item in accepted['runtime_files']:
            assert sha(ROOT / item['path']) == item['sha256'], 'Changed pinned native base: ' + item['path']
    else:
        assert all([args.core, args.core_sha, args.host, args.host_sha]), 'Unified requires exact matched core/host'
        core, host = ROOT / args.core, ROOT / args.host
        provider = ROOT / 'run/source-built-lithium-unified/mods/unified-infinity-preload-0.1.0-dev.jar'
        assert sha(core) == args.core_sha and sha(host) == args.host_sha and sha(provider) == PROVIDER_SHA
        inputs += [core, host, provider]
    assert (base / 'eula.txt').read_text().strip() == 'eula=true', 'Reuse existing accepted EULA only'
    profile.mkdir()
    (profile / 'mods').mkdir()
    # Separate files, never symlinks/hardlinks into any accepted profile or world.
    shutil.copytree(base / 'libraries', profile / 'libraries')
    shutil.copy2(base / 'eula.txt', profile / 'eula.txt')
    for item in inputs:
        shutil.copy2(item, profile / 'mods' / item.name)
    props = {
        'server-ip': '127.0.0.1', 'server-port': '25594' if args.loader == 'native' else '25595',
        'online-mode': 'true', 'enable-rcon': 'false', 'enable-query': 'false', 'enable-status': 'false',
        'white-list': 'true', 'enforce-whitelist': 'true', 'enforce-secure-profile': 'true',
        'max-players': '1', 'level-name': 'world', 'level-seed': '521019', 'view-distance': '2',
        'simulation-distance': '2', 'spawn-protection': '0', 'difficulty': 'peaceful',
        'generate-structures': 'false', 'sync-chunk-writes': 'true', 'max-tick-time': '60000',
        'pause-when-empty-seconds': '-1', 'motd': 'Private Clumps behavior control',
    }
    (profile / 'server.properties').write_text(''.join(f'{k}={v}\n' for k, v in props.items()))
    if args.loader == 'native':
        config = profile / 'defaultconfigs/forge-server.toml'
        config.parent.mkdir()
        config.write_text('[server]\nadvertiseDedicatedServerToLan = false\n')
        argfile = 'libraries/net/minecraftforge/forge/1.21.1-52.1.0/unix_args.txt'
        shim = profile / 'forge-1.21.1-52.1.0-shim.jar'
        shutil.copy2(base / shim.name, shim)
    else:
        config = profile / 'config/neoforge-server.toml'
        config.parent.mkdir()
        config.write_text('advertiseDedicatedServerToLan = false\n')
        argfile = 'libraries/net/neoforged/neoforge/21.1.219/unix_args.txt'
    runtime = sorted((profile / 'libraries').rglob('*.jar'))
    runtime += [profile / argfile, ROOT / '.toolchains/jdk-21.0.12.1+1/bin/java']
    if args.loader == 'native':
        runtime.append(shim)
    lock = {
        'profile': str(profile.relative_to(ROOT)), 'loader': args.loader, 'minecraft': '1.21.1',
        'referenceForge': '52.1.0', 'nativeHost': '21.1.219' if args.loader == 'unified' else '52.1.0',
        'argfile': argfile, 'probe_sha256': sha(probe), 'clumps_sha256': CLUMPS_SHA,
        'mods': {x.name: sha(x) for x in sorted((profile / 'mods').glob('*.jar'))},
        'original_inputs': [{'path': str(x.relative_to(ROOT)), 'sha256': sha(x)} for x in inputs],
        'fixture_sources': fixture_sources,
        'runtime_files': [{'path': str(x.relative_to(ROOT)), 'sha256': sha(x)} for x in runtime],
        'expected_stages': STAGES, 'expected_saved_marker': args.marker,
        'expected_clumped_map': {'1': 1, '3': 1, '7': 2, '17': 1, '37': 1}, 'expected_xp': 72,
        'server_properties': props, 'lan_disabled_config': str(config.relative_to(profile)),
        'scope': 'Exact original Clumps plus identical project-owned comparison companion; no accounts/public service',
        'core_sha256': args.core_sha, 'host_sha256': args.host_sha,
        'inherited_native_lock_sha256': sha(inherited_lock) if inherited_lock else None,
        'eula': 'Reuses previously accepted local Minecraft test-server EULA',
    }
    lock_path.write_text(json.dumps(lock, indent=2) + '\n')
    (ROOT / 'logs' / args.profile).mkdir()
    print(json.dumps({'profile': str(profile), 'lock': str(lock_path), 'mods': lock['mods']}, indent=2))

if __name__ == '__main__':
    main()
