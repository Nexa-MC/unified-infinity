"""Additive native Quilt staging, never a compiler or game/runtime acceptance gate.

The caller must independently review the actual build and supply its exact closure
hashes, independently rederive ``before`` from the source-owned fresh assembler,
and pass that assembler's command, not values trusted from our receipt. This
module checks structural/source binding only. Recheck immediately before launch.
Nothing here modifies the passing assembler or starts a JVM.
"""
from pathlib import Path, PurePosixPath
import copy
import hashlib
import importlib.util
import json
import os
import re
import shutil
import stat
import struct
import sys
import zipfile

ARTIFACT_NAME = 'unified-native-quilt-probe-0.1.0.jar'
TRANSPORT_NAME = 'fabric-network-control-0.1.0.jar'
TRANSPORT_SHA256 = 'cd02f33e8110580802f1d9ec043dcd7c1a2e183ae9051654c950e4f6a65e4df8'
TRANSPORT_SOURCE_SHA256 = '6a7e1afe7f405a2d6a7075f283067d9efa5b4e72467e31e76240fbe7cadff4bf'
LEGACY_PROBE_NAME = 'network-control-probe-0.1.1.jar'
LEGACY_PROBE_SHA256 = '791f6c303475ad9d32baaacc98f0350c027d6efe826dcd5aa9dc99a81da2918a'
MOD_ID = 'unified-quilt-probe'
PHASE_PROPERTY = '-Dunified.quiltProbe.phase='
BUNDLE_SCHEMA = 'quilt-lifecycle-staging-bundle-v1'
REVIEW_SCHEMA = 'independently-reviewed-quilt-staging-closure-v1'
REVIEW_SCOPE = 'SOURCE_ARTIFACT_CLOSURE_ONLY_NOT_COMPILE_OR_RUNTIME_ACCEPTANCE'
RECEIPT_SCHEMA = 'quilt-lifecycle-staging-assembly-v1'
PHASE_POLICY_SCHEMA = 'quilt-lifecycle-phase-policy-v1'
POLICY_ENTRY = 'META-INF/unified-admission/installation.json'
ASSEMBLER_SHA256 = '07148f3909828a55ee9698a8ed9d96ad6bada651226ab1bf1fdff858c703b37a'
VALIDATOR_SHA256 = 'a2ba610d504b73160cdd124e399df48d9b8c196c9591f43ab82c6b14729f5451'
SOURCE_PREFIX = 'four-loader/quilt-probe/'
SHA = re.compile(r'[0-9a-f]{64}')
FLAGS = {'diagnostic_only': True, 'baseline_acceptance': False,
         'game_acceptance': False, 'full_api_acceptance': False,
         'game_launched': False, 'jvm_started': False}
SOURCE_HASHES = {
    'README.md': (3622, 'da5118d05e926f8a9c40a2e03581cb80580282ae284362705f151b9235be585c'),
    'build.py': (3123, 'a29e546d804ec9fd3e31d1ce87599cba0b1b2babd02547866f35961739b19ee4'),
    'build/build-report.json': (1584, '1e533c17b2021860f9544a9be3f66254630d705ce8d93deb64879e5869d280f4'),
    'resources/infinity_native_quilt_probe.mixins.json': (147, '96f9e6307d03383409137a93d2404cd3a4ebc0238432df37daa1ca0fbbccd4b9'),
    'resources/native-quilt-proof.txt': (31, '34bcc75c0355a9c1e8a15cd6ddd852b51c6f65b351e0456d9bc269f5eb343657'),
    'resources/quilt.mod.json': (1065, '8f5c209e656228a23a994f4511c830c249942136f16e358d2ca0e2e12e925adf'),
    'src/dev/infinity/quiltprobe/ClientProbe.java': (494, '60fd1b6f920d0edcffea2dded0654b7f3396206948cdd8a1f5eb67ad5263234f'),
    'src/dev/infinity/quiltprobe/QuiltProbe.java': (7332, 'd794d5291aff5e095d33dd54f7795ae3addaaca785eb2da337fb42c3b3bed82f'),
    'src/dev/infinity/quiltprobe/mixin/TickMixin.java': (631, '632dc968592cf2a4a3388e35fb78e70ed1798073218791e899025b5187512916'),
}
CLASS_NAMES = {
    'dev/infinity/quiltprobe/ClientProbe', 'dev/infinity/quiltprobe/QuiltProbe',
    'dev/infinity/quiltprobe/QuiltProbe$AutomaticEvents',
    'dev/infinity/quiltprobe/QuiltProbe$ProbeData',
    'dev/infinity/quiltprobe/mixin/TickMixin',
}
RESOURCE_NAMES = {'quilt.mod.json', 'native-quilt-proof.txt', 'infinity_native_quilt_probe.mixins.json'}


def require(value, message):
    if not value:
        raise ValueError(message)


def exact(value, keys, label):
    require(type(value) is dict and set(value) == set(keys), 'Invalid ' + label)


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode('ascii')


def digest(data):
    return hashlib.sha256(data).hexdigest()


def root_path(root):
    root = Path(root).absolute()
    require(root.is_dir() and root.resolve() == root, 'Canonical existing consumer required')
    return root


def local(root, value):
    require(type(value) is str and value and '\\' not in value, 'Invalid portable path')
    path = PurePosixPath(value)
    require(not path.is_absolute() and '..' not in path.parts and path.as_posix() == value,
            'Noncanonical/uncontained portable path')
    result = root / value
    require(result.resolve() == result, 'Redirected path refused')
    return result


def absolute(root, value):
    require(type(value) is str, 'Absolute path string required')
    path = Path(value)
    require(path.is_absolute() and path.is_relative_to(root) and str(path) == value,
            'Noncanonical/outside consumer path')
    return local(root, path.relative_to(root).as_posix())


def pin(root, path):
    path = absolute(root, str(path))
    info = path.stat()
    require(stat.S_ISREG(info.st_mode) and 0 <= info.st_size <= 1024 * 1024 * 1024,
            'Bounded regular file required')
    sha = hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            sha.update(chunk)
    after = path.stat()
    require((after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns) ==
            (info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns), 'Input changed during hashing')
    return {'path': path.relative_to(root).as_posix(), 'bytes': info.st_size, 'sha256': sha.hexdigest()}


def absolute_pin(root, path):
    row = pin(root, path)
    return dict(row, path=str(local(root, row['path'])))


def check(root, row):
    exact(row, ('path', 'bytes', 'sha256'), 'file pin')
    require(type(row['bytes']) is int and row['bytes'] >= 0 and type(row['sha256']) is str
            and SHA.fullmatch(row['sha256']), 'Strict file pin required')
    path = local(root, row['path'])
    require(pin(root, path) == row, 'Changed source/build input')
    return path


def check_absolute(root, row):
    exact(row, ('path', 'bytes', 'sha256'), 'absolute file pin')
    path = absolute(root, row['path'])
    portable = dict(row, path=path.relative_to(root).as_posix())
    check(root, portable)
    return path


def load(path, maximum=4 * 1024 * 1024):
    require(path.stat().st_size <= maximum, 'JSON bound exceeded')
    def pairs(rows):
        result = {}
        for key, value in rows:
            require(key not in result, 'Duplicate JSON key')
            result[key] = value
        return result
    def invalid(_):
        raise ValueError('Nonfinite JSON value')
    return json.loads(path.read_bytes(), object_pairs_hook=pairs, parse_constant=invalid)


def _class_identity(data, expected):
    """Parse enough class structure to reject mislabeled classes; no ABI claim."""
    require(len(data) >= 12 and data[:4] == b'\xca\xfe\xba\xbe'
            and struct.unpack_from('>HH', data, 4) == (0, 65), 'Expected Java 21 class')
    count = struct.unpack_from('>H', data, 8)[0]
    pool = {}; offset = 10; index = 1
    try:
        while index < count:
            tag = data[offset]; offset += 1
            if tag == 1:
                length = struct.unpack_from('>H', data, offset)[0]; offset += 2
                require(offset + length <= len(data), 'Truncated class UTF8')
                pool[index] = data[offset:offset + length]; offset += length
            elif tag == 7:
                pool[index] = struct.unpack_from('>H', data, offset)[0]; offset += 2
            elif tag in (8, 16, 19, 20): offset += 2
            elif tag in (3, 4, 9, 10, 11, 12, 17, 18): offset += 4
            elif tag in (5, 6): offset += 8; index += 1
            elif tag == 15: offset += 3
            else: raise ValueError('Unsupported class constant tag')
            require(offset <= len(data), 'Truncated class pool')
            index += 1
        this_class = struct.unpack_from('>H', data, offset + 2)[0]
        require(pool[pool[this_class]] == expected.encode('ascii'), 'Wrong class identity')
    except (IndexError, KeyError, struct.error) as error:
        raise ValueError('Malformed class identity') from error
    require(not any(b'net/fabricmc/' in value or b'net/neoforged/' in value
                    for value in pool.values() if type(value) is bytes),
            'Foreign loader API reference')


