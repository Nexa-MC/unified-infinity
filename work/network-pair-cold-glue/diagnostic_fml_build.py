"""Opt-in source-built FML diagnostics. Never modifies a locked baseline or launches a game.

All subprocess work consumes the caller's existing monotonic deadline. The two
artifact receipts are portable; only the outer supervisor manifest has absolute
receipt paths. Full refreshed-build validation is mandatory, including on reuse.
"""
from __future__ import annotations
import copy
import hashlib
import json
import math
from pathlib import Path, PurePosixPath
import shutil
import stat
import time
import zipfile

import bounded_process
import refreshed_candidate as refreshed

HERE = Path(__file__).resolve().parent
MODULE = 'work/network-pair-cold-glue/diagnostic_fml_build.py'
SOURCES = 'work/network-pair-cold-glue/diagnostic-java'
OUTPUT = 'work/process-start-hardware-cpu-skip-diagnostic-fml'
SCHEMA = 'fml-process-start-diagnostic-v1'
RECEIPT_SCHEMA = 'fml-process-start-diagnostic-build-v1'
NATIVE_SHA = '182fcee7ed6e2be4c815bd08d2c766d355c58ab1e227b6ffd84ed26a0f71b6d6'
FIXED_FML_SHA = '4d697ba080277ed270ddd427102e03da4d6cd58b2b9ed584db010b59f037c2e9'
CLASS = 'net/neoforged/fml/loading/targets/CommonLaunchHandler'
REPLACEMENTS = {CLASS + '.class', CLASS + '$1ExplodedModPath.class'}
OWN = 'net/neoforged/fml/loading/diagnostic/'
OWN_CLASSES = {OWN + name + '.class' for name in (
    'ProcessStartDiagnostic', 'ProcessStartDiagnostic$Caller', 'ProcessStartDiagnostic$DecodeFault',
    'ProcessStartDiagnostic$Event', 'ProcessStartDiagnostic$Limits', 'ProcessStartDiagnostic$Reason',
    'ProcessStartDiagnostic$RequestedCommand', 'ProcessStartDiagnostic$SetupFault',
    'ProcessStartDiagnostic$Snapshot', 'ProcessStartDiagnosticLaunch', 'ProcessStartDiagnosticLaunch$Refused',
    'HardwareInventorySkipLaunchPlugin', 'HardwareInventorySkipLaunchPlugin$Refused')}
METADATA = 'META-INF/unified-hardware-inventory-skip-diagnostic.json'
SERVICE = 'META-INF/services/cpw.mods.modlauncher.serviceapi.ILaunchPluginService'
SERVICE_ORIGINAL = (b'net.neoforged.fml.loading.log4j.SLF4JFixerLaunchPluginService\n'
                    b'net.neoforged.fml.common.asm.RuntimeDistCleaner\n'
                    b'net.neoforged.fml.common.asm.enumextension.RuntimeEnumExtender')
SERVICE_PROVIDER = 'net.neoforged.fml.loading.diagnostic.HardwareInventorySkipLaunchPlugin'
SERVICE_DERIVED = SERVICE_ORIGINAL + b'\n' + SERVICE_PROVIDER.encode('ascii') + b'\n'
SCOPE = {'diagnosticProfile': 'system-report-and-glx-cpu-inventory-skip-v2',
         'behavioralChange': True,
         'hardwareScope': 'all-SystemReport-instances-including-crash-reports-and-GLX-CPU-description',
         'nonHardwareFieldsPreserved': True, 'gameJarBytesModified': False}
