"""Failure-only evidence; never changes a build gate or accepts changed output."""
import hashlib
import json
from pathlib import Path
import re
import stat
import struct
import time
import zipfile
import zlib

MAX_FILE = 128 * 1024 * 1024
MAX_ENTRIES = 30000
MAX_EXPANDED = 256 * 1024 * 1024
MAX_HASH_WORK = 512 * 1024 * 1024
MAX_REPORT = 32 * 1024
KNOWN_PARTIAL = {
    'net/minecraft/client/Minecraft.class': '8ff7643f44f4dca5d2b3428729a52de15c39bfabad9c9201c9f401134496dd66',
    'META-INF/jarjar/mixinextras-neoforge-0.5.0.jar': '9c617719248f8b89847348fc7ea5e705739c147ae5e172551264d225bc9f2507',
    'META-INF/jarjar/net.neoforged.neoforge-coremods-21.1.219.jar': 'aff9b8e71473979ef1c65f2e22de785c48b30bd3f0dcf46f7d0862baa1434256',
}


class Limited(Exception):
    pass


def _json(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False)


def _check(budget):
    if time.monotonic() >= budget[0]:
        raise Limited('DEADLINE')


def _hash(stream, budget, limit):
    digest, count = hashlib.sha256(), 0
    while True:
        _check(budget)
        block = stream.read(min(65536, limit - count + 1))
        if not block:
            return count, digest.hexdigest()
        count += len(block)
        budget[1] -= len(block)
        if count > limit or budget[1] < 0:
            raise Limited('HASH_WORK_LIMIT')
        digest.update(block)


def _safe(root, path):
    path = Path(path)
    canonical = path.resolve()
    if not path.is_relative_to(root) or canonical != path or not canonical.is_relative_to(root):
        raise Limited('UNSAFE_PATH')
    return canonical


def _directory_check(stream, budget):
    """Bound real central-directory rows before ZipFile allocates ZipInfo objects."""
    stream.seek(0, 2)
    size = stream.tell()
    stream.seek(max(0, size - 65557))
    tail = stream.read()
    offset = tail.rfind(b'PK\x05\x06')
    if offset < 0 or len(tail) - offset < 22:
        raise zipfile.BadZipFile('end record')
    _, disk, directory_disk, disk_count, count, length, start, comment = struct.unpack('<4s4H2LH', tail[offset:offset + 22])
    if disk or directory_disk or disk_count != count or count == 65535 or start == 0xffffffff:
        raise Limited('UNSUPPORTED_ZIP')
    if count > MAX_ENTRIES or length > 16 * 1024 * 1024:
        raise Limited('ZIP_ENTRY_LIMIT')
    if offset + 22 + comment != len(tail):
        raise zipfile.BadZipFile('directory bounds')
    # ZipFile relocates the directory for concatenated/prefixed archives. Only
    # accept the ordinary contiguous layout that the bounded pre-scan inspected.
    if start + length != size - len(tail) + offset:
        raise Limited('UNSUPPORTED_ZIP_LAYOUT')
    position, actual = start, 0
    while position < start + length:
        _check(budget)
        stream.seek(position)
        header = stream.read(46)
        if len(header) != 46 or header[:4] != b'PK\x01\x02':
            raise zipfile.BadZipFile('directory record')
        position += 46 + sum(struct.unpack('<3H', header[28:34]))
        actual += 1
        if actual > MAX_ENTRIES:
            raise Limited('ZIP_ENTRY_LIMIT')
    if position != start + length or actual != count:
        raise zipfile.BadZipFile('directory count')


def _digest(rows, budget):
    _check(budget)
    digest = hashlib.sha256()
    for row in rows:
        digest.update((_json(row) + '\n').encode())
    _check(budget)
    return digest.hexdigest()


def _name(name):
    return name if len(name) <= 256 else name[:256] + '[name-sha256:' + hashlib.sha256(name.encode()).hexdigest() + ']'