def verify_archive(artifact, source_root):
    expected_files = {name + '.class' for name in CLASS_NAMES} | RESOURCE_NAMES | {'META-INF/MANIFEST.MF'}
    allowed_dirs = {str(parent) + '/' for name in expected_files
                    for parent in PurePosixPath(name).parents if str(parent) != '.'}
    with zipfile.ZipFile(artifact) as archive:
        infos = archive.infolist()
        require(1 <= len(infos) <= 64, 'Archive inventory bound')
        names = [row.filename for row in infos]
        require(len(names) == len(set(names)), 'Duplicate archive entry')
        files = set(); total = 0
        for info in infos:
            name = info.filename; path = PurePosixPath(name)
            canonical_name = path.as_posix() + ('/' if info.is_dir() else '')
            require(name and not path.is_absolute() and '..' not in path.parts and '\\' not in name
                    and canonical_name == name, 'Unsafe archive member')
            mode = stat.S_IFMT(info.external_attr >> 16)
            require(mode in (0, stat.S_IFREG, stat.S_IFDIR) and not info.flag_bits & 1,
                    'Redirected/encrypted archive member')
            require((info.is_dir() and name in allowed_dirs and info.file_size == 0)
                    or (not info.is_dir() and name in expected_files and mode != stat.S_IFDIR),
                    'Foreign or fallback archive entry')
            total += info.file_size
            require(info.file_size <= 2 * 1024 * 1024 and total <= 16 * 1024 * 1024,
                    'Archive payload bound')
            if not info.is_dir(): files.add(name)
        require(files - {'META-INF/MANIFEST.MF'} == expected_files - {'META-INF/MANIFEST.MF'},
                'Exact native resource/class roster required')
        for name in RESOURCE_NAMES:
            require(archive.read(name) == (source_root / 'resources' / name).read_bytes(),
                    'Native resource differs from original source')
        for name in CLASS_NAMES:
            _class_identity(archive.read(name + '.class'), name)
        if 'META-INF/MANIFEST.MF' in files:
            manifest = archive.read('META-INF/MANIFEST.MF').decode('ascii')
            lines = [line for line in manifest.splitlines() if line]
            require(lines and lines[0] == 'Manifest-Version: 1.0'
                    and len(lines) <= 2 and (len(lines) == 1 or lines[1].startswith('Created-By: ')),
                    'Unexpected executable/implicit classpath manifest')
    metadata = load(source_root / 'resources/quilt.mod.json', 16384)
    require(metadata['schema_version'] == 1 and type(metadata['schema_version']) is int
            and metadata['quilt_loader']['id'] == MOD_ID
            and metadata['quilt_loader']['intermediate_mappings'] == 'net.fabricmc:intermediary',
            'Native Quilt descriptor identity changed')


def _compile_references(root, report, closure, source_manifest):
    """Bind external receipt references, never interpret status as proof of build."""
    require(report.get('diagnosticOnly') is True and report.get('runtimeAcceptance') is False
            and report.get('gameLaunched') is False, 'Compile receipt cannot claim runtime acceptance')
    def visit(value, trail=()):
        if type(value) is list:
            for item in value: visit(item, trail)
        elif type(value) is dict:
            if 'path' in value and 'sha256' in value:
                if trail and trail[0] in ('classFiles', 'jarEntries'):
                    return  # Archive-relative inventories checked against original artifact below.
                path = value['path']
                if trail and trail[0] == 'sourceFiles':
                    path = str(local(source_manifest.parent, path))
                target = absolute(root, path)
                row = closure.get(target.relative_to(root).as_posix())
                require(row is not None and row['sha256'] == value['sha256']
                        and ('bytes' not in value or type(value['bytes']) is int and row['bytes'] == value['bytes']),
                        'Compile receipt references input outside reviewed closure')
            for key, item in value.items(): visit(item, trail + (key,))
    visit(report)


def _compile_inventories(report, artifact, source):
    require(report.get('sourceFiles') == source['files'], 'Compile source inventory changed')
    with zipfile.ZipFile(artifact) as archive:
        entries = [{'path': info.filename, 'bytes': info.file_size,
                    'sha256': digest(archive.read(info.filename))}
                   for info in archive.infolist() if not info.is_dir()]
    entries.sort(key=lambda r:r['path'])
    classes = [dict(row, majorVersion=65) for row in entries if row['path'].endswith('.class')]
    require(report.get('jarEntries') == entries and report.get('classFiles') == classes,
            'Compile archive/class inventory changed')


def verify_source_binding(root, bundle_pin, *, validated_provenance):
    """Structural gate only. Reviewed hashes MUST come from independent review.

    No boolean/optional bypass and no reading a bundle's own claims as approval.
    The full compile result (including toolchain manifest members) must already be
    reviewed by its owner; this function cannot establish successful compilation.
    """
    root = root_path(root)
    hash_fields = ('bundle_sha256', 'artifact_sha256', 'source_manifest_sha256',
                   'compile_receipt_sha256', 'closure_sha256')
    exact(validated_provenance, ('schema', 'scope', 'source_namespace', 'artifact_namespace', *hash_fields),
          'independently validated provenance')
    require(validated_provenance['schema'] == REVIEW_SCHEMA and validated_provenance['scope'] == REVIEW_SCOPE
            and validated_provenance['source_namespace'] == 'intermediary'
            and validated_provenance['artifact_namespace'] == 'intermediary'
            and all(type(validated_provenance[k]) is str and SHA.fullmatch(validated_provenance[k])
                    for k in hash_fields), 'Independently reviewed intermediary closure required')
    bundle_path = check(root, bundle_pin)
    require(bundle_pin['sha256'] == validated_provenance['bundle_sha256'], 'Reviewed bundle identity changed')
    bundle = load(bundle_path)
    exact(bundle, ('schema', 'artifact', 'source_manifest', 'compile_receipt', 'inputs', *FLAGS), 'native Quilt bundle')
    require(bundle['schema'] == BUNDLE_SCHEMA and all(type(bundle[k]) is type(v) and bundle[k] == v for k,v in FLAGS.items()),
            'Bundle cannot claim runtime/baseline/API acceptance')
    require(type(bundle['inputs']) is list and 1 <= len(bundle['inputs']) <= 2048, 'Bounded closure required')
    closure = {}; identities = {}
    for row in bundle['inputs']:
        path = check(root, row); info = path.stat(); inode = (info.st_dev, info.st_ino)
        require(row['path'] not in closure and inode not in identities and path != bundle_path,
                'Duplicate/aliased closure input')
        closure[row['path']] = row; identities[inode] = row['path']
    require(bundle['inputs'] == sorted(bundle['inputs'], key=lambda row: row['path'])
            and digest(canonical(bundle['inputs'])) == validated_provenance['closure_sha256'],
            'Reviewed closure identity changed')
    paths = {}
    for key in ('artifact', 'source_manifest', 'compile_receipt'):
        paths[key] = check(root, bundle[key])
        require(closure.get(bundle[key]['path']) == bundle[key]
                and bundle[key]['sha256'] == validated_provenance[key + '_sha256'],
                'Reviewed artifact/source/receipt identity changed')
    require(len(set(paths.values())) == 3 and paths['artifact'].name == ARTIFACT_NAME
            and paths['source_manifest'].name == 'source-recovery.json', 'Aliased/wrong fixture provenance')
    source = load(paths['source_manifest'])
    require(source.get('status') == 'EXACT_HISTORICAL_SOURCE_EXTRACTED_NOT_COMPILED_OR_RUNTIME_READY'
            and source.get('archiveSha256') == '655c90673ce9f6d1cc0783037fe9a066dfaa774c3f347752f8ece8035c5c1762'
            and all(source.get(k) is False for k in ('originalArtifactLocksChanged', 'ciStarted', 'baselineAcceptance', 'fullApiCompatibility')),
            'Original source recovery manifest required')
    expected_source = [{'path': SOURCE_PREFIX + name, 'bytes': size, 'sha256': sha}
                       for name, (size, sha) in SOURCE_HASHES.items()]
    require(type(source.get('files')) is list and sorted(source['files'], key=lambda r:r['path']) ==
            sorted(expected_source, key=lambda r:r['path']), 'Exact original source roster required')
    source_root = paths['source_manifest'].parent / SOURCE_PREFIX
    observed = set()
    for path in source_root.rglob('*'):
        require(not path.is_symlink(), 'Redirected source inventory')
        if path.is_file(): observed.add(path.relative_to(source_root).as_posix())
    require(observed == set(SOURCE_HASHES), 'Unexpected original source inventory')
    for row in source['files']:
        path = check(paths['source_manifest'].parent, row)
        actual = pin(root, path)
        require(closure.get(actual['path']) == actual, 'Source missing from reviewed closure')
    verify_archive(paths['artifact'], source_root)
    report = load(paths['compile_receipt'])
    empty_logs = {phase['log']['path'] for phase in report.get('phases', [])
                  if type(phase) is dict and type(phase.get('log')) is dict
                  and phase['log'].get('bytes') == 0 and type(phase['log'].get('path')) is str}
    require(all(row['bytes'] > 0 or str(local(root, row['path'])) in empty_logs
                for row in bundle['inputs']), 'Only explicitly pinned phase logs may be empty')
    require(all(bundle[key]['bytes'] > 0 for key in paths), 'Nonempty artifact/source/receipt required')
    _compile_references(root, report, closure, paths['source_manifest'])
    _compile_inventories(report, paths['artifact'], source)
    require(report.get('sourceManifest') == absolute_pin(root, paths['source_manifest']),
            'Compile source manifest structural binding changed')
    artifact_report = report.get('artifact', {})
    require(artifact_report == dict(absolute_pin(root, paths['artifact']), namespace='intermediary'),
            'Compile artifact structural binding changed')
    return {'bundle_pin': copy.deepcopy(bundle_pin), 'bundle': bundle,
            'validated_provenance': copy.deepcopy(validated_provenance), 'inputs': bundle['inputs'], **FLAGS}


