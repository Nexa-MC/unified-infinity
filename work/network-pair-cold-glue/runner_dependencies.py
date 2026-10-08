"""Reviewed seven-package Ubuntu closure; no execution or mutation on import.

Native APT checks the whole actual status plus only pinned missing additions.
APT never resolves, downloads, installs, or changes system configuration here.
"""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import time
import urllib.request

import graphics_runner as graphics
import bounded_process

HERE = Path(__file__).resolve().parent
PACKAGE = 'mesa-utils-bin'
VERSION = '9.0.0-2'
CANONICAL = '/usr/bin/glxinfo.x86_64-linux-gnu'
STATUS = Path('/var/lib/dpkg/status')
MAX_PACKAGES = 7
MAX_BYTES = 390800
SETUP_SECONDS = 180
METADATA_PINS = {
    'ubuntu-graphics-candidates.json': 'fdcdd96f2c270b3741d84e80cc1a42562b60da7e42105c808361ad4691c804f5',
    'ubuntu-graphics.Packages': '0f936bae8be7cb6a5a128fe079c950d6b3efad923c05b7c112c40fc081072d35',
}
PACKAGE_PATHS = {
    'libdecor-0-0': '/usr/lib/x86_64-linux-gnu/libdecor-0.so.0',
    'libegl-mesa0': '/usr/lib/x86_64-linux-gnu/libEGL_mesa.so.0',
    'libegl1': '/usr/lib/x86_64-linux-gnu/libEGL.so.1',
    'libgles2': '/usr/lib/x86_64-linux-gnu/libGLESv2.so.2',
    'libxcb-xkb1': '/usr/lib/x86_64-linux-gnu/libxcb-xkb.so.1',
    'libxkbcommon-x11-0': '/usr/lib/x86_64-linux-gnu/libxkbcommon-x11.so.0',
    PACKAGE: CANONICAL,
}
# All fields that can affect package identity, dependency satisfaction or conflicts.
CONTROL_FIELDS = ('Package', 'Version', 'Architecture', 'Multi-Arch', 'Depends',
                  'Pre-Depends', 'Provides', 'Conflicts', 'Breaks', 'Replaces',
                  'Recommends', 'Suggests', 'Enhances', 'Essential', 'Protected')


def require(value, message):
    if not value:
        raise ValueError(message)


def parse_stanzas(text):
    records, record, field = [], {}, None
    for line in text.splitlines() + ['']:
        if not line:
            if record:
                records.append(record)
            record, field = {}, None
        elif line[0].isspace():
            require(field is not None, 'Malformed package continuation')
            record[field] += '\n' + line
        else:
            require(': ' in line or line.endswith(':'), 'Malformed package field')
            field, value = line.split(':', 1)
            require(field and field not in record, 'Duplicate package field: ' + field)
            record[field] = value.lstrip()
    return records


def load_candidates():
    raw = {}
    for name, expected in METADATA_PINS.items():
        raw[name] = (HERE / name).read_bytes()
        require(hashlib.sha256(raw[name]).hexdigest() == expected, 'Reviewed metadata changed: ' + name)
    candidates = json.loads(raw['ubuntu-graphics-candidates.json'])
    records = parse_stanzas(raw['ubuntu-graphics.Packages'].decode('utf-8'))
    require(len(candidates) == len(records) == MAX_PACKAGES, 'Reviewed package count mismatch')
    controls = {row['Package']: row for row in records}
    require(set(controls) == {row['Package'] for row in candidates} == set(PACKAGE_PATHS),
            'Unexpected reviewed package set')
    for row in candidates:
        control = controls[row['Package']]
        for key, value in row.items():
            if key not in ('url', 'metadata_url', 'observed_installed_version'):
                require(control.get(key) == value, 'Candidate/stanza mismatch: ' + row['Package'] + '/' + key)
        require(row['Architecture'] == 'amd64' and
                row['url'] == 'https://archive.ubuntu.com/ubuntu/' + row['Filename'],
                'Noncanonical official package URL or architecture')
        row['control'] = control
    require(sum(int(row['Size']) for row in candidates) == MAX_BYTES, 'Reviewed byte bound mismatch')
    return candidates


def query(args, deadline):
    require(deadline > time.monotonic(), 'Runner setup deadline expired')
    value = subprocess.run(args, stdin=subprocess.DEVNULL, capture_output=True,
                           text=True, timeout=min(10, deadline-time.monotonic()),
                           env={'PATH': '/usr/bin:/bin', 'LC_ALL': 'C.UTF-8'})
    require(len(value.stdout)+len(value.stderr) < 262144, 'Package inventory exceeds bound')
    return value


