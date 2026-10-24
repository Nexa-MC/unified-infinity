#!/usr/bin/env python3
"""Stage and, only in explicit future CI, observe installed graphics and own its collector.

No package installation, downloads, JVMs, namespace or host setting changes.
prepare() writes source/recipes only. execute() is called by the independently
admitted future pair driver; it observes installed files before starting GL.
"""
from __future__ import annotations
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import platform
import re
import signal
import stat
import subprocess
import sys
import time

HERE = Path(__file__).resolve().parent
COLLECTOR = 'work/network-graphics-ci-portable2/graphics_preflight.py'
COLLECTOR_SHA = 'e63fe78404bc6e44c12daacae7bf44aa68d79511b910ed09a2c3d4b25f46da0d'
SUPERVISOR = 'work/network-ci-supervisor-portable3/supervisor.py'
SUPERVISOR_SHA = '2f86c57b6baa693b07064f520d3e2020ba015d07b3bfb29b2ca8a65db8cb1b9b'
MIB = 1024 * 1024
# Must match the hash-pinned supervisor and collector graphics-only contract.
GRAPHICS_RECEIPT_MAX_BYTES = 32 * 1024
ACTIVE_DEADLINE = None
REQUIRED = {'xvfb': '/usr/bin/Xvfb', 'glxinfo': '/usr/bin/glxinfo.x86_64-linux-gnu',
            'software_dri': '/usr/lib/x86_64-linux-gnu/dri/swrast_dri.so',
            'mesa_glx': '/usr/lib/x86_64-linux-gnu/libGLX_mesa.so.0',
            'egl_dispatch': '/usr/lib/x86_64-linux-gnu/libEGL.so.1',
            'mesa_egl': '/usr/lib/x86_64-linux-gnu/libEGL_mesa.so.0'}


def require(ok, message):
    if not ok:
        raise ValueError(message)


def pin(path):
    path = Path(path)
    require(path.is_absolute() and path.resolve() == path and path.is_file()
            and not path.is_symlink(), 'Expected canonical regular input: ' + str(path))
    with path.open('rb') as stream:
        digest = hashlib.file_digest(stream, 'sha256').hexdigest()
    return {'path': str(path), 'bytes': path.stat().st_size, 'sha256': digest}


def pin_loader_cache():
    """Bounded no-follow snapshot of the single generated loader configuration."""
    path = trusted_installed('/etc/ld.so.cache')
    require(str(path) == '/etc/ld.so.cache', 'Loader cache must not be redirected')
    def identity(info):
        return (info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns,
                info.st_ctime_ns, info.st_mode, info.st_uid, info.st_gid)
    fd = os.open(path, os.O_RDONLY | os.O_NONBLOCK | os.O_NOFOLLOW)
    try:
        before = os.fstat(fd)
        require(stat.S_ISREG(before.st_mode) and before.st_uid == 0 and
                not before.st_mode & 0o022 and 0 < before.st_size <= MIB,
                'Untrusted or excessive loader cache')
        with os.fdopen(os.dup(fd), 'rb') as stream:
            data = stream.read(MIB + 1)
        require(len(data) == before.st_size and identity(os.fstat(fd)) == identity(before)
                and identity(path.lstat()) == identity(before),
                'Loader cache changed during bounded read')
        return ({'path': str(path), 'bytes': len(data),
                 'sha256': hashlib.sha256(data).hexdigest()}, identity(before))
    finally:
        os.close(fd)


def write(path, value):
    raw = json.dumps(value, separators=(',', ':')).encode('ascii') + b'\n'
    require(len(raw) <= MIB, 'Graphics evidence exceeds 1 MiB')
    with path.open('xb') as stream:
        stream.write(raw)
    path.chmod(0o444)
    return pin(path)


