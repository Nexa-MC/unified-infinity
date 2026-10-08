#!/usr/bin/env python3
"""Source-only preparation and pinned original Forge ABI regression fixture.

The unchanged build.py is run once by the caller's bounded process owner. It is
not a game, a PLAY implementation, or a substitute for any original input JAR.
"""
import json
from pathlib import Path
import shutil
import sys
import fml_metadata as files

HERE = Path(__file__).resolve().parent
LOCK_SHA = '18164e1e9df3dc2d9076ed05304823a51319644b6c6ea4cffb145e6eb5f15177'
EXPECTED = '3a016e8b8340c7c10b6490f15bb7452c1555363035c7373f4d81ccfacfde15fe'
SOURCE = 'four-loader/forge-probe'
SUPPORT = 'work/emi-render-integration/forge-fixture'
CLEAN_SOURCE = 'run/api1-unified-client-build/build/moddev/artifacts/minecraft-1.21.1-clean.jar'
CLEAN_DESTINATION = 'source-workspace/connector-combined/build/createCleanArtifact/minecraft-renamed.jar'
CLEAN_SHA = '26a29a83d298df77d4bc78e7029ffb453e479a0e4fd2d7f7a0ac84b6726fdf3c'
CLEAN_BYTES = 18887912
require = files.require


def lock(path):
    require(files.sha(path) == LOCK_SHA, 'Original Forge fixture source/compile lock changed')
    data = json.loads(path.read_text())
    require(data['expectedFixtureSha256'] == EXPECTED, 'Original Forge fixture reference changed')
    return data


def prepare(consumer):
    root = files.canonical(consumer)
    bundled = HERE / 'fixture-support'
    data = lock(bundled / 'input-lock.json')
    expected = {'input-lock.json', *[r['path'] for r in data['files']]}
    require({p.relative_to(bundled).as_posix() for p in bundled.rglob('*') if p.is_file()} == expected,
            'Unexpected Forge fixture source bundle entry')
    payloads = []
    for row in data['files']:
        source = bundled / row['path']
        require(files.sha(source) == row['sha256'] and source.stat().st_size == row['bytes'],
                'Original Forge fixture source changed')
        payloads.append((root / 'work/api1' / row['path'], source.read_bytes()))
    payloads.append((root / SUPPORT / 'input-lock.json', (bundled / 'input-lock.json').read_bytes()))
    for destination, raw in payloads:
        destination = files.canonical(destination)
        require(not destination.exists() or destination.is_file() and destination.read_bytes() == raw,
                'Refusing changed Forge fixture prerequisite: ' + str(destination))
    for destination, raw in payloads:
        if not destination.exists():
            destination.parent.mkdir(parents=True, exist_ok=True)
            with destination.open('xb') as stream:
                stream.write(raw)
    result = {'schema': 1, 'status': 'ORIGINAL_FORGE_FIXTURE_SOURCE_READY_NO_JVM',
              'sourceInputs': verify_sources(root), 'expectedFixtureSha256': EXPECTED,
              'inputLock': files.pin(root / SUPPORT / 'input-lock.json'), 'jvmStarted': False, 'gameLaunched': False}
    files.save(root / SUPPORT / 'source-preparation.json', result)
    return result


def verify_sources(root):
    root = files.canonical(root)
    api = root / 'work/api1'
    data = lock(root / SUPPORT / 'input-lock.json')
    rows = []
    for row in data['files']:
        current = files.pin(api / row['path'])
        require(current['sha256'] == row['sha256'] and current['bytes'] == row['bytes'],
                'Forge fixture source input changed: ' + row['path'])
        rows.append(current)
    source = api / SOURCE
    require(sorted(p.relative_to(api).as_posix() for p in (source / 'src').rglob('*.java')) == data['sourceFiles'],
            'Original Forge source selection changed')
    require(sorted(p.relative_to(api).as_posix() for p in (source / 'resources').rglob('*') if p.is_file()) == data['resourceFiles'],
            'Original Forge resource selection changed')
    require(json.loads((source / 'expected-abi.json').read_text())['probe_sha256'] == EXPECTED,
            'Original Forge expected ABI identity changed')
    return rows