# Deterministic output of the pinned source/dependency/compiler recipe, independently
# compiled and module-smoke-tested before this portable builder was introduced.
EXPECTED_CLASS_SHA = {'net/neoforged/fml/loading/diagnostic/ProcessStartDiagnostic$Caller.class': '58292d8e01856d6fdb9e69ba22dd46eb4578e30a6f85f061656b473694d655a5',
 'net/neoforged/fml/loading/diagnostic/ProcessStartDiagnostic$DecodeFault.class': '10d05e73f9280e76e443ef5499111b01b569d4d20e0e8325454f28680c0d1b67',
 'net/neoforged/fml/loading/diagnostic/ProcessStartDiagnostic$Event.class': 'a62c0b58f67de612545e79e312275cd5d0845f22133c1273ffbaf78f7aabb6cb',
 'net/neoforged/fml/loading/diagnostic/ProcessStartDiagnostic$Limits.class': 'f06170d00816fa0a681425b9abfb886ddef1bc5e4933d8b03742df77557d35c2',
 'net/neoforged/fml/loading/diagnostic/ProcessStartDiagnostic$Reason.class': '632c8c3e83cd14b3cdb3254af05994c872fd40e43d47a64a588b0a9a384b905b',
 'net/neoforged/fml/loading/diagnostic/ProcessStartDiagnostic$RequestedCommand.class': '0a2881c75a859c5484a6b8f41fca59fdc927ea8da1a4cf9fc7e5f77a3fb8ac04',
 'net/neoforged/fml/loading/diagnostic/ProcessStartDiagnostic$SetupFault.class': '943f89890ecedc61fba74a5f5b86bcc394ceff7caaf2c52da48b910bd897fe90',
 'net/neoforged/fml/loading/diagnostic/ProcessStartDiagnostic$Snapshot.class': '67af308098ce28b0195df5ac87d047766ff3edeab8793fae0943e11b6d62a4ea',
 'net/neoforged/fml/loading/diagnostic/ProcessStartDiagnostic.class': '71a2f62c198a5eb23d69d3b1cfc6ae9ed5c03b56c01dfcc56aa5a3dbe720ac0b',
 'net/neoforged/fml/loading/diagnostic/ProcessStartDiagnosticLaunch$Refused.class': 'd1d23ebf31d2db1bb8554c3c43cf6e1fc1c588bccb3093836017f22739a1500e',
 'net/neoforged/fml/loading/diagnostic/ProcessStartDiagnosticLaunch.class': '580bf1968dfc2aa1b2dd28338e06b99f5ce953aa260a23269e913c8e23263a23',
 'net/neoforged/fml/loading/targets/CommonLaunchHandler$1ExplodedModPath.class': '4488817c19c3aef17b0d9f64f5b758184761497164119b0772fc0a8557bd24a2',
 'net/neoforged/fml/loading/targets/CommonLaunchHandler.class': '3542e38e6c7a8d961a6d53a712b862238bf3ebb7fe8b506d3a622087be16c525'}