def read_status():
    graphics.trusted_installed(STATUS)
    with STATUS.open('rb') as stream:
        data = stream.read(64 * 1024 * 1024 + 1)
    require(0 < len(data) <= 64 * 1024 * 1024, 'Whole dpkg status exceeds bound or is empty')
    return data


def status_inventory(data):
    inventory = {}
    for row in parse_stanzas(data.decode('utf-8')):
        key = (row['Package'], row.get('Architecture', ''))
        require(key not in inventory, 'Duplicate actual dpkg status record: ' + repr(key))
        inventory[key] = row
    return inventory


def require_status_unchanged(expected):
    require(hashlib.sha256(read_status()).hexdigest() == expected,
            'Actual dpkg status changed after closure planning; no package mutation permitted')


def installed_row(inventory, name):
    for architecture in ('amd64', 'all'):
        row = inventory.get((name, architecture))
        if row and row.get('Status') == 'install ok installed':
            return row
    return None


def apt_check(status_path, root, deadline):
    """Read-only whole-state validation, without repositories or system writes."""
    root.mkdir()
    (root/'sources.list').write_text('')
    (root/'lists').mkdir()
    (root/'archives').mkdir()
    command = ['/usr/bin/apt-get', '--simulate', '-o', 'Debug::NoLocking=1',
               '-o', 'Dir::Etc::sourcelist=' + str(root/'sources.list'),
               '-o', 'Dir::Etc::sourceparts=-',
               '-o', 'Dir::State::status=' + str(status_path),
               '-o', 'Dir::State::lists=' + str(root/'lists'),
               '-o', 'Dir::Cache::archives=' + str(root/'archives'),
               '-o', 'Dir::Cache::pkgcache=', '-o', 'Dir::Cache::srcpkgcache=', 'check']
    result = query(command, deadline)
    return {'command': command, 'exitCode': result.returncode,
            'stdout': result.stdout, 'stderr': result.stderr}


def verify_paths(candidates, inventory, deadline):
    observations, blockers = [], []
    for candidate in candidates:
        name = candidate['Package']
        path = PACKAGE_PATHS[name]
        if not installed_row(inventory, name):
            if os.path.lexists(path):
                blockers.append({'package': name, 'path': path,
                                 'reason': 'Existing path without an installed candidate; no automatic replacement'})
            continue
        try:
            graphics.trusted_installed(path, name == PACKAGE)
            owner = query(['/usr/bin/dpkg-query', '-S', path], deadline)
            require(owner.returncode == 0 and owner.stdout.strip() in
                    (name + ': ' + path, name + ':amd64: ' + path),
                    'Installed path lacks expected package owner')
            observations.append({'package': name, 'path': path, 'owner': owner.stdout.strip()})
        except (OSError, ValueError) as error:
            blockers.append({'package': name, 'path': path,
                             'reason': str(error) + '; no automatic repair/upgrade'})
    return observations, blockers


