"""Source-only candidate for one exact, owned Quilt SavedData continuation.

Never changes the published supervisor or accepts an arbitrary existing world.
The create run remains the original pair. Only a separately sealed reopen may
use this owner, after direct requalification of retained actual create evidence.
Execution is available only through the dedicated supervised CLI. Imports and
preparation never launch a process.
"""
import ast
import argparse
from contextlib import contextmanager
import hashlib
import io
import json
import math
import os
from pathlib import Path, PurePosixPath
import re
import signal
import stat
import textwrap
import time
import types
import zipfile

BASE_SHA256 = '2f86c57b6baa693b07064f520d3e2020ba015d07b3bfb29b2ca8a65db8cb1b9b'
RUN_SHA256 = 'a7ca63c9d47f0dcb60d98702449938f65dcbdf7db461197622c1ec1d49fd757d'
STAGING_SHA256 = '6ddc65d700e41340385e80d80ef5a7b025294224f31af4bacf86b181c5d9c825'
HERE = Path(__file__).resolve().parent
MIB = 1024 * 1024
MAX_FILES = 8192
MAX_DIRECTORIES = 2048
MAX_FILE_BYTES = 64 * MIB
MAX_WORLD_BYTES = 256 * MIB
MAX_JSON = 8 * MIB
PHASE_PREFIX = '-Dunified.quiltProbe.phase='
RECEIPT_SCHEMA = 'quilt-owned-world-continuation-v1'
OWNER_SCHEMA = 'quilt-lifecycle-continuation-owner-v1'
POLICY = 'META-INF/unified-admission/installation.json'


def require(value, message):
    if not value:
        raise ValueError(message)


def exact(value, keys, label):
    require(type(value) is dict and set(value) == set(keys), 'Invalid ' + label)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def decode(raw):
    require(len(raw) <= MAX_JSON, 'JSON bound exceeded')
    def pairs(rows):
        result = {}
        for key, value in rows:
            require(key not in result, 'Duplicate JSON key')
            result[key] = value
        return result
    return json.loads(raw, object_pairs_hook=pairs,
                      parse_constant=lambda _: (_ for _ in ()).throw(ValueError('Nonfinite JSON')))


def canonical(path):
    path = Path(path)
    require(path.is_absolute() and '..' not in path.parts and path.resolve() == path,
            'Canonical absolute path required')
    require(not any(p.is_symlink() for p in (path, *path.parents)), 'Redirected path')
    return path


def local(root, path):
    root = canonical(root)
    path = canonical(path)
    require(path.is_relative_to(root), 'Path leaves consumer root')
    return path


def owned_chain(root, path):
    root, path = canonical(root), local(root, path)
    for value in (path, *path.parents):
        owned_directory(value)
        if value == root:
            return
    raise ValueError('Owned chain leaves consumer root')


def owned_directory(path):
    path = canonical(path)
    info = path.stat(follow_symlinks=False)
    require(stat.S_ISDIR(info.st_mode) and info.st_uid == os.geteuid()
            and stat.S_IMODE(info.st_mode) in (0o700, 0o750, 0o755),
            'World directory must be ordinary, owned and not group/world writable')
    require(os.access(path, os.R_OK | os.X_OK), 'World directory is not readable/traversable')
    return info


def signature(info):
    return (info.st_dev, info.st_ino, info.st_mode, info.st_uid, info.st_nlink,
            info.st_size, info.st_mtime_ns, info.st_ctime_ns)


def read_regular(path, maximum, *, owned=True, nonempty=True):
    """Stable, bounded, nonblocking read with no symlink or hard-link admission."""
    path = canonical(path)
    directory = os.open('/', os.O_RDONLY | os.O_DIRECTORY)
    try:
        for component in path.parts[1:-1]:
            nxt = os.open(component, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=directory)
            os.close(directory)
            directory = nxt
        descriptor = os.open(path.name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=directory)
    finally:
        os.close(directory)
    try:
        before = os.fstat(descriptor)
        require(stat.S_ISREG(before.st_mode) and before.st_nlink == 1,
                'Singly linked regular file required')
        require((not owned or before.st_uid == os.geteuid())
                and stat.S_IMODE(before.st_mode) in (0o400, 0o440, 0o444, 0o600, 0o640, 0o644,
                                                     0o500, 0o550, 0o555, 0o700, 0o750, 0o755),
                'Unowned or unsafe file mode')
        require((1 if nonempty else 0) <= before.st_size <= maximum, 'File byte bound exceeded')
        with os.fdopen(descriptor, 'rb') as stream:
            descriptor = None
            raw = stream.read(maximum + 1)
            after = os.fstat(stream.fileno())
        require(signature(before) == signature(after) == signature(path.stat(follow_symlinks=False))
                and len(raw) == before.st_size, 'File changed during read')
        return raw, {'path': str(path), 'bytes': len(raw), 'sha256': sha(raw)}
    finally:
        if descriptor is not None:
            os.close(descriptor)


