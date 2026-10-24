"""Strict source binding and Unified-only probe overlay; no JVM or runtime acceptance.

The caller MUST first run the source-owned build validator for the complete fresh
compiler/runtime/dependency proof. This module does not infer compilation from a
receipt. Reviewed hashes must come from that reviewed build and namespace proof,
not be copied from an untrusted/self-declared bundle. No supervisor is patched.
"""
from pathlib import Path, PurePosixPath
import copy
import hashlib
import json
import os
import re
import stat
import zipfile

ARTIFACT_NAME = 'fabric-network-control-0.1.0.jar'
MOD_ID = 'fabric_network_control'
ENTRYPOINTS = {'main': ['dev.infinity.fabricnetworkcontrol.NonceProbe'],
              'client': ['dev.infinity.fabricnetworkcontrol.NonceProbeClient']}
LEGACY_NAME = 'network-control-probe-0.1.1.jar'
LEGACY_SHA256 = '791f6c303475ad9d32baaacc98f0350c027d6efe826dcd5aa9dc99a81da2918a'
BUNDLE_SCHEMA = 'fabric-ffapi-probe-bundle-v1'
MAPPING_SCHEMA = 'fabric-probe-namespace-proof-v1'
OVERLAY_SCHEMA = 'unified-fabric-ffapi-probe-overlay-v1'
SHA = re.compile('[0-9a-f]{64}')


def require(value, message):
    if not value:
        raise ValueError(message)


def exact_keys(value, keys, label):
    require(type(value) is dict and set(value) == set(keys), 'Invalid ' + label)


def digest(data):
    return hashlib.sha256(data).hexdigest()


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode('ascii')


def root_path(root):
    root = Path(root).absolute()
    require(root.is_dir() and root.resolve() == root, 'Canonical existing consumer required')
    return root


def local(root, relative):
    require(type(relative) is str and relative and '\\' not in relative, 'Invalid portable path')
    path = PurePosixPath(relative)
    require(not path.is_absolute() and '..' not in path.parts and path.as_posix() == relative,
            'Uncontained portable path')
    result = root / relative
    require(result.resolve() == result, 'Redirected path refused')
    return result


def absolute(root, path):
    path = Path(path)
    require(path.is_absolute() and path.is_relative_to(root), 'Path leaves consumer')
    return local(root, path.relative_to(root).as_posix())


def pin(root, path):
    path = absolute(root, path)
    info = path.stat()
    require(stat.S_ISREG(info.st_mode) and 1 <= info.st_size <= 256 * 1024 * 1024,
            'Nonempty bounded regular input required')
    return {'path': path.relative_to(root).as_posix(), 'bytes': info.st_size, 'sha256': digest(path.read_bytes())}


def check(root, row):
    exact_keys(row, ('path', 'bytes', 'sha256'), 'file pin')
    require(type(row['bytes']) is int and row['bytes'] >= 1
            and type(row['sha256']) is str and SHA.fullmatch(row['sha256']), 'Invalid strict file pin')
    path = local(root, row['path'])
    require(pin(root, path) == row, 'Changed source/build input')
    return path


def absolute_pin(root, path):
    row = pin(root, path)
    return dict(row, path=str(local(root, row['path'])))


def check_absolute(root, row):
    exact_keys(row, ('path', 'bytes', 'sha256'), 'absolute file pin')
    require(type(row['bytes']) is int and row['bytes'] >= 1
            and type(row['sha256']) is str and SHA.fullmatch(row['sha256']), 'Invalid strict role pin')
    path = absolute(root, row['path'])
    require(absolute_pin(root, path) == row, 'Changed role input')
    return path


def load(path, maximum=256 * 1024):
    data = path.read_bytes()
    require(len(data) <= maximum, 'JSON bound exceeded')
    def pairs(rows):
        out = {}
        for key, value in rows:
            require(key not in out, 'Duplicate JSON key')
            out[key] = value
        return out
    def invalid(_):
        raise ValueError('Nonfinite JSON value')
    return json.loads(data, object_pairs_hook=pairs, parse_constant=invalid)


