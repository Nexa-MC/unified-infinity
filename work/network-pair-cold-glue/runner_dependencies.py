"""Proposed conditional Ubuntu package setup; nothing executes on import.

Only the explicitly reviewed driver flag permits one pinned mesa-utils-bin DEB.
No dependency resolver, repository changes, upgrades, or manual aliases.
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

PACKAGE = 'mesa-utils-bin'
VERSION = '9.0.0-2'
URL = 'https://archive.ubuntu.com/ubuntu/pool/universe/m/mesa-demos/mesa-utils-bin_9.0.0-2_amd64.deb'
SIZE = 164440
SHA256 = 'd64539eb18416708948d7857506946a024637e4c6147d91a28a42868e038cb00'
CANONICAL = '/usr/bin/glxinfo.x86_64-linux-gnu'
DEPENDENCIES = {'libc6': '2.38', 'libdecor-0-0': '0.1.0', 'libegl1': None,
                'libgl1': None, 'libgles2': None, 'libvulkan1': '1.2.131.2',
                'libwayland-client0': '1.20.0', 'libwayland-egl1': '1.15.0',
                'libx11-6': None, 'libxcb1': None, 'libxkbcommon-x11-0': '0.5.0',
                'libxkbcommon0': '0.5.0'}


def require(value, message):
    if not value:
        raise ValueError(message)


def query(args, deadline):
    require(deadline > time.monotonic(), 'Runner setup deadline expired')
    value = subprocess.run(args, stdin=subprocess.DEVNULL, capture_output=True,
                           text=True, timeout=min(10, deadline-time.monotonic()),
                           env={'PATH': '/usr/bin:/bin', 'LC_ALL': 'C.UTF-8'})
    require(len(value.stdout)+len(value.stderr) < 262144, 'Package inventory exceeds bound')
    return value


def installed(name, deadline):
    result = query(['/usr/bin/dpkg-query', '-W', '-f=${Status}\t${Version}\t${Architecture}', name], deadline)
    fields = result.stdout.strip().split('\t')
    if result.returncode or len(fields) != 3 or fields[0] != 'install ok installed':
        return {'package': name, 'installed': False, 'detail': result.stdout.strip()}
    return {'package': name, 'installed': True, 'version': fields[1], 'architecture': fields[2]}


def inspect(plan, deadline):
    availability = graphics.availability(plan)
    result = {'availability': availability, 'dependencies': [], 'installedPrerequisites': [], 'blockers': [],
              'canonicalPresent': False, 'package': None}
    # Validate the actual runner before starting even read-only package tools.
    if 'runner' not in availability:
        result['blockers'] = availability['missingInputs']
        return result
    result['blockers'] += [x for x in availability['missingInputs'] if x.get('path') != CANONICAL]
    query_tools_ok = True
    for path in ('/usr/bin/dpkg-query', '/usr/bin/dpkg'):
        try:
            graphics.trusted_installed(path, True)
        except (OSError, ValueError) as error:
            result['blockers'].append({'path': path, 'reason': str(error)})
            query_tools_ok = False
    if not query_tools_ok:
        return result
    for name in ('xvfb', 'libgl1-mesa-dri', 'dpkg', 'libc-bin'):
        row = installed(name, deadline)
        result['installedPrerequisites'].append(row)
        if not row['installed'] or row.get('architecture') not in ('amd64', 'all'):
            result['blockers'].append({'package': name, 'reason': 'Mandatory installed graphics prerequisite unavailable'})
    result['package'] = installed(PACKAGE, deadline)
    for name, minimum in DEPENDENCIES.items():
        row = installed(name, deadline)
        row['minimumVersion'] = minimum
        row['satisfied'] = row['installed'] and row.get('architecture') in ('amd64', 'all')
        if row['satisfied'] and minimum:
            row['satisfied'] = query(['/usr/bin/dpkg', '--compare-versions', row['version'], 'ge', minimum], deadline).returncode == 0
        result['dependencies'].append(row)
        if not row['satisfied']:
            result['blockers'].append({'package': name, 'reason': 'Declared dependency absent or below required version'})
    if not any(x.get('path') == CANONICAL for x in availability['missingInputs']):
        owner = query(['/usr/bin/dpkg-query', '-S', CANONICAL], deadline)
        result['canonicalOwner'] = owner.stdout.strip()
        result['canonicalPresent'] = (owner.returncode == 0 and
            owner.stdout.strip() in (PACKAGE+': '+CANONICAL, PACKAGE+':amd64: '+CANONICAL) and
            result['package']['installed'])
        if not result['canonicalPresent']:
            result['blockers'].append({'path': CANONICAL, 'reason': 'Canonical executable lacks expected installed package owner'})
    elif result['package']['installed']:
        result['blockers'].append({'package': PACKAGE, 'reason': 'Installed package has missing or untrusted executable; no automatic repair/upgrade'})
    else:
        for path in ('/usr/bin/dpkg-deb', '/usr/bin/sudo', '/usr/bin/timeout'):
            try:
                graphics.trusted_installed(path, True)
            except (OSError, ValueError) as error:
                result['blockers'].append({'path': path, 'reason': str(error)})
    return result


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, request, fp, code, message, headers, newurl):
        raise ValueError('Pinned package URL redirected; review new location separately')


def download(destination, deadline):
    request = urllib.request.Request(URL, headers={'User-Agent': 'Unified-nonce-diagnostic/1'})
    with urllib.request.build_opener(NoRedirect).open(request, timeout=min(15, deadline-time.monotonic())) as response:
        require(response.status == 200 and response.url == URL, 'Unexpected official package response')
        data = bytearray()
        while len(data) <= SIZE:
            require(time.monotonic() < deadline, 'Package download deadline expired')
            chunk = response.read(min(65536, SIZE+1-len(data)))
            if not chunk:
                break
            data.extend(chunk)
        require(len(data) == SIZE and hashlib.sha256(data).hexdigest() == SHA256, 'Official package size/hash mismatch')
    with destination.open('xb') as stream:
        stream.write(data)
    return {'url': URL, 'bytes': SIZE, 'sha256': SHA256, 'path': str(destination)}


def install_deb(path, deadline):
    require(path.stat().st_size == SIZE and hashlib.sha256(path.read_bytes()).hexdigest() == SHA256, 'Package bytes changed before install')
    metadata = query(['/usr/bin/dpkg-deb', '-f', str(path), 'Package', 'Version', 'Architecture'], deadline)
    require(metadata.returncode == 0 and metadata.stdout.strip() ==
            'Package: '+PACKAGE+'\nVersion: '+VERSION+'\nArchitecture: amd64', 'Pinned package metadata mismatch')
    seconds = min(60, int(deadline-time.monotonic())-10)
    require(seconds >= 10, 'Insufficient setup deadline for bounded package installation')
    # timeout runs as root with dpkg, so it can terminate its own child. On
    # cancellation wait for that bounded command; never abandon root children.
    command = ['/usr/bin/sudo', '-n', '/usr/bin/timeout', '--signal=TERM', '--kill-after=5s',
               str(seconds)+'s', '/usr/bin/dpkg', '--install', str(path)]
    process = None
    with bounded_process.owned_stops() as check_stop:
        try:
            check_stop()
            process = subprocess.Popen(command, stdin=subprocess.DEVNULL)
            wait_deadline=time.monotonic()+seconds+10
            while True:
                check_stop()
                remaining=wait_deadline-time.monotonic()
                require(remaining>0,'Bounded package owner did not exit')
                try:
                    code=process.wait(timeout=min(0.2,remaining))
                    break
                except subprocess.TimeoutExpired:
                    continue
            check_stop()
        except BaseException as error:
            if process is not None:
                try:process.wait(timeout=seconds+10)
                except BaseException as cleanup:
                    error.add_note('Package owner cleanup also failed: '+type(cleanup).__name__+': '+str(cleanup))
            raise
    require(code == 0, 'Pinned package install failed: '+str(code))
    return {'command': command, 'exitCode': code, 'processReaped': True}


def ensure(plan, consumer, deadline, allow_install=False):
    deadline = min(deadline, time.monotonic()+120)
    receipt = {'schema': 1, 'status': 'FAILED', 'installationRequested': allow_install,
               'packageInstallStarted': False, 'graphicsStarted': False, 'jvmStarted': False}
    try:
        receipt['before'] = before = inspect(plan, deadline)
        require(not before['blockers'], 'Runner prerequisites blocked: '+json.dumps(before['blockers']))
        if before['canonicalPresent']:
            receipt['status'] = 'ALREADY_INSTALLED_NO_MUTATION'
            return receipt
        require(allow_install, 'Canonical glxinfo missing; reviewed exact package setup flag required')
        root = Path(consumer)/'runner-package-setup'
        root.mkdir()
        target = root/'mesa-utils-bin_9.0.0-2_amd64.deb'
        receipt['download'] = download(target, deadline)
        receipt['packageInstallStarted'] = True
        receipt['installation'] = install_deb(target, deadline)
        receipt['after'] = after = inspect(plan, deadline)
        require(after['canonicalPresent'] and not after['blockers'] and after['package']['version'] == VERSION,
                'Installed package verification failed')
        receipt['status'] = 'PINNED_PACKAGE_INSTALLED'
        return receipt
    except BaseException as error:
        receipt['failure'] = type(error).__name__+': '+str(error)
        raise
    finally:
        output = Path(consumer)/'runner-dependencies.json'
        with output.open('x') as stream:
            json.dump(receipt, stream, indent=2)
        print('RUNNER_DEPENDENCIES '+json.dumps(receipt, sort_keys=True), flush=True)