def check_pin(root, row, maximum=MAX_JSON, *, owned=True):
    exact(row, ('path', 'bytes', 'sha256'), 'file pin')
    require(type(row['bytes']) is int and row['bytes'] > 0
            and type(row['sha256']) is str and len(row['sha256']) == 64
            and all(c in '0123456789abcdef' for c in row['sha256']), 'Invalid identity pin')
    raw, actual = read_regular(local(root, row['path']), maximum, owned=owned)
    require(actual == row, 'Evidence differs from exact pin')
    return raw


def exclusive_stream(path):
    """Create a new private regular output through nonredirecting directory FDs."""
    path = canonical(path)
    owned_directory(path.parent)
    directory = os.open('/', os.O_RDONLY | os.O_DIRECTORY)
    try:
        for component in path.parts[1:-1]:
            nxt = os.open(component, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=directory)
            os.close(directory)
            directory = nxt
        descriptor = os.open(path.name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                             0o600, dir_fd=directory)
    finally:
        os.close(directory)
    return os.fdopen(descriptor, 'wb')


def write_new(path, value):
    path = canonical(path)
    owned_directory(path.parent)
    raw = json.dumps(value, sort_keys=True, indent=2, allow_nan=False).encode('ascii') + b'\n'
    require(len(raw) <= MAX_JSON, 'Receipt bound exceeded')
    with exclusive_stream(path) as stream:
        stream.write(raw)
        stream.flush()
        os.fsync(stream.fileno())
    return read_regular(path, MAX_JSON)[1]


def evidence_destination(root, path, specs):
    path = local(root, path)
    owned_chain(root, path.parent)
    require(not os.path.lexists(path), 'Fresh evidence destination required')
    protected = []
    for spec in specs:
        protected.extend(Path(spec[role]['cwd']) for role in ('server', 'client'))
        protected.extend(Path(tree) for tree in spec['immutable_trees'])
    require(not any(path.is_relative_to(item) or item.is_relative_to(path) for item in protected),
            'Evidence destination overlaps a game profile or immutable input tree')
    return path


def world_inventory(root, world):
    """Inventory all regular bytes and directories; reject every other entry type."""
    world = local(root, world)
    owned_chain(root, world)
    files, directories, total = [], [], 0
    pending = [world]
    seen_directories = []
    while pending:
        folder = pending.pop()
        before = owned_directory(folder)
        seen_directories.append((folder, signature(before)))
        names = []
        for entry in sorted(os.scandir(folder), key=lambda row: row.name):
            path = folder / entry.name
            relative = path.relative_to(world).as_posix()
            require(PurePosixPath(relative).as_posix() == relative and
                    not any(c in relative for c in ('\\', '\x00', '\n', '\r')),
                    'Invalid world member name')
            info = entry.stat(follow_symlinks=False)
            names.append(entry.name)
            if stat.S_ISDIR(info.st_mode):
                owned_directory(path)
                directories.append(relative)
                require(len(directories) <= MAX_DIRECTORIES, 'World directory bound exceeded')
                pending.append(path)
            else:
                require(stat.S_ISREG(info.st_mode), 'Special or redirected world member')
                raw, row = read_regular(path, MAX_FILE_BYTES, nonempty=False)
                files.append(dict(row, path=relative))
                total += len(raw)
                require(len(files) <= MAX_FILES and total <= MAX_WORLD_BYTES,
                        'World inventory bound exceeded')
        require(names == sorted(os.listdir(folder)), 'World membership changed during read')
    for folder, before in seen_directories:
        require(signature(owned_directory(folder)) == before, 'World directory changed during inventory')
    require(files, 'Empty world cannot continue')
    return {'schema': 'quilt-owned-world-inventory-v1', 'files': sorted(files, key=lambda r: r['path']),
            'directories': sorted(directories), 'total_bytes': total,
            'limits': {'files': MAX_FILES, 'directories': MAX_DIRECTORIES,
                       'file_bytes': MAX_FILE_BYTES, 'total_bytes': MAX_WORLD_BYTES}}


