#!/usr/bin/env python3
"""Consumer-local pair fixtures and four launch seals; no JVM or network.

The frozen assembly implementation remains authoritative. A recorded derivative
binds consumer receipts, the repaired FML tuple, and the exact probe 0.1.1.
"""
from __future__ import annotations
import argparse
from contextlib import contextmanager, redirect_stdout
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import shutil
import sys
import zipfile
import source_materialize
import compile_probe
import fml_metadata
import forge_fixture

SOURCE_AREA = 'work/network-pair-assembly-local1'
SOURCE_PINS = {
    'assemble_pairs.py': 'e3a54d562339ebdb090231e4b50e6d2055139deb06983109d715e8edcc6a75f1',
    'input-lock.json': '616469fb3005028cedb6e6ec0c72e2aec6749bc17162cea9f347b7cfa2ce43dd',
    'required-text-inputs.json': 'cee61fb4bd359450973bf7d38b975c1b7a9d8df663aa5e504bc2aa0bce4debd9',
    'source-manifest.json': '39d42049548a6e5b5c6b87730922c382e45a75ef40c0d6f7f40a359c95b39942',
}
SERVER_REFERENCE = 'work/api1/four-loader/forge-probe/unified-forge-probe-final26b-environment-lock.json'
SERVER_REFERENCE_SHA = '037020ef98eed6ee8c8fc5af8359058cedb248d87d3b3acf756129b22c60b652'
GAME_ENVIRONMENT_SHA = '46e0fec38191d7b521fa6ae2c415c04285d04d1b545787054ab2a41ab67892e8'
JAVA_SHA = '2a207f5e7d075afa01d97f8048389a64432a44c4a5af0f5e77d6e286ec5f401d'
IDENTITY = '54e5f302c1bad0de54a6845a50b128d6a2aa9f4fb9d44ec14c84c754d7fb21f6'
TUPLE_PINS = {
    'service': '7fbabf5eb18b590bd5a30410d076fd814f11d03e8842e3327b4468217e275aa7',
    'game': '9dc29ac8a8030f629dd7afea8b744114504a552c4fce022c6199b23a1024e162',
    'fml': fml_metadata.FIXED_FML_SHA,
    'product': 'b20903f821455682ff5fee62491483e833252dc1a4f4caaa15bef51a356f1409',
}
SUPPORT = 'work/network-pair-cold-assembly'
PROFILES = 'work/network-pair-profiles-cold'
ASSEMBLED = 'work/network-pair-assembled-cold'


def require(value, message):
    if not value:
        raise ValueError(message)


