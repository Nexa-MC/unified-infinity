#!/usr/bin/env python3
"""Pinned, offline official-Loom build; default checks never download or start Java."""
from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import subprocess
import tarfile
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
import zipfile

CI = Path(__file__).resolve().parent
ROOT = CI.parent
LOCK = json.loads((CI / 'dependency-lock.json').read_text())
EXPECTED = json.loads((CI / 'expected.json').read_text())
REPORT = ROOT / 'diagnostic-output'
MAX_INPUT_BYTES = 256 * 1024 * 1024
MAX_TOTAL_BYTES = 1024 * 1024 * 1024
BRANCH = 'refs/heads/diagnostic/quilt-loom-api1-20261005-0934'
REPOSITORY = 'Nexa-MC/unified-infinity'
PROBE = 'four-loader/quilt-api-probe/build/unified-native-quilt-tooltip-probe-0.1.0.jar'


def require(condition, message):
    if not condition:
        raise RuntimeError(message)


def digest(path, algorithm='sha256'):
    with path.open('rb') as source:
        return hashlib.file_digest(source, algorithm).hexdigest()


def destination(name, root=ROOT):
    part = PurePosixPath(name)
    require(bool(part.parts) and not part.is_absolute() and '..' not in part.parts, 'Unsafe relative path')
    path = root.joinpath(*part.parts)
    require(path.is_relative_to(root), 'Destination escaped its root')
    for parent in [path, *path.parents]:
        if parent == root.parent:
            break
        require(not parent.is_symlink(), 'Symlink destination is not accepted: ' + name)
    return path


def validate_url(url):
    parsed = urllib.parse.urlsplit(url)
    require(parsed.scheme == 'https' and parsed.hostname in LOCK['allowedDownloadHosts']
            and not parsed.username and not parsed.password and parsed.port in (None, 443),
            'Non-allowlisted HTTPS download or redirect')
    return url


class SafeRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        validate_url(newurl)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def verify(row, path):
    require(path.is_file() and path.stat().st_size == row['bytes'], 'Pinned input size mismatch: ' + row['path'])
    for algorithm in ('sha256', 'sha1'):
        if algorithm in row:
            require(digest(path, algorithm) == row[algorithm], 'Pinned ' + algorithm + ' mismatch: ' + row['path'])


def check_sources(require_ready=False):
    manifest = json.loads((CI / 'input-source-manifest.json').read_text())
    for name, expected in manifest['files'].items():
        require(digest(destination(name)) == expected, 'Source checksum mismatch: ' + name)
    require(EXPECTED['probeSha256'] == '9106f5a6629d3e3f2206bc967d77aaff228f67ef6e216cd8f27f79139e743dfe', 'Changed original probe target')
    require(len(EXPECTED['builderInputPins']) == 22, 'Changed original builder input count')
    require(EXPECTED['probeMaxBytes'] == 65536, 'Changed probe transport bound')
    validate_recovery_policy(json.loads((CI / 'recovery-policy.json').read_text()))
    seen = set()
    for row in LOCK['artifacts']:
        destination(row['path'])
        require(row['path'] not in seen, 'Duplicate destination: ' + row['path'])
        seen.add(row['path'])
        require(0 < row['bytes'] <= MAX_INPUT_BYTES, 'Unbounded input size')
        require(any(key in row for key in ('sha256', 'sha1')), 'Unhashed input')
        for key, length in [('sha256', 64), ('sha1', 40)]:
            if key in row:
                require(re.fullmatch('[0-9a-f]{' + str(length) + '}', row[key]) is not None, 'Invalid hash')
        require(bool(row['urls']), 'No official URL for ' + row['path'])
        for url in row['urls']:
            validate_url(url)
        if 'mavenPath' in row:
            destination('ci/maven/' + row['mavenPath'])
    require(sum(row['bytes'] for row in LOCK['artifacts']) <= MAX_TOTAL_BYTES, 'Input closure exceeds 1 GiB')
    if require_ready:
        require(LOCK['closureStatus'] == 'PINNED' and not LOCK['missingPrerequisites'],
                'Unresolved prerequisite pins: ' + '; '.join(LOCK['missingPrerequisites']))
    return manifest