def verify_world(root, world, expected):
    require(world_inventory(root, world) == expected, 'Owned world inventory changed')


def copy_owned_world(root, source, destination, expected):
    """Preserve create evidence and copy only its exact owned world into a fresh role."""
    source, destination = local(root, source), local(root, destination)
    require(source != destination and not source.is_relative_to(destination)
            and not destination.is_relative_to(source), 'Overlapping world continuation')
    require(not os.path.lexists(destination), 'Destination world already exists')
    owned_chain(root, destination.parent)
    verify_world(root, source, expected)
    destination.mkdir(mode=0o700)
    for relative in expected['directories']:
        (destination / relative).mkdir(mode=0o700)
    for row in expected['files']:
        raw, actual = read_regular(source / row['path'], MAX_FILE_BYTES, nonempty=False)
        require(dict(actual, path=row['path']) == row, 'Source changed during copy')
        target = destination / row['path']
        with exclusive_stream(target) as stream:
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
    verify_world(root, source, expected)
    verify_world(root, destination, expected)


def verify_phase_command(command, phase):
    require(type(command) is list and len(command) >= 3, 'Invalid phase command')
    # Position 1 is unambiguously a JVM option, never an application argument.
    required = PHASE_PREFIX + phase
    require(command[1] == required and
            [v for v in command if type(v) is str and v.startswith('-Dunified.quiltProbe.phase')] == [required],
            'Exactly one phase property immediately after pinned Java is required')


def relocate_paths(value, replacements):
    """Only complete paths or argv/property/classpath path tokens, never substrings."""
    if isinstance(value, str):
        for old, new in replacements:
            value = re.sub(r'(^|[=:])' + re.escape(old) + r'(?=/|$)',
                           lambda match: match.group(1) + new, value)
        return value
    if isinstance(value, list):
        return [relocate_paths(v, replacements) for v in value]
    if isinstance(value, dict):
        return {k: relocate_paths(v, replacements) for k, v in value.items()}
    return value


def digest_arguments(arguments):
    """Exact frozen validate_launch.digest_strings encoding, covered by source test."""
    value = hashlib.sha256()
    for argument in arguments:
        raw = argument.encode()
        value.update((str(len(raw)) + '\n').encode('ascii'))
        value.update(raw)
    return value.hexdigest()


def sealed_references(root, value, pins):
    """Every absolute source/build reference must also be in the ordinary seal."""
    if isinstance(value, list):
        for item in value:
            sealed_references(root, item, pins)
    elif isinstance(value, dict):
        path = value.get('path')
        if isinstance(path, str) and path.startswith('/') and 'sha256' in value:
            local(root, path)
            require(path in pins and pins[path]['sha256'] == value['sha256']
                    and ('bytes' not in value or pins[path]['bytes'] == value['bytes']),
                    'Phase source/build reference is outside ordinary sealed inputs')
        for item in value.values():
            sealed_references(root, item, pins)


def configured_owner_pin(root, spec, role):
    """Identify only the exact BOOT owner named by the sealed after-staging role."""
    pins = {row['path']: row for row in spec['inputs']}
    matches = []
    for source in spec.get('source_receipts', []):
        require(source in pins, 'Unsealed source receipt')
        record = decode(check_pin(root, pins[source]))
        if type(record) is not dict or record.get('cwd') != spec[role]['cwd']:
            continue
        if record.get('command') != spec[role]['command']:
            continue
        assembly = record.get('assembly')
        if type(assembly) is not dict:
            continue
        require(record.get('original_mods') == spec[role]['original_mods']
                and record.get('managed_mods') == spec[role]['managed_mods'],
                'Configured owner role inventory mismatch')
        owner = assembly.get('configuredOwner')
        path = local(root, owner)
        require(path.is_relative_to(Path(spec[role]['cwd']) / 'installation')
                and path.suffix == '.jar' and owner in pins,
                'Configured BOOT owner leaves exact role installation')
        require(assembly.get('configuredOwnerSha256') == pins[owner]['sha256']
                and assembly.get('classOwnerCount') == 1
                and pins[owner] in record.get('files', []), 'Configured BOOT source binding changed')
        phase = spec[role]['command'][1][len(PHASE_PREFIX):]
        require(assembly.get('quiltLifecyclePhase') == phase, 'Configured owner phase changed')
        base_assembly = assembly.get('baseAssembly')
        require(type(base_assembly) is dict, 'Original phase assembly provenance required')
        receipt_path = base_assembly.get('buildReceipt')
        require(receipt_path in pins and base_assembly.get('buildReceiptSha256') == pins[receipt_path]['sha256'],
                'Phase configuration receipt is not sealed')
        final_receipt_path = assembly.get('buildReceipt')
        require(final_receipt_path in pins and assembly.get('buildReceiptSha256') == pins[final_receipt_path]['sha256'],
                'Final phase staging receipt is not sealed')
        sealed_references(root, decode(check_pin(root, pins[final_receipt_path])), pins)
        staging_rows = [row for row in spec['inputs']
                        if Path(row['path']).name == 'quilt_lifecycle_staging.py'
                        and row['sha256'] == STAGING_SHA256]
        require(len(staging_rows) == 1, 'Exact independently reviewed phase staging source required')
        staging_raw = check_pin(root, staging_rows[0], MIB)
        staging = types.ModuleType('quilt_continuation_pinned_phase_staging')
        staging.__file__ = staging_rows[0]['path']
        exec(compile(staging_raw, staging.__file__, 'exec'), staging.__dict__)
        details = staging.verify_phase_configuration(root, record, phase=phase,
            assembly_command=[record['command'][0], *record['command'][2:]],
            assembly_receipt_pin=pins[receipt_path])
        sealed_references(root, details['receipt'], pins)
        spec_row = details['assemblySpec']
        require(pins.get(spec_row['path']) == spec_row, 'Phase assembly spec is not sealed')
        sealed_references(root, decode(check_pin(root, spec_row)), pins)
        require(check_pin(root, staging_rows[0], MIB) == staging_raw, 'Phase staging source changed')
        matches.append(pins[owner])
    require(len(matches) == 1, 'Exactly one source-bound configured BOOT owner required')
    return matches[0]


