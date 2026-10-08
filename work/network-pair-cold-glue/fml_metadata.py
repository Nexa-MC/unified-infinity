#!/usr/bin/env python3
"""Portable, source-only FML metadata overlay and strict fresh-output checks.

The ce4b identity is a reviewed historical artifact-equivalence reference, not a
recomputed identity of this consumer's absolute paths. Fresh source, command and
output receipts are independently bound. No historical build receipt admits work.
"""
from __future__ import annotations
import hashlib
import json
from pathlib import Path
import re
import struct
import zipfile

HERE = Path(__file__).resolve().parent
SUPPORT_MANIFEST_SHA = '6293d847593780d7b4fa6022aaab033d7b8f6ea7795ab630789d22cddeda7a39'
BASE_IDENTITY = '54e5f302c1bad0de54a6845a50b128d6a2aa9f4fb9d44ec14c84c754d7fb21f6'
CANDIDATE_IDENTITY = 'ce4b907075e2892f39ee13ed75d19afc193ad602d9ecc8cb5eca03cea4181844'
BASE_FML_SHA = '0281b9389e92c7f560fd1921f86ece8203e23ff7ebbbd2240f10c911e6546c26'
FIXED_FML_SHA = '4d697ba080277ed270ddd427102e03da4d6cd58b2b9ed584db010b59f037c2e9'
CACHE = 'META-INF/org/apache/logging/log4j/core/config/plugins/Log4j2Plugins.dat'
CACHE_SHA = 'd0f0b5582b430acd1be817a94989f6eda13d359d6980dcdc1bb568408bcb76e6'
AREA = 'work/fml-logging-metadata-fix-20261007-v3'
PROJECT = 'work/api1/source-workspace/fml-unified-logging-fix-v3'
SUPPORT = 'work/emi-render-integration/portable-build-support'
EXPECTED_PLUGIN = [{'category': 'converter', 'key': 'highlightforge',
                    'className': 'net.neoforged.fml.loading.log4j.ForgeHighlight',
                    'pluginName': 'highlightForge', 'printable': False, 'defer': False}]


def require(value, message):
    if not value:
        raise ValueError(message)