def _check_role(root, role):
    require(type(role) is dict and type(role.get('files')) is list, 'Sealed role required')
    game = absolute(root, role['cwd'])
    rows = {}; inodes = set()
    for row in role['files']:
        require(type(row.get('bytes')) is int and row['bytes'] > 0, 'Nonempty sealed role input required')
        path = check_absolute(root, row); info = path.stat(); inode = (info.st_dev, info.st_ino)
        require(row['path'] not in rows and inode not in inodes, 'Duplicate/aliased role input')
        rows[row['path']] = row; inodes.add(inode)
    require(type(role['original_mods']) is list and type(role['managed_mods']) is list, 'Exact mod rosters required')
    mods = [*role['original_mods'], *role['managed_mods'], role['probe_path']]
    require(len(mods) == len(set(mods)) and all(absolute(root, p).parent == game / 'mods' for p in mods),
            'Overlapping/uncontained mod roles')
    require(set(mods) == {str(p) for p in (game / 'mods').iterdir()}, 'Unexpected profile mod entry')
    require(all(path in rows for path in mods), 'Unsealed profile mod')
    return game, rows


def phase_command(assembly_command, phase):
    require(phase in ('create', 'reopen'), 'Exact create/reopen phase required')
    require(type(assembly_command) is list and len(assembly_command) >= 2
            and all(type(token) is str and token and not token.startswith('@') for token in assembly_command)
            and not any(token.startswith('-Dunified.quiltProbe.phase') for token in assembly_command),
            'Fresh flattened assembler command without phase required')
    return [assembly_command[0], PHASE_PROPERTY + phase, *assembly_command[1:]]


def _assembler(root, assembler_pin, validator_pin):
    assembler_path = check_absolute(root, assembler_pin)
    validator_path = check_absolute(root, validator_pin)
    require(assembler_pin['sha256'] == ASSEMBLER_SHA256 and validator_pin['sha256'] == VALIDATOR_SHA256
            and assembler_path.name == 'assemble_installation.py'
            and validator_path == assembler_path.parent / 'validate_launch.py',
            'Exact frozen assembler and validator sources required')
    spec = importlib.util.spec_from_file_location('quilt_staging_original_assembler', assembler_path)
    module = importlib.util.module_from_spec(spec)
    previous = sys.dont_write_bytecode
    try:
        sys.dont_write_bytecode = True
        spec.loader.exec_module(module)
    finally:
        sys.dont_write_bytecode = previous
    return module


def _phase_policy(root, assembler, spec_pin, phase):
    spec = load(check_absolute(root, spec_pin))
    base_policy, args, java = assembler.prepare(spec)
    base_command = [java, *args]
    command = phase_command(base_command, phase)
    policy = copy.deepcopy(base_policy)
    require(base_policy['processArgumentsSha256'] == assembler.v.digest_strings(args),
            'Original assembler argument binding changed')
    policy['processArgumentsSha256'] = assembler.v.digest_strings(command[1:])
    return spec, base_policy, policy, base_command, command


def _configured_entries(derivative, owner, policy):
    with zipfile.ZipFile(derivative) as source, zipfile.ZipFile(owner) as configured:
        before, after = source.namelist(), configured.namelist()
        require(len(before) == len(set(before)) and len(after) == len(set(after))
                and set(before) == set(after), 'Configured BOOT entry roster changed')
        require(source.read(POLICY_ENTRY) == b'{"schema":1,"approved":false}\n',
                'Unconfigured diagnostic derivative required')
        for name in before:
            require(not name.upper().endswith(('.SF', '.RSA', '.DSA', '.EC')), 'Signed derivative refused')
            expected = canonical(policy) + b'\n' if name == POLICY_ENTRY else source.read(name)
            require(configured.read(name) == expected, 'Configured BOOT non-policy/policy bytes changed')


def _phase_receipt(root, *, assembler_pin, validator_pin, spec_pin, derivative_pin,
                   diagnostic_manifest_pin, phase, owner, base_policy, policy):
    return {'schema': PHASE_POLICY_SCHEMA, **FLAGS, 'phase': phase,
            'artifact': str(owner), 'sha256': absolute_pin(root, owner)['sha256'],
            'installationPolicySha256': digest(canonical(policy) + b'\n'),
            'baseArgumentsSha256': base_policy['processArgumentsSha256'],
            'phaseArgumentsSha256': policy['processArgumentsSha256'],
            'originalAssembler': assembler_pin, 'originalValidator': validator_pin,
            'assemblySpec': spec_pin, 'unconfiguredDerivative': derivative_pin,
            'diagnosticManifest': diagnostic_manifest_pin}


def configure_phase_assembly(root, *, assembler_pin, validator_pin, spec_pin, derivative_pin,
                             diagnostic_manifest_pin, phase, receipt_path):
    """Create a fresh source-owned phase BOOT; no JVM and no old-owner overwrite.

    The caller's original diagnostic build validation must precede this function.
    Only processArgumentsSha256 differs from exact frozen prepare() policy output.
    Actual frozen validate_launch validates the configured owner and phase argv.
    """
    root = root_path(root)
    assembler = _assembler(root, assembler_pin, validator_pin)
    derivative = check_absolute(root, derivative_pin)
    check_absolute(root, diagnostic_manifest_pin)
    spec, base_policy, policy, base_command, command = _phase_policy(root, assembler, spec_pin, phase)
    game = absolute(root, policy['gameDirectory'])
    require(game.name in ('server', 'client') and game.parent.name == 'unified',
            'Fresh Unified phase game required')
    owners = [row for row in policy['artifacts'] if row['role'] == 'BOOT_OWNER']
    require(len(owners) == 1 and owners[0]['sha256'] == 'SELF', 'Exact single self-owned BOOT required')
    installation = absolute(root, policy['installationDirectory'])
    owner = local(installation, owners[0]['path'])
    receipt_path = absolute(root, str(receipt_path))
    require(owner.is_relative_to(game) and owner != derivative
            and receipt_path.is_relative_to(game.parent) and not receipt_path.is_relative_to(game),
            'Fresh phase owner/receipt must belong to sibling lane')
    require(not owner.exists() and not owner.is_symlink()
            and not receipt_path.exists() and not receipt_path.is_symlink()
            and not receipt_path.parent.exists(), 'Existing phase owner/receipt output refused')
    with zipfile.ZipFile(derivative) as source:
        names = source.namelist()
        require(len(names) == len(set(names)) and POLICY_ENTRY in names
                and source.read(POLICY_ENTRY) == b'{"schema":1,"approved":false}\n'
                and not any(n.upper().endswith(('.SF', '.RSA', '.DSA', '.EC')) for n in names),
                'Exact unsigned unconfigured derivative required')
        owner.parent.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(owner, 'x', zipfile.ZIP_DEFLATED) as output:
            for name in sorted(names):
                info = zipfile.ZipInfo(name, (1980, 1, 1, 0, 0, 0)); info.compress_type = zipfile.ZIP_DEFLATED
                output.writestr(info, canonical(policy) + b'\n' if name == POLICY_ENTRY else source.read(name))
    _configured_entries(derivative, owner, policy)
    receipt = _phase_receipt(root, assembler_pin=assembler_pin, validator_pin=validator_pin,
        spec_pin=spec_pin, derivative_pin=derivative_pin, diagnostic_manifest_pin=diagnostic_manifest_pin,
        phase=phase, owner=owner, base_policy=base_policy, policy=policy)
    receipt_path.parent.mkdir()
    with receipt_path.open('xb') as stream: stream.write(canonical(receipt) + b'\n')
    receipt_pin = absolute_pin(root, receipt_path)
    checked = assembler.v.validate(receipt_path, receipt_pin['sha256'], command[1:], policy['environment'])
    require(checked['classOwnerCount'] == 1 and checked['gameLaunched'] is False,
            'Original phase launch validation failed')
    report = {**checked, 'schema': PHASE_POLICY_SCHEMA, 'buildReceipt': str(receipt_path),
        'buildReceiptSha256': receipt_pin['sha256'], 'configuredOwner': str(owner),
        'configuredOwnerSha256': receipt['sha256'], 'javaExecutable': command[0],
        'argumentCount': len(command) - 1, 'rawArgumentsStored': False, 'jvmStarted': False,
        'diagnostic_only': True, 'baseline_acceptance': False}
    return base_command, command, report, receipt_pin


