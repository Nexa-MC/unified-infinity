#!/usr/bin/env python3
"""Explicit, bounded Linux CI pair runner. No launch without a reviewed pair seal.

Preparation of this source is not approval to execute it. This program does not
start Xvfb, build/download anything, accept terms, or modify desktop helpers.
"""
import argparse
import ctypes
import difflib
import fcntl
import hashlib
import json
import math
import os
from pathlib import Path
import re
import secrets
import selectors
import select
import signal
import stat
import subprocess
import time
import tomllib

MIB = 1024 * 1024
# Graphics-only bounded receipt: complete installed closure plus measured fields.
GRAPHICS_RECEIPT_MAX_BYTES = 32 * 1024
PROCESS_BYTES = (1280 + 512) * MIB
PAIR_BYTES = PROCESS_BYTES * 2
IDENTITY = 'dd29b97d-cafa-3d53-94e1-f85f75bcf1f6'
NAME = 'APILocal'
MAX_LOG = 2 * MIB
# The sealed 95-entry Unified classpath produces a 20,072-byte JNA line.
# Keep that complete diagnostic within a finite 32 KiB line envelope; the
# 2 MiB process log, 2 KiB protocol JSON, and all capture checks are unchanged.
MAX_LINE = 32 * 1024
MAX_JSON = 2048
TABLES = ('tcp', 'tcp6', 'udp', 'udp6')
PRIVATE = {'HOME': '.launch-home', 'XDG_CACHE_HOME': '.launch-cache',
           'XDG_CONFIG_HOME': '.launch-config', 'XDG_DATA_HOME': '.launch-data',
           'TMPDIR': '.launch-tmp'}
ENV_KEYS = set(PRIVATE) | {'JAVA_HOME', 'PATH', 'DISPLAY', 'XAUTHORITY',
                         'LANG', 'LC_ALL', 'TZ', 'LIBGL_ALWAYS_SOFTWARE',
                         'GALLIUM_DRIVER', '__GLX_VENDOR_LIBRARY_NAME'}
PROBE_FILES = ('network-control-input.json', 'network-control-release.json',
               'network-control-client-result.json', 'network-control-server-result.json')
FAIL_MARKERS = ('NETWORK_CONTROL_FAIL', 'Failed to start the minecraft server',
                'Failed to load mods', 'ModLoadingException', 'MixinApplyError',
                'Exception in thread', 'OutOfMemoryError')
PREPARATION_SHA256 = 'effd845cb6b8673f6e3be7d2a8ce10b6675a9ea281540c46817b25a25ae32c85'
HANDLED_SIGNALS = (signal.SIGTERM, signal.SIGHUP, signal.SIGINT, signal.SIGALRM)
ORIGINAL_MODS = {
    'sophisticatedbackpacks-1.21.1-3.25.34.1604.jar': '889fb2af58e9f7951d0553033a856078b28fcdf802ca13eb432336b2b7b9780c',
    'sophisticatedcore-1.21.1-1.4.11.1553.jar': 'acafbe72eb161b0b763feb61eba06584e97e48f563de75f767611ee520dfcad7',
}
EMI_MODS = {
    'native-neoforge': ('emi-1.1.24+1.21.1+neoforge.jar', 'b68691f94f0727fc517cac2ab55bd6658d1179cc8cc715fe610b60c37469bc4c'),
    'unified': ('emi-1.1.24+1.21.1+fabric.jar', '56ecd418e988cba23dd653d498309fd7b886265708253d5ca7a8fb621dcc5db4'),
}


def require(condition, message):
    if not condition:
        raise ValueError(message)


def exact_keys(value, keys, label):
    require(isinstance(value, dict) and set(value) == set(keys), label + ': unexpected keys')


def integer(value, low=0, high=2**63-1):
    return type(value) is int and low <= value <= high


def digest(path):
    value = hashlib.sha256()
    descriptor = os.open(path, os.O_RDONLY | os.O_NONBLOCK | os.O_NOFOLLOW)
    with os.fdopen(descriptor, 'rb') as stream:
        require(stat.S_ISREG(os.fstat(stream.fileno()).st_mode), 'Expected regular hashed file')
        for chunk in iter(lambda: stream.read(MIB), b''):
            value.update(chunk)
    return value.hexdigest()


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        require(key not in result, 'Duplicate JSON key')
        result[key] = value
    return result


def decode_json(raw, limit=MAX_JSON):
    require(len(raw) <= limit, 'JSON byte bound exceeded')
    return json.loads(raw, object_pairs_hook=unique_object,
                      parse_constant=lambda _: (_ for _ in ()).throw(ValueError('Nonfinite JSON')))


def read_bounded(path, limit):
    descriptor = os.open(path, os.O_RDONLY | os.O_NONBLOCK | os.O_NOFOLLOW)
    with os.fdopen(descriptor, 'rb') as stream:
        require(stat.S_ISREG(os.fstat(stream.fileno()).st_mode), 'Expected regular evidence file')
        raw = stream.read(limit + 1)
    require(len(raw) <= limit, 'File byte bound exceeded')
    return raw


def write_new(path, value):
    data = json.dumps(value, separators=(',', ':')).encode('ascii') + b'\n'
    with Path(path).open('xb') as stream:
        stream.write(data)
        stream.flush()
        os.fsync(stream.fileno())


def publish_release(path, value):
    """Expose the complete LF-terminated release atomically without overwrite."""
    path = Path(path)
    temporary = path.with_name(path.name + '.supervisor-tmp')
    write_new(temporary, value)
    try:
        os.link(temporary, path, follow_symlinks=False)
    finally:
        temporary.unlink()


def clean_path(value):
    require(isinstance(value, str) and '\x00' not in value, 'Invalid path')
    path = Path(value)
    require(path.is_absolute() and '..' not in path.parts, 'Consumer-local absolute path required')
    require(path == path.resolve(), 'Noncanonical or redirected path')
    for parent in (path, *path.parents):
        require(not parent.is_symlink(), 'Symlink in sealed path')
    return path


def unprivileged_runner(proc_root=Path('/proc')):
    """Match kernel access checks to an ordinary nonroot runner, never sudo/root."""
    uids, gids = os.getresuid(), os.getresgid()
    require(uids[0] > 0 and len(set(uids)) == 1 and gids[0] > 0 and len(set(gids)) == 1,
            'Trusted read-only access requires a nonroot matching real/effective/saved identity')
    values = {}
    for line in read_bounded(Path(proc_root) / 'self/status', 65536).decode('ascii').splitlines():
        require(':' in line, 'Malformed runner identity evidence')
        key, value = line.split(':', 1)
        require(key not in values, 'Duplicate runner identity evidence')
        values[key] = value.strip()
    for key, identity in (('Uid', uids), ('Gid', gids)):
        require(re.fullmatch(r'\d+\s+\d+\s+\d+\s+\d+', values.get(key, '')) is not None,
                'Missing runner identity evidence')
        require(tuple(map(int, values[key].split())) == (*identity, identity[0]),
                'Runner filesystem/effective identity mismatch')
    for key in ('CapInh', 'CapPrm', 'CapEff', 'CapAmb'):
        require(re.fullmatch('[0-9a-fA-F]{16}', values.get(key, '')) is not None and
                int(values[key], 16) == 0, 'Privileged or missing runner capability evidence')
    require(os.access in os.supports_effective_ids, 'Effective identity access checks unavailable')
    return {'uid': uids[0], 'gid': gids[0], 'capabilities': 'none'}


def trusted_system_file_access(path, info):
    """The caller's reviewed exact pin supplies file provenance; never infer it.

    Only standard root-owned package files may retain owner-write permission.
    User-owned preparation inputs still use the original read-only seal rule.
    """
    require(info.st_uid == 0 and stat.S_IMODE(info.st_mode) in (0o644, 0o755),
            'Sealed input must be read-only unless a standard root-owned package file')
    unprivileged_runner()
    require(os.access(path, os.R_OK, effective_ids=True) and
            not os.access(path, os.W_OK, effective_ids=True),
            'Trusted system input must be readable and not actually writable by runner')
    # A non-writable inode inside a writable directory could still be replaced.
    require(all(not os.access(parent, os.W_OK, effective_ids=True) for parent in path.parents),
            'Trusted system input has an actually writable parent directory')


def owned_directory_chain(path, root):
    """Explicit preparation root, never a guessed common ancestor."""
    require(path == root or root in path.parents, 'Owned path escapes preparation root')
    for directory in (path, *path.parents):
        current = directory.stat()
        require(stat.S_ISDIR(current.st_mode) and current.st_uid == os.geteuid() and
                stat.S_IMODE(current.st_mode) in (0o700, 0o750, 0o755),
                'Preparation directories must be owned and not group/world writable')
        require(os.access(directory, os.R_OK | os.X_OK, effective_ids=True), 'Preparation directory access denied')
        if directory == root:
            break


def owned_preparation_access(path, info, root):
    """Ordinary owned files remain exactly byte-pinned without chmod or copying."""
    root = clean_path(str(root))
    uid = os.geteuid()
    require(uid > 0 and os.getuid() == uid, 'Owned preparation requires nonroot runner')
    require(root in path.parents, 'Owned input escapes preparation root')
    require(info.st_uid == uid and info.st_nlink == 1 and
            stat.S_IMODE(info.st_mode) in (0o400, 0o440, 0o444, 0o500, 0o550, 0o555,
                                          0o600, 0o640, 0o644, 0o700, 0o750, 0o755),
            'Input must be singly linked, runner-owned and not special or group/world writable')
    owned_directory_chain(path.parent, root)
    access = os.R_OK | (os.X_OK if info.st_mode & 0o111 else 0)
    require(os.access(path, access, effective_ids=True), 'Owned input actual read/execute access denied')
    if info.st_mode & 0o200:
        require(os.access(path, os.W_OK, effective_ids=True), 'Owned input owner-write claim is false')


def preparation_root(roots, value):
    path = Path(value)
    return next((root for root in roots if root in path.parents or root == path), None)


def verify_preparation_roots(values):
    require(isinstance(values, list) and 1 <= len(values) <= 64, 'Bounded explicit preparation roots required')
    require(os.geteuid() > 0 and os.getuid() == os.geteuid(), 'Owned preparation requires nonroot runner')
    roots = [clean_path(value) for value in values]
    for index, root in enumerate(roots):
        require(all(root != other and root not in other.parents and other not in root.parents
                    for other in roots[:index]), 'Duplicate or overlapping preparation roots')
        owned_directory_chain(root, root)
    return roots


def verify_jdk_legal_links(spec, pins, roots):
    """Only manifest-pinned legal-file aliases; no executable/directory aliases."""
    rows = spec.get('jdk_legal_links', [])
    require(isinstance(rows, list) and len(rows) <= 1024, 'JDK legal link bound exceeded')
    jdks = {Path(spec[role]['command'][0]).parent.parent for role in ('server', 'client')}
    links = {}
    for row in rows:
        exact_keys(row, ('path', 'link_text', 'resolved_path', 'jdk_root'), 'JDK legal link')
        jdk = clean_path(row['jdk_root'])
        path = Path(row['path'])
        require(jdk in jdks and str(jdk) in spec['immutable_trees'], 'Legal link must use the exact command JDK root')
        require(path.is_absolute() and '..' not in path.parts and str(path) == row['path'] and
                jdk / 'legal' in path.parents, 'Only legal-file aliases inside the JDK are allowed')
        clean_path(str(path.parent))
        root = preparation_root(roots, str(path))
        require(root is not None, 'Legal link outside explicit preparation roots')
        owned_directory_chain(path.parent, root)
        require(path.is_symlink() and path.lstat().st_uid == os.geteuid(), 'Legal alias must be an owned symlink')
        require(str(path) not in links and str(path) not in pins, 'Duplicate or file-pinned legal alias')
        require(isinstance(row['link_text'], str) and 1 <= len(row['link_text']) <= 4096 and
                '\x00' not in row['link_text'] and not Path(row['link_text']).is_absolute(), 'Bounded relative legal link text required')
        require(os.readlink(path) == row['link_text'], 'JDK legal link text changed')
        target = clean_path(row['resolved_path'])
        require(jdk / 'legal' in target.parents and target.is_file() and str(target) in pins,
                'Legal target must be a canonical pinned file inside the exact JDK')
        links[str(path)] = row
    for initial, row in links.items():
        current, seen = Path(initial), set()
        jdk = Path(row['jdk_root'])
        for _ in range(8):
            require(str(current) not in seen, 'JDK legal link cycle')
            seen.add(str(current))
            require(str(current) in links and links[str(current)]['jdk_root'] == str(jdk), 'Unsealed intermediate legal alias')
            hop = links[str(current)]
            require(os.readlink(current) == hop['link_text'], 'JDK legal link text changed during resolution')
            current = Path(os.path.normpath(current.parent / hop['link_text']))
            require(jdk / 'legal' in current.parents, 'JDK legal link escapes exact JDK legal subtree')
            if not current.is_symlink():
                require(str(clean_path(str(current))) == row['resolved_path'] and str(current) in pins,
                        'JDK legal link resolved target changed')
                break
        else:
            raise ValueError('JDK legal link depth exceeds eight')
    return set(links)


def file_pin(row, owned_profile=None):
    exact_keys(row, ('path', 'bytes', 'sha256'), 'input pin')
    path = clean_path(row['path'])
    require(integer(row['bytes'], 1) and re.fullmatch('[0-9a-f]{64}', row['sha256']), 'Invalid pin')
    info = path.stat()
    require(stat.S_ISREG(info.st_mode) and info.st_size == row['bytes'], 'Input size/type changed')
    if owned_profile is not None:
        owned_preparation_access(path, info, owned_profile)
    elif info.st_mode & 0o222:
        trusted_system_file_access(path, info)
    require(digest(path) == row['sha256'], 'Sealed input digest changed')
    return path


def verify_pair_seal(path, sha256, spec):
    path = clean_path(str(path))
    root = None
    if spec.get('schema') == 'network-ci-pair-v2':
        root = preparation_root(verify_preparation_roots(spec['preparation_roots']), str(path))
        require(root is not None, 'Pair seal outside explicit preparation roots')
    else:
        require(path.stat().st_mode & 0o222 == 0, 'Read-only pair spec seal required')
    file_pin({'path': str(path), 'bytes': path.stat().st_size, 'sha256': sha256}, root)


def property_unescape(text):
    """Java Properties.load escapes, restricted to one physical ASCII line."""
    result, index = [], 0
    while index < len(text):
        character = text[index]
        index += 1
        if character == '\\':
            require(index < len(text), 'Property continuation or trailing escape forbidden')
            character = text[index]
            index += 1
            if character == 'u':
                digits = text[index:index + 4]
                require(re.fullmatch('[0-9a-fA-F]{4}', digits) is not None, 'Malformed property Unicode escape')
                character = chr(int(digits, 16))
                index += 4
            else:
                character = {'t': '\t', 'n': '\n', 'r': '\r', 'f': '\f'}.get(character, character)
        result.append(character)
    return ''.join(result)


def parse_properties(raw):
    """Decode the host's single-line Properties serialization, fail closed.

    No defaults are supplied: every original semantic key/value stays locked.
    Continuations and duplicate decoded keys are deliberately unsupported.
    """
    require(isinstance(raw, bytes) and len(raw) <= 16384, 'Properties byte bound exceeded')
    text = raw.decode('ascii')
    require(all(32 <= ord(c) <= 126 or c in '\t\n\r\f' for c in text), 'Raw property control character')
    result = {}
    for line in re.split(r'\r\n|\n|\r', text):
        line = line.lstrip(' \t\f')
        if not line or line.startswith(('#', '!')):
            continue
        require((len(line) - len(line.rstrip('\\'))) % 2 == 0,
                'Property continuation or trailing escape forbidden')
        index = 0
        while index < len(line):
            if line[index] == '\\':
                index += 2
            elif line[index] in '=:\t\f ':
                break
            else:
                index += 1
        require(index < len(line), 'Unsupported server property syntax')
        key = property_unescape(line[:index])
        if line[index] in ' \t\f':
            while index < len(line) and line[index] in ' \t\f':
                index += 1
        if index < len(line) and line[index] in '=:':
            index += 1
        while index < len(line) and line[index] in ' \t\f':
            index += 1
        value = property_unescape(line[index:])
        require(re.fullmatch('[A-Za-z0-9_.-]+', key) is not None, 'Unsupported server property key')
        require(key not in result, 'Duplicate server property')
        result[key] = value
    return result


