#!/usr/bin/env python3
"""Freeze the installed official native control and its original project-owned input."""
import hashlib
import json
import pathlib
import shutil

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parents[1]
PROFILE = ROOT / 'run/forge-native-probe'
LOGS = ROOT / 'logs/forge-native-probe'
LOCK = HERE / 'native-environment-lock.json'
assert not LOCK.exists(), 'Preserve the existing native environment lock'
assert not (PROFILE / 'world').exists(), 'Pin only before the first world launch'
assert 'The server installed successfully' in (LOGS / 'installer.log').read_text()
build = json.loads((HERE / 'build/build-report.json').read_text())
probe = ROOT / build['probe']
sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
assert sha(probe) == build['sha256']
mods = PROFILE / 'mods'
mods.mkdir(exist_ok=True)
assert not list(mods.iterdir()), 'Native own-probe control must start with an empty mods directory'
shutil.copy2(probe, mods / probe.name)
(PROFILE / 'eula.txt').write_text('eula=true\n')
properties = {
    'server-ip': '127.0.0.1', 'server-port': '25591', 'online-mode': 'true',
    'enable-rcon': 'false', 'enable-query': 'false', 'enable-status': 'false',
    'enforce-secure-profile': 'true', 'white-list': 'true', 'enforce-whitelist': 'true',
    'max-players': '1', 'level-name': 'world', 'level-seed': '5210',
    'view-distance': '2', 'simulation-distance': '2', 'spawn-protection': '0',
    'max-tick-time': '60000', 'motd': 'Project-owned Forge native ABI control',
    'difficulty': 'peaceful', 'allow-nether': 'true', 'generate-structures': 'false',
    'sync-chunk-writes': 'true', 'pause-when-empty-seconds': '-1',
}
(PROFILE / 'server.properties').write_text(''.join(f'{k}={v}\n' for k, v in properties.items()))
(PROFILE / 'defaultconfigs').mkdir(exist_ok=True)
(PROFILE / 'defaultconfigs/forge-server.toml').write_text('[server]\nadvertiseDedicatedServerToLan = false\n')
runtime = sorted((PROFILE / 'libraries').rglob('*.jar'))
runtime += [PROFILE / 'libraries/net/minecraftforge/forge/1.21.1-52.1.0/unix_args.txt',
            PROFILE / 'forge-1.21.1-52.1.0-shim.jar',
            PROFILE / 'defaultconfigs/forge-server.toml',
            ROOT / '.toolchains/jdk-21.0.12.1+1/bin/java',
            ROOT / 'docs/four-loader/forge/upstream/forge-1.21.1-52.1.0-installer.jar']
assert hashlib.sha1((PROFILE / 'libraries/net/minecraftforge/forge/1.21.1-52.1.0/forge-1.21.1-52.1.0-server.jar').read_bytes()).hexdigest() == 'a58e275894025c9f600ef3b60eb0ad6caf4532c8'
lock = {'minecraft': '1.21.1', 'forge': '52.1.0', 'eventbus': '6.2.27',
        'java': '21.0.12.1+1-LTS', 'probe_sha256': sha(probe),
        'namespace': 'Mojmap native production', 'server_properties': properties,
        'eula_approval': 'Existing user approval for local cloud test servers, reaffirmed by coordinating parent',
        'mods': [{'name': probe.name, 'sha256': sha(probe)}],
        'runtime_files': [{'path': str(p.relative_to(ROOT)), 'sha256': sha(p)} for p in runtime]}
LOCK.write_text(json.dumps(lock, indent=2) + '\n')
print(json.dumps({'lock': str(LOCK), 'lock_sha256': sha(LOCK), 'probe_sha256': sha(probe), 'runtime_files': len(runtime)}))