def verify_phase_configuration(root, role, *, phase, assembly_command, assembly_receipt_pin):
    """Read-only rederivation using exact frozen prepare/validate sources."""
    root = root_path(root)
    receipt_path = check_absolute(root, assembly_receipt_pin)
    receipt = load(receipt_path)
    require(receipt.get('schema') == PHASE_POLICY_SCHEMA and receipt.get('phase') == phase,
            'Exact phase-policy configuration receipt required')
    assembler = _assembler(root, receipt['originalAssembler'], receipt['originalValidator'])
    derivative = check_absolute(root, receipt['unconfiguredDerivative'])
    check_absolute(root, receipt['diagnosticManifest'])
    spec, base_policy, policy, base_command, command = _phase_policy(root, assembler, receipt['assemblySpec'], phase)
    require(base_command == assembly_command and role['cwd'] == policy['gameDirectory'],
            'Phase configuration differs from independently rederived assembler argv/profile')
    owner = absolute(root, receipt['artifact'])
    expected = _phase_receipt(root, assembler_pin=receipt['originalAssembler'], validator_pin=receipt['originalValidator'],
        spec_pin=receipt['assemblySpec'], derivative_pin=receipt['unconfiguredDerivative'],
        diagnostic_manifest_pin=receipt['diagnosticManifest'], phase=phase, owner=owner,
        base_policy=base_policy, policy=policy)
    require(receipt == expected, 'Phase configuration receipt has unapproved delta')
    _configured_entries(derivative, owner, policy)
    assembly = role['assembly']
    require(role['command'] == (command if assembly.get('schema') == RECEIPT_SCHEMA else base_command),
            'Role command does not match exact phase configuration')
    if assembly.get('schema') == RECEIPT_SCHEMA: assembly = assembly['baseAssembly']
    require(assembly.get('schema') == PHASE_POLICY_SCHEMA and assembly['buildReceipt'] == str(receipt_path)
            and assembly['buildReceiptSha256'] == assembly_receipt_pin['sha256']
            and assembly['configuredOwner'] == str(owner) and assembly['configuredOwnerSha256'] == receipt['sha256'],
            'Role phase configuration binding changed')
    checked = assembler.v.validate(receipt_path, assembly_receipt_pin['sha256'], command[1:], policy['environment'])
    require(checked['classOwnerCount'] == 1 and checked['gameLaunched'] is False,
            'Original phase launch validation failed')
    if role['assembly'].get('schema') == RECEIPT_SCHEMA:
        staged_path = absolute(root, role['assembly']['buildReceipt'])
        assembler.v.validate(staged_path, role['assembly']['buildReceiptSha256'], command[1:], policy['environment'])
    return {'basePolicy': base_policy, 'policy': policy, 'command': command, 'baseCommand': base_command,
            'receipt': receipt, 'receiptPin': assembly_receipt_pin, 'assemblySpec': receipt['assemblySpec']}


def _context(root, before, verified, target, phase, overlay_root, source_role_pin,
             assembly_command, assembly_receipt_pin):
    require(target == 'unified', 'Native Quilt fixture staging is Unified-only')
    source_path = check_absolute(root, source_role_pin)
    source = load(source_path)
    source_game, source_rows = _check_role(root, source)
    game = absolute(root, before['cwd']); overlay = absolute(root, str(overlay_root))
    require(game.name in ('server', 'client') and game == overlay / 'unified' / game.name
            and source_game.name == game.name and source_game.parent.name == 'unified'
            and not overlay.is_relative_to(source_game.parent.parent)
            and not source_game.parent.parent.is_relative_to(overlay), 'Fresh nonoverlapping Unified profile required')
    require(before.get('diagnostic_only') is True and before.get('baseline_acceptance') is False,
            'Diagnostic-only predecessor role required')
    require(before['command'] == assembly_command, 'Role argv differs from rederived assembler command')
    for key in ('original_mods', 'managed_mods'):
        expected = [str(game / Path(p).relative_to(source_game)) for p in source[key]]
        require(before[key] == expected, 'Original/managed mod roster changed before additive staging')
    require(Path(source['probe_path']).name == TRANSPORT_NAME
            and before['probe_path'] == str(game / Path(source['probe_path']).relative_to(source_game)),
            'Unchanged Fabric transport control required')
    before_rows = {row['path']: row for row in before['files']}
    require(len(before_rows) == len(before['files']), 'Duplicate predecessor input')
    for path in [*source['original_mods'], *source['managed_mods'], source['probe_path']]:
        destination = str(game / Path(path).relative_to(source_game))
        require(before_rows.get(destination) == dict(source_rows[path], path=destination),
                'Original/managed/transport input identity changed')
        destination_path = absolute(root, destination)
        require(destination_path.stat().st_ino != Path(path).stat().st_ino
                or destination_path.stat().st_dev != Path(path).stat().st_dev,
                'Profile clone aliases protected source input')
    receipt_path = check_absolute(root, assembly_receipt_pin)
    require(receipt_path.is_relative_to(overlay / 'unified')
            and not receipt_path.is_relative_to(game), 'Fresh base assembly receipt must belong to sibling lane')
    prior_assembly = before['assembly']
    require(type(prior_assembly) is dict and prior_assembly.get('buildReceipt') == str(receipt_path)
            and prior_assembly.get('buildReceiptSha256') == assembly_receipt_pin['sha256'],
            'Predecessor assembly receipt binding changed')
    require(not any(Path(p).name == ARTIFACT_NAME for p in [*source['original_mods'], *source['managed_mods'], source['probe_path']]),
            'Source profile already contains lifecycle fixture')
    verify_phase_configuration(root, before, phase=phase, assembly_command=assembly_command,
                               assembly_receipt_pin=assembly_receipt_pin)
    owner = absolute(root, before['assembly']['configuredOwner'])
    require(before_rows.get(str(owner)) == absolute_pin(root, owner), 'Configured phase BOOT missing from sealed role inputs')
    fixture = game / 'mods' / ARTIFACT_NAME
    return game, fixture


def _expected(root, before, verified, *, target, phase, overlay_root, source_role_pin,
              assembly_command, assembly_receipt_pin):
    game, fixture = _context(root, before, verified, target, phase, overlay_root, source_role_pin,
                             assembly_command, assembly_receipt_pin)
    after = copy.deepcopy(before)
    after['command'] = phase_command(assembly_command, phase)
    after['managed_mods'] = [*before['managed_mods'], str(fixture)]
    fixture_pin = dict(verified['bundle']['artifact'], path=str(fixture))
    after['files'] = sorted([*before['files'], fixture_pin], key=lambda r:r['path'])
    receipt_path = game.parent / (game.name + '-quilt-' + phase + '-assembly.json')
    projection = copy.deepcopy(after); projection.pop('assembly')
    receipt = {'schema': RECEIPT_SCHEMA, **FLAGS, 'target': target, 'phase': phase,
               'sourceRole': source_role_pin, 'baseAssemblyReceipt': assembly_receipt_pin,
               'bundle': verified['bundle_pin'], 'validatedProvenance': verified['validated_provenance'],
               'fixture': fixture_pin, 'beforeRoleSha256': digest(canonical(before)),
               'baseCommandSha256': digest(canonical(assembly_command)),
               'commandSha256': digest(canonical(after['command'])),
               'afterRoleWithoutAssemblySha256': digest(canonical(projection)),
               'transportProbeUnchanged': True, 'nativeControlUnchanged': True,
               **{key: load(Path(assembly_receipt_pin['path']))[key]
                  for key in ('artifact', 'sha256', 'installationPolicySha256', 'assemblySpec')}}
    raw = canonical(receipt) + b'\n'
    after['assembly'] = {**copy.deepcopy(before['assembly']), 'schema': RECEIPT_SCHEMA,
                         'baseAssembly': copy.deepcopy(before['assembly']),
                         'buildReceipt': str(receipt_path), 'buildReceiptSha256': digest(raw),
                         'argumentCount': len(after['command']) - 1,
                         'quiltLifecyclePhase': phase, 'diagnostic_only': True,
                         'baseline_acceptance': False, 'gameLaunched': False, 'jvmStarted': False}
    return after, receipt, receipt_path