EXPECTED_CLASS_SHA.update({
    OWN + 'HardwareInventorySkipLaunchPlugin.class': '217f85ebbced90c322c50f704bcae7cd2604c2d444ead65a0c866966d0dd2e7e',
    OWN + 'HardwareInventorySkipLaunchPlugin$Refused.class': 'c5470025788660b342e6a4075d427868391ffac6a37e55c640c0cb6be587c8ca',
})
SOURCE_SHA = {
    'HardwareInventorySkipLaunchPlugin.java': 'e9eddd6814f34a632232b229184083c0d60d95cdaed74a180a9bf88083caa372',
    'CommonLaunchHandler.java': 'e453b96e10128d665cda58d458203b7201875c84c1742d73f84f2563404b8a58',
    'ProcessStartDiagnostic.java': 'c7915ed6d33f41fa9bc4de5a4f1903300f7f358f2801f749a59006c81387c5b0',
    'ProcessStartDiagnosticLaunch.java': '50e1e7da3c32d68b509a7db3b66a1c0a9d7b7b0b0d1a0f9c55b8371446776f65',
}
HOOK_SOURCE_SHA = '5d9b6eb9bc012b76e80bfa11aa9760e80431b8eddefeed82649249dd1d06d463'
DEPENDENCIES = {
 'net/neoforged/fancymodloader/loader/4.0.42/loader-4.0.42.jar': NATIVE_SHA,
 'com/mojang/logging/1.2.7/logging-1.2.7.jar': '3dc3190204bac5f4184d8405bfe1f724f73a6a15a0d3f36ec7f69e6872c1a76c',
 'cpw/mods/modlauncher/11.0.5/modlauncher-11.0.5.jar': 'fd9b9fc7cf043d2264ea0113eac6b258f0a71fece5b00e831bfbdf9726c78a24',
 'net/neoforged/mergetool/2.0.0/mergetool-2.0.0-api.jar': '0260881294d8b218afe3d673f084d3745a55c28b35205d07d5e62d7f22202a00',
 'org/apache/logging/log4j/log4j-core/2.22.1/log4j-core-2.22.1.jar': '46dccecac556623d8e2ce8648496824a82951d139062a4e61148aff1a25ed18d',
 'org/apache/logging/log4j/log4j-api/2.22.1/log4j-api-2.22.1.jar': '5d7beae7ff15d8516d6517121d7f12a79a6ac180df64b5fcec55d5be21056e53',
 'org/slf4j/slf4j-api/2.0.9/slf4j-api-2.0.9.jar': '0818930dc8d7debb403204611691da58e49d42c50b6ffcfdce02dadb7c3c2b6c',
 'org/ow2/asm/asm/9.8/asm-9.8.jar': '876eab6a83daecad5ca67eb9fcabb063c97b5aeb8cf1fca7a989ecde17522051',
 'org/ow2/asm/asm-tree/9.8/asm-tree-9.8.jar': '14b7880cb7c85eed101e2710432fc3ffb83275532a6a894dc4c4095d49ad59f1',
}
JDK_FILES = {
 'bin/java': '2a207f5e7d075afa01d97f8048389a64432a44c4a5af0f5e77d6e286ec5f401d',
 'bin/javac': '55859b80e7a9c4c4736be19ad3addeb35112ca6d17a30c4e0e116afc0a499bdb',
 'release': 'ebbd70bf00bab6d39addf51969c5ff244030b86b29de400b9fb10612ebd3ceec',
 'lib/modules': '70c5465dabf8e1bec2860631ea3ffd342f0ec23a5e2efd3a389d2abe32448f98',
 'lib/libjli.so': '6703dbc0a7d5953ba248f45afca71b13807e5be9682110ed205f4361640f496a',
 'lib/server/libjvm.so': '462fa559157ee8a862e7e4b8a4a74f8abbf5e1a9deb64f22ee23c7e8c43f698b',
}
ARTIFACT_NAMES = {'native': 'loader-4.0.42-process-start-hardware-cpu-skip-diagnostic-only.jar',
                  'unified': 'fml-loader-4.0.42-unified-process-start-hardware-cpu-skip-diagnostic-only.jar'}


def require(value, message):
    if not value: raise ValueError(message)


def remaining(deadline):
    require(isinstance(deadline, (int, float)) and math.isfinite(deadline), 'Existing monotonic deadline required')
    left = deadline - time.monotonic()
    if left <= 0: raise TimeoutError('Diagnostic build inherited deadline expired')
    return left


def rel(root, path):
    root = Path(root).absolute(); path = Path(path)
    if path.is_absolute():
        require(path.is_relative_to(root), 'Input outside consumer')
        path = path.relative_to(root)
    return refreshed.local(root, path.as_posix())


def exact_pin(root, path, expected=None):
    path = rel(root, path)
    require(path.is_file() and stat.S_ISREG(path.stat().st_mode), 'Regular diagnostic input required')
    row = refreshed.pin(root, path)
    if expected: require(row['sha256'] == expected, 'Diagnostic pinned input changed: ' + row['path'])
    return row


def canonical_digest(data): return hashlib.sha256(data).hexdigest()


