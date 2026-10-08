#!/usr/bin/env python3
"""Reconstruct the pinned render candidate's source inputs in a fresh consumer root.

Pure Python only: this module never starts Java/Gradle, downloads a dependency,
executes copied helpers, or treats historical build receipts as fresh evidence.
"""
from __future__ import annotations

import argparse
from contextlib import ExitStack
import hashlib
import io
import json
import os
from pathlib import Path, PurePosixPath
import stat
import zipfile

HERE = Path(__file__).resolve().parent
MANIFEST = HERE / 'source-manifest.json'
MANIFEST_SHA256 = '70ebe485d8266e821cae41eec10495350b3a4081f2f75bbfd09eace2edf892c3'
MAX_ARCHIVE_BYTES = 32 * 1024 * 1024
MAX_MEMBER_BYTES = 16 * 1024 * 1024
MAX_EXPANDED_BYTES = 64 * 1024 * 1024


class SourceMaterializationError(ValueError):
    """An input, archive member, destination, or candidate identity was rejected."""


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _relative(name: str) -> PurePosixPath:
    if not isinstance(name, str) or not name or '\\' in name or '\x00' in name:
        raise SourceMaterializationError(f'Unsafe relative path: {name!r}')
    path = PurePosixPath(name)
    if path.is_absolute() or any(p in ('', '.', '..') for p in name.split('/')) or ':' in name:
        raise SourceMaterializationError(f'Unsafe relative path: {name!r}')
    return path


def _no_symlink_ancestors(path: Path) -> None:
    for part in (path, *path.parents):
        if part.is_symlink():
            raise SourceMaterializationError(f'Symlink path is not permitted: {part}')


def _load_manifest() -> dict:
    data = MANIFEST.read_bytes()
    if sha256(data) != MANIFEST_SHA256:
        raise SourceMaterializationError('The pinned source manifest changed')
    return json.loads(data)


def _archive_members(archive: zipfile.ZipFile, label: str) -> list[str]:
    infos = archive.infolist()
    names = [info.filename for info in infos]
    if len(names) != len(set(names)):
        raise SourceMaterializationError(f'Duplicate archive member: {label}')
    if len(infos) > 10000 or sum(i.file_size for i in infos) > MAX_EXPANDED_BYTES:
        raise SourceMaterializationError(f'Archive expansion exceeds source bound: {label}')
    for info in infos:
        _relative(info.filename[:-1] if info.is_dir() else info.filename)
        mode = info.external_attr >> 16
        kind = stat.S_IFMT(mode)
        if kind not in (0, stat.S_IFREG, stat.S_IFDIR):
            raise SourceMaterializationError(f'Non-regular archive member: {label}!/{info.filename}')
        if info.flag_bits & 1 or info.file_size > MAX_MEMBER_BYTES:
            raise SourceMaterializationError(f'Encrypted/oversized member: {label}!/{info.filename}')
    return names


def _source_only(data: bytes, name: str, depth: int = 0) -> None:
    if depth > 4:
        raise SourceMaterializationError(f'Nested source archive depth exceeded: {name}')
    lower = name.lower()
    if lower.endswith(('.class', '.dll', '.so', '.dylib', '.exe', '.bin', '.pyc')):
        raise SourceMaterializationError(f'Compiled binary is not a source input: {name}')
    if data.startswith((b'\xca\xfe\xba\xbe', b'\x7fELF', b'MZ')):
        raise SourceMaterializationError(f'Binary content is not a source input: {name}')
    if lower.endswith(('.zip', '.jar')):
        if lower.endswith('.jar') and not lower.endswith('-sources.jar'):
            raise SourceMaterializationError(f'Only source JARs may be copied: {name}')
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            _archive_members(archive, name)
            for info in archive.infolist():
                if not info.is_dir():
                    _source_only(archive.read(info), f'{name}!/{info.filename}', depth + 1)


def inspect_inputs(repo_root: str | Path) -> dict:
    """Check the four local source archive pins without creating a consumer root."""
    repo = Path(repo_root).absolute()
    manifest = _load_manifest()
    missing = []
    mismatches = []
    verified = []
    for key, row in manifest['archives'].items():
        path = repo / _relative(row['path'])
        _no_symlink_ancestors(path)
        if not path.is_file():
            missing.append({'archive': key, **row, 'members': len(row['members'])})
            continue
        if path.stat().st_size != row['bytes'] or row['bytes'] > MAX_ARCHIVE_BYTES:
            mismatches.append({'path': row['path'], 'reason': 'size mismatch'})
            continue
        if sha256(path.read_bytes()) != row['sha256']:
            mismatches.append({'path': row['path'], 'reason': 'SHA-256 mismatch'})
            continue
        verified.append({'archive': key, 'path': row['path'], 'sha256': row['sha256']})
    return {'status': 'PASS' if not missing and not mismatches else 'BLOCKED_SOURCE_INPUTS',
            'verified': verified, 'missing_source_archives': missing,
            'mismatched_source_archives': mismatches}


