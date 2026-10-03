#!/usr/bin/env python3
"""Reproducible source-class patch build against one immutable official Connector JAR."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import zipfile

ROOT = Path(__file__).resolve().parent
REPO = ROOT.parent
BUILD = ROOT / 'build'
UPSTREAM = REPO / 'docs/research/upstream/connector-2.0.0-beta.17+1.21.1-full.jar'
EXPECTED_SHA = '270b2d385be50932419b7d57d4f4bf7328d70e08d0dd9d88adefdb3c5d08a986'
JAVA_HOME = Path(os.environ.get('JAVA_HOME', REPO / '.toolchains/jdk-21.0.12.1+1'))
sha = lambda data: hashlib.sha256(data).hexdigest()
if sha(UPSTREAM.read_bytes()) != EXPECTED_SHA:
    raise SystemExit('Upstream Connector artifact SHA-256 mismatch')
expected_blobs = {
    'JarTransformer.java': '196ce6e501034a68c084f6b924dd949d1fa2b148',
    'ConnectorLocator.java': '3db45cc99095ff3bdbbad4aa75c2071d5981a7d8',
    'JarTransformInstance.java': 'f53f23319e609495aa17a47dfa800eb57c5821fd',
    'ConnectorTransformerEnvironment.java': 'ef09acfac243d6ae09e73062ab0b6756c1048eaa',
}
for name, expected in expected_blobs.items():
    raw = (ROOT / 'upstream' / name).read_bytes()
    actual = hashlib.sha1(f'blob {len(raw)}\0'.encode() + raw).hexdigest()
    if actual != expected:
        raise SystemExit(f'Captured released source Git blob mismatch: {name}')
FART_SOURCES = ROOT / 'upstream/ForgeAutoRenamingTool-1.0.14-sources.jar'
FART_SHA = '1cf3acb13c14360805a84040266cb12ad467bdd98238b3ba8ec1b115be79782a'
if sha(FART_SOURCES.read_bytes()) != FART_SHA:
    raise SystemExit('FART source artifact SHA-256 mismatch')
with zipfile.ZipFile(FART_SOURCES) as fart:
    assert fart.read('net/minecraftforge/fart/internal/AsyncHelper.java') == (ROOT / 'upstream/AsyncHelper.java').read_bytes()
BUILD.mkdir(exist_ok=True)
classes = BUILD / 'classes'
if classes.exists(): shutil.rmtree(classes)
classes.mkdir()
source_files = sorted((ROOT / 'src/main/java').rglob('*.java'))
source_digest = hashlib.sha256()
for f in source_files:
    source_digest.update(f.relative_to(ROOT).as_posix().encode() + b'\0' + f.read_bytes() + b'\0')
patch_id = source_digest.hexdigest()
generated = BUILD / 'generated/org/sinytra/connector/infinity/BuildIdentity.java'
generated.parent.mkdir(parents=True, exist_ok=True)
generated.write_text('package org.sinytra.connector.infinity;\npublic final class BuildIdentity {\n'
    + '    private BuildIdentity() {}\n'
    + f'    public static final String SOURCE_SHA256 = "{patch_id}";\n'
    + f'    public static final String TRANSFORM_CACHE_SUFFIX = ":unified-infinity:{patch_id}";\n}}\n')
# All host jars are pinned by the installed NeoForge distribution. Gradle bundles
# JetBrains annotations for compilation only; it is not added to the derived JAR.
classpath = [UPSTREAM] + sorted((REPO / 'run/neoforge-native/libraries').rglob('*.jar'))
classpath += sorted((REPO / '.toolchains/gradle-8.11.1/lib').glob('annotations-*.jar'))
command = [str(JAVA_HOME / 'bin/javac'), '-proc:none', '--release', '21', '-g', '-encoding', 'UTF-8',
    '-classpath', os.pathsep.join(map(str, classpath)), '-d', str(classes)] + list(map(str, source_files)) + [str(generated)]
subprocess.run(command, check=True)

output = BUILD / 'libs/unified-infinity-connector-2.0.0-beta.17+1.21.1-derived.jar'
output.parent.mkdir(parents=True, exist_ok=True)
replacements = {f.relative_to(classes).as_posix(): f.read_bytes() for f in sorted(classes.rglob('*.class'))}
replacements['META-INF/unified-infinity/LICENSE-Connector.txt'] = (ROOT / 'LICENSE').read_bytes()
replacements['META-INF/unified-infinity/LICENSE-FART-LGPL-2.1.txt'] = (ROOT / 'upstream/FART-LICENSE.txt').read_bytes()
replacements['META-INF/unified-infinity/sources/ForgeAutoRenamingTool-1.0.14-sources.jar'] = FART_SOURCES.read_bytes()
replacements['META-INF/unified-infinity/sources/AsyncHelper.java'] = (ROOT / 'src/main/java/reloc/net/minecraftforge/fart/internal/AsyncHelper.java').read_bytes()
replacements['META-INF/unified-infinity/PATCHES.md'] = (ROOT / 'PATCHES.md').read_bytes()
provenance = {
    'format': 1, 'kind': 'source-class-patch-research-build',
    'upstream_sha256': EXPECTED_SHA, 'source_sha256': patch_id,
    'upstream_tag': '2.0.0-beta.17+1.21.1',
    'upstream_git_tree': '8b27f1ad042aae8037bcc522b321c03fcce1a12a',
    'upstream_source_git_blobs': expected_blobs,
    'fart_sources_sha256': FART_SHA,
    'fart_sources_url': 'https://maven.sinytra.org/org/sinytra/ForgeAutoRenamingTool/1.0.14/ForgeAutoRenamingTool-1.0.14-sources.jar',
    'fart_license_url': 'https://raw.githubusercontent.com/MinecraftForge/ForgeAutoRenamingTool/master/LICENSE.txt',
    'compiler': subprocess.check_output([str(JAVA_HOME / 'bin/javac'), '-version'], text=True).strip(),
    'compile_dependencies': [{'path': p.relative_to(REPO).as_posix(), 'sha256': sha(p.read_bytes())} for p in classpath],
    'source_files': [{'path': p.relative_to(ROOT).as_posix(), 'sha256': sha(p.read_bytes())} for p in source_files],
}
replacements['META-INF/unified-infinity/provenance.json'] = (json.dumps(provenance, indent=2, sort_keys=True) + '\n').encode()
# Only the explicitly owned upstream classes, private core, and fork provenance may change.
allowed = ('org/sinytra/connector/locator/ConnectorLocator', 'org/sinytra/connector/transformer/jar/JarTransformer',
           'org/sinytra/connector/transformer/jar/JarTransformInstance', 'reloc/net/minecraftforge/fart/internal/AsyncHelper',
           'org/sinytra/connector/infinity/', 'META-INF/unified-infinity/')
assert all(any(n.startswith(prefix) for prefix in allowed) for n in replacements)
changed = []
with zipfile.ZipFile(UPSTREAM) as src, zipfile.ZipFile(output, 'w', compression=zipfile.ZIP_DEFLATED, compresslevel=9) as dst:
    names = src.namelist()
    assert len(names) == len(set(names)), 'Duplicate upstream ZIP entries'
    assert not any(n.upper().endswith(('.SF', '.RSA', '.DSA', '.EC')) for n in names), 'Signed upstream JAR needs a separate signing policy'
    for name in sorted(set(names) | set(replacements)):
        data = replacements.get(name) if name in replacements else src.read(name)
        if name in replacements:
            before = src.read(name) if name in names else None
            changed.append({'path': name, 'action': 'replace' if before is not None else 'add',
                'before_sha256': sha(before) if before is not None else None, 'after_sha256': sha(data)})
        info = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
        info.compress_type = zipfile.ZIP_DEFLATED
        info.external_attr = (0o40755 if name.endswith('/') else 0o100644) << 16
        dst.writestr(info, data)
with zipfile.ZipFile(UPSTREAM) as before, zipfile.ZipFile(output) as after:
    for name in before.namelist():
        if name not in replacements:
            assert before.read(name) == after.read(name), f'Unexpected payload change: {name}'
    services = [name for name in before.namelist() if name.startswith('META-INF/services/') and not name.endswith('/')]
    assert all(before.read(name) == after.read(name) for name in services)
report = {'artifact': output.relative_to(REPO).as_posix(), 'artifact_sha256': sha(output.read_bytes()),
    'source_sha256': patch_id, 'upstream_sha256': EXPECTED_SHA, 'changes': changed,
    'unchanged_service_descriptors': services,
    'note': 'ZIP container metadata is normalized; unchanged entry payloads are byte-identical.'}
(BUILD / 'entry-diff.json').write_text(json.dumps(report, indent=2, sort_keys=True) + '\n')
(BUILD / 'provenance.json').write_text(json.dumps(provenance, indent=2, sort_keys=True) + '\n')
print(json.dumps({'artifact': str(output), 'sha256': report['artifact_sha256'], 'source_sha256': patch_id}, indent=2))
