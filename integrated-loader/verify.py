#!/usr/bin/env python3
"""Check payload ownership, upstream provider preservation and reproducible output."""
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import zipfile

ROOT = Path(__file__).resolve().parent
REPO = ROOT.parent
ARTIFACT = ROOT / 'build/libs/unified-infinity-connector-2.0.0-beta.17+1.21.1-derived.jar'
UPSTREAM = REPO / 'docs/research/upstream/connector-2.0.0-beta.17+1.21.1-full.jar'
sha = lambda path: hashlib.sha256(path.read_bytes()).hexdigest()
before_sha = sha(ARTIFACT)
subprocess.run([sys.executable, str(ROOT / 'build.py')], check=True)
assert before_sha == sha(ARTIFACT), 'Derived artifact not reproducible with same inputs'
with zipfile.ZipFile(UPSTREAM) as before, zipfile.ZipFile(ARTIFACT) as after:
    assert len(after.namelist()) == len(set(after.namelist())), 'Duplicate derived entry'
    services = [n for n in after.namelist() if n.startswith('META-INF/services/') and not n.endswith('/')]
    original_services = [n for n in before.namelist() if n.startswith('META-INF/services/') and not n.endswith('/')]
    assert set(services) == set(original_services), 'Service descriptor set changed'
    for name in services:
        assert before.read(name) == after.read(name), name
    assert before.read('META-INF/MANIFEST.MF') == after.read('META-INF/MANIFEST.MF')
    changed = []
    for name in before.namelist():
        if before.read(name) != after.read(name):
            assert name.startswith(('org/sinytra/connector/locator/ConnectorLocator',
                'org/sinytra/connector/transformer/jar/JarTransformer',
                'org/sinytra/connector/transformer/jar/JarTransformInstance',
                'reloc/net/minecraftforge/fart/internal/AsyncHelper')), name
            changed.append(name)
    assert 'org/sinytra/connector/locator/ConnectorLocator.class' in changed
    assert 'org/sinytra/connector/transformer/jar/JarTransformer.class' in changed
    assert 'org/sinytra/connector/infinity/BoundedBatch.class' in after.namelist()
    assert 'org/sinytra/connector/infinity/LoadProgress.class' in after.namelist()
    identity = after.read('org/sinytra/connector/infinity/BuildIdentity.class')
    provenance = json.loads(after.read('META-INF/unified-infinity/provenance.json'))
    assert provenance['source_sha256'].encode() in identity, 'Cache patch identity absent'
report = {'reproducible': True, 'artifact_sha256': before_sha,
    'changed_upstream_payloads': changed, 'unchanged_service_descriptors': services,
    'manifest_preserved': True, 'source_identity_in_cache_class': True}
(ROOT / 'build/verification.json').write_text(json.dumps(report, indent=2) + '\n')
print('PASS reproducible build, owned payloads, unchanged services/manifest, cache patch identity')