def read_archive(path, *, diagnostic=False):
    """Inspect without extracting. No aliases, signatures, configured bases or duplicate entries."""
    entries = {}
    with zipfile.ZipFile(path) as archive:
        require(len(archive.infolist()) <= 4096, 'Oversized diagnostic archive inventory')
        total = 0
        for info in archive.infolist():
            name = info.filename; member = PurePosixPath(name.rstrip('/'))
            require(name and '\\' not in name and not member.is_absolute()
                    and '..' not in member.parts and member.as_posix() == name.rstrip('/'), 'Unsafe archive member')
            require(name not in entries, 'Duplicate archive member')
            require(not stat.S_ISLNK(info.external_attr >> 16), 'Archive symlink refused')
            require(not info.flag_bits & 1, 'Encrypted archive refused')
            upper = name.upper()
            require(not (upper.startswith('META-INF/') and
                    (upper.endswith(('.SF', '.RSA', '.DSA', '.EC')) or upper.startswith('META-INF/SIG-'))),
                    'Signed archive refused')
            if not diagnostic:
                require(not name.startswith(OWN) and name != METADATA, 'Previously derived base refused')
            total += info.file_size
            require(info.file_size <= 16 * 1024 * 1024 and total <= 64 * 1024 * 1024, 'Archive payload bound exceeded')
            payload = archive.read(info)
            if member.name.lower() == 'installation.json':
                require(name == 'META-INF/unified-admission/installation.json'
                        and payload == b'{"schema":1,"approved":false}\n',
                        'Configured installation base refused')
            entries[name] = (copy.copy(info), payload)
    require(REPLACEMENTS <= entries.keys(), 'Required launch classes absent')
    require(SERVICE in entries and entries[SERVICE][1] == (SERVICE_DERIVED if diagnostic else SERVICE_ORIGINAL),
            'Unexpected launch plugin service descriptor')
    return entries


def inventory(entries):
    return {name: canonical_digest(data) for name, (_, data) in sorted(entries.items())}