def property_values(path):
    return parse_properties(read_bounded(path, 16384))


def capture_server_properties(spec):
    """Full original byte-pin verification before capturing the in-memory baseline."""
    pins = verify_spec(spec)
    path = str(Path(spec['server']['cwd']) / 'server.properties')
    raw = read_bounded(path, 16384)
    require(len(raw) == pins[path]['bytes'] and hashlib.sha256(raw).hexdigest() == pins[path]['sha256'],
            'Server properties changed during prestart capture')
    return raw


def verify_server_properties(row, before, receipt_path, owned_profile=None):
    """One named lifecycle exception; all other input pins use file_pin unchanged."""
    exact_keys(row, ('path', 'bytes', 'sha256'), 'input pin')
    require(integer(row['bytes'], 1) and re.fullmatch('[0-9a-f]{64}', row['sha256']), 'Invalid pin')
    require(isinstance(before, bytes) and len(before) == row['bytes'] and
            hashlib.sha256(before).hexdigest() == row['sha256'], 'Original server property byte pin mismatch')
    path = clean_path(row['path'])
    after = read_bounded(path, 16384)
    receipt = {'schema': 1, 'status': 'REJECTED', 'path': str(path),
               'before': {'bytes': len(before), 'sha256': hashlib.sha256(before).hexdigest(), 'hex': before.hex()},
               'after': {'bytes': len(after), 'sha256': hashlib.sha256(after).hexdigest(), 'hex': after.hex()},
               'byte_identical': before == after,
               'diff': list(difflib.unified_diff(before.decode('ascii', 'backslashreplace').splitlines(keepends=True),
                                               after.decode('ascii', 'backslashreplace').splitlines(keepends=True),
                                               fromfile='pinned-prestart', tofile='observed-post-start'))}
    try:
        # Retain original regular-file, path and permission rules. Verify that
        # bytes did not change while computing this semantic receipt.
        file_pin(dict(row, bytes=len(after), sha256=receipt['after']['sha256']), owned_profile)
        expected, actual = parse_properties(before), parse_properties(after)
        receipt['added_keys'] = sorted(actual.keys() - expected.keys())
        receipt['removed_keys'] = sorted(expected.keys() - actual.keys())
        receipt['changed_keys'] = sorted(k for k in expected.keys() & actual.keys() if expected[k] != actual[k])
        require(actual == expected, 'Server property semantic key/value change')
        receipt['status'] = 'SEMANTICS_PRESERVED'
    except Exception as error:
        receipt['failure'] = type(error).__name__ + ': ' + str(error)
        raise
    finally:
        if receipt_path is not None:
            write_new(receipt_path, receipt)
    return path


def verify_listeners(tables, owned_inodes, port):
    """Exact current preparation validator; source-equivalence checked in tests.

    Require exactly one server-owned IPv4 loopback TCP listener. Reject any other
    listener owned by this process, wildcard/IPv6/UDP sockets, or port collision.
    This is an observation check, not a firewall or network-sandbox claim.
    """
    if set(tables) != {'tcp', 'tcp6', 'udp', 'udp6'}:
        raise ValueError('All IPv4/IPv6 TCP/UDP socket tables are required')
    found = []
    for protocol, text in tables.items():
        if protocol not in {'tcp', 'tcp6', 'udp', 'udp6'}:
            raise ValueError('Unknown socket table')
        for line in text.splitlines()[1:]:
            fields = line.split()
            if len(fields) < 10:
                raise ValueError('Incomplete socket row')
            address, encoded_port = fields[1].split(':')
            local_port = int(encoded_port, 16)
            listening = fields[3] == '0A' if protocol.startswith('tcp') else local_port != 0
            owned = fields[9] in owned_inodes
            if not listening or not (owned or local_port == port):
                continue
            row = {'protocol': protocol, 'addressHex': address, 'port': local_port,
                   'inode': fields[9], 'owned': owned}
            if protocol != 'tcp' or address != '0100007F' or local_port != port or not owned:
                raise ValueError('Unexpected listener/bound UDP socket: ' + json.dumps(row))
            found.append(row)
    if len(found) != 1:
        raise ValueError('Expected exactly one positively owned loopback TCP listener')
    return found[0]


def fixed_lshw_argv_tag(proc, expected, executable_sha256, deadline):
    """Hash-gated, fixed-token diagnostic only. Never return raw arguments."""
    if executable_sha256 != 'ee5d244d47458564a6de33a7d08f8b72a1418c17469ebbd2e3fcc1136ad72c0f':
        return 'NOT_CLASSIFIED'
    try:
        require(time.monotonic() < deadline, 'Diagnostic budget')
        proc.same(expected)
        path = proc.root / str(expected['pid']) / 'cmdline'
        raw = read_bounded(path, 128)
        require(raw == read_bounded(path, 128), 'Arguments changed')
        proc.same(expected)
        require(time.monotonic() < deadline, 'Diagnostic budget')
        return {b'lshw\0-class\0processor\0': 'OSHI_PROCESSOR_FORM',
                b'lshw\0-C\0display\0': 'OSHI_DISPLAY_FORM',
                b'lshw\0-C\0system\0': 'OSHI_SYSTEM_FORM'}.get(raw, 'OTHER_FORM')
    except (OSError, ValueError, UnicodeError):
        return 'UNAVAILABLE'


def rejected_child_executable(proc, expected, deadline):
    """Failure-only diagnostic, never admission. No raw argv, environment or FD contents."""
    result = {'pid': expected['pid'], 'start_ticks': expected['start_ticks'],
              'status': 'UNAVAILABLE'}
    descriptor = None
    try:
        if time.monotonic() >= deadline:
            result['status'] = 'BUDGET_EXHAUSTED'
            return result
        proc.same(expected)
        path = proc.root / str(expected['pid']) / 'exe'
        target = os.readlink(path)
        require(len(os.fsencode(target)) <= 4096, 'Executable link bound')
        # /proc/PID/exe is a kernel magic link. Follow only this exact process
        # handle, never a path copied from its target; reject non-regular files.
        descriptor = os.open(path, os.O_RDONLY | os.O_NONBLOCK | os.O_CLOEXEC)
        before = os.fstat(descriptor)
        require(stat.S_ISREG(before.st_mode), 'Executable is not regular')
        if before.st_size > 8 * MIB:
            result['status'] = 'OVERSIZE'
            return result
        identity_fields = lambda value: (value.st_dev, value.st_ino, value.st_size,
                                        value.st_mode, value.st_uid, value.st_gid,
                                        value.st_mtime_ns, value.st_ctime_ns)
        hasher, count = hashlib.sha256(), 0
        while True:
            if time.monotonic() >= deadline:
                result['status'] = 'BUDGET_EXHAUSTED'
                return result
            chunk = os.read(descriptor, min(65536, 8 * MIB + 1 - count))
            if not chunk:
                break
            count += len(chunk)
            if count > 8 * MIB:
                result['status'] = 'OVERSIZE'
                return result
            hasher.update(chunk)
        require(count == before.st_size and identity_fields(os.fstat(descriptor)) == identity_fields(before),
                'Executable changed while read')
        require(os.readlink(path) == target and identity_fields(os.stat(path)) == identity_fields(before),
                'Executable link changed')
        proc.same(expected)
        argv_tag = fixed_lshw_argv_tag(proc, expected, hasher.hexdigest(), deadline)
        require(os.readlink(path) == target and identity_fields(os.stat(path)) == identity_fields(before)
                and identity_fields(os.fstat(descriptor)) == identity_fields(before),
                'Executable changed during argument classification')
        proc.same(expected)
        # Only fixed public tool labels may be printed; arbitrary path text and
        # arbitrary executable basenames can contain private data and are omitted.
        basename = Path(target.removesuffix(' (deleted)')).name
        public_labels = {'java', 'jspawnhelper', 'sh', 'dash', 'bash', 'stty',
                         'uname', 'tput', 'infocmp', 'ldconfig'}
        result.update(status='OBSERVED_NOT_ADMITTED', sha256=hasher.hexdigest(),
                      bytes=count, device=before.st_dev, inode=before.st_ino,
                      uid=before.st_uid, gid=before.st_gid, mode=stat.S_IMODE(before.st_mode),
                      executable_basename_hint=basename if basename in public_labels else 'WITHHELD',
                      basename_hint_trusted=False, argv_form_tag=argv_tag, argv_form_is_admission=False,
                      link_deleted=target.endswith(' (deleted)'))
    except (FileNotFoundError, ProcessLookupError):
        result['status'] = 'GONE'
    except PermissionError:
        result['status'] = 'UNREADABLE'
    except (OSError, ValueError, UnicodeError):
        result['status'] = 'RACED_OR_UNAVAILABLE'
    finally:
        if descriptor is not None:
            os.close(descriptor)
    return result


def rejected_children_diagnostics(proc, rows):
    # At most 4 * 8 MiB; a shared cooperative two-second budget is checked
    # between reads. This is not a hard kernel syscall timeout.
    deadline = time.monotonic() + 2
    results = []
    for row in rows[:4]:
        try:
            results.append(rejected_child_executable(proc, row, deadline))
        except Exception:
            # Optional diagnostics cannot replace the original rejection/cleanup.
            results.append({'pid': row['pid'], 'start_ticks': row['start_ticks'],
                            'status': 'UNAVAILABLE'})
    return {'observed_count': len(rows), 'reported_count': len(results),
            'truncated': len(rows) > len(results), 'children': results}


# This is an application test contract, not an OS sandbox or permission change.
CPU_PROBE_SHA256 = 'ee5d244d47458564a6de33a7d08f8b72a1418c17469ebbd2e3fcc1136ad72c0f'
CPU_PROBE_BYTES = 980168
CPU_PROBE_ARGV = b'lshw\0-class\0processor\0'
CPU_PROBE_DISPLAY_ARGV = b'lshw\0-C\0display\0'
CPU_PROBE_ALLOWED_ARGV = (CPU_PROBE_ARGV, CPU_PROBE_DISPLAY_ARGV)
CPU_PROBE_PATH = '/usr/bin/lshw'
CPU_PROBE_MAX_PER_ROLE = 4
CPU_PROBE_MAX_SECONDS = 10
CPU_PROBE_MAX_CPU_SECONDS = 2
CPU_PROBE_MAX_RSS = 64 * MIB
CPU_PROBE_RESERVE_BYTES = 2 * CPU_PROBE_MAX_RSS
JDK_SPAWN_SHA256 = 'e3101d3a580c9ae6e973acbf2e861855e93ebceb0bbd8e5fa3ddf6abbf6fd63d'
JDK_SPAWN_BYTES = 17888
JDK_SPAWN_VERSION = b'21.0.12.1+1-LTS'
CPU_PROBE_VERIFY_SECONDS = 1


def cpu_probe_credentials(proc, identity, helper=False, terminal=False):
    """Read only fixed credential/resource fields; never environment or raw argv."""
    def same():
        if not terminal:
            return proc.same(identity)
        actual = proc.identity(identity['pid'])
        require(actual['state'] == 'Z' and all(actual[key] == identity[key] for key in
                ('pid', 'start_ticks', 'ppid', 'pgrp', 'session')), 'CPU probe terminal identity changed')
        return actual
    same()
    values = {}
    for line in read_bounded(proc.root / str(identity['pid']) / 'status', 65536).decode('ascii').splitlines():
        require(':' in line, 'CPU probe malformed status')
        key, value = line.split(':', 1)
        require(key not in values, 'CPU probe duplicate status field')
        values[key] = value.strip()
    for key, ids in (('Uid', os.getresuid()), ('Gid', os.getresgid())):
        require(ids[0] > 0 and len(set(ids)) == 1, 'CPU probe requires ordinary runner identity')
        require(re.fullmatch(r'\d+\s+\d+\s+\d+\s+\d+', values.get(key, '')) is not None and
                tuple(map(int, values[key].split())) == (*ids, ids[0]), 'CPU probe credential mismatch')
    for key in ('CapInh', 'CapPrm', 'CapEff', 'CapAmb'):
        require(re.fullmatch('[0-9a-fA-F]{16}', values.get(key, '')) is not None and
                int(values[key], 16) == 0, 'CPU probe capability mismatch')
    high_water = 0
    if helper:
        require(values.get('Threads') == '1', 'CPU probe must be single threaded')
        require(re.fullmatch(r'\d+ kB', values.get('VmHWM', '')) is not None,
                'CPU probe missing high-water RSS')
        high_water = int(values['VmHWM'].split()[0]) * 1024
        require(high_water <= CPU_PROBE_MAX_RSS, 'CPU probe high-water RSS exceeded')
    same()
    return high_water


def cpu_probe_parent(proc, parent, command):
    live = proc.same(parent)
    require(live['ppid'] == os.getpid(), 'CPU probe game parent was reparented')
    cpu_probe_credentials(proc, parent)
    require(proc.command(parent) == command, 'CPU probe parent command changed')
    expected = os.stat(command[0], follow_symlinks=False)
    actual = os.stat(proc.root / str(parent['pid']) / 'exe')
    signature = lambda value: (value.st_dev, value.st_ino, value.st_size, value.st_mode,
                               value.st_uid, value.st_gid, value.st_mtime_ns, value.st_ctime_ns)
    require(stat.S_ISREG(expected.st_mode) and signature(actual) == signature(expected),
            'CPU probe parent executable changed')
    proc.same(parent)
    return signature(expected)


def cpu_probe_usage(proc, expected):
    raw = read_bounded(proc.root / str(expected['pid']) / 'stat', 16384).decode('ascii')
    fields = raw[raw.rfind(')') + 2:].split()
    require(int(raw[:raw.index('(')].strip()) == expected['pid'] and len(fields) >= 22 and
            int(fields[19]) == expected['start_ticks'], 'CPU probe resource identity changed')
    ticks = os.sysconf('SC_CLK_TCK')
    require(ticks > 0 and int(fields[11]) >= 0 and int(fields[12]) >= 0, 'CPU probe invalid CPU ticks')
    cpu_ticks = int(fields[11]) + int(fields[12])
    age = time.clock_gettime(time.CLOCK_BOOTTIME) - expected['start_ticks'] / ticks
    require(0 <= age <= CPU_PROBE_MAX_SECONDS, 'CPU probe lifetime exceeded')
    require(0 <= cpu_ticks <= CPU_PROBE_MAX_CPU_SECONDS * ticks, 'CPU probe CPU budget exceeded')
    return age, cpu_ticks


def cpu_probe_zombie(proc, expected, parent, command):
    # A previously verified helper may become a direct parent's unreaped zombie.
    # This is terminal observation only: no executable/argv or exit-code claim.
    parent_signature = cpu_probe_parent(proc, parent, command)
    def terminal():
        actual = proc.identity(expected['pid'])
        require(all(actual[key] == expected[key] for key in ('pid', 'start_ticks', 'ppid', 'pgrp', 'session')) and
                actual['state'] == 'Z' and actual['ppid'] == parent['pid'] and
                actual['pgrp'] == parent['pgrp'] and actual['session'] == parent['session'] and
                actual['start_ticks'] >= parent['start_ticks'], 'CPU probe zombie relationship changed')
    terminal()
    cpu_probe_credentials(proc, expected, terminal=True)
    age, cpu_ticks = cpu_probe_usage(proc, expected)
    terminal()
    require(cpu_probe_parent(proc, parent, command) == parent_signature,
            'CPU probe parent executable changed during verification')
    return {'age_seconds': round(age, 3), 'cpu_ticks': cpu_ticks,
            'rss_bytes': 0, 'high_water_rss_bytes': 0}