def prepare(repo_root, consumer_root):
    repo, consumer = Path(repo_root).resolve(strict=True), Path(consumer_root)
    require(consumer.is_absolute() and consumer.resolve() == consumer
            and consumer != repo and not consumer.is_relative_to(repo / 'work/api1')
            and not repo.is_relative_to(consumer), 'Fresh consumer-local graphics root required')
    root = consumer / 'work/network-pair-cold-glue/graphics-production'
    require(not root.exists(), 'Graphics producer already staged')
    sources = [(repo / COLLECTOR, COLLECTOR_SHA), (repo / SUPERVISOR, SUPERVISOR_SHA)]
    for source, expected in sources:
        require(pin(source)['sha256'] == expected, 'Frozen graphics source mismatch: ' + str(source))
    root.mkdir(parents=True)
    staged = {}
    for source, expected in sources:
        target = root / source.name
        with target.open('xb') as stream:
            stream.write(source.read_bytes())
        target.chmod(0o444)
        staged[source.name] = pin(target)
    result = {'schema': 'installed-graphics-producer-v1', 'status': 'SOURCE_STAGED_GRAPHICS_UNRUN',
              'root': str(root), 'producer': pin(HERE / 'graphics_runner.py'),
              'collector': staged['graphics_preflight.py'], 'supervisor': staged['supervisor.py'],
              'observationPath': str(root / 'installed-observations.json'),
              'provenancePath': str(root / 'installed-provenance.json'),
              'lockPath': str(root / 'graphics-lock.json'),
              'destination': str(root / 'actual-preflight'), 'display': ':97',
              'commandRecipe': [sys.executable, str(root / 'graphics_preflight.py'), '--supervisor',
                                str(root / 'supervisor.py'), '--lock', str(root / 'graphics-lock.json'),
                                '--sha256', '<actual-produced-lock-sha256>', '--destination',
                                str(root / 'actual-preflight'), '--execute-reviewed-ci-preflight',
                                '--owner-cutoff', '<driver-owned-absolute-cutoff-json>'],
              'observationCommands': ['/usr/bin/dpkg-query --show --showformat=<exact fields> <observed package>',
                                      '/usr/bin/dpkg-query --search <canonical file and verified alias>',
                                      '/usr/bin/ldd <package-owned recognized ELF input>'],
              'availabilityCallable': 'graphics_runner.availability(plan)',
              'executionCallable': 'graphics_runner.execute(plan, deadline=driver_deadline, owner_cutoff=driver_cutoff)',
              'cleanupCallable': 'graphics_runner.stop(result["handle"])',
              'installedInputsObserved': False, 'graphicsStarted': False, 'gameLaunched': False}
    write(root / 'graphics-producer-plan.json', result)
    return result


def trusted_installed(path, executable=False):
    path = Path(path).resolve(strict=True)
    info = path.stat()
    require(stat.S_ISREG(info.st_mode) and info.st_uid == 0 and not info.st_mode & 0o022,
            'Untrusted installed file ownership/mode: ' + str(path))
    for parent in path.parents:
        data = parent.stat()
        require(data.st_uid == 0 and not data.st_mode & 0o022,
                'Untrusted installed file ancestor: ' + str(parent))
    if executable:
        require(os.access(path, os.X_OK), 'Installed tool is not executable: ' + str(path))
    return path