def verify_policy_only_relocation(root, old_pin, new_pin, relocate, old_command, new_command):
    """No executable byte may change: only exact canonical installation path relocation."""
    before = check_pin(root, old_pin, 128 * MIB)
    after = check_pin(root, new_pin, 128 * MIB)
    with zipfile.ZipFile(io.BytesIO(before)) as left, zipfile.ZipFile(io.BytesIO(after)) as right:
        a, b = left.infolist(), right.infolist()
        names_a, names_b = [r.filename for r in a], [r.filename for r in b]
        require(1 <= len(a) <= 8192 and len(names_a) == len(set(names_a))
                and len(names_b) == len(set(names_b)) and set(names_a) == set(names_b)
                and POLICY in names_a, 'Configured owner ZIP inventory changed')
        for entries in (a, b):
            require(sum(r.file_size for r in entries) <= 256 * MIB
                    and all(r.file_size <= 16 * MIB and not r.flag_bits & 1 for r in entries),
                    'Configured owner payload bound exceeded')
        for name in names_a:
            if name != POLICY:
                require(left.read(name) == right.read(name), 'Configured owner executable/resource bytes changed')
        raw_a, raw_b = left.read(POLICY), right.read(POLICY)
        policy = decode(raw_a)
        require(type(policy) is dict and policy.get('schema') == 1 and policy.get('approved') is True
                and type(policy.get('artifacts')) is list,
                'Actual approved configured owner policy required')
        owner_rows = [row for row in policy['artifacts'] if row.get('role') == 'BOOT_OWNER']
        require(len(owner_rows) == 1 and type(policy.get('installationDirectory')) is str
                and str(Path(policy['installationDirectory']) / owner_rows[0]['path']) == old_pin['path'],
                'Embedded policy is not for the exact old BOOT owner')
        expected = relocate(policy)
        require(policy.get('processArgumentsSha256') == digest_arguments(old_command[1:]),
                'Create policy does not bind the exact actual phase argv')
        expected['processArgumentsSha256'] = digest_arguments(new_command[1:])
        require(str(Path(expected['installationDirectory']) / owner_rows[0]['path']) == new_pin['path'],
                'Embedded policy is not for the exact new BOOT owner')
        encode = lambda value: (json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False) + '\n').encode('ascii')
        require(raw_a == encode(policy) and raw_b == encode(expected),
                'Configured policy changed beyond canonical role path relocation')