def cpu_probe_handle_live(descriptor):
    poller = select.poll()
    poller.register(descriptor, select.POLLIN | select.POLLHUP | select.POLLERR)
    require(not poller.poll(0), 'CPU probe retained handle is not live')


def cpu_probe_socket_diagnostic(proc, expected, descriptor_path, target, deadline):
    """Failure-only bounded namespace observation, never socket admission."""
    result = {'admission_evidence': False, 'status': 'UNAVAILABLE'}
    try:
        name = Path(descriptor_path).name
        match = re.fullmatch(r'socket:\[([0-9]{1,20})\]', target)
        require(re.fullmatch(r'[0-9]{1,20}', name) is not None and match is not None,
                'CPU probe socket diagnostic identity malformed')
        inode = match.group(1)
        result.update(fd=int(name), inode=inode)
        require(time.monotonic() < deadline, 'CPU probe socket diagnostic budget exceeded')
        proc.same(expected)
        require(os.readlink(descriptor_path) == target, 'CPU probe socket diagnostic FD changed')
        matches, tables = [], []
        for table in ('tcp', 'tcp6', 'udp', 'udp6', 'unix', 'netlink'):
            require(time.monotonic() < deadline, 'CPU probe socket diagnostic budget exceeded')
            try:
                raw = read_bounded(proc.root / str(expected['pid']) / 'net' / table, 65536)
                lines = raw.decode('ascii').splitlines()
                require(len(lines) <= 1025, 'CPU probe socket diagnostic row bound exceeded')
                hits = []
                for line in lines[1:]:
                    require(time.monotonic() < deadline, 'CPU probe socket diagnostic budget exceeded')
                    fields = line.split()
                    index = 6 if table == 'unix' else 9
                    require(len(fields) > index and re.fullmatch(r'[0-9]{1,20}', fields[index]) is not None,
                            'CPU probe socket diagnostic table malformed')
                    if fields[index] == inode:
                        require(not hits, 'CPU probe socket diagnostic duplicate inode')
                        hit = {'table': table}
                        if table == 'netlink':
                            require(re.fullmatch(r'[0-9]{1,3}', fields[1]) is not None and int(fields[1]) <= 255,
                                    'CPU probe socket diagnostic protocol malformed')
                            hit['protocol'] = int(fields[1])
                        elif table == 'unix':
                            require(re.fullmatch(r'[0-9A-Fa-f]{1,4}', fields[4]) is not None,
                                    'CPU probe socket diagnostic type malformed')
                            hit['type'] = int(fields[4], 16)
                        hits.append(hit)
                matches.extend(hits)
                tables.append({'table': table, 'status': 'READ'})
            except (OSError, ValueError, UnicodeError):
                tables.append({'table': table, 'status': 'UNAVAILABLE'})
        proc.same(expected)
        require(os.readlink(descriptor_path) == target and time.monotonic() < deadline,
                'CPU probe socket diagnostic observation changed or expired')
        result.update(status='OBSERVED', matches=matches, tables=tables,
                      classification='AMBIGUOUS' if len(matches) > 1 else
                      'MATCHED' if matches else 'UNRESOLVED',
                      complete=all(t['status'] == 'READ' for t in tables))
    except Exception:
        # Diagnostic failures must never replace the original socket prohibition.
        result['status'] = 'UNAVAILABLE'
    return result


def cpu_probe_fds(proc, expected, deadline):
    # A live helper may close an enumerated descriptor before readlink. Restart
    # the whole census, never skip an unobserved entry or renew its deadline.
    for attempt in range(3):
        proc.same(expected)
        require(time.monotonic() < deadline, 'CPU probe descriptor bound exceeded')
        changed = False
        with os.scandir(proc.root / str(expected['pid']) / 'fd') as entries:
            for count, descriptor in enumerate(entries, 1):
                require(count <= 64 and time.monotonic() < deadline, 'CPU probe descriptor bound exceeded')
                try:
                    target = os.readlink(descriptor.path)
                except FileNotFoundError as exc:
                    if exc.errno != 2:
                        raise
                    proc.same(expected)
                    changed = True
                    break
                if re.fullmatch(r'socket:\[\d+\]', target) is not None:
                    error = ValueError('CPU probe socket descriptor forbidden')
                    error.socket_diagnostic = cpu_probe_socket_diagnostic(
                        proc, expected, descriptor.path, target, deadline)
                    raise error
        proc.same(expected)
        require(time.monotonic() < deadline, 'CPU probe descriptor bound exceeded')
        if not changed:
            return
    raise ValueError('CPU probe descriptor census remained unstable')


def cpu_probe_sample(proc, expected, parent, command, previous=None, *, deadline=None, transition_context=None):
    """Separate fail-closed admission; diagnostic labels are never authoritative."""
    deadline = time.monotonic() + CPU_PROBE_VERIFY_SECONDS if deadline is None else deadline
    def relationship():
        live_parent, live = proc.same(parent), proc.same(expected)
        require(live_parent['ppid'] == os.getpid() and live['ppid'] == parent['pid'] and
                live['pgrp'] == parent['pgrp'] == parent['pid'] and
                live['session'] == parent['session'] == parent['pid'] and
                live['start_ticks'] >= parent['start_ticks'], 'CPU probe direct-parent relationship changed')
        require(live['state'] in ('R', 'S', 'D'), 'CPU probe unexpected process state')
        require(0 <= live['rss_bytes'] <= CPU_PROBE_MAX_RSS, 'CPU probe RSS exceeded')
        return live
    live = relationship()
    parent_signature = cpu_probe_parent(proc, parent, command)
    high_water = cpu_probe_credentials(proc, expected, helper=True)
    path = proc.root / str(expected['pid']) / 'exe'
    descriptor = None
    try:
        if os.readlink(path) != CPU_PROBE_PATH and previous is None and transition_context is not None:
            pair, retained_pidfd = transition_context
            signature, metrics = cpu_probe_spawn_transition(pair, expected, parent, command, retained_pidfd, deadline)
            metrics['rss_bytes'] = max(metrics['rss_bytes'], live['rss_bytes'])
            metrics['high_water_rss_bytes'] = max(metrics['high_water_rss_bytes'], high_water)
            return signature, metrics
        require(os.readlink(path) == CPU_PROBE_PATH, 'CPU probe executable path changed')
        descriptor = os.open(path, os.O_RDONLY | os.O_NONBLOCK | os.O_CLOEXEC)
        before = os.fstat(descriptor)
        require(stat.S_ISREG(before.st_mode) and before.st_uid == before.st_gid == 0 and
                stat.S_IMODE(before.st_mode) == 0o755 and before.st_nlink == 1 and
                before.st_size == CPU_PROBE_BYTES, 'CPU probe executable metadata mismatch')
        signature = lambda value: (value.st_dev, value.st_ino, value.st_size, value.st_mode,
                                   value.st_uid, value.st_gid, value.st_nlink,
                                   value.st_mtime_ns, value.st_ctime_ns)
        identity = signature(before)
        require(previous is None or (type(previous) is tuple and len(previous) == len(identity) + 1 and
                                     previous[:-1] == identity), 'CPU probe executable identity changed')
        trusted_system_file_access(clean_path(CPU_PROBE_PATH), before)
        hasher, size = hashlib.sha256(), 0
        while True:
            require(time.monotonic() < deadline, 'CPU probe verification budget exceeded')
            chunk = os.read(descriptor, min(65536, CPU_PROBE_BYTES + 1 - size))
            if not chunk:
                break
            size += len(chunk)
            require(size <= CPU_PROBE_BYTES, 'CPU probe executable size exceeded')
            hasher.update(chunk)
        require(size == CPU_PROBE_BYTES and hasher.hexdigest() == CPU_PROBE_SHA256,
                'CPU probe executable digest mismatch')
        args = proc.root / str(expected['pid']) / 'cmdline'
        argv = read_bounded(args, 128)
        require(argv in CPU_PROBE_ALLOWED_ARGV and read_bounded(args, 128) == argv,
                'CPU probe argument form mismatch')
        require(previous is None or previous[-1] == argv, 'CPU probe argument form changed across observations')
        cpu_probe_fds(proc, expected, deadline)
        age, cpu_ticks = cpu_probe_usage(proc, expected)
        require(os.readlink(path) == CPU_PROBE_PATH and signature(os.stat(path)) == identity and
                signature(os.fstat(descriptor)) == identity, 'CPU probe executable changed during verification')
        high_water = max(high_water, cpu_probe_credentials(proc, expected, helper=True))
        require(cpu_probe_parent(proc, parent, command) == parent_signature,
                'CPU probe parent executable changed during verification')
        live = relationship()
        require(time.monotonic() < deadline, 'CPU probe verification budget exceeded')
        return identity + (argv,), {'age_seconds': round(age, 3), 'cpu_ticks': cpu_ticks,
                          'rss_bytes': live['rss_bytes'], 'high_water_rss_bytes': high_water}
    finally:
        if descriptor is not None:
            os.close(descriptor)


def cpu_probe_spawn_census(pair, expected, parent):
    """A bounded wait cannot rely on the process census from before the wait."""
    members = pair.proc.all_identities()
    require(any((row['pid'], row['start_ticks']) == (expected['pid'], expected['start_ticks'])
                for row in members), 'CPU probe transition identity disappeared')
    require(not any(row['ppid'] == expected['pid'] for row in members),
            'CPU probe descendants forbidden')
    require(not any(row['pid'] != expected['pid'] and row['ppid'] == parent['pid']
                    for row in members), 'CPU probe simultaneous instance limit exceeded')
    require(all(row['pid'] in (parent['pid'], expected['pid']) for row in members
                if row['pgrp'] == parent['pgrp'] and row['session'] == parent['session']
                and row['state'] != 'Z'), 'CPU probe unexpected group member during transition')


def cpu_probe_spawn_sample(pair, expected, parent, command, deadline, state=None):
    """Verify one pinned helper snapshot, never infer its pipe-delivered target.

    True means only that the exact target path is now observable; the caller
    must perform a completely independent lshw sample before any acceptance.
    No permission/FD/resource/hash failure is caught or forgiven as a race.
    """
    proc = pair.proc
    helper = clean_path(str(Path(command[0]).parent.parent / 'lib/jspawnhelper'))
    require(Path(command[0]).name == 'java' and Path(command[0]).parent.name == 'bin',
            'CPU probe parent JDK layout changed')
    require(str(helper.parent.parent) in pair.spec['immutable_trees'],
            'CPU probe helper JDK is not sealed')
    pin = {'path': str(helper), 'bytes': JDK_SPAWN_BYTES, 'sha256': JDK_SPAWN_SHA256}
    require(sum(row == pin for row in pair.spec['inputs']) == 1,
            'CPU probe helper original input pin missing')
    root = None
    if pair.spec.get('schema') == 'network-ci-pair-v2':
        root = preparation_root([Path(value) for value in pair.spec['preparation_roots']], str(helper))
        require(root is not None, 'CPU probe helper outside preparation roots')
    require(time.monotonic() < deadline, 'CPU probe verification budget exceeded')
    seal = helper.stat()
    require(stat.S_ISREG(seal.st_mode) and seal.st_nlink == 1 and
            stat.S_IMODE(seal.st_mode) in (0o500, 0o550, 0o555, 0o700, 0o750, 0o755) and
            seal.st_size == JDK_SPAWN_BYTES, 'CPU probe helper metadata mismatch')
    if root is not None:
        owned_preparation_access(helper, seal, root)
    elif seal.st_mode & 0o222:
        trusted_system_file_access(helper, seal)
    signature = lambda value: (value.st_dev, value.st_ino, value.st_size, value.st_mode,
                               value.st_uid, value.st_gid, value.st_nlink,
                               value.st_mtime_ns, value.st_ctime_ns)
    sealed_signature = signature(seal)
    if state is not None:
        require(state.get('executable', sealed_signature) == sealed_signature,
                'CPU probe helper executable changed across observations')
    path = proc.root / str(expected['pid']) / 'exe'
    def target_now():
        proc.same(expected)
        target = os.readlink(path)
        if target not in (str(helper), CPU_PROBE_PATH):
            error = ValueError('CPU probe transition target forbidden')
            # Path-label evidence from this existing readlink only, not inode identity.
            deleted = target.endswith(' (deleted)')
            label = target[:-10] if deleted else target
            error.transition_target_diagnostic = {
                'admission_evidence': False, 'identity_verified': False,
                'path_label': 'PARENT_COMMAND_PATH' if label == command[0] else 'OTHER_PATH',
                'deleted_suffix': deleted}
            raise error
        return target == CPU_PROBE_PATH
    if target_now():
        return True
    descriptor = os.open(path, os.O_RDONLY | os.O_NONBLOCK | os.O_CLOEXEC)
    try:
        before = os.fstat(descriptor)
        if signature(before) != sealed_signature:
            # An exec can happen between readlink and open. Only the exact
            # system target inode may start a fresh, full target verification.
            require(target_now() and signature(before) == signature(os.stat(CPU_PROBE_PATH)),
                    'CPU probe helper executable identity mismatch')
            return True
        hasher, count = hashlib.sha256(), 0
        while True:
            require(time.monotonic() < deadline, 'CPU probe verification budget exceeded')
            chunk = os.read(descriptor, min(65536, JDK_SPAWN_BYTES + 1 - count))
            if not chunk:
                break
            count += len(chunk)
            require(count <= JDK_SPAWN_BYTES, 'CPU probe helper size exceeded')
            hasher.update(chunk)
        require(count == JDK_SPAWN_BYTES and hasher.hexdigest() == JDK_SPAWN_SHA256,
                'CPU probe helper digest mismatch')
        require(signature(os.fstat(descriptor)) == sealed_signature and
                signature(helper.stat()) == sealed_signature, 'CPU probe helper changed during verification')
        if target_now():
            return True
        args = proc.root / str(expected['pid']) / 'cmdline'
        def helper_argv(raw):
            fields = raw.split(b'\0')
            if len(fields) != 4 or fields[0] != os.fsencode(helper) or fields[1] != JDK_SPAWN_VERSION or fields[3]:
                return False
            if re.fullmatch(rb'(?:0|[1-9][0-9]{0,9}):(?:0|[1-9][0-9]{0,9}):(?:0|[1-9][0-9]{0,9})', fields[2]) is None:
                return False
            fds = tuple(map(int, fields[2].split(b':')))
            return len(set(fds)) == 3 and all(value <= 2**31-1 for value in fds)
        raw = read_bounded(args, 8192)
        if not helper_argv(raw):
            require(raw in CPU_PROBE_ALLOWED_ARGV and target_now(), 'CPU probe helper argument form mismatch')
            return True
        again = read_bounded(args, 8192)
        if again != raw:
            require(again in CPU_PROBE_ALLOWED_ARGV and target_now(), 'CPU probe helper argument form changed')
            return True
        if state is not None:
            require(state.get('argv', raw) == raw, 'CPU probe helper argument form changed across observations')
        require(signature(os.fstat(descriptor)) == sealed_signature and
                signature(helper.stat()) == sealed_signature, 'CPU probe helper changed during argument verification')
        if target_now():
            return True
        require(signature(os.stat(path)) == sealed_signature, 'CPU probe helper executable changed')
        if state is not None:
            state.update(executable=sealed_signature, argv=raw)
        return False
    finally:
        os.close(descriptor)


