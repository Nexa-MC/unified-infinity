#!/usr/bin/env python3
"""Bounded portable base build followed by the proven FML metadata source overlay."""
import argparse
import datetime
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import time
import zipfile
import bounded_process
import fml_metadata
import forge_fixture

VERSION = '2.0.0-beta.17+1.21.1+infinity-source+api1-emi-render-integration'
IDENTITY = fml_metadata.BASE_IDENTITY
CANDIDATE_IDENTITY = fml_metadata.CANDIDATE_IDENTITY
EXTRA = '24a5d2d162cfad2a1a574c4d552e99dc6c6303a49d1e68b43a7b638f3b0930fd'
ORIGINALS = {'sophisticatedcore-1.21.1-1.4.11.1553.jar': 'acafbe72eb161b0b763feb61eba06584e97e48f563de75f767611ee520dfcad7',
             'sophisticatedbackpacks-1.21.1-3.25.34.1604.jar': '889fb2af58e9f7951d0553033a856078b28fcdf802ca13eb432336b2b7b9780c'}
BASE_EXPECTED = {'service': '7fbabf5eb18b590bd5a30410d076fd814f11d03e8842e3327b4468217e275aa7',
                 'game': '9dc29ac8a8030f629dd7afea8b744114504a552c4fce022c6199b23a1024e162',
                 'fml': fml_metadata.BASE_FML_SHA,
                 'product': 'b20903f821455682ff5fee62491483e833252dc1a4f4caaa15bef51a356f1409'}
EXPECTED = dict(BASE_EXPECTED, fml=fml_metadata.FIXED_FML_SHA)


def require(value, message):
    if not value:
        raise ValueError(message)