def inspect(plan, deadline, root):
    availability = graphics.availability(plan)
    result = {'availability': availability, 'installedPrerequisites': [], 'blockers': [],
              'canonicalPresent': False, 'candidates': [], 'missing': []}
    # The wrong-runner path starts no package commands and writes no snapshot.
    if 'runner' not in availability:
        result['blockers'] = availability['missingInputs']
        return result
    result['blockers'] += [x for x in availability['missingInputs'] if x.get('path') != CANONICAL]
    for path in ('/usr/bin/dpkg-query', '/usr/bin/dpkg', '/usr/bin/apt-get'):
        try:
            graphics.trusted_installed(path, True)
        except (OSError, ValueError) as error:
            result['blockers'].append({'path': path, 'reason': str(error)})
    if any(x.get('path') in ('/usr/bin/dpkg-query', '/usr/bin/dpkg', '/usr/bin/apt-get', str(STATUS))
           for x in result['blockers']):
        return result
    candidates = load_candidates()
    root = Path(root)
    root.mkdir()
    actual = read_status()
    inventory = status_inventory(actual)
    snapshot = root/'status.actual'
    snapshot.write_bytes(actual)
    result['statusSnapshot'] = {'path': str(snapshot), 'bytes': len(actual),
        'sha256': hashlib.sha256(actual).hexdigest(), 'records': len(inventory),
        'installedRecords': sum(row.get('Status') == 'install ok installed' for row in inventory.values())}
    for name in ('xvfb', 'libgl1-mesa-dri', 'dpkg', 'libc-bin'):
        row = installed_row(inventory, name)
        result['installedPrerequisites'].append({'package': name, 'installed': bool(row),
            'version': row.get('Version') if row else None})
        if row is None:
            result['blockers'].append({'package': name, 'reason': 'Mandatory installed graphics prerequisite unavailable'})
    for candidate in candidates:
        name = candidate['Package']
        row = installed_row(inventory, name)
        result['candidates'].append({'package': name, 'installed': bool(row),
            'version': row.get('Version') if row else None, 'reviewedVersion': candidate['Version']})
        if row is None:
            if any(key[0] == name for key in inventory):
                result['blockers'].append({'package': name,
                    'reason': 'Existing foreign-architecture or incomplete package state; no automatic repair'})
            else:
                result['missing'].append(candidate)
    require(len(result['missing']) <= MAX_PACKAGES and
            sum(int(row['Size']) for row in result['missing']) <= MAX_BYTES, 'Closure exceeds reviewed bound')
    result['installedPaths'], path_blockers = verify_paths(candidates, inventory, deadline)
    result['blockers'] += path_blockers
    result['canonicalPresent'] = any(row['path'] == CANONICAL for row in result['installedPaths'])
    if result['missing']:
        for path in ('/usr/bin/dpkg-deb', '/usr/bin/sudo', '/usr/bin/timeout'):
            try:
                graphics.trusted_installed(path, True)
            except (OSError, ValueError) as error:
                result['blockers'].append({'path': path, 'reason': str(error)})
    # Preserve every installed version and relationship. Only missing pinned
    # candidate stanzas are appended; the reference solution is never substituted.
    proposed = bytearray(actual.rstrip() + b'\n\n')
    for candidate in result['missing']:
        stanza = dict(candidate['control'], Status='install ok installed')
        proposed.extend(('\n'.join(key + ': ' + value for key, value in stanza.items()) + '\n\n').encode())
    proposed_path = root/'status.proposed'
    proposed_path.write_bytes(proposed)
    result['baselineAptCheck'] = apt_check(snapshot, root/'apt-baseline', deadline)
    result['proposedAptCheck'] = apt_check(proposed_path, root/'apt-proposed', deadline)
    result['proposedStatusSha256'] = hashlib.sha256(proposed).hexdigest()
    if result['baselineAptCheck']['exitCode'] != 0:
        result['blockers'].append({'reason': 'Whole existing dpkg dependency/conflict state is broken; no automatic repair',
                                  'diagnostics': result['baselineAptCheck']})
    if result['proposedAptCheck']['exitCode'] != 0:
        result['blockers'].append({'reason': 'Whole proposed dpkg dependency/conflict state is broken',
                                  'diagnostics': result['proposedAptCheck']})
    require_status_unchanged(result['statusSnapshot']['sha256'])
    return result


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, request, fp, code, message, headers, newurl):
        raise ValueError('Pinned package URL redirected; review new location separately')


def download(candidate, destination, deadline):
    url, size, digest = candidate['url'], int(candidate['Size']), candidate['SHA256']
    require(deadline > time.monotonic(), 'Package download deadline expired')
    request = urllib.request.Request(url, headers={'User-Agent': 'Unified-nonce-diagnostic/1'})
    with urllib.request.build_opener(NoRedirect).open(request, timeout=min(15, deadline-time.monotonic())) as response:
        require(response.status == 200 and response.url == url, 'Unexpected official package response')
        data = bytearray()
        while len(data) <= size:
            require(time.monotonic() < deadline, 'Package download deadline expired')
            chunk = response.read(min(65536, size+1-len(data)))
            if not chunk:
                break
            data.extend(chunk)
        require(len(data) == size and hashlib.sha256(data).hexdigest() == digest, 'Official package size/hash mismatch')
    with destination.open('xb') as stream:
        stream.write(data)
    return {'url': url, 'bytes': size, 'sha256': digest, 'path': str(destination), 'candidate': candidate}


def verify_deb(item, deadline):
    path, candidate = Path(item['path']), item['candidate']
    require(path.stat().st_size == int(candidate['Size']) and
            hashlib.sha256(path.read_bytes()).hexdigest() == candidate['SHA256'], 'Package bytes changed before install')
    metadata = query(['/usr/bin/dpkg-deb', '-f', str(path)], deadline)
    records = parse_stanzas(metadata.stdout)
    require(metadata.returncode == 0 and len(records) == 1, 'Pinned package metadata unreadable')
    for field in CONTROL_FIELDS:
        expected = ' '.join(candidate['control'].get(field, '').split())
        observed = ' '.join(records[0].get(field, '').split())
        require(expected == observed, 'Pinned package metadata mismatch: ' + candidate['Package'] + '/' + field)
    return {'package': candidate['Package'], 'version': candidate['Version'], 'controlVerified': True}