def sha(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def canonical(path):
    path = Path(path).absolute()
    source_materialize._no_symlink_ancestors(path)
    require(path.resolve() == path, 'Noncanonical path: ' + str(path))
    return path


def pin(path):
    path = canonical(path)
    require(path.is_file(), 'Expected regular input: ' + str(path))
    return {'path': str(path), 'bytes': path.stat().st_size, 'sha256': sha(path)}


def local(root, path):
    path = canonical(path)
    require(path.is_relative_to(root), 'Input leaves consumer root: ' + str(path))
    return path


def write_missing(path, data):
    path = canonical(path)
    if path.exists():
        require(path.is_file() and path.read_bytes() == data, 'Refusing changed existing text: ' + str(path))
    else:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open('xb') as stream:
            stream.write(data)
    return pin(path)


def save(path, value):
    path = canonical(path)
    require(not path.exists(), 'Refusing overwrite: ' + str(path))
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('x') as stream:
        json.dump(value, stream, indent=2)
        stream.write('\n')
    return pin(path)


def pinned_read(path, expected):
    record = pin(path)
    require(record['sha256'] == expected, 'Changed source prerequisite: ' + str(path))
    return Path(path).read_bytes()


def module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


@contextmanager
def python_context(argv, root):
    """Keep imported frozen helpers independent of a caller's argv/common module."""
    previous_argv, previous_path = sys.argv, list(sys.path)
    previous_common = sys.modules.get('common')
    sys.argv = argv
    helpers = root / 'work/api1/four-loader/api-contract-controls'
    sys.path.insert(0, str(helpers))
    try:
        if (helpers / 'common.py').exists():
            sys.modules['common'] = module('pair_consumer_common', helpers / 'common.py')
        yield
    finally:
        sys.argv = previous_argv
        sys.path[:] = previous_path
        if previous_common is None:
            sys.modules.pop('common', None)
        else:
            sys.modules['common'] = previous_common


def prepare(repo_root, consumer_root):
    """Restore exact assembly helper/config/legal text into an existing consumer.

    This stage has no dependency on binaries or successful runtime/build receipts.
    Existing byte-identical source files are accepted; differing files are refused.
    """
    repo, root = canonical(repo_root), canonical(consumer_root)
    require(root.is_dir() and root != repo, 'An existing separate consumer root is required')
    area, support = repo / SOURCE_AREA, root / SUPPORT
    originals = {name: pinned_read(area / name, expected) for name, expected in SOURCE_PINS.items()}
    required = json.loads(originals['required-text-inputs.json'])
    source_manifest = json.loads(originals['source-manifest.json'])
    rows = []
    # Validate every required byte before the first copy.
    payloads = []
    for row in required['files']:
        source = area / source_materialize._relative(row['bundledRelativePath'])
        destination = root / source_materialize._relative(row['originalRelativePath'])
        data = pinned_read(source, row['sha256'])
        require(len(data) == row['bytes'], 'Changed required text size')
        payloads.append((destination, data))
    for row in source_manifest['files']:
        if row['path'].startswith('LICENSE'):
            payloads.append((support / 'licenses' / row['path'], pinned_read(area / row['path'], row['sha256'])))
    recovery = source_materialize._load_manifest()['archives']['accepted-recovery']
    archive_data = pinned_read(repo / recovery['path'], recovery['sha256'])
    with zipfile.ZipFile(io.BytesIO(archive_data)) as archive:
        data = archive.read('four-loader/launch-support/game_environment.py')
    require(hashlib.sha256(data).hexdigest() == GAME_ENVIRONMENT_SHA, 'Unexpected launch-support helper')
    payloads.append((root / 'work/api1/four-loader/launch-support/game_environment.py', data))
    for name, data in originals.items():
        payloads.append((support / 'frozen-source' / name, data))
    official = json.loads(pinned_read(repo / SERVER_REFERENCE, SERVER_REFERENCE_SHA))
    reference = {'schema': 1, 'referenceSha256': SERVER_REFERENCE_SHA, 'purpose': 'Exact official dependency identities only; no historical run acceptance',
                 'runtime_files': [{'relative': 'libraries/' + r['path'].split('/libraries/', 1)[1], 'sha256': r['sha256']}
                                   for r in official['runtime_files'] if '/libraries/' in r['path']]}
    payloads.append((support / 'official-server-identity.json', (json.dumps(reference, indent=2) + '\n').encode()))
    for destination, data in payloads:
        rows.append(write_missing(destination, data))
    result = {'schema': 1, 'status': 'PAIR_SOURCE_CONFIG_READY_NO_LAUNCH', 'consumerRoot': str(root),
              'files': rows, 'requiredTextFiles': len(required['files']), 'extraSourceHelpers': 1,
              'sourceAssemblerSha256': SOURCE_PINS['assemble_pairs.py'], 'jvmStarted': False, 'gameLaunched': False}
    write_missing(support / 'source-preparation.json', (json.dumps(result, indent=2) + '\n').encode())
    return result


def _input_receipts(root):
    """Reject missing or historical receipts before creating profile outputs."""
    api = root / 'work/api1'
    candidate = root / 'work/emi-render-integration'
    paths = {
        'clientSeal': api / 'run/api1-unified-client-build/official-client-launch-seal.json',
        'serverClosure': api / 'ci/runtime-restore/native-server-closure.json',
        'runtimeResult': api / 'ci/runtime-restore/runtime-result.json',
        'tuple': candidate / 'cold-built-tuple-artifacts.json',
        'baseReceipt': candidate / 'cold-fml-base-build-receipt.json',
        'buildResult': candidate / 'cold-build-result.json',
        'probeResult': root / compile_probe.OUTPUT_RELATIVE / 'result.json',
        'probeJar': root / compile_probe.OUTPUT_RELATIVE / compile_probe.ARTIFACT_NAME,
        'candidateBinding': root / fml_metadata.AREA / 'candidate-identity.json',
        'archiveComparison': root / fml_metadata.AREA / 'archive-comparison.json',
        'fmlSourcePreparation': root / fml_metadata.AREA / 'source-preparation.json',
        'forgeFixture': root / forge_fixture.SUPPORT / 'build-result.json',
    }
    missing = [str(p.relative_to(root)) for p in paths.values() if not p.is_file()]
    require(not missing, 'Missing fresh consumer build/runtime/probe inputs: ' + json.dumps(missing))
    pins = {key: pin(local(root, path)) for key, path in paths.items()}
    runtime = json.loads(paths['runtimeResult'].read_text())
    require(runtime['status'] == 'OFFICIAL_RUNTIME_PREPARED_GAME_UNRUN' and runtime['gameLaunched'] is False and
            runtime['networkAcceptance'] is False, 'Official runtime preparation must complete first')
    for key in ('clientSeal', 'nativeServerClosure'):
        expected = pins['clientSeal' if key == 'clientSeal' else 'serverClosure']
        require(runtime[key]['path'] == expected['path'] and runtime[key]['sha256'] == expected['sha256'], 'Runtime result does not bind current ' + key)
    server = json.loads(paths['serverClosure'].read_text())
    server_root = api / 'run/neoforge-native'
    require(server['status'] == 'OFFICIAL_NATIVE_SERVER_CLOSURE_VERIFIED' and server['gameLaunched'] is False and
            server['root'] == str(server_root), 'Unexpected native server closure')
    identity = json.loads((root / SUPPORT / 'official-server-identity.json').read_text())
    expected = {str(server_root / r['relative']): r['sha256'] for r in identity['runtime_files']}
    observed = {}
    for row in server['runtime_files']:
        current = pin(local(root, row['path']))
        require(current['sha256'] == row['sha256'] and current['bytes'] == row['bytes'], 'Changed official server input')
        require(current['path'] not in observed, 'Duplicate official server input')
        observed[current['path']] = current['sha256']
    require(observed == expected and len(observed) == 95, 'Official server dependency pins differ from the frozen source recipe')
    require(server['argfile'] == str(server_root / 'libraries/net/neoforged/neoforge/21.1.219/unix_args.txt'), 'Native server argument source differs')
    client = json.loads(paths['clientSeal'].read_text())
    require(client['gameLaunched'] is False and client['heapMiB'] == 1280 and client['activeProcessors'] == 2, 'Unexpected client export bounds')
    local(root, client['workingDirectory'])
    for row in client['files']:
        path = local(root, row['path'])
        if row.get('kind') == 'declared-empty-source-output':
            require(not path.exists() or path.is_dir() and not any(path.iterdir()), 'Nonempty development output')
        else:
            require(pin(path)['sha256'] == row['sha256'], 'Changed official client input')
    require(sha(api / '.toolchains/jdk-21.0.12.1+1/bin/java') == JAVA_SHA, 'Pinned Java executable differs')
    build = json.loads(paths['buildResult'].read_text())
    require(build['status'] == 'COLD_TUPLE_BUILT_CHECKED_GAME_UNRUN' and build['sourceIdentity'] == IDENTITY and
            build['baseSourceIdentity'] == IDENTITY and build['candidateIdentity'] == fml_metadata.CANDIDATE_IDENTITY and
            build['candidateIdentityKind'] == 'reviewed-artifact-equivalence-reference' and
            build['fmlCompilationSources'] == 195 and build['identicalFmlClassCount'] == 309 and
            build['generatedPluginCacheBytes'] == 101 and
            build['sourceRecords'] == 670 and build['dependencyRecords'] == 169 and build['duplicateClasses'] == 0 and
            build['splitPackages'] == 0 and build['gameLaunched'] is False, 'A fresh exact full-source build result is required')
    require(build['forgeFixture'] == pins['forgeFixture'] == forge_fixture.verify_result(root),
            'The exact source-built original Forge regression fixture must bind this core build')
    artifacts = json.loads(paths['tuple'].read_text())
    require(set(artifacts) == set(TUPLE_PINS) and artifacts == build['artifacts'], 'Unexpected rebuilt tuple roles')
    for role, row in artifacts.items():
        current = pin(local(root, row['path']))
        require(row['sha256'] == current['sha256'] == TUPLE_PINS[role], 'Exact rebuilt tuple changed: ' + role)
    for key in ('coreBuildReceipt', 'productBuildReceipt', 'fmlBuildReceipt'):
        path = local(root, build[key])
        receipt = json.loads(path.read_text())
        require(receipt['status'] == 'PASS' and receipt['exitCode'] == 0 and receipt['gameTask'] is False, 'Required genuine bounded build receipt failed')
        require(pin(local(root, receipt['log']))['sha256'] == receipt['logSha256'], 'Build log changed')
        pins[key] = pin(path)
    base = json.loads(paths['baseReceipt'].read_text())
    require(base['artifact'] == artifacts['fml']['path'] and base['sha256'] == TUPLE_PINS['fml'] and
            base['sourceIdentitySha256'] == IDENTITY and base['sourceBuildReceipt'] == build['fmlBuildReceipt'] and
            base['baseBuildReceipt'] == build['coreBuildReceipt'] and
            base['historicalFmlSha256'] == fml_metadata.BASE_FML_SHA and
            base['candidateIdentity'] == fml_metadata.CANDIDATE_IDENTITY and
            base['candidateBinding'] == build['candidateBinding'] == pins['candidateBinding'],
            'Fresh full-source repaired FML receipt differs')
    verify_candidate_binding(root, paths, pins, build, base, artifacts)
    probe = json.loads(paths['probeResult'].read_text())
    require(probe.get('version') == '0.1.1' and probe.get('sourceManifestSha256') == compile_probe.SOURCE_SHA and
            sha(paths['probeJar']) == compile_probe.REFERENCE_JAR_SHA,
            'The exact source-built probe 0.1.1 is required')
    require(probe.get('artifactPath') == str(paths['probeJar']) and probe.get('runtimeInputReceipt') == pins['runtimeResult'],
            'Probe receipt must bind this fresh consumer artifact and runtime preparation')
    require([phase['name'] for phase in probe['phases']] == ['compile-main', 'compile-test', 'codec-test'],
            'Missing genuine probe compile/test phases')
    for phase in probe['phases']:
        require(phase['exitCode'] == 0 and phase['heapMiB'] == 192 and phase['processors'] == 1,
                'Failed or differently bounded probe phase')
        require(pin(local(root, phase['log']['path'])) == phase['log'], 'Probe phase log changed')
        local(root, phase['command'][0])
    require(len(probe['classpathInputs']) == 95, 'Unexpected genuine probe classpath closure')
    for row in probe['classpathInputs']:
        require(pin(local(root, row['path'])) == row, 'Probe classpath input changed')
    return paths, pins


def verify_candidate_binding(root, paths, pins, build, base, artifacts):
    """Recheck local source/receipt binding and exact base-to-repaired BOOT delta."""
    binding = json.loads(paths['candidateBinding'].read_text())
    digest = binding.pop('consumerBindingSha256')
    require(hashlib.sha256(json.dumps(binding, sort_keys=True, separators=(',', ':')).encode()).hexdigest() == digest,
            'Consumer candidate binding digest differs')
    require(binding['candidateIdentity'] == fml_metadata.CANDIDATE_IDENTITY and
            binding['baseSourceIdentity'] == IDENTITY and
            binding['candidateIdentityKind'] == 'reviewed-artifact-equivalence-reference' and
            binding['artifacts'] == artifacts and binding['buildReceipt'] == pins['fmlBuildReceipt'] and
            binding['archiveComparison'] == build['archiveComparison'] == pins['archiveComparison'] and
            binding['sourcePreparation'] == pins['fmlSourcePreparation'], 'Candidate binding belongs to another build')
    source = fml_metadata.verify_sources(root)
    require(source == binding['sourceInputs'], 'FML compilation source binding changed')
    dependencies, official = fml_metadata.verify_dependencies(root)
    require(dependencies == binding['dependencies'] and official == binding['officialFmlReference'],
            'Pinned FML source compile inputs changed')
    historical = binding['historicalArtifacts']
    require(set(historical) == set(TUPLE_PINS), 'Historical tuple roles differ')
    for role, row in historical.items():
        expected = fml_metadata.BASE_FML_SHA if role == 'fml' else TUPLE_PINS[role]
        require(pin(local(root, row['path']))['sha256'] == row['sha256'] == expected,
                'Fresh base output changed: ' + role)
    comparison = fml_metadata.compare_archives(historical['fml']['path'], artifacts['fml']['path'], official['path'])
    require(json.loads(paths['archiveComparison'].read_text()) == comparison, 'FML archive comparison differs')
    require(pin(local(root, binding['sourcesJar']['path'])) == binding['sourcesJar'], 'Fresh FML sources JAR changed')
    java_sources = {str(Path(row['path']).relative_to(root / 'work/api1/source-workspace')): row['sha256']
                    for key in ('fixedSources', 'sharedSources') for row in source['sources'][key]
                    if '/src/main/java/' in row['path'] and row['path'].endswith('.java')}
    require(len(java_sources) == 195 and base['sources'] == base['compilationSources'] == java_sources,
            'FML receipt must bind the 195 sources actually compiled')


def prepare_profile_helper(root):
    """Keep the archived four-mod fixture helper intact; bind only probe 0.1.1."""
    original = root / 'work/network-pair-ci-next/prepare_profiles.py'
    path = root / SUPPORT / 'prepare_profiles_probe011.py'
    text = original.read_text()
    substitutions = [
        ("SOURCE_MANIFEST = '65cf1c852d6e07226fcd7d2f66df8d202f3a6e70cd4d8f963c6dc40b28554909'",
         "SOURCE_MANIFEST = '" + compile_probe.SOURCE_SHA + "'", 1),
        ("'network-control-probe-0.1.0.jar'", repr(compile_probe.ARTIFACT_NAME), 1),
    ]
    for before, after, count in substitutions:
        require(text.count(before) == count, 'Frozen profile helper substitution shape changed')
        text = text.replace(before, after)
    write_missing(path, text.encode())
    write_missing(root / SUPPORT / 'profile-helper-derivation.json',
                  (json.dumps({'schema': 1, 'original': pin(original), 'derivative': pin(path),
                               'changes': [{'before': a, 'after': b, 'occurrences': n} for a, b, n in substitutions],
                               'sourceManifestSha256': compile_probe.SOURCE_SHA,
                               'expectedProbeSha256': compile_probe.REFERENCE_JAR_SHA,
                               'gameLaunched': False}, indent=2) + '\n').encode())
    return path


def _prepare_profiles(root, paths, offline_identity_reference, eula_reference):
    for reference in (offline_identity_reference, eula_reference):
        require(isinstance(reference, str) and 0 < len(reference) <= 512 and '\n' not in reference,
                'Existing authorization references are required for the virtual identity and accepted EULA')
    area = root / PROFILES
    require(not area.exists(), 'Refusing an existing pair profile preparation')
    source = root / compile_probe.SOURCE_RELATIVE
    helper = prepare_profile_helper(root)
    fixture = module('pair_consumer_profiles', helper)
    result = {}
    for target in ('native-neoforge', 'unified'):
        argv = [str(helper), '--target', target, '--source', str(source), '--probe', str(paths['probeJar']),
                '--compile-result', str(paths['probeResult']), '--compile-result-sha256', sha(paths['probeResult']),
                '--mods', str(root / 'complex-mod-research'),
                '--config', str(root / 'work/api1/run/api1-native-emi-backpacks/config/neoforge-server.toml'),
                '--output', str(area / target), '--offline-identity-reference', offline_identity_reference,
                '--eula-reference', eula_reference, '--prepare']
        with python_context(argv, root), redirect_stdout(io.StringIO()):
            fixture.main()
        result[target] = pin(area / target / 'profile-preparation.json')
    return result


def _derivative(source, input_lock_sha):
    replacements = [
        ("LOCK_SHA = '" + SOURCE_PINS['input-lock.json'] + "'", "LOCK_SHA = '" + input_lock_sha + "'", 1),
        ("TUPLE = ROOT / 'work/emi-render-integration/built-tuple-artifacts.json'", "TUPLE = ROOT / 'work/emi-render-integration/cold-built-tuple-artifacts.json'", 1),
        ("BASE_RECEIPT = ROOT / 'work/emi-render-integration/fml-base-build-receipt.json'", "BASE_RECEIPT = ROOT / 'work/emi-render-integration/cold-fml-base-build-receipt.json'", 1),
        ("API/'four-loader/forge-probe/unified-forge-probe-final26b-environment-lock.json'", "API/'ci/runtime-restore/native-server-closure.json'", 2),
        ("ROOT/'work/network-pair-profiles-local1'", "ROOT/'work/network-pair-profiles-cold'", 1),
    ]
    for old, new, count in replacements:
        require(source.count(old) == count, 'Frozen assembly substitution shape changed: ' + old)
        source = source.replace(old, new)
    return source, [{'before': a, 'after': b, 'occurrences': n} for a, b, n in replacements]


def assemble(repo_root, consumer_root, output=None, *, offline_identity_reference, eula_reference):
    """Prepare true fresh fixtures and build four seals using verified receipts.

    Requires completed official-runtime, exact cold-build, and genuine own-probe
    compile stages in this consumer. The supplied authorization references are
    recorded verbatim by the unchanged profile helper. Nothing is launched.
    """
    repo, root = canonical(repo_root), canonical(consumer_root)
    out = canonical(output) if output is not None else root / ASSEMBLED
    local(root, out)
    require(not out.exists(), 'Fresh consumer-local assembly output required')
    preparation = prepare(repo, root)
    paths, dynamic = _input_receipts(root)
    fixtures = _prepare_profiles(root, paths, offline_identity_reference, eula_reference)
    support = root / SUPPORT
    frozen_lock = json.loads((support / 'frozen-source/input-lock.json').read_text())
    required = json.loads((support / 'frozen-source/required-text-inputs.json').read_text())
    static_paths = [row['originalRelativePath'] for row in required['files']]
    static_paths.append('work/api1/four-loader/launch-support/game_environment.py')
    records = [pin(root / p) for p in static_paths] + list(dynamic.values()) + list(fixtures.values())
    records += [pin(root / SUPPORT / 'prepare_profiles_probe011.py'), pin(root / SUPPORT / 'profile-helper-derivation.json')]
    rows = []
    for record in records:
        path = local(root, record['path'])
        rows.append({'path': path.relative_to(root).as_posix(), 'bytes': record['bytes'], 'sha256': record['sha256']})
    require(len({r['path'] for r in rows}) == len(rows), 'Duplicate dynamic assembly input')
    lock = {'schema': 1, 'files': rows, 'acceptedConfigSources': frozen_lock['acceptedConfigSources'],
            'configNote': frozen_lock['configNote'], 'serverPropertiesBasis': frozen_lock['serverPropertiesBasis'],
            'purpose': 'Consumer-local fresh runtime/build/profile receipts plus unchanged source/config pins',
            'frozenSourceAssemblerSha256': SOURCE_PINS['assemble_pairs.py']}
    lock_pin = save(support / 'input-lock.json', lock)
    source = (support / 'frozen-source/assemble_pairs.py').read_text()
    derivative, changes = _derivative(source, lock_pin['sha256'])
    derivative_path = support / 'assemble_pairs.py'
    require(not derivative_path.exists(), 'Refusing existing assembly derivative')
    derivative_path.write_text(derivative)
    save(support / 'derivation.json', {'schema': 1, 'source': pin(support / 'frozen-source/assemble_pairs.py'),
                                    'derivative': pin(derivative_path), 'changes': changes,
                                    'inputLock': lock_pin, 'sourcePreparation': pin(support / 'source-preparation.json'),
                                    'jvmStarted': False, 'gameLaunched': False})
    worker = module('consumer_cold_pair_assembler', derivative_path)
    with python_context([str(derivative_path), '--output', str(out)], root), redirect_stdout(io.StringIO()) as stdout:
        worker.main()
    assembled = json.loads((out / 'assembly-result.json').read_text())
    require(assembled['status'] == 'SOURCE_ASSEMBLED_GAME_UNRUN' and assembled['gameLaunched'] is False and
            assembled['jvmStarted'] is False and set(assembled['groups']) == {'native-neoforge', 'unified'}, 'Unexpected pair assembly result')
    # Check all fresh role paths, exact four mods, original byte identities, and
    # Unified source-owned validation receipts without starting a process.
    fixture_module = module('consumer_pair_final_fixture', root / 'work/network-pair-ci-next/prepare_profiles.py')
    for target, group in assembled['groups'].items():
        require(group['port'] == (25631 if target == 'native-neoforge' else 25632), 'Wrong bounded pair port')
        expected_mods = dict(fixture_module.SHARED, **dict([fixture_module.EMI[target]]))
        expected_mods[paths['probeJar'].name] = dynamic['probeJar']['sha256']
        for side, record in group['roles'].items():
            seal_path = local(root, record['path'])
            require(sha(seal_path) == record['sha256'], 'Fresh role seal changed')
            role = json.loads(seal_path.read_text())
            game = local(root, role['cwd'])
            members = list((game / 'mods').iterdir())
            require(len(members) == 4 and all(p.is_file() and not p.is_symlink() for p in members), 'Unexpected user-mod directory entry')
            mods = {p.name: sha(p) for p in members}
            require(mods == expected_mods and len(mods) == 4, 'Profile has other or changed user mods')
            for row in role['files']:
                require(pin(local(root, row['path'])) == row, 'Final role input changed')
            worker.validate_command(role['command'], side, game, group['port'], role['files'])
            if target == 'unified':
                require(role['assembly']['status'] == 'validated-before-jvm' and role['assembly']['classOwnerCount'] == 1 and
                        role['assembly']['gameLaunched'] is False and role['assembly']['jvmStarted'] is False,
                        'Unified full-source assembly did not validate')
    result = {'schema': 1, 'status': 'COLD_FOUR_ROLE_ASSEMBLY_READY_GAME_UNRUN',
              'consumerRoot': str(root), 'assemblyRoot': str(out), 'assemblyResult': pin(out / 'assembly-result.json'),
              'roleCount': 4, 'groups': assembled['groups'], 'profiles': fixtures,
              'baseSourceIdentity': IDENTITY, 'candidateIdentity': fml_metadata.CANDIDATE_IDENTITY,
              'candidateIdentityKind': 'reviewed-artifact-equivalence-reference',
              'probeVersion': '0.1.1', 'probeSha256': compile_probe.REFERENCE_JAR_SHA,
              'derivation': pin(support / 'derivation.json'), 'inputLock': lock_pin,
              'requiredTextFiles': preparation['requiredTextFiles'],
              'jvmStarted': False, 'gameLaunched': False, 'networkAcceptance': False,
              'remaining': assembled['remaining']}
    save(support / 'pair-assembly-result.json', result)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['prepare', 'assemble'])
    parser.add_argument('--repo-root', type=Path, required=True)
    parser.add_argument('--consumer-root', type=Path, required=True)
    parser.add_argument('--output', type=Path)
    parser.add_argument('--offline-identity-reference')
    parser.add_argument('--eula-reference')
    args = parser.parse_args()
    if args.action == 'prepare':
        result = prepare(args.repo_root, args.consumer_root)
    else:
        result = assemble(args.repo_root, args.consumer_root, args.output,
                          offline_identity_reference=args.offline_identity_reference, eula_reference=args.eula_reference)
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