def availability(plan):
    """Read-only early check before downloads; no package, GL or child process."""
    runner = {'ImageOS': os.environ.get('ImageOS'), 'ImageVersion': os.environ.get('ImageVersion'),
              'machine': platform.machine()}
    missing = []
    if (os.environ.get('GITHUB_ACTIONS') != 'true' or os.getuid() == 0 or
            runner['ImageOS'] != 'ubuntu24' or runner['machine'] != 'x86_64' or
            not re.fullmatch(r'\d{8}\.\d+\.\d+', runner['ImageVersion'] or '')):
        missing.append({'input': 'runner', 'expected': 'Unprivileged official GitHub Ubuntu24 x86_64 runner with exact ImageVersion',
                        'observed': runner})
        return {'status': 'GRAPHICS_AVAILABILITY_BLOCKED', 'missingInputs': missing,
                'graphicsStarted': False, 'packageCommandsStarted': False}
    try:
        source = trusted_installed('/etc/os-release')
        fields = dict(line.split('=', 1) for line in source.read_text().splitlines()
                      if line and not line.startswith('#') and '=' in line)
        distribution = {'id': fields.get('ID', '').strip('"'), 'version_id': fields.get('VERSION_ID', '').strip('"')}
        if distribution != {'id': 'ubuntu', 'version_id': '24.04'}:
            missing.append({'path': '/etc/os-release', 'reason': 'Expected Ubuntu 24.04', 'observed': distribution})
    except (OSError, ValueError) as error:
        missing.append({'path': '/etc/os-release', 'reason': str(error)})
    for name, path in {**REQUIRED, 'dpkg-query': '/usr/bin/dpkg-query', 'ldd': '/usr/bin/ldd',
                       'package-database': '/var/lib/dpkg/status'}.items():
        try:
            trusted_installed(path, name in ('xvfb', 'glxinfo', 'dpkg-query', 'ldd'))
        except (OSError, ValueError) as error:
            missing.append({'path': path, 'reason': str(error)})
    return {'status': 'GRAPHICS_AVAILABILITY_BLOCKED' if missing else 'INSTALLED_GRAPHICS_TOOLS_PRESENT',
            'missingInputs': missing, 'runner': runner, 'packageOwnershipVerified': False,
            'graphicsStarted': False, 'packageCommandsStarted': False}


def query(command, observations, allowed_failure=False):
    timeout=20
    if ACTIVE_DEADLINE is not None:
        require(ACTIVE_DEADLINE>time.monotonic(),'Overall deadline expired during installed graphics observation')
        timeout=min(timeout,ACTIVE_DEADLINE-time.monotonic())
    result = subprocess.run(command, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                            stderr=subprocess.PIPE, text=True, encoding='utf-8', errors='strict',
                            env={'PATH': '/usr/bin:/bin', 'LANG': 'C.UTF-8', 'LC_ALL': 'C.UTF-8'},
                            timeout=timeout, check=False)
    require(len(result.stdout.encode()) + len(result.stderr.encode()) <= MIB,
            'Installed inventory output exceeds bound')
    observations.append({'command': command, 'returncode': result.returncode,
                         'stdout': result.stdout, 'stderr': result.stderr})
    require(allowed_failure or result.returncode == 0,
            'Installed inventory command failed: ' + repr(command) + ': ' + result.stderr.strip())
    return result


def parse_ldd(text):
    require('not found' not in text and 'not a dynamic executable' not in text,
            'Missing native dependency in ldd output: ' + text.strip())
    paths = set()
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith('linux-vdso.'):
            continue
        match = re.fullmatch(r'(?:\S+\s+=>\s+)?(/\S+)\s+\(0x[0-9a-fA-F]+\)', line)
        require(match is not None, 'Unrecognized native dependency line: ' + line)
        paths.add(match.group(1))
    require(paths, 'No native dependency paths observed')
    return paths



# Ubuntu Noble libc6's no-rename usrmerge diversion. This is metadata only:
# it never establishes ownership, and the diverted destination need not exist.
LIBC_LOADER_DIVERSION = ('/lib64/ld-linux-x86-64.so.2',
                        '/lib64/ld-linux-x86-64.so.2.usr-is-merged', 'libc6')


def parse_diversion_database(text):
    """Parse dpkg's installed triples, rejecting malformed/ambiguous records."""
    require(len(text.encode('utf-8')) <= MIB, 'Diversion database exceeds bound')
    lines = text.splitlines()
    require(len(lines) % 3 == 0, 'Malformed diversion database triples')
    records, paths = [], set()
    for index in range(0, len(lines), 3):
        source, target, package = lines[index:index + 3]
        require(all(p.startswith('/') and str(Path(p)) == p and
                    '..' not in Path(p).parts and not any(ord(c) < 32 for c in p)
                    for p in (source, target)) and source != target,
                'Malformed diversion database path')
        require(package == ':' or re.fullmatch(r'[a-z0-9][a-z0-9+.-]+', package),
                'Malformed diversion database package')
        require(source not in paths and target not in paths,
                'Ambiguous diversion database paths')
        paths.update((source, target))
        records.append((source, target, package))
    return records


