#!/usr/bin/env python3
"""Capture the bounded exact render build's verified Maven inputs; no downloads.

The 347-component strict XML is the upper bound, not all contents of a Gradle
cache. We retain verified plugin/test/POM/module inputs because no narrower
resolved plugin/test graph was preserved. Six source-substituted artifacts are
reported explicitly; no unverified cached file is admitted.
"""
from __future__ import annotations
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import urllib.parse
import xml.etree.ElementTree as ET
import zipfile
import io
import source_materialize

XML_REL = 'portable-bootstrap/verification-metadata.xml'
XML_SHA256 = '301991fa4fb172adc5776daa36a48efadcb855f145cc386fdfc49e307fe9105f'
IDENTITY_REL = 'work/emi-render-integration/build-identity.json'
IDENTITY_SHA256 = 'd633cd27e50bdb75de44c47951510eed3a00241a57ad67c7101017169c317f38'
CACHE_REL = 'work/api1/source-workspace/gradle-cache/caches/modules-2/files-2.1'
PINNED_REL = 'work/api1/source-workspace/pinned-maven'
SUBSTITUTED = {
    ('org.sinytra', 'ForgeAutoRenamingTool', '1.0.14'): ':infinity-fart',
    ('org.sinytra.adapter', 'core', '2.0.43+1.21.1'): ':infinity-adapter',
}
REPOSITORIES = {
    'central': 'https://repo.maven.apache.org/maven2/',
    'neoforge': 'https://maven.neoforged.net/releases/',
    'sinytra': 'https://maven.su5ed.dev/releases/',
    'fabric': 'https://maven.fabricmc.net/',
    'forge': 'https://maven.minecraftforge.net/',
    'minecraft': 'https://libraries.minecraft.net/',
    'plugins': 'https://plugins.gradle.org/m2/',
    'parchment': 'https://maven.parchmentmc.org/',
}


def digest(path: Path) -> str:
    value = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            value.update(block)
    return value.hexdigest()


def pinned_bytes(repo: Path, relative: str, expected: str) -> bytes:
    path = repo / source_materialize._relative(relative)
    source_materialize._no_symlink_ancestors(path)
    data = path.read_bytes()
    if hashlib.sha256(data).hexdigest() != expected:
        raise ValueError('Changed source input: ' + relative)
    return data


def fallback_repositories(group: str, name: str) -> list[str]:
    if group.startswith('org.sinytra'):
        return ['sinytra']
    if group.startswith('net.fabricmc'):
        return ['fabric', 'central']
    if group.startswith('com.mojang'):
        return ['minecraft', 'central']
    if group.startswith('org.parchmentmc'):
        return ['parchment', 'neoforge']
    if group.startswith('net.minecraftforge'):
        return ['forge', 'neoforge', 'central']
    if group.startswith(('net.neoforged', 'cpw.mods')):
        return ['neoforge', 'plugins', 'central']
    if name.endswith('.gradle.plugin') or group.startswith(('com.gradleup', 'gradle.plugin.', 'org.moddedmc', 'me.modmuss50')):
        return ['plugins', 'central', 'neoforge']
    return ['central', 'neoforge', 'plugins']