def stage_unified_fixture(root, before, verified, *, target, phase, overlay_root, source_role_pin,
                          assembly_command, assembly_receipt_pin):
    """Stage one phase into a fresh clone; return new role and honest receipt.

    Create and reopen use separate nonoverlapping profiles. Copying an independently
    authenticated saved world is a separate runtime-owner step, not a bypass here.
    Existing fixture copies or phase receipts are rejected even if byte-identical.
    Only the exact fixture and a new receipt are added; nothing is deleted/rewritten.
    Call for BOTH Unified sides; both must be sealed before a pair can run.
    """
    root = root_path(root)
    require(target == 'unified', 'Native Quilt fixture staging is Unified-only')
    current = verify_source_binding(root, verified['bundle_pin'],
                                    validated_provenance=verified['validated_provenance'])
    require(current == verified, 'Fixture closure changed before staging')
    kwargs = dict(target=target, overlay_root=overlay_root, source_role_pin=source_role_pin,
                  assembly_command=assembly_command, assembly_receipt_pin=assembly_receipt_pin)
    game, fixture = _context(root, before, verified, phase=phase, **kwargs)
    _check_role(root, before)
    observed = set()
    for path in game.rglob('*'):
        require(not path.is_symlink(), 'Redirected fresh profile inventory')
        if path.is_file(): observed.add(str(path))
    require(observed == {r['path'] for r in before['files'] if Path(r['path']).is_relative_to(game)},
            'Fresh profile contains unsealed/stale files')
    after, receipt, receipt_path = _expected(root, before, verified, phase=phase, **kwargs)
    require(not fixture.exists() and not fixture.is_symlink(), 'Stale fixture copy refused')
    require(not receipt_path.exists() and not receipt_path.is_symlink(), 'Stale phase assembly receipt refused')
    artifact = check(root, verified['bundle']['artifact'])
    with fixture.open('xb') as stream:
        stream.write(artifact.read_bytes()); stream.flush(); os.fsync(stream.fileno())
    with receipt_path.open('xb') as stream:
        stream.write(canonical(receipt) + b'\n'); stream.flush(); os.fsync(stream.fileno())
    validate_staged_role(root, before, after, verified, receipt, phase=phase, **kwargs)
    return after, receipt


def validate_staged_role(root, before, after, verified, receipt, *, target, phase, overlay_root,
                         source_role_pin, assembly_command, assembly_receipt_pin):
    """Recheck immediately before launch, with independently rederived base inputs.

    Strict pristine role inputs: unlike the existing runtime sealer this validator
    does NOT silently exempt options.txt or world files. Runtime mutable state is
    outside the sealed input roster and remains the runtime owner's responsibility.
    """
    root = root_path(root)
    require(verify_source_binding(root, verified['bundle_pin'],
            validated_provenance=verified['validated_provenance']) == verified, 'Fixture closure changed after staging')
    expected, expected_receipt, path = _expected(root, before, verified, target=target, phase=phase,
        overlay_root=overlay_root, source_role_pin=source_role_pin,
        assembly_command=assembly_command, assembly_receipt_pin=assembly_receipt_pin)
    require(after == expected and receipt == expected_receipt, 'Unapproved role/receipt delta')
    require(path.read_bytes() == canonical(expected_receipt) + b'\n', 'Stored phase assembly receipt changed')
    _check_role(root, after)
    verify_phase_configuration(root, after, phase=phase, assembly_command=assembly_command,
                               assembly_receipt_pin=assembly_receipt_pin)
    return True


def relocate_role_paths(value, old, new):
    """Exact Linux path-token relocation, including nested path-map keys."""
    if type(value) is dict:
        result = {}
        for key, item in value.items():
            new_key = relocate_role_paths(key, old, new)
            require(new_key not in result, 'Relocation creates duplicate key')
            result[new_key] = relocate_role_paths(item, old, new)
        return result
    if type(value) is list:
        return [relocate_role_paths(item, old, new) for item in value]
    if type(value) is str:
        prefix, text = '', value
        if value.startswith('-D') and '=' in value:
            prefix, text = value.split('=', 1); prefix += '='
        parts = text.split(':')
        return prefix + ':'.join(str(new) + part[len(str(old)):] if part == str(old)
            or part.startswith(str(old) + '/') else part for part in parts)
    return value


def _pristine_role(root, role):
    game, rows = _check_role(root, role)
    require(not (game / 'world').exists(), 'Pristine source profile cannot contain a world')
    observed = set()
    for path in game.rglob('*'):
        require(not path.is_symlink(), 'Redirected pristine profile inventory')
        if path.is_file(): observed.add(str(path))
    require(observed == {path for path in rows if Path(path).is_relative_to(game)},
            'Source profile contains unsealed/stale files')
    return game


def _referenced_pins(root, value):
    """Only explicit pin objects, not arbitrary filenames or directory walks."""
    rows = {}
    def visit(item, installation=None):
        if type(item) is dict:
            if 'installationDirectory' in item:
                installation = absolute(root, item['installationDirectory'])
            if 'path' in item and 'sha256' in item:
                if item['sha256'] != 'SELF':
                    if Path(item['path']).is_absolute(): path = absolute(root, item['path'])
                    elif 'role' in item and installation is not None: path = local(installation, item['path'])
                    else: path = local(root, item['path'])
                    row = absolute_pin(root, path)
                    require(item['sha256'] == row['sha256']
                            and ('bytes' not in item or type(item['bytes']) is int and item['bytes'] == row['bytes']),
                            'Source provenance reference changed')
                    rows[row['path']] = row
            for child in item.values(): visit(child, installation)
        elif type(item) is list:
            for child in item: visit(child, installation)
    visit(value)
    return rows


