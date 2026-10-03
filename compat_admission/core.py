"""Bounded metadata-only admission planner. No extraction, classloading or execution."""
from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import io
import json
import os
from pathlib import Path, PurePosixPath
import re
import stat
import struct
import tomllib
import unicodedata
import zipfile
import zlib

from .versions import UnsupportedVersion, Version, matches

SUPPORTED_MINECRAFT = '1.21.1'
# Global policy for current and future game adapters; adapters may raise this floor.
MINIMUM_JAVA_MAJOR = 21
ID = re.compile(r'[a-z][a-z0-9_-]{1,63}\Z')
RESERVED = {'minecraft', 'java', 'fabricloader', 'neoforge', 'fml'}
CATEGORIES = ('game_version', 'dependency', 'api', 'loader', 'environment', 'metadata', 'security')
RUNTIME_DEFERRED_CODES = {
    'GAME_VERSION_MISMATCH', 'API_BUNDLED_CONFLICT', 'API_VERSION_MISMATCH', 'API_INCOMPATIBLE',
    'ENVIRONMENT_DEPENDENCY', 'ENVIRONMENT_EXCLUDED', 'METADATA_SCHEMA_UNSUPPORTED',
    'METADATA_UNRESOLVED_VERSION', 'METADATA_LEGACY_DEPENDENCY',
}


@dataclass(frozen=True)
class Limits:
    max_archive_bytes: int = 64 * 1024 * 1024
    max_total_archive_bytes: int = 256 * 1024 * 1024
    max_uncompressed_bytes: int = 512 * 1024 * 1024
    max_entry_bytes: int = 64 * 1024 * 1024
    max_metadata_bytes: int = 1024 * 1024
    max_entries: int = 10000
    max_total_entries: int = 30000
    max_archives: int = 128
    max_nested_depth: int = 4
    max_compression_ratio: int = 200
    max_mods: int = 1024
    max_dependencies: int = 256

    def __post_init__(self):
        for key, value in asdict(self).items():
            if not isinstance(value, int) or isinstance(value, bool) or value < 1:
                raise ValueError(f'{key} must be a positive integer')


@dataclass(frozen=True)
class Target:
    minecraft: str = SUPPORTED_MINECRAFT
    environment: str = 'client'
    java_version: str = str(MINIMUM_JAVA_MAJOR)
    fabric_loader_version: str | None = None
    neoforge_version: str | None = None
    fml_version: str | None = None


class AdmissionError(Exception):
    def __init__(self, code, category, message):
        super().__init__(message)
        self.code, self.category = code, category


def fail(code, category, message):
    raise AdmissionError(code, category, message)