def parse_package_search(text, canonical, candidate, load_diversions):
    """Real dpkg-query parser; diversion annotations cannot grant ownership."""
    names, annotations = set(), {}
    for line in text.splitlines():
        if line.startswith('diversion '):
            match = re.fullmatch(r'diversion by ([a-z0-9][a-z0-9+.-]+) (from|to): (/\S+)', line)
            require(match is not None, 'Malformed or local diversion annotation: ' + line)
            package, direction, path = match.groups()
            require(direction not in annotations, 'Duplicate diversion annotation')
            annotations[direction] = (package, path)
        else:
            require(': ' in line, 'Ambiguous package ownership: ' + line)
            name, owned = line.rsplit(': ', 1)
            require(re.fullmatch(r'[a-z0-9][a-z0-9+.-]+(?::(?:amd64|all))?', name)
                    and Path(owned).is_absolute() and Path(owned).exists()
                    and Path(owned).resolve(strict=True) == canonical,
                    'Ambiguous canonical package owner')
            names.add(name)
    diversion = None
    if annotations:
        require(set(annotations) == {'from', 'to'}, 'Unpaired diversion annotation')
        package, source = annotations['from']
        to_package, target = annotations['to']
        diversion = (source, target, package)
        require(package == to_package and diversion == LIBC_LOADER_DIVERSION,
                'Unapproved installed diversion')
        require(candidate == source and Path(source).exists()
                and Path(source).resolve(strict=True) == canonical,
                'Diversion does not identify queried canonical file')
        records = load_diversions()
        require(records.count(diversion) == 1 and
                all(record == diversion or not ({source, target} & set(record[:2]))
                    for record in records), 'Unverified or ambiguous installed diversion')
    return names, diversion


def resolve_package_owner(canonical, alias, search, package, load_diversions):
    # Ubuntu usrmerge databases may retain /lib paths. Only query an alias
    # after verifying that its actual target is the same canonical file.
    aliases = [str(canonical)]
    if alias is not None and Path(alias).resolve(strict=True) == canonical:
        aliases.append(str(alias))
    if str(canonical).startswith('/usr/lib/'):
        candidate = Path(str(canonical)[4:])
        if candidate.exists() and candidate.resolve(strict=True) == canonical:
            aliases.append(str(candidate))
    names, diversions = set(), set()
    for candidate in dict.fromkeys(aliases):
        found = search(candidate)
        if found.returncode:
            continue
        parsed, diversion = parse_package_search(found.stdout, canonical, candidate, load_diversions)
        names.update(package(name) for name in parsed)
        if diversion is not None:
            diversions.add(diversion)
    require(len(names) == 1, 'Missing/ambiguous owner for installed input: ' + str(canonical))
    identity = names.pop()
    if diversions:
        require(diversions == {LIBC_LOADER_DIVERSION} and identity.startswith('libc6:amd64='),
                'Diversion package differs from unique installed owner')
    return identity