def check_phase_specs(root, create_spec, reopen_spec):
    for phase, spec in (('create', create_spec), ('reopen', reopen_spec)):
        require(spec.get('schema') == 'network-ci-pair-v2' and spec.get('target') == 'unified'
                and spec.get('port') == 25632, 'Only sealed Unified pairs may continue')
        for role in ('server', 'client'):
            local(root, spec[role]['cwd'])
            verify_phase_command(spec[role]['command'], phase)
    require(create_spec['pair_lock'] == reopen_spec['pair_lock'], 'Original serial lock must be retained')
    require(create_spec['diagnostic_profile'] == reopen_spec['diagnostic_profile'],
            'Diagnostic product ancestry changed across phases')
    for key in ('probe_path', 'probe_source_manifest', 'probe_build_receipt'):
        require(create_spec[key] == reopen_spec[key], 'Fabric transport control changed across phases')
    paths = [local(root, spec[role]['cwd']) for spec in (create_spec, reopen_spec)
             for role in ('server', 'client')]
    require(len(set(paths)) == 4 and not any(a.is_relative_to(b) for a in paths for b in paths if a != b),
            'Four fresh nonoverlapping role directories required')
    replacements = [(create_spec[r]['cwd'], reopen_spec[r]['cwd']) for r in ('server', 'client')]
    def relocate(value):
        return relocate_paths(value, replacements)
    for role in ('server', 'client'):
        expected_role = relocate(create_spec[role])
        expected_role['command'][1] = PHASE_PREFIX + 'reopen'
        require(reopen_spec[role] == expected_role,
                'Role changed beyond explicit profile relocation and phase property')
    require(reopen_spec['immutable_trees'] == relocate(create_spec['immutable_trees'])
            and reopen_spec['jdk_legal_links'] == create_spec['jdk_legal_links'],
            'Immutable/JDK closure changed across phases')
    prior = {r['path']: r for r in create_spec['inputs']}
    following = {r['path']: r for r in reopen_spec['inputs']}
    require(len(prior) == len(create_spec['inputs']) and len(following) == len(reopen_spec['inputs']),
            'Duplicate phase input pins')
    for role in ('server', 'client'):
        profile = create_spec[role]['cwd']
        old_rows = [r for r in create_spec['inputs'] if Path(r['path']).is_relative_to(profile)]
        new_profile = relocate(profile)
        new_rows = [r for r in reopen_spec['inputs'] if Path(r['path']).is_relative_to(new_profile)]
        expected = {row['path']: row for row in relocate(old_rows)}
        observed = {row['path']: row for row in new_rows}
        require(set(expected) == set(observed), 'Pristine role file inventory changed across phases')
        changed = [path for path in expected if observed[path] != expected[path]]
        if changed:
            old_owner = configured_owner_pin(root, create_spec, role)
            new_owner = configured_owner_pin(root, reopen_spec, role)
            require(changed == [new_owner['path']] and relocate(old_owner['path']) == new_owner['path'],
                    'Pristine role changed outside the sole configured BOOT policy')
            verify_policy_only_relocation(root, old_owner, new_owner, relocate,
                                          create_spec[role]['command'], reopen_spec[role]['command'])
    # Every external executable/configuration input used by the unchanged
    # command/trees must retain its identity, even if new proof receipts exist.
    for path, row in prior.items():
        if path in following:
            require(following[path] == row, 'Shared input pin changed across phases')


def load_base(path):
    raw, pin = read_regular(path, MIB, owned=False)
    require(pin['sha256'] == BASE_SHA256, 'Original supervisor source changed')
    module = types.ModuleType('quilt_continuation_pinned_base')
    module.__file__ = str(path)
    exec(compile(raw, str(path), 'exec'), module.__dict__)
    require(read_regular(path, MIB, owned=False)[1] == pin, 'Supervisor changed during import')
    return module, raw


def checked_run_source(base_raw):
    """Only these two AST changes are permitted, not a configurable source patch."""
    tree = ast.parse(base_raw)
    pair = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == 'Pair')
    original = next(n for n in pair.body if isinstance(n, ast.FunctionDef) and n.name == 'run')
    source = textwrap.dedent('\n'.join(base_raw.decode().splitlines()[original.lineno-1:original.end_lineno]))
    old = "            require(not (profile / 'world').exists(), 'Fresh disposable profiles required')"
    require(source.count(old) == 1 and source.count("        self.spawn('server')") == 1,
            'Original run no longer has the exact reviewed structure')
    expected = source.replace(old, '            self.verify_profile_world(role, profile)')
    expected = expected.replace("        self.spawn('server')",
                                "        self.revalidate_continuation()\n        self.spawn('server')")
    raw, pin = read_regular(HERE / 'owned_pair_run.py', MIB)
    require(pin['sha256'] == RUN_SHA256, 'Continuation run source changed')
    candidate = ast.parse(raw)
    functions = [n for n in candidate.body if isinstance(n, ast.FunctionDef)]
    require(len(functions) == 1 and functions[0].name == 'run'
            and all(isinstance(n, (ast.FunctionDef, ast.Expr)) for n in candidate.body),
            'Unexpected continuation run code')
    require(ast.dump(functions[0], include_attributes=False) ==
            ast.dump(ast.parse(expected).body[0], include_attributes=False),
            'Continuation altered an unapproved process/resource/protocol/cleanup statement')
    return raw, pin