def _identity_path(root: Path, name: str) -> Path:
    base = root / 'work/api1/source-workspace'
    if name.startswith('loader-sources/'):
        return base / _relative(name.removeprefix('loader-sources/'))
    return base / 'connector-four-loader' / _relative(name)


def verify_sources(consumer_root: str | Path) -> dict:
    """Rehash every reconstructed source/config and all 670 identity records."""
    root = Path(consumer_root).absolute()
    manifest = _load_manifest()
    for row in manifest['files']:
        path = root / _relative(row['destination'])
        _no_symlink_ancestors(path)
        if not path.is_file() or path.stat().st_size != row['bytes'] or sha256(path.read_bytes()) != row['sha256']:
            raise SourceMaterializationError(f'Reconstructed source/config changed: {row["destination"]}')
    identity = json.loads((root / 'work/emi-render-integration/build-identity.json').read_text())
    if (identity['identity_sha256'] != manifest['candidate_identity'] or
            identity['compiler_runtime'] != manifest['compiler_runtime'] or
            len(identity['sources']) != 670 or len(identity['dependencies']) != 169):
        raise SourceMaterializationError('Unexpected candidate identity or record counts')
    if len({row['path'] for row in identity['sources']}) != 670:
        raise SourceMaterializationError('Duplicate identity source record')
    for row in identity['sources']:
        path = _identity_path(root, row['path'])
        if sha256(path.read_bytes()) != row['sha256']:
            raise SourceMaterializationError(f'Candidate source identity mismatch: {row["path"]}')
    if identity['dependencies'] != [{k: row[k] for k in ('filename', 'sha256')} for row in manifest['dependencies']]:
        raise SourceMaterializationError('Dependency identity roster changed')
    return {'status': 'PASS_EXACT_SOURCE_RECORDS', 'source_records_verified': 670,
            'dependency_records_preserved': 169,
            'candidate_identity': identity['identity_sha256'],
            'combined_identity_recomputed': False,
            'combined_identity_note': 'Full identity includes 169 external dependency byte streams and exact JDK runtime; source reconstruction alone cannot recompute it.',
            'full_fml_java_sources': sum(1 for r in identity['sources'] if r['path'].startswith('loader-sources/fml-unified/src/') and r['path'].endswith('.java')),
            'source_and_config_files_verified': len(manifest['files'])}


def _requirements(root: Path, manifest: dict) -> dict:
    """Describe exact external pins separately from code required by the driver."""
    fml = json.loads((root / 'work/api1/source-workspace/fml-unified/provenance/compile-classpath-lock.json').read_text())
    locks = []
    for row in manifest['files']:
        if row['destination'].startswith('portable-bootstrap/') and row['destination'].endswith('-lock.json'):
            data = json.loads((root / row['destination']).read_text())
            locks.append({'path': row['destination'], 'sha256': row['sha256'],
                          'artifacts': data.get('artifacts', []),
                          'generated_inputs': data.get('generatedFmlInputs', [])})
    return {
        'missing_external_source_inputs': [],
        'missing_source_config_inputs': [],
        'external_build_inputs': {
            'resolved_candidate_dependencies': manifest['dependencies'],
            'all_169_have_verification_metadata': True,
            'dependencies_also_in_restoration_locks': sum(bool(r['restoration_locks']) for r in manifest['dependencies']),
            'fml_compile_inputs': fml['artifacts'],
            'official_restoration_locks': locks,
            'fresh_generated_receipts': [
                'work/api1/run/client-dev/development-build/moddev/client-launch-inputs.json',
                'work/emi-render-integration/built-core-artifacts.json (replace historical absolute paths only in a new derived receipt)',
            ],
            'regression_fixture_properties': ['emiCoreJar (pinned Sophisticated Core original)', 'emiBackpackJar (pinned Sophisticated Backpacks original)'],
            'note': 'None of these binary dependencies/toolchains are extracted. Gradle plugin/POM/module metadata must also resolve under strict verification, with the pinned SNAPSHOT repository restored. Runtime/mod/config/graphics preparation belongs to the official runtime and pair driver stages.',
        },
        'needed_code_adapters': manifest['needed_code_adapters'],
    }