def _source_user_mods(root, source, spec, inputs, source_role_pin):
    """Authenticate the original producer's historical userMods disposition.

    userMods is not an installation-policy field. The original Fabric overlay
    deliberately retains that pre-overlay copy recipe while deleting only its
    cloned legacy emitter. No missing-file exception is used here: the complete
    predecessor, source fixture, old and current probe identities must agree.
    Returned extra pins are live historical sources, not retired destinations.
    The caller has already run the original complete diagnostic/build validators.
    """
    if 'userMods' not in spec:
        require('beforeRole' not in source.get('ffapiProbeOverlay', {}),
                'Original Fabric overlay requires its complete userMods recipe')
        return None, {}
    game = absolute(root, source['cwd']); side = game.name
    extra = {}
    def sealed(row, portable=False):
        path = check(root, row) if portable else check_absolute(root, row)
        actual = absolute_pin(root, path)
        require(inputs.get(actual['path']) == actual, 'Unsealed original userMods ancestry')
        return path
    def historical(row):
        path = check_absolute(root, row)
        require(row['bytes'] > 0 and path.stat().st_nlink == 1, 'Empty or aliased historical source input')
        require(row['path'] not in inputs or inputs[row['path']] == row,
                'Historical source conflicts with sealed input')
        extra[row['path']] = row
        return path
    overlay = source.get('ffapiProbeOverlay')
    exact(overlay, ('beforeRole', 'receipt', 'bundle'), 'original Fabric overlay ancestry')
    before_path = sealed(overlay['beforeRole']); overlay_path = sealed(overlay['receipt'])
    require(before_path == game.parent / (side + '-pre-ffapi-launch-seal.json')
            and overlay_path == game.parent / (side + '-ffapi-probe-overlay.json'),
            'Original Fabric overlay belongs to another role')
    original = load(sealed(source['baselineRole'])); old = absolute(root, original['cwd'])
    require(old.name == side and old.parent.name == 'unified' and old != game
            and not old.is_relative_to(game) and not game.is_relative_to(old),
            'Distinct same-side original baseline required')
    require(source['baselineRole']['path'] == str(old.parent / (side + '-launch-seal.json'))
            and len({row['path'] for row in original['files']}) == len(original['files']),
            'Baseline role path or file inventory changed')
    prior = original['assembly']
    prior_receipt_path = absolute(root, prior['buildReceipt'])
    prior_pin = absolute_pin(root, prior_receipt_path); sealed(prior_pin)
    require(prior_pin['sha256'] == prior['buildReceiptSha256'], 'Baseline assembly receipt changed')
    prior_receipt = load(prior_receipt_path)
    prior_spec_path = old.parent / (side + '-assembly-spec.json')
    prior_spec_pin = absolute_pin(root, prior_spec_path); sealed(prior_spec_pin)
    require(prior_spec_pin['sha256'] == prior_receipt['assemblySpecSha256'], 'Baseline assembly spec changed')
    require(spec == relocate_role_paths(load(prior_spec_path), old, game),
            'Diagnostic assembly spec differs from exact original recipe')
    # assemble_pairs creates this document after its input-lock. The original
    # configured receipt and spec authenticate it, but the original sealer does
    # not flatten it into inputs. Retain that exact live document in this sibling
    # closure, never invent a path or relax generic reference membership.
    launch_pin = spec['launchSource']
    require(launch_pin['path'] == str(old.parent / (side + '-source-launch.json'))
            and launch_pin['sha256'] == prior_receipt['sourceLaunchSealSha256'],
            'Original launch source differs from baseline receipt/side')
    historical(launch_pin)
    diagnostic_path = game.parent.parent / 'diagnostic-assembly.json'
    sealed(absolute_pin(root, diagnostic_path)); diagnostic = load(diagnostic_path)
    require(diagnostic.get('schema') == 'diagnostic-pair-assembly-v1'
            and diagnostic.get('assemblyRoot') == str(game.parent.parent)
            and diagnostic.get('manifest') == source['diagnosticManifest']
            and diagnostic.get('diagnostic_only') is True
            and all(diagnostic.get(k) is False for k in ('baseline_acceptance', 'gameAcceptance', 'gameLaunched', 'jvmStarted'))
            and diagnostic['groups']['unified']['roles'][side] == source_role_pin,
            'Original diagnostic producer does not bind this source role')
    baseline = load(sealed(diagnostic['baselineAssembly']))
    require(baseline.get('status') == 'REFRESHED_FOUR_ROLE_ASSEMBLY_READY_GAME_UNRUN'
            and baseline.get('assemblyRoot') == str(old.parent.parent)
            and baseline.get('gameLaunched') is False and baseline.get('jvmStarted') is False,
            'Exact original refreshed baseline assembly required')
    assembly_path = sealed(baseline['assemblyResult'])
    require(assembly_path == old.parent.parent / 'assembly-result.json', 'Baseline assembly result belongs elsewhere')
    assembly = load(assembly_path)
    require(assembly.get('status') == 'SOURCE_ASSEMBLED_GAME_UNRUN'
            and assembly.get('gameLaunched') is False and assembly.get('jvmStarted') is False,
            'Original unrun assembly provenance required')
    require(assembly['groups'] == baseline['groups'], 'Baseline producer groups changed')
    group = assembly['groups']['unified']
    require(group['port'] == 25632 and group['roles'][side] == source['baselineRole'],
            'Original source role/group binding changed')
    require(diagnostic['groups']['unified']['sourceFixture'] == group['sourceFixture'],
            'Diagnostic source fixture ancestry changed')
    fixture_path = sealed(group['sourceFixture']); fixture = load(fixture_path)
    require(fixture.get('schema') == 1 and fixture.get('target') == 'unified'
            and fixture.get('port') == 25632 and fixture.get('gameLaunched') is False
            and fixture.get('status') == 'FRESH_PROFILES_PREPARED_NO_LAUNCH',
            'Exact pristine prepared source fixture required')
    profile = fixture['profiles'][side]; prepared = absolute(root, profile['workingDirectory'])
    require(prepared == fixture_path.parent / ('unified-' + side)
            and not prepared.is_relative_to(old) and not old.is_relative_to(prepared)
            and not prepared.is_relative_to(game) and not game.is_relative_to(prepared),
            'Prepared, baseline and diagnostic sources must remain distinct')
    fixture_rows = {row['path']: row for row in profile['files']}
    require(len(fixture_rows) == len(profile['files']), 'Duplicate prepared source file')
    origins = [*profile['original_mods'], profile['probe_path']]
    require(len(origins) == len(set(origins)) and all(absolute(root, path).parent == prepared / 'mods' for path in origins),
            'Wrong-role prepared user-mod origin')
    expected_mods = []
    for origin in origins:
        require(origin in fixture_rows, 'Missing prepared source user-mod pin')
        row = fixture_rows[origin]; historical(row)
        expected_mods.append({'source': origin, 'path': str(game / 'mods' / Path(origin).name), 'sha256': row['sha256']})
    require(spec['userMods'] == expected_mods, 'Historical userMods changed, missing, duplicated or unowned')
    require(source['original_mods'] == [row['path'] for row in expected_mods[:-1]]
            and original['original_mods'] == [str(old / 'mods' / Path(path).name) for path in profile['original_mods']],
            'Original user-mod roster changed')
    legacy = expected_mods[-1]; retired = absolute(root, legacy['path'])
    require(retired == game / 'mods' / LEGACY_PROBE_NAME and legacy['sha256'] == LEGACY_PROBE_SHA256
            and Path(legacy['source']).name == LEGACY_PROBE_NAME
            and original['probe_path'] == str(old / 'mods' / LEGACY_PROBE_NAME),
            'Exact original legacy probe recipe required')
    baseline_probe = absolute_pin(root, Path(original['probe_path'])); historical(baseline_probe)
    require(baseline_probe == dict(fixture_rows[legacy['source']], path=original['probe_path'])
            and baseline_probe in original['files'], 'Baseline legacy copy differs from prepared source')
    require(not retired.exists() and not retired.is_symlink(), 'Retired diagnostic probe must remain absent')
    # The original diagnostic producer appends exactly its two derivative pins.
    manifest = load(sealed(source['diagnosticManifest']))
    exact(manifest, ('schema', 'diagnostic_only', 'baseline_acceptance', 'build_receipts'), 'diagnostic manifest')
    require(manifest['schema'] == 'fml-process-start-diagnostic-v1' and manifest['diagnostic_only'] is True
            and manifest['baseline_acceptance'] is False and len(manifest['build_receipts']) == 2,
            'Exact diagnostic build ancestry required')
    derivatives = []
    for target, row in zip(('native', 'unified'), manifest['build_receipts']):
        path = sealed(row); value = load(path)
        require(path.parent.name == target and path.name == 'build-receipt.json'
                and path.parent.parent == Path(source['diagnosticManifest']['path']).parent
                and value.get('schema') == 'fml-process-start-diagnostic-build-v1'
                and value.get('target') == target and value.get('diagnostic_only') is True
                and all(value.get(k) is False for k in ('baseline_acceptance', 'runtimeAcceptance', 'gameLaunched')),
                'Wrong diagnostic derivative receipt role')
        derivatives.append(absolute_pin(root, sealed(value['artifact'], portable=True)))
    prior_files = []
    owner = absolute(root, source['assembly']['configuredOwner'])
    for row in original['files']:
        moved = dict(row, path=relocate_role_paths(row['path'], old, game))
        prior_files.append(absolute_pin(root, owner) if moved['path'] == str(owner) else moved)
    prior_files.extend(derivatives)
    expected_before = relocate_role_paths(original, old, game)
    scope = {'diagnosticProfile': 'system-report-and-glx-cpu-inventory-skip-v2', 'behavioralChange': True,
             'hardwareScope': 'all-SystemReport-instances-including-crash-reports-and-GLX-CPU-description',
             'nonHardwareFieldsPreserved': True, 'gameJarBytesModified': False}
    expected_before.update(command=source['command'], assembly=source['assembly'],
        files=sorted({row['path']: row for row in prior_files}.values(), key=lambda row: row['path']),
        diagnostic_only=True, baseline_acceptance=False, diagnosticManifest=source['diagnosticManifest'],
        baselineRole=source['baselineRole'], **scope)
    before = load(before_path)
    require(before == expected_before, 'Fabric predecessor differs from independently derived baseline')
    bundle = load(sealed(overlay['bundle'], portable=True))
    exact(bundle, ('schema', 'diagnostic_only', 'baseline_acceptance', 'artifact', 'source_manifest',
                   'build_binding', 'build_result', 'namespace_proof'), 'original Fabric bundle')
    require(bundle['schema'] == 'fabric-ffapi-probe-bundle-v1' and bundle['diagnostic_only'] is True
            and bundle['baseline_acceptance'] is False, 'Original diagnostic Fabric bundle required')
    require(diagnostic.get('ffapiProbeBundle') == {'bundle_pin': overlay['bundle'], 'reviewed': {
        'source_manifest_sha256': TRANSPORT_SOURCE_SHA256, 'artifact_sha256': TRANSPORT_SHA256,
        'namespace_proof_sha256': bundle['namespace_proof']['sha256']}}
        and bundle['source_manifest']['sha256'] == TRANSPORT_SOURCE_SHA256,
        'Fabric bundle differs from original reviewed producer binding')
    for key in ('artifact', 'source_manifest', 'build_binding', 'build_result', 'namespace_proof'):
        sealed(bundle[key], portable=True)
    artifact = absolute_pin(root, check(root, bundle['artifact']))
    require(Path(artifact['path']).name == TRANSPORT_NAME and artifact['sha256'] == TRANSPORT_SHA256,
            'Exact current reviewed Fabric transport artifact required')
    copied = dict(artifact, path=str(game / 'mods' / TRANSPORT_NAME))
    removed = dict(baseline_probe, path=str(retired))
    require(before['probe_path'] == str(retired) and removed in before['files'], 'Retired copy absent from exact predecessor')
    expected_after = copy.deepcopy(before); expected_after['probe_path'] = copied['path']
    expected_after['files'] = sorted([row for row in before['files'] if row['path'] != str(retired)] + [copied],
                                     key=lambda row: row['path'])
    after = copy.deepcopy(source); after.pop('ffapiProbeOverlay')
    require(after == expected_after, 'Original Fabric overlay changed non-probe role data')
    expected_receipt = {'schema': 'unified-fabric-ffapi-probe-overlay-v1', 'target': 'unified',
        'diagnostic_only': True, 'baseline_acceptance': False, 'game_launched': False,
        'native_control_unchanged': True, 'bundle': overlay['bundle'], 'baseline_probe': baseline_probe,
        'removed_diagnostic_copy': removed, 'new_diagnostic_copy': copied,
        'before_role_sha256': digest(canonical(before)), 'after_role_sha256': digest(canonical(after))}
    require(load(overlay_path) == expected_receipt, 'Historical Fabric overlay receipt changed')
    check_absolute(root, copied)
    # New phase specs describe the current transport. Original specs stay intact.
    current = copy.deepcopy(expected_mods)
    current[-1] = {'source': artifact['path'], 'path': copied['path'], 'sha256': artifact['sha256']}
    return current, extra


