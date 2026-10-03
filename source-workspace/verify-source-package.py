#!/usr/bin/env python3
"""Verify the published immutable source package; never downloads, builds or launches."""
import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import zipfile

BASE = Path(__file__).resolve().parent
ARCHIVE = BASE / 'artifacts/unified-infinity-complete-connector-fart-adapter-sources.zip'
EXPECTED_ARCHIVE = '7b3b85e3334a48c1b61cc7aaafed605cd9d4525322554828ef80bee4a8b1a672'


def require(condition, message):
    if not condition:
        raise SystemExit(message)


def digest(data):
    return hashlib.sha256(data).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--reconstructed', type=Path, help='Optional ordinary reconstructed source checkout')
    args = parser.parse_args()
    lock = json.loads((BASE / 'source-lock.json').read_text())
    for name, expected in lock['files'].items():
        require(digest((BASE / name).read_bytes()) == expected, 'Source-lock mismatch: ' + name)
    require(digest(ARCHIVE.read_bytes()) == EXPECTED_ARCHIVE, 'Complete source archive digest mismatch')
    identity = json.loads((BASE / 'provenance/final-build-identity.json').read_text())
    with zipfile.ZipFile(ARCHIVE) as source:
        entries = [entry for entry in source.infolist() if not entry.is_dir()]
        require(len({entry.filename for entry in entries}) == len(entries), 'Duplicate archive names')
        for entry in entries:
            path = PurePosixPath(entry.filename)
            require(not path.is_absolute() and '..' not in path.parts, 'Unsafe archive path')
            require(not entry.filename.endswith(('.class', '.dll', '.so', '.exe')), 'Compiled artifact in source archive')
            data = source.read(entry)
            if args.reconstructed:
                candidate = args.reconstructed / entry.filename
                require(candidate.is_file() and candidate.read_bytes() == data,
                        'Reconstruction mismatch: ' + entry.filename)
        for item in identity['sources']:
            require(digest(source.read(item['path'])) == item['sha256'],
                    'Build identity source mismatch: ' + item['path'])
    result = {
        'status': 'passed', 'source_lock_inputs': len(lock['files']),
        'source_archive_sha256': EXPECTED_ARCHIVE, 'source_archive_files': len(entries),
        'build_identity_source_inputs': len(identity['sources']),
        'reconstruction_checked': bool(args.reconstructed),
        'scope': 'Source/package integrity only; no compilation, dependency resolution or Minecraft execution',
    }
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