def install_debs(downloads, deadline, status_sha256):
    require(0 < len(downloads) <= MAX_PACKAGES and
            len({item['candidate']['Package'] for item in downloads}) == len(downloads) and
            sum(int(item['candidate']['Size']) for item in downloads) <= MAX_BYTES, 'Invalid bounded install set')
    reviewed = {row['Package']: row for row in load_candidates()}
    require(all(item['candidate'] == reviewed.get(item['candidate']['Package']) for item in downloads),
            'Install set contains an unreviewed package or changed pin')
    metadata = [verify_deb(item, deadline) for item in downloads]
    require_status_unchanged(status_sha256)
    seconds = min(60, int(deadline-time.monotonic())-10)
    require(seconds >= 10, 'Insufficient setup deadline for bounded package installation')
    # One root timeout owns the entire dpkg group. Record-only signal handlers
    # retain its handle across spawn and wait; cancellation waits for its bound.
    command = ['/usr/bin/sudo', '-n', '/usr/bin/timeout', '--signal=TERM', '--kill-after=5s',
               str(seconds)+'s', '/usr/bin/dpkg', '--install'] + [item['path'] for item in downloads]
    process = None
    with bounded_process.owned_stops() as check_stop:
        try:
            check_stop()
            process = subprocess.Popen(command, stdin=subprocess.DEVNULL, start_new_session=True)
            wait_deadline = time.monotonic()+seconds+10
            while True:
                check_stop()
                remaining = wait_deadline-time.monotonic()
                require(remaining > 0, 'Bounded package owner did not exit')
                try:
                    code = process.wait(timeout=min(0.2, remaining))
                    break
                except subprocess.TimeoutExpired:
                    continue
            check_stop()
        except BaseException as error:
            if process is not None:
                try:
                    process.wait(timeout=seconds+10)
                except BaseException as cleanup:
                    error.add_note('Package owner cleanup also failed: '+type(cleanup).__name__+': '+str(cleanup))
            raise
    require(code == 0, 'Pinned package closure install failed: '+str(code))
    return {'command': command, 'exitCode': code, 'processReaped': True, 'metadata': metadata}


def verify_status_transition(before, after, additions):
    old = status_inventory(Path(before['statusSnapshot']['path']).read_bytes())
    new = status_inventory(Path(after['statusSnapshot']['path']).read_bytes())
    def installed_versions(inventory):
        return {key: row['Version'] for key, row in inventory.items() if row.get('Status') == 'install ok installed'}
    expected = installed_versions(old)
    for candidate in additions:
        expected[(candidate['Package'], candidate['Architecture'])] = candidate['Version']
    require(installed_versions(new) == expected,
            'Installed package state changed beyond reviewed missing additions')


def ensure(plan, consumer, deadline, allow_install=False):
    deadline = min(deadline, time.monotonic()+SETUP_SECONDS)
    receipt = {'schema': 2, 'status': 'FAILED', 'installationRequested': allow_install,
               'packageInstallStarted': False, 'graphicsStarted': False, 'jvmStarted': False,
               'maximumPackages': MAX_PACKAGES, 'maximumDownloadBytes': MAX_BYTES, 'setupSeconds': SETUP_SECONDS}
    try:
        root = Path(consumer)/'runner-package-setup'
        root.mkdir()
        receipt['before'] = before = inspect(plan, deadline, root/'before')
        require(not before['blockers'], 'Runner prerequisites blocked: '+json.dumps(before['blockers']))
        if not before['missing']:
            require(before['canonicalPresent'], 'Canonical installed graphics path unavailable')
            receipt['status'] = 'ALREADY_INSTALLED_NO_MUTATION'
            return receipt
        require(allow_install, 'Reviewed runner closure setup flag required')
        receipt['downloads'] = []
        require_status_unchanged(before['statusSnapshot']['sha256'])
        for candidate in before['missing']:
            target = root/Path(candidate['Filename']).name
            receipt['downloads'].append(download(candidate, target, deadline))
        require_status_unchanged(before['statusSnapshot']['sha256'])
        # Verify all controls before handing the full set to the single mutation.
        receipt['verifiedControls'] = [verify_deb(item, deadline) for item in receipt['downloads']]
        receipt['packageInstallStarted'] = True
        receipt['installation'] = install_debs(receipt['downloads'], deadline, before['statusSnapshot']['sha256'])
        receipt['after'] = after = inspect(plan, deadline, root/'after')
        require(after['canonicalPresent'] and not after['blockers'] and not after['missing'],
                'Installed closure verification failed: '+json.dumps(after['blockers']))
        verify_status_transition(before, after, before['missing'])
        receipt['status'] = 'PINNED_CLOSURE_INSTALLED'
        return receipt
    except BaseException as error:
        receipt['failure'] = type(error).__name__+': '+str(error)
        raise
    finally:
        output = Path(consumer)/'runner-dependencies.json'
        with output.open('x') as stream:
            json.dump(receipt, stream, indent=2)
        print('RUNNER_DEPENDENCIES '+json.dumps(receipt, sort_keys=True), flush=True)