def observe(plan):
    """Actual installed-file observations; caller has already admitted future CI."""
    root = Path(plan['root'])
    raw = []
    runner = {'ImageOS': os.environ.get('ImageOS'), 'ImageVersion': os.environ.get('ImageVersion'),
              'machine': platform.machine()}
    require(os.environ.get('GITHUB_ACTIONS') == 'true' and os.getuid() > 0,
            'Explicit unprivileged GitHub CI execution required')
    require(runner['ImageOS'] == 'ubuntu24' and runner['machine'] == 'x86_64' and
            re.fullmatch(r'\d{8}\.\d+\.\d+', runner['ImageVersion'] or ''),
            'Actual official Ubuntu24 runner image is required')
    os_release = trusted_installed('/etc/os-release')
    distribution_text = os_release.read_text()
    fields = dict(line.split('=', 1) for line in distribution_text.splitlines()
                  if line and not line.startswith('#') and '=' in line)
    distribution = {'id': fields.get('ID', '').strip('"'),
                    'version_id': fields.get('VERSION_ID', '').strip('"')}
    require(distribution == {'id': 'ubuntu', 'version_id': '24.04'}, 'Installed distribution differs')
    dpkg = trusted_installed('/usr/bin/dpkg-query', True)
    ldd = trusted_installed('/usr/bin/ldd', True)
    database = trusted_installed('/var/lib/dpkg/status')
    before = pin(database)
    # ldconfig output is generated host state, never a package-owned library.
    loader_cache = trusted_installed('/etc/ld.so.cache')
    require(str(loader_cache) == '/etc/ld.so.cache', 'Loader cache must not be redirected')
    cache_before, cache_identity = pin_loader_cache()
    packages, ownership = {}, {}
    diversion_state = {}

    def load_diversions():
        if not diversion_state:
            path = trusted_installed('/var/lib/dpkg/diversions')
            before = pin(path)
            with path.open('rb') as stream:
                data = stream.read(MIB + 1)
            require(len(data) <= MIB, 'Diversion database exceeds bound')
            records = parse_diversion_database(data.decode('utf-8', errors='strict'))
            require(pin(path) == before, 'Diversion database changed while reading')
            diversion_state.update(path=path, before=before, records=records)
        return diversion_state['records']

    def package(name):
        result = query([str(dpkg), '--show', '--showformat=${Package}\t${Version}\t${Architecture}\t${db:Status-Status}\n', name], raw)
        rows = [line.split('\t') for line in result.stdout.splitlines()]
        require(len(rows) == 1 and len(rows[0]) == 4 and rows[0][3] == 'installed',
                'Missing/ambiguous installed package: ' + name)
        name, version, architecture, _ = rows[0]
        require(re.fullmatch('[a-z0-9][a-z0-9+.-]+', name) and architecture in ('amd64', 'all')
                and re.fullmatch('[A-Za-z0-9.+:~-]{1,128}', version), 'Invalid installed package identity')
        row = {'package': name, 'version': version, 'architecture': architecture}
        identity = name + ':' + architecture + '=' + version
        packages[identity] = row
        return identity

    def owner(canonical, alias=None):
        identity = resolve_package_owner(canonical, alias,
            lambda candidate: query([str(dpkg), '--search', candidate], raw, allowed_failure=True),
            package, load_diversions)
        ownership[str(canonical)] = identity
        return identity

    # Verify the inventory tools' actual package identities before allowing ldd
    # to inspect only recognized, root-owned distro ELF files.
    require(owner(dpkg).startswith('dpkg:'), 'Unexpected dpkg-query owner')
    require(owner(ldd).startswith('libc-bin:'), 'Unexpected ldd owner')
    ownership.clear()  # Inventory tool pins remain in observations, not GL inputs.
    for name in ('xvfb', 'mesa-utils-bin', 'libgl1-mesa-dri'):
        package(name)
    required = REQUIRED
    missing = [{'path': path, 'reason': 'Required installed graphics input is absent'}
               for path in required.values() if not Path(path).exists()]
    if missing:
        return {'status': 'MISSING_INSTALLED_GRAPHICS_INPUTS', 'missingInputs': missing,
                'graphicsStarted': False, 'gameLaunched': False, 'downloadsStarted': False}
    roots = {name: trusted_installed(path, name in ('xvfb', 'glxinfo')) for name, path in required.items()}
    require(roots['xvfb'].name == 'Xvfb' and roots['glxinfo'].name == 'glxinfo.x86_64-linux-gnu',
            'Unexpected official graphics tool target')
    files = set(roots.values())
    for name, path in roots.items():
        identity = owner(path, required.get(name))
        expected_owner = {'xvfb': 'xvfb:', 'glxinfo': 'mesa-utils-bin:',
                          'egl_dispatch': 'libegl1:', 'mesa_egl': 'libegl-mesa0:'}.get(name)
        if expected_owner:
            require(identity.startswith(expected_owner), 'Unexpected graphics tool package: ' + str(path))
        with path.open('rb') as stream:
            magic = stream.read(4)
        require(magic == b'\x7fELF', 'ldd input is not a recognized installed ELF: ' + str(path))
        linked = parse_ldd(query([str(ldd), str(path)], raw).stdout)
        for alias in linked:
            canonical = trusted_installed(alias)
            owner(canonical, alias)
            files.add(canonical)
    require(len(files) + 1 <= 128, 'Installed native closure exceeds frozen collector pin bound')
    files.add(loader_cache)
    require(len(files) + 1 <= 128, 'Installed native closure exceeds frozen collector pin bound')
    actual = [pin(path) for path in sorted(files)]
    require(pin_loader_cache() == (cache_before, cache_identity),
            'Loader cache changed during installed observation')
    require(next(row for row in actual if row['path'] == '/etc/ld.so.cache') == cache_before,
            'Loader cache pin differs from stable snapshot')
    require(pin(database) == before, 'Package database changed during installed observation')
    if diversion_state:
        require(pin(trusted_installed('/var/lib/dpkg/diversions')) == diversion_state['before'],
                'Diversion database changed during installed observation')
    observation = {'schema': 1, 'status': 'ACTUAL_INSTALLED_GRAPHICS_OBSERVATIONS',
                   'distribution': distribution, 'osRelease': pin(os_release), 'osReleaseText': distribution_text,
                   'runner': runner, 'packageDatabaseBeforeAfter': before,
                   'inventoryTools': [pin(dpkg), pin(ldd)], 'queries': raw, 'files': actual,
                   'diversionDatabaseBeforeAfter': diversion_state.get('before'),
                   'generatedLoaderCacheBeforeAfter': cache_before,
                   'producer': plan['producer'], 'archiveSignaturesVerified': False}
    evidence = write(Path(plan['observationPath']), observation)
    provenance = {'schema': 2, 'status': 'OBSERVED_INSTALLED_PACKAGES',
                  'observation_reference': evidence['path'] + '#sha256=' + evidence['sha256'],
                  'distribution': distribution, 'runner': runner,
                  'packages': sorted(packages.values(), key=lambda r: (r['package'], r['architecture'])),
                  'file_packages': {r['path']: ownership[r['path']] for r in actual if r['path'] != str(loader_cache)},
                  'generated_config': {'/etc/ld.so.cache': {'kind': 'root-owned-ldconfig-cache',
                                                        'sha256': cache_before['sha256']}},
                  'file_sha256': {r['path']: r['sha256'] for r in actual}}
    provenance_pin = write(Path(plan['provenancePath']), provenance)
    lock = {'schema': 'network-graphics-lock-v1', 'status': 'COMPLETE_REVIEWED',
            'review_reference': 'Reviewed producer sha256=' + plan['producer']['sha256'] + '; ' + evidence['path'],
            'expected_runner': runner, 'display': plan['display'],
            'tools': {name: str(roots[name]) for name in ('xvfb', 'glxinfo')},
            'inputs': [*actual, provenance_pin], 'package_provenance': provenance_pin['path']}
    validate_receipt_capacity(lock['inputs'])
    lock_pin = write(Path(plan['lockPath']), lock)
    return {'status': 'OBSERVED_INSTALLED_INPUTS_READY_GRAPHICS_UNRUN', 'lock': lock_pin,
            'observations': evidence, 'missingInputs': [], 'graphicsStarted': False}


