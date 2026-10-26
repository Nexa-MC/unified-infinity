"""Serial exact-pin restoration into the existing fresh CI consumer. No JVM.

Only absent (404/410) locked URLs may fall through. Access denials, redirects
outside the original host set, hash mismatches and other errors stop the stage.
"""
from pathlib import Path, PurePosixPath
import hashlib
import json
import os
import shutil
import signal
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request

CORE_SHA = '43ac0ce038cb00da23f0ae625f64c4b1bb83251c82ee2269b6ae698f50d4389b'
PRODUCT_SHA = '3df7f63664e36a374f7beee8e258a96ec8e1620dc361843107d25749e3a7aa03'
FML_SHA = '9471fe1033f2af3811f8307b96b5b1bdbbcb6c11a8ee90e8d33c7bb97485a7f4'
QSL = {'docs/four-loader/quilt/upstream/qsl_base-alpha5.jar',
       'docs/four-loader/quilt/upstream/lifecycle_events-alpha5.jar'}


def require(ok, message):
    if not ok:
        raise ValueError(message)


def sha(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def local(root, relative):
    p = PurePosixPath(relative)
    require(relative and not p.is_absolute() and '..' not in p.parts and str(p) == relative,
            'Noncanonical relative input')
    target = root.joinpath(*p.parts)
    require(not any(p.is_symlink() for p in [target, *target.parents]), 'Redirected input')
    require(target.resolve().is_relative_to(root), 'Input escapes consumer')
    return target


def checked(path, row):
    require(path.is_file() and not path.is_symlink(), 'Missing regular input: ' + str(path))
    require('bytes' not in row or path.stat().st_size == row['bytes'],
            'Exact input size mismatch: ' + str(path))
    algorithms = [name for name in ('sha256', 'sha1') if name in row]
    require(algorithms, 'Original digest required')
    for name in algorithms:
        with path.open('rb') as stream:
            actual = hashlib.file_digest(stream, name).hexdigest()
        require(actual == row[name], 'Exact input ' + name + ' mismatch: ' + str(path))
    return {'path': str(path), 'bytes': path.stat().st_size, 'sha256': sha(path)}


def read_lock(path, expected):
    checked(path, {'sha256': expected})
    return json.loads(path.read_text())


def remaining(deadline):
    left = deadline - time.monotonic()
    if left <= 0:
        raise TimeoutError('Core restoration deadline expired')
    return left


def valid_url(url, hosts):
    p = urllib.parse.urlsplit(url)
    require(p.scheme == 'https' and p.hostname in hosts and not p.username and not p.password
            and p.port in (None, 443) and not p.fragment, 'Unapproved locked URL/redirect')
    return url


class Redirects(urllib.request.HTTPRedirectHandler):
    def __init__(self, hosts):
        self.hosts = hosts

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        valid_url(newurl, self.hosts)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def download(row, target, hosts, deadline):
    opener = urllib.request.build_opener(Redirects(hosts))
    target.parent.mkdir(parents=True, exist_ok=True)
    for url in row['urls']:
        valid_url(url, hosts)
        fd, name = tempfile.mkstemp(prefix='.restore-', dir=target.parent)
        temp = Path(name)
        try:
            with os.fdopen(fd, 'wb') as out:
                try:
                    response = opener.open(url, timeout=min(20, remaining(deadline)))
                except urllib.error.HTTPError as error:
                    if error.code in (404, 410):
                        continue
                    raise
                with response:
                    valid_url(response.geturl(), hosts)
                    require(response.status == 200, 'Unexpected HTTP status')
                    size = 0
                    while True:
                        remaining(deadline)
                        data = response.read(65536)
                        if not data:
                            break
                        size += len(data)
                        require(size <= row['bytes'], 'Download exceeds original size')
                        out.write(data)
            checked(temp, row)
            require(not target.exists(), 'Destination appeared during restoration')
            os.link(temp, target)  # Atomic no-overwrite publication on this filesystem.
            return {'method': 'original-url', 'url': url, **checked(target, row)}
        finally:
            temp.unlink(missing_ok=True)
    raise FileNotFoundError('All original URLs absent: ' + row['path'])


def seed(row, api, index, hosts, deadline, allow_download=True):
    remaining(deadline)
    target = local(api, row['path'])
    if target.exists():
        result = {'method': 'existing-exact', **checked(target, row)}
    elif row['sha256'] in index:
        source = index[row['sha256']]
        checked(source, row)
        target.parent.mkdir(parents=True, exist_ok=True)
        fd, name = tempfile.mkstemp(prefix='.restore-', dir=target.parent)
        temp = Path(name)
        try:
            with os.fdopen(fd, 'wb') as out, source.open('rb') as src:
                shutil.copyfileobj(src, out, 65536)
            checked(temp, row)
            os.link(temp, target)
            result = {'method': 'same-root-exact-copy', 'source': str(source), **checked(target, row)}
        finally:
            temp.unlink(missing_ok=True)
    else:
        require(allow_download, 'Missing same-root FML input: ' + row['path'])
        result = download(row, target, hosts, deadline)
    index[row['sha256']] = target
    return result


def _restore(repo, consumer, deadline):
    api = local(consumer, 'work/api1')
    core_path = repo / 'work/network-pair-cold-glue/profiles/ffapi-core-dependency-lock.json'
    product_path = repo / 'work/network-pair-cold-glue/product-input-lock.json'
    fml_path = local(api, 'source-workspace/fml-unified/provenance/compile-classpath-lock.json')
    core = read_lock(core_path, CORE_SHA)
    product = read_lock(product_path, PRODUCT_SHA)
    fml = read_lock(fml_path, FML_SHA)
    require(len(core['artifacts']) == 706 and len(fml['artifacts']) == 116, 'Original lock counts changed')
    extras = [r for r in product['artifacts'] if r['path'] in QSL or
              (r.get('phase') == 'snapshot' and '/1.2.1-SNAPSHOT/' in r['path'])]
    require(len(extras) == 6 and {r['path'] for r in extras if r['path'] in QSL} == QSL,
            'Exact QSL and snapshot aliases required')
    wanted = {r['sha256'] for r in [*core['artifacts'], *extras, *fml['artifacts']]}
    index = {}
    # Search only the same consumer's dependency stores; never historical caches.
    for rel in ('ci/runtime-maven', 'run/client-dev/libraries', 'run/neoforge-native/libraries',
                'source-workspace/pinned-build-maven', 'source-workspace/pinned-maven'):
        base = local(api, rel)
        if not base.exists():
            continue
        for path in sorted(base.rglob('*')):
            remaining(deadline)
            require(not path.is_symlink(), 'Redirected dependency store')
            if path.is_file():
                digest = sha(path)
                if digest in wanted:
                    index.setdefault(digest, path)
    results = []
    for row in core['artifacts']:
        results.append(seed(row, api, index, set(core['allowedHosts']), deadline))
    for row in extras:
        results.append(seed(row, api, index, set(product['allowedHosts']), deadline))
    fml_results = [seed(row, api, index, set(), deadline, False) for row in fml['artifacts']]
    # Final immutable input verification, not merely successful download reports.
    for row in [*core['artifacts'], *extras, *fml['artifacts']]:
        remaining(deadline)
        checked(local(api, row['path']), row)
    return {'schema': 'forge-same-root-input-restoration-v1', 'consumerRoot': str(consumer),
            'locks': [checked(core_path, {'sha256': CORE_SHA}),
                      checked(product_path, {'sha256': PRODUCT_SHA}),
                      checked(fml_path, {'sha256': FML_SHA})],
            'coreCount': 706, 'aliasAndQslCount': 6, 'fmlCount': 116,
            'restored': results, 'fml': fml_results, 'allInputsVerified': True,
            'jvmStarted': False, 'gameLaunched': False}


def restore(repo, consumer, deadline_monotonic):
    """Restore originals serially; caller owns invocation and eventual text receipt.

    SIGALRM bounds slow HTTP reads and hashing as well as connection setup. Must
    run in the main thread, without another active real-time timer.
    """
    repo = Path(repo).absolute()
    consumer = Path(consumer).absolute()
    require(repo.resolve() == repo and consumer.resolve() == consumer and consumer.is_dir(),
            'Canonical existing consumer and repo required')
    require(signal.getitimer(signal.ITIMER_REAL) == (0.0, 0.0), 'Existing deadline timer must be owned by caller')
    def expired(_sig, _frame):
        raise TimeoutError('Core restoration deadline expired')
    left = remaining(deadline_monotonic)
    previous = signal.signal(signal.SIGALRM, expired)
    signal.setitimer(signal.ITIMER_REAL, left)
    try:
        return _restore(repo, consumer, deadline_monotonic)
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
        signal.signal(signal.SIGALRM, previous)