def sha(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def canonical(path):
    path = Path(path).absolute()
    require(path.resolve() == path and not any(p.is_symlink() for p in (path, *path.parents)),
            'Noncanonical or symlink path: ' + str(path))
    return path


def pin(path):
    path = canonical(path)
    require(path.is_file(), 'Expected regular file: ' + str(path))
    return {'path': str(path), 'sha256': sha(path), 'bytes': path.stat().st_size}


def save(path, value):
    path = canonical(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('x') as stream:
        json.dump(value, stream, indent=2)
        stream.write('\n')
    return pin(path)


def sources(path):
    path = canonical(path)
    return sorted(p for p in path.rglob('*') if p.is_file()
                  and not set(p.relative_to(path).parts) & {'build', '.gradle', '__pycache__'})


def verify_tree(path, rows):
    observed = []
    for p in sources(path):
        row = pin(p)
        row['path'] = p.relative_to(path).as_posix()
        observed.append(row)
    require(observed == rows, 'Source inventory changed: ' + str(path))
    return [pin(path / row['path']) for row in rows]


def support_manifest(path):
    require(sha(path / 'manifest.json') == SUPPORT_MANIFEST_SHA, 'Build support manifest changed')
    data = json.loads((path / 'manifest.json').read_text())
    require({p.relative_to(path).as_posix() for p in sources(path)} ==
            {'manifest.json', *[r['path'] for r in data['files']]}, 'Unexpected build support input')
    for row in data['files']:
        current = pin(path / row['path'])
        require(current['sha256'] == row['sha256'] and current['bytes'] == row['bytes'],
                'Build support bytes changed: ' + row['path'])
    return data


def prepare(consumer):
    root = canonical(consumer)
    bundled = HERE / 'build-support'
    manifest = support_manifest(bundled)
    inventory = json.loads((bundled / 'fml-source-inventory.json').read_text())
    original = root / 'work/api1/source-workspace/fml-unified'
    shared = root / 'work/api1/source-workspace/admission-bootstrap'
    verify_tree(original, inventory['originalSources'])
    verify_tree(shared, inventory['sharedSources'])
    destinations = (root / SUPPORT, root / PROJECT, root / AREA)
    require(all(not path.exists() for path in destinations), 'Refusing existing FML source preparation')
    payloads = [(root / SUPPORT / row['path'], (bundled / row['path']).read_bytes()) for row in manifest['files']]
    payloads.append((root / SUPPORT / 'manifest.json', (bundled / 'manifest.json').read_bytes()))
    old = {r['path']: r for r in inventory['originalSources']}
    for row in inventory['fixedSources']:
        relative = row['path']
        source = original / relative if old.get(relative, {}).get('sha256') == row['sha256'] else bundled / 'fml' / relative
        require(sha(source) == row['sha256'] and source.stat().st_size == row['bytes'], 'FML source overlay changed')
        payloads.append((root / PROJECT / relative, source.read_bytes()))
    for destination, data in payloads:
        canonical(destination).parent.mkdir(parents=True, exist_ok=True)
        with destination.open('xb') as stream:
            stream.write(data)
    result = verify_sources(root)
    result.update(schema=1, status='FML_SOURCE_OVERLAY_PREPARED_NO_JVM', jvmStarted=False, gameLaunched=False)
    save(root / AREA / 'source-preparation.json', result)
    return result


def verify_sources(consumer):
    root = canonical(consumer)
    support = root / SUPPORT
    support_manifest(support)
    inventory = json.loads((support / 'fml-source-inventory.json').read_text())
    original = root / 'work/api1/source-workspace/fml-unified'
    project = root / PROJECT
    shared = root / 'work/api1/source-workspace/admission-bootstrap'
    rows = {key: verify_tree(path, inventory[key]) for key, path in
            [('originalSources', original), ('fixedSources', project), ('sharedSources', shared)]}
    java = sorted((project / 'src/main/java').rglob('*.java'))
    shared_java = sorted((shared / 'src/main/java').rglob('*.java'))
    require(len(java) == 184 and len(shared_java) == 11, 'Full 195-source FML compilation required')
    upstream = json.loads((project / 'provenance/upstream-source.json').read_text())
    require(len([r for r in upstream['files'] if r['path'].endswith('.java')]) == 179,
            'Incomplete upstream FML source provenance')
    plugins = [p for p in java + shared_java if re.search(r'^\s*@Plugin\(', p.read_text(), re.M)]
    require(plugins == [project / 'src/main/java/net/neoforged/fml/loading/log4j/ForgeHighlight.java'],
            'Unexpected Log4j plugin source')
    reference = json.loads((support / 'accepted-candidate-reference.json').read_text())
    identity = reference.pop('identity_sha256')
    require(hashlib.sha256(json.dumps(reference, sort_keys=True, separators=(',', ':')).encode()).hexdigest() ==
            identity == CANDIDATE_IDENTITY and reference['historicalCandidateIdentity'] == BASE_IDENTITY,
            'Accepted artifact-equivalence reference changed')
    return {'supportManifest': pin(support / 'manifest.json'), 'sources': rows,
            'baseSourceIdentity': BASE_IDENTITY, 'candidateIdentity': CANDIDATE_IDENTITY,
            'candidateIdentityKind': 'reviewed-artifact-equivalence-reference',
            'acceptedCandidateReference': pin(support / 'accepted-candidate-reference.json'),
            'fullJavaSourceCount': len(java) + len(shared_java)}


def verify_dependencies(root):
    root = canonical(root)
    api = root / 'work/api1'
    project = root / PROJECT
    lock = json.loads((project / 'provenance/compile-classpath-lock.json').read_text())
    require(len(lock['artifacts']) == 116, 'FML dependency closure changed')
    rows = []
    for row in lock['artifacts']:
        path = canonical(api / row['path'])
        require(path.is_relative_to(api) and sha(path) == row['sha256'], 'FML dependency pin changed')
        require(not path.name.startswith('loader-4.0.42'), 'Upstream FML classes cannot mask source compilation')
        rows.append(pin(path))
    inventory = json.loads((root / SUPPORT / 'fml-source-inventory.json').read_text())
    official_row = inventory['officialFml']
    official = api / official_row['path']
    require(sha(official) == official_row['sha256'] and official.stat().st_size == official_row['bytes'],
            'Official FML registration reference changed')
    with zipfile.ZipFile(official) as archive:
        raw = archive.read(CACHE)
    require(len(raw) == 101 and hashlib.sha256(raw).hexdigest() == CACHE_SHA and
            decode_cache(raw) == EXPECTED_PLUGIN, 'Official Log4j registration differs')
    return rows, pin(official)


def decode_cache(data):
    offset = 0
    def take(size):
        nonlocal offset
        require(offset + size <= len(data), 'Truncated Log4j cache')
        value = data[offset:offset + size]
        offset += size
        return value
    def number():
        return struct.unpack('>i', take(4))[0]
    def utf():
        return take(struct.unpack('>H', take(2))[0]).decode('ascii')
    require(number() == 1, 'Expected one Log4j cache category')
    category = utf()
    require(number() == 1, 'Expected one Log4j plugin')
    row = {'category': category, 'key': utf(), 'className': utf(), 'pluginName': utf()}
    flags = take(2)
    require(all(flag in (0, 1) for flag in flags) and offset == len(data), 'Invalid Log4j cache layout')
    row.update(printable=bool(flags[0]), defer=bool(flags[1]))
    return [row]


def archive_entries(path):
    with zipfile.ZipFile(path) as archive:
        names = archive.namelist()
        require(len(names) == len(set(names)), 'Duplicate archive entry')
        require(not any(n.startswith('/') or '..' in Path(n).parts for n in names), 'Unsafe archive entry')
        return {n: {'sha256': hashlib.sha256(archive.read(n)).hexdigest(),
                    'bytes': archive.getinfo(n).file_size, 'mode': archive.getinfo(n).external_attr >> 16,
                    'timestamp': list(archive.getinfo(n).date_time)} for n in names}


def compare_archives(old_path, new_path, official_path):
    old, new = archive_entries(old_path), archive_entries(new_path)
    removed = sorted(set(old) - set(new))
    added = sorted(set(new) - set(old))
    changed = sorted(n for n in set(old) & set(new) if old[n] != new[n])
    classes = sorted(n for n in old if n.endswith('.class'))
    require(not removed and not changed and [n for n in added if not n.endswith('/')] == [CACHE],
            'Only the generated plugin cache may extend the historical FML archive')
    require(all(CACHE.startswith(n) for n in added if n.endswith('/')), 'Unexpected added archive directory')
    require(len(classes) == 309 and classes == sorted(n for n in new if n.endswith('.class')),
            'FML must preserve all 309 compiled class payloads')
    with zipfile.ZipFile(new_path) as archive, zipfile.ZipFile(official_path) as official:
        raw = archive.read(CACHE)
        require(len(raw) == 101 and raw == official.read(CACHE) and
                hashlib.sha256(raw).hexdigest() == CACHE_SHA and decode_cache(raw) == EXPECTED_PLUGIN,
                'Fresh annotation-processor cache differs from reviewed registration')
        require(archive.read('META-INF/unified-admission/installation.json') == b'{"schema":1,"approved":false}\n',
                'Unapproved installation policy changed')
    return {'schema': 1, 'status': 'PASS_ONLY_PLUGIN_CACHE_ADDED', 'historicalFml': pin(old_path),
            'newFml': pin(new_path), 'oldEntryCount': len(old), 'newEntryCount': len(new),
            'identicalClassCount': len(classes), 'changedEntries': changed, 'removedEntries': removed,
            'addedEntries': added, 'existingZipMetadataChanges': [], 'cacheBytes': len(raw),
            'generatedCacheSha256': CACHE_SHA, 'decodedGeneratedCache': decode_cache(raw),
            'cacheMatchesOfficialBytes': True, 'oldEntries': old, 'newEntries': new}