def cpu_probe_spawn_transition(pair, expected, parent, command, retained_pidfd, deadline):
    """Synchronous observation grace only, sharing the original one-second budget."""
    deadline = min(deadline, pair.deadline)
    proc, observations, helper_state = pair.proc, 0, {}
    peak = {'age_seconds': 0, 'cpu_ticks': 0, 'rss_bytes': 0, 'high_water_rss_bytes': 0}
    parent_signature = cpu_probe_parent(proc, parent, command)
    def invariants():
        require(time.monotonic() < deadline, 'CPU probe verification budget exceeded')
        cpu_probe_handle_live(retained_pidfd)
        live = proc.same(expected)
        require(live['ppid'] == parent['pid'] and live['pgrp'] == parent['pgrp'] == parent['pid'] and
                live['session'] == parent['session'] == parent['pid'] and
                live['start_ticks'] >= parent['start_ticks'], 'CPU probe direct-parent relationship changed')
        require(live['state'] in ('R', 'S', 'D'), 'CPU probe unexpected process state')
        require(0 <= live['rss_bytes'] <= CPU_PROBE_MAX_RSS, 'CPU probe RSS exceeded')
        high_water = cpu_probe_credentials(proc, expected, helper=True)
        cpu_probe_fds(proc, expected, deadline)
        age, ticks = cpu_probe_usage(proc, expected)
        metrics = {'age_seconds': round(age, 3), 'cpu_ticks': ticks,
                   'rss_bytes': live['rss_bytes'], 'high_water_rss_bytes': high_water}
        for key, value in metrics.items():
            peak[key] = max(peak[key], value)
        require(cpu_probe_parent(proc, parent, command) == parent_signature,
                'CPU probe parent executable changed during verification')
        role = next((role for role, identity in pair.identities.items() if identity == parent), None)
        require(role is not None and pair.children[role].poll() is None,
                'CPU probe parent exited during verification')
        cpu_probe_spawn_census(pair, expected, parent)
        require(time.monotonic() < deadline, 'CPU probe verification budget exceeded')
    while True:
        invariants()
        transitioned = cpu_probe_spawn_sample(pair, expected, parent, command, deadline, helper_state)
        invariants()
        if transitioned:
            signature, metrics = cpu_probe_sample(proc, expected, parent, command, deadline=deadline)
            invariants()
            metrics = {key: max(value, peak[key]) for key, value in metrics.items()}
            pair.report.setdefault('jdk_spawn_transitions', []).append({
                'pid': expected['pid'], 'start_ticks': expected['start_ticks'],
                'helper_observations': observations, 'target_verified': True})
            return signature, metrics
        observations += 1
        time.sleep(min(0.005, max(0, deadline - time.monotonic())))


def cpu_probe_failure_diagnostic(error, row, records):
    """Failure-only in-memory evidence; never retry, read proc, or admit a child."""
    allowed_frames = {
        'check', 'cpu_probe_sample', 'relationship', 'cpu_probe_parent',
        'cpu_probe_credentials', 'same', 'cpu_probe_fds', 'cpu_probe_usage',
        'cpu_probe_spawn_transition', 'invariants', 'cpu_probe_spawn_sample',
        'target_now', 'cpu_probe_spawn_census', 'cpu_probe_handle_live',
        'cpu_probe_zombie', 'terminal', 'identity', 'command', 'all_identities',
        'read_bounded', 'clean_path', 'trusted_system_file_access',
        'owned_preparation_access', 'preparation_root', 'require'}
    categories = {FileNotFoundError: 'NOT_FOUND', ProcessLookupError: 'NO_PROCESS',
                  PermissionError: 'PERMISSION', ValueError: 'VALUE'}
    result = {'admission_evidence': False,
              'category': categories.get(type(error), 'OS_ERROR' if isinstance(error, OSError) else 'VALUE'),
              'errno': error.errno if isinstance(error, OSError) and type(error.errno) is int
                       and 0 <= error.errno <= 4095 else None}
    if row is not None:
        key = (row['pid'], row['start_ticks'])
        result.update(pid=key[0], start_ticks=key[1], previously_verified=key in records)
    frames, scanned, matched = [], 0, 0
    trace = error.__traceback__
    while trace is not None and scanned < 32:
        code = trace.tb_frame.f_code
        if code.co_filename == cpu_probe_failure_diagnostic.__code__.co_filename and code.co_name in allowed_frames:
            frames.append({'function': code.co_name, 'line': trace.tb_lineno})
            matched += 1
            if len(frames) > 12:
                frames.pop(0)
        trace = trace.tb_next
        scanned += 1
    result.update(frames=frames, traceback_truncated=trace is not None or matched > 12)
    if type(error) is ValueError and hasattr(error, 'socket_diagnostic'):
        result['socket_diagnostic'] = error.socket_diagnostic
    if type(error) is ValueError and hasattr(error, 'transition_target_diagnostic'):
        result['transition_target_diagnostic'] = error.transition_target_diagnostic
    return result


def cpu_probe_retired(pair, row, role, old, members, error, deadline):
    """Reconcile an already verified, now absent identity, not live admission.

    A missing child stat is the sole recoverable observation error. Retained
    pidfd terminal evidence never supplies exit status or final CPU/RSS usage.
    """
    stat_path = pair.proc.root / str(row['pid']) / 'stat'
    require(error.errno == 2 and error.filename == str(stat_path) and
            old is not None and old['observations'] > 0 and old['role'] == role and
            not old.get('terminal_observations'), 'CPU probe retirement evidence unavailable')
    require(all(row[k] == old['identity'][k] for k in
                ('pid', 'start_ticks', 'ppid', 'pgrp', 'session')),
            'CPU probe retirement identity changed')
    parent = pair.identities[role]
    require(row['ppid'] == parent['pid'] and row['pgrp'] == parent['pgrp'] and
            row['session'] == parent['session'], 'CPU probe retirement parent changed')
    require(time.monotonic() < deadline, 'CPU probe retirement budget exceeded')
    poller = select.poll()
    poller.register(old['pidfd'], select.POLLIN | select.POLLHUP | select.POLLERR)
    events = poller.poll(0)
    require(len(events) == 1 and events[0][0] == old['pidfd'] and
            events[0][1] & select.POLLIN and
            not events[0][1] & ~(select.POLLIN | select.POLLHUP),
            'CPU probe retirement handle is not terminal')
    signature = cpu_probe_parent(pair.proc, parent, pair.spec[role]['command'])
    require(pair.children[role].poll() is None, 'CPU probe retirement parent exited')
    ticks = os.sysconf('SC_CLK_TCK')
    require(ticks > 0 and 0 <= time.clock_gettime(time.CLOCK_BOOTTIME) -
            row['start_ticks'] / ticks <= CPU_PROBE_MAX_SECONDS,
            'CPU probe retirement lifetime exceeded')
    fresh = pair.proc.all_identities()
    require(not any(p['pid'] == row['pid'] or p['ppid'] == row['pid'] for p in fresh),
            'CPU probe retirement identity or descendants remain')
    known = {p['pid'] for p in pair.identities.values()}
    helpers = {key[0] for key in pair.cpu_helpers.records}
    groups = {(p['pgrp'], p['session']) for p in pair.identities.values()}
    previous = {(p['pid'], p['start_ticks'], p['ppid'], p['pgrp'], p['session']) for p in members}
    require(all((p['pid'], p['start_ticks'], p['ppid'], p['pgrp'], p['session']) in previous
                for p in fresh if p['pid'] not in known and
                (p['ppid'] in known | helpers | {os.getpid()} or
                 (p['pgrp'], p['session']) in groups)),
            'CPU probe retirement census changed')
    try:
        pair.proc.identity(row['pid'])
    except FileNotFoundError as missing:
        require(missing.errno == 2 and missing.filename == str(stat_path),
                'CPU probe retirement absence unavailable')
    else:
        raise ValueError('CPU probe retirement PID reappeared')
    require(cpu_probe_parent(pair.proc, parent, pair.spec[role]['command']) == signature and
            pair.children[role].poll() is None, 'CPU probe retirement parent changed')
    require(time.monotonic() < deadline, 'CPU probe retirement budget exceeded')


class CpuProbePolicy:
    """Finite observed identities with owned pidfds; no unknown-child allowance."""
    def __init__(self):
        self.records = {}
        self.failed = False

    def check(self, pair, members, candidates):
        require(not self.failed, 'CPU probe failure remains sticky')
        accepted, active = set(), set()
        current = None
        try:
            for row in candidates:
                current = row
                key = (row['pid'], row['start_ticks'])
                role = next((name for name, parent in pair.identities.items()
                             if row['ppid'] == parent['pid']), None)
                require(role is not None and pair.children[role].poll() is None,
                        'CPU probe requires retained live direct game parent')
                require(role not in active, 'CPU probe simultaneous instance limit exceeded')
                require(not any(child['ppid'] == row['pid'] for child in members),
                        'CPU probe descendants forbidden')
                old = self.records.get(key)
                require(old is None or old['role'] == role, 'CPU probe parent role changed')
                if old is None:
                    require(sum(r['role'] == role for r in self.records.values()) < CPU_PROBE_MAX_PER_ROLE,
                            'CPU probe total instance limit exceeded')
                if row['state'] == 'Z':
                    require(old is not None, 'CPU probe unverified zombie forbidden')
                    metrics = cpu_probe_zombie(pair.proc, row, pair.identities[role], pair.spec[role]['command'])
                    require(pair.children[role].poll() is None, 'CPU probe parent exited during verification')
                    old['terminal_observations'] = old.get('terminal_observations', 0) + 1
                    old['metrics'] = {name: max(value, old['metrics'][name]) for name, value in metrics.items()}
                    active.add(role)
                    continue
                require(old is None or not old.get('terminal_observations'), 'CPU probe revived terminal identity')
                fd = os.pidfd_open(row['pid'], 0) if old is None else old['pidfd']
                verification_deadline = time.monotonic() + CPU_PROBE_VERIFY_SECONDS
                try:
                    cpu_probe_handle_live(fd)
                    signature, metrics = cpu_probe_sample(pair.proc, row, pair.identities[role],
                                                         pair.spec[role]['command'],
                                                         old['signature'] if old else None,
                                                         deadline=verification_deadline, transition_context=(pair, fd))
                    cpu_probe_handle_live(fd)
                    require(pair.children[role].poll() is None, 'CPU probe parent exited during verification')
                except FileNotFoundError as error:
                    if old is None:
                        os.close(fd)
                        raise
                    if error.errno != 2 or error.filename != str(pair.proc.root / str(row['pid']) / 'stat'):
                        raise
                    cpu_probe_retired(pair, row, role, old, members, error, verification_deadline)
                    old['terminal_observations'] = old.get('terminal_observations', 0) + 1
                    old['retired_after_stat_race'] = True
                    accepted.add(key)  # Only discharges this stale census row, not live admission.
                    active.add(role)
                    continue
                except BaseException:
                    if old is None:
                        os.close(fd)
                    raise
                if old is None:
                    old = {'role': role, 'identity': dict(row), 'signature': signature,
                           'pidfd': fd, 'observations': 0, 'metrics': metrics, 'reaped': False}
                    self.records[key] = old
                old['observations'] += 1
                old['metrics'] = {name: max(value, old['metrics'][name]) for name, value in metrics.items()}
                accepted.add(key)
                active.add(role)
        except (OSError, ValueError) as error:
            self.failed = True
            self.failure = (str(error) if type(error) is ValueError and str(error).startswith('CPU probe ')
                            else 'CPU probe observation unavailable or raced')
            try:
                self.failure_context = cpu_probe_failure_diagnostic(error, current, self.records)
            except Exception:
                self.failure_context = {'admission_evidence': False, 'status': 'UNAVAILABLE'}
            raise
        finally:
            pair.report['cpu_probe_policy'] = {
                'contract': 'EXACT_OSHI_PROCESSOR_DISPLAY_V3',
                'jdk_spawn_transition': 'SYNCHRONOUS_EXACT_TARGET_REQUIRED',
                'maximum_verification_seconds': CPU_PROBE_VERIFY_SECONDS, 'failed': self.failed,
                'sampled_observations': True, 'hard_resource_enforcement': False,
                'complete_process_history': False,
                'failure': getattr(self, 'failure', None),
                'failure_context': getattr(self, 'failure_context', None),
                'maximum_per_role': CPU_PROBE_MAX_PER_ROLE, 'maximum_simultaneous_per_role': 1,
                'maximum_age_seconds': CPU_PROBE_MAX_SECONDS, 'maximum_cpu_seconds': CPU_PROBE_MAX_CPU_SECONDS,
                'maximum_rss_bytes': CPU_PROBE_MAX_RSS,
                'observed': [{'pid': key[0], 'start_ticks': key[1], 'role': r['role'],
                              'observations': r['observations'], 'terminal_observations': r.get('terminal_observations', 0),
                              'retired_after_stat_race': r.get('retired_after_stat_race', False),
                              **r['metrics']} for key, r in self.records.items()]}
        return accepted

    def signal_owned(self, pair, sig):
        # A retained pidfd cannot target a recycled PID, even after group escape.
        for record in self.records.values():
            try:
                signal.pidfd_send_signal(record['pidfd'], sig)
                pair.report.setdefault('cpu_probe_cleanup_signals', []).append(
                    {'pid': record['identity']['pid'], 'start_ticks': record['identity']['start_ticks'],
                     'signal': sig.name})
            except ProcessLookupError:
                pass
            except OSError:
                pair.report['cleanup_incomplete'] = True

    def cleanup_pending(self, pair):
        """Reap only retained helper pidfds once adopted; never waitpid(-1)."""
        pending = False
        for record in self.records.values():
            if record['reaped']:
                continue
            try:
                waited = os.waitid(os.P_PIDFD, record['pidfd'], os.WEXITED | os.WNOHANG)
                if waited is not None:
                    record['reaped'] = True
                    pair.report.setdefault('cpu_probe_reaped', []).append(record['identity']['pid'])
                    continue
            except ChildProcessError:
                pass  # Still parented to Java, or already reaped by that Java.
            except (OSError, ValueError):
                pair.report['cleanup_incomplete'] = True
                pair.report['cpu_probe_cleanup_observation_error'] = 'Owned helper wait observation unavailable'
                pending = True
            try:
                row = pair.proc.identity(record['identity']['pid'])
                if row['start_ticks'] == record['identity']['start_ticks']:
                    pending = True
            except (FileNotFoundError, ProcessLookupError):
                pass
            except (OSError, ValueError):
                pending = True
        return pending

    def close(self, pair):
        for record in self.records.values():
            try:
                os.close(record['pidfd'])
            except OSError:
                pair.report['cleanup_incomplete'] = True
                pair.report.update(passed=False, status='INCONCLUSIVE')
                pair.report.setdefault('failure', 'Owned helper handle cleanup failed')
        self.records.clear()


