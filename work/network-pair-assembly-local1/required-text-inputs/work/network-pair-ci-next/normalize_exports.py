#!/usr/bin/env python3
"""Normalize genuine consumer-local ModDev exports. Never launches a process."""
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path

NAME = 'APILocal'
UUID = 'dd29b97d-cafa-3d53-94e1-f85f75bcf1f6'
ASSEMBLER_SHA = '07148f3909828a55ee9698a8ed9d96ad6bada651226ab1bf1fdff858c703b37a'
VALIDATOR_SHA = 'a2ba610d504b73160cdd124e399df48d9b8c196c9591f43ab82c6b14729f5451'
JAVA_SHA = '2a207f5e7d075afa01d97f8048389a64432a44c4a5af0f5e77d6e286ec5f401d'
TARGETS = {'client': 'forgeclientdev', 'server': 'forgeserverdev'}
PATH_OPTIONS = {'-cp', '-classpath', '--class-path', '-p', '--module-path'}
FORBIDDEN = ('-javaagent', '-agentlib', '-agentpath', '-Xbootclasspath', '--patch-module', '--upgrade-module-path')

def require(ok, message):
    if not ok: raise ValueError(message)

def sha(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for part in iter(lambda: stream.read(1048576), b''): h.update(part)
    return h.hexdigest()

def canonical(value):
    p = Path(value)
    require(p.is_absolute() and '..' not in p.parts and not p.is_symlink(), 'Noncanonical or redirected input')
    require(p.resolve() == p, 'Redirected input ancestor')
    return p

def set_option(args, name, value):
    positions = [i for i, token in enumerate(args) if token == name]
    require(len(positions) <= 1, 'Duplicate launch option: ' + name)
    if positions:
        index = positions[0]
        require(index + 1 < len(args), 'Missing launch value: ' + name)
        args[index + 1] = value
    else:
        args.extend([name, value])

def strip_empty_paths(value, empty, add_file):
    result = []
    for name in value.split(os.pathsep):
        require(name and '*' not in name, 'Implicit or wildcard classpath')
        p = canonical(name)
        if str(p) in empty:
            require(not p.exists() or (p.is_dir() and not any(p.iterdir())), 'Declared empty root contains data')
            continue
        add_file(p)
        result.append(str(p))
    require(result, 'Empty effective classpath')
    return os.pathsep.join(result)

def normalize_role(role, row, java, flatten, port, asset_root):
    require(role in TARGETS and row['environment'] == {}, 'Unknown role or injected development environment')
    cwd = canonical(row['workingDirectory'])
    require(cwd.is_dir(), 'Exporter game directory missing')
    empty = set(row['emptyDevelopmentRoots'])
    pins = {}
    def add_file(value):
        p = canonical(str(value))
        require(p.is_file(), 'Missing literal launch input: ' + str(p))
        pin = {'path': str(p), 'bytes': p.stat().st_size, 'sha256': sha(p)}
        if str(p) in pins: require(pins[str(p)] == pin, 'Launch input changed during normalization')
        pins[str(p)] = pin
        return p
    for pin in row['files']:
        p = add_file(pin['path'])
        require(pins[str(p)] == pin, 'Generated export input hash/size mismatch')
    java = add_file(java)
    command = [str(java), *row['jvmArgs'], '-cp', os.pathsep.join(row['classpath']), row['mainClass'], *row['args']]
    flat = flatten(command, {p: r['sha256'] for p, r in pins.items()}, cwd)
    require('cpw.mods.bootstraplauncher.BootstrapLauncher' in flat, 'Official BootstrapLauncher delegation missing')
    require(flat.count('--launchTarget') == 1 and flat[flat.index('--launchTarget') + 1] == TARGETS[role], 'Wrong physical launch side')
    require(not any(x.startswith(FORBIDDEN) for x in flat), 'Unapproved pre-BOOT injection')
    require([x for x in flat if x.startswith('-Xmx')] in (['-Xmx1280m'], ['-Xmx1280M']), 'Original heap differs')
    require([x for x in flat if x.startswith('-XX:ActiveProcessorCount=')] == ['-XX:ActiveProcessorCount=2'], 'Original processor count differs')
    require(not any(x.startswith(('-XX:MaxHeapSize=', '-XX:Flags=', '-XX:VMOptionsFile=')) for x in flat), 'Conflicting VM options')
    result = []
    i = 0
    while i < len(flat):
        arg = flat[i]
        if arg in PATH_OPTIONS:
            require(i + 1 < len(flat), 'Missing JVM path value')
            result.extend([arg, strip_empty_paths(flat[i + 1], empty, add_file)])
            i += 2
            continue
        if arg.startswith('-DlegacyClassPath.file='):
            p = add_file(arg.split('=', 1)[1])
            require(p.stat().st_size <= 1048576, 'Oversized legacy classpath')
            entries = [line.strip() for line in p.read_text().splitlines() if line.strip()]
            result.append('-DlegacyClassPath=' + strip_empty_paths(os.pathsep.join(entries), empty, add_file))
        elif arg.startswith('-DlegacyClassPath='):
            result.append('-DlegacyClassPath=' + strip_empty_paths(arg.split('=', 1)[1], empty, add_file))
        elif arg.startswith('-D'):
            key, _, value = arg[2:].partition('=')
            require(key not in {'fml.modFolders', 'fml.modFoldersFile', 'java.system.class.loader'} or not value,
                    'Grouped/custom loader implementation roots')
            if key in {'log4j2.configurationFile', 'connector.clean.path'}: add_file(value)
            result.append(arg)
        else:
            result.append('-Xmx1280m' if arg.startswith('-Xmx') else arg)
        i += 1
    require(not any(x.startswith('@') for x in result), 'Unexpanded launch response file')
    set_option(result, '--gameDir', str(cwd))
    if role == 'client':
        forbidden = {'--username', '--uuid', '--accessToken', '--userProperties', '--clientId', '--xuid', '--server',
                     '--proxyHost', '--proxyPort', '--quickPlayMultiplayer', '--quickPlaySingleplayer', '--quickPlayRealms'}
        require(not forbidden.intersection(result), 'Export already contains account, server or quick-play parameters')
        require(result.count('--assetIndex') == 1 and result[result.index('--assetIndex') + 1] == '17', 'Wrong official asset index')
        require(result.count('--assetsDir') == 1 and canonical(result[result.index('--assetsDir') + 1]) == asset_root,
                'Asset root must be generated by this consumer, not rewritten from a producer')
        for key, value in [('--username', NAME), ('--uuid', UUID), ('--accessToken', '0'),
                           ('--quickPlayMultiplayer', '127.0.0.1:' + str(port))]: set_option(result, key, value)
    else:
        require(not any(x in result for x in ('--username', '--uuid', '--accessToken', '--quickPlayMultiplayer')), 'Client identity on server')
        require(result.count('nogui') <= 1 and '--nogui' not in result, 'Unexpected no-GUI form')
        if 'nogui' not in result: result.append('nogui')
    return {'workingDirectory': str(cwd), 'command': [str(java), *result], 'environment': {},
            'files': sorted(pins.values(), key=lambda x: x['path']), 'emptyDevelopmentRoots': sorted(empty),
            'gameLaunched': False, 'launchReady': False}

def main():
    parser = argparse.ArgumentParser()
    for name in ('export', 'export-sha256', 'assembler', 'assembler-sha256', 'java', 'assets', 'output'):
        parser.add_argument('--' + name, required=True)
    args = parser.parse_args()
    export = canonical(args.export)
    require(export.is_file() and export.stat().st_size <= 4*1024*1024 and sha(export) == args.export_sha256, 'Export pin mismatch')
    assembler = canonical(args.assembler)
    require(sha(assembler) == args.assembler_sha256 == ASSEMBLER_SHA, 'Existing assembler source identity differs')
    require(sha(assembler.with_name('validate_launch.py')) == VALIDATOR_SHA, 'Existing validator source identity differs')
    require(sha(canonical(args.java)) == JAVA_SHA, 'Approved Temurin Java executable identity differs')
    module_spec = importlib.util.spec_from_file_location('pair_source_assembler', assembler)
    module = importlib.util.module_from_spec(module_spec)
    module_spec.loader.exec_module(module)
    doc = json.loads(export.read_text())
    require({k: doc[k] for k in ('schema', 'gameLaunched', 'minecraft', 'neoForge', 'modDev', 'binaryOnly')} ==
            {'schema': 1, 'gameLaunched': False, 'minecraft': '1.21.1', 'neoForge': '21.1.219', 'modDev': '2.0.140', 'binaryOnly': True}, 'Wrong official exporter provenance')
    require(set(doc['roles']) == {'client', 'server'}, 'Exactly two independent launch roles required')
    out = canonical(args.output)
    require(not out.exists(), 'Refusing to overwrite earlier normalization')
    assets = canonical(args.assets)
    rows = {side: normalize_role(side, doc['roles'][side], canonical(args.java), module.flatten, 25631, assets)
            for side in ('server', 'client')}
    require(rows['server']['workingDirectory'] != rows['client']['workingDirectory'], 'Shared client/server profile')
    result = {'schema': 1, 'status': 'COMMANDS_NORMALIZED_PAIR_NOT_READY', 'target': 'native-neoforge',
              'officialExport': {'path': str(export), 'sha256': sha(export)}, 'roles': rows,
              'remaining': ['Compiled probe and source-bound receipt', 'Exact original four-mod inventories',
                            'Complete verified assets/native files', 'Actual graphics preflight',
                            'Consumer-generated supervisor spec and fresh aggregate memory gate']}
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps({'status': result['status'], 'path': str(out), 'sha256': sha(out), 'gameLaunched': False}))

if __name__ == '__main__': main()