def source_identity(supervisor_path):
    base, raw = load_base(supervisor_path)
    _, derivative = checked_run_source(raw)
    owner = read_regular(HERE / 'quilt_continuation.py', MIB)[1]
    return base, {'original_supervisor_sha256': BASE_SHA256,
                  'derivative_run_sha256': derivative['sha256'], 'owner_source_sha256': owner['sha256']}


def load_qualifier(root, source_pin):
    raw = check_pin(root, source_pin, MIB)
    module = types.ModuleType('quilt_continuation_pinned_qualifier')
    module.__file__ = source_pin['path']
    # Its implementation must be independently reviewed and pinned by the caller.
    exec(compile(raw, source_pin['path'], 'exec'), module.__dict__)
    require(callable(getattr(module, 'validate_phase', None)), 'Missing create qualification API')
    require(check_pin(root, source_pin, MIB) == raw, 'Qualifier changed during import')
    return module


def qualify_create(root, receipt, supervisor_path):
    qualifier = load_qualifier(root, receipt['qualifier_source'])
    result = qualifier.validate_phase(root, phase='create', spec_pin=receipt['create_spec'],
        report_pin=receipt['create_report'], fixture=receipt['fixture'], reviewed=receipt['reviewed'],
        supervisor_path=supervisor_path)
    require(type(result) is dict, 'Create qualifier did not return evidence')
    return result


def prepare(root, *, create_spec_pin, create_report_pin, reopen_spec_pin, fixture, reviewed,
            qualifier_source_pin, supervisor_path, reviewed_owner_sources,
            reviewed_qualifier_sha256, output):
    """After real create only: requalify, snapshot, copy and seal exact continuation.

    Staging of complete role/JAR/build/config inputs is a separate required step.
    This does not launch a game, synthesize runtime evidence or modify a baseline.
    """
    root = canonical(root)
    output = local(root, output)
    owned_directory(output.parent)
    require(not os.path.lexists(output), 'Fresh continuation evidence directory required')
    base, sources = source_identity(supervisor_path)
    require(sources == reviewed_owner_sources
            and qualifier_source_pin['sha256'] == reviewed_qualifier_sha256,
            'Explicit reviewed owner and qualifier identities required')
    create_spec = decode(check_pin(root, create_spec_pin))
    reopen_spec = decode(check_pin(root, reopen_spec_pin))
    check_phase_specs(root, create_spec, reopen_spec)
    evidence_destination(root, output, (create_spec, reopen_spec))
    base.verify_spec(reopen_spec)
    receipt = {'schema': RECEIPT_SCHEMA, 'diagnostic_only': True, 'baseline_acceptance': False,
               'qsl_network_acceptance': False, 'phase': 'reopen',
               'create_spec': create_spec_pin, 'create_report': create_report_pin,
               'reopen_spec': reopen_spec_pin, 'fixture': fixture, 'reviewed': reviewed,
               'qualifier_source': qualifier_source_pin, 'owner_sources': sources,
               'source_world': str(Path(create_spec['server']['cwd']) / 'world'),
               'destination_world': str(Path(reopen_spec['server']['cwd']) / 'world')}
    qualification = qualify_create(root, receipt, supervisor_path)
    inventory = world_inventory(root, receipt['source_world'])
    for role in ('server', 'client'):
        profile = Path(reopen_spec[role]['cwd'])
        require(not os.path.lexists(profile / 'world'), 'Fresh reopen roles required before staging')
        for name in base.PROBE_FILES:
            require(not any(os.path.lexists(profile / (name + suffix))
                            for suffix in ('', '.tmp', '.supervisor-tmp')), 'Stale reopen probe evidence')
    output.mkdir(mode=0o700)
    receipt['create_qualification'] = write_new(output / 'create-qualification.json', qualification)
    receipt['world_inventory'] = write_new(output / 'world-inventory.json', inventory)
    copy_owned_world(root, receipt['source_world'], receipt['destination_world'], inventory)
    # Recheck actual source qualification and exact receipt ancestry after copying.
    require(qualify_create(root, receipt, supervisor_path) == qualification,
            'Create qualification changed during staging')
    for row in (create_spec_pin, create_report_pin, reopen_spec_pin):
        check_pin(root, row)
    return write_new(output / 'continuation.json', receipt)


