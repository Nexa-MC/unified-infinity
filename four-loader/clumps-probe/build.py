#!/usr/bin/env python3
"""Build this original fixture only. Never launch Minecraft or modify its inputs."""
import hashlib
import json
import pathlib
import shutil
import subprocess
import zipfile

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parents[1]
JAVA = ROOT / '.toolchains/jdk-21.0.12.1+1/bin'
BUILD = HERE / 'build'
UPSTREAM = ROOT / 'docs/four-loader/forge/upstream'
MC = ROOT / 'source-workspace/connector-combined/build/createCleanArtifact/minecraft-renamed.jar'
CLUMPS = UPSTREAM / 'Clumps-forge-1.21.1-19.0.0.1.jar'
CLUMPS_SHA256 = 'e1de425ddd6f2b5c195c37a008d9fbc2c00c32fe1e214d76c63ab35446d13c19'
OFFICIAL = ['forge-1.21.1-52.1.0-universal.jar', 'fmlcore-1.21.1-52.1.0.jar',
            'javafmllanguage-1.21.1-52.1.0.jar', 'eventbus-6.2.27.jar']


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    BUILD.mkdir(exist_ok=True)
    locks = json.loads((ROOT / 'docs/four-loader/forge/source-lock.json').read_text())
    expected = {pathlib.Path(a['path']).name: a['sha256'] for a in locks['artifacts']}
    for name in OFFICIAL:
        assert sha(UPSTREAM / name) == expected[name], f'Official artifact mismatch: {name}'
    assert sha(CLUMPS) == CLUMPS_SHA256, 'Approved Clumps artifact mismatch'
    with zipfile.ZipFile(MC) as archive:
        assert 'net/minecraft/world/entity/ExperienceOrb.class' in archive.namelist()
        assert not any(p.startswith(('net/neoforged/', 'net/fabricmc/')) for p in archive.namelist())
    libraries = ROOT / 'run/neoforge-native/libraries'
    groups = ['com/google/guava', 'com/mojang', 'it/unimi/dsi', 'org/joml',
              'org/slf4j', 'org/jetbrains/annotations', 'com/google/code/findbugs']
    dependencies = sorted(p for group in groups for p in (libraries / group).rglob('*.jar'))
    cp = [UPSTREAM / name for name in OFFICIAL] + [MC, CLUMPS] + dependencies
    classes = BUILD / 'classes'
    if classes.exists():
        shutil.rmtree(classes)
    classes.mkdir()
    sources = sorted((HERE / 'src').rglob('*.java'))
    for source in sources:
        assert not any(p in source.read_text() for p in ('net.neoforged', 'net.fabricmc'))
    subprocess.run([str(JAVA / 'javac'), '-proc:none', '--release', '21', '-encoding', 'UTF-8',
                    '-cp', ':'.join(map(str, cp)), '-d', str(classes), *map(str, sources)], check=True)
    shutil.copyfile(HERE / 'LICENSE', HERE / 'resources/META-INF/LICENSE')
    jar = BUILD / 'unified-clumps-probe-0.1.0.jar'
    subprocess.run([str(JAVA / 'jar'), '--create', '--date=2026-01-01T00:00:00Z', '--file', str(jar),
                    '-C', str(classes), '.', '-C', str(HERE / 'resources'), '.'], check=True)
    with zipfile.ZipFile(jar) as archive:
        names = archive.namelist()
        assert 'META-INF/mods.toml' in names and 'META-INF/LICENSE' in names
        assert not any(n in names for n in ('fabric.mod.json', 'META-INF/neoforge.mods.toml'))
        for name in names:
            if name.endswith('.class'):
                assert name.startswith('dev/infinity/clumpsprobe/'), f'Bundled dependency: {name}'
                data = archive.read(name)
                assert b'net/neoforged' not in data and b'net/fabricmc' not in data, name
                assert b'clumps$setClumpedMap' not in data, 'Fixture must not manufacture Clumps state'
    disassembly = subprocess.check_output([str(JAVA / 'javap'), '-c', '-p', '-s', '-v',
                    '-classpath', str(jar), 'dev.infinity.clumpsprobe.ClumpsProbe',
                    'dev.infinity.clumpsprobe.ClumpsProbe$ProbeData'], text=True)
    (BUILD / 'probe-javap.txt').write_text(disassembly)
    required = ['net/minecraftforge/fml/common/Mod', 'ServerTickEvent$Post.haveTime:()Z',
                'ServerTickEvent$Post.getServer:()Lnet/minecraft/server/MinecraftServer;',
                'net/minecraftforge/eventbus/api/IEventBus.addListener:(Ljava/util/function/Consumer;)V',
                'com/blamejared/clumps/helper/IClumpedOrb.clumps$getClumpedMap:()Ljava/util/Map;']
    for symbol in required:
        assert symbol in disassembly, f'Missing real ABI: {symbol}'
    report = {'probe': str(jar.relative_to(ROOT)), 'sha256': sha(jar), 'java_release': 21,
              'namespace': 'Mojmap production Forge 52.1.0; no reobfuscation',
              'compile_method': 'javac against official Forge, clean Minecraft and compile-only Clumps',
              'runtime_validation': 'NOT RUN: compile and pure arithmetic tests do not establish Minecraft behavior',
              'clumps_sha256': CLUMPS_SHA256,
              'sources': {str(p.relative_to(ROOT)): sha(p) for p in sources},
              'resources': {str(p.relative_to(ROOT)): sha(p) for p in sorted((HERE / 'resources').rglob('*')) if p.is_file()},
              'compile_inputs': [{'path': str(p.relative_to(ROOT)), 'sha256': sha(p)} for p in cp],
              'foreign_loader_reference_check': 'PASS', 'required_abi_check': 'PASS',
              'no_bundled_dependencies_check': 'PASS', 'no_clumped_map_setter_check': 'PASS'}
    (BUILD / 'build-report.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps({k: report[k] for k in ('probe', 'sha256', 'required_abi_check', 'runtime_validation')}))


if __name__ == '__main__':
    main()