class Proc:
    """Production always uses /proc. An injected root exists only for unit fixtures."""
    def __init__(self, root=Path('/proc')):
        self.root = Path(root)

    def identity(self, pid):
        text = read_bounded(self.root / str(pid) / 'stat', 16384).decode('ascii')
        prefix, fields = text[:text.index('(')].strip(), text[text.rfind(')') + 2:].split()
        require(int(prefix) == pid and len(fields) >= 22, 'Malformed process stat')
        return {'pid': pid, 'start_ticks': int(fields[19]), 'ppid': int(fields[1]), 'pgrp': int(fields[2]),
                'session': int(fields[3]), 'state': fields[0], 'rss_bytes': int(fields[21]) * os.sysconf('SC_PAGE_SIZE')}

    def same(self, expected):
        actual = self.identity(expected['pid'])
        for key in ('pid', 'start_ticks', 'pgrp', 'session'):
            require(actual[key] == expected[key], 'Process identity changed: ' + key)
        require(actual['state'] != 'Z', 'Expected live process')
        return actual

    def command(self, identity):
        self.same(identity)
        values = read_bounded(self.root / str(identity['pid']) / 'cmdline', 1024*1024).split(b'\0')
        result = [v.decode('utf-8', 'strict') for v in values if v]
        self.same(identity)
        return result

    def inodes(self, identity):
        self.same(identity)
        result = set()
        for fd in (self.root / str(identity['pid']) / 'fd').iterdir():
            try:
                target = os.readlink(fd)
            except FileNotFoundError:
                continue
            match = re.fullmatch(r'socket:\[(\d+)\]', target)
            if match:
                result.add(match[1])
        self.same(identity)
        return result

    def all_identities(self):
        result = []
        for path in self.root.iterdir():
            if path.name.isdigit():
                try:
                    result.append(self.identity(int(path.name)))
                except (FileNotFoundError, ProcessLookupError):
                    pass
        return result

    def sockets(self, server, port, client=None):
        server_inodes = self.inodes(server)
        client_inodes = self.inodes(client) if client else set()
        tables = {name: read_bounded(self.root / 'net' / name, 2*MIB).decode('ascii') for name in TABLES}
        listener = verify_listeners(tables, server_inodes | client_inodes, port)
        require(listener['inode'] in server_inodes, 'Listener is not owned by server')
        owned = []
        for protocol, table in tables.items():
            for line in table.splitlines()[1:]:
                fields = line.split()
                if fields[9] in server_inodes | client_inodes:
                    owned.append({'protocol': protocol, 'local': fields[1], 'remote': fields[2],
                                  'state': fields[3], 'inode': fields[9],
                                  'role': 'server' if fields[9] in server_inodes else 'client'})
        require(len(owned) <= 16, 'Owned network socket evidence bound exceeded')
        connection = None
        if client:
            require(not server_inodes & client_inodes, 'Shared game socket inode')
            server_endpoint = '0100007F:' + format(port, '04X')
            server_connections = [r for r in owned if r['role'] == 'server' and r['protocol'] == 'tcp'
                                  and r['state'] == '01' and r['local'] == server_endpoint
                                  and r['remote'].startswith('0100007F:')]
            require(len(server_connections) == 1, 'Expected one server-owned established loopback peer')
            connection = server_connections[0]
            peers = [r for r in owned if r['role'] == 'client' and r['protocol'] == 'tcp'
                     and r['state'] == '01' and r['local'] == connection['remote']
                     and r['remote'] == connection['local']]
            require(len(peers) == 1, 'Expected matching client-owned established loopback peer')
        self.same(server)
        if client:
            self.same(client)
        current_inodes = {'server': self.inodes(server), 'client': self.inodes(client) if client else set()}
        require(all(row['inode'] in current_inodes[row['role']] for row in owned), 'Socket ownership changed during observation')
        return {'listener': listener, 'owned': owned, 'connected': connection is not None,
                'tableSha256': {k: hashlib.sha256(v.encode('ascii')).hexdigest() for k, v in tables.items()}}


def verify_environment(env, profile, command, display):
    require(isinstance(env, dict) and not set(env) - ENV_KEYS, 'Environment is not closed')
    require(all(isinstance(v, str) and '\x00' not in v and '\n' not in v for v in env.values()), 'Invalid environment')
    java_home = str(Path(command[0]).parent.parent)
    require(env.get('JAVA_HOME') == java_home, 'JAVA_HOME mismatch')
    require(env.get('PATH') == java_home + '/bin:/usr/bin:/bin', 'Closed PATH required')
    for key, child in PRIVATE.items():
        require(env.get(key) == str(profile / child), 'Private environment directory mismatch')
    require(env.get('LANG') == 'C.UTF-8' and env.get('TZ') == 'UTC', 'Fixed locale/timezone required')
    require(env.get('DISPLAY') == display, 'Display seal mismatch')
    require(env.get('LIBGL_ALWAYS_SOFTWARE') == 'true' and env.get('GALLIUM_DRIVER') == 'llvmpipe', 'Software renderer required')
    require(env.get('__GLX_VENDOR_LIBRARY_NAME', 'mesa') == 'mesa', 'Unexpected GLX vendor')
    return dict(env)  # Deliberately never reads os.environ.


def one_argument(command, name, value):
    require(command.count(name) == 1 and command.index(name) + 1 < len(command), 'Missing/duplicate argument: ' + name)
    require(command[command.index(name) + 1] == value, 'Changed argument: ' + name)


def verify_spec(spec, server_properties_before=None, property_receipt=None):
    keys = ('schema', 'target', 'port', 'authorization', 'inputs', 'immutable_trees',
                     'graphics', 'server', 'client', 'probe_path', 'probe_source_manifest',
                     'probe_build_receipt', 'pair_lock', 'source_receipts')
    if spec.get('schema') == 'network-ci-pair-v2':
        exact_keys(spec, (*keys, 'preparation_roots', 'jdk_legal_links'), 'pair spec')
        roots = verify_preparation_roots(spec['preparation_roots'])
        for role in ('server', 'client'):
            profile = clean_path(spec[role]['cwd'])
            root = preparation_root(roots, str(profile))
            require(root is not None, 'Profile outside explicit preparation roots')
            owned_directory_chain(profile, root)
    else:
        exact_keys(spec, keys, 'pair spec')
        require(spec['schema'] == 'network-ci-pair-v1', 'Unknown pair schema')
        roots = []
    require(spec['target'] in ('native-neoforge', 'unified'), 'Unknown target')
    require(spec['port'] == (25631 if spec['target'] == 'native-neoforge' else 25632), 'Assigned port mismatch')
    exact_keys(spec['authorization'], ('offline_identity_reference', 'eula_reference', 'ci_pair_review_reference'), 'authorization')
    require(all(isinstance(v, str) and 1 <= len(v) <= 512 for v in spec['authorization'].values()), 'Review references required')
    require(isinstance(spec['inputs'], list) and 1 <= len(spec['inputs']) <= 16000, 'Input inventory bound')
    pins = {}
    for row in spec['inputs']:
        config_root = preparation_root(roots, row['path'])
        if spec['schema'] == 'network-ci-pair-v2' and config_root is None:
            require(clean_path(row['path']).stat().st_uid == 0, 'Owned input outside explicit preparation roots')
        if server_properties_before is not None and row.get('path') == str(Path(spec['server']['cwd']) / 'server.properties'):
            path = verify_server_properties(row, server_properties_before, property_receipt, config_root)
        elif server_properties_before is not None and row.get('path') == str(Path(spec['server']['cwd']) / 'ops.json'):
            path = verify_empty_ops_serialization(row, property_receipt, config_root)
        elif server_properties_before is not None and spec['target'] == 'unified' and row.get('path') == str(Path(spec['client']['cwd']) / 'config/fabric/indigo-renderer.properties'):
            path = verify_indigo_timestamp(row, spec, property_receipt, config_root)
        else:
            path = file_pin(row, config_root)
        require(str(path) not in pins, 'Duplicate sealed file')
        pins[str(path)] = row
    require(spec['probe_path'] in pins and spec['probe_path'].endswith('.jar'), 'Built probe must be pinned')
    require(spec['probe_source_manifest'] in pins and spec['probe_build_receipt'] in pins, 'Probe source and build receipts required')
    manifest_path = Path(spec['probe_source_manifest'])
    manifest = decode_json(read_bounded(manifest_path, 256*1024), 256*1024)
    exact_keys(manifest, ('schema', 'status', 'files'), 'probe source manifest')
    require(manifest['schema'] == 1 and manifest['status'] == 'SOURCE_ONLY_NOT_RUNTIME_ACCEPTANCE', 'Expected original source-only probe manifest')
    require(isinstance(manifest['files'], list) and 1 <= len(manifest['files']) <= 128, 'Probe source inventory bound')
    seen = set()
    for row in manifest['files']:
        exact_keys(row, ('path', 'bytes', 'sha256'), 'probe source row')
        relative = Path(row['path'])
        require(not relative.is_absolute() and '..' not in relative.parts and str(relative) not in seen, 'Invalid probe source path')
        seen.add(str(relative))
        path = str(manifest_path.parent / relative)
        require(pins.get(path) == dict(row, path=path), 'Probe source differs from manifest or input pins')
    require('protocol-schema.json' in seen and 'build.gradle' in seen, 'Probe schema/build source must be sealed')
    build = decode_json(read_bounded(spec['probe_build_receipt'], 8192), 8192)
    expected_build = {'schema': 1, 'status': 'BUILT', 'source_manifest_sha256': pins[spec['probe_source_manifest']]['sha256'],
                      'artifact_path': spec['probe_path'], 'artifact_sha256': pins[spec['probe_path']]['sha256'],
                      'artifact_bytes': pins[spec['probe_path']]['bytes']}
    exact_keys(build, expected_build, 'probe build receipt')
    require(build == expected_build, 'Probe JAR/source build binding mismatch')
    require(isinstance(spec['source_receipts'], list) and len(spec['source_receipts']) >= 2, 'Native/portable generation receipts required')
    require(all(p in pins for p in spec['source_receipts']), 'Producer receipt is not sealed')
    require(isinstance(spec['immutable_trees'], list) and spec['immutable_trees'], 'Complete immutable trees required')
    legal_links = verify_jdk_legal_links(spec, pins, roots)
    observed_links = set()
    trees = []
    for value in spec['immutable_trees']:
        root = clean_path(value)
        require(root.is_dir(), 'Missing immutable directory')
        actual = set()
        for path in root.rglob('*'):
            if path.is_symlink():
                require(str(path) in legal_links, 'Redirected immutable entry')
                observed_links.add(str(path))
                continue
            if path.is_file():
                actual.add(str(path))
                require(str(path) in pins, 'Unsealed file in immutable tree')
        require(actual, 'Empty immutable tree')
        trees.append(root)
    require(observed_links == legal_links, 'Legal link manifest is not the complete observed tree inventory')
    exact_keys(spec['graphics'], ('display', 'pid', 'start_ticks', 'executable', 'preflight', 'reserve_bytes'), 'graphics')
    graphics = spec['graphics']
    require(re.fullmatch(r':\d{1,5}', graphics['display']) is not None, 'Literal local DISPLAY required')
    require(graphics['executable'] in pins and graphics['preflight'] in pins, 'Graphics evidence must be sealed')
    require(integer(graphics['reserve_bytes'], 256*MIB), 'Measured graphics reserve required')
    for role in ('server', 'client'):
        row = spec[role]
        exact_keys(row, ('cwd', 'command', 'environment', 'original_mods', 'managed_mods'), role)
        profile = clean_path(row['cwd'])
        require(profile.is_dir(), 'Missing isolated profile')
        command = row['command']
        require(isinstance(command, list) and 4 <= len(command) <= 16384 and
                all(isinstance(v, str) and v and '\x00' not in v and '\n' not in v for v in command), 'Invalid exact command')
        require(command[0] in pins and Path(command[0]).name == 'java', 'Direct pinned Java executable required')
        require(Path(command[0]).parent.parent in trees, 'Complete pinned JDK tree required')
        require(all(not v.startswith('@') for v in command), 'Producer must expand all response files before sealing')
        require([v for v in command if v.startswith('-Xmx')] == ['-Xmx1280m'], '1280 MiB heap required')
        require(not any(v.startswith('-XX:MaxHeapSize=') for v in command), 'Conflicting heap override')
        require([v for v in command if v.startswith('-XX:ActiveProcessorCount=')] == ['-XX:ActiveProcessorCount=2'], 'Two active processors required')
        require(not any(v.startswith(('-javaagent:', '-agentlib:', '-agentpath:', '-XX:Flags=', '-XX:VMOptionsFile=')) for v in command), 'Injected JVM agent/options not allowed')
        require(any(v in ('-cp', '-classpath', '--class-path', '-p', '--module-path') or
                    v.startswith(('--class-path=', '--module-path=')) for v in command), 'Explicit sealed class/module path required')
        for index, value in enumerate(command):
            if value in ('-cp', '-classpath', '--class-path', '-p', '--module-path'):
                require(index + 1 < len(command), 'Missing classpath')
                entries = command[index+1].split(':')
            elif value.startswith(('-DlegacyClassPath=', '--class-path=', '--module-path=')):
                entries = value.split('=', 1)[1].split(':')
            else:
                continue
            for entry in entries:
                require(entry and '*' not in entry, 'No implicit/wildcard classpath')
                path = clean_path(entry)
                require(str(path) in pins or path in trees, 'Every classpath entry must be exactly sealed')
        for value in command:
            if value.startswith('-Djava.library.path='):
                require(all(clean_path(entry) in trees for entry in value.split('=', 1)[1].split(':')), 'Unsealed native-library directory')
        verify_environment(row['environment'], profile, command, graphics['display'])
        require(isinstance(row['original_mods'], list) and len(row['original_mods']) == 3, 'Three original mods required')
        require(isinstance(row['managed_mods'], list), 'Managed mod inventory required')
        expected_originals = dict(ORIGINAL_MODS, **dict([EMI_MODS[spec['target']]]))
        require({Path(p).name: pins.get(p, {}).get('sha256') for p in row['original_mods']} == expected_originals,
                'Original real-mod identities changed')
        require(spec['target'] != 'native-neoforge' or not row['managed_mods'], 'Native pair has no Unified-managed mods')
        mods = [*row['original_mods'], *row['managed_mods'], str(profile / 'mods' / Path(spec['probe_path']).name)]
        require(len(set(mods)) == len(mods), 'Overlapping mod roles')
        require(all(m in pins and Path(m).parent == profile / 'mods' for m in mods), 'Exact profile mod pins required')
        require(pins[mods[-1]]['sha256'] == pins[spec['probe_path']]['sha256'], 'Pair probe bytes differ')
        require(set(mods) == {str(p) for p in (profile / 'mods').iterdir()}, 'Unexpected mod entry')
        require(profile / 'mods' in trees, 'Mods must be complete immutable tree')
        for relative in ('config/neoforge-server.toml', 'defaultconfigs/neoforge-server.toml'):
            path = profile / relative
            require(str(path) in pins, 'Complete NeoForge config pin required')
            config = tomllib.loads(read_bounded(path, 65536).decode())
            require(config.get('advertiseDedicatedServerToLan') is False, 'LAN advertisement must be disabled')
            require(path.parent in trees, 'Complete immutable config directory required')
        if role == 'client':
            for name, value in (('--username', NAME), ('--uuid', IDENTITY),
                                ('--quickPlayMultiplayer', '127.0.0.1:' + str(spec['port'])),
                                ('--accessToken', '0'), ('--gameDir', str(profile))):
                one_argument(command, name, value)
            require(not any(v in command for v in ('--userProperties', '--proxyHost', '--proxyPort', '--clientId', '--xuid')), 'Account/proxy fields forbidden')
            require(command.count('--assetsDir') == 1 and command.count('--assetIndex') == 1, 'Exact official assets arguments required')
            asset_root = clean_path(command[command.index('--assetsDir') + 1])
            asset_index = command[command.index('--assetIndex') + 1]
            require(re.fullmatch('[A-Za-z0-9_.-]+', asset_index) and asset_root in trees,
                    'Complete sealed official asset tree required')
            require(str(asset_root / 'indexes' / (asset_index + '.json')) in pins, 'Official asset index pin required')
        else:
            require('nogui' in command, 'Dedicated no-GUI command required')
            expected = {'server-ip': '127.0.0.1', 'server-port': str(spec['port']), 'online-mode': 'false',
                        'enforce-secure-profile': 'false', 'white-list': 'true', 'enforce-whitelist': 'true',
                        'enable-rcon': 'false', 'enable-query': 'false', 'enable-status': 'false',
                        'max-players': '1', 'level-name': 'world'}
            for relative in ('server.properties', 'whitelist.json', 'ops.json', 'eula.txt'):
                require(str(profile / relative) in pins, 'Pinned server control missing')
            props = property_values(profile / 'server.properties')
            require(all(props.get(k) == v for k, v in expected.items()), 'Unsafe server properties')
            require(decode_json(read_bounded(profile / 'whitelist.json', MAX_JSON)) == [{'uuid': IDENTITY, 'name': NAME}], 'Exact virtual whitelist required')
            require(decode_json(read_bounded(profile / 'ops.json', MAX_JSON)) == [], 'Empty operators required')
            require(read_bounded(profile / 'eula.txt', 128).strip() == b'eula=true', 'Existing EULA receipt required')
    require(spec['server']['cwd'] != spec['client']['cwd'], 'Profiles must be distinct')
    lock = clean_path(spec['pair_lock'])
    require(lock.parent.is_dir(), 'Missing shared pair-lock directory')
    return pins