def validate_continuation(root, *, spec_pin, continuation_pin, supervisor_path,
                          reviewed_owner_sources, reviewed_qualifier_sha256):
    root = canonical(root)
    base, sources = source_identity(supervisor_path)
    require(sources == reviewed_owner_sources, 'Reviewed continuation owner changed')
    receipt = decode(check_pin(root, continuation_pin))
    exact(receipt, ('schema', 'diagnostic_only', 'baseline_acceptance', 'qsl_network_acceptance',
                   'phase', 'create_spec', 'create_report', 'reopen_spec', 'fixture', 'reviewed',
                   'qualifier_source', 'owner_sources', 'source_world', 'destination_world',
                   'create_qualification', 'world_inventory'), 'continuation receipt')
    require(receipt['schema'] == RECEIPT_SCHEMA and receipt['phase'] == 'reopen'
            and receipt['diagnostic_only'] is True and receipt['baseline_acceptance'] is False
            and receipt['qsl_network_acceptance'] is False, 'Invalid continuation scope')
    require(receipt['owner_sources'] == sources and receipt['reopen_spec'] == spec_pin
            and receipt['qualifier_source']['sha256'] == reviewed_qualifier_sha256,
            'Continuation source/spec review binding changed')
    create_spec = decode(check_pin(root, receipt['create_spec']))
    spec = decode(check_pin(root, spec_pin))
    check_phase_specs(root, create_spec, spec)
    require(receipt['source_world'] == str(Path(create_spec['server']['cwd']) / 'world')
            and receipt['destination_world'] == str(Path(spec['server']['cwd']) / 'world'),
            'World does not belong to the exact paired roles')
    expected_qualification = decode(check_pin(root, receipt['create_qualification']))
    require(qualify_create(root, receipt, supervisor_path) == expected_qualification,
            'Retained create qualification no longer matches actual evidence')
    inventory = decode(check_pin(root, receipt['world_inventory']))
    verify_world(root, receipt['source_world'], inventory)
    verify_world(root, receipt['destination_world'], inventory)
    base.verify_spec(spec)
    base.verify_pair_seal(Path(spec_pin['path']), spec_pin['sha256'], spec)
    return base, spec, receipt, sources


def owner_report(sources, continuation_pin):
    return dict(sources, schema=OWNER_SCHEMA, phase='reopen', continuation_receipt=continuation_pin)


@contextmanager
def owned_alarm(cutoff, handled_signals):
    """A dedicated supervisor owns its alarm; never borrow or erase a caller timer."""
    require(signal.getitimer(signal.ITIMER_REAL) == (0.0, 0.0),
            'Dedicated continuation process must not inherit an active alarm')
    require(type(cutoff) in (int, float) and math.isfinite(cutoff), 'Finite absolute cutoff required')
    previous, installed, armed = {}, [], False
    def interrupted(signum, _frame):
        raise InterruptedError('Continuation interrupted by signal ' + str(signum))
    try:
        for number in handled_signals:
            previous[number] = signal.getsignal(number)
            installed.append(number)
            signal.signal(number, interrupted)
        remaining = cutoff - time.monotonic()
        require(remaining > 0, 'Absolute work cutoff expired during continuation admission')
        # An active timer appearing during setup is still someone else's timer.
        require(signal.getitimer(signal.ITIMER_REAL) == (0.0, 0.0),
                'Earlier alarm appeared during dedicated supervisor setup')
        armed = True
        signal.setitimer(signal.ITIMER_REAL, remaining)
        yield
    finally:
        if armed:
            signal.setitimer(signal.ITIMER_REAL, 0)
        for number in reversed(installed):
            signal.signal(number, previous[number])