def verify_archive(artifact, metadata_source):
    with zipfile.ZipFile(artifact) as archive:
        infos = archive.infolist()
        require(1 <= len(infos) <= 256, 'Probe archive inventory bound')
        names = [row.filename for row in infos]
        require(len(names) == len(set(names)), 'Duplicate probe archive entry')
        total = 0
        for info in infos:
            name = info.filename
            path = PurePosixPath(name)
            require(name and not path.is_absolute() and '..' not in path.parts and '\\' not in name
                    and path.as_posix() == name and not name.endswith('/'), 'Unsafe probe archive member')
            require(not stat.S_ISLNK(info.external_attr >> 16) and not info.flag_bits & 1,
                    'Redirected/encrypted probe archive member')
            require(name in ('META-INF/MANIFEST.MF', 'LICENSE', 'fabric.mod.json') or
                    name.startswith('dev/infinity/fabricnetworkcontrol/') and name.endswith('.class'),
                    'Foreign or fallback probe archive entry')
            total += info.file_size
            require(info.file_size <= 2 * 1024 * 1024 and total <= 16 * 1024 * 1024,
                    'Probe archive payload bound')
        require('fabric.mod.json' in names and archive.read('fabric.mod.json') == metadata_source.read_bytes(),
                'Fabric metadata is not exact source resource')
        require(all(value[0].replace('.', '/') + '.class' in names for value in ENTRYPOINTS.values()),
                'Missing actual Fabric entrypoint classes')
        if 'META-INF/MANIFEST.MF' in names:
            manifest = archive.read('META-INF/MANIFEST.MF').decode('ascii')
            require(not any(line.lower().startswith('class-path:') for line in manifest.splitlines()),
                    'Implicit probe classpath refused')
    metadata = load(metadata_source, 16384)
    require(type(metadata.get('schemaVersion')) is int and metadata.get('schemaVersion') == 1 and metadata.get('id') == MOD_ID
            and metadata.get('version') == '0.1.0' and metadata.get('environment') == '*'
            and metadata.get('entrypoints') == ENTRYPOINTS, 'Wrong Fabric probe identity/entrypoints')
    require(metadata.get('custom', {}).get('unified:diagnosticOnly') is True
            and metadata.get('custom', {}).get('unified:baselineAcceptance') is False,
            'Probe cannot claim baseline acceptance')
    require(metadata.get('depends', {}).get('minecraft') == '1.21.1'
            and {'fabricloader', 'fabric-networking-api-v1', 'fabric-lifecycle-events-v1'} <= metadata['depends'].keys(),
            'Real Fabric/FFAPI dependencies required')