def archive_derivative(base, output, classes, metadata):
    require(not Path(output).exists(), 'Stale diagnostic artifact refused')
    entries = read_archive(base)
    require(set(classes) == REPLACEMENTS | OWN_CLASSES, 'Unexpected/missing compiled class inventory')
    require({n: canonical_digest(p) for n, p in classes.items()} == EXPECTED_CLASS_SHA, 'Compiled classes differ from reviewed deterministic reference')
    with zipfile.ZipFile(output, 'x') as archive:
        # Unrelated entry payload and metadata are copied, not regenerated.
        for name, (info, payload) in entries.items():
            archive.writestr(info, SERVICE_DERIVED if name == SERVICE else classes.get(name, payload))
        for name in sorted(OWN_CLASSES):
            info = zipfile.ZipInfo(name, (1980, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED; info.external_attr = 0o644 << 16
            archive.writestr(info, classes[name])
        info = zipfile.ZipInfo(METADATA, (1980, 1, 1, 0, 0, 0))
        info.compress_type = zipfile.ZIP_DEFLATED; info.external_attr = 0o644 << 16
        archive.writestr(info, json.dumps(metadata, sort_keys=True, separators=(',', ':')).encode())
    return compare_derivative(base, output, metadata)


def compare_derivative(base, output, metadata):
    before = read_archive(base); after = read_archive(output, diagnostic=True)
    require(set(after) == set(before) | OWN_CLASSES | {METADATA}, 'Derivative archive entry drift')
    require(after[METADATA][1] == json.dumps(metadata, sort_keys=True, separators=(',', ':')).encode(),
            'Derivative metadata mismatch')
    preserved = []
    for name, (info, data) in before.items():
        if name in REPLACEMENTS or name == SERVICE: continue
        out_info, out_data = after[name]
        require(data == out_data, 'Unrelated archive entry payload changed: ' + name)
        for field in ('date_time', 'compress_type', 'comment', 'extra', 'external_attr', 'internal_attr', 'create_system'):
            require(getattr(info, field) == getattr(out_info, field), 'Unrelated archive metadata changed: ' + name)
        preserved.append(name)
    return {'originalEntryHashes': inventory(before), 'newEntryHashes': inventory(after),
            'replacedEntries': sorted(REPLACEMENTS | {SERVICE}),
            'serviceOriginalSha256': canonical_digest(SERVICE_ORIGINAL),
            'serviceDerivedSha256': canonical_digest(SERVICE_DERIVED),
            'originalProvidersPreserved': True, 'addedEntries': sorted(OWN_CLASSES | {METADATA}),
            'unrelatedEntriesPreserved': len(preserved), 'unrelatedEntryPayloadsPreserved': True}


def source_inputs(repo):
    repo = Path(repo).absolute()
    require(rel(repo, MODULE).resolve() == Path(__file__).resolve(), 'Loaded diagnostic builder differs from repository')
    require(Path(bounded_process.__file__).resolve() == rel(repo, 'work/network-pair-cold-glue/bounded_process.py'), 'Loaded process runner differs from repository')
    require(Path(refreshed.__file__).resolve() == rel(repo, 'work/network-pair-cold-glue/refreshed_candidate.py'), 'Loaded full-proof validator differs from repository')
    pins = [exact_pin(repo, MODULE), exact_pin(repo, 'work/network-pair-cold-glue/bounded_process.py'),
            exact_pin(repo, 'work/network-pair-cold-glue/refreshed_candidate.py')]
    for name, expected in SOURCE_SHA.items(): pins.append(exact_pin(repo, SOURCES + '/' + name, expected))
    require({p.name for p in rel(repo, SOURCES).iterdir()} == set(SOURCE_SHA), 'Unexpected diagnostic source inventory')
    return pins


def compiler_inputs(consumer):
    jdk = rel(consumer, 'work/api1/.toolchains/jdk-21.0.12.1+1')
    compiler = [exact_pin(consumer, jdk / name, expected) for name, expected in JDK_FILES.items()]
    dependencies = [exact_pin(consumer, 'work/api1/source-workspace/pinned-build-maven/' + name, expected)
                    for name, expected in DEPENDENCIES.items()]
    return jdk, compiler, dependencies


def compiler_command(consumer, root, jdk, dependencies, sources):
    return [str(jdk / 'bin/javac'), '-J-Xmx128m', '-J-XX:ActiveProcessorCount=2',
            '--release', '21', '-proc:none', '-cp', ':'.join(str(rel(consumer, p['path'])) for p in dependencies),
            '-d', str(root / 'classes'), *[str(rel(consumer, row['path'])) for row in sources]]


def diagnostic_metadata(role, baseline, sources, compiler, proof_pins):
    return {'schema': RECEIPT_SCHEMA, 'target': role, 'diagnostic_only': True, **SCOPE,
            'baseline_acceptance': False, 'runtimeAcceptance': False,
            'baselineSha256': baseline['sha256'],
            'sourceHashes': {r['path'].rsplit('/', 1)[-1]: r['sha256'] for r in sources},
            'compilerHashes': {r['path']: r['sha256'] for r in compiler},
            'fullBuildProofSha256': proof_pins[1]['sha256']}


def compile_classes(consumer, root, jdk, dependencies, sources, deadline):
    remaining(deadline)
    classes = root / 'classes'; classes.mkdir()
    stdout = root / 'compile.stdout.txt'; stderr = root / 'compile.stderr.txt'
    command = compiler_command(consumer, root, jdk, dependencies, sources)
    timeout = min(60, remaining(deadline))
    env = {'PATH': str(jdk / 'bin') + ':/usr/bin:/bin', 'JAVA_HOME': str(jdk),
           'HOME': str(root), 'TMPDIR': str(root), 'LANG': 'C.UTF-8'}
    try:
        with stdout.open('xb') as out, stderr.open('xb') as err:
            process = bounded_process.run(command, cwd=root, env=env, stdout=out, stderr=err, timeout=timeout)
        remaining(deadline)
        require(process.returncode == 0, 'Diagnostic source compilation failed')
        require(stdout.stat().st_size + stderr.stat().st_size <= 65536, 'Compiler output exceeds bound')
        emitted = {}
        for path in classes.rglob('*'):
            require(not path.is_symlink(), 'Redirected compiler output')
            if path.is_file(): emitted[path.relative_to(classes).as_posix()] = path.read_bytes()
        require(set(emitted) == REPLACEMENTS | OWN_CLASSES, 'Compiler emitted unexpected classes')
        require({n: canonical_digest(p) for n, p in emitted.items()} == EXPECTED_CLASS_SHA, 'Compiler output differs from reviewed pinned reference')
        return emitted, {'exitCode': 0, 'timeoutSeconds': timeout, 'inheritedDeadline': True,
                         'heapMiB': 128, 'activeProcessors': 2, 'javaRelease': 21,
                         'command': [arg.replace(str(Path(consumer).absolute()), '${CONSUMER}') for arg in command],
                         'stdout': exact_pin(consumer, stdout), 'stderr': exact_pin(consumer, stderr),
                         'classHashes': {n: canonical_digest(p) for n, p in sorted(emitted.items())}}
    finally:
        shutil.rmtree(classes)


def _proof(consumer, profile, build_proof):
    profile = rel(consumer, profile); build_proof = rel(consumer, build_proof)
    proof = refreshed.validate_full_build(consumer, profile.relative_to(consumer).as_posix(),
                                          build_proof.relative_to(consumer).as_posix())
    require(proof['artifacts']['fml']['sha256'] == FIXED_FML_SHA, 'Wrong unconfigured Unified FML base')
    return proof, [exact_pin(consumer, profile), exact_pin(consumer, build_proof)]


def execute(repo, consumer, *, deadline, profile, build_proof):
    """Return the absolute supervisor manifest Path. Never grants runtime acceptance."""
    return build(repo, consumer, deadline=deadline, profile=profile, build_proof=build_proof)


def build(repo, consumer, *, deadline, profile=refreshed.PROFILE_PATH,
          build_proof=refreshed.PROOF_PATH, output_relative=OUTPUT):
    repo = Path(repo).absolute(); consumer = Path(consumer).absolute()
    remaining(deadline)
    proof, proof_pins = _proof(consumer, profile, build_proof) # Mandatory BEFORE deriving either artifact.
    remaining(deadline)
    repo_pins = source_inputs(repo)
    jdk, compiler, dependencies = compiler_inputs(consumer)
    native = rel(consumer, dependencies[0]['path'])
    unified = refreshed.check_pin(consumer, proof['artifacts']['fml'])
    bases = {'native': exact_pin(consumer, native, NATIVE_SHA),
             'unified': exact_pin(consumer, unified, FIXED_FML_SHA)}
    for row in bases.values(): read_archive(rel(consumer, row['path']))
    root = rel(consumer, output_relative)
    require(not root.exists(), 'Stale diagnostic output root refused')
    root.mkdir(parents=True)
    source_root = root / 'sources'; source_root.mkdir()
    source_pins = []
    for name in SOURCE_SHA:
        data = rel(repo, SOURCES + '/' + name).read_bytes()
        if name == 'CommonLaunchHandler.java':
            anchor = b'        var args = preLaunch(arguments, gameLayer);\n'
            require(data.count(anchor) == 1, 'Launch hook anchor changed')
            data = data.replace(anchor, anchor + b'        net.neoforged.fml.loading.diagnostic.ProcessStartDiagnosticLaunch.startOrThrow();\n')
            require(canonical_digest(data) == HOOK_SOURCE_SHA, 'Derived launch source changed')
        path = source_root / name
        with path.open('xb') as stream: stream.write(data)
        source_pins.append(exact_pin(consumer, path))
    classes, compilation = compile_classes(consumer, root, jdk, dependencies, source_pins, deadline)
    receipt_rows = []
    for role in ('native', 'unified'):
        remaining(deadline)
        target = root / role; target.mkdir()
        artifact = target / ARTIFACT_NAMES[role]
        metadata = diagnostic_metadata(role, bases[role], source_pins, compiler, proof_pins)
        comparison = archive_derivative(rel(consumer, bases[role]['path']), artifact, classes, metadata)
        receipt = dict(metadata, baseline=bases[role], artifact=exact_pin(consumer, artifact),
                       originalSourceHashes=SOURCE_SHA, sources=source_pins, repoPins=repo_pins,
                       compiler=compiler, dependencies=dependencies, proofPins=proof_pins,
                       fullBuildInputPins=proof['inputPins'], compilation=compilation,
                       archiveComparison=comparison, archiveMetadata=metadata,
                       gameLaunched=False, baselineUnchanged=True, temporaryClassesRemoved=True)
        receipt_rows.append(refreshed.save(consumer, (target / 'build-receipt.json').relative_to(consumer).as_posix(), receipt))
    # Revalidate the full original proof and every input after compilation/packaging.
    again, again_pins = _proof(consumer, profile, build_proof)
    require(again == proof and again_pins == proof_pins, 'Original refreshed proof changed while deriving')
    for row in [*bases.values(), *compiler, *dependencies, *source_pins]: refreshed.check_pin(consumer, row)
    require(source_inputs(repo) == repo_pins, 'Diagnostic source changed while deriving')
    remaining(deadline)
    manifest = {'schema': SCHEMA, 'diagnostic_only': True, 'baseline_acceptance': False,
                'build_receipts': [dict(row, path=str(rel(consumer, row['path']))) for row in receipt_rows]}
    path = root / 'manifest.json'
    refreshed.save(consumer, path.relative_to(consumer).as_posix(), manifest)
    return path


def compiler_log_input_pins(consumer, compile_receipt, build_root):
    """Revalidate all observations; export only nonempty files as runtime pins.

    Silent javac stdout/stderr are legitimate zero-byte observations, not launch
    inputs. Their exact paths/sizes/hashes remain bound inside the nonempty sealed
    build receipts, and are checked on every validation. Never blanket-filter the
    provenance closure: other zero-byte inputs must still fail strict admission.
    """
    logs = []
    for key in ('stdout', 'stderr'):
        row = compile_receipt[key]
        require(type(row.get('bytes')) is int and row['bytes'] >= 0,
                'Invalid compiler log size')
        require(row == exact_pin(consumer, build_root / ('compile.' + key + '.txt')),
                'Changed compiler log pin')
        logs.append(row)
    require(sum(row['bytes'] for row in logs) <= 65536, 'Compiler output exceeds bound')
    return [row for row in logs if row['bytes'] > 0]


def validate(repo, consumer, manifest, profile, build_proof):
    """Rehash full proof, sources, toolchain, dependencies and every archive payload."""
    repo = Path(repo).absolute(); consumer = Path(consumer).absolute()
    proof, proof_pins = _proof(consumer, profile, build_proof)
    repo_pins = source_inputs(repo)
    jdk, compiler, dependencies = compiler_inputs(consumer)
    manifest_path = rel(consumer, manifest); value = json.loads(manifest_path.read_text())
    require(set(value) == {'schema', 'diagnostic_only', 'baseline_acceptance', 'build_receipts'}
            and value['schema'] == SCHEMA and value['diagnostic_only'] is True
            and value['baseline_acceptance'] is False, 'Invalid diagnostic manifest')
    rows = value['build_receipts']
    require(isinstance(rows, list) and len(rows) == 2 and rows[0]['path'] != rows[1]['path'], 'Exactly two distinct ordered receipts required')
    receipts = []; artifacts = {}; pins = [exact_pin(consumer, manifest_path)]
    for role, row in zip(('native', 'unified'), rows):
        require(set(row) == {'path', 'bytes', 'sha256'} and Path(row['path']).is_absolute(), 'Manifest needs absolute receipt pins')
        portable_row = exact_pin(consumer, row['path'])
        require(dict(portable_row, path=str(rel(consumer, row['path']))) == row, 'Changed receipt pin')
        receipt_path = rel(consumer, row['path'])
        build_root = receipt_path.parent.parent
        require(receipt_path.name == 'build-receipt.json' and receipt_path.parent.name == role
                and manifest_path == build_root / 'manifest.json', 'Mixed/stale diagnostic output roots')
        receipt = json.loads(receipt_path.read_text())
        require(receipt['schema'] == RECEIPT_SCHEMA and receipt['target'] == role
                and receipt['diagnostic_only'] is True and receipt['baseline_acceptance'] is False
                and receipt['runtimeAcceptance'] is False and receipt['gameLaunched'] is False,
                'Receipt cannot grant baseline/runtime acceptance')
        require(receipt['proofPins'] == proof_pins and receipt['fullBuildInputPins'] == proof['inputPins']
                and receipt['repoPins'] == repo_pins and receipt['compiler'] == compiler
                and receipt['dependencies'] == dependencies, 'Changed diagnostic provenance')
        expected_base = dependencies[0] if role == 'native' else proof['artifacts']['fml']
        require(receipt['baseline'] == expected_base, 'Wrong diagnostic base binding')
        require(receipt['baselineSha256'] == (NATIVE_SHA if role == 'native' else FIXED_FML_SHA), 'Wrong original FML hash')
        require(receipt['originalSourceHashes'] == SOURCE_SHA, 'Original sources changed')
        expected_source_hashes = dict(SOURCE_SHA, **{'CommonLaunchHandler.java': HOOK_SOURCE_SHA})
        require({r['path'].rsplit('/', 1)[-1]: r['sha256'] for r in receipt['sources']} == expected_source_hashes,
                'Compilation source bytes differ')
        expected_sources = [exact_pin(consumer, build_root / 'sources' / name, expected_source_hashes[name])
                            for name in SOURCE_SHA]
        require(receipt['sources'] == expected_sources, 'Changed compilation source paths/order')
        expected_metadata = diagnostic_metadata(role, receipt['baseline'], expected_sources, compiler, proof_pins)
        require(receipt['archiveMetadata'] == expected_metadata
                and all(type(receipt.get(key)) is type(value) and receipt.get(key) == value
                        and type(receipt['archiveMetadata'].get(key)) is type(value)
                        for key, value in expected_metadata.items()),
                'Changed embedded/top-level diagnostic metadata')
        baseline = refreshed.check_pin(consumer, receipt['baseline'])
        artifact = refreshed.check_pin(consumer, receipt['artifact'])
        require(artifact == receipt_path.parent / ARTIFACT_NAMES[role] and artifact != baseline, 'Diagnostic output masquerades as locked baseline')
        comparison = compare_derivative(baseline, artifact, receipt['archiveMetadata'])
        require(comparison == receipt['archiveComparison'], 'Changed archive comparison')
        require(receipt['compilation']['classHashes'] == EXPECTED_CLASS_SHA, 'Compiled class reference differs')
        for name, digest in receipt['compilation']['classHashes'].items():
            require(comparison['newEntryHashes'].get(name) == digest, 'Compiled class binding changed')
        require(set(receipt['compilation']['classHashes']) == REPLACEMENTS | OWN_CLASSES,
                'Incomplete compiled class evidence')
        require(receipt['compilation']['exitCode'] == 0 and receipt['compilation']['inheritedDeadline'] is True
                and 0 < receipt['compilation']['timeoutSeconds'] <= 60, 'Invalid bounded compiler receipt')
        compile_receipt = receipt['compilation']
        expected_command = [arg.replace(str(consumer), '${CONSUMER}') for arg in
                            compiler_command(consumer, build_root, jdk, dependencies, expected_sources)]
        require(compile_receipt['command'] == expected_command and compile_receipt['heapMiB'] == 128
                and compile_receipt['activeProcessors'] == 2 and compile_receipt['javaRelease'] == 21,
                'Changed exact compiler command/bounds')
        log_input_pins = compiler_log_input_pins(consumer, compile_receipt, build_root)
        require(receipt['baselineUnchanged'] is True and receipt['temporaryClassesRemoved'] is True
                and not (build_root / 'classes').exists(), 'Stale compiler output remains')
        pins.extend([portable_row, receipt['baseline'], receipt['artifact'], *receipt['sources'],
                     *log_input_pins])
        receipts.append(receipt); artifacts[role] = artifact
    pins.extend([*proof_pins, *proof['inputPins'], *compiler, *dependencies])
    unique = {}
    for row in pins:
        require(type(row['bytes']) is int and row['bytes'] >= 1,
                'Runtime provenance input must be nonempty')
        require(row['path'] not in unique or unique[row['path']] == row, 'Conflicting provenance pin')
        refreshed.check_pin(consumer, row); unique[row['path']] = row
    return {'receipts': receipts, 'artifacts': artifacts,
            'inputPins': [unique[name] for name in sorted(unique)], 'repoPins': repo_pins}