def validate_recovery_policy(policy):
    require(policy['adaptation'] == 'CI_ONLY_SINGLE_GENERATED_COMPILER_INPUT', 'Unexpected recovery adaptation')
    name = policy['generatedInputPath']
    require(name in EXPECTED['generatedPins'] and name in EXPECTED['builderInputPins']
            and name.endswith('.jar'), 'Recovery must target the original single generated JAR')
    require(policy['historicalWholeJarSha256'] == EXPECTED['generatedPins'][name]
            == EXPECTED['builderInputPins'][name]
            == 'bd5e9b18303dfbd03365286b126dfde5c688861307e0ed541e16313e6aca1d90', 'Historical whole-JAR pin changed')
    require(policy['recoverySortedEntryContentSha256']
            == '2a3f775046bf277ef041dca2666ccc6b33933bec769e55ae35ca12f1f15e5ae8', 'Unapproved recovery content identity')
    require(policy['historicalEntryEquivalence'] == 'UNKNOWN', 'Unproven historical entry equivalence')


def recovery_input_record():
    """Reverify every locked input, with one explicit generated-content gate."""
    check_sources(require_ready=True)
    policy = json.loads((CI / 'recovery-policy.json').read_text())
    validate_recovery_policy(policy)
    for row in LOCK['artifacts']:
        verify(row, destination(row['path']))
    name = policy['generatedInputPath']
    for input_name, expected in EXPECTED['builderInputPins'].items():
        if input_name != name:
            path = destination(input_name)
            require(path.is_file() and digest(path) == expected, 'Unchanged original builder pin mismatch: ' + input_name)
    path = destination(name)
    require(path.is_file() and 0 < path.stat().st_size <= MAX_INPUT_BYTES, 'Recovery generated input missing or oversized')
    metadata = zip_metadata(path)
    require(metadata['sortedEntryContentSha256'] == policy['recoverySortedEntryContentSha256'],
            'Recovery sorted-entry content identity mismatch; no further relaxation')
    return {'path': name, 'sha256': digest(path), 'bytes': path.stat().st_size,
            'sortedEntryContentSha256': metadata['sortedEntryContentSha256'],
            'historicalWholeJarSha256': policy['historicalWholeJarSha256'],
            'matchesHistoricalWholeJarPin': digest(path) == policy['historicalWholeJarSha256'],
            'historicalEntryEquivalence': 'UNKNOWN', 'officialInputsReverified': len(LOCK['artifacts']),
            'unchangedBuilderInputsReverified': len(EXPECTED['builderInputPins']) - 1,
            'mappingsOriginalPinMatch': True, 'zipMetadata': metadata}


def restore(row, deadline):
    path = destination(row['path'])
    if path.exists():
        verify(row, path)
        return path
    path.parent.mkdir(parents=True, exist_ok=True)
    opener = urllib.request.build_opener(SafeRedirect())
    last = None
    for url in row['urls']:
        require(time.monotonic() < deadline, 'Pinned input restoration exceeded 10 minutes')
        validate_url(url)
        try:
            with opener.open(urllib.request.Request(url, headers={'User-Agent': 'Unified-Quilt-Bounded-CI/1'}), timeout=45) as response:
                with tempfile.NamedTemporaryFile(dir=path.parent, prefix='.download-', delete=False) as output:
                    temporary = Path(output.name)
                    try:
                        count = 0
                        while True:
                            data = response.read(1024 * 1024)
                            if not data:
                                break
                            require(time.monotonic() < deadline, 'Pinned input restoration exceeded 10 minutes')
                            count += len(data)
                            require(count <= row['bytes'], 'Response exceeds pinned size')
                            output.write(data)
                        output.flush()
                        verify(row, temporary)
                        temporary.replace(path)
                    finally:
                        temporary.unlink(missing_ok=True)
            return path
        except urllib.error.HTTPError as error:
            if error.code not in (404, 410):
                raise
            last = error
    raise RuntimeError('No pinned official URL supplied ' + row['path']) from last


