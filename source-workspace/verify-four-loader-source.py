#!/usr/bin/env python3
"""Read-only accepted source correspondence checks; no Java, Gradle, network or game."""
import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath

ROOT = Path(__file__).resolve().parent.parent
DOCS = ROOT / 'docs/four-loader'
IDENTITY_SHA256 = 'f35bda92ca5648a4fb33b68c8c5b68e4b9aea5a3c8e86e8c9db7900d9e55460e'
ACCEPTED_IDENTITY = 'c5bc17c49d1a2e2f2eadbc51e2a23e2f7a2ecc4720d827b855047b22bdf83499'


def require(condition, message):
    if not condition:
        raise SystemExit(message)


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def verify(root):
    identity_path = DOCS / 'accepted-build-identity-98d86a92.json'
    require(digest(identity_path) == IDENTITY_SHA256, 'Accepted identity manifest changed')
    identity = json.loads(identity_path.read_text())
    require(identity['identity_sha256'] == ACCEPTED_IDENTITY, 'Wrong accepted identity')
    records = identity['sources']
    require(len(records) == 390, 'Expected 390 source/build records')
    expected_java = set()
    for record in records:
        name = record['path']
        path = PurePosixPath(name)
        require(not path.is_absolute() and '..' not in path.parts, 'Unsafe identity path')
        actual = root / name
        require(actual.is_file() and digest(actual) == record['sha256'], 'Source mismatch: ' + name)
        if name.endswith('.java'):
            expected_java.add(name)
    actual_java = {str(path.relative_to(root)) for path in root.rglob('*.java')
                   if not any(part in {'.git', '.gradle', 'build'} for part in path.relative_to(root).parts)}
    require(actual_java == expected_java, 'Unexpected or missing Java source files')
    recovery = json.loads((DOCS / 'helper-recovery-verification.json').read_text())
    for record in recovery['files']:
        require(digest(root / record['path']) == record['sha256'], 'Recovered helper mismatch: ' + record['path'])
    components = json.loads((DOCS / 'accepted-component-sources.json').read_text())
    for record in components['files']:
        require(digest(ROOT / record['path']) == record['sha256'], 'Component source mismatch: ' + record['path'])
    return {
        'status': 'passed', 'accepted_identity': ACCEPTED_IDENTITY,
        'matched_source_records': len(records), 'java_source_files': len(expected_java),
        'recorded_dependency_digests': len(identity['dependencies']),
        'recovered_helper_records': len(recovery['files']),
        'host_provider_source_records': len(components['files']),
        'source_mismatches': 0,
        'scope': 'Source correspondence only; no compilation, dependency resolution or runtime execution',
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-root', type=Path, default=ROOT / 'source-workspace/connector-four-loader')
    args = parser.parse_args()
    print(json.dumps(verify(args.source_root), indent=2))


if __name__ == '__main__':
    main()