def verify_inputs(root):
    root = files.canonical(root)
    api = root / 'work/api1'
    verify_sources(root)
    data = lock(root / SUPPORT / 'input-lock.json')
    rows = []
    for row in data['inputs']:
        current = files.pin(api / row['path'])
        require(current['sha256'] == row['sha256'] and current['bytes'] == row['bytes'],
                'Forge fixture compile input changed: ' + row['path'])
        rows.append(current)
    libraries = api / 'run/neoforge-native/libraries'
    dependencies = sorted(p.relative_to(api).as_posix() for group in data['dependencyGroups']
                          for p in (libraries / group).rglob('*.jar'))
    require(dependencies == data['compileDependencyFiles'], 'Forge fixture dependency selection changed')
    return rows


def clean_alias(root):
    api = files.canonical(root) / 'work/api1'
    source, destination = api / CLEAN_SOURCE, api / CLEAN_DESTINATION
    require(files.sha(source) == CLEAN_SHA and source.stat().st_size == CLEAN_BYTES,
            'Fresh official clean Minecraft compile artifact differs')
    files.canonical(destination)
    if destination.exists():
        require(files.sha(destination) == CLEAN_SHA and destination.stat().st_size == CLEAN_BYTES,
                'Existing clean Minecraft alias differs')
    else:
        destination.parent.mkdir(parents=True, exist_ok=True)
        with source.open('rb') as src, destination.open('xb') as dst:
            shutil.copyfileobj(src, dst)
    return {'source': files.pin(source), 'destination': files.pin(destination), 'contentChanged': False}


def command(root):
    return [sys.executable, '-B', str(files.canonical(root) / 'work/api1' / SOURCE / 'build.py')]


def execute(root, run_command, deadline):
    root = files.canonical(root)
    api = root / 'work/api1'
    require(not (api / SOURCE / 'build').exists(), 'Original Forge fixture must compile once into a fresh build directory')
    alias = clean_alias(root)
    before = verify_inputs(root)
    receipt = run_command(root, command(root), 'forge-fixture', 180, deadline)
    require(verify_inputs(root) == before, 'Original Forge fixture inputs changed during compilation')
    jar = api / SOURCE / 'build/unified-forge-probe-0.1.0.jar'
    require(files.sha(jar) == EXPECTED, 'Original Forge fixture did not reproduce exact accepted bytes')
    report_path = api / SOURCE / 'build/build-report.json'
    report = json.loads(report_path.read_text())
    require(report['sha256'] == EXPECTED and report['foreign_loader_reference_check'] == 'PASS' and
            report['required_abi_check'] == 'PASS', 'Original Forge source/ABI build checks failed')
    result = {'schema': 1, 'status': 'PASS_EXACT_SOURCE_BUILT_FORGE_FIXTURE',
              'inputLock': files.pin(root / SUPPORT / 'input-lock.json'), 'inputs': before,
              'cleanMinecraftAlias': alias, 'command': command(root), 'buildReceipt': files.pin(receipt),
              'artifact': files.pin(jar), 'sourceBuildReport': files.pin(report_path),
              'disassembly': files.pin(api / SOURCE / 'build/probe-javap.txt'),
              'perJvmHeapMiB': 512, 'activeProcessors': 1, 'workers': 1,
              'gameLaunched': False, 'clientRosterChanged': False}
    return files.save(root / SUPPORT / 'build-result.json', result)


def verify_result(root):
    root = files.canonical(root)
    path = root / SUPPORT / 'build-result.json'
    result = json.loads(path.read_text())
    require(result['status'] == 'PASS_EXACT_SOURCE_BUILT_FORGE_FIXTURE' and result['gameLaunched'] is False and
            result['inputs'] == verify_inputs(root) and result['command'] == command(root),
            'Fresh original Forge fixture receipt differs')
    for key in ('inputLock', 'buildReceipt', 'artifact', 'sourceBuildReport', 'disassembly'):
        row = result[key]
        current = files.canonical(row['path'])
        require(current.is_relative_to(root) and files.pin(current) == row, 'Original Forge fixture output binding changed')
    require(result['artifact']['sha256'] == EXPECTED, 'Original Forge fixture identity differs')
    receipt = json.loads(Path(result['buildReceipt']['path']).read_text())
    require(receipt['status'] == 'PASS' and receipt['exitCode'] == 0 and receipt['command'] == command(root) and
            receipt['gameTask'] is False and receipt['activeProcessors'] == 1 and receipt['workers'] == 1 and
            receipt['perJvmHeapMiB'] == 512 and files.sha(receipt['log']) == receipt['logSha256'],
            'Bounded original Forge fixture build receipt differs')
    return files.pin(path)
