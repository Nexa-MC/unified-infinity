#!/usr/bin/env python3
"""Verify published v6 source correspondence without running code or downloading."""
import hashlib
import json
from pathlib import Path, PurePosixPath
import zipfile

ROOT = Path(__file__).resolve().parent.parent
DOC = ROOT / 'docs/fusion-v6'

def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def relative(name):
    path = PurePosixPath(name)
    if path.is_absolute() or '..' in path.parts:
        raise ValueError('Unsafe relative path: ' + name)
    return ROOT.joinpath(*path.parts)

def verify():
    identity = json.loads((DOC / 'accepted-core-build-identity.json').read_text())
    assert identity['identity_sha256'] == 'b468ee1cffa3d6e35a0f106ad55a02a8b43eb14267e900b18264712def7ffa94'
    assert len(identity['sources']) == 655
    archive = ROOT / 'source-workspace/artifacts/unified-infinity-fusion-v6-complete-sources.zip'
    assert digest(archive) == '80c7f6e4b8ad52e9d153f895487a10312fc6950a4bc8c35e2eb61f286f8a443e'
    seen = set()
    with zipfile.ZipFile(archive) as source:
        for item in identity['sources']:
            name = PurePosixPath(item['path'])
            assert item['path'] not in seen
            seen.add(item['path'])
            rel = 'source-workspace/' + str(PurePosixPath(*name.parts[1:])) if name.parts[0] == 'loader-sources' else 'source-workspace/connector-four-loader/' + item['path']
            assert digest(relative(rel)) == item['sha256'], rel
            assert hashlib.sha256(source.read(item['path'])).hexdigest() == item['sha256'], item['path']
    product = json.loads((DOC / 'product-source-correspondence.json').read_text())
    for name, item in product['sourceFiles'].items():
        assert digest(relative(name)) == item['sha256'], name
    preload = json.loads((DOC / 'preload-source-continuity.json').read_text())
    for item in preload['records']:
        assert digest(relative(item['path'])) == item['sha256'], item['path']
    launch = json.loads((DOC / 'core-source-freeze-receipt.json').read_text())
    for name, sha in launch['launchToolSources'].items():
        assert digest(relative(name)) == sha, name
    print(json.dumps({'status': 'PASS_SOURCE_CORRESPONDENCE', 'core_records': len(seen), 'product_records': len(product['sourceFiles']), 'preload_continuity_records': len(preload['records']), 'launch_tool_records': len(launch['launchToolSources']), 'runtime_proof': 'See separate scoped v6 acceptance summary', 'provider_proof': 'Immutable source continuity only; no fresh reproducible build'}))

if __name__ == '__main__':
    verify()