def _fresh_phase_spec(source, game):
    spec = copy.deepcopy(source['spec'])
    if source['currentUserMods'] is not None: spec['userMods'] = source['currentUserMods']
    return relocate_role_paths(spec, source['game'], game)


def _source_phase_inputs(root, *, source_roles, source_specs, source_inputs, assembler_pin,
                         validator_pin, derivative_pin, diagnostic_manifest_pin):
    exact(source_roles, ('server', 'client'), 'source Unified roles')
    exact(source_specs, ('server', 'client'), 'source Unified specs')
    require(type(source_inputs) is list and 1 <= len(source_inputs) <= 8192, 'Complete passing source closure required')
    inputs = {}
    for row in source_inputs:
        check_absolute(root, row)
        require(row['path'] not in inputs, 'Duplicate source closure input')
        inputs[row['path']] = row
    assembler = _assembler(root, assembler_pin, validator_pin)
    derivative = check_absolute(root, derivative_pin)
    check_absolute(root, diagnostic_manifest_pin)
    for row in [assembler_pin, validator_pin, derivative_pin, diagnostic_manifest_pin,
                *source_roles.values(), *source_specs.values()]:
        require(inputs.get(row['path']) == row, 'Required original input missing from passing source closure')
    result = {}
    for side in ('server', 'client'):
        source = load(check_absolute(root, source_roles[side]))
        spec = load(check_absolute(root, source_specs[side]))
        game = _pristine_role(root, source)
        require(game.name == side and game.parent.name == 'unified'
                and Path(source['probe_path']).name == TRANSPORT_NAME
                and source.get('diagnostic_only') is True and source.get('baseline_acceptance') is False,
                'Pristine passing Unified Fabric source required')
        require(not any(Path(path).name == ARTIFACT_NAME for path in source['managed_mods']),
                'Source role already contains Quilt fixture')
        policy, args, java = assembler.prepare(spec)
        require(source['command'] == [java, *args] and policy['gameDirectory'] == str(game)
                and not any(token.startswith('-Dunified.quiltProbe.phase') for token in source['command']),
                'Source argv differs from original assembler or already has phase')
        assembly = source['assembly']; receipt_path = absolute(root, assembly['buildReceipt'])
        receipt_pin = absolute_pin(root, receipt_path)
        require(receipt_pin['sha256'] == assembly['buildReceiptSha256']
                and inputs.get(receipt_pin['path']) == receipt_pin, 'Source assembly receipt changed/unsealed')
        receipt = load(receipt_path)
        require(receipt.get('assemblySpec') == source_specs[side]
                and receipt.get('unconfiguredDerivative') == derivative_pin
                and receipt.get('diagnosticManifest') == diagnostic_manifest_pin,
                'Source diagnostic spec/derivative/manifest binding changed')
        owner = absolute(root, assembly['configuredOwner'])
        require(owner.is_relative_to(game) and receipt['artifact'] == str(owner)
                and receipt['sha256'] == assembly['configuredOwnerSha256'], 'Source configured owner binding changed')
        _configured_entries(derivative, owner, policy)
        checked = assembler.v.validate(receipt_path, receipt_pin['sha256'], args, policy['environment'])
        require(checked['classOwnerCount'] == 1 and checked['gameLaunched'] is False,
                'Original source role launch validation failed')
        current_mods, historical_inputs = _source_user_mods(root, source, spec, inputs, source_roles[side])
        # Only the typed producer-owned slot is projected. Every other nested
        # path/sha reference retains the existing strict live-file requirement.
        live_spec = {key: value for key, value in spec.items() if key != 'userMods'}
        if current_mods is not None:
            require(receipt.get('sourceLaunch') == spec['launchSource'],
                    'Diagnostic receipt launch source binding changed')
        references = _referenced_pins(root, [source, live_spec, receipt])
        if current_mods is not None: references.update(_referenced_pins(root, current_mods))
        reference_inputs = dict(inputs); reference_inputs.update(historical_inputs)
        require(all(reference_inputs.get(path) == row for path, row in references.items()),
                'Referenced source input missing from passing source closure')
        result[side] = {'role': source, 'spec': spec, 'game': game, 'owner': owner,
                        'currentUserMods': current_mods, 'historicalInputs': historical_inputs}
    require(result['server']['game'].parent == result['client']['game'].parent,
            'Source roles must form one passing Unified pair')
    return result


def _materialized_before(root, source, game, phase, config_receipt_pin):
    before = relocate_role_paths(source['role'], source['game'], game)
    receipt = load(check_absolute(root, config_receipt_pin))
    assembler = _assembler(root, receipt['originalAssembler'], receipt['originalValidator'])
    _, _, policy, command, phase_cmd = _phase_policy(root, assembler, receipt['assemblySpec'], phase)
    owner = absolute(root, receipt['artifact'])
    checked = assembler.v.validate(Path(config_receipt_pin['path']), config_receipt_pin['sha256'], phase_cmd[1:], policy['environment'])
    before['command'] = command
    before['assembly'] = {**checked, 'schema': PHASE_POLICY_SCHEMA, 'buildReceipt': config_receipt_pin['path'],
        'buildReceiptSha256': config_receipt_pin['sha256'], 'configuredOwner': str(owner),
        'configuredOwnerSha256': receipt['sha256'], 'javaExecutable': command[0],
        'argumentCount': len(phase_cmd) - 1, 'rawArgumentsStored': False, 'jvmStarted': False,
        'diagnostic_only': True, 'baseline_acceptance': False}
    files = []
    for row in source['role']['files']:
        path = Path(row['path'])
        if path == source['owner']:
            files.append(absolute_pin(root, owner))
        elif path.is_relative_to(source['game']):
            files.append(dict(row, path=str(game / path.relative_to(source['game']))))
        else:
            files.append(copy.deepcopy(row))
    before['files'] = sorted(files, key=lambda r:r['path'])
    return before, command