def verify_source_binding(root, bundle_pin, *, reviewed):
    """Return strict portable closure after the caller's full build validation.

    `reviewed` has exactly source_manifest_sha256, artifact_sha256 and
    namespace_proof_sha256. Missing/unresolved namespace proof fails closed.
    """
    root = root_path(root)
    exact_keys(reviewed, ('source_manifest_sha256', 'artifact_sha256', 'namespace_proof_sha256'), 'reviewed hashes')
    require(all(type(v) is str and SHA.fullmatch(v) for v in reviewed.values()), 'Reviewed hashes required')
    bundle_path = check(root, bundle_pin)
    bundle = load(bundle_path)
    exact_keys(bundle, ('schema', 'diagnostic_only', 'baseline_acceptance', 'artifact', 'source_manifest',
                        'build_binding', 'build_result', 'namespace_proof'), 'FFAPI bundle')
    require(bundle['schema'] == BUNDLE_SCHEMA and bundle['diagnostic_only'] is True
            and bundle['baseline_acceptance'] is False, 'FFAPI bundle cannot claim acceptance')
    paths = {key: check(root, bundle[key]) for key in
             ('artifact', 'source_manifest', 'build_binding', 'build_result', 'namespace_proof')}
    require(len(set(paths.values())) == len(paths), 'Aliased probe provenance inputs')
    require(paths['artifact'].name == ARTIFACT_NAME
            and paths['source_manifest'].name == 'source-manifest.json', 'Separate probe artifact/source names required')
    require(bundle['artifact']['sha256'] == reviewed['artifact_sha256']
            and bundle['source_manifest']['sha256'] == reviewed['source_manifest_sha256']
            and bundle['namespace_proof']['sha256'] == reviewed['namespace_proof_sha256'], 'Reviewed probe identity changed')
    source = load(paths['source_manifest'])
    exact_keys(source, ('schema', 'status', 'files'), 'probe source manifest')
    require(type(source['schema']) is int and source['schema'] == 1
            and source['status'] == 'SOURCE_ONLY_NOT_RUNTIME_ACCEPTANCE'
            and type(source['files']) is list and 1 <= len(source['files']) <= 128, 'Source-only manifest required')
    source_root = paths['source_manifest'].parent
    source_rows = []
    seen = set()
    for row in source['files']:
        exact_keys(row, ('path', 'bytes', 'sha256'), 'source row')
        require(type(row['bytes']) is int and row['bytes'] >= 1
                and type(row['sha256']) is str and SHA.fullmatch(row['sha256']), 'Invalid strict source pin')
        path = local(source_root, row['path'])
        require(row['path'] not in seen and row['path'] != 'source-manifest.json', 'Duplicate source member')
        seen.add(row['path'])
        actual = pin(root, path)
        require(dict(actual, path=row['path']) == row, 'Source/resource bytes changed')
        source_rows.append(actual)
    required = {'build.gradle', 'protocol-schema.json', 'src/main/resources/fabric.mod.json'}
    require(required <= seen, 'Source build/protocol/Fabric metadata required')
    observed = set()
    for path in source_root.rglob('*'):
        require(not path.is_symlink(), 'Redirected source inventory')
        if path.is_file(): observed.add(path.relative_to(source_root).as_posix())
    require(observed == seen | {'source-manifest.json'}, 'Unexpected source inventory')
    expected = {'schema': 1, 'status': 'BUILT',
                'source_manifest_sha256': bundle['source_manifest']['sha256'],
                'artifact_path': str(paths['artifact']), 'artifact_sha256': bundle['artifact']['sha256'],
                'artifact_bytes': bundle['artifact']['bytes']}
    binding = load(paths['build_binding'], 8192)
    exact_keys(binding, expected, 'supervisor probe build binding')
    require(binding == expected and type(binding['schema']) is int and type(binding['artifact_bytes']) is int,
            'Probe JAR/source build binding changed')
    namespace = load(paths['namespace_proof'])
    exact_keys(namespace, ('schema', 'status', 'source_namespace', 'artifact_namespace', 'runtime_namespace', 'mechanism',
                           'source_manifest_sha256', 'artifact_sha256', 'evidence'), 'namespace proof')
    require(namespace['schema'] == MAPPING_SCHEMA
            and namespace['status'] == 'REMAP_VERIFIED_NOT_RUNTIME_ACCEPTANCE'
            and namespace['source_namespace'] == 'mojang'
            and namespace['artifact_namespace'] == 'intermediary'
            and namespace['runtime_namespace'] == 'mojang'
            and namespace['mechanism'] == 'pinned-fart-mojang-to-intermediary'
            and namespace['source_manifest_sha256'] == reviewed['source_manifest_sha256']
            and namespace['artifact_sha256'] == reviewed['artifact_sha256'], 'Unresolved/wrong namespace route')
    require(type(namespace['evidence']) is list and 1 <= len(namespace['evidence']) <= 32,
            'Source-backed namespace evidence required')
    for row in namespace['evidence']: check(root, row)
    verify_archive(paths['artifact'], source_root / 'src/main/resources/fabric.mod.json')
    rows = [bundle_pin, *[bundle[k] for k in paths], *source_rows, *namespace['evidence']]
    inputs = {}
    for row in rows:
        require(row['path'] not in inputs or inputs[row['path']] == row, 'Conflicting provenance pin')
        inputs[row['path']] = row
    return {'bundle': bundle, 'bundle_pin': bundle_pin, 'reviewed': dict(reviewed),
            'inputs': sorted(inputs.values(), key=lambda row: row['path'])}


def _expected_role(root, before, verified, baseline_probe, overlay_root):
    root = root_path(root)
    check_absolute(root, baseline_probe)
    require(Path(baseline_probe['path']).name == LEGACY_NAME and baseline_probe['sha256'] == LEGACY_SHA256,
            'Exact unchanged native 0.1.1 baseline required')
    game = absolute(root, before['cwd']); overlay = absolute(root, overlay_root)
    original_profile = Path(baseline_probe['path']).parent.parent
    require(game.name in ('server', 'client') and game == overlay / 'unified' / game.name
            and original_profile.name == game.name and original_profile.parent.name == 'unified'
            and not overlay.is_relative_to(original_profile) and not original_profile.is_relative_to(overlay),
            'Fresh nonoverlapping Unified diagnostic profile required')
    old = game / 'mods' / LEGACY_NAME
    require(before['probe_path'] == str(old) and old != Path(baseline_probe['path']), 'Only copied legacy probe may be replaced')
    files = before['files']
    require(type(files) is list and len({row['path'] for row in files}) == len(files), 'Duplicate role input')
    old_rows = [row for row in files if row['path'] == str(old)]
    require(len(old_rows) == 1 and old_rows[0] == dict(baseline_probe, path=str(old)), 'Copied legacy identity changed')
    for key in ('original_mods', 'managed_mods'):
        require(type(before[key]) is list and str(old) not in before[key], 'Probe overlaps other mod role')
    artifact = check(root, verified['bundle']['artifact'])
    new = game / 'mods' / ARTIFACT_NAME
    expected = copy.deepcopy(before)
    expected['probe_path'] = str(new)
    copied = dict(verified['bundle']['artifact'], path=str(new))
    expected['files'] = sorted([row for row in files if row['path'] != str(old)] + [copied], key=lambda row: row['path'])
    receipt = {'schema': OVERLAY_SCHEMA, 'target': 'unified', 'diagnostic_only': True,
               'baseline_acceptance': False, 'game_launched': False, 'native_control_unchanged': True,
               'bundle': verified['bundle_pin'], 'baseline_probe': baseline_probe,
               'removed_diagnostic_copy': old_rows[0], 'new_diagnostic_copy': copied,
               'before_role_sha256': digest(canonical(before)), 'after_role_sha256': digest(canonical(expected))}
    return game, old, new, artifact, expected, receipt