def install_toolchains():
    jdk = ROOT / '.toolchains/jdk-21.0.12.1+1'
    require(not jdk.exists(), 'Toolchain destination must be fresh')
    with tarfile.open(ROOT / '.toolchains/jdk21.tar.gz') as archive:
        members = archive.getmembers()
        require(sum(member.size for member in members) < 1024 * 1024 * 1024, 'Oversized JDK archive')
        require(all(PurePosixPath(member.name).parts[0] == jdk.name for member in members), 'Unexpected JDK root')
        archive.extractall(ROOT / '.toolchains', filter='data')
    with zipfile.ZipFile(ROOT / '.toolchains/gradle-8.11.1-bin.zip') as archive:
        require(sum(info.file_size for info in archive.infolist()) < 512 * 1024 * 1024, 'Oversized Gradle archive')
        for info in archive.infolist():
            parts = PurePosixPath(info.filename).parts
            require(parts and parts[0] == 'gradle-8.11.1' and '..' not in parts, 'Unexpected Gradle archive path')
            require((info.external_attr >> 16) & 0o170000 != 0o120000, 'Gradle symlink is not accepted')
            destination('.toolchains/' + info.filename)
        archive.extractall(ROOT / '.toolchains')
    gradle = ROOT / '.toolchains/gradle-8.11.1/bin/gradle'
    gradle.chmod(0o755)
    for name, expected in EXPECTED['toolchainFiles'].items():
        require(digest(destination(name)) == expected, 'Original builder JDK input changed: ' + name)
    return jdk, gradle


def seed_verified_inputs():
    for row in LOCK['artifacts']:
        path = destination(row['path'])
        verify(row, path)
        if 'mavenPath' in row:
            target = destination('ci/maven/' + row['mavenPath'])
            if target != path:
                target.parent.mkdir(parents=True, exist_ok=True)
                if target.exists():
                    verify(row, target)
                else:
                    shutil.copyfile(path, target)
    url = 'https://piston-meta.mojang.com/v1/packages/22a1966494dfa4eeb5ee778c8e6ed5b774839582/1.21.1.json'
    java_hash = 0
    for character in url:
        java_hash = (31 * java_hash + ord(character)) & 0xffffffff
    target = destination('run/quilt-native-client/gradle-cache/caches/quilt-loom/1.21.1/minecraft_info_' + format(java_hash, 'x') + '.json')
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(CI / 'minecraft-1.21.1.json', target)


def run_step(name, command, environment, timeout, receipt):
    result = subprocess.run(list(map(str, command)), cwd=ROOT, env=environment,
                            text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=timeout)
    (REPORT / (name + '.log')).write_text(result.stdout)
    print(result.stdout, flush=True)
    receipt['steps'].append({'name': name, 'exitCode': result.returncode})
    (REPORT / 'receipt.json').write_text(json.dumps(receipt, indent=2) + '\n')
    require(result.returncode == 0, name + ' failed; no successful-build claim')


def zip_metadata(path):
    """Describe packaging and hash sorted entry contents without returning them."""
    with zipfile.ZipFile(path) as archive:
        entries = archive.infolist()
        require(len(entries) <= 100000, 'Unexpected generated ZIP entry count')
        require(sum(entry.file_size for entry in entries) <= 1024 * 1024 * 1024, 'Oversized generated ZIP contents')
        timestamps = sorted({entry.date_time for entry in entries})
        content = []
        for entry in sorted(entries, key=lambda item: item.filename):
            if not entry.is_dir():
                with archive.open(entry) as stream:
                    content.append([entry.filename, entry.file_size, hashlib.file_digest(stream, 'sha256').hexdigest()])
        canonical = json.dumps(content, ensure_ascii=True, separators=(',', ':')).encode('ascii')
        order = json.dumps([entry.filename for entry in entries], ensure_ascii=True, separators=(',', ':')).encode('ascii')
        return {'entryCount': len(entries), 'fileEntryCount': len(content),
                'compressedBytes': sum(entry.compress_size for entry in entries),
                'uncompressedBytes': sum(entry.file_size for entry in entries),
                'compressionMethods': sorted({entry.compress_type for entry in entries}),
                'distinctTimestampCount': len(timestamps), 'timestampsFirst16': timestamps[:16],
                'entryOrderSha256': hashlib.sha256(order).hexdigest(),
                'sortedEntryContentSha256': hashlib.sha256(canonical).hexdigest(),
                'contentDigestFormat': 'SHA256(compact ASCII JSON of filename-sorted [name,size,SHA256(uncompressed bytes)] for non-directory entries)'}