def materialize_unified_phase(root, verified, *, phase, overlay_root, source_roles, source_specs,
                              source_inputs, assembler_pin, validator_pin, derivative_pin,
                              diagnostic_manifest_pin):
    """Clone a validated pristine Fabric pair into a fresh phase; never launch.

    Copy every profile input except the old configured BOOT, which is never copied
    or deleted. A fresh BOOT is configured once from the original diagnostic
    derivative. External Fabric ancestry remains explicitly the old source data.
    Both output roles get the native fixture and source-owned phase policy.
    """
    root = root_path(root); phase_command(['placeholder-java', 'placeholder-main'], phase)
    require(verify_source_binding(root, verified['bundle_pin'],
        validated_provenance=verified['validated_provenance']) == verified, 'Fixture closure changed before materialization')
    kwargs = dict(source_roles=source_roles, source_specs=source_specs, source_inputs=source_inputs,
        assembler_pin=assembler_pin, validator_pin=validator_pin, derivative_pin=derivative_pin,
        diagnostic_manifest_pin=diagnostic_manifest_pin)
    sources = _source_phase_inputs(root, **kwargs)
    overlay = absolute(root, str(overlay_root))
    source_root = sources['server']['game'].parent.parent
    require(not overlay.exists() and not overlay.is_symlink()
            and not overlay.is_relative_to(source_root) and not source_root.is_relative_to(overlay),
            'Fresh nonoverlapping phase materialization root required')
    # Refuse output overlapping ANY original pinned input before creating it.
    require(not any(Path(row['path']).is_relative_to(overlay) for row in source_inputs),
            'Phase output overlaps original input closure')
    overlay.mkdir(parents=True)
    folder = overlay / 'unified'; folder.mkdir()
    roles = {}; before_roles = {}; configurations = {}; specs = {}; inputs = {row['path']: row for row in source_inputs}
    for source in sources.values():
        for path, row in source['historicalInputs'].items():
            require(path not in inputs or inputs[path] == row, 'Conflicting historical source input')
            inputs[path] = row
    for row in verified['inputs']:
        absolute_row = dict(row, path=str(local(root, row['path']))); inputs[absolute_row['path']] = absolute_row
    inputs[str(local(root, verified['bundle_pin']['path']))] = dict(verified['bundle_pin'], path=str(local(root, verified['bundle_pin']['path'])))
    for side in ('server', 'client'):
        source = sources[side]; game = folder / side; old_owner = source['owner']
        def ignore(path, names):
            return [old_owner.name] if Path(path) == old_owner.parent else []
        shutil.copytree(source['game'], game, ignore=ignore)
        spec = _fresh_phase_spec(source, game)
        spec_path = folder / (side + '-assembly-spec.json')
        with spec_path.open('xb') as stream: stream.write(canonical(spec) + b'\n')
        spec_pin = absolute_pin(root, spec_path)
        _, _, _, config_pin = configure_phase_assembly(root, assembler_pin=assembler_pin,
            validator_pin=validator_pin, spec_pin=spec_pin, derivative_pin=derivative_pin,
            diagnostic_manifest_pin=diagnostic_manifest_pin, phase=phase,
            receipt_path=folder / (side + '-phase-configured/build-receipt.json'))
        before, command = _materialized_before(root, source, game, phase, config_pin)
        before_path = folder / (side + '-pre-quilt-launch-seal.json')
        with before_path.open('xb') as stream: stream.write(canonical(before) + b'\n')
        after, receipt = stage_unified_fixture(root, before, verified, target='unified', phase=phase,
            overlay_root=overlay, source_role_pin=source_roles[side], assembly_command=command,
            assembly_receipt_pin=config_pin)
        role_path = folder / (side + '-launch-seal.json')
        with role_path.open('xb') as stream: stream.write(canonical(after) + b'\n')
        roles[side] = absolute_pin(root, role_path); before_roles[side] = absolute_pin(root, before_path)
        configurations[side] = config_pin; specs[side] = spec_pin
        for row in [roles[side], before_roles[side], config_pin, spec_pin,
                    absolute_pin(root, Path(after['assembly']['buildReceipt'])), *after['files']]:
            require(row['path'] not in inputs or inputs[row['path']] == row, 'Conflicting materialized input pin')
            inputs[row['path']] = row
    manifest = {'schema': 'quilt-lifecycle-materialized-phase-v1', **FLAGS, 'phase': phase,
        'assemblyRoot': str(overlay), 'sourceRoles': source_roles, 'sourceSpecs': source_specs,
        'sourceInputs': source_inputs, 'roles': roles, 'beforeRoles': before_roles,
        'phaseConfigurations': configurations, 'assemblySpecs': specs,
        'fixtureBundle': verified['bundle_pin'], 'validatedProvenance': verified['validated_provenance'],
        'originalAssembler': assembler_pin, 'originalValidator': validator_pin,
        'unconfiguredDerivative': derivative_pin, 'diagnosticManifest': diagnostic_manifest_pin,
        'inputs': sorted(inputs.values(), key=lambda r:r['path'])}
    manifest_path = overlay / 'phase-assembly.json'
    with manifest_path.open('xb') as stream: stream.write(canonical(manifest) + b'\n')
    validate_materialized_phase(root, absolute_pin(root, manifest_path), verified)
    return absolute_pin(root, manifest_path), manifest


def validate_materialized_phase(root, manifest_pin, verified):
    """Read-only staging-to-sealing proof; no supervisor or game acceptance."""
    root = root_path(root)
    manifest = load(check_absolute(root, manifest_pin))
    exact(manifest, ('schema', *FLAGS, 'phase', 'assemblyRoot', 'sourceRoles', 'sourceSpecs', 'sourceInputs',
                    'roles', 'beforeRoles', 'phaseConfigurations', 'assemblySpecs', 'fixtureBundle',
                    'validatedProvenance', 'originalAssembler', 'originalValidator', 'unconfiguredDerivative',
                    'diagnosticManifest', 'inputs'), 'materialized phase manifest')
    for key in ('roles', 'beforeRoles', 'phaseConfigurations', 'assemblySpecs'):
        exact(manifest[key], ('server', 'client'), 'materialized ' + key)
    require(manifest.get('schema') == 'quilt-lifecycle-materialized-phase-v1'
            and all(type(manifest.get(k)) is type(v) and manifest[k] == v for k,v in FLAGS.items()),
            'Materialized phase cannot claim runtime acceptance')
    require(manifest['fixtureBundle'] == verified['bundle_pin']
            and manifest['validatedProvenance'] == verified['validated_provenance'], 'Materialized fixture ancestry changed')
    sources = _source_phase_inputs(root, source_roles=manifest['sourceRoles'], source_specs=manifest['sourceSpecs'],
        source_inputs=manifest['sourceInputs'], assembler_pin=manifest['originalAssembler'],
        validator_pin=manifest['originalValidator'], derivative_pin=manifest['unconfiguredDerivative'],
        diagnostic_manifest_pin=manifest['diagnosticManifest'])
    overlay = absolute(root, manifest['assemblyRoot']); phase = manifest['phase']
    expected_inputs = {row['path']: row for row in manifest['sourceInputs']}
    for source in sources.values():
        for path, row in source['historicalInputs'].items():
            require(path not in expected_inputs or expected_inputs[path] == row, 'Conflicting historical source input')
            expected_inputs[path] = row
    for row in [verified['bundle_pin'], *verified['inputs']]:
        row = dict(row, path=str(local(root, row['path']))); expected_inputs[row['path']] = row
    require(Path(manifest_pin['path']) == overlay / 'phase-assembly.json', 'Materialized manifest path changed')
    for side in ('server', 'client'):
        before_path = check_absolute(root, manifest['beforeRoles'][side])
        role_path = check_absolute(root, manifest['roles'][side])
        game = overlay / 'unified' / side
        require(before_path == game.parent / (side + '-pre-quilt-launch-seal.json')
                and role_path == game.parent / (side + '-launch-seal.json'), 'Materialized role belongs elsewhere')
        config = load(check_absolute(root, manifest['phaseConfigurations'][side]))
        require(config['assemblySpec'] == manifest['assemblySpecs'][side], 'Phase configuration spec ancestry changed')
        before, command = _materialized_before(root, sources[side], game, phase, manifest['phaseConfigurations'][side])
        require(load(before_path) == before, 'Materialized predecessor differs from independently rederived source')
        expected_spec = _fresh_phase_spec(sources[side], game)
        require(load(check_absolute(root, manifest['assemblySpecs'][side])) == expected_spec,
                'Materialized spec differs from exact source-role relocation')
        after = load(role_path); receipt = load(absolute(root, after['assembly']['buildReceipt']))
        validate_staged_role(root, before, after, verified, receipt, target='unified', phase=phase,
            overlay_root=overlay, source_role_pin=manifest['sourceRoles'][side],
            assembly_command=command, assembly_receipt_pin=manifest['phaseConfigurations'][side])
        for row in [manifest['roles'][side], manifest['beforeRoles'][side], manifest['phaseConfigurations'][side],
                    manifest['assemblySpecs'][side], absolute_pin(root, Path(after['assembly']['buildReceipt'])), *after['files']]:
            require(row['path'] not in expected_inputs or expected_inputs[row['path']] == row,
                    'Conflicting materialized input pin')
            expected_inputs[row['path']] = row
    require(manifest['inputs'] == sorted(expected_inputs.values(), key=lambda r:r['path']),
            'Materialized complete input closure changed')
    seen = set()
    for row in manifest['inputs']:
        check_absolute(root, row)
        require(row['path'] not in seen, 'Duplicate materialized closure input'); seen.add(row['path'])
    return manifest
