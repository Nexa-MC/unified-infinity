#!/usr/bin/env python3
"""Source-only preflight locally; network/JVM execution guarded for reviewed CI."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import tarfile
import time
import urllib.parse
import urllib.request

ROOT = Path(__file__).resolve().parent
BRANCH = 'diagnostic/qsl-receiver-contract-20261005-a'
REPO = 'Nexa-MC/unified-infinity'

def require(value, message):
    if not value:
        raise SystemExit(message)

def identity(path):
    data = path.read_bytes()
    return {'sha256': hashlib.sha256(data).hexdigest(), 'bytes': len(data)}

def check():
    manifest = json.loads((ROOT / 'source-manifest.json').read_text())
    actual = {str(p.relative_to(ROOT)) for p in ROOT.rglob('*') if p.is_file() and '.run' not in p.relative_to(ROOT).parts and p.name != 'source-manifest.json'}
    require(actual == set(manifest['files']), 'Source file set differs from reviewed manifest')
    for name, pin in manifest['files'].items():
        p = ROOT / name
        require(not p.is_symlink() and identity(p) == pin, 'Source identity mismatch: ' + name)
    provenance = json.loads((ROOT / 'source-provenance.json').read_text())
    for item in provenance['unchanged_upstream']:
        require(identity(ROOT / item['path']) == {k: item[k] for k in ('sha256', 'bytes')}, 'Original alpha.5 bytes changed')
    lock = json.loads((ROOT / 'dependency-lock.json').read_text())
    require(len(lock['artifacts']) == 4, 'Expected only JDK and three library inputs')
    require(sum(x['bytes'] for x in lock['artifacts']) < 232_000_000, 'Download ceiling exceeded')
    for pin in lock['artifacts']:
        u = urllib.parse.urlparse(pin['url'])
        require(u.scheme == 'https' and u.hostname in lock['allowed_download_hosts'], 'Unexpected input origin')
        require(Path(pin['path']).name == pin['path'], 'Invalid dependency filename')
        require(len(pin['sha256']) == 64 and pin['bytes'] > 0, 'Incomplete input pin')
    print('SOURCE_PREFLIGHT_PASS: source identities and four dependency pins; no Java or network executed')
    return lock

class Redirects(urllib.request.HTTPRedirectHandler):
    def __init__(self, allowed):
        self.allowed = allowed
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        url = urllib.parse.urlparse(newurl)
        require(url.scheme == 'https' and url.hostname in self.allowed, 'Unexpected download redirect')
        return super().redirect_request(req, fp, code, msg, headers, newurl)

def run():
    require(os.environ.get('GITHUB_ACTIONS') == 'true', 'Execution is restricted to reviewed GitHub Actions')
    require(os.environ.get('GITHUB_REPOSITORY') == REPO and os.environ.get('GITHUB_REF') == 'refs/heads/' + BRANCH and os.environ.get('GITHUB_EVENT_NAME') == 'push', 'Wrong repository/ref/event')
    lock = check()
    work = ROOT / '.run'
    require(not work.exists(), 'Expected fresh ephemeral run directory; no cache reuse')
    work.mkdir()
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), Redirects(lock['allowed_download_hosts']))
    deadline = time.monotonic() + 300
    for pin in lock['artifacts']:
        target = work / pin['path']
        digest = hashlib.sha256()
        count = 0
        request = urllib.request.Request(pin['url'], headers={'User-Agent': 'qsl-receiver-contract-ci/1'})
        with opener.open(request, timeout=45) as response, target.open('xb') as out:
            while chunk := response.read(1024 * 1024):
                require(time.monotonic() <= deadline, 'Total download timeout')
                count += len(chunk)
                require(count <= pin['bytes'], 'Download exceeds exact byte ceiling')
                digest.update(chunk)
                out.write(chunk)
        require(count == pin['bytes'] and digest.hexdigest() == pin['sha256'], 'Downloaded input identity mismatch: ' + pin['path'])
        print('INPUT_VERIFIED: ' + pin['path'] + ' sha256=' + pin['sha256'] + ' bytes=' + str(count))
    jdk = work / 'jdk'
    jdk.mkdir()
    with tarfile.open(work / 'jdk21.tar.gz', 'r:gz') as archive:
        entries = archive.getmembers()
        require(len(entries) <= 10000 and sum(x.size for x in entries) <= 700_000_000, 'Toolchain extraction ceiling exceeded')
        archive.extractall(jdk, filter='data')
    candidates = list(jdk.glob('*/bin/javac'))
    require(len(candidates) == 1, 'Expected one pinned JDK')
    java_home = candidates[0].parent.parent
    require('JAVA_VERSION="21.0.12.1"' in (java_home / 'release').read_text(), 'Unexpected JDK release')
    classes = work / 'classes'
    classes.mkdir()
    classpath = os.pathsep.join(str(work / x['path']) for x in lock['artifacts'] if x['path'].endswith('.jar'))
    sources = sorted(str(p) for folder in ('src', 'upstream', 'test-doubles') for p in (ROOT / folder).rglob('*.java'))
    require(len(sources) == 12, 'Expected 3 candidate, 2 test, 2 original and 5 double Java sources')
    subprocess.run([str(java_home / 'bin/javac'), '-J-Xmx256m', '--release', '21', '-proc:none', '-encoding', 'UTF-8', '-classpath', classpath, '-d', str(classes), *sources], check=True, timeout=120)
    for test in ('QslPlayReceiverContractTest', 'QslOriginalCoreDifferentialTest'):
        subprocess.run([str(java_home / 'bin/java'), '-Xmx256m', '-ea', '-classpath', str(classes) + os.pathsep + classpath, 'org.sinytra.connector.network.qsl.internal.' + test], check=True, timeout=60)
    print('QSL_RECEIVER_CONTRACT_PASS: candidate 24 cases + 10 unchanged-original-core differential scenarios; native runtime untested')
    summary = os.environ.get('GITHUB_STEP_SUMMARY')
    if summary:
        with open(summary, 'a') as out:
            out.write('Passed: candidate 24 source contracts and 10 differential scenarios against unchanged QSL alpha.5 GlobalReceiverRegistry/AbstractNetworkAddon. External Minecraft IDs, phase/side, reserved IDs and payload lookup are test doubles. No Minecraft/Netty/ABI/codec/wire/loader acceptance. No binary upload or Actions cache.\n')

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('command', choices=['check', 'run'])
    command = parser.parse_args().command
    check() if command == 'check' else run()