def record_generated_inputs(receipt):
    """Print only bounded path/size/hash metadata, never Minecraft payload bytes."""
    cache = destination('run/quilt-native-client/gradle-cache/caches/quilt-loom')
    names = set(EXPECTED['generatedPins'])
    if cache.exists():
        names.update(path.relative_to(ROOT).as_posix() for path in cache.rglob('*')
                     if path.is_file() and (path.suffix in ('.jar', '.tiny') or path.name.endswith('.jar.backup')))
    require(len(names) <= 128, 'Unexpected generated-input inventory size')
    inventory = []
    for name in sorted(names):
        path = destination(name)
        row = {'path': name, 'exists': path.is_file()}
        if path.is_file():
            require(path.stat().st_size <= MAX_INPUT_BYTES, 'Oversized generated input')
            row.update({'bytes': path.stat().st_size, 'sha256': digest(path)})
        if name in EXPECTED['generatedPins']:
            row['expectedSha256'] = EXPECTED['generatedPins'][name]
            row['matchesOriginalPin'] = row.get('sha256') == row['expectedSha256']
            if path.is_file() and path.suffix == '.jar' and not row['matchesOriginalPin']:
                row['zipMetadata'] = zip_metadata(path)
        inventory.append(row)
    receipt['generatedInputInventory'] = inventory
    (REPORT / 'generated-input-inventory.json').write_text(json.dumps(inventory, indent=2) + '\n')
    (REPORT / 'receipt.json').write_text(json.dumps(receipt, indent=2) + '\n')
    print('OFFICIAL_LOOM_GENERATED_INPUT_INVENTORY ' + json.dumps(inventory, sort_keys=True), flush=True)