def validate_receipt_capacity(inputs):
    # Reserve sufficient room for genuine measured renderer/process fields.
    estimated_bytes = len(json.dumps({r['path']: r['sha256'] for r in inputs})) + 1300
    print('Graphics receipt capacity (not readiness): inputs=%d estimated_bytes=%d limit=%d' %
          (len(inputs), estimated_bytes, GRAPHICS_RECEIPT_MAX_BYTES), flush=True)
    require(estimated_bytes < GRAPHICS_RECEIPT_MAX_BYTES,
            'Observed graphics closure cannot fit frozen 32768-byte runtime receipt')


def stop(handle):
    """Stop only this unreaped direct collector child; frozen collector owns Xvfb."""
    process = handle['process']
    try:
        if process.poll() is None:
            signal.pidfd_send_signal(handle['pidfd'], signal.SIGTERM)
            try:
                process.wait(timeout=20)
            except subprocess.TimeoutExpired:
                # A hard kill could orphan its Xvfb. Report rather than claim
                # cleanup or signal a PID obtained from imported evidence.
                raise RuntimeError('Owned collector did not complete bounded cleanup')
        path = Path(handle['lifecyclePath'])
        require(path.is_file(), 'Collector exited without lifecycle evidence')
        lifecycle = json.loads(path.read_text())
        require(type(lifecycle.get('schema')) is int and lifecycle['schema'] == 1 and
                lifecycle.get('pair_acceptance') is False and
                lifecycle.get('status') in ('STOPPED_BY_ORCHESTRATOR', 'FAILED') and
                not lifecycle.get('cleanup_errors'), 'Collector lifecycle reports cleanup failure')
        require(lifecycle.get('owner_cutoff') == handle.get('ownerCutoff') and
                type(handle.get('ownerCutoff')) is dict and lifecycle.get('cleanup_before_cutoff') is True,
                'Collector cleanup cutoff proof differs or expired')
        cleanup = lifecycle.get('cleanup')
        require(isinstance(cleanup, dict) and cleanup.get('collector_pid') == process.pid and
                cleanup.get('all_reaped') is True, 'Collector lacks explicit owned-child cleanup proof')
        children = cleanup.get('children')
        expected = cleanup.get('expected_children')
        require(type(expected) is int and 0 <= expected <= 2 and isinstance(children, list) and
                len(children) == expected, 'Incomplete graphics child cleanup proof')
        require(lifecycle['status'] != 'STOPPED_BY_ORCHESTRATOR' or expected == 2,
                'Successful preflight must clean both owned children')
        require(all(isinstance(row, dict) and set(row) == {'pid', 'reaped', 'returncode'} and
                    type(row['pid']) is int and row['pid'] > 0 and row['reaped'] is True and
                    type(row['returncode']) is int for row in children) and
                len({row['pid'] for row in children}) == len(children),
                'Invalid graphics child cleanup proof')
        return {'status': 'GRAPHICS_COLLECTOR_CLEANED', 'lifecycle': pin(path)}
    finally:
        # Retain exact ownership handles if bounded cleanup did not complete,
        # allowing the caller to report/continue cleanup without imported PIDs.
        if process.poll() is not None:
            os.close(handle['pidfd'])
            handle['log'].close()