def _zip(path, budget, known, sample_limit=8):
    result = {'complete': False, 'samples': [], 'fullHistoricalEntryBaseline': False,
              'metadataOnlyDifferenceConclusion': 'UNAVAILABLE'}
    with path.open('rb') as stream:
        _directory_check(stream, budget)
        with zipfile.ZipFile(stream) as archive:
            entries = archive.infolist()
            # Ordinary generated JARs use stored or deflated members. Other
            # ZipExtFile codecs may expand beyond the requested read bound.
            if any(entry.compress_type not in (zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED) for entry in entries):
                raise Limited('UNSUPPORTED_ZIP_COMPRESSION')
            result['entryCount'] = len(entries)
            result['declaredExpandedBytes'] = sum(entry.file_size for entry in entries)
            if result['declaredExpandedBytes'] > MAX_EXPANDED:
                raise Limited('ZIP_EXPANDED_LIMIT')
            payloads, metadata, names, partial = [], [], set(), {}
            expanded = duplicates = 0
            for entry in entries:
                _check(budget)
                duplicates += entry.filename in names
                names.add(entry.filename)
                with archive.open(entry) as source:
                    count, digest = _hash(source, budget, MAX_EXPANDED - expanded)
                expanded += count
                payloads.append((entry.filename, digest))
                row = {'name': entry.filename, 'bytes': count, 'compressedBytes': entry.compress_size,
                       'payloadSha256': digest, 'crc32': entry.CRC, 'compression': entry.compress_type,
                       'dateTime': list(entry.date_time), 'flags': entry.flag_bits, 'externalAttributes': entry.external_attr,
                       'internalAttributes': entry.internal_attr, 'createSystem': entry.create_system,
                       'createVersion': entry.create_version, 'extractVersion': entry.extract_version,
                       'extraSha256': hashlib.sha256(entry.extra).hexdigest(),
                       'commentSha256': hashlib.sha256(entry.comment).hexdigest()}
                metadata.append(_json({key: value for key, value in row.items() if key != 'payloadSha256'}))
                if len(result['samples']) < min(sample_limit, 64):
                    result['samples'].append({**row, 'name': _name(entry.filename)})
                if known and entry.filename in KNOWN_PARTIAL:
                    partial.setdefault(entry.filename, []).append(digest)
            _check(budget)
            result.update(complete=True, expandedBytes=expanded, duplicateNameCount=duplicates,
                          payloadAggregateSha256=_digest(sorted(payloads), budget), entryOrderSha256=_digest(payloads, budget),
                          zipMetadataSha256=_digest([hashlib.sha256(archive.comment).hexdigest(), *sorted(metadata)], budget))
            _check(budget)
            if known:
                result['knownPartialPayloadBaseline'] = [
                    {'name': name, 'expectedSha256': expected, 'actualSha256': partial.get(name, [None])[0],
                     'occurrences': len(partial.get(name, [])),
                     'status': 'MISSING' if name not in partial else
                     'MATCH' if partial[name] == [expected] else 'MISMATCH_OR_DUPLICATE'}
                    for name, expected in KNOWN_PARTIAL.items()]
    return result


def _manifest(root, profile, budget):
    path = profile / 'build/tmp/createMinecraftArtifacts/nfrt_artifact_manifest.properties'
    result = {'path': str(path.relative_to(root)), 'exists': None, 'bytes': None, 'sha256': None,
              'parsedRecordCount': None, 'resolvedInputIdentities': 'UNAVAILABLE', 'invocationArgv': 'UNAVAILABLE'}
    try:
        _safe(root, path)
        info = path.stat()
        result.update(exists=True, bytes=info.st_size)
        if not stat.S_ISREG(info.st_mode):
            raise Limited('NOT_REGULAR_FILE')
        if info.st_size > 1024 * 1024:
            raise Limited('MANIFEST_SIZE_LIMIT')
        with path.open('rb') as source:
            result['bytes'], result['sha256'] = _hash(source, budget, 1024 * 1024)
            source.seek(0)
            count = 0
            for raw in source:
                _check(budget)
                line = raw.decode('ascii').strip()
                if not line or line.startswith(('#', '!')):
                    continue
                if ((len(line) - len(line.rstrip('\\'))) % 2
                        or not re.fullmatch(r'(?:\\.|[^\\=\s])+\s*=.*', line)):
                    raise Limited('UNSUPPORTED_PROPERTIES_FORMAT')
                count += 1
                if count > 160:
                    raise Limited('MANIFEST_RECORD_LIMIT')
            result.update(parsedRecordCount=count, status='RAW_IDENTITY_ONLY')
    except FileNotFoundError:
        result.update(exists=False, status='MISSING')
    except (OSError, UnicodeError, Limited) as error:
        result.update(complete=False, status=str(error) if isinstance(error, Limited) else type(error).__name__)
    return result