def sha(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def save(path, value):
    require(not path.exists(), 'Refusing overwrite: ' + str(path))
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('x') as stream:
        json.dump(value, stream, indent=2)
        stream.write('\n')


def layout(consumer):
    root = fml_metadata.canonical(consumer)
    require(root.is_dir(), 'Existing consumer required')
    api = root / 'work/api1'
    candidate = root / 'work/emi-render-integration'
    return root, api, candidate, api / 'source-workspace/connector-four-loader'


def plan(consumer):
    root, api, candidate, core = layout(consumer)
    support = root / fml_metadata.SUPPORT
    jdk = api / '.toolchains/jdk-21.0.12.1+1'
    common = [str(api / '.toolchains/gradle-8.11.1/bin/gradle'), '--offline', '--no-daemon',
              '--no-parallel', '--max-workers=1', '--no-build-cache', '--no-configuration-cache',
              '--console=plain', '--dependency-verification=strict',
              '-Dorg.gradle.jvmargs=-Xmx512m -XX:ActiveProcessorCount=1 -Dfile.encoding=UTF-8',
              '-Dorg.gradle.java.installations.auto-download=false',
              '-Dorg.gradle.java.installations.auto-detect=false',
              '-Dorg.gradle.java.installations.paths=' + str(jdk)]
    base = [*common, '--init-script', str(candidate / 'bounded-build.init.gradle'),
            '--init-script', str(support / 'cold-repositories.init.gradle'),
            '--init-script', str(support / 'verified-repositories.init.gradle'),
            '--init-script', str(support / 'archive-permissions.init.gradle')]
    mods = root / 'complex-mod-research'
    arguments = ['-PemiCoreJar=' + str(mods / next(n for n in ORIGINALS if 'core' in n)),
                 '-PemiBackpackJar=' + str(mods / next(n for n in ORIGINALS if 'backpacks' in n)),
                 ':fml-unified:jar', ':fml-unified:sourcesJar', 'fullJar', 'check', 'writeProductCompileInputs']
    return {'schema': 2, 'consumerRoot': str(root), 'apiRoot': str(api), 'candidateRoot': str(candidate),
            'forgeFixtureCommand': forge_fixture.command(root),
            'forgeFixtureExpectedSha256': forge_fixture.EXPECTED,
            'coreCommand': [*base, '--project-cache-dir', str(candidate / 'cold-core-cache'), '-p', str(core), *arguments],
            'productCommandPrefix': [*base, '--init-script', str(support / 'product-payload-permissions.init.gradle'),
                                     '--rerun-tasks', '--project-cache-dir', str(candidate / 'cold-product-cache'),
                                     '-p', str(api / 'runtime-bundle')],
            'fmlCommand': [*common, '--gradle-user-home', str(root / fml_metadata.AREA / 'gradle-user-home'),
                           '--project-cache-dir', str(root / fml_metadata.AREA / 'project-cache'),
                           '--init-script', str(support / 'fml/bounded-build.init.gradle'),
                           '-p', str(root / fml_metadata.PROJECT), 'jar', 'sourcesJar'],
            'perJvmHeapMiB': 512, 'processorsPerBuildJvm': 1, 'workers': 1, 'fmlCompilerHeapMiB': 192,
            'gameTask': False, 'baseSourceIdentity': IDENTITY, 'expectedCandidateIdentity': CANDIDATE_IDENTITY,
            'candidateIdentityKind': 'reviewed-artifact-equivalence-reference',
            'expectedBaseArtifacts': BASE_EXPECTED, 'expectedArtifacts': EXPECTED,
            'supportManifestSha256': fml_metadata.SUPPORT_MANIFEST_SHA}


def prepare(consumer, profile=None):
    if profile is not None:
        return prepare_refreshed(consumer, profile)
    root, api, candidate, core = layout(consumer)
    source = fml_metadata.prepare(root)
    fixture_source = forge_fixture.prepare(root)
    result = plan(root)
    result.update(status='BUILD_PLAN_PREPARED_NOT_EXECUTED', fmlSourcePreparation=source,
                  forgeFixtureSourcePreparation=fixture_source,
                  repositoryAdapterSha256=sha(root / fml_metadata.SUPPORT / 'cold-repositories.init.gradle'))
    save(candidate / 'cold-build-plan.json', result)
    return result


def command(consumer, argv, name, timeout, deadline=None):
    root, api, candidate, core = layout(consumer)
    jdk = api / '.toolchains/jdk-21.0.12.1+1'
    env = {'PATH': str(jdk / 'bin') + ':/usr/bin:/bin', 'JAVA_HOME': str(jdk),
           'HOME': str(api / 'source-workspace/home'), 'GRADLE_USER_HOME': str(api / 'source-workspace/gradle-cache'),
           'XDG_CACHE_HOME': str(api / 'source-workspace/xdg-cache'), 'XDG_CONFIG_HOME': str(api / 'source-workspace/xdg-config'),
           'LANG': 'C.UTF-8', 'LC_ALL': 'C.UTF-8', 'TZ': 'UTC', 'CI': 'true', 'PUBLISH_RELEASE_TYPE': 'alpha',
           'PAIR_API_ROOT': str(api), 'PAIR_MAVEN_MIRROR': str(api / 'ci/runtime-maven'),
           'PAIR_CORE_MAVEN': str(api / 'source-workspace/pinned-build-maven'),
           'FORGE_FACADE_HOST_LIBRARIES': str(api / 'run/neoforge-native/libraries'),
           '_JAVA_OPTIONS': '-Xmx512m -XX:ActiveProcessorCount=1 -Dfile.encoding=UTF-8',
           'JAVA_TOOL_OPTIONS': '-Duser.home=' + str(api / 'source-workspace/home')}
    if name == 'fml-logging-v3':
        env['HOME'] = str(root / fml_metadata.AREA / 'build-home')
        env['GRADLE_USER_HOME'] = str(root / fml_metadata.AREA / 'gradle-user-home')
        env['JAVA_TOOL_OPTIONS'] = '-Duser.home=' + env['HOME']
        # Enforce one CPU after every project JVM flag, without overriding
        # the recovered recipe's explicit 192 MiB javac heap.
        env['_JAVA_OPTIONS'] = '-XX:ActiveProcessorCount=1'
        env['JAVA_OPTS'] = '-Xmx64m -XX:ActiveProcessorCount=1'
    for key in ('HOME', 'GRADLE_USER_HOME', 'XDG_CACHE_HOME', 'XDG_CONFIG_HOME'):
        Path(env[key]).mkdir(parents=True, exist_ok=True)
    evidence = candidate / 'cold-evidence'
    evidence.mkdir(exist_ok=True)
    log, receipt = evidence / (name + '.log'), evidence / (name + '.json')
    require(not log.exists() and not receipt.exists(), 'Refusing repeated cold build receipt')
    started = datetime.datetime.now(datetime.timezone.utc).isoformat()
    require(deadline is not None and deadline > time.monotonic(), 'Shared build deadline is required and must not be expired')
    timeout = min(timeout, deadline - time.monotonic())
    with log.open('x') as output:
        result = bounded_process.run(argv, cwd=api, env=env, stdout=output, stderr=subprocess.STDOUT, timeout=timeout)
    value = {'schema': 1, 'status': 'PASS' if result.returncode == 0 else 'FAILED', 'exitCode': result.returncode,
             'startedUtc': started, 'finishedUtc': datetime.datetime.now(datetime.timezone.utc).isoformat(),
             'command': argv, 'log': str(log), 'logSha256': sha(log), 'perJvmHeapMiB': 512,
             'activeProcessors': 1, 'workers': 1, 'timeoutSeconds': timeout, 'gameTask': False}
    save(receipt, value)
    if result.returncode != 0:
        print(log.read_text(errors='replace')[-48000:], flush=True)
    require(result.returncode == 0, 'Cold build failed; preserved log ' + str(log))
    return receipt


def capture_core(consumer):
    root, api, candidate, core = layout(consumer)
    expected = json.loads((candidate / 'build-identity.json').read_text())
    generated = json.loads((core / 'components/infinity-core/build/generated/resources/infinity/META-INF/unified-infinity/build-identity.json').read_text())
    require(generated == expected and generated['identity_sha256'] == IDENTITY,
            'Base source/dependency/compiler identity changed before the explicit FML overlay')
    paths = {'service': core / f'build/libs/connector-{VERSION}-full.jar',
             'game': core / f'build/libs/connector-{VERSION}-mod.jar',
             'fml': api / 'source-workspace/fml-unified/build/libs/fml-loader-4.0.42-unified-source.jar'}
    rows = {role: {'path': str(path), 'sha256': sha(path)} for role, path in paths.items()}
    for role, row in rows.items():
        require(row['sha256'] == BASE_EXPECTED[role], 'Base output differs from reviewed bytes: ' + role)
    save(candidate / 'cold-built-core-artifacts.json', rows)
    return rows


def inspect_tuple(paths, expected):
    artifacts, entries, owners, packages = {}, {}, {}, {}
    require(set(paths) == set(expected), 'Unexpected source tuple roles')
    for role, path in paths.items():
        require(sha(path) == expected[role], 'Exact tuple artifact differs: ' + role)
        artifacts[role] = {'path': str(path), 'sha256': sha(path)}
        with zipfile.ZipFile(path) as archive:
            names = [n for n in archive.namelist() if not n.endswith('/')]
            require(len(names) == len(set(names)), 'Duplicate archive entry')
            entries[role] = {n: hashlib.sha256(archive.read(n)).hexdigest() for n in names}
            for name in names:
                if name.endswith('.class'):
                    require(name not in owners, 'Duplicate top-level class owner')
                    owners[name] = role
                    packages.setdefault(name.rsplit('/', 1)[0], set()).add(role)
    require(all(len(value) == 1 for value in packages.values()), 'Split top-level package')
    return artifacts, entries


def execute(consumer, deadline=None, profile=None):
    if profile is not None:
        return execute_refreshed(consumer, profile, deadline)
    require(os.environ.get('GITHUB_ACTIONS') == 'true' and os.environ.get('GITHUB_REPOSITORY') == 'Nexa-MC/unified-infinity'
            and os.environ.get('GITHUB_REF') == 'refs/heads/diagnostic/network-pair-20261006-a',
            'Actual execution requires the separately reviewed future pair diagnostic branch')
    # A standalone invocation owns one total budget; a driver passes its already
    # running deadline, so no phase can reset or extend the shared 42 minutes.
    if deadline is None:
        deadline = time.monotonic() + 42 * 60
    root, api, candidate, core = layout(consumer)
    recipe = json.loads((candidate / 'cold-build-plan.json').read_text())
    require(all(recipe.get(key) == value for key, value in plan(root).items()), 'Prepared build plan changed')
    source_before = fml_metadata.verify_sources(root)
    prepared = json.loads((root / fml_metadata.AREA / 'source-preparation.json').read_text())
    require(all(prepared.get(key) == value for key, value in source_before.items()), 'Prepared FML sources changed')
    dependencies, official_fml = fml_metadata.verify_dependencies(root)
    for name, digest in ORIGINALS.items():
        require(sha(root / 'complex-mod-research' / name) == digest, 'Changed original regression fixture')
    relative = Path('libraries/net/minecraft/server/1.21.1-20240808.144430/server-1.21.1-20240808.144430-extra.jar')
    official = api / 'run/neoforge-native' / relative
    require(sha(official) == EXTRA, 'Server manifest regression input differs')
    fixture = api / 'run/api1-unified-server-2' / relative
    if fixture.exists():
        require(sha(fixture) == EXTRA, 'Existing regression fixture differs')
    else:
        fixture.parent.mkdir(parents=True, exist_ok=True)
        with official.open('rb') as source, fixture.open('xb') as target:
            shutil.copyfileobj(source, target)
    fixture_result = forge_fixture.execute(root, command, deadline)
    core_receipt = command(root, recipe['coreCommand'], 'core', 1200, deadline)
    rows = capture_core(root)
    manifest = api / 'run/client-dev/development-build/moddev/client-launch-inputs.json'
    data = json.loads(manifest.read_text())
    for row in data['inputs']:
        require(sha(Path(row['path'])) == row['sha256'], 'PRODUCT compile manifest input differs')
    require(os.access(api / 'tools/java-env.sh', os.X_OK), 'Pinned java-env.sh must retain executable mode')
    args = [*recipe['productCommandPrefix'], '-PmanagedCoreJar=' + rows['service']['path'],
            '-PmanagedCoreSha256=' + rows['service']['sha256'], '-PunifiedFmlJar=' + rows['fml']['path'],
            '-PffapiJar=' + str(api / 'docs/research/upstream/ffapi-baseline.jar'),
            '-PqslInventory=' + str(api / 'docs/four-loader/quilt/bundled-tooltip.json'),
            '-PclientClasspathManifest=' + str(manifest), 'jar', 'sourcesJar', 'check']
    product_receipt = command(root, args, 'product', 600, deadline)
    paths = {role: Path(row['path']) for role, row in rows.items()}
    paths['product'] = api / 'runtime-bundle/build/libs/unified-infinity-0.1.0-dev.jar'
    inspect_tuple(paths, BASE_EXPECTED)
    # Preserve all verified base outputs separately before compiling the overlay.
    historical = {}
    for role, path in paths.items():
        dest = candidate / 'cold-base-artifacts' / (role + '.jar')
        dest.parent.mkdir(exist_ok=True)
        with path.open('rb') as source, dest.open('xb') as target:
            shutil.copyfileobj(source, target)
        historical[role] = {'path': str(dest), 'sha256': sha(dest)}
    save(candidate / 'cold-base-tuple-artifacts.json', historical)
    base = json.loads((candidate / 'fml-base-build-receipt.json').read_text())
    for name, digest in base['sources'].items():
        require(sha(api / 'source-workspace' / name) == digest, 'Historical FML source receipt differs')
    require(base['sha256'] == historical['fml']['sha256'], 'Compiled FML base differs')
    base.update(artifact=historical['fml']['path'], sourceBuildReceipt=str(core_receipt),
                buildKind='Fresh bounded full-source base build; game unrun')
    save(candidate / 'cold-historical-fml-base-build-receipt.json', base)
    fml_receipt = command(root, recipe['fmlCommand'], 'fml-logging-v3', 600, deadline)
    require(fml_metadata.verify_sources(root) == source_before, 'FML sources changed during compilation')
    require(fml_metadata.verify_dependencies(root) == (dependencies, official_fml), 'FML dependencies changed during compilation')
    fixed = root / fml_metadata.PROJECT / 'build/libs/fml-loader-4.0.42-unified-source.jar'
    source_jar = fixed.with_name('fml-loader-4.0.42-unified-source-sources.jar')
    require(sha(fixed) == EXPECTED['fml'] and source_jar.is_file(), 'Reviewed full-source FML output differs')
    comparison = fml_metadata.compare_archives(historical['fml']['path'], fixed, official_fml['path'])
    comparison_pin = fml_metadata.save(root / fml_metadata.AREA / 'archive-comparison.json', comparison)
    final_paths = {role: Path(row['path']) for role, row in historical.items()}
    final_paths['fml'] = fixed
    artifacts, entries = inspect_tuple(final_paths, EXPECTED)
    compilation_sources = {str(p.relative_to(api / 'source-workspace')): sha(p) for p in
                           sorted((root / fml_metadata.PROJECT / 'src/main/java').rglob('*.java')) +
                           sorted((api / 'source-workspace/admission-bootstrap/src/main/java').rglob('*.java'))}
    binding = {'schema': 1, 'candidateIdentity': CANDIDATE_IDENTITY,
               'candidateIdentityKind': 'reviewed-artifact-equivalence-reference', 'baseSourceIdentity': IDENTITY,
               'acceptedCandidateReference': source_before['acceptedCandidateReference'],
               'sourcePreparation': fml_metadata.pin(root / fml_metadata.AREA / 'source-preparation.json'),
               'sourceInputs': source_before, 'dependencies': dependencies, 'officialFmlReference': official_fml,
               'historicalArtifacts': historical, 'artifacts': artifacts, 'buildReceipt': fml_metadata.pin(fml_receipt),
               'archiveComparison': comparison_pin, 'sourcesJar': fml_metadata.pin(source_jar),
               'generatedCacheSha256': fml_metadata.CACHE_SHA, 'gameLaunched': False}
    binding['consumerBindingSha256'] = hashlib.sha256(json.dumps(binding, sort_keys=True, separators=(',', ':')).encode()).hexdigest()
    binding_pin = fml_metadata.save(root / fml_metadata.AREA / 'candidate-identity.json', binding)
    base.update(artifact=str(fixed), sha256=sha(fixed), historicalFmlSha256=BASE_EXPECTED['fml'],
                sourceBuildReceipt=str(fml_receipt), baseBuildReceipt=str(core_receipt),
                sources=compilation_sources, compilationSources=compilation_sources,
                sourceIdentitySha256=IDENTITY, candidateIdentity=CANDIDATE_IDENTITY,
                candidateIdentityKind='reviewed-artifact-equivalence-reference', candidateBinding=binding_pin,
                pluginCacheSha256=fml_metadata.CACHE_SHA, buildKind='Full 195-source FML v3 build: proc:none classes, separate pinned Log4j proc:only metadata; game unrun')
    save(candidate / 'cold-fml-base-build-receipt.json', base)
    save(candidate / 'cold-built-tuple-artifacts.json', artifacts)
    save(candidate / 'cold-artifact-entry-manifests.json', entries)
    result = {'schema': 2, 'status': 'COLD_TUPLE_BUILT_CHECKED_GAME_UNRUN', 'sourceIdentity': IDENTITY,
              'baseSourceIdentity': IDENTITY, 'candidateIdentity': CANDIDATE_IDENTITY,
              'candidateIdentityKind': 'reviewed-artifact-equivalence-reference', 'candidateBinding': binding_pin,
              'artifacts': artifacts, 'forgeFixture': fixture_result, 'coreBuildReceipt': str(core_receipt), 'productBuildReceipt': str(product_receipt),
              'fmlBuildReceipt': str(fml_receipt), 'archiveComparison': comparison_pin,
              'sourceRecords': 670, 'dependencyRecords': 169, 'fmlCompilationSources': 195,
              'identicalFmlClassCount': 309, 'generatedPluginCacheBytes': 101,
              'duplicateClasses': 0, 'splitPackages': 0, 'gameLaunched': False}
    save(candidate / 'cold-build-result.json', result)
    return result


def refreshed_commands(consumer, profile):
    """Deterministic command contract, including every task/property/flag."""
    root, api, candidate, core = layout(consumer)
    recipe = plan(root)
    service = root / profile['artifactPaths']['service']
    base_fml = api / 'source-workspace/fml-unified/build/libs/fml-loader-4.0.42-unified-source.jar'
    manifest = api / 'run/client-dev/development-build/moddev/client-launch-inputs.json'
    product = [*recipe['productCommandPrefix'], '-PmanagedCoreJar='+str(service),
               '-PmanagedCoreSha256='+profile['observedOutputReference']['service'],
               '-PunifiedFmlJar='+str(base_fml), '-PffapiJar='+str(api/'docs/research/upstream/ffapi-baseline.jar'),
               '-PqslInventory='+str(api/'docs/four-loader/quilt/bundled-tooltip.json'),
               '-PclientClasspathManifest='+str(manifest), 'jar', 'sourcesJar', 'check']
    return {'core':recipe['coreCommand'], 'product':product, 'fml':recipe['fmlCommand']}


def refreshed_environment(consumer, role):
    root, api, candidate, core = layout(consumer)
    jdk = api / '.toolchains/jdk-21.0.12.1+1'
    env = {'PATH': str(jdk/'bin')+':/usr/bin:/bin', 'JAVA_HOME': str(jdk),
           'HOME': str(api/'source-workspace/home'), 'GRADLE_USER_HOME': str(api/'source-workspace/gradle-cache'),
           'XDG_CACHE_HOME': str(api/'source-workspace/xdg-cache'), 'XDG_CONFIG_HOME': str(api/'source-workspace/xdg-config'),
           'LANG':'C.UTF-8','LC_ALL':'C.UTF-8','TZ':'UTC','CI':'true','PUBLISH_RELEASE_TYPE':'alpha',
           'PAIR_API_ROOT':str(api),'PAIR_MAVEN_MIRROR':str(api/'ci/runtime-maven'),
           'PAIR_CORE_MAVEN':str(api/'source-workspace/pinned-build-maven'),
           'FORGE_FACADE_HOST_LIBRARIES':str(api/'run/neoforge-native/libraries'),
           '_JAVA_OPTIONS':'-Xmx512m -XX:ActiveProcessorCount=1 -Dfile.encoding=UTF-8',
           'JAVA_TOOL_OPTIONS':'-Duser.home='+str(api/'source-workspace/home')}
    if role == 'fml':
        env.update(HOME=str(root/fml_metadata.AREA/'build-home'),GRADLE_USER_HOME=str(root/fml_metadata.AREA/'gradle-user-home'),
                   _JAVA_OPTIONS='-XX:ActiveProcessorCount=1',JAVA_OPTS='-Xmx64m -XX:ActiveProcessorCount=1')
        env['JAVA_TOOL_OPTIONS']='-Duser.home='+env['HOME']
    return env


def prepare_refreshed(consumer, profile_path):
    import refreshed_candidate as refresh
    root, api, candidate, core = layout(consumer)
    require(refresh.sha(refresh.local(root, str(profile_path))) == refresh.PROFILE_SHA256,
            'Unreviewed refreshed profile bytes')
    # Existing verified FML/fixture preparations are reused only after rechecking.
    if (root / fml_metadata.AREA / 'source-preparation.json').exists():
        fml_metadata.verify_sources(root)
    else:
        fml_metadata.prepare(root)
    if (root / forge_fixture.SUPPORT / 'source-preparation.json').exists():
        forge_fixture.verify_sources(root)
    else:
        forge_fixture.prepare(root)
    profile = refresh.load_profile(root, profile_path)
    recipe = plan(root)
    result = {'schema': 'portable-refreshed-build-plan-v1', 'profileSha256': refresh.PROFILE_SHA256,
              'profilePath': str(profile_path), 'proofPath': refresh.PROOF_PATH,
              'recipe': refresh.portable(root, recipe), 'inputsBinding': refresh.inputs_binding(root, profile),
              'status': 'PREPARED_FULL_BUILD_NOT_EXECUTED', 'gameLaunched': False, 'runtimeAcceptance': False}
    refresh.save(root, refresh.OUTPUT + '/plan.json', result)
    return result


def execute_refreshed(consumer, profile_path, deadline=None):
    import uuid
    import refreshed_candidate as refresh
    require(os.environ.get('GITHUB_ACTIONS') == 'true' and os.environ.get('GITHUB_REPOSITORY') == 'Nexa-MC/unified-infinity'
            and os.environ.get('GITHUB_REF') == 'refs/heads/diagnostic/network-pair-20261006-a',
            'Actual execution requires the reviewed diagnostic branch; no environment impersonation')
    if deadline is None:
        deadline = time.monotonic() + 42 * 60
    root, api, candidate, core = layout(consumer)
    profile = refresh.load_profile(root, profile_path, require_dependencies=True)
    recipe = plan(root)
    prepared = json.loads(refresh.local(root, refresh.OUTPUT + '/plan.json').read_text())
    require(prepared['profileSha256'] == refresh.PROFILE_SHA256 and prepared['profilePath'] == str(profile_path)
            and prepared['recipe'] == refresh.portable(root, recipe)
            and prepared['inputsBinding'] == refresh.inputs_binding(root, profile), 'Stale/mixed refreshed build plan')
    # Do not begin another core build while prerequisite artifacts are absent.
    fml_metadata.verify_sources(root); fml_metadata.verify_dependencies(root)
    for name, digest in ORIGINALS.items():
        require(sha(root / 'complex-mod-research' / name) == digest, 'Changed original regression fixture')
    relative = Path('libraries/net/minecraft/server/1.21.1-20240808.144430/server-1.21.1-20240808.144430-extra.jar')
    official = api / 'run/neoforge-native' / relative
    require(sha(official) == EXTRA, 'Server regression input differs')
    destination = api / 'run/api1-unified-server-2' / relative
    if not destination.exists():
        destination.parent.mkdir(parents=True, exist_ok=True)
        with official.open('rb') as src, destination.open('xb') as dst: shutil.copyfileobj(src, dst)
    require(sha(destination) == EXTRA, 'Existing server regression alias differs')
    forge_fixture.verify_inputs(root)
    session = {'schema': 'portable-refreshed-build-session-v1', 'sessionId': str(uuid.uuid4()),
               'profileSha256': refresh.PROFILE_SHA256, 'inputsBinding': refresh.inputs_binding(root, profile),
               'startedUtc': datetime.datetime.now(datetime.timezone.utc).isoformat(), 'gameLaunched': False,
               'commandsDigest': refresh.canonical_digest(refresh.normalized_commands(root, profile))}
    session_pin = refresh.save(root, refresh.OUTPUT + '/session.json', session)
    def run(argv, role, limit, outputs=(), legacy_fixture=False):
        require(deadline > time.monotonic(), 'Shared round deadline expired')
        limit = min(limit, deadline - time.monotonic())
        log_rel = refresh.OUTPUT + '/evidence/' + role + '.log'
        log = refresh.local(root, log_rel); require(not log.exists(), 'Refusing reused build log')
        log.parent.mkdir(parents=True, exist_ok=True)
        env = refreshed_environment(root, role)
        for key in ('HOME','GRADLE_USER_HOME','XDG_CACHE_HOME','XDG_CONFIG_HOME'):Path(env[key]).mkdir(parents=True,exist_ok=True)
        refresh.load_profile(root, profile_path, require_dependencies=True)
        before = refresh.inputs_binding(root, profile)
        started = datetime.datetime.now(datetime.timezone.utc).isoformat()
        with log.open('x') as stream:
            outcome = bounded_process.run(argv,cwd=api,env=env,stdout=stream,stderr=subprocess.STDOUT,timeout=limit)
        finished = datetime.datetime.now(datetime.timezone.utc).isoformat()
        refresh.load_profile(root, profile_path, require_dependencies=True)
        after = refresh.inputs_binding(root, profile)
        receipt = {'schema':'portable-refreshed-build-receipt-v1','role':role,'profileSha256':refresh.PROFILE_SHA256,
                   'sessionId':session['sessionId'],'inputsBefore':before,'inputsAfter':after,
                   'startedUtc':started,'finishedUtc':finished,'command':[str(arg).replace(str(root),'${CONSUMER}') for arg in argv],
                   'commandDigest':refresh.canonical_digest([str(arg).replace(str(root),'${CONSUMER}') for arg in argv]),
                   'environment':{key:value.replace(str(root),'${CONSUMER}') for key,value in env.items()},
                   'cwd':'${CONSUMER}/work/api1',
                   'exitCode':outcome.returncode,'log':refresh.pin(root,log),'workers':1,'activeProcessors':1,
                   'perJvmHeapMiB':512,'timeoutSeconds':limit,'gameTask':False,'outputs':[]}
        if outcome.returncode == 0:
            receipt['outputs']=[refresh.pin(root,path) for path in outputs]
        if legacy_fixture:
            # Unchanged fixture verifier consumes its existing bounded receipt schema.
            receipt.update(schema=1,status='PASS' if outcome.returncode==0 else 'FAILED',command=argv,
                           log=str(log),logSha256=sha(log))
        receipt_pin = refresh.save(root,refresh.OUTPUT+'/evidence/'+role+'.json',receipt)
        require(outcome.returncode==0 and before==after, 'Build failed/inputs changed; preserved receipt '+receipt_pin['path'])
        if not legacy_fixture:refresh.validate_receipt(root,receipt_pin,role,profile,session)
        return receipt_pin
    fixture_path = root / forge_fixture.SUPPORT / 'build-result.json'
    if fixture_path.exists():
        fixture_pin = forge_fixture.verify_result(root)
    else:
        def fixture_command(unused_root, argv, name, timeout, unused_deadline):
            return refresh.check_pin(root,run(argv,'forge-fixture',min(timeout,180),legacy_fixture=True))
        fixture_pin = forge_fixture.execute(root,fixture_command,deadline)
    service = core / f'build/libs/connector-{VERSION}-full.jar'
    game = core / f'build/libs/connector-{VERSION}-mod.jar'
    base_fml = api / 'source-workspace/fml-unified/build/libs/fml-loader-4.0.42-unified-source.jar'
    core_receipt=run(recipe['coreCommand'],'core',1200,[service,game,base_fml])
    generated=refresh.pin(root,core/'components/infinity-core/build/generated/resources/infinity/META-INF/unified-infinity/build-identity.json')
    require(refresh.read_pin(root,generated)==refresh.read_pin(root,profile['expectedIdentity']),'Actual source/dependency/compiler identity changed')
    baseline = refresh.local(root,refresh.OUTPUT+'/baseline-fml.jar')
    with base_fml.open('rb') as src, baseline.open('xb') as dst:shutil.copyfileobj(src,dst)
    require(sha(baseline)==fml_metadata.BASE_FML_SHA,'Original FML output changed')
    manifest = api/'run/client-dev/development-build/moddev/client-launch-inputs.json'
    for row in json.loads(manifest.read_text())['inputs']:
        require(sha(Path(row['path']))==row['sha256'],'PRODUCT compile classpath changed')
    args=[*recipe['productCommandPrefix'],'-PmanagedCoreJar='+str(service),'-PmanagedCoreSha256='+sha(service),
          '-PunifiedFmlJar='+str(base_fml),'-PffapiJar='+str(api/'docs/research/upstream/ffapi-baseline.jar'),
          '-PqslInventory='+str(api/'docs/four-loader/quilt/bundled-tooltip.json'),'-PclientClasspathManifest='+str(manifest),'jar','sourcesJar','check']
    product=api/'runtime-bundle/build/libs/unified-infinity-0.1.0-dev.jar'
    require(args == refreshed_commands(root, profile)['product'], 'PRODUCT command differs from profile recipe')
    product_receipt=run(args,'product',600,[product])
    fixed=root/fml_metadata.PROJECT/'build/libs/fml-loader-4.0.42-unified-source.jar'
    fml_receipt=run(recipe['fmlCommand'],'fml',600,[fixed])
    sources=fml_metadata.verify_sources(root);dependencies,official_fml=fml_metadata.verify_dependencies(root)
    comparison=fml_metadata.compare_archives(baseline,fixed,official_fml['path'])
    comparison_pin=refresh.save(root,refresh.OUTPUT+'/fml-comparison.json',refresh.portable(root,comparison))
    source_pin=refresh.save(root,refresh.OUTPUT+'/fml-source-preparation.json',refresh.portable(root,sources))
    artifacts={role:refresh.pin(root,path) for role,path in {'service':service,'game':game,'fml':fixed,'product':product}.items()}
    ownership=refresh.inspect_tuple(root,profile,artifacts)
    java={str(Path(row['path']).relative_to(api/'source-workspace')):row['sha256'] for key in ('fixedSources','sharedSources') for row in sources['sources'][key] if '/src/main/java/' in row['path'] and row['path'].endswith('.java')}
    base={'schema':1,'artifact':artifacts['fml']['path'],'sha256':artifacts['fml']['sha256'],'sources':java,'compilationSources':java,
          'profileSha256':refresh.PROFILE_SHA256,'sourceIdentitySha256':refresh.CORE_IDENTITY,'candidateIdentity':refresh.PROFILE_SHA256,
          'candidateIdentityKind':'verified-refreshed-build-profile','sourceBuildReceipt':fml_receipt['path'],'baseBuildReceipt':core_receipt['path'],
          'installationApproved':False,'historicalFmlSha256':fml_metadata.BASE_FML_SHA,'gameLaunched':False}
    base_pin=refresh.save(root,refresh.OUTPUT+'/fml-base-receipt.json',base)
    proof={'schema':'portable-refreshed-full-build-v1','status':'FULL_BUILD_CHECKED_GAME_UNRUN','profileSha256':refresh.PROFILE_SHA256,
           'sessionId':session['sessionId'],'session':session_pin,'receipts':{'core':core_receipt,'product':product_receipt,'fml':fml_receipt},
           'artifacts':artifacts,'generatedIdentity':generated,'baselineFml':refresh.pin(root,baseline),'fmlComparison':comparison_pin,
           'fmlSourcePreparation':source_pin,'baseReceipt':base_pin,'forgeFixture':refresh.portable(root,fixture_pin),
           'bundleVerification':refresh.pin(root,api/'runtime-bundle/build/reports/bundle-verification.json'),'ownership':ownership,'runtimeAcceptance':False}
    # Validate the complete candidate before publishing the final proof filename.
    draft=refresh.save(root,refresh.OUTPUT+'/proof.pending.json',proof)
    verified=refresh.validate_full_build(root,profile_path,draft['path'])
    refresh.save(root,refresh.PROOF_PATH,proof)
    verified=refresh.validate_full_build(root,profile_path,refresh.PROOF_PATH)
    return dict(verified,proofPath=refresh.PROOF_PATH)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('action', choices=['prepare', 'execute'])
    parser.add_argument('--consumer', type=Path, required=True)
    parser.add_argument('--profile', help='Consumer-relative portable refreshed profile; historical default if omitted')
    args = parser.parse_args()
    print(json.dumps(prepare(args.consumer, profile=args.profile) if args.action == 'prepare' else execute(args.consumer, profile=args.profile), indent=2))