def execute(plan,deadline=None,interrupt_check=None,owner_cutoff=None):
    """Explicit future-CI operation; no execution occurs when imported/prepared."""
    global ACTIVE_DEADLINE
    ACTIVE_DEADLINE=deadline
    def check_stops():
        if interrupt_check is not None:interrupt_check()
    check_stops()
    for key in ('producer', 'collector', 'supervisor'):
        require(pin(Path(plan[key]['path'])) == plan[key], 'Staged graphics source changed: ' + key)
    require(hasattr(os, 'pidfd_open') and hasattr(signal, 'pidfd_send_signal'), 'Owned collector requires pidfd support')
    try:
        observed = observe(plan)
    except (OSError, ValueError, subprocess.SubprocessError) as error:
        return {'status': 'INSTALLED_GRAPHICS_INPUTS_BLOCKED', 'missingInputs': [{'reason': str(error)}],
                'graphicsStarted': False, 'gameLaunched': False, 'downloadsStarted': False}
    if observed['missingInputs']:
        return observed
    spec = importlib.util.spec_from_file_location('frozen_graphics_preflight', plan['collector']['path'])
    collector = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(collector)
    supervisor = collector.load_supervisor(plan['supervisor']['path'])
    lock = json.loads(Path(plan['lockPath']).read_text())
    lease = collector.OwnerDeadline(owner_cutoff)
    require(type(deadline) in (int, float) and owner_cutoff['work_monotonic'] == deadline + 90,
            'Graphics cutoff differs from driver work deadline')
    collector.validate_lock(lock, supervisor)
    lease.check()
    command = [sys.executable, plan['collector']['path'], '--supervisor', plan['supervisor']['path'],
               '--lock', plan['lockPath'], '--sha256', observed['lock']['sha256'],
               '--destination', plan['destination'], '--execute-reviewed-ci-preflight',
               '--owner-cutoff', json.dumps(owner_cutoff, sort_keys=True, separators=(',', ':'))]
    environment = {'PATH': '/usr/bin:/bin', 'LANG': 'C.UTF-8', 'LC_ALL': 'C.UTF-8',
                   'GITHUB_ACTIONS': 'true', 'ImageOS': lock['expected_runner']['ImageOS'],
                   'ImageVersion': lock['expected_runner']['ImageVersion']}
    check_stops()
    process=None;pidfd=None;log=None;handle=None
    try:
        log = (Path(plan['root']) / 'collector.log').open('xb')
        # The driver defers its handled signals until this direct child and its
        # ownership descriptor have been retained. Never block inherited masks.
        lease.check()
        process = subprocess.Popen(command, cwd=plan['root'], env=environment, stdin=subprocess.DEVNULL,
                                   stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
        pidfd = os.pidfd_open(process.pid)
        destination = Path(plan['destination'])
        handle = {'process': process, 'pidfd': pidfd, 'log': log,
                  'lifecyclePath': str(destination / 'lifecycle.json'), 'ownerCutoff': dict(owner_cutoff)}
        check_stops()
        ready_deadline = min(time.monotonic() + 60, deadline if deadline is not None else float('inf'))
        ready_path = destination / 'ready.json'
        while not ready_path.exists():
            check_stops()
            require(process.poll() is None, 'Graphics collector exited before readiness; see collector.log')
            require(time.monotonic() < ready_deadline, 'Graphics collector readiness timeout')
            require(log.tell() <= MIB, 'Collector launcher log exceeded bound')
            time.sleep(0.1)
        ready = supervisor.decode_json(supervisor.read_bounded(ready_path, MIB), MIB)
        require(ready.get('status') == 'GRAPHICS_PREFLIGHT_READY' and ready.get('collector_pid') == process.pid
                and ready.get('pair_acceptance') is False, 'Collector readiness identity differs')
        require(ready.get('maximum_lifetime_seconds') == collector.MAX_LIFETIME == 42 * 60,
                'Collector lifetime receipt differs from the shared work budget')
        require(ready.get('owner_cutoff') == handle['ownerCutoff'], 'Collector owner cutoff receipt differs')
        lease.check()
        supervisor.verify_graphics(ready, supervisor.Proc())
        return {'status': 'GRAPHICS_PREFLIGHT_READY', 'readyPath': str(ready_path),
                'ready': ready, 'readyPin': pin(ready_path), 'observedInputs': observed,
                'handle': handle, 'gameLaunched': False, 'maximumLifetimeSeconds': ready['maximum_lifetime_seconds']}
    except BaseException as error:
        try:
            if process is not None:
                if pidfd is not None:
                    # Construct from retained ownership even if interruption fell
                    # between descriptor acquisition and handle construction.
                    if handle is None:
                        handle={'process':process,'pidfd':pidfd,'log':log,
                                'lifecyclePath':str(Path(plan['destination'])/'lifecycle.json'), 'ownerCutoff':dict(owner_cutoff)}
                    error.graphics_cleanup=stop(handle)
                else:
                    # No imported PID: Popen still owns this unreaped child.
                    if process.poll() is None:process.terminate()
                    code=process.wait(timeout=20)
                    error.graphics_cleanup={'status':'GRAPHICS_COLLECTOR_REAPED_BEFORE_READY',
                                            'exitCode':code}
        except BaseException as cleanup_error:
            error.graphics_cleanup={'status':'GRAPHICS_CLEANUP_FAILED',
                                    'failure':type(cleanup_error).__name__+': '+str(cleanup_error)}
        finally:
            if pidfd is None and log is not None:log.close()
        raise
