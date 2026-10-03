#!/usr/bin/env python3
"""Compile the original Forge-only fixture; never launch or rewrite the input JAR."""
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
    with zipfile.ZipFile(MC) as archive:
        assert 'net/minecraft/world/item/Item.class' in archive.namelist()
        assert not any(p.startswith(('net/neoforged/', 'net/fabricmc/')) for p in archive.namelist())
    libraries = ROOT / 'run/neoforge-native/libraries'
    dependency_groups = ['com/google/guava', 'com/mojang', 'it/unimi/dsi', 'org/joml',
                         'org/slf4j', 'org/jetbrains/annotations', 'com/google/code/findbugs']
    dependencies = sorted(p for group in dependency_groups for p in (libraries / group).rglob('*.jar'))
    cp = [UPSTREAM / name for name in OFFICIAL] + [MC] + dependencies
    classes = BUILD / 'classes'
    if classes.exists():
        shutil.rmtree(classes)
    classes.mkdir()
    sources = sorted((HERE / 'src').rglob('*.java'))
    for source in sources:
        assert not any(p in source.read_text() for p in ('net.neoforged', 'net.fabricmc'))
    subprocess.run([str(JAVA / 'javac'), '-proc:none', '--release', '21', '-encoding', 'UTF-8',
                    '-cp', ':'.join(map(str, cp)), '-d', str(classes), *map(str, sources)], check=True)
    jar = BUILD / 'unified-forge-probe-0.1.0.jar'
    subprocess.run([str(JAVA / 'jar'), '--create', '--date=2026-01-01T00:00:00Z', '--file', str(jar),
                    '-C', str(classes), '.', '-C', str(HERE / 'resources'), '.'], check=True)
    with zipfile.ZipFile(jar) as archive:
        assert 'META-INF/mods.toml' in archive.namelist()
        assert not any(n in archive.namelist() for n in ('fabric.mod.json', 'META-INF/neoforge.mods.toml'))
        for name in archive.namelist():
            if name.endswith('.class'):
                data = archive.read(name)
                assert b'net/neoforged' not in data and b'net/fabricmc' not in data, name
    disassembly = subprocess.check_output([str(JAVA / 'javap'), '-c', '-p', '-s', '-v',
                    '-classpath', str(jar), 'dev.infinity.forgeprobe.ForgeProbe',
                    'dev.infinity.forgeprobe.ForgeProbe$ProbeData'], text=True)
    (BUILD / 'probe-javap.txt').write_text(disassembly)
    required = ['FMLJavaModLoadingContext', 'net/minecraftforge/registries/RegistryObject',
                'net/minecraftforge/registries/DeferredRegister', 'ServerTickEvent$Post.haveTime:()Z',
                'net/minecraftforge/eventbus/api/IEventBus.addListener:(Ljava/util/function/Consumer;)V']
    for symbol in required:
        assert symbol in disassembly, f'Missing real Forge ABI: {symbol}'
    report = {'probe': str(jar.relative_to(ROOT)), 'sha256': sha(jar), 'java_release': 21,
              'namespace': 'Mojmap production Forge 52.1.0; no reobfuscation',
              'compile_method': 'javac against official Forge binaries and clean Mojmap Minecraft compile types',
              'native_runtime_validation': 'not asserted by build; see native phase reports',
              'sources': {str(p.relative_to(ROOT)): sha(p) for p in sources},
              'resources': {str(p.relative_to(ROOT)): sha(p) for p in sorted((HERE / 'resources').rglob('*')) if p.is_file()},
              'compile_inputs': [{'path': str(p.relative_to(ROOT)), 'sha256': sha(p)} for p in cp],
              'foreign_loader_reference_check': 'PASS', 'required_abi_check': 'PASS'}
    (BUILD / 'build-report.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps({k: report[k] for k in ('probe', 'sha256', 'foreign_loader_reference_check', 'required_abi_check')}))

if __name__ == '__main__':
    main()