def materialize(repo_root: str | Path, consumer_root: str | Path) -> dict:
    """Create exactly one fresh project root containing work/api1 and source helpers.

    All archives/members are validated before the first destination is written.
    An existing destination (even empty) is refused. Partial output on an I/O
    failure is retained for diagnosis and must not be used as a successful result.
    """
    repo = Path(repo_root).absolute()
    root = Path(consumer_root).absolute()
    _no_symlink_ancestors(root)
    if os.path.lexists(root):
        raise SourceMaterializationError(f'Refusing an existing consumer root: {root}')
    if not root.parent.is_dir():
        raise SourceMaterializationError(f'Consumer parent must already exist: {root.parent}')
    manifest = _load_manifest()
    preflight = inspect_inputs(repo)
    if preflight['status'] != 'PASS':
        raise SourceMaterializationError(json.dumps(preflight, sort_keys=True))
    payloads = {}
    with ExitStack() as stack:
        archives = {}
        for key, row in manifest['archives'].items():
            # Recheck the bytes used to open each archive, avoiding a check/read race.
            data = (repo / row['path']).read_bytes()
            if sha256(data) != row['sha256']:
                raise SourceMaterializationError(f'Archive changed during materialization: {row["path"]}')
            archive = stack.enter_context(zipfile.ZipFile(io.BytesIO(data)))
            names = _archive_members(archive, row['path'])
            if names != row['members']:
                raise SourceMaterializationError(f'Unrecognized/missing/reordered archive member: {row["path"]}')
            archives[key] = archive
        for row in manifest['files']:
            destination = str(_relative(row['destination']))
            if destination in payloads:
                raise SourceMaterializationError(f'Duplicate extraction destination: {destination}')
            data = archives[row['archive']].read(row['member'])
            if len(data) != row['bytes'] or sha256(data) != row['sha256']:
                raise SourceMaterializationError(f'Pinned member mismatch: {row["member"]}')
            _source_only(data, row['member'])
            payloads[destination] = data
    if sum(map(len, payloads.values())) > MAX_EXPANDED_BYTES:
        raise SourceMaterializationError('Source extraction exceeds total byte bound')
    root.mkdir(mode=0o755)
    for destination, data in payloads.items():
        output = root / destination
        output.parent.mkdir(parents=True, exist_ok=True)
        _no_symlink_ancestors(output)
        with output.open('xb') as stream:
            stream.write(data)
    for row in manifest['files']:
        if row.get('executable'):
            if row['destination'] != 'work/api1/tools/java-env.sh':
                raise SourceMaterializationError('Unexpected executable source input')
            (root / row['destination']).chmod(0o755)
    identity = verify_sources(root)
    report = {
        'schema': 1, 'status': 'PASS_SOURCE_MATERIALIZATION_ONLY',
        'consumer_root': str(root), 'api1_root': str(root / 'work/api1'),
        'source_manifest_sha256': MANIFEST_SHA256, 'archives': preflight['verified'],
        'identity': identity, 'layout': manifest['layout'],
        'legal_notices_preserved': [r['destination'] for r in manifest['files']
                                    if any(s in r['destination'].lower() for s in ('license', 'notice', 'modifications'))],
        'requirements': _requirements(root, manifest),
        'java_started': False, 'gradle_started': False, 'network_used': False,
        'runtime_ready': False, 'game_accepted': False,
    }
    with (root / 'source-materialization.json').open('x') as stream:
        json.dump(report, stream, indent=2)
        stream.write('\n')
    return report


# The runtime preparation module uses this same repository/consumer contract.
prepare = materialize


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repo-root', type=Path, required=True)
    parser.add_argument('--consumer-root', type=Path)
    parser.add_argument('--inspect', action='store_true')
    args = parser.parse_args()
    if not args.inspect and args.consumer_root is None:
        parser.error('--consumer-root is required unless --inspect is used')
    try:
        report = inspect_inputs(args.repo_root) if args.inspect else materialize(args.repo_root, args.consumer_root)
    except (SourceMaterializationError, OSError, zipfile.BadZipFile) as error:
        print(json.dumps({'status': 'FAILED_SOURCE_MATERIALIZATION', 'error': str(error)}))
        return 1
    print(json.dumps(report if args.inspect else {
        'status': report['status'], 'consumer_root': report['consumer_root'],
        'identity': report['identity'],
        'report': str(args.consumer_root / 'source-materialization.json'),
        'runtime_ready': False,
    }, indent=2))
    return 0 if report['status'].startswith('PASS') else 1


if __name__ == '__main__':
    raise SystemExit(main())