def capture(repo_root: str | Path) -> dict:
    repo = Path(repo_root).absolute()
    xml = ET.fromstring(pinned_bytes(repo, XML_REL, XML_SHA256))
    identity = json.loads(pinned_bytes(repo, IDENTITY_REL, IDENTITY_SHA256))
    for element in xml.iter():
        element.tag = element.tag.rsplit('}', 1)[-1]
    verified = {}
    for component in xml.findall('.//component'):
        c = component.attrib
        for artifact in component.findall('artifact'):
            key = (c['group'], c['name'], c['version'], artifact.attrib['name'])
            hashes = [node.attrib['value'] for node in artifact.findall('sha256')]
            if len(hashes) != 1 or key in verified:
                raise ValueError('Expected one immutable SHA-256 per Maven artifact: ' + repr(key))
            verified[key] = hashes[0]
    if len(verified) != 712:
        raise ValueError('The bounded 712-entry strict metadata set changed')
    known_urls = {}
    lock_inputs = []
    for row in source_materialize._load_manifest()['files']:
        relative = row['destination']
        if relative.startswith('portable-bootstrap/') and relative.endswith('-lock.json'):
            lock = json.loads(pinned_bytes(repo, relative, row['sha256']))
            lock_inputs.append({'path': relative, 'sha256': row['sha256']})
            for artifact in lock.get('artifacts', []):
                for url in artifact.get('urls', []):
                    known_urls.setdefault(artifact.get('sha256'), []).append({'url': url, 'basis': 'exact existing restoration lock', 'source': relative})
    matches = {}
    excluded = []
    total_files = 0
    observed_bytes = 0
    cache = repo / CACHE_REL
    source_materialize._no_symlink_ancestors(cache)
    for path in sorted(cache.rglob('*')):
        if path.is_symlink():
            raise ValueError('Symlink in observed Gradle cache: ' + str(path))
        if not path.is_file():
            continue
        total_files += 1
        observed_bytes += path.stat().st_size
        if total_files > 2000 or observed_bytes > 512 * 1024 * 1024 or path.stat().st_size > 64 * 1024 * 1024:
            raise ValueError('Observed cache exceeds bounded capture limits')
        parts = path.relative_to(cache).parts
        sha = digest(path)
        if len(parts) != 5:
            excluded.append({'path': path.relative_to(repo).as_posix(), 'sha256': sha, 'reason': 'unrecognized Gradle file-cache layout'})
            continue
        key = (*parts[:3], parts[4])
        if key not in verified or sha != verified[key]:
            excluded.append({'path': path.relative_to(repo).as_posix(), 'sha256': sha,
                             'reason': 'absent from strict verification set' if key not in verified else 'bytes do not match strict verification SHA-256',
                             **({'expected_sha256': verified[key]} if key in verified else {})})
            continue
        if key in matches:
            raise ValueError('Duplicate identical verified cache artifact: ' + repr(key))
        matches[key] = path
    # SNAPSHOTs are already restored to an explicit Maven layout instead of the
    # Gradle cache. Admit only these four exact XML-pinned snapshot entries.
    for key, expected in verified.items():
        group, name, version, filename = key
        if not version.endswith('-SNAPSHOT'):
            continue
        path = repo / PINNED_REL / group.replace('.', '/') / name / version / filename
        source_materialize._no_symlink_ancestors(path)
        if path.is_file() and digest(path) == expected:
            matches[key] = path
    artifacts = []
    omissions = []
    for key, expected in sorted(verified.items()):
        group, name, version, filename = key
        coordinate = {'group': group, 'artifact': name, 'version': version, 'filename': filename}
        if key not in matches:
            replacement = SUBSTITUTED.get(key[:3])
            omissions.append({**coordinate, 'sha256': expected,
                              'reason': 'replaced by source project in exact render build' if replacement else 'required verified bytes missing from inspected cache',
                              'source_project': replacement,
                              'evidence': 'work/emi-render-integration/candidate-complete-core-sources.zip!/build.gradle.kts' if replacement else None,
                              'blocks_capture': replacement is None})
            continue
        path = matches[key]
        rel = '/'.join([group.replace('.', '/'), name, version, filename])
        urls = []
        for item in known_urls.get(expected, []):
            if item['url'] not in [u['url'] for u in urls]:
                urls.append(item)
        if version.endswith('-SNAPSHOT') and not urls:
            raise ValueError('Timestamped SNAPSHOT URL evidence is missing: ' + repr(key))
        if not version.endswith('-SNAPSHOT'):
            quoted = urllib.parse.quote(rel, safe='/')
            for repository in fallback_repositories(group, name):
                url = REPOSITORIES[repository] + quoted
                if url not in [u['url'] for u in urls]:
                    urls.append({'url': url, 'basis': 'repository-layout fallback; availability-unverified', 'repository': repository})
        artifacts.append({**coordinate, 'path': 'source-workspace/pinned-build-maven/' + rel,
                          'sha256': expected, 'bytes': path.stat().st_size,
                          'phase': 'core-build', 'kind': 'verified-maven-' + path.suffix.lstrip('.'),
                          'urls': [row['url'] for row in urls], 'url_evidence': urls,
                          'observed_source_path': path.relative_to(repo).as_posix(),
                          'verification': XML_REL,
                          'cache_revalidated': True})
    by_hash = {row['sha256']: row for row in artifacts}
    missing_identity = [row for row in identity['dependencies'] if row['sha256'] not in by_hash]
    coverage = [{**row, 'path': by_hash[row['sha256']]['path']} for row in identity['dependencies'] if row['sha256'] in by_hash]
    source_archive = source_materialize._load_manifest()['archives']['render-core']
    full_identity = hashlib.sha256()
    if not missing_identity:
        archive_bytes = pinned_bytes(repo, source_archive['path'], source_archive['sha256'])
        with zipfile.ZipFile(io.BytesIO(archive_bytes)) as archive:
            for row in identity['sources']:
                data = archive.read(row['path'])
                if hashlib.sha256(data).hexdigest() != row['sha256']:
                    raise ValueError('Exact render source hash changed: ' + row['path'])
                full_identity.update(row['path'].encode() + b'\0' + data + b'\0')
        for row in identity['dependencies']:
            data = (repo / by_hash[row['sha256']]['observed_source_path']).read_bytes()
            if hashlib.sha256(data).hexdigest() != row['sha256']:
                raise ValueError('Identity dependency changed during capture: ' + row['filename'])
            full_identity.update(row['filename'].encode() + b'\0' + data + b'\0')
        full_identity.update(identity['compiler_runtime'].encode())
        if full_identity.hexdigest() != identity['identity_sha256']:
            raise ValueError('Combined source/dependency/compiler identity did not reproduce')
    hosts = {urllib.parse.urlsplit(url).hostname for row in artifacts for url in row['urls']}
    # Official download redirects used by the pre-existing source helper; no
    # retrieval is attempted by this capture script.
    hosts.update(['repo1.maven.org', 'plugins-artifacts.gradle.org'])
    return {
        'schema': 1, 'status': 'PASS_LOCAL_CAPTURE' if not missing_identity and not any(r['blocks_capture'] for r in omissions) else 'BLOCKED_LOCAL_CAPTURE',
        'purpose': 'Bounded exact-render Maven source-build index including plugin/test/POM/module metadata; not a runtime binary package',
        'rootPolicy': 'Artifact paths are relative to explicit consumer work/api1 root',
        'allowedHosts': sorted(hosts), 'artifacts': artifacts,
        'source_inputs': [{'path': XML_REL, 'sha256': XML_SHA256}, {'path': IDENTITY_REL, 'sha256': IDENTITY_SHA256}, {'path': source_archive['path'], 'sha256': source_archive['sha256']}, *lock_inputs],
        'candidate_identity': identity['identity_sha256'],
        'reference_identity_verification': {'source_records': len(identity['sources']), 'dependency_records': len(coverage), 'compiler_runtime_literal': identity['compiler_runtime'], 'combined_digest': full_identity.hexdigest() if not missing_identity else None, 'exact_match': not missing_identity, 'scope': 'Pure-Python recomputation from pinned source archive and locally observed verified dependency bytes; no consumer build or JVM'},
        'identity_dependency_coverage': coverage, 'missing_identity_dependencies': missing_identity,
        'counts': {'strict_components': len(xml.findall('.//component')), 'strict_artifact_entries': len(verified),
                   'observed_cache_files': total_files, 'observed_cache_bytes': observed_bytes, 'included_cache_files': sum(not a['version'].endswith('-SNAPSHOT') for a in artifacts),
                   'included_pinned_snapshot_files': sum(a['version'].endswith('-SNAPSHOT') for a in artifacts),
                   'included_artifacts': len(artifacts), 'included_bytes': sum(a['bytes'] for a in artifacts),
                   'identity_dependencies': len(coverage), 'excluded_cache_files': len(excluded),
                   'omitted_strict_entries': len(omissions), 'artifact_extensions': dict(sorted(Counter(Path(a['filename']).suffix for a in artifacts).items()))},
        'excluded_cache_files': excluded, 'omitted_strict_entries': omissions,
        'needed_code_adapters': [
            'After restoring this lock under consumer work/api1, prepend its pinned-build-maven repository to pluginManagement and project repositories via a consumer-only init script while retaining strict verification. Keep the four existing timestamped SNAPSHOT entries in pinned-maven for the original exclusiveContent rule.',
            'Do not treat Gradle files-2.1 payloads as a complete offline cache; binary Gradle metadata/cache indexes were deliberately excluded. Resolve against the restored Maven file repository and source metadata.',
            'Keep official ModDev/NeoForm game artifacts, FML local files, QSL/FFAPI originals, actual probe/test fixture JARs, client assets, and launcher exports in the separate exact runtime restoration stage.',
        ],
        'limitations': [
            'No download/availability check or clean Gradle resolution was run. Fallback URLs are hypotheses about repository layout and every downloaded byte must match the listed SHA-256.',
            'The full previously verified XML set bounds the capture; it is not a newly computed minimal plugin/test dependency graph. Missing source-substituted FART/Adapter release artifacts are explicitly omitted.',
            'Successful local capture proves verified source-build input bytes were observed, not cold-runner build success or runtime acceptance.',
        ],
        'network_used': False, 'java_started': False, 'gradle_started': False,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repo-root', required=True, type=Path)
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    report = capture(args.repo_root)
    with args.output.open('x') as stream:
        json.dump(report, stream, indent=2)
        stream.write('\n')
    print(json.dumps({'status': report['status'], 'counts': report['counts'], 'output': str(args.output)}))
    return 0 if report['status'] == 'PASS_LOCAL_CAPTURE' else 1


if __name__ == '__main__':
    raise SystemExit(main())