def build(fetch):
    require(fetch, 'Build requires explicit --fetch')
    require(os.environ.get('GITHUB_ACTIONS') == 'true' and os.environ.get('GITHUB_REPOSITORY') == REPOSITORY
            and os.environ.get('GITHUB_REF') == BRANCH, 'Build restricted to the approved diagnostic CI branch')
    manifest = check_sources(require_ready=True)
    require(not REPORT.exists(), 'Diagnostic output must start fresh')
    REPORT.mkdir()
    receipt = {'status': 'STARTED_NOT_ACCEPTED', 'gameLaunched': False, 'assetsDownloaded': False,
               'officialLoomModified': False, 'runtimeAcceptance': 'NOT RUN', 'steps': [],
               'commit': os.environ.get('GITHUB_SHA'), 'sourceFiles': len(manifest['files']),
               'sourceManifestSha256': digest(CI / 'input-source-manifest.json'),
               'dependencyLockSha256': digest(CI / 'dependency-lock.json')}
    deadline = time.monotonic() + 600
    for row in LOCK['artifacts']:
        restore(row, deadline)
    seed_verified_inputs()
    jdk, gradle = install_toolchains()
    environment = dict(os.environ)
    for variable in ('JAVA_TOOL_OPTIONS', 'JDK_JAVA_OPTIONS', '_JAVA_OPTIONS', 'CLASSPATH', 'GRADLE_OPTS'):
        environment.pop(variable, None)
    environment.update({'JAVA_HOME': str(jdk), 'GRADLE_USER_HOME': str(ROOT / 'run/quilt-native-client/gradle-cache'),
                        'PATH': str(jdk / 'bin') + os.pathsep + environment['PATH'], 'LC_ALL': 'C.UTF-8', 'TZ': 'UTC'})
    try:
        run_step('official-loom-mappings', [gradle, '--offline', '--no-daemon', '--no-parallel', '--max-workers=1',
                 '--console=plain', '-p', CI, '-Porg.gradle.java.installations.paths=' + str(jdk), 'prepareProbeMappings'],
                 environment, 720, receipt)
    finally:
        record_generated_inputs(receipt)
    receipt['recoveryInputPreflight'] = recovery_input_record()
    run_step('documented-recovery-adapter', ['python3', CI / 'recovery-builder.py', '--compile'], environment, 180, receipt)
    probe = destination(PROBE)
    require(probe.stat().st_size <= EXPECTED['probeMaxBytes'] and digest(probe) == EXPECTED['probeSha256'],
            'Original probe output mismatch; return transport forbidden')
    check_sources(require_ready=True)
    recovery_receipt = json.loads((REPORT / 'recovery-receipt.json').read_text())
    require(recovery_receipt['status'] == 'PASS_RECOVERY_ADAPTER_EXACT_ORIGINAL_PROBE', 'Recovery adapter did not pass')
    receipt.update({'status': 'PASS_RECOVERY_ADAPTER_EXACT_ORIGINAL_PROBE', 'probeSha256': digest(probe), 'probeBytes': probe.stat().st_size,
                    'historicalGeneratedInputPins': EXPECTED['generatedPins'], 'recovery': recovery_receipt,
                    'builderExecution': 'UNCHANGED_SOURCE_WITH_ONE_IN_MEMORY_INPUT_PIN_ADAPTATION',
                    'historicalEntryEquivalence': 'UNKNOWN'})
    (REPORT / 'receipt.json').write_text(json.dumps(receipt, indent=2) + '\n')
    print(json.dumps(receipt, indent=2))
    if os.environ.get('GITHUB_STEP_SUMMARY'):
        with open(os.environ['GITHUB_STEP_SUMMARY'], 'a') as summary:
            summary.write('CI recovery adapter compiled the original API1 Quilt probe source bytes with the exact original output SHA-256: ' + digest(probe) + '. One generated compiler-input pin was adapted after the approved content gate; historical entry equivalence remains unknown. Static build only; runtime acceptance remains NOT RUN.\n')


def emit_probe():
    check_sources(require_ready=True)
    receipt = json.loads((REPORT / 'receipt.json').read_text())
    require(receipt['status'] == 'PASS_RECOVERY_ADAPTER_EXACT_ORIGINAL_PROBE', 'No successful exact recovery-build receipt')
    probe = destination(PROBE)
    require(0 < probe.stat().st_size <= EXPECTED['probeMaxBytes'] and digest(probe) == EXPECTED['probeSha256'], 'Probe transport gate failed')
    resource_root = ROOT / 'four-loader/quilt-api-probe/resources'
    resources = {path.relative_to(resource_root).as_posix(): path.read_bytes()
                 for path in resource_root.rglob('*') if path.is_file()}
    with zipfile.ZipFile(probe) as archive:
        require(all(info.filename in resources or info.filename.startswith('dev/infinity/quilttooltipprobe/')
                    and info.filename.endswith('.class') for info in archive.infolist()), 'Unexpected probe payload')
        require(all(archive.read(name) == data for name, data in resources.items()), 'Original probe resources differ')
    encoded = base64.b64encode(probe.read_bytes()).decode('ascii')
    print('BEGIN_ORIGINAL_API1_QUILT_PROBE_BASE64 sha256=' + digest(probe) + ' bytes=' + str(probe.stat().st_size))
    for start in range(0, len(encoded), 120):
        print(encoded[start:start + 120])
    print('END_ORIGINAL_API1_QUILT_PROBE_BASE64')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=['check', 'build', 'emit-probe'])
    parser.add_argument('--fetch', action='store_true')
    parser.add_argument('--require-ready', action='store_true')
    args = parser.parse_args()
    if args.command == 'build':
        build(args.fetch)
    elif args.command == 'emit-probe':
        emit_probe()
    else:
        check_sources(args.require_ready)
        print('PASS source/manifest/URL validation; no download or JVM performed. Closure: ' + LOCK['closureStatus'])


if __name__ == '__main__':
    main()