def _object_pairs(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            fail('METADATA_DUPLICATE_KEY', 'metadata', f'duplicate JSON key {key!r}')
        result[key] = value
    return result


def strict_json(data):
    # Bound structural nesting before the decoder allocates recursive containers.
    quoted, escaped, depth = False, False, 0
    for byte in data:
        if quoted:
            if escaped:
                escaped = False
            elif byte == 92:
                escaped = True
            elif byte == 34:
                quoted = False
        elif byte == 34:
            quoted = True
        elif byte in (91, 123):
            depth += 1
            if depth > 128:
                fail('SECURITY_METADATA_DEPTH', 'security', 'JSON structural nesting exceeds 128 levels')
        elif byte in (93, 125):
            depth -= 1
    def bad_constant(value):
        fail('METADATA_INVALID_JSON', 'metadata', f'invalid JSON constant {value}')
    return json.loads(data.decode('utf-8'), object_pairs_hook=_object_pairs, parse_constant=bad_constant)


def _string(value, field, limit=256):
    if not isinstance(value, str) or not value or len(value) > limit or any(ord(c) < 32 for c in value):
        fail('METADATA_INVALID_FIELD', 'metadata', f'{field} must be a nonempty string of at most {limit} characters without controls')
    return value


def _id(value):
    if not isinstance(value, str) or not ID.fullmatch(value):
        fail('METADATA_INVALID_ID', 'metadata', f'invalid logical mod id: {value!r}')
    return value


def _version(value):
    _string(value, 'version')
    if '${' in value:
        fail('METADATA_UNRESOLVED_VERSION', 'metadata', f'unresolved version token: {value!r}')
    return value


def _predicate(value, dialect):
    values = value if isinstance(value, list) and dialect == 'fabric' else [value]
    if not values or len(values) > 128 or any(not isinstance(v, str) or not v.strip() or len(v) > 1024 for v in values):
        fail('METADATA_INVALID_FIELD', 'metadata', 'version predicate must contain bounded nonempty strings')
    # Syntax validation must not depend on whether a dependency is installed.
    try:
        matches('1.0.0', value, dialect)
    except UnsupportedVersion as exc:
        fail('DEPENDENCY_UNSUPPORTED_RANGE', 'dependency', str(exc))
    return value


def _path(name):
    if (not name or len(name) > 1024 or '\\' in name or '\x00' in name or ':' in name
            or any(ord(c) < 32 or ord(c) == 127 for c in name)
            or name.startswith('/') or any(p in ('.', '..') for p in name.split('/'))
            or '//' in name):
        fail('SECURITY_UNSAFE_PATH', 'security', f'unsafe archive entry path: {name!r}')
    return str(PurePosixPath(name))


def _guard_directory(data, max_entries):
    """Count central records without allocating ZipInfo objects. ZIP64 fails closed.

    EOCD's count is untrusted: walk each record as well before zipfile parses it.
    This prevents a small archive with huge entry counts exhausting object memory.
    """
    offset = data.rfind(b'PK\x05\x06', max(0, len(data)-65557))
    if offset < 0 or len(data)-offset < 22:
        fail('METADATA_INVALID_ARCHIVE', 'metadata', 'missing ZIP end-of-central-directory record')
    _, disk, cd_disk, disk_count, count, size, start, comment = struct.unpack_from('<4s4H2LH', data, offset)
    if disk or cd_disk or disk_count != count:
        fail('SECURITY_MULTIDISK_ARCHIVE', 'security', 'multi-disk or inconsistent ZIP archives are unsupported')
    if count == 65535 or size == 0xffffffff or start == 0xffffffff or data[max(0, offset-20):offset-16] == b'PK\x06\x07':
        fail('SECURITY_ZIP64_UNSUPPORTED', 'security', 'ZIP64 archives are outside this bounded prototype')
    if count > max_entries:
        fail('SECURITY_ENTRY_COUNT', 'security', 'ZIP entry count budget exceeded before object allocation')
    if offset+22+comment != len(data) or start+size != offset:
        fail('SECURITY_ARCHIVE_LAYOUT', 'security', 'ZIP trailing/prefixed data or inconsistent directory offsets are unsupported')
    position, actual_count, member_ranges = start, 0, []
    while position < offset:
        if position+46 > offset or data[position:position+4] != b'PK\x01\x02':
            fail('SECURITY_ARCHIVE_LAYOUT', 'security', 'invalid central-directory record')
        name_len, extra_len, comment_len, disk_start = struct.unpack_from('<4H', data, position+28)
        if disk_start:
            fail('SECURITY_MULTIDISK_ARCHIVE', 'security', 'multi-disk ZIP members are unsupported')
        compressed, expanded = struct.unpack_from('<2L', data, position+20)
        local_offset = struct.unpack_from('<L', data, position+42)[0]
        if 0xffffffff in (compressed, expanded, local_offset):
            fail('SECURITY_ZIP64_UNSUPPORTED', 'security', 'ZIP64 members are outside this bounded prototype')
        if name_len > 4096:
            fail('SECURITY_UNSAFE_PATH', 'security', 'ZIP filename byte length is excessive')
        if local_offset+30 > start or data[local_offset:local_offset+4] != b'PK\x03\x04':
            fail('SECURITY_ARCHIVE_LAYOUT', 'security', 'invalid ZIP member offset')
        local_flags, local_method = struct.unpack_from('<2H', data, local_offset+6)
        central_flags, central_method = struct.unpack_from('<2H', data, position+8)
        local_name_len, local_extra_len = struct.unpack_from('<2H', data, local_offset+26)
        payload_start = local_offset + 30 + local_name_len + local_extra_len
        payload_end = payload_start + compressed
        if payload_end > start or payload_start > start:
            fail('SECURITY_ARCHIVE_LAYOUT', 'security', 'ZIP member extends into the directory')
        local_name = data[local_offset+30:local_offset+30+local_name_len]
        central_name = data[position+46:position+46+name_len]
        if local_name != central_name or (local_flags, local_method) != (central_flags, central_method):
            fail('SECURITY_ARCHIVE_LAYOUT', 'security', 'ZIP local header differs from directory metadata')
        member_ranges.append((local_offset, payload_end))
        position += 46 + name_len + extra_len + comment_len
        actual_count += 1
        if actual_count > max_entries:
            fail('SECURITY_ENTRY_COUNT', 'security', 'ZIP directory count exceeds budget')
    previous_end = 0
    for member_start, member_end in sorted(member_ranges):
        if member_start < previous_end:
            fail('SECURITY_ARCHIVE_LAYOUT', 'security', 'overlapping ZIP member payloads')
        previous_end = member_end
    if position != offset or count != actual_count:
        fail('SECURITY_ARCHIVE_LAYOUT', 'security', 'ZIP directory size/count mismatch')


def _read_regular(path, limit):
    """Open no-follow and bound the bytes read even if a file grows after fstat."""
    try:
        fd = os.open(os.fspath(path), os.O_RDONLY | getattr(os, 'O_NOFOLLOW', 0) | getattr(os, 'O_NONBLOCK', 0))
        with os.fdopen(fd, 'rb') as stream:
            before = os.fstat(stream.fileno())
            if not stat.S_ISREG(before.st_mode):
                fail('SECURITY_NOT_REGULAR_FILE', 'security', 'input must be a regular non-symlink file')
            if before.st_size > limit:
                fail('SECURITY_ARCHIVE_SIZE', 'security', f'input exceeds {limit} bytes')
            data = stream.read(limit + 1)
            after = os.fstat(stream.fileno())
            if len(data) > limit:
                fail('SECURITY_ARCHIVE_SIZE', 'security', f'input exceeds {limit} bytes')
            if (before.st_size, before.st_mtime_ns, before.st_ctime_ns) != (after.st_size, after.st_mtime_ns, after.st_ctime_ns):
                fail('SECURITY_INPUT_CHANGED', 'security', 'input changed while reading')
            return data
    except OSError as exc:
        fail('SECURITY_INPUT_UNREADABLE', 'security', f'cannot read input: {exc.strerror}')


class Planner:
    def __init__(self, target, limits, runtime_authoritative=False):
        self.target, self.limits = target, limits
        self.runtime_authoritative = runtime_authoritative
        self.issues, self.artifacts, self.mods, self.bundled = [], [], [], []
        self.archive_bytes = self.entry_count = self.declared_bytes = 0
        self.graph, self.order_graph = {}, {}
        self.inventory_source = None

    def issue(self, code, category, message, *, origin=None, mod_id=None, severity='error', **details):
        deferred = self.runtime_authoritative and (code in RUNTIME_DEFERRED_CODES or code.startswith('DEPENDENCY_') or code.startswith('LOADER_'))
        issue = {'code': code, 'category': category, 'severity': 'deferred' if deferred else severity, 'message': message}
        if deferred:
            issue['decision_owner'] = 'pinned_neoforge_fml_and_sinytra_connector'
            issue['diagnostic_severity'] = severity
        if origin is not None:
            issue['origin'] = origin
        if mod_id is not None:
            issue['logical_id'] = mod_id
        if details:
            issue['details'] = details
        self.issues.append(issue)

    def caught(self, exc, origin):
        if isinstance(exc, AdmissionError):
            self.issue(exc.code, exc.category, str(exc), origin=origin)
        else:
            self.issue('METADATA_INVALID_ARCHIVE', 'metadata', f'{type(exc).__name__}: {str(exc)[:512]}', origin=origin)

    def inventory(self, path):
        origin = str(Path(path).absolute())
        try:
            data = _read_regular(path, self.limits.max_metadata_bytes)
            obj = strict_json(data)
            self.inventory_source = {'origin': origin, 'sha256': hashlib.sha256(data).hexdigest()}
            if not isinstance(obj, dict) or obj.get('schema_version') != 1 or isinstance(obj.get('schema_version'), bool) or not isinstance(obj.get('bundled_apis'), list):
                fail('API_INVALID_INVENTORY', 'api', 'inventory requires schema_version: 1 and bundled_apis list')
            if len(obj['bundled_apis']) > self.limits.max_mods:
                fail('SECURITY_MOD_LIMIT', 'security', 'bundled inventory exceeds logical mod limit')
            records = []
            for record in obj['bundled_apis']:
                if not isinstance(record, dict):
                    fail('API_INVALID_INVENTORY', 'api', 'each bundled API must be an object')
                mid, version = _id(record.get('id')), _version(record.get('version'))
                if mid in RESERVED:
                    fail('API_RESERVED_ID', 'api', f'bundled API cannot impersonate runtime id {mid}')
                aliases = record.get('provides', [])
                if not isinstance(aliases, list) or len(aliases) > self.limits.max_dependencies:
                    fail('API_INVALID_INVENTORY', 'api', 'bundled API provides must be a bounded list')
                aliases = [_id(alias) for alias in aliases]
                if len(set([mid] + aliases)) != len([mid] + aliases) or any(alias in RESERVED for alias in aliases):
                    fail('API_INVALID_INVENTORY', 'api', 'bundled API aliases must be unique and non-reserved')
                ecosystem = record.get('ecosystem')
                if ecosystem not in ('fabric', 'neoforge'):
                    fail('API_INVALID_INVENTORY', 'api', 'bundled API ecosystem must be fabric or neoforge')
                env = record.get('environment', '*')
                if env not in ('*', 'client', 'server'):
                    fail('API_INVALID_INVENTORY', 'api', 'bundled API environment must be *, client, or server')
                sha = record.get('sha256')
                if sha is not None and (not isinstance(sha, str) or not re.fullmatch('[0-9a-f]{64}', sha)):
                    fail('API_INVALID_INVENTORY', 'api', 'optional sha256 must be 64 lowercase hexadecimal characters')
                records.append({'id': mid, 'version': version, 'ecosystem': ecosystem, 'environment': env,
                                'origin': origin, 'bundled': True, 'active': env in ('*', self.target.environment),
                                'sha256': sha, 'provides': aliases, 'verification': 'provided_inventory_only'})
            self.bundled.extend(records)
        except (AdmissionError, ValueError, UnicodeError, RecursionError) as exc:
            self.caught(exc, origin)

    def scan_file(self, path):
        origin = str(Path(path).absolute())
        try:
            remaining = self.limits.max_total_archive_bytes - self.archive_bytes
            if remaining < 1:
                fail('SECURITY_TOTAL_ARCHIVE_SIZE', 'security', 'total archive byte budget exhausted')
            data = _read_regular(path, min(self.limits.max_archive_bytes, remaining))
            self.scan_bytes(data, origin, 0, None)
        except (AdmissionError, zipfile.BadZipFile, ValueError, UnicodeError, RuntimeError, NotImplementedError, OSError, zlib.error, EOFError) as exc:
            self.caught(exc, origin)

    def scan_bytes(self, data, origin, depth, parent):
        if depth > self.limits.max_nested_depth:
            fail('SECURITY_NESTING_DEPTH', 'security', 'nested JAR depth budget exceeded')
        if len(self.artifacts) >= self.limits.max_archives:
            fail('SECURITY_ARCHIVE_COUNT', 'security', 'archive count budget exceeded')
        if len(data) > self.limits.max_archive_bytes:
            fail('SECURITY_ARCHIVE_SIZE', 'security', 'archive byte budget exceeded')
        self.archive_bytes += len(data)
        if self.archive_bytes > self.limits.max_total_archive_bytes:
            fail('SECURITY_TOTAL_ARCHIVE_SIZE', 'security', 'total archive byte budget exceeded')
        artifact = {'origin': origin, 'parent': parent, 'depth': depth, 'sha256': hashlib.sha256(data).hexdigest(),
                    'size_bytes': len(data), 'ecosystem': None, 'logical_ids': []}
        self.artifacts.append(artifact)
        _guard_directory(data, min(self.limits.max_entries, self.limits.max_total_entries - self.entry_count))
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            entries = archive.infolist()
            self.entry_count += len(entries)
            if len(entries) > self.limits.max_entries or self.entry_count > self.limits.max_total_entries:
                fail('SECURITY_ENTRY_COUNT', 'security', 'ZIP entry count budget exceeded')
            seen, by_name = set(), {}
            for entry in entries:
                if entry.orig_filename != entry.filename:
                    fail('SECURITY_UNSAFE_PATH', 'security', 'ZIP contains truncated NUL filename')
                normalized = _path(entry.filename)
                key = unicodedata.normalize('NFC', normalized).casefold()
                if key in seen:
                    fail('SECURITY_DUPLICATE_ENTRY', 'security', f'duplicate or ambiguous ZIP entry: {entry.filename!r}')
                seen.add(key); by_name[entry.filename] = entry
                mode = entry.external_attr >> 16
                filetype = stat.S_IFMT(mode)
                if filetype not in (0, stat.S_IFREG, stat.S_IFDIR):
                    fail('SECURITY_SPECIAL_ENTRY', 'security', f'symlink or special ZIP entry: {entry.filename!r}')
                if entry.flag_bits & 1:
                    fail('SECURITY_ENCRYPTED_ENTRY', 'security', 'encrypted ZIP members are unsupported')
                if entry.compress_type not in (zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED):
                    fail('SECURITY_COMPRESSION_METHOD', 'security', 'only stored and deflated ZIP entries are supported')
                if entry.file_size > self.limits.max_entry_bytes:
                    fail('SECURITY_ENTRY_SIZE', 'security', f'entry exceeds byte budget: {entry.filename!r}')
                self.declared_bytes += entry.file_size
                if self.declared_bytes > self.limits.max_uncompressed_bytes:
                    fail('SECURITY_UNCOMPRESSED_BUDGET', 'security', 'aggregate declared uncompressed byte budget exceeded')
                if entry.file_size > max(1, entry.compress_size) * self.limits.max_compression_ratio:
                    fail('SECURITY_COMPRESSION_RATIO', 'security', f'compression ratio exceeds budget: {entry.filename!r}')
            if self.runtime_authoritative:
                mods, nested = self.runtime_metadata(archive, by_name, artifact, origin)
            else:
                descriptors = [name for name in ('fabric.mod.json', 'META-INF/neoforge.mods.toml') if name in by_name]
                if len(descriptors) != 1:
                    fail('LOADER_AMBIGUOUS_METADATA' if descriptors else 'LOADER_UNKNOWN_METADATA', 'loader',
                         'exactly one Fabric or NeoForge descriptor is required')
                descriptor = descriptors[0]
                raw = self.read_entry(archive, by_name[descriptor], self.limits.max_metadata_bytes)
                if descriptor == 'fabric.mod.json':
                    artifact['ecosystem'] = 'fabric'
                    obj = strict_json(raw)
                    mods, nested = self.fabric(obj, origin)
                else:
                    artifact['ecosystem'] = 'neoforge'
                    obj = tomllib.loads(raw.decode('utf-8'))
                    mods, nested = self.neoforge(obj, origin, archive, by_name), []
                    if 'META-INF/jarjar/metadata.json' in by_name:
                        fail('LOADER_JARJAR_UNSUPPORTED', 'loader', 'NeoForge Jar-in-Jar selection is not implemented by this prototype')
            if len(self.mods) + len(mods) + len(self.bundled) > self.limits.max_mods:
                fail('SECURITY_MOD_LIMIT', 'security', 'logical mod budget exceeded')
            artifact['logical_ids'] = [mod['id'] for mod in mods]
            self.mods.extend(mods)
            for name in nested:
                if name not in by_name or by_name[name].is_dir():
                    self.issue('METADATA_NESTED_MISSING', 'metadata', f'declared nested JAR not found: {name}', origin=origin)
                    continue
                child_origin = origin + '!/' + name
                try:
                    if depth >= self.limits.max_nested_depth:
                        fail('SECURITY_NESTING_DEPTH', 'security', 'nested JAR depth budget exceeded')
                    nested_data = self.read_entry(archive, by_name[name], self.limits.max_archive_bytes)
                    self.scan_bytes(nested_data, child_origin, depth+1, origin)
                except (AdmissionError, zipfile.BadZipFile, ValueError, UnicodeError, RuntimeError, NotImplementedError, OSError, zlib.error, EOFError) as exc:
                    self.caught(exc, child_origin)

    def runtime_metadata(self, archive, entries, artifact, origin):
        """Inspect every declared nested candidate without choosing a loader winner."""
        mods, nested = [], []
        descriptors = [name for name in ('fabric.mod.json', 'META-INF/neoforge.mods.toml') if name in entries]
        if len(descriptors) != 1:
            self.issue('LOADER_AMBIGUOUS_METADATA' if descriptors else 'LOADER_UNKNOWN_METADATA', 'loader',
                       'Descriptor interpretation and candidate eligibility belong to the pinned runtime', origin=origin)
        artifact['ecosystem'] = ('fabric' if descriptors[0] == 'fabric.mod.json' else 'neoforge') if len(descriptors) == 1 else None
        jarjar = entries.get('META-INF/jarjar/metadata.json')
        if jarjar is not None:
            obj = strict_json(self.read_entry(archive, jarjar, self.limits.max_metadata_bytes))
            if not isinstance(obj, dict) or not isinstance(obj.get('jars'), list):
                fail('METADATA_INVALID_JARJAR', 'metadata', 'JarJar metadata requires a jars array')
            if len(obj['jars']) > self.limits.max_archives:
                fail('SECURITY_ARCHIVE_COUNT', 'security', 'JarJar declaration count exceeds archive budget')
            for entry in obj['jars']:
                if not isinstance(entry, dict):
                    fail('METADATA_INVALID_JARJAR', 'metadata', 'JarJar declaration must be an object')
                identifier, version = entry.get('identifier'), entry.get('version')
                if not isinstance(identifier, dict) or not isinstance(version, dict):
                    fail('METADATA_INVALID_JARJAR', 'metadata', 'JarJar identifier and version must be objects')
                for label, value in [('group', identifier.get('group')), ('artifact', identifier.get('artifact')), ('range', version.get('range')), ('artifactVersion', version.get('artifactVersion'))]:
                    _string(value, 'JarJar ' + label, 1024)
                name = _path(_string(entry.get('path'), 'JarJar path', 1024))
                if not name.endswith('.jar'):
                    fail('METADATA_INVALID_JARJAR', 'metadata', 'JarJar path must identify a .jar file')
                if name not in nested:
                    nested.append(name)
            self.issue('LOADER_JARJAR_UNSUPPORTED', 'loader',
                       'JarJar candidates are bounded-inspected; selection and version semantics are deferred to the pinned runtime', origin=origin)
        for descriptor in descriptors:
            # Parsing errors are never downgraded. An advisory from one descriptor
            # must not hide malformed JSON/TOML in a second descriptor.
            raw = self.read_entry(archive, entries[descriptor], self.limits.max_metadata_bytes)
            obj = strict_json(raw) if descriptor == 'fabric.mod.json' else tomllib.loads(raw.decode('utf-8'))
            if descriptor == 'fabric.mod.json':
                if not isinstance(obj, dict):
                    fail('METADATA_INVALID_FIELD', 'metadata', 'Fabric metadata must be an object')
                for name in self.fabric_nested(obj):
                    if name not in nested:
                        nested.append(name)
            try:
                if descriptor == 'fabric.mod.json':
                    parsed, _ = self.fabric(obj, origin)
                else:
                    parsed = self.neoforge(obj, origin, archive, entries)
                mods.extend(parsed)
            except AdmissionError as exc:
                self.caught(exc, origin)
        return mods, nested

    def fabric_nested(self, obj):
        nested = obj.get('jars', [])
        if not isinstance(nested, list) or len(nested) > self.limits.max_archives:
            fail('METADATA_INVALID_FIELD', 'metadata', 'jars must be a bounded list')
        names = []
        for entry in nested:
            if not isinstance(entry, dict):
                fail('METADATA_INVALID_FIELD', 'metadata', 'nested JAR declaration must be an object')
            name = _path(_string(entry.get('file'), 'jars.file', 1024))
            if not name.endswith('.jar'):
                fail('METADATA_INVALID_FIELD', 'metadata', 'nested JAR path must end in .jar')
            if name in names:
                if self.runtime_authoritative:
                    self.issue('DEPENDENCY_DUPLICATE_NESTED', 'dependency', 'Repeated nested candidate declaration is deferred to the pinned runtime')
                    continue
                fail('METADATA_DUPLICATE_NESTED', 'metadata', 'nested JAR is declared more than once')
            names.append(name)
        return names

    @staticmethod
    def read_entry(archive, entry, limit):
        if entry.file_size > limit:
            fail('SECURITY_METADATA_SIZE', 'security', f'requested entry exceeds {limit} bytes: {entry.filename}')
        with archive.open(entry) as stream:
            data = stream.read(limit+1)
        if len(data) > limit or len(data) != entry.file_size:
            fail('SECURITY_ENTRY_SIZE', 'security', 'actual entry size differs from bounded declared size')
        return data

    def fabric(self, obj, origin):
        if not isinstance(obj, dict) or not isinstance(obj.get('schemaVersion'), int) or isinstance(obj.get('schemaVersion'), bool):
            fail('METADATA_INVALID_FIELD', 'metadata', 'Fabric schemaVersion must be an integer')
        if obj.get('schemaVersion') != 1:
            fail('METADATA_SCHEMA_UNSUPPORTED', 'metadata', 'Fabric schemaVersion must be 1')
        mid, version = _id(obj.get('id')), _version(obj.get('version'))
        env = obj.get('environment', '*')
        if env not in ('*', 'client', 'server'):
            fail('ENVIRONMENT_INVALID', 'environment', f'invalid Fabric environment: {env!r}')
        aliases = obj.get('provides', [])
        if not isinstance(aliases, list) or len(aliases) > self.limits.max_dependencies:
            fail('METADATA_INVALID_FIELD', 'metadata', 'provides must be a bounded list')
        aliases = [_id(alias) for alias in aliases]
        if len(set([mid] + aliases)) != len([mid] + aliases):
            fail('DEPENDENCY_DUPLICATE_ID', 'dependency', 'mod id and provides aliases must be unique')
        deps = []
        for key, kind in [('depends', 'required'), ('recommends', 'recommended'), ('suggests', 'optional'), ('breaks', 'incompatible'), ('conflicts', 'discouraged')]:
            table = obj.get(key, {})
            if not isinstance(table, dict):
                fail('METADATA_INVALID_FIELD', 'metadata', f'{key} must be an object')
            for dep_id, requirement in table.items():
                deps.append({'id': _id(dep_id), 'predicate': _predicate(requirement, 'fabric'), 'kind': kind, 'environment': '*', 'ordering': 'NONE', 'dialect': 'fabric'})
                if len(deps) > self.limits.max_dependencies:
                    fail('SECURITY_DEPENDENCY_LIMIT', 'security', 'dependency count budget exceeded')
        names = self.fabric_nested(obj)
        return [self.mod(mid, version, env, origin, 'fabric', deps, aliases)], names

    def neoforge(self, obj, origin, archive, entries):
        if obj.get('modLoader') != 'javafml':
            fail('LOADER_UNSUPPORTED', 'loader', f'unsupported NeoForge language loader: {obj.get("modLoader")!r}')
        loader_range = _predicate(obj.get('loaderVersion'), 'maven')
        if not self.target.fml_version:
            self.issue('LOADER_VERSION_UNKNOWN', 'loader', 'NeoForge javafml loaderVersion requires --fml-version; NeoForge and FML versions are distinct', origin=origin)
        else:
            self.check_range('fml', self.target.fml_version, loader_range, 'maven', origin, None, 'loader')
        rows = obj.get('mods')
        if not isinstance(rows, list) or not rows or len(rows) > self.limits.max_mods:
            fail('METADATA_INVALID_FIELD', 'metadata', 'NeoForge mods must be a nonempty bounded array of tables')
        dep_tables = obj.get('dependencies', {})
        if not isinstance(dep_tables, dict):
            fail('METADATA_INVALID_FIELD', 'metadata', 'NeoForge dependencies must be a table')
        declared = {_id(row.get('modId')) for row in rows if isinstance(row, dict)}
        if set(dep_tables) - declared:
            fail('METADATA_UNKNOWN_DEPENDENCY_OWNER', 'metadata', 'NeoForge dependency table names an undeclared mod')
        mods = []
        for row in rows:
            if not isinstance(row, dict):
                fail('METADATA_INVALID_FIELD', 'metadata', 'each NeoForge mod must be a table')
            mid = _id(row.get('modId'))
            version = row.get('version')
            if version == '${file.jarVersion}':
                version = self.manifest_version(archive, entries)
            version = _version(version)
            raw_deps = dep_tables.get(mid, [])
            if not isinstance(raw_deps, list) or len(raw_deps) > self.limits.max_dependencies:
                fail('METADATA_INVALID_FIELD', 'metadata', 'NeoForge dependencies must be bounded arrays of tables')
            deps = []
            for dep in raw_deps:
                if not isinstance(dep, dict):
                    fail('METADATA_INVALID_FIELD', 'metadata', 'each NeoForge dependency must be a table')
                if 'mandatory' in dep:
                    fail('METADATA_LEGACY_DEPENDENCY', 'metadata', 'legacy mandatory dependency syntax is unsupported; use NeoForge type')
                kind = dep.get('type', 'required')
                if kind not in ('required', 'optional', 'incompatible', 'discouraged'):
                    fail('METADATA_INVALID_FIELD', 'metadata', f'unsupported dependency type: {kind!r}')
                side = dep.get('side', 'BOTH')
                if side not in ('BOTH', 'CLIENT', 'SERVER'):
                    fail('ENVIRONMENT_INVALID', 'environment', f'invalid dependency side: {side!r}')
                ordering = dep.get('ordering', 'NONE')
                if ordering not in ('NONE', 'BEFORE', 'AFTER'):
                    fail('METADATA_INVALID_FIELD', 'metadata', f'invalid ordering: {ordering!r}')
                deps.append({'id': _id(dep.get('modId')), 'predicate': _predicate(dep.get('versionRange'), 'maven'),
                             'kind': kind, 'environment': '*' if side == 'BOTH' else side.lower(), 'ordering': ordering, 'dialect': 'maven'})
            mods.append(self.mod(mid, version, '*', origin, 'neoforge', deps, []))
        return mods

    def manifest_version(self, archive, entries):
        entry = entries.get('META-INF/MANIFEST.MF')
        if not entry:
            fail('METADATA_UNRESOLVED_VERSION', 'metadata', '${file.jarVersion} requires Implementation-Version in the JAR manifest')
        content = self.read_entry(archive, entry, self.limits.max_metadata_bytes).decode('utf-8')
        lines = content.replace('\r\n', '\n').split('\n')
        unfolded = []
        for line in lines:
            if line.startswith(' '):
                if not unfolded:
                    fail('METADATA_INVALID_MANIFEST', 'metadata', 'manifest starts with an invalid continuation')
                unfolded[-1] += line[1:]
            else:
                unfolded.append(line)
        value = None
        for line in unfolded:
            if not line:
                break  # Only the main section defines the file version.
            key, sep, item = line.partition(': ')
            if not sep:
                fail('METADATA_INVALID_MANIFEST', 'metadata', 'invalid manifest main section')
            if key.lower() == 'implementation-version':
                if value is not None:
                    fail('METADATA_INVALID_MANIFEST', 'metadata', 'duplicate Implementation-Version')
                value = item
        return _version(value)

    def mod(self, mid, version, env, origin, ecosystem, deps, aliases):
        if any(value in RESERVED for value in [mid] + aliases):
            fail('LOADER_RESERVED_ID', 'loader', f'mod cannot impersonate a runtime id: {mid}')
        active = env in ('*', self.target.environment)
        if not active:
            self.issue('ENVIRONMENT_EXCLUDED', 'environment', f'{mid} is excluded from the {self.target.environment} metadata plan',
                       origin=origin, mod_id=mid, severity='info')
        return {'id': mid, 'version': version, 'environment': env, 'ecosystem': ecosystem, 'origin': origin,
                'active': active, 'bundled': False, 'provides': aliases, 'dependencies': deps}

    def check_range(self, dep_id, actual, predicate, dialect, origin, owner, category, severity='error'):
        try:
            okay = matches(actual, predicate, dialect)
        except UnsupportedVersion as exc:
            self.issue('DEPENDENCY_UNSUPPORTED_RANGE', 'dependency', str(exc), origin=origin, mod_id=owner, dependency=dep_id)
            return False
        if not okay:
            code = {'game_version': 'GAME_VERSION_MISMATCH', 'loader': 'LOADER_VERSION_MISMATCH',
                    'api': 'API_VERSION_MISMATCH'}.get(category, 'DEPENDENCY_VERSION_MISMATCH')
            self.issue(code, category, f'{dep_id} version {actual} does not satisfy {predicate!r}', origin=origin, mod_id=owner,
                       severity=severity, dependency=dep_id, actual=actual, required=predicate)
        return okay

    def resolve(self):
        providers, excluded = {}, set()
        for mod in self.bundled + self.mods:
            ids = [mod['id']] + mod.get('provides', [])
            if not mod['active']:
                excluded.update(ids)
                continue
            for mid in ids:
                if mid in providers:
                    category = 'api' if mod['bundled'] or providers[mid]['bundled'] else 'dependency'
                    self.issue('API_BUNDLED_CONFLICT' if category == 'api' else 'DEPENDENCY_DUPLICATE_ID', category,
                               f'multiple active providers for logical id {mid}; no candidate was silently selected',
                               origin=mod['origin'], mod_id=mid, other_origin=providers[mid]['origin'])
                else:
                    providers[mid] = mod
        builtin_versions = {'minecraft': self.target.minecraft, 'java': self.target.java_version,
                            'fabricloader': self.target.fabric_loader_version, 'neoforge': self.target.neoforge_version,
                            'fml': self.target.fml_version}
        active = [m for m in self.mods if m['active']]
        self.graph = {m['id']: set() for m in active}
        self.order_graph = {m['id']: set() for m in active}
        for mod in active:
            for dep in mod['dependencies']:
                if dep['environment'] not in ('*', self.target.environment):
                    continue
                mid, kind = dep['id'], dep['kind']
                required = kind == 'required'
                negative = kind in ('incompatible', 'discouraged')
                provider = providers.get(mid)
                actual = builtin_versions.get(mid) if mid in RESERVED else provider['version'] if provider else None
                category = ('game_version' if mid == 'minecraft' else 'loader' if mid in RESERVED else 'api' if provider and provider['bundled'] else 'dependency')
                if actual is None:
                    if required or kind == 'recommended':
                        code, cat = ('LOADER_VERSION_UNKNOWN', 'loader') if mid in RESERVED else ('ENVIRONMENT_DEPENDENCY', 'environment') if mid in excluded else ('DEPENDENCY_MISSING', 'dependency')
                        self.issue(code, cat, f'{mod["id"]} requires an available {mid} satisfying {dep["predicate"]!r}',
                                   origin=mod['origin'], mod_id=mod['id'], dependency=mid, severity='error' if required else 'warning')
                    continue
                if negative:
                    try:
                        conflict = matches(actual, dep['predicate'], dep['dialect'])
                    except UnsupportedVersion as exc:
                        self.issue('DEPENDENCY_UNSUPPORTED_RANGE', 'dependency', str(exc), origin=mod['origin'], mod_id=mod['id'])
                        continue
                    if conflict:
                        self.issue('API_INCOMPATIBLE' if category == 'api' else 'DEPENDENCY_INCOMPATIBLE', category,
                                   f'{mod["id"]} declares {mid} {actual} {kind}', origin=mod['origin'], mod_id=mod['id'],
                                   dependency=mid, severity='error' if kind == 'incompatible' else 'warning')
                    continue
                compatible = self.check_range(mid, actual, dep['predicate'], dep['dialect'], mod['origin'], mod['id'], category,
                                              'warning' if kind in ('recommended', 'optional') else 'error')
                # Optional installed NeoForge dependencies still constrain their versions.
                if kind == 'optional' and mod['ecosystem'] == 'neoforge' and not compatible and not self.runtime_authoritative:
                    self.issues[-1]['severity'] = 'error'
                if provider and not provider['bundled'] and provider['id'] != mod['id']:
                    if required:
                        self.graph[mod['id']].add(provider['id'])
                    if dep['ordering'] == 'AFTER':
                        self.order_graph[mod['id']].add(provider['id'])
                    elif dep['ordering'] == 'BEFORE':
                        self.order_graph[provider['id']].add(mod['id'])
                elif provider and provider['id'] == mod['id'] and dep['ordering'] != 'NONE':
                    self.issue('DEPENDENCY_ORDER_CYCLE', 'dependency', f'{mod["id"]} has a self ordering constraint', origin=mod['origin'], mod_id=mod['id'])
        for group in strongly_connected(self.order_graph):
            if len(group) > 1:
                self.issue('DEPENDENCY_ORDER_CYCLE', 'dependency', 'NeoForge explicit ordering constraints form a cycle', logical_ids=group)
        groups = strongly_connected(self.graph)
        for group in groups:
            if len(group) > 1:
                self.issue('DEPENDENCY_CYCLE_GROUP', 'dependency', 'Mutual metadata dependencies are resolved as a group; this does not establish runtime initialization order', severity='info', logical_ids=group)
        return groups

    def report(self):
        groups = self.resolve()
        errors = [i for i in self.issues if i['severity'] == 'error']
        report = {'schema_version': 1, 'tool': {'name': 'mod-compat-admission', 'version': '0.1.0'},
                'admission': 'rejected' if errors else 'metadata_pass', 'runtime_compatibility': 'unverified',
                'scope': 'Bounded read-only metadata inspection only. No extraction, classloading, transformation, registry initialization, API implementation verification, or mod execution.',
                'target': asdict(self.target), 'limits': asdict(self.limits), 'bundled_inventory': self.inventory_source,
                'bundled_apis': self.bundled, 'artifacts': self.artifacts, 'mods': self.mods,
                'dependency_groups': groups,
                'ordering_constraints': {k: sorted(v) for k, v in sorted(self.order_graph.items())},
                'issues': self.issues, 'summary': {'errors': len(errors), 'warnings': sum(i['severity'] == 'warning' for i in self.issues),
                'artifacts': len(self.artifacts), 'active_mods': sum(m['active'] for m in self.mods),
                'excluded_mods': sum(not m['active'] for m in self.mods), 'categories': sorted({i['category'] for i in errors})},
                'resource_usage': {'archive_bytes': self.archive_bytes, 'zip_entries': self.entry_count, 'declared_uncompressed_bytes': self.declared_bytes}}

        report['java_policy'] = {
            'minimum_major': MINIMUM_JAVA_MAJOR,
            'declared_target_version': self.target.java_version,
            'actual_jvm_observation': 'not_performed_by_preflight',
            'applies_to_future_target_adapters': True,
            'higher_game_requirements_may_raise_minimum': True,
        }
        report['mode'] = 'runtime_authoritative' if self.runtime_authoritative else 'strict_diagnostic'
        if self.runtime_authoritative:
            report['admission'] = 'rejected' if errors else 'runtime_deferred'
            report['candidate_selection'] = 'deferred'
            report['dependency_resolution'] = 'deferred'
            report['runtime_authority'] = {
                'name': 'pinned_neoforge_fml_and_sinytra_connector',
                'components': ['NeoForge FML', 'Sinytra Connector'],
                'pin_verification': 'external_runtime_responsibility',
                'declared_neoforge_version': self.target.neoforge_version,
                'declared_fml_version': self.target.fml_version,
            }
            report['candidate_graph_authoritative'] = False
            report['logical_metadata_coverage'] = 'best_effort_not_runtime_inventory'
            report['dependency_groups'] = None
            report['ordering_constraints'] = None
            report['summary']['candidate_mods'] = len(self.mods)
            report['summary']['active_mods'] = None
            report['summary']['excluded_mods'] = None
            report['summary']['deferred'] = sum(issue['severity'] == 'deferred' for issue in self.issues)
            for mod in report['mods'] + report['bundled_apis']:
                mod['diagnostic_environment_match'] = mod.pop('active')
                mod['selection'] = 'deferred'
            report['scope'] += ' Candidate selection, version/dependency resolution, sidedness and ordering are owned by the pinned NeoForge FML/Connector runtime; this report selects no candidates.'
        return report


def strongly_connected(graph):
    """Iterative Kosaraju, avoiding recursion on hostile dependency chains."""
    visited, finish = set(), []
    for root in sorted(graph):
        if root in visited:
            continue
        stack = [(root, False)]
        while stack:
            node, expanded = stack.pop()
            if expanded:
                finish.append(node)
            elif node not in visited:
                visited.add(node)
                stack.append((node, True))
                stack.extend((child, False) for child in sorted(graph.get(node, ()), reverse=True) if child not in visited)
    reverse = {node: set() for node in graph}
    for node, children in graph.items():
        for child in children:
            reverse.setdefault(child, set()).add(node)
    visited, groups = set(), []
    for root in reversed(finish):
        if root in visited:
            continue
        stack, group = [root], []
        while stack:
            node = stack.pop()
            if node in visited:
                continue
            visited.add(node); group.append(node)
            stack.extend(sorted(reverse.get(node, ()), reverse=True))
        groups.append(sorted(group))
    # Dependencies come first, but these are metadata groups, not runtime order.
    return list(reversed(groups))


def plan(paths, *, target=None, limits=None, bundled_inventory=None, runtime_authoritative=False):
    """Read supplied JARs and return a JSON-serializable report, never executing them."""
    planner = Planner(target or Target(), limits or Limits(), runtime_authoritative)
    if planner.target.minecraft != SUPPORTED_MINECRAFT:
        planner.issue('GAME_VERSION_UNSUPPORTED', 'game_version', f'prototype supports only Minecraft {SUPPORTED_MINECRAFT}')
    if planner.target.environment not in ('client', 'server'):
        planner.issue('ENVIRONMENT_INVALID', 'environment', 'target environment must be client or server')
    # This is target policy, not a loader dependency verdict or a JVM probe.
    # Keep it blocking in both modes, including future adapter implementations.
    try:
        declared_java = Version(planner.target.java_version)
        if declared_java < Version(str(MINIMUM_JAVA_MAJOR)):
            raise UnsupportedVersion(f'all target adapters require declared Java {MINIMUM_JAVA_MAJOR} or newer; game requirements may raise this minimum')
    except UnsupportedVersion as exc:
        planner.issue('TARGET_INVALID_VERSION', 'environment', f'java_version: {exc}', minimum_java_major=MINIMUM_JAVA_MAJOR)
    if runtime_authoritative:
        for field in ('fabric_loader_version', 'neoforge_version', 'fml_version'):
            value = getattr(planner.target, field)
            if value is None:
                continue
            try:
                Version(value)
            except UnsupportedVersion as exc:
                planner.issue('TARGET_INVALID_VERSION', 'environment', f'{field}: {exc}')
    if bundled_inventory is not None:
        planner.inventory(bundled_inventory)
    else:
        planner.issue('API_INVENTORY_UNVERIFIED', 'api', 'No bundled API inventory was provided; no bundled API IDs or versions have been assumed', severity='warning')
    if not paths:
        planner.issue('METADATA_NO_INPUTS', 'metadata', 'at least one input JAR is required')
    for index, path in enumerate(paths):
        if index >= planner.limits.max_archives:
            planner.issue('SECURITY_ARCHIVE_COUNT', 'security', 'top-level archive count budget exceeded')
            break
        planner.scan_file(path)
    return planner.report()