def verify_indigo_timestamp(row, spec, receipt_path, owned_profile):
    """Only Indigo's Java Properties timestamp comment may change after start."""
    exact_keys(row, ('path','bytes','sha256'), 'Indigo original pin')
    expected_sha = '6ccd84c116ad3a0d4277413074cc5b71ac6e5027ea45aa298a21e0b145b25d9b'
    require(row['bytes'] == 281 and row['sha256'] == expected_sha, 'Unexpected original Indigo configuration')
    baseline = clean_path(spec['pair_lock']).parent / 'indigo-baseline.properties'
    baseline_row = next((r for r in spec['inputs'] if r['path'] == str(baseline)), None)
    require(baseline_row == {'path':str(baseline),'bytes':281,'sha256':expected_sha},
            'Original Indigo baseline must be sealed')
    file_pin(baseline_row, owned_profile)
    before = read_bounded(baseline, 1024)
    require(len(before) == 281 and hashlib.sha256(before).hexdigest() == expected_sha,
            'Original Indigo baseline changed during verification')
    path = clean_path(row['path'])
    after = read_bounded(path, 1024)
    left, right = before.splitlines(keepends=True), after.splitlines(keepends=True)
    require(len(left) == len(right) == 9 and left[0] == right[0] == b'#Indigo properties file\n'
            and left[2:] == right[2:], 'Indigo settings or non-timestamp bytes changed')
    timestamp = rb'#[A-Z][a-z]{2} [A-Z][a-z]{2} [0-9]{2} [0-9]{2}:[0-9]{2}:[0-9]{2} [A-Z]{3} [0-9]{4}\n'
    require(re.fullmatch(timestamp,left[1]) is not None and re.fullmatch(timestamp,right[1]) is not None,
            'Unexpected Indigo timestamp-comment form')
    require(parse_properties(before) == parse_properties(after), 'Indigo semantic settings changed')
    current = {'path':row['path'],'bytes':len(after),'sha256':hashlib.sha256(after).hexdigest()}
    file_pin(current, owned_profile)
    require(receipt_path is not None, 'Indigo serialization evidence required')
    output = Path(receipt_path).with_name(Path(receipt_path).stem+'-indigo-timestamp.json')
    write_new(output, {'schema':1,'status':'EXACT_INDIGO_SETTINGS_PRESERVED','original':row,'baseline':baseline_row,
                       'observed':current,'beforeTimestamp':left[1].decode().rstrip(),
                       'afterTimestamp':right[1].decode().rstrip(),'settings':parse_properties(after),
                       'onlyAllowedChange':'Second-line Java Properties timestamp comment',
                       'beforeHex':before.hex(),'afterHex':after.hex(),'byteIdentical':before == after,
                       'diff':list(difflib.unified_diff(before.decode('ascii').splitlines(keepends=True),
                                                      after.decode('ascii').splitlines(keepends=True),
                                                      fromfile='pinned-prestart',tofile='observed-post-start'))})
    return path


def verify_empty_ops_serialization(row, receipt_path, owned_profile):
    """Allow only Minecraft's observed empty-array newline removal after start."""
    exact_keys(row, ('path','bytes','sha256'), 'original empty-operator pin')
    require(row['bytes'] == 3 and row['sha256'] == hashlib.sha256(b'[]\n').hexdigest(),
            'Expected original exact empty-operator source pin')
    path = clean_path(row['path'])
    content = read_bounded(path, 128)
    require(content in (b'[]\n', b'[]'), 'Operators must remain exactly empty')
    current = {'path':row['path'],'bytes':len(content),'sha256':hashlib.sha256(content).hexdigest()}
    file_pin(current, owned_profile)  # Preserve ownership/type/access/hash rules.
    require(receipt_path is not None, 'Operator serialization evidence required')
    output = Path(receipt_path).with_name(Path(receipt_path).stem+'-empty-ops.json')
    write_new(output, {'schema':1,'status':'EXACT_EMPTY_OPERATORS_PRESERVED','original':row,
                       'observed':current,'operator_count':0,'onlyAllowedChange':'optional terminal LF on the empty JSON array'})
    return path


def verify_graphics(spec, proc):
    graphics = spec['graphics']
    identity = proc.identity(graphics['pid'])
    require(identity['start_ticks'] == graphics['start_ticks'], 'Xvfb identity changed')
    command = proc.command(identity)
    require(command and command[0] == graphics['executable'] and Path(command[0]).name == 'Xvfb', 'Actual pinned Xvfb required')
    require(os.readlink(proc.root / str(identity['pid']) / 'exe') == graphics['executable'], 'Actual Xvfb executable mismatch')
    running, pinned = os.stat(proc.root / str(identity['pid']) / 'exe'), os.stat(graphics['executable'])
    require((running.st_dev, running.st_ino) == (pinned.st_dev, pinned.st_ino), 'Xvfb executable inode mismatch')
    proc.same(identity)
    require(graphics['display'] in command, 'Xvfb display mismatch')
    one_argument(command, '-nolisten', 'tcp')
    require('-listen' not in command, 'Xvfb TCP listening forbidden')
    inodes = proc.inodes(identity)
    socket_path = '/tmp/.X11-unix/X' + graphics['display'][1:]
    rows = read_bounded(proc.root / 'net' / 'unix', 2*MIB).decode('ascii').splitlines()[1:]
    require(any(len(f := line.split()) >= 8 and f[6] in inodes and f[7] == socket_path for line in rows), 'DISPLAY is not owned by recorded Xvfb')
    receipt = decode_json(read_bounded(graphics['preflight'], GRAPHICS_RECEIPT_MAX_BYTES),
                          GRAPHICS_RECEIPT_MAX_BYTES)
    exact_keys(receipt, ('schema', 'display', 'xvfb_pid', 'xvfb_start_ticks', 'renderer',
                         'direct_rendering', 'glx_capable', 'gl_probe_peak_rss_bytes',
                         'measured_headroom_bytes', 'input_sha256'), 'graphics preflight')
    require(receipt['schema'] == 1 and receipt['display'] == graphics['display'] and
            receipt['xvfb_pid'] == identity['pid'] and receipt['xvfb_start_ticks'] == identity['start_ticks'], 'Graphics receipt identity mismatch')
    require(receipt['glx_capable'] is True and receipt['direct_rendering'] is True and
            isinstance(receipt['renderer'], str) and 'llvmpipe' in receipt['renderer'].lower(), 'Measured llvmpipe/GLX capability required')
    require(integer(receipt['gl_probe_peak_rss_bytes'], 1) and integer(receipt['measured_headroom_bytes'], 256*MIB), 'Graphics measurements missing')
    pins = {r['path']: r['sha256'] for r in spec['inputs']}
    require(isinstance(receipt['input_sha256'], dict) and receipt['input_sha256'] and
            all(pins.get(p) == h for p, h in receipt['input_sha256'].items()), 'Unsealed graphics tool/library input')
    reserve = max(graphics['reserve_bytes'], receipt['measured_headroom_bytes'],
                  identity['rss_bytes'] + receipt['gl_probe_peak_rss_bytes'])
    return {'identity': identity, 'reserve_bytes': reserve, 'preflight_sha256': pins[graphics['preflight']]}


def cgroup_directories(proc):
    memberships = read_bounded(proc.root / 'self/cgroup', 16384).decode('ascii').splitlines()
    groups = []
    for row in memberships:
        require(re.fullmatch(r'\d+:[^:]*:/[^\x00]*', row) is not None, 'Malformed cgroup membership')
        if row.startswith('0::'):
            groups.append(row[3:])
    mounts = []
    legacy_memory = False
    for line in read_bounded(proc.root / 'self/mountinfo', MIB).decode('ascii').splitlines():
        require(line.count(' - ') == 1, 'Malformed cgroup mount evidence')
        left, right = line.split(' - ', 1)
        fields, extra = left.split(), right.split()
        require(len(fields) >= 6 and len(extra) >= 3, 'Malformed cgroup mount evidence')
        legacy_memory |= extra[0] == 'cgroup' and 'memory' in extra[2].split(',')
        if extra[0] == 'cgroup2':
            require(not any('\\' in value for value in fields[3:5]), 'Ambiguous escaped cgroup path')
            root, mount = Path(fields[3]), Path(fields[4])
            require(root.is_absolute() and mount.is_absolute() and
                    '..' not in root.parts and '..' not in mount.parts, 'Invalid cgroup mount path')
            mounts.append((root, mount))
    # A raw VM may expose no cgroup hierarchy at all. Missing/unreadable proc
    # evidence is an error, not evidence that no hierarchy exists.
    if not memberships and not mounts and not legacy_memory:
        return [], True
    require(len(groups) == 1 and not legacy_memory, 'Unambiguous unified cgroup v2 required')
    group = Path(groups[0])
    require(group.is_absolute() and '..' not in group.parts, 'Invalid cgroup membership path')
    candidates = [(root, mount) for root, mount in mounts if group.is_relative_to(root)]
    require(len(candidates) == 1, 'Cannot unambiguously resolve actual cgroup v2')
    root, mount = candidates[0]
    require(root == Path('/'), 'Cgroup ancestors are hidden by a subtree mount')
    leaf = mount / group.relative_to(root)
    return [leaf, *[p for p in leaf.parents if p.is_relative_to(mount)]], True


def measured_integer(text, label):
    require(isinstance(text, str) and re.fullmatch(r'0|[1-9]\d*', text) is not None,
            'Malformed ' + label + ' measurement')
    value = int(text)
    require(integer(value), 'Out-of-range ' + label + ' measurement')
    return value


def measured_counters(text, required, label):
    result = {}
    for line in text.splitlines():
        fields = line.split()
        require(len(fields) == 2 and fields[0] not in result, 'Malformed or duplicate ' + label + ' measurement')
        result[fields[0]] = measured_integer(fields[1], label)
    require(set(required) <= result.keys(), 'Missing ' + label + ' measurement')
    return result


def measured_kib(text, field, label):
    rows = [line.split(':', 1)[1].strip() for line in text.splitlines() if line.startswith(field + ':')]
    require(len(rows) == 1 and re.fullmatch(r'(0|[1-9]\d*)[ \t]+kB', rows[0]) is not None,
            'Missing or malformed ' + label + ' measurement')
    value = measured_integer(rows[0].split()[0], label) * 1024
    require(integer(value), 'Out-of-range ' + label + ' measurement')
    return value


def memory_gate(proc, graphics, owned=None):
    require(integer(graphics['reserve_bytes'], 256*MIB), 'Measured graphics reserve required')
    limits, measurements = [], []
    directories, includes_hierarchy_root = cgroup_directories(proc)
    for cg in directories:
        require(cg.is_dir(), 'Missing cgroup measurement directory')
        try:
            maximum_text = read_bounded(cg / 'memory.max', 128).decode('ascii').strip()
        except FileNotFoundError:
            require(includes_hierarchy_root and cg == directories[-1], 'Missing cgroup memory.max measurement')
            measurements.append({'path': str(cg), 'maximum_bytes': None,
                                 'scope': 'actual_hierarchy_root_without_memory_max'})
            continue  # The actual cgroup2 hierarchy root has no configurable limit.
        maximum = None if maximum_text == 'max' else measured_integer(maximum_text, 'memory.max')
        current = measured_integer(read_bounded(cg / 'memory.current', 128).decode('ascii').strip(), 'memory.current')
        stats = measured_counters(read_bounded(cg / 'memory.stat', 65536).decode('ascii'),
                                  ('inactive_file', 'file_dirty', 'file_writeback'), 'memory.stat')
        events_text = read_bounded(cg / 'memory.events', 16384).decode('ascii')
        measured_counters(events_text, ('oom', 'oom_kill'), 'memory.events')
        credit = min(current, max(0, stats['inactive_file'] - stats['file_dirty'] - stats['file_writeback']))
        row = {'path': str(cg), 'maximum_bytes': maximum, 'current_bytes': current,
               'clean_inactive_credit_bytes': credit, 'memory_events': events_text}
        if maximum is not None:
            row['eligible_bytes'] = max(0, maximum - current + credit)
            limits.append(row)
        measurements.append(row)
    host_available = measured_kib(read_bounded(proc.root / 'meminfo', 65536).decode('ascii'),
                                  'MemAvailable', 'MemAvailable')
    eligible = min([host_available, *[row['eligible_bytes'] for row in limits]])
    live_java = []
    for identity in proc.all_identities():
        if identity['state'] == 'Z':
            continue
        try:
            name = (proc.root / str(identity['pid']) / 'comm').read_text().strip()
        except FileNotFoundError:
            continue
        if name in ('java', 'javac'):
            if owned and identity['pid'] == owned['pid']:
                proc.same(owned)
            else:
                live_java.append({'pid': identity['pid'], 'start_ticks': identity['start_ticks']})
    charged = 0
    if owned:
        proc.same(owned)
        # Only anonymous resident bytes are credited; file-backed RSS could also
        # be present in clean-inactive credit and must not be counted twice.
        charged = min(measured_kib(read_bounded(proc.root / str(owned['pid']) / 'status', 65536).decode('ascii'),
                                  'RssAnon', 'owned RssAnon'), PROCESS_BYTES)
        proc.same(owned)
    required = PAIR_BYTES + graphics['reserve_bytes'] + CPU_PROBE_RESERVE_BYTES
    result = {'host_mem_available_bytes': host_available,
              'cgroup_measurements': measurements,
              'memory_bound_source': 'host_and_finite_cgroup_minimum' if limits else 'host_MemAvailable',
              'effective_cgroup_limits': limits, 'eligible_bytes': eligible,
              'owned_server_credit_bytes': charged,
              'pair_bytes': PAIR_BYTES, 'graphics_reserve_bytes': graphics['reserve_bytes'],
              'cpu_probe_reserve_bytes': CPU_PROBE_RESERVE_BYTES,
              'required_bytes': required, 'competing_jvms': live_java}
    require(not live_java and eligible + charged >= required, 'Aggregate memory or competing-JVM gate blocked')
    return result


def no_new_oom_events(gate):
    for row in gate.get('cgroup_measurements', gate['effective_cgroup_limits']):
        if 'memory_events' not in row:
            continue  # Actual hierarchy root without per-cgroup memory controls.
        before = measured_counters(row['memory_events'], ('oom', 'oom_kill'), 'memory.events')
        after = measured_counters(read_bounded(Path(row['path']) / 'memory.events', 16384).decode('ascii'),
                                  ('oom', 'oom_kill'), 'memory.events')
        require(all(after.get(k, 0) == before.get(k, 0) for k in ('oom', 'oom_kill', 'oom_group_kill')), 'New cgroup OOM event')


def become_subreaper():
    # Adoption is needed only to notice a helper escaping a game process group.
    # Such a helper fails the run; this does not grant authority to kill it.
    libc = ctypes.CDLL(None, use_errno=True)
    require(libc.prctl(36, 1, 0, 0, 0) == 0, 'Cannot enable Linux child subreaper')


def validate_probe(row, role, identity, nonce, port):
    keys = ('schema', 'role', 'status', 'nonce', 'sequence', 'counter_before', 'counter_after',
            'player_uuid', 'player_name', 'port', 'pid', 'start_ticks', 'main_thread', 'loopback',
            'memory_connection', 'dedicated_server', 'remote_join', 'phase', 'flow', 'code')
    exact_keys(row, keys, 'probe PASS')
    expected = {'schema': 1, 'role': role, 'status': 'PASS', 'nonce': nonce, 'sequence': 1,
                'counter_before': 0, 'counter_after': 1, 'player_uuid': IDENTITY,
                'player_name': NAME, 'port': port, 'pid': identity['pid'],
                'start_ticks': identity['start_ticks'], 'main_thread': True, 'loopback': True,
                'memory_connection': False, 'dedicated_server': role == 'server',
                'remote_join': role == 'client', 'phase': 'PLAY',
                'flow': 'SERVERBOUND' if role == 'server' else 'CLIENTBOUND', 'code': 'ok'}
    require(all(type(row[k]) is type(v) and row[k] == v for k, v in expected.items()), 'Probe/supervisor observation mismatch')
    require(integer(nonce, 1), 'Nonce must be positive signed 63-bit integer')