def execute_reopen(root, *, spec_pin, continuation_pin, supervisor_path,
                   reviewed_owner_sources, reviewed_qualifier_sha256, destination,
                   work_cutoff):
    """Dedicated subprocess CLI only, never in-process execution in an outer driver."""
    require(__name__ == '__main__', 'Execute only through the dedicated supervised continuation CLI')
    require(signal.getitimer(signal.ITIMER_REAL) == (0.0, 0.0),
            'Dedicated continuation process must not inherit an active alarm')
    initial_base, _ = load_base(supervisor_path)
    cutoff = initial_base.pair_deadline(work_cutoff)
    arguments = dict(spec_pin=spec_pin, continuation_pin=continuation_pin,
                     supervisor_path=supervisor_path, reviewed_owner_sources=reviewed_owner_sources,
                     reviewed_qualifier_sha256=reviewed_qualifier_sha256)
    base, spec, receipt, sources = validate_continuation(root, **arguments)
    base.unprivileged_runner()
    create_spec = decode(check_pin(root, receipt['create_spec']))
    destination = evidence_destination(root, destination, (create_spec, spec))
    destination.mkdir(mode=0o700)
    run_raw, _ = checked_run_source(read_regular(supervisor_path, MIB, owned=False)[0])
    namespace = dict(base.__dict__)
    exec(compile(run_raw, str(HERE / 'owned_pair_run.py'), 'exec'), namespace)

    class ContinuationPair(base.Pair):
        run = namespace['run']

        def verify_profile_world(self, role, profile):
            if role == 'server':
                require(str(profile / 'world') == receipt['destination_world'], 'Wrong continuation world')
                verify_world(root, profile / 'world', decode(check_pin(root, receipt['world_inventory'])))
            else:
                require(not os.path.lexists(profile / 'world'), 'Fresh disposable client required')

        def revalidate_continuation(self):
            # Under the original serial lock, after memory/graphics gates and
            # immediately before the unchanged owned server spawn.
            _, current_spec, current_receipt, current_sources = validate_continuation(root, **arguments)
            require((current_spec, current_receipt, current_sources) == (spec, receipt, sources),
                    'Continuation changed at launch boundary')
            checked = {'schema': 'quilt-world-prelaunch-v1', 'phase': 'reopen',
                       'continuation_receipt': continuation_pin,
                       'source_world': receipt['source_world'],
                       'destination_world': receipt['destination_world'],
                       'world_inventory': receipt['world_inventory'],
                       'create_spec': receipt['create_spec'], 'create_report': receipt['create_report'],
                       'reopen_spec': spec_pin, 'checked_under_serial_lock': True,
                       'game_spawned_at_check': False}
            self.report['continuation_prelaunch'] = write_new(self.destination / 'world-prelaunch.json', checked)

    # No process, socket, FD, resource, helper, capture or cleanup override exists.
    require(set(ContinuationPair.__dict__) - {'__module__', '__doc__'} ==
            {'run', 'verify_profile_world', 'revalidate_continuation'}, 'Unexpected owner override')
    with owned_alarm(cutoff, base.HANDLED_SIGNALS):
        pair = ContinuationPair(spec, destination, work_cutoff=cutoff)
        pair.report['continuation_owner'] = owner_report(sources, continuation_pin)
        return pair.run(spec_pin['sha256'], Path(spec_pin['path']))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('root', 'spec', 'spec-sha256', 'continuation', 'continuation-sha256',
                 'supervisor', 'owner-source-sha256', 'derivative-run-sha256',
                 'qualifier-sha256', 'destination'):
        parser.add_argument('--' + name, required=True)
    parser.add_argument('--work-cutoff-monotonic', type=float, required=True)
    parser.add_argument('--execute-reviewed-quilt-reopen', action='store_true', required=True)
    args = parser.parse_args()
    # A flag is not authorization. Both seals must carry the existing reviewed
    # task references; the outer driver must supervise this dedicated process.
    root = canonical(args.root)
    def selected(path, expected):
        _, row = read_regular(local(root, path), MAX_JSON)
        require(row['sha256'] == expected, 'Independent CLI evidence digest mismatch')
        return row
    report = execute_reopen(root, spec_pin=selected(args.spec, args.spec_sha256),
        continuation_pin=selected(args.continuation, args.continuation_sha256),
        supervisor_path=canonical(args.supervisor),
        reviewed_owner_sources={'original_supervisor_sha256': BASE_SHA256,
                                'derivative_run_sha256': args.derivative_run_sha256,
                                'owner_source_sha256': args.owner_source_sha256},
        reviewed_qualifier_sha256=args.qualifier_sha256,
        destination=local(root, args.destination), work_cutoff=args.work_cutoff_monotonic)
    print(json.dumps({'schema': 'quilt-continuation-transport-result-v1',
                      'status': 'TRANSPORT_PASS_PENDING_QSL_QUALIFICATION' if report['passed'] else report['status'],
                      'transport_passed': report['passed'], 'qsl_lifecycle_qualified': False,
                      'diagnostic_only': True, 'baseline_acceptance': False,
                      'qsl_network_acceptance': False,
                      'result': str(Path(args.destination) / 'result.json')}))
    return 0 if report['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