def emit(consumer, deadline):
    """Print one bounded JSON marker after the owner's failed export and cleanup."""
    budget = [min(deadline, time.monotonic() + 20), MAX_HASH_WORK]
    root = Path(consumer).absolute()
    profile = root / 'work/api1/run/api1-unified-client-build'
    report = {'schema': 1, 'diagnosticOnly': True, 'complete': True, 'outputs': [],
              'fullHistoricalEntryBaseline': False, 'metadataOnlyDifferenceConclusion': 'UNAVAILABLE'}
    try:
        lock_path = _safe(root, root / 'work/api1/ci/runtime-restore/input-lock.json')
        lock_info = lock_path.stat()
        if not stat.S_ISREG(lock_info.st_mode):
            raise Limited('INVALID_LOCK')
        if lock_info.st_size > 8 * 1024 * 1024:
            raise Limited('LOCK_SIZE_LIMIT')
        with lock_path.open('rb') as source:
            raw = source.read(8 * 1024 * 1024 + 1)
        if len(raw) > 8 * 1024 * 1024:
            raise Limited('LOCK_SIZE_LIMIT')
        lock = json.loads(raw)
        pins = [*lock['generatedDevelopmentOutputs'], lock['additionalCleanOutput']]
        if len(pins) != 3:
            raise Limited('INVALID_LOCK')
        paths = []
        for pin in pins:
            relative = Path(pin['path'])
            if (relative.is_absolute() or '..' in relative.parts or relative.parts[:1] != ('build',)
                    or len(_json(str(relative)).encode()) > 2048 or not isinstance(pin['bytes'], int)
                    or not 0 <= pin['bytes'] < 2 ** 63 or not re.fullmatch('[0-9a-f]{64}', pin['sha256'])):
                raise Limited('INVALID_LOCK')
            path = profile / relative
            canonical = str(path.resolve())
            if len(_json(canonical).encode()) > 4096:
                raise Limited('PATH_SIZE_LIMIT')
            row = {'path': str(relative), 'canonicalPath': canonical, 'exists': None,
                   'regularFile': None, 'expectedBytes': pin['bytes'], 'expectedSha256': pin['sha256'],
                   'actualBytes': None, 'actualSha256': None, 'statuses': []}
            report['outputs'].append(row)
            try:
                _safe(root, path)
                info = path.stat()
                row.update(exists=True, regularFile=stat.S_ISREG(info.st_mode), actualBytes=info.st_size)
                if not row['regularFile']:
                    row['statuses'].append('NOT_REGULAR_FILE')
                elif info.st_size != pin['bytes']:
                    row['statuses'].append('SIZE_MISMATCH')
            except FileNotFoundError:
                row.update(exists=False, regularFile=False)
                row['statuses'].append('MISSING')
            except (OSError, Limited) as error:
                row['statuses'].append(str(error) if isinstance(error, Limited) else 'IO_ERROR')
            paths.append(path)
        # Finish critical whole-file identities before spending time on ZIP detail.
        for path, row in zip(paths, report['outputs']):
            if not row['regularFile']:
                continue
            try:
                if row['actualBytes'] > MAX_FILE:
                    raise Limited('FILE_SIZE_LIMIT')
                with path.open('rb') as source:
                    count, digest = _hash(source, budget, MAX_FILE)
                row['actualBytes'], row['actualSha256'] = count, digest
                if count != row['expectedBytes'] and 'SIZE_MISMATCH' not in row['statuses']:
                    row['statuses'].append('SIZE_MISMATCH')
                if digest != row['expectedSha256']:
                    row['statuses'].append('HASH_MISMATCH')
            except Limited as error:
                row['statuses'].append(str(error))
                report['complete'] = False
            except OSError:
                row['statuses'].append('IO_ERROR')
                report['complete'] = False
        report['nfrtManifest'] = _manifest(root, profile, budget)
        if report['nfrtManifest'].get('complete') is False:
            report['complete'] = False
        for path, row in zip(paths, report['outputs']):
            if row['actualSha256'] is None:
                continue
            try:
                row['zip'] = _zip(path, budget, path.name == 'neoforge-21.1.219.jar')
                if row['zip']['duplicateNameCount']:
                    row['statuses'].append('DUPLICATE_ZIP_ENTRIES')
                if not row['statuses']:
                    row['statuses'].append('IDENTITY_MATCH')
            except Limited as error:
                row['statuses'].append(str(error))
                report['complete'] = False
            except (zipfile.BadZipFile, EOFError, RuntimeError, NotImplementedError, zlib.error, UnicodeError):
                row['statuses'].append('CORRUPT_ZIP')
            except OSError:
                row['statuses'].append('IO_ERROR')
                report['complete'] = False
    except (OSError, ValueError, KeyError, TypeError, Limited) as error:
        report.update(complete=False, error=str(error) if isinstance(error, Limited) else type(error).__name__)
    if any('UNSAFE_PATH' in row['statuses'] or 'IO_ERROR' in row['statuses'] for row in report['outputs']):
        report['complete'] = False
    if len(_json(report).encode()) > MAX_REPORT - 64:
        for row in report['outputs']:
            if 'zip' in row:
                row['zip'].pop('samples', None)
        report.update(complete=False, optionalDetailsDropped=True)
    if len(_json(report).encode()) > MAX_REPORT - 64:
        report.pop('nfrtManifest', None)
        for row in report['outputs']:
            row.pop('zip', None)
    if len(_json(report).encode()) > MAX_REPORT - 64:
        for row in report['outputs']:
            row.pop('canonicalPath', None)
    marker = 'GENERATED_OUTPUT_DIAGNOSTIC ' + _json(report)
    assert len((marker + '\n').encode()) <= MAX_REPORT
    print(marker, flush=True)
    return report
