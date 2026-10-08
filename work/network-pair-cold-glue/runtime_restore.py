#!/usr/bin/env python3
"""Consumer-local official NeoForge restoration/export glue; prepare never executes.

The serial owner executes returned commands only after its own reviewed CI policy
admits the run. This module does not import, modify, or bypass the old diagnostic
bootstrap's branch/workflow checks. It reuses its immutable 360 input records,
original probe source and actual Java codec assertions via an explicit derivative.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import importlib.util
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import sys
import urllib.parse
import xml.etree.ElementTree as ET
import zipfile

HERE = Path(__file__).resolve().parent
RUNTIME_LOCK = HERE / 'runtime-inputs.lock.json'
NONCE = 'work/network-probe-compile-ci/diagnostics/neoforge-nonce-compile'
CLIENT = 'work/api1/four-loader/api-contract-controls/client-development'
PUBLIC = 'portable-bootstrap/input-lock.json'
ASSET_LOCK = 'portable-bootstrap/client-restoration/client-assets-lock.json'
INDEX_LOCK = 'portable-bootstrap/client-restoration/client-index-lock.json'
JAVA_VERSION = '21.0.12.1+1'
GRADLE_VERSION = '8.11.1'
SOURCE_SHA = '65cf1c852d6e07226fcd7d2f66df8d202f3a6e70cd4d8f963c6dc40b28554909'
JAVA_SHA = '2a207f5e7d075afa01d97f8048389a64432a44c4a5af0f5e77d6e286ec5f401d'
REDIRECT_HOSTS = {'github.com', 'release-assets.githubusercontent.com',
                  'objects.githubusercontent.com', 'services.gradle.org',
                  'downloads.gradle.org', 'plugins.gradle.org', 'plugins-artifacts.gradle.org'}


def require(ok, message):
    if not ok:
        raise ValueError(message)


def identity(path):
    path = Path(path)
    require(path.is_file() and not path.is_symlink(), 'Not a regular input: ' + str(path))
    with path.open('rb') as stream:
        digest = hashlib.file_digest(stream, 'sha256').hexdigest()
    return {'bytes': path.stat().st_size, 'sha256': digest}


def pin(path):
    return {'path': str(Path(path)), **identity(path)}


def relative(value):
    path = PurePosixPath(value)
    require(value and not path.is_absolute() and '..' not in path.parts and str(path) == value,
            'Unsafe relative input path: ' + str(value))
    return path


def destination(root, value):
    result = root.joinpath(*relative(value).parts)
    require(result.resolve().is_relative_to(root.resolve()), 'Destination escapes consumer')
    return result


def save(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    require(not path.exists() and not path.is_symlink(), 'Refusing overwrite: ' + str(path))
    path.write_text(json.dumps(value, indent=2) + '\n')
    return pin(path)


def put(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    require(not path.exists() and not path.is_symlink(), 'Refusing overwrite: ' + str(path))
    path.write_text(text)
    return pin(path)


def load_sources(repo_root):
    meta = json.loads(RUNTIME_LOCK.read_text())
    for row in meta['sources']:
        source = destination(repo_root, row['path'])
        require(identity(source) == {k: row[k] for k in ('bytes', 'sha256')},
                'Pinned runtime source changed: ' + row['path'])
    return meta


def compile_path(value):
    for old, new in [('toolchains/', '.toolchains/'), ('maven/', 'ci/runtime-maven/'),
                     ('gradle-home/', 'source-workspace/gradle-cache/')]:
        if value.startswith(old):
            return new + value[len(old):]
    raise ValueError('Unknown original compile lock destination: ' + value)


def compose_lock(repo_root, meta):
    """Merge known immutable public pins; no binary reads, downloads or JVMs."""
    read = lambda name: json.loads(destination(repo_root, name).read_text())
    original = read(NONCE + '/dependency-lock.json')
    require(len(original['artifacts']) == 360 and original['totalBytes'] == 637208559
            and original['unresolvedParentMetadata'] == [], 'Original compile closure changed')
    rows = []
    for record in original['artifacts']:
        row = copy.deepcopy(record)
        row['path'] = compile_path(row['path'])
        row['also_seed'] = [compile_path(p) for p in row.get('also_seed', [])]
        row['phase'] = 'toolchains' if row['kind'] == 'toolchain' else 'moddev-inputs'
        row['originalCompilePin'] = record
        rows.append(row)
    for record in read(PUBLIC)['artifacts']:
        if record['phase'] != 'forge':
            rows.append(copy.deepcopy(record))
    rows += [copy.deepcopy(r) for r in read('portable-bootstrap/game-input-lock.json')['artifacts']
             if r['phase'] == 'minecraft-official']
    rows += copy.deepcopy(meta['supplementalArtifacts'])
    for name in (INDEX_LOCK, ASSET_LOCK):
        rows += copy.deepcopy(read(name)['artifacts'])
    # Same immutable Minecraft metadata feeds the official client installer.
    manifest = next(r for r in rows if r['path'].endswith('minecraft_1.21.1_version_manifest.json'))
    manifest.setdefault('also_seed', []).append('run/client-dev/versions/1.21.1/1.21.1.json')
    # SHA-1-only original records may join records with both official digests.
    sha1_to_sha256 = {r['sha1']: r['sha256'] for r in rows if 'sha1' in r and 'sha256' in r}
    url_to_sha256 = {u: r['sha256'] for r in rows if 'sha256' in r for u in r['urls']}
    for row in rows:
        if 'sha256' not in row:
            matches = {url_to_sha256[u] for u in row['urls'] if u in url_to_sha256}
            require(len(matches) <= 1, 'Conflicting official URL identity')
            if matches: row['sha256'] = matches.pop()
        if 'bytes' not in row and row.get('sha256') in meta['publicArtifactSizes']:
            row['bytes'] = meta['publicArtifactSizes'][row['sha256']]
    combined = {}
    destinations = {}
    for row in rows:
        if 'sha256' not in row and row.get('sha1') in sha1_to_sha256:
            row['sha256'] = sha1_to_sha256[row['sha1']]
        require(row.get('urls') and row.get('bytes', 0) > 0 and
                (re.fullmatch('[0-9a-f]{64}', row.get('sha256', '')) or
                 re.fullmatch('[0-9a-f]{40}', row.get('sha1', ''))), 'Unpinned artifact')
        key = ('sha256', row['sha256']) if 'sha256' in row else ('sha1', row['sha1'])
        for path in [row['path'], *row.get('also_seed', [])]:
            relative(path)
            previous = destinations.setdefault(path, key)
            require(previous == key, 'Conflicting artifact destination: ' + path)
        if key in combined:
            target = combined[key]
            require(target['bytes'] == row['bytes'], 'Same hash with inconsistent bytes')
            target['also_seed'] = sorted(set(target.get('also_seed', []) +
                                            [row['path'], *row.get('also_seed', [])]) - {target['path']})
            target['urls'] = list(dict.fromkeys(target['urls'] + row['urls']))
            if row.get('originalCompilePin'):
                target.setdefault('originalCompilePins', []).append(row['originalCompilePin'])
        else:
            combined[key] = row
    artifacts = list(combined.values())
    by_sha = {r.get('sha256'): r for r in artifacts if 'sha256' in r}
    missing = list(meta['missingOfficialInputs'])
    generated_server = []
    for record in meta['serverClosure']:
        public = by_sha.get(record['sha256'])
        if public:
            public['also_seed'] = sorted(set(public.get('also_seed', []) + [record['path']]) - {public['path']})
        elif record['origin'] == 'official-installer-generated':
            generated_server.append(record)
        else:
            missing.append({'path': record['path'], 'sha256': record['sha256'],
                            'bytes': record['bytes'], 'missing': 'official URL/hash download record'})
    generated_hashes = {r['sha256'] for r in meta['generatedDevelopmentOutputs']}
    for record in meta['clientClasspathIdentities']:
        if record['sha256'] not in by_sha and record['sha256'] not in generated_hashes:
            missing.append({**record, 'missing': 'official client classpath URL/hash record'})
    hosts = set(REDIRECT_HOSTS)
    for row in artifacts:
        for url in row['urls']:
            parsed = urllib.parse.urlsplit(url)
            require(parsed.scheme == 'https' and parsed.hostname and not parsed.username
                    and not parsed.password and parsed.port in (None, 443) and not parsed.fragment,
                    'Unsafe official URL: ' + url)
            hosts.add(parsed.hostname)
    require(len(read(ASSET_LOCK)['artifacts']) == 3888, 'Asset object closure changed')
    return {'schema': 1, 'rootPolicy': 'All paths relative to fresh consumer work/api1',
            'allowedHosts': sorted(hosts), 'artifacts': artifacts,
            'originalCompileRecords': 360, 'originalCompileBytes': original['totalBytes'],
            'totalDownloadBytes': sum(r['bytes'] for r in artifacts),
            'generatedFmlInputs': meta['generatedFmlInputs'],
            'generatedServerInputs': generated_server,
            'generatedDevelopmentOutputs': meta['generatedDevelopmentOutputs'],
            'additionalCleanOutput': meta['additionalCleanOutput'],
            'missingOfficialInputs': missing}


def build_environment(api):
    java_home = api / ('.toolchains/jdk-' + JAVA_VERSION)
    home = api / 'ci/build-home'
    return {'PATH': str(java_home / 'bin') + ':/usr/bin:/bin', 'JAVA_HOME': str(java_home),
            'GRADLE_USER_HOME': str(api / 'source-workspace/gradle-cache'), 'HOME': str(home),
            'LANG': 'C.UTF-8', 'LC_ALL': 'C.UTF-8', 'CI': 'true',
            'XDG_CACHE_HOME': str(api / 'ci/xdg-cache'),
            'XDG_CONFIG_HOME': str(api / 'ci/xdg-config'),
            '_JAVA_OPTIONS': '-Xmx512m -XX:ActiveProcessorCount=1 -Djava.awt.headless=true',
            'JAVA_TOOL_OPTIONS': '-Duser.home=' + str(home),
            'RUNTIME_API_ROOT': str(api)}


def gradle_command(api, project, init, tasks):
    return [str(api / ('.toolchains/gradle-' + GRADLE_VERSION + '/bin/gradle')),
            '--offline', '--no-daemon', '--no-parallel', '--max-workers=1', '--no-build-cache',
            '--no-configuration-cache', '--console=plain', '--dependency-verification=strict',
            '-Dorg.gradle.jvmargs=-Xmx512m -XX:ActiveProcessorCount=1 -Dfile.encoding=UTF-8',
            '-Dorg.gradle.workers.max=1', '-Dorg.gradle.parallel=false',
            '-Dorg.gradle.java.installations.auto-download=false', '--project-cache-dir',
            str(project / '.project-cache'), '--init-script', str(init), '-p', str(project), *tasks]


def verification_metadata(repo, output, meta):
    # The complete original strict metadata already includes DevLaunch; the
    # 360-row download subset omitted it because compilation never needed it.
    # Verify its three pins and preserve the whole XML byte-for-byte.
    source = repo / NONCE / 'probe/gradle/verification-metadata.xml'
    ns = {'v': 'https://schema.gradle.org/dependency-verification'}
    root = ET.parse(source).getroot()
    components = [c for c in root.findall('v:components/v:component', ns)
                  if (c.get('group'), c.get('name'), c.get('version')) ==
                     ('net.neoforged', 'DevLaunch', '1.0.2')]
    require(len(components) == 1, 'Expected one originally verified DevLaunch component')
    verified = {a.get('name'): {h.get('value') for h in a.findall('v:sha256', ns)}
                for a in components[0].findall('v:artifact', ns)}
    for row in meta['supplementalArtifacts']:
        if row.get('coordinate') == 'net.neoforged:DevLaunch:1.0.2':
            require(row['sha256'] in verified.get(Path(row['path']).name, set()),
                    'DevLaunch differs from unchanged original strict verification metadata')
    put(output, source.read_text())


INIT = '''import groovy.json.JsonSlurper
import java.security.MessageDigest

def api = new File(System.getenv('RUNTIME_API_ROOT'))
def mirror = new File(api, 'ci/runtime-maven').toURI()
def lock = new JsonSlurper().parse(new File(api, 'ci/runtime-restore/input-lock.json'))
settingsEvaluated { settings ->
    settings.pluginManagement.repositories.clear()
    settings.pluginManagement.repositories.maven { url = mirror }
}
allprojects {
    buildscript.repositories.clear()
    buildscript.repositories.maven { url = mirror }
    afterEvaluate { repositories.clear(); repositories.maven { url = mirror } }
    tasks.withType(JavaCompile).configureEach {
        options.forkOptions.memoryMaximumSize = '512m'
        options.forkOptions.jvmArgs = ['-XX:ActiveProcessorCount=1']
    }
    tasks.withType(JavaExec).configureEach {
        // runClient is only read by prepareClientLaunch; its exported VM recipe
        // remains 1280 MiB / two CPUs. The task graph below prohibits execution.
        if (name != 'runClient') { maxHeapSize = '512m'; jvmArgs '-XX:ActiveProcessorCount=1' }
    }
    tasks.withType(Test).configureEach {
        maxHeapSize = '512m'; maxParallelForks = 1; jvmArgs '-XX:ActiveProcessorCount=1'
    }
    tasks.matching { it.name == 'createMinecraftArtifacts' }.configureEach {
        doLast {
            lock.generatedDevelopmentOutputs.each { pin ->
                def artifact = new File(layout.buildDirectory.get().asFile, pin.path.substring(6))
                if (!artifact.isFile() || artifact.length() != pin.bytes ||
                    MessageDigest.getInstance('SHA-256').digest(artifact.bytes).encodeHex().toString() != pin.sha256)
                    throw new GradleException('Generated official output differs: ' + pin.path)
            }
        }
    }
}
gradle.taskGraph.whenReady { graph ->
    def permitted = [':createMinecraftArtifacts', ':compileJava', ':processResources', ':classes',
                     ':writeClientLegacyClasspath', ':prepareClientRun', ':prepareClientLaunch'] as Set
    def actual = graph.allTasks.collect { it.path } as Set
    if (!(actual - permitted).empty || !actual.contains(':prepareClientLaunch'))
        throw new GradleException('Unexpected client preparation task graph: ' + actual.sort())
    println('BOUNDED_CLIENT_PREPARATION_GRAPH: ' + actual.sort().join(','))
}
'''


def prepare(repo_root, consumer_root):
    """Stage text, exact pins and recipes only. Caller owns authorized execution."""
    repo = Path(repo_root).resolve(strict=True)
    consumer = Path(consumer_root)
    require(consumer.is_absolute() and consumer.resolve() == consumer, 'Canonical consumer root required')
    require(consumer != repo and not consumer.is_relative_to(repo / 'work/api1') and not repo.is_relative_to(consumer),
            'Consumer must not overwrite canonical inputs')
    require(not any(c in str(consumer) for c in ('\n', '\r', "'", '\\', ' ')),
            'Consumer path must support exact Gradle/Java property literals')
    meta = load_sources(repo)
    lock = compose_lock(repo, meta)
    api = consumer / 'work/api1'
    support = api / 'ci/runtime-restore'
    require(not support.exists(), 'Runtime preparation already exists; use its sealed plan')
    support.mkdir(parents=True)
    save(support / 'input-lock.json', lock)
    save(support / 'runtime-inputs.lock.json', meta)
    original_compile = json.loads((repo / NONCE / 'dependency-lock.json').read_text())
    put(support / 'original-nonce-dependency-lock.json', (repo / NONCE / 'dependency-lock.json').read_text())
    for name in ('restore_inputs.py', 'prepare_toolchains.py'):
        put(support / name, (repo / 'portable-bootstrap' / name).read_text())
    project = api / 'four-loader/api-contract-controls/client-development'
    for name in ('settings.gradle', 'build.gradle'):
        # The existing exporter already uses project-relative output locations.
        # Preserving its exact source bytes naturally relocates every generated
        # path when the same consumer-local directory topology is reproduced.
        put(project / name, (repo / CLIENT / name).read_text())
    verification_metadata(repo, project / 'gradle/verification-metadata.xml', meta)
    put(support / 'client.init.gradle', INIT)
    client = api / 'run/api1-unified-client-build'
    assets_properties = client / 'build/moddev/minecraft_assets.properties'
    put(assets_properties,
        'asset_index=17\nassets_root=' + str(api / 'run/client-dev/assets') + '\n')
    put(api / 'run/client-dev/launcher_profiles.json', '{"profiles":{},"settings":{}}\n')
    for path in (api / 'run/client-dev/installer-work', api / 'run/neoforge-native/installer-work',
                 api / 'ci/build-home', api / 'ci/xdg-cache', api / 'ci/xdg-config'):
        path.mkdir(parents=True, exist_ok=True)
    seal_source = (repo / 'portable-bootstrap/client-restoration/seal_official_client.py').read_text()
    old = "HERE=pathlib.Path(__file__).resolve().parent;ROOT=HERE.parent.parent/'work/api1';PROFILE=ROOT/'run/api1-unified-client-build'"
    new = "HERE=pathlib.Path(__file__).resolve().parent;ROOT=HERE.parent.parent;PROFILE=ROOT/'run/api1-unified-client-build'"
    require(seal_source.count(old) == 1, 'Known official seal source changed')
    seal_source = seal_source.replace(old, new)
    # Source materializer places the original assembler under this same API
    # root, so its existing source-workspace-relative import stays unchanged.
    seal_source = seal_source.replace(
        "'compiledSourceTuple':'portable-bootstrap/manifest-main-candidate/candidate-seal.json'",
        "'compiledSourceTuple':None")
    put(support / 'seal_official_client.py', seal_source)
    environment = build_environment(api)
    java = str(api / ('.toolchains/jdk-' + JAVA_VERSION + '/bin/java'))
    installer = str(api / 'docs/research/upstream/neoforge-21.1.219-installer.jar')
    steps = [{'name': 'extract-toolchains', 'command': [sys.executable, str(support / 'prepare_toolchains.py'),
              '--root', str(api)], 'cwd': str(api), 'environment': environment, 'timeoutSeconds': 180}]
    for name, root, flag in [('installer-client', 'run/client-dev', '--installClient'),
                             ('installer-native-server', 'run/neoforge-native', '--installServer')]:
        steps.append({'name': name, 'command': [java, '-Xmx512m', '-XX:ActiveProcessorCount=1',
                      '-jar', installer, flag, str(api / root)],
                      'cwd': str(api / root / 'installer-work'), 'environment': environment,
                      'timeoutSeconds': 1800, 'requiresExternalExecutionPolicy': True})
    steps.append({'name': 'export-official-client',
                  'command': gradle_command(api, project, support / 'client.init.gradle',
                                            ['prepareClientLaunch', '-x', 'downloadAssets']),
                  'cwd': str(project), 'environment': environment, 'timeoutSeconds': 1800,
                  'requiresExternalExecutionPolicy': True})
    steps.append({'name': 'seal-official-client', 'command': [sys.executable, str(support / 'seal_official_client.py')],
                  'cwd': str(api), 'environment': environment, 'timeoutSeconds': 120})
    result = {'schema': 'consumer-runtime-prepare-v1', 'status': 'SOURCE_STAGED_EXECUTION_UNVERIFIED',
              'consumerRoot': str(consumer), 'apiRoot': str(api), 'supportRoot': str(support),
              'javaHome': str(api / ('.toolchains/jdk-' + JAVA_VERSION)),
              'gradleHome': str(api / ('.toolchains/gradle-' + GRADLE_VERSION)),
              'gradleUserHome': str(api / 'source-workspace/gradle-cache'),
              'mavenRoot': str(api / 'ci/runtime-maven'),
              'nonceCompileInputs': {'originalLock': str(support / 'original-nonce-dependency-lock.json'),
                  'seedRoot': str(api), 'mavenRoot': str(api / 'ci/runtime-maven'),
                  'nfrtArtifactsRoot': str(api / 'source-workspace/gradle-cache/caches/neoformruntime/artifacts'),
                  'records': [{'originalPath': r['path'], 'consumerPath': str(api / compile_path(r['path'])),
                               'alsoSeed': [str(api / compile_path(v)) for v in r.get('also_seed', [])]}
                              for r in original_compile['artifacts']]},
              'assetsRoot': str(api / 'run/client-dev/assets'),
              'clientExport': str(client / 'client-launch-inputs.json'),
              'clientSeal': str(client / 'official-client-launch-seal.json'),
              'nativeServerRoot': str(api / 'run/neoforge-native'),
              'nativeServerClosure': str(support / 'native-server-closure.json'),
              'runtimeReceipt': str(support / 'runtime-result.json'),
              'restoreCallable': 'runtime_restore.restore(apiRoot)',
              'verifyCallable': 'runtime_restore.verify(apiRoot)',
              'beforeJvmCallable': 'runtime_restore.verify_inputs(apiRoot)',
              'steps': steps, 'missingOfficialInputs': lock['missingOfficialInputs'],
              'unverifiedExecution': meta['unverifiedExecution'],
              'inputArtifacts': len(lock['artifacts']), 'inputBytes': lock['totalDownloadBytes'],
              'jvmStarted': False, 'gameLaunched': False, 'downloadsStarted': False}
    result['preparationFiles'] = [pin(p) for p in sorted(support.rglob('*')) if p.is_file()]
    result['preparationFiles'].append(pin(assets_properties))
    result['preparationFiles'] += [pin(project / name) for name in
                                   ('build.gradle', 'settings.gradle', 'gradle/verification-metadata.xml')]
    save(support / 'runtime-plan.json', result)
    return result


def verify_preparation(api):
    plan = json.loads((api / 'ci/runtime-restore/runtime-plan.json').read_text())
    require(plan['apiRoot'] == str(api), 'Plan belongs to another consumer root')
    for row in plan['preparationFiles']:
        path = Path(row['path'])
        require(path.resolve() == path and path.is_relative_to(api), 'Preparation input escapes consumer')
        require(identity(path) == {k: row[k] for k in ('bytes', 'sha256')},
                'Consumer preparation source changed: ' + str(path))
    return plan


def restore(api_root):
    """Explicit future execution hook, never called by prepare or static checks."""
    api = Path(api_root).resolve(strict=True)
    support = api / 'ci/runtime-restore'
    verify_preparation(api)
    lock = json.loads((support / 'input-lock.json').read_text())
    require(not lock['missingOfficialInputs'], 'Missing official input records')
    spec = importlib.util.spec_from_file_location('consumer_pinned_restore', support / 'restore_inputs.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    records = []
    for restored_index, row in enumerate(lock['artifacts'], 1):
        # The original downloader enforces byte ceilings, exact hashes, official
        # HTTPS origins/redirects and bounded retries. One download runs at a time.
        records.append(module.restore(api, row, set(lock['allowedHosts'])))
        for alias in row.get('also_seed', []):
            target = destination(api, alias)
            target.parent.mkdir(parents=True, exist_ok=True)
            if target.exists():
                module.validate(target, row)
            else:
                shutil.copyfile(destination(api, row['path']), target)
                module.validate(target, row)
        if restored_index % 64 == 0 or restored_index == len(lock['artifacts']):
            print('OFFICIAL_RUNTIME_INPUTS_VERIFIED: ' + str(restored_index) + '/' + str(len(lock['artifacts'])), flush=True)
    result = verify_inputs(api)
    result['restoredArtifacts'] = len(records)
    save(support / 'restore-result.json', result)
    return result


def verify_inputs(api_root):
    api = Path(api_root).resolve(strict=True)
    verify_preparation(api)
    lock = json.loads((api / 'ci/runtime-restore/input-lock.json').read_text())
    require(not lock['missingOfficialInputs'], 'Missing official input records')
    expected_nfrt = set()
    expected_mirror = set()
    mirror = api / 'ci/runtime-maven'
    nfrt = api / 'source-workspace/gradle-cache/caches/neoformruntime/artifacts'
    count = 0
    for row in lock['artifacts']:
        for name in [row['path'], *row.get('also_seed', [])]:
            path = destination(api, name)
            require(path.is_file() and not path.is_symlink() and path.stat().st_size == row['bytes'],
                    'Missing/changed official input: ' + name)
            for algorithm in ('sha256', 'sha1'):
                if algorithm in row:
                    with path.open('rb') as stream:
                        actual = hashlib.file_digest(stream, algorithm).hexdigest()
                    require(actual == row[algorithm], 'Changed ' + algorithm + ': ' + name)
            if path.is_relative_to(nfrt):
                expected_nfrt.add(str(path.relative_to(nfrt)))
            if path.is_relative_to(mirror):
                expected_mirror.add(str(path.relative_to(mirror)))
            count += 1
    actual_nfrt = {str(p.relative_to(nfrt)) for p in nfrt.rglob('*') if p.is_file()}
    require(actual_nfrt == expected_nfrt, 'Unexpected NFRT public input closure')
    actual_mirror = {str(p.relative_to(mirror)) for p in mirror.rglob('*') if p.is_file()}
    require(actual_mirror == expected_mirror, 'Unexpected Maven mirror input closure')
    index = json.loads((api / 'run/client-dev/assets/indexes/17.json').read_text())
    expected_assets = {r['sha1'] for r in lock['artifacts'] if r['phase'] == 'client-assets'}
    index_assets = {r['hash'] for r in index['objects'].values()}
    require(expected_assets == index_assets and len(index_assets) == 3888,
            'Pinned asset objects do not cover the original index')
    return {'status': 'VERIFIED_PUBLIC_INPUTS_ONLY', 'filesVerified': count,
            'inputLock': pin(api / 'ci/runtime-restore/input-lock.json'),
            'networkIsolationClaimed': False, 'gameLaunched': False}


def verify(api_root):
    """Verify actual outputs after the owner executes every serial build step."""
    api = Path(api_root).resolve(strict=True)
    support = api / 'ci/runtime-restore'
    meta = json.loads((support / 'runtime-inputs.lock.json').read_text())
    public = verify_inputs(api)
    java = api / ('.toolchains/jdk-' + JAVA_VERSION + '/bin/java')
    require(identity(java)['sha256'] == JAVA_SHA, 'Approved Java identity differs')
    generated = []
    for row in [*meta['generatedFmlInputs'], *meta['serverClosure']]:
        path = destination(api, row['path'])
        require(identity(path) == {k: row[k] for k in ('bytes', 'sha256')},
                'Official installer output differs: ' + row['path'])
        generated.append(pin(path))
    client = api / 'run/api1-unified-client-build'
    for row in [*meta['generatedDevelopmentOutputs'], meta['additionalCleanOutput']]:
        path = destination(client, row['path'])
        require(identity(path) == {k: row[k] for k in ('bytes', 'sha256')},
                'Official ModDev output differs: ' + row['path'])
        generated.append(pin(path))
    export = json.loads((client / 'client-launch-inputs.json').read_text())
    require(export['environment'] == {} and export['gameLaunched'] is False
            and export['mainClass'] == 'net.neoforged.devlaunch.Main', 'Unexpected official client export')
    expected = {(r['name'], r['sha256']) for r in meta['clientClasspathIdentities']}
    actual = {(Path(r['path']).name, r['sha256']) for r in export['inputs']}
    require(actual == expected and len(export['inputs']) == 95, 'Client classpath identity closure changed')
    for row in export['inputs']:
        path = Path(row['path'])
        require(path.is_absolute() and path.resolve() == path and path.is_relative_to(api),
                'Client export escapes consumer')
        require(identity(path)['sha256'] == row['sha256'], 'Client input changed')
    seal = json.loads((client / 'official-client-launch-seal.json').read_text())
    require(seal['gameLaunched'] is False and seal['heapMiB'] == 1280 and seal['activeProcessors'] == 2,
            'Exported game recipe differs')
    for row in seal['files']:
        path = Path(row['path'])
        require(path.is_absolute() and path.resolve() == path and path.is_relative_to(api),
                'Client seal escapes consumer')
        if row.get('kind') == 'declared-empty-source-output':
            require(not path.exists() or (path.is_dir() and not any(path.iterdir())),
                    'Unexpected project implementation root')
        else:
            require(identity(path)['sha256'] == row['sha256'], 'Sealed client input changed')
    server = {'schema': 1, 'status': 'OFFICIAL_NATIVE_SERVER_CLOSURE_VERIFIED',
              'root': str(api / 'run/neoforge-native'), 'runtime_files':
              [pin(destination(api, row['path'])) for row in meta['serverClosure']],
              'argfile': str(api / 'run/neoforge-native/libraries/net/neoforged/neoforge/21.1.219/unix_args.txt'),
              'gameLaunched': False}
    save(support / 'native-server-closure.json', server)
    result = {'schema': 1, 'status': 'OFFICIAL_RUNTIME_PREPARED_GAME_UNRUN',
              'publicInputClosure': public, 'generatedOutputs': generated,
              'nativeServerClosure': pin(support / 'native-server-closure.json'),
              'clientExport': pin(client / 'client-launch-inputs.json'),
              'clientSeal': pin(client / 'official-client-launch-seal.json'),
              'assetObjectsVerified': 3888, 'fmlGeneratedOutputs': 4,
              'developmentGeneratedOutputs': 2, 'additionalCleanOutputVerified': True,
              'nativeServerFiles': 95, 'gameLaunched': False, 'networkAcceptance': False}
    save(support / 'runtime-result.json', result)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=['check', 'prepare'])
    parser.add_argument('--repo-root', type=Path, required=True)
    parser.add_argument('--consumer-root', type=Path)
    args = parser.parse_args()
    if args.command == 'check':
        meta = load_sources(args.repo_root.resolve(strict=True))
        lock = compose_lock(args.repo_root.resolve(strict=True), meta)
        print(json.dumps({'status': 'SOURCE_CHECKED_EXECUTION_UNVERIFIED',
                          'artifactRecords': len(lock['artifacts']), 'downloadBytes': lock['totalDownloadBytes'],
                          'originalCompileRecords': 360, 'serverFiles': len(meta['serverClosure']),
                          'clientClasspathInputs': len(meta['clientClasspathIdentities']),
                          'missingOfficialInputs': lock['missingOfficialInputs'],
                          'unverifiedExecution': meta['unverifiedExecution'],
                          'jvmStarted': False, 'downloadsStarted': False}, indent=2))
    else:
        require(args.consumer_root is not None, '--consumer-root required for source staging')
        print(json.dumps(prepare(args.repo_root, args.consumer_root), indent=2))


if __name__ == '__main__':
    main()