def verify_mod_inventory(root, role):
    game = absolute(root, role['cwd'])
    paths = [*role['original_mods'], *role['managed_mods'], role['probe_path']]
    require(len(paths) == len(set(paths)) and all(Path(p).parent == game / 'mods' for p in paths), 'Overlapping/uncontained mod roles')
    require(set(paths) == {str(p) for p in (game / 'mods').iterdir()}, 'Unexpected profile mod entry')
    file_rows = {row['path']: row for row in role['files']}
    for path in paths:
        require(path in file_rows, 'Unsealed profile mod')
        check_absolute(root, file_rows[path])


def stage_unified_probe(root, before, verified, *, target, baseline_probe, overlay_root):
    """Change only a fresh copied Unified probe, returning new role plus receipt.

    Save/pin both returned values through the source-owned assembly receipt path.
    Native target is deliberately rejected, never silently converted or skipped.
    """
    require(target == 'unified', 'FFAPI replacement is Unified-only')
    root = root_path(root)
    current = verify_source_binding(root, verified['bundle_pin'], reviewed=verified['reviewed'])
    require(current == verified, 'Probe closure changed before staging')
    game, old, new, artifact, after, receipt = _expected_role(root, before, verified, baseline_probe, overlay_root)
    verify_mod_inventory(root, before)
    for row in before['files']: check_absolute(root, row)
    require(not new.exists() and not new.is_symlink(), 'Stale FFAPI copy refused')
    with new.open('xb') as stream:
        stream.write(artifact.read_bytes()); stream.flush(); os.fsync(stream.fileno())
    require(absolute_pin(root, new) == receipt['new_diagnostic_copy'], 'Staged FFAPI bytes changed')
    # This is solely the just-created diagnostic clone, never the baseline.
    old.unlink()
    validate_staged_role(root, before, after, verified, receipt,
                         baseline_probe=baseline_probe, overlay_root=overlay_root)
    return after, receipt


def validate_staged_role(root, before, after, verified, receipt, *, baseline_probe, overlay_root):
    """Caller supplies its independently derived pre-overlay role, not receipt data."""
    root = root_path(root)
    require(verify_source_binding(root, verified['bundle_pin'], reviewed=verified['reviewed']) == verified,
            'Probe closure changed after staging')
    game, old, new, artifact, expected, expected_receipt = _expected_role(root, before, verified, baseline_probe, overlay_root)
    require(after == expected and receipt == expected_receipt, 'Probe overlay has an unapproved role/receipt delta')
    require(not old.exists() and not old.is_symlink(), 'Legacy emitter remains in Unified profile')
    for row in after['files']:
        # Initial stage checked every pristine input. Later validation retains
        # the existing sealer's mutable options contract, not a new exception.
        if row['path'] != str(game/'options.txt'):check_absolute(root, row)
    verify_mod_inventory(root, after)
    return True


def supervisor_binding(root, verified):
    """Only for Unified; native sealing retains its unchanged compile_probe path."""
    root = root_path(root)
    require(verify_source_binding(root, verified['bundle_pin'], reviewed=verified['reviewed']) == verified,
            'Changed probe binding')
    bundle = verified['bundle']
    return {'probe_path': str(check(root, bundle['artifact'])),
            'probe_source_manifest': str(check(root, bundle['source_manifest'])),
            'probe_build_receipt': str(check(root, bundle['build_binding'])),
            'source_receipts': [str(check(root, bundle['build_result'])), str(check(root, verified['bundle_pin']))],
            'inputs': [absolute_pin(root, check(root, row)) for row in verified['inputs']]}