def validate_ready(row, identity, port):
    expected = {'schema': 1, 'role': 'server', 'pid': identity['pid'],
                'start_ticks': identity['start_ticks'], 'port': port,
                'main_thread': True, 'dedicated_server': True}
    exact_keys(row, expected, 'server READY')
    require(all(type(row[k]) is type(v) and row[k] == v for k, v in expected.items()), 'Readiness identity mismatch')


def validate_disconnect(row, identity, nonce):
    expected = {'schema': 1, 'role': 'client', 'pid': identity['pid'],
                'start_ticks': identity['start_ticks'], 'nonce': nonce, 'sequence': 1,
                'player_uuid': IDENTITY, 'code': 'ok'}
    exact_keys(row, expected, 'client DISCONNECTED')
    require(all(type(row[k]) is type(v) and row[k] == v for k, v in expected.items()), 'Disconnect identity mismatch')


class CompletedReloadGate:
    MAX_WAIT_SECONDS = 10.0
    DWELL_SECONDS = 2.0
    PROBE_TIMEOUT_SECONDS = 15.0
    PROBE_MARGIN_SECONDS = 1.0
    EMI_LINE = re.compile(r'^\[([^\]\r\n]+)\] \[[^\]\r\n]+/INFO\] \[EMI/\]: \[EMI\] (.+)$')

    def __init__(self, started, reply_absent, hard_deadline):
        require(reply_absent is not None and reply_absent <= started,
                'Missing causal pre-PASS result absence observation')
        self.cutoff = min(hard_deadline, started + self.MAX_WAIT_SECONDS,
                          reply_absent + self.PROBE_TIMEOUT_SECONDS - self.PROBE_MARGIN_SECONDS)
        self.cursor = 0
        self.report = {
            'status': 'WAITING_FOR_CURRENT_RELOAD', 'gate_started_monotonic': started,
            'client_result_absent_monotonic': reply_absent,
            'conservative_probe_deadline_monotonic': reply_absent + self.PROBE_TIMEOUT_SECONDS,
            'gate_cutoff_monotonic': self.cutoff, 'maximum_extra_wait_seconds': self.MAX_WAIT_SECONDS,
            'required_observed_dwell_seconds': self.DWELL_SECONDS,
            'probe_deadline_margin_seconds': self.PROBE_MARGIN_SECONDS,
            'milestones': [], 'reload_start': None, 'reload_completed': None,
            'release_call_started_monotonic': None, 'release_call_returned_monotonic': None,
            'release_published': False,
            'timing_basis': 'Fresh owned stdout observation times; result-file absence precedes the pinned probe release timer; release publication is bounded by call start and return',
        }

    def observe(self, capture):
        require(len(capture.lines) == len(capture.line_observed_monotonic)
                and self.cursor <= len(capture.lines), 'Current-run line observation mismatch')
        for index in range(self.cursor, len(capture.lines)):
            line = capture.lines[index]
            match = self.EMI_LINE.fullmatch(line)
            if match is None:
                continue
            message = match.group(2)
            milestone = None
            if message == 'Starting EMI reload...':
                milestone = 'reload_start'
            elif re.fullmatch(r'Reloaded EMI in [0-9]+ms', message):
                milestone = 'reload_completed'
            elif message == 'Disconnecting from server, EMI data cleared':
                milestone = 'disconnect_before_release'
            if milestone is None:
                continue
            row = {'milestone': milestone, 'line': index + 1, 'raw_line': line,
                   'log_timestamp': match.group(1),
                   'observed_monotonic': capture.line_observed_monotonic[index]}
            self.report['milestones'].append(row)
            if milestone == 'reload_start':
                require(self.report['reload_start'] is None,
                        'A later EMI reload started before release')
                self.report['reload_start'] = row
            elif milestone == 'reload_completed':
                start = self.report['reload_start']
                require(start is not None and start['line'] < row['line'],
                        'Stale EMI completion without a current-run start')
                require(self.report['reload_completed'] is None, 'Duplicate EMI completion')
                require(row['observed_monotonic'] >= start['observed_monotonic'],
                        'EMI observation clock moved backwards')
                self.report['reload_completed'] = row
                self.report['status'] = 'OBSERVING_POST_RELOAD_DWELL'
            else:
                raise ValueError('EMI disconnected before the completed-reload release')
        self.cursor = len(capture.lines)

    def ready(self, now, alive):
        require(alive, 'Completed-reload gate: process exited early')
        require(self.report['gate_started_monotonic'] <= now < self.cutoff,
                'Completed-reload gate timeout before unchanged probe deadline')
        completed = self.report['reload_completed']
        if completed is None:
            return False
        dwell = now - completed['observed_monotonic']
        require(dwell >= 0, 'EMI observation clock moved backwards')
        self.report['observed_dwell_seconds'] = dwell
        if dwell < self.DWELL_SECONDS:
            return False
        self.report.setdefault('dwell_satisfied_monotonic', now)
        return True

    def before_release(self, now, alive):
        require(self.ready(now, alive), 'Completed EMI reload and two-second dwell required')
        require(self.report['release_call_started_monotonic'] is None, 'Duplicate release attempt')
        self.report['status'] = 'PUBLISHING_RELEASE'
        self.report['release_call_started_monotonic'] = now
        self.report['observed_dwell_at_release_seconds'] = now - self.report['reload_completed']['observed_monotonic']
        self.report['extra_wait_before_release_seconds'] = now - self.report['gate_started_monotonic']

    def after_release(self, now):
        self.report['release_published'] = True
        self.report['release_call_returned_monotonic'] = now
        self.report['extra_wait_through_publication_seconds'] = now - self.report['gate_started_monotonic']
        require(self.report['release_call_started_monotonic'] is not None
                and self.report['release_call_started_monotonic'] <= now < self.cutoff,
                'Release publication exceeded conservative completed-reload budget')
        self.report['status'] = 'RELEASE_PUBLISHED_AFTER_OBSERVED_DWELL'


class Capture:
    def __init__(self, path):
        self.stream = Path(path).open('xb')
        self.raw = bytearray()
        self.pending = bytearray()
        self.lines = []
        self.line_observed_monotonic = []
        self.events = {}

    def feed(self, data):
        require(len(self.raw) + len(data) <= MAX_LOG, 'Console byte bound exceeded')
        self.stream.write(data)
        self.stream.flush()
        self.raw.extend(data)
        self.pending.extend(data)
        while b'\n' in self.pending:
            line, _, remainder = self.pending.partition(b'\n')
            self.pending = bytearray(remainder)
            require(len(line) <= MAX_LINE, 'Console line bound exceeded')
            text = line.decode('utf-8', 'strict').rstrip('\r')
            self.lines.append(text)
            self.line_observed_monotonic.append(time.monotonic())
            require(not any(marker in text for marker in FAIL_MARKERS), 'Game/probe failure marker')
            for marker in ('NETWORK_CONTROL_JSON', 'NETWORK_CONTROL_READY', 'NETWORK_CONTROL_DISCONNECTED'):
                if marker in text:
                    require(text.startswith(marker + ' '), 'Probe marker must be exact stdout prefix')
                    row = decode_json(text[len(marker)+1:].encode())
                    require(isinstance(row, dict) and row.get('status') != 'FAIL', 'Probe reported failure')
                    require(marker not in self.events, 'Duplicate probe event')
                    self.events[marker] = row
        require(len(self.pending) <= MAX_LINE, 'Unterminated console line bound exceeded')

    def finish(self):
        require(not self.pending.strip(), 'Truncated console line')

    def close(self):
        self.stream.close()


def pair_deadline(work_cutoff=None):
    """Narrow the existing pair budget; never renew a supplied same-host cutoff."""
    now = time.monotonic()
    require(math.isfinite(now), 'Invalid pair monotonic clock')
    if work_cutoff is None:
        return now + 600
    require(type(work_cutoff) in (int, float) and math.isfinite(work_cutoff) and work_cutoff > now,
            'Invalid or expired absolute pair work cutoff')
    return min(now + 600, work_cutoff)


class Pair:
    def __init__(self, spec, destination, proc=None, work_cutoff=None):
        self.spec = spec
        self.destination = destination
        self.proc = proc or Proc()
        self.children = {}
        self.identities = {}
        self.group_members = {}
        self.cpu_helpers = CpuProbePolicy()
        self.logs = {}
        self.client_result_absent_monotonic = None
        self.selector = selectors.DefaultSelector()
        self.deadline = pair_deadline(work_cutoff)
        self.report = {'schema': 1, 'target': spec['target'], 'status': 'INCONCLUSIVE',
                       'passed': False, 'game_launched': False, 'phase': 'preflight',
                       'observations': [], 'exits': {}, 'cleanup_signals': []}

    def spawn(self, role):
        require(role in ('server', 'client') and role not in self.children, 'Exactly one process per role')
        row = self.spec[role]
        profile = Path(row['cwd'])
        for relative in PRIVATE.values():
            path = clean_path(str(profile / relative))
            path.mkdir(mode=0o700, exist_ok=True)
        capture = Capture(self.destination / (role + '.log'))
        self.logs[role] = capture
        # This entrypoint is deliberately single-threaded. Defer termination
        # while Popen transfers ownership; unblock in the child before exec.
        libc = ctypes.CDLL(None, use_errno=True)
        parent_pid = os.getpid()
        old_mask = signal.pthread_sigmask(signal.SIG_BLOCK, HANDLED_SIGNALS)
        def child_setup():
            signal.pthread_sigmask(signal.SIG_SETMASK, old_mask)
            # The direct game process cannot outlive abrupt supervisor death.
            if libc.prctl(1, signal.SIGKILL, 0, 0, 0) != 0 or os.getppid() != parent_pid:
                os._exit(125)
        try:
            child = subprocess.Popen(row['command'], cwd=profile, env=dict(row['environment']),
                                     stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                     bufsize=0, start_new_session=True, close_fds=True, preexec_fn=child_setup)
            self.children[role] = child
            self.report['game_launched'] = True
        finally:
            signal.pthread_sigmask(signal.SIG_SETMASK, old_mask)
        identity = self.proc.identity(child.pid)
        self.identities[role] = identity
        self.group_members[role] = [identity]
        require(identity['pgrp'] == child.pid and identity['session'] == child.pid, 'Child must own its fresh process group/session')
        require(all(other['pid'] != child.pid or other['start_ticks'] != identity['start_ticks']
                    for name, other in self.identities.items() if name != role), 'Pair process identity collision')
        require(self.proc.command(identity) == row['command'], 'Observed process command differs from seal')
        os.set_blocking(child.stdout.fileno(), False)
        self.selector.register(child.stdout, selectors.EVENT_READ, role)
        self.report['identities'] = self.identities
        write_new(self.destination / (role + '-started.json'), {'role': role, 'identity': identity})

    def pump(self, timeout=0.1):
        require(time.monotonic() < self.deadline, 'Hard pair deadline exceeded')
        if 'client' in self.logs and 'NETWORK_CONTROL_JSON' not in self.logs['client'].events:
            # This fresh result is atomically written before pass() emits stdout
            # and before the pinned client starts its unchanged 15-second timer.
            absent_observed = time.monotonic()
            result_path = Path(self.spec['client']['cwd']) / 'network-control-client-result.json'
            if not os.path.lexists(result_path):
                self.client_result_absent_monotonic = absent_observed
        for key, _ in self.selector.select(timeout):
            data = os.read(key.fileobj.fileno(), 65536)
            if data:
                self.logs[key.data].feed(data)
            else:
                self.selector.unregister(key.fileobj)
        for role, child in self.children.items():
            code = child.poll()
            if code is not None:
                self.report['exits'][role] = code
                require(code == 0, 'Nonzero ' + role + ' exit')
            else:
                require(role in self.identities, 'Initial child identity capture failed')
                try:
                    self.proc.same(self.identities[role])
                except (FileNotFoundError, ProcessLookupError, ValueError) as error:
                    # poll(None) can precede this exact owned child's clean exit.
                    # Never forgive live identity changes or access denials.
                    if isinstance(error, ValueError) and str(error) != 'Expected live process':
                        raise
                    code = child.poll()  # Reconcile only the retained Popen.
                    if code is None:
                        remaining = min(0.2, self.deadline-time.monotonic())
                        require(remaining > 0, 'Hard pair deadline expired during exit reconciliation')
                        try:
                            code = child.wait(timeout=remaining)
                        except subprocess.TimeoutExpired as timeout_error:
                            raise ValueError('Owned child did not become waitable within reconciliation budget') from timeout_error
                    self.report['exits'][role] = code
                    require(code == 0, 'Nonzero ' + role + ' exit during identity observation')
        members = self.proc.all_identities()
        for role, identity in self.identities.items():
            group = [row for row in members if row['pgrp'] == identity['pgrp'] and row['session'] == identity['session'] and row['state'] != 'Z']
            observed = {(row['pid'], row['start_ticks']): row for row in self.group_members[role]}
            observed.update({(row['pid'], row['start_ticks']): row for row in group})
            self.group_members[role] = list(observed.values())
        known = {child.pid for child in self.children.values()}
        helper_pids = {key[0] for key in self.cpu_helpers.records}
        groups = {(row['pgrp'], row['session']) for row in self.identities.values()}
        escaped = [row for row in members if row['pid'] not in known and
                   ((row['pid'], row['start_ticks']) in self.cpu_helpers.records or
                    row['ppid'] in known | helper_pids | {os.getpid()} or
                    (row['pgrp'], row['session']) in groups)]
        try:
            accepted = self.cpu_helpers.check(self, members, escaped)
        except (OSError, ValueError):
            self.report['unexpected_descendants'] = escaped
            self.report['unexpected_descendant_diagnostics'] = rejected_children_diagnostics(self.proc, escaped)
            raise ValueError('Unexpected game descendant or CPU probe contract violation') from None
        for role, identity in self.identities.items():
            group = [row for row in members if row['pgrp'] == identity['pgrp'] and row['session'] == identity['session'] and row['state'] != 'Z']
            require(all(row['pid'] == identity['pid'] or (row['pid'], row['start_ticks']) in accepted
                        for row in group), 'Unexpected descendant process in game group')

    def wait(self, predicate, seconds, label, required_alive=()):
        until = min(self.deadline, time.monotonic() + seconds)
        while True:
            self.pump()
            if predicate():
                return
            require(time.monotonic() < until, label + ' timeout')
            require(all(self.children[r].poll() is None for r in required_alive), label + ': process exited early')

    def wait_for_completed_reload(self):
        gate = CompletedReloadGate(time.monotonic(), self.client_result_absent_monotonic, self.deadline)
        self.report['completed_reload_release'] = gate.report
        self.report['phase'] = 'completed_emi_reload_and_dwell'
        def alive():
            return all(self.children[role].poll() is None for role in ('server', 'client'))
        while True:
            gate.ready(time.monotonic(), alive())
            self.pump(min(0.1, max(0, gate.cutoff - time.monotonic())))
            gate.observe(self.logs['client'])
            gate.ready(time.monotonic(), alive())
            self.observe('during_completed_reload_dwell', connected=True)
            if gate.ready(time.monotonic(), alive()):
                # Catch a later start queued during the final socket observation.
                self.drain()
                gate.observe(self.logs['client'])
                require(gate.ready(time.monotonic(), alive()), 'Completed-reload gate changed before release')
                return gate

    def drain(self):
        # Read all currently available bytes without a blocking tail read.
        for _ in range(128):
            if not self.selector.select(0):
                return
            self.pump(0)
        raise ValueError('Console did not quiesce within bounded drain')

    def send(self, command):
        require(command in (b'save-all flush\n', b'stop\n'), 'Only fixed server shutdown commands allowed')
        self.proc.same(self.identities['server'])
        self.children['server'].stdin.write(command)
        self.children['server'].stdin.flush()

    def probe_results(self, nonce):
        for role in ('server', 'client'):
            row = self.logs[role].events.get('NETWORK_CONTROL_JSON')
            require(row is not None, 'Missing probe result')
            validate_probe(row, role, self.identities[role], nonce, self.spec['port'])
            path = clean_path(str(Path(self.spec[role]['cwd']) / ('network-control-' + role + '-result.json')))
            result = decode_json(read_bounded(path, MAX_JSON))
            require(result == row, 'Result file and stdout disagree')
        return {role: self.logs[role].events['NETWORK_CONTROL_JSON'] for role in ('server', 'client')}

    def observe(self, label, connected=False):
        row = self.proc.sockets(self.identities['server'], self.spec['port'],
                                self.identities['client'] if connected else None)
        row['phase'] = label
        self.report['observations'].append(row)
        return row

    def adopted_group_cleanup_pending(self, until):
        """Terminal-only reaping, not descendant admission or a new signal path."""
        pending = False
        direct = {child.pid for child in self.children.values()}
        try:
            members = self.proc.all_identities()
            for row in members:
                if row['pid'] in direct or row['ppid'] != os.getpid():
                    continue
                role = next((name for name, owner in self.identities.items()
                             if name in self.children and
                             owner['pid'] == owner['pgrp'] == owner['session'] == self.children[name].pid and
                             row['pgrp'] == owner['pgrp'] and row['session'] == owner['session'] and
                             row['start_ticks'] >= owner['start_ticks']), None)
                if role is None or (row['pid'], row['start_ticks']) in self.cpu_helpers.records:
                    continue
                if time.monotonic() >= until:
                    return True
                if row['state'] != 'Z':
                    pending = True  # Keep the existing bounded signal/wait phases alive.
                    continue
                descriptor = None
                try:
                    descriptor = os.pidfd_open(row['pid'], 0)
                    actual = self.proc.identity(row['pid'])
                    require(all(actual[key] == row[key] for key in
                                ('pid', 'start_ticks', 'ppid', 'pgrp', 'session', 'state')),
                            'Adopted zombie identity changed')
                    # The self-parented zombie cannot recycle before this wait.
                    # P_PIDFD also prevents a stale numeric PID from being reaped.
                    waited = os.waitid(os.P_PIDFD, descriptor, os.WEXITED | os.WNOHANG)
                    if waited is None:
                        pending = True
                    else:
                        require(waited.si_pid == row['pid'], 'Adopted zombie wait identity changed')
                        self.report.setdefault('adopted_group_zombies_reaped', []).append(
                            {'role': role, 'pid': row['pid'], 'start_ticks': row['start_ticks'],
                             'pgrp': row['pgrp'], 'session': row['session']})
                except (FileNotFoundError, ProcessLookupError):
                    pass
                finally:
                    if descriptor is not None:
                        os.close(descriptor)
        except (OSError, ValueError):
            self.report['cleanup_incomplete'] = True
            self.report['adopted_group_cleanup_observation_error'] = 'Owned adopted child wait observation unavailable'
            pending = True
        return pending

    def cleanup(self):
        # No pkill, name matching, PID-only termination, or Xvfb shutdown.
        def inspect_survivors():
            try:
                return self.proc.all_identities()
            except (OSError, ValueError) as error:
                self.report['cleanup_incomplete'] = True
                self.report['cleanup_observation_error'] = str(error)[:512]
                return []
        for sig, seconds in ((signal.SIGTERM, 5), (signal.SIGKILL, 5)):
            self.cpu_helpers.signal_owned(self, sig)
            parents = {os.getpid(), *(p.pid for p in self.children.values()),
                       *(p['pid'] for group in self.group_members.values() for p in group)}
            for row in inspect_survivors():
                if row['state'] != 'Z' and row['ppid'] in parents:
                    for role, identity in self.identities.items():
                        if row['pgrp'] == identity['pgrp'] and row['session'] == identity['session']:
                            self.group_members[role].append(row)
            # A direct Popen child is still ours while unreaped, even when its
            # first /proc read failed. Its PID cannot be recycled before waitpid.
            for role, child in self.children.items():
                if role not in self.identities and child.poll() is None:
                    try:
                        os.killpg(child.pid, sig)
                        self.report['cleanup_signals'].append({'role': role, 'pgrp': child.pid, 'signal': sig.name,
                                                              'ownership': 'direct_unreaped_Popen_child'})
                    except ProcessLookupError:
                        pass
            for role, identity in self.identities.items():
                eligible = False
                for member in self.group_members.get(role, []):
                    try:
                        live = self.proc.same(member)
                        eligible |= live['pgrp'] == identity['pgrp'] and live['session'] == identity['session']
                    except (OSError, ValueError):
                        continue
                if eligible:
                    try:
                        os.killpg(identity['pgrp'], sig)
                        self.report['cleanup_signals'].append({'role': role, 'pgrp': identity['pgrp'], 'signal': sig.name})
                    except ProcessLookupError:
                        pass
            until = time.monotonic() + seconds
            while time.monotonic() < until:
                # Poll direct children first, so adoption following their exit is
                # visible before deciding that the whole owned tree is finished.
                direct_pending = any(p.poll() is None for p in self.children.values())
                helper_pending = self.cpu_helpers.cleanup_pending(self)
                adopted_pending = self.adopted_group_cleanup_pending(until)
                if not (direct_pending or helper_pending or adopted_pending):
                    break
                try:
                    self.pump(0.1)
                except (ValueError, OSError):
                    # Failure remains sticky; still reap only our children.
                    time.sleep(0.05)
        if self.cpu_helpers.cleanup_pending(self):
            self.report['cleanup_incomplete'] = True
        for role, child in self.children.items():
            self.report['exits'][role] = child.poll()
            if child.poll() is None:
                self.report['cleanup_incomplete'] = True
        surviving = [row for row in inspect_survivors() if (row['state'] != 'Z' or row['ppid'] == os.getpid()) and
                     (row['pgrp'] in {i['pgrp'] for i in self.identities.values()} or
                      row['ppid'] in {os.getpid(), *(p.pid for p in self.children.values())})]
        if surviving:
            self.report['cleanup_incomplete'] = True
            self.report['surviving_owned_or_adopted_processes'] = surviving

    def run(self, seal_sha, seal_path):
        nonce = secrets.randbelow(2**63-1) + 1
        self.report['spec_sha256'] = seal_sha
        self.report['nonce'] = nonce
        lock = None
        try:
            lock_path = clean_path(self.spec['pair_lock'])
            lock = os.fdopen(os.open(lock_path, os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600), 'r+')
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            verify_pair_seal(seal_path, seal_sha, self.spec)
            server_properties_before = capture_server_properties(self.spec)
            require(not any(p['ppid'] == os.getpid() for p in self.proc.all_identities()), 'CI supervisor requires no preexisting child processes')
            become_subreaper()
            for role in ('server', 'client'):
                profile = Path(self.spec[role]['cwd'])
                require(not (profile / 'world').exists(), 'Fresh disposable profiles required')
                for name in PROBE_FILES:
                    require(not (profile / name).exists(), 'Stale probe input/result/release file')
                    require(not (profile / (name + '.tmp')).exists() and
                            not (profile / (name + '.supervisor-tmp')).exists(), 'Stale probe temporary file')
            graphics = verify_graphics(self.spec, self.proc)
            self.report['graphics'] = graphics
            self.report['initial_memory_gate'] = memory_gate(self.proc, graphics)
            write_new(Path(self.spec['client']['cwd']) / PROBE_FILES[0],
                      {'schema': 1, 'nonce': nonce, 'sequence': 1, 'port': self.spec['port']})
            self.report['phase'] = 'server_start'
            self.spawn('server')
            self.wait(lambda: 'NETWORK_CONTROL_READY' in self.logs['server'].events and
                      any('Done (' in line and 'For help' in line for line in self.logs['server'].lines),
                      300, 'Dedicated server readiness', ('server',))
            validate_ready(self.logs['server'].events['NETWORK_CONTROL_READY'], self.identities['server'], self.spec['port'])
            self.observe('before_client')
            graphics = verify_graphics(self.spec, self.proc)
            self.report['client_memory_gate'] = memory_gate(self.proc, graphics, self.identities['server'])
            verify_spec(self.spec, server_properties_before, self.destination / 'server-properties-before-client.json')
            self.report['phase'] = 'actual_client_join_and_payload'
            self.spawn('client')
            self.wait(lambda: all('NETWORK_CONTROL_JSON' in self.logs[r].events for r in ('server', 'client')),
                      180, 'Actual join and nonce round trip', ('server', 'client'))
            self.report['probe'] = self.probe_results(nonce)
            self.observe('after_matching_reply', connected=True)
            completed_gate = self.wait_for_completed_reload()
            self.report['phase'] = 'client_disconnect'
            completed_gate.before_release(time.monotonic(), all(self.children[r].poll() is None for r in ('server', 'client')))
            publish_release(Path(self.spec['client']['cwd']) / PROBE_FILES[1], {'schema': 1, 'nonce': nonce, 'sequence': 1})
            completed_gate.after_release(time.monotonic())
            self.wait(lambda: self.children['client'].poll() == 0 and
                      'NETWORK_CONTROL_DISCONNECTED' in self.logs['client'].events,
                      30, 'Clean client disconnect and exit', ('server',))
            validate_disconnect(self.logs['client'].events['NETWORK_CONTROL_DISCONNECTED'], self.identities['client'], nonce)
            self.observe('after_client_exit')
            self.report['phase'] = 'save_and_stop'
            self.drain()
            offset = len(self.logs['server'].lines)
            self.send(b'save-all flush\n')
            self.report['save_requested_after_line'] = offset
            def saved():
                lines = self.logs['server'].lines[offset:]
                started = next((i for i, line in enumerate(lines) if 'Saving the game' in line), None)
                return started is not None and any('Saved the game' in line or 'Saved the world' in line for line in lines[started+1:])
            self.wait(saved, 45, 'Save-all flush acknowledgment after command', ('server',))
            self.report['save_acknowledged_after_command'] = True
            self.send(b'stop\n')
            self.report['stop_requested'] = True
            self.wait(lambda: self.children['server'].poll() == 0, 30, 'Server stop')
            self.drain()
            require(any('All dimensions are saved' in line for line in self.logs['server'].lines[offset:]), 'Missing final all-dimensions save')
            self.probe_results(nonce)
            verify_spec(self.spec, server_properties_before, self.destination / 'server-properties-after-stop.json')
            no_new_oom_events(self.report['initial_memory_gate'])
            verify_pair_seal(seal_path, seal_sha, self.spec)
            self.report['pair_spec_unchanged'] = True
            world = clean_path(str(Path(self.spec['server']['cwd']) / 'world/level.dat'))
            require(world.is_file() and 0 < world.stat().st_size <= 2*MIB, 'Saved world metadata missing or unbounded')
            self.report['saved_world_level_dat_sha256'] = digest(world)
            self.report['immutable_inputs_unchanged'] = True
            for capture in self.logs.values():
                capture.finish()
            require(set(self.logs['server'].events) == {'NETWORK_CONTROL_READY', 'NETWORK_CONTROL_JSON'} and
                    set(self.logs['client'].events) == {'NETWORK_CONTROL_JSON', 'NETWORK_CONTROL_DISCONNECTED'},
                    'Unexpected role/event combination')
            # A wait predicate may reap after pump; console drain need not pump again.
            # Read the retained owned children, never infer success from cached exits.
            for role, child in self.children.items():
                require(role in self.identities and child.pid == self.identities[role]['pid'],
                        'Owned child identity mismatch at final exit reconciliation')
                self.report['exits'][role] = child.poll()
            require(set(self.children) == {'server', 'client'} and self.report['exits'] == {'server': 0, 'client': 0}, 'Both owned clean exits required')
            require(not any(p['pgrp'] in {i['pgrp'] for i in self.identities.values()} and p['state'] != 'Z'
                            for p in self.proc.all_identities()), 'Game process group survived')
            require(not any(p['ppid'] == os.getpid() for p in self.proc.all_identities()), 'Adopted game helper survived or requires reaping')
            self.report.update(passed=True, status='PASS', phase='complete')
        except (Exception, KeyboardInterrupt) as error:
            self.report.update(passed=False, status='INCONCLUSIVE')
            self.report['failure'] = type(error).__name__ + ': ' + str(error)
        finally:
            # A one-shot deadline or repeated CI cancellation must not interrupt
            # the bounded, identity-checked cleanup and evidence write.
            signal.setitimer(signal.ITIMER_REAL, 0)
            for sig in HANDLED_SIGNALS:
                signal.signal(sig, signal.SIG_IGN)
            if not self.report['passed']:
                self.cleanup()
            self.cpu_helpers.close(self)
            self.selector.close()
            for role, capture in self.logs.items():
                capture.close()
                self.report.setdefault('log_sha256', {})[role] = digest(self.destination / (role + '.log'))
            for child in self.children.values():
                for pipe in (child.stdin, child.stdout):
                    if pipe is not None:
                        pipe.close()
            if lock is not None:
                lock.close()
            write_new(self.destination / 'result.json', self.report)
        return self.report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--spec', required=True, type=Path)
    parser.add_argument('--sha256', required=True)
    parser.add_argument('--execute-reviewed-ci-pair', action='store_true')
    parser.add_argument('--destination', type=Path)
    parser.add_argument('--work-cutoff-monotonic', type=float)
    args = parser.parse_args()
    require(args.work_cutoff_monotonic is None or args.execute_reviewed_ci_pair,
            'Absolute pair work cutoff applies only to execution')
    work_cutoff = pair_deadline(args.work_cutoff_monotonic) if args.work_cutoff_monotonic is not None else None
    require(re.fullmatch('[0-9a-f]{64}', args.sha256) is not None, 'Expected exact pair-spec SHA-256')
    path = clean_path(str(args.spec))
    require(digest(path) == args.sha256, 'Pair spec digest mismatch')
    spec = decode_json(read_bounded(path, 8*MIB), 8*MIB)
    verify_pair_seal(path, args.sha256, spec)
    verify_spec(spec)
    if not args.execute_reviewed_ci_pair:
        print(json.dumps({'status': 'STATIC_INPUTS_VERIFIED_ONLY', 'game_launched': False,
                          'runtime_evidence_observed': False, 'passed': False}))
        return 0
    unprivileged_runner()
    require(args.destination is not None, 'Fresh local evidence destination required')
    destination = clean_path(str(args.destination))
    require(not destination.exists(), 'Evidence directory already exists')
    destination.mkdir(mode=0o700)
    remaining = 600 if work_cutoff is None else work_cutoff - time.monotonic()
    require(remaining > 0, 'Absolute pair work cutoff expired during validation')
    def interrupted(signum, _frame):
        raise InterruptedError('Supervisor interrupted by signal ' + str(signum))
    previous = {sig: signal.signal(sig, interrupted) for sig in HANDLED_SIGNALS}
    signal.setitimer(signal.ITIMER_REAL, remaining)
    try:
        if work_cutoff is None:
            report = Pair(spec, destination).run(args.sha256, path)
        else:
            report = Pair(spec, destination, work_cutoff=work_cutoff).run(args.sha256, path)
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
        for sig, handler in previous.items():
            signal.signal(sig, handler)
    print(json.dumps({'status': report['status'], 'passed': report['passed'],
                      'game_launched': report['game_launched'], 'result': str(destination / 'result.json')}))
    return 0 if report['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
