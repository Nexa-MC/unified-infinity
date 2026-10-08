#!/usr/bin/env python3
"""Source-only preparation. Runtime needs a complete reviewed lock and CI flag.

Starts exactly one Xvfb and one official glxinfo; never downloads, installs,
launches Java, dispatches CI, changes system settings, or kills by name/group.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import re
import selectors
import signal
import stat
import subprocess
import time
import types

MIB = 1024 * 1024
SUPERVISOR_SHA256 = '01f3796c0d6e9c54a770375f0ae1cc3451a89074bb88934023f997f7c48dc1bf'
MAX_LOG = MIB
MAX_LIFETIME = 42 * 60  # Shared by both serial 650-second pairs; bounded by driver work budget.


def require(value, message):
    if not value:
        raise ValueError(message)


def load_supervisor(path):
    # Import only this exact, unchanged source. No configurable Python plugin.
    raw = Path(path).read_bytes()
    require(len(raw) < MIB and hashlib.sha256(raw).hexdigest() == SUPERVISOR_SHA256,
            'Frozen supervisor source mismatch')
    module = types.ModuleType('frozen_network_supervisor')
    exec(compile(raw, str(path), 'exec'), module.__dict__)
    return module


def validate_lock(lock, s):
    s.exact_keys(lock, ('schema', 'status', 'review_reference', 'expected_runner',
                       'display', 'inputs', 'tools', 'package_provenance'), 'graphics lock')
    require(lock['schema'] == 'network-graphics-lock-v1' and
            lock['status'] == 'COMPLETE_REVIEWED', 'Complete reviewed graphics lock required')
    require(isinstance(lock['review_reference'], str) and
            1 <= len(lock['review_reference']) <= 512, 'Missing external review reference')
    s.exact_keys(lock['expected_runner'], ('ImageOS', 'ImageVersion', 'machine'), 'runner')
    require(lock['expected_runner']['ImageOS'] == 'ubuntu24' and
            re.fullmatch(r'\d{8}\.\d+\.\d+', lock['expected_runner']['ImageVersion']) and
            lock['expected_runner']['machine'] == 'x86_64', 'Exact Ubuntu 24.04 amd64 image required')
    require(isinstance(lock['display'], str) and re.fullmatch(r':\d{1,5}', lock['display']),
            'Literal local DISPLAY required')
    require(isinstance(lock['inputs'], list) and 3 <= len(lock['inputs']) <= 128,
            'Missing or excessive tool/library pins')
    pins = {}
    for pin in lock['inputs']:
        s.file_pin(pin)
        require(pin['path'] not in pins, 'Duplicate pin')
        pins[pin['path']] = pin['sha256']
    s.exact_keys(lock['tools'], ('xvfb', 'glxinfo'), 'tools')
    for name, basename in (('xvfb', 'Xvfb'), ('glxinfo', 'glxinfo.x86_64-linux-gnu')):
        path = lock['tools'][name]
        require(path in pins and Path(path).name == basename, 'Pinned official native tool required')
        require(os.access(path, os.X_OK), 'Tool is not executable')
    require(lock['package_provenance'] in pins, 'Sealed Ubuntu package provenance receipt required')
    provenance = s.decode_json(s.read_bounded(lock['package_provenance'], MIB), MIB)
    if isinstance(provenance, dict) and provenance.get('status') == 'OBSERVED_INSTALLED_PACKAGES':
        validate_installed_observations(provenance, lock, pins, s)
        return pins
    s.exact_keys(provenance, ('schema', 'status', 'snapshot', 'signed_index_review_reference',
                             'packages', 'file_packages'), 'package closure receipt')
    require(provenance['schema'] == 1 and provenance['status'] == 'VERIFIED_UBUNTU_CLOSURE',
            'Producer must verify the complete signed Ubuntu closure')
    require(re.fullmatch(r'\d{8}T\d{6}Z', provenance['snapshot']) and
            isinstance(provenance['signed_index_review_reference'], str) and
            1 <= len(provenance['signed_index_review_reference']) <= 512,
            'Snapshot/signature verification reference missing')
    packages = provenance['packages']
    require(isinstance(packages, list) and 3 <= len(packages) <= 256, 'Package closure missing')
    identities = set()
    for row in packages:
        s.exact_keys(row, ('package', 'version', 'architecture', 'uri', 'bytes', 'sha256'), 'package')
        require(re.fullmatch(r'[a-z0-9][a-z0-9+.-]+', row['package']) and
                isinstance(row['version'], str) and 1 <= len(row['version']) <= 128 and
                row['architecture'] in ('amd64', 'all'), 'Invalid package identity')
        prefix = 'https://snapshot.ubuntu.com/ubuntu/' + provenance['snapshot'] + '/pool/'
        require(row['uri'].startswith(prefix) and '..' not in row['uri'] and
                row['uri'].endswith('.deb'), 'Exact official snapshot package URL required')
        require(s.integer(row['bytes'], 1) and re.fullmatch('[0-9a-f]{64}', row['sha256']),
                'Exact package size/hash required')
        identity = row['package'] + ':' + row['architecture'] + '=' + row['version']
        require(identity not in identities, 'Duplicate package identity')
        identities.add(identity)
    require({'xvfb', 'mesa-utils-bin', 'libgl1-mesa-dri'} <= {r['package'] for r in packages},
            'Xvfb, GLX utility and Mesa DRI package closure required')
    mapping = provenance['file_packages']
    require(isinstance(mapping, dict) and set(mapping) == set(pins) - {lock['package_provenance']} and
            all(value in identities for value in mapping.values()), 'Every tool/library needs package provenance')
    require(mapping[lock['tools']['xvfb']].startswith('xvfb:') and
            mapping[lock['tools']['glxinfo']].startswith('mesa-utils-bin:'), 'Wrong official tool package')
    return pins



def validate_installed_observations(provenance, lock, pins, s):
    """Check reviewed installed-package observations, without an archive-chain claim.

    The producer records actual target-runner os-release, image, dpkg identities,
    file ownership and hashes. This parser checks consistency and exact file
    pins; it neither runs dpkg nor verifies archive signatures or .deb origins.
    """
    s.exact_keys(provenance, ('schema', 'status', 'observation_reference', 'distribution',
                             'runner', 'packages', 'file_packages', 'file_sha256'),
                 'installed package observations')
    require(provenance['schema'] == 1 and
            provenance['status'] == 'OBSERVED_INSTALLED_PACKAGES',
            'Explicit installed-package observation status required')
    require(isinstance(provenance['observation_reference'], str) and
            1 <= len(provenance['observation_reference']) <= 512,
            'Installed package observation reference missing')
    s.exact_keys(provenance['distribution'], ('id', 'version_id'), 'observed distribution')
    require(provenance['distribution'] == {'id': 'ubuntu', 'version_id': '24.04'},
            'Observed packages must come from Ubuntu 24.04')
    s.exact_keys(provenance['runner'], ('ImageOS', 'ImageVersion', 'machine'), 'observed runner')
    require(provenance['runner'] == lock['expected_runner'],
            'Observed package runner differs from reviewed runner')
    packages = provenance['packages']
    require(isinstance(packages, list) and 3 <= len(packages) <= 256,
            'Installed package inventory missing')
    identities = set()
    for row in packages:
        s.exact_keys(row, ('package', 'version', 'architecture'), 'installed package')
        require(isinstance(row['package'], str) and
                re.fullmatch(r'[a-z0-9][a-z0-9+.-]+', row['package']) and
                isinstance(row['version'], str) and 1 <= len(row['version']) <= 128 and
                re.fullmatch(r'[0-9A-Za-z.+:~\-]+', row['version']) and
                row['architecture'] in ('amd64', 'all'), 'Invalid installed package identity')
        identity = row['package'] + ':' + row['architecture'] + '=' + row['version']
        require(identity not in identities, 'Duplicate installed package identity')
        identities.add(identity)
    require({'xvfb', 'mesa-utils-bin', 'libgl1-mesa-dri'} <= {r['package'] for r in packages},
            'Observed Xvfb, GLX utility and Mesa DRI packages required')
    mapping = provenance['file_packages']
    files = set(pins) - {lock['package_provenance']}
    require(isinstance(mapping, dict) and set(mapping) == files and
            all(isinstance(value, str) and value in identities for value in mapping.values()),
            'Every tool/library needs observed package ownership')
    require(mapping[lock['tools']['xvfb']].startswith('xvfb:') and
            mapping[lock['tools']['glxinfo']].startswith('mesa-utils-bin:'),
            'Wrong observed official tool package')
    hashes = provenance['file_sha256']
    require(isinstance(hashes, dict) and set(hashes) == files and
            all(hashes[path] == pins[path] for path in files),
            'Every observed file SHA-256 must equal its reviewed input pin')


def parse_glxinfo(text, display):
    """Require glxinfo -B's genuine display/direct/core-context/renderer output."""
    require(len(text.encode('utf-8')) <= MAX_LOG, 'GLX output too large')
    def one(pattern, label):
        values = re.findall(pattern, text, re.MULTILINE)
        require(len(values) == 1, 'Missing or ambiguous ' + label)
        return values[0].strip()
    require(one(r'^name of display:\s*(.+)$', 'display') in (display, display + '.0'),
            'GLX output came from another display')
    require(one(r'^direct rendering:\s*(.+)$', 'direct rendering') == 'Yes',
            'Direct rendering was not observed')
    renderer = one(r'^OpenGL renderer string:\s*(.+)$', 'renderer')
    require(len(renderer) <= 512 and re.search(r'\bllvmpipe\b', renderer, re.I),
            'Actual llvmpipe renderer required')
    version = one(r'^OpenGL core profile version string:\s*(.+)$', 'core GL context')
    match = re.match(r'(\d+)\.(\d+)\b', version)
    require(match and tuple(map(int, match.groups())) >= (3, 2),
            'Measured OpenGL core capability below 3.2')
    return {'renderer': renderer, 'core_version': version, 'direct_rendering': True,
            'glx_capable': True}


def traced_libraries(text):
    # glibc's actual loader trace includes dlopen-loaded Mesa modules. /proc maps
    # alone could miss a short-lived glxinfo process or already-unloaded module.
    paths = re.findall(r'^\s*\d+:\s+calling init:\s+(/[^\r\n]+)', text, re.MULTILINE)
    require(paths, 'No native dynamic-loader observations')
    return {str(Path(path.strip()).resolve(strict=True)) for path in paths}


def process_libraries(pid, s):
    paths = set()
    for line in s.read_bounded(Path('/proc') / str(pid) / 'maps', 2 * MIB).decode().splitlines():
        fields = line.split(None, 5)
        if len(fields) == 6 and fields[5].startswith('/'):
            require(not fields[5].endswith(' (deleted)'), 'Deleted mapped input')
            paths.add(str(Path(fields[5]).resolve(strict=True)))
    return paths


def measured_reserve(xvfb_peak, probe_peak):
    require(type(xvfb_peak) is int and xvfb_peak > 0 and
            type(probe_peak) is int and probe_peak > 0, 'Kernel RSS measurements required')
    # Reserve measured simultaneous process peaks plus 256 MiB of slack. This
    # is a derived graphics budget, not a fabricated free-memory observation.
    return xvfb_peak + probe_peak + 256 * MIB


class OwnedChild:
    def __init__(self, command, environment, destination):
        self.process = subprocess.Popen(command, env=environment, cwd=destination,
                                        stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                                        stderr=subprocess.PIPE, start_new_session=True)
        self.pid = self.process.pid
        try:
            self.fd = os.pidfd_open(self.pid)
        except OSError:
            # Unreaped direct child cannot have its PID reused; retain ownership
            # and clean it even if pidfd acquisition fails immediately after spawn.
            self.process.kill()
            self.process.wait(timeout=3)
            raise
        self.result = None

    def reap(self):
        if self.result is None:
            pid, status, usage = os.wait4(self.pid, os.WNOHANG)
            if pid:
                code = os.waitstatus_to_exitcode(status)
                self.process.returncode = code  # Popen must not reap it again.
                self.result = {'returncode': code, 'peak_rss_bytes': int(usage.ru_maxrss) * 1024}
        return self.result

    def stop(self):
        # pidfd names this exact child even if its numeric PID is later reused.
        try:
            if not self.reap():
                signal.pidfd_send_signal(self.fd, signal.SIGTERM)
                until = time.monotonic() + 3
                while not self.reap() and time.monotonic() < until:
                    time.sleep(0.02)
                if not self.reap():
                    signal.pidfd_send_signal(self.fd, signal.SIGKILL)
                    until = time.monotonic() + 3
                    while not self.reap() and time.monotonic() < until:
                        time.sleep(0.02)
                    require(self.reap(), 'Owned child survived bounded TERM/KILL cleanup')
        except ProcessLookupError:
            self.reap()
        finally:
            os.close(self.fd)


class Logs:
    def __init__(self, destination):
        self.selector = selectors.DefaultSelector()
        self.destination = destination
        self.buffers = {}
        self.files = {}

    def add(self, label, child):
        for kind in ('stdout', 'stderr'):
            name = label + '.' + kind
            stream = getattr(child.process, kind)
            os.set_blocking(stream.fileno(), False)
            self.selector.register(stream, selectors.EVENT_READ, name)
            self.buffers[name] = bytearray()
            self.files[name] = (self.destination / (name + '.log')).open('xb')

    def drain(self, delay=0.02):
        for key, _ in self.selector.select(delay):
            chunk = os.read(key.fileobj.fileno(), 65536)
            if not chunk:
                self.selector.unregister(key.fileobj)
                key.fileobj.close()
                continue
            data = self.buffers[key.data]
            require(len(data) + len(chunk) <= MAX_LOG, 'Native log bound exceeded')
            data.extend(chunk)
            self.files[key.data].write(chunk)
            self.files[key.data].flush()

    def text(self, name):
        return self.buffers[name].decode('utf-8', 'strict')

    def close(self):
        self.selector.close()
        for stream in self.files.values():
            stream.close()


def write_receipt(destination, name, value, s, limit=MIB):
    require(len(json.dumps(value, separators=(',', ':')).encode('ascii')) + 1 <= limit,
            'Receipt exceeds frozen consumer bound')
    path = destination / name
    temporary = destination / (name + '.new')
    s.write_new(temporary, value)
    temporary.chmod(0o444)
    try:
        os.link(temporary, path, follow_symlinks=False)
    finally:
        temporary.unlink()
    return str(path)


def execute(lock, pins, s, destination, lock_identity=None):
    require(os.environ.get('GITHUB_ACTIONS') == 'true', 'Future GitHub CI mode only')
    require(all(os.environ.get(key) == lock['expected_runner'][key]
                for key in ('ImageOS', 'ImageVersion')) and
            platform.machine() == lock['expected_runner']['machine'], 'Runner image changed; review new lock')
    require(hasattr(os, 'pidfd_open') and hasattr(signal, 'pidfd_send_signal'), 'Linux pidfd support required')
    proc = s.Proc()
    # Reuse the frozen gate. No cgroup creation or relaxation when unavailable.
    initial_gate = s.memory_gate(proc, {'reserve_bytes': 256 * MIB})
    display = lock['display']
    for path in (Path('/tmp/.X11-unix/X' + display[1:]), Path('/tmp/.X' + display[1:] + '-lock')):
        require(not os.path.lexists(path), 'DISPLAY already occupied; never remove another display')
    destination.mkdir(mode=0o700)
    env = {'PATH': '/usr/bin:/bin', 'LANG': 'C.UTF-8', 'LC_ALL': 'C.UTF-8', 'TZ': 'UTC',
           'DISPLAY': display, 'LIBGL_ALWAYS_SOFTWARE': 'true', 'GALLIUM_DRIVER': 'llvmpipe',
           '__GLX_VENDOR_LIBRARY_NAME': 'mesa', 'LD_DEBUG': 'files'}
    for name in ('HOME', 'XDG_CACHE_HOME', 'XDG_CONFIG_HOME', 'XDG_DATA_HOME', 'TMPDIR'):
        path = destination / name.lower()
        path.mkdir(mode=0o700)
        env[name] = str(path)
    xvfb_command = [lock['tools']['xvfb'], display, '-screen', '0', '1280x720x24',
                    '-nolisten', 'tcp', '-noreset']
    gl_command = [lock['tools']['glxinfo'], '-B']
    logs, children = Logs(destination), []
    requested_stop = []
    previous = {}
    def stop_signal(number, frame):
        requested_stop.append(number)
    for number in (signal.SIGTERM, signal.SIGINT, signal.SIGHUP):
        previous[number] = signal.signal(number, stop_signal)
    deadline = time.monotonic() + MAX_LIFETIME
    result = {'schema': 1, 'status': 'FAILED', 'pair_acceptance': False}
    try:
        x = OwnedChild(xvfb_command, env, destination)
        children.append(x)
        logs.add('xvfb', x)
        identity = proc.identity(x.pid)
        require(identity['ppid'] == os.getpid(), 'Xvfb is not our direct child')
        startup_deadline = time.monotonic() + 15
        socket_path = '/tmp/.X11-unix/X' + display[1:]
        while True:
            require(not requested_stop and not x.reap(), 'Xvfb stopped during startup')
            require(time.monotonic() < startup_deadline, 'Xvfb startup timeout')
            logs.drain()
            inodes = proc.inodes(identity)
            rows = s.read_bounded(Path('/proc/net/unix'), 2 * MIB).decode().splitlines()[1:]
            if any(len(f := line.split()) >= 8 and f[6] in inodes and f[7] == socket_path for line in rows):
                require(stat.S_ISSOCK(os.stat(socket_path).st_mode), 'DISPLAY path is not a live Unix socket')
                break
        observed = process_libraries(x.pid, s)
        gl = OwnedChild(gl_command, env, destination)
        children.append(gl)
        logs.add('glxinfo', gl)
        probe_deadline = time.monotonic() + 30
        while not gl.reap():
            require(not requested_stop and not x.reap(), 'Preflight interrupted or Xvfb exited')
            require(time.monotonic() < probe_deadline, 'GLX probe timeout')
            logs.drain()
        # Drain both final pipes after wait4; EOF is mandatory and bounded.
        drain_deadline = time.monotonic() + 2
        while any(key.data.startswith('glxinfo.') for key in logs.selector.get_map().values()):
            require(time.monotonic() < drain_deadline, 'GLX output EOF timeout')
            logs.drain()
        require(gl.result['returncode'] == 0, 'Official GLX preflight failed')
        measured = parse_glxinfo(logs.text('glxinfo.stdout'), display)
        observed |= process_libraries(x.pid, s) | traced_libraries(logs.text('glxinfo.stderr'))
        require(observed <= set(pins), 'Observed unpinned graphics library/tool: ' + ', '.join(sorted(observed - set(pins))))
        status = s.read_bounded(Path('/proc') / str(x.pid) / 'status', 65536).decode()
        peak = re.findall(r'^VmHWM:\s+(\d+) kB$', status, re.MULTILINE)
        require(len(peak) == 1, 'Missing Xvfb kernel RSS high-water mark')
        xvfb_peak = int(peak[0]) * 1024
        reserve = measured_reserve(xvfb_peak, gl.result['peak_rss_bytes'])
        gate = s.memory_gate(proc, {'reserve_bytes': reserve})
        s.no_new_oom_events(initial_gate)
        validate_lock(lock, s)  # Post-execution file hashes are not self-generated pins.
        receipt = {'schema': 1, 'display': display, 'xvfb_pid': x.pid,
                   'xvfb_start_ticks': identity['start_ticks'], 'renderer': measured['renderer'],
                   'direct_rendering': True, 'glx_capable': True,
                   'gl_probe_peak_rss_bytes': gl.result['peak_rss_bytes'],
                   'measured_headroom_bytes': reserve, 'input_sha256': pins}
        receipt_path = write_receipt(destination, 'graphics-preflight.json', receipt, s, 8192)
        receipt_pin = {'path': receipt_path, 'bytes': Path(receipt_path).stat().st_size,
                       'sha256': s.digest(receipt_path)}
        graphics = {'display': display, 'pid': x.pid, 'start_ticks': identity['start_ticks'],
                    'executable': lock['tools']['xvfb'], 'preflight': receipt_path, 'reserve_bytes': reserve}
        spec = {'graphics': graphics, 'inputs': lock['inputs'] + [receipt_pin]}
        s.verify_graphics(spec, proc)  # Exact existing schema, executable and Unix ownership check.
        write_receipt(destination, 'measurement.json', {'schema': 1, 'xvfb_command': xvfb_command,
                      'glxinfo_command': gl_command, 'environment': env, 'xvfb_identity': identity,
                      'xvfb_peak_rss_bytes': xvfb_peak, 'glxinfo_wait4': gl.result,
                      'measured_glx': measured, 'observed_files': sorted(observed),
                      'initial_memory_gate': initial_gate, 'post_probe_memory_gate': gate,
                      'headroom_derivation': 'Xvfb VmHWM + glxinfo wait4 ru_maxrss + 256 MiB slack',
                      'review_reference': lock['review_reference'], 'lock_identity': lock_identity}, s)
        write_receipt(destination, 'ready.json', {'schema': 1, 'status': 'GRAPHICS_PREFLIGHT_READY',
                      'pair_acceptance': False, 'graphics': graphics, 'inputs': spec['inputs'],
                      'collector_pid': os.getpid(), 'maximum_lifetime_seconds': MAX_LIFETIME}, s)
        print(json.dumps({'status': 'GRAPHICS_PREFLIGHT_READY', 'ready': str(destination / 'ready.json')}), flush=True)
        # The future orchestration keeps this collector alive for both serial
        # pairs, then signals it. No game/consumer command is accepted here.
        while not requested_stop:
            require(time.monotonic() < deadline, 'Graphics lifetime exhausted')
            require(not x.reap(), 'Owned Xvfb exited while consumers could be running')
            proc.same(identity)
            logs.drain(0.1)
        result['status'] = 'STOPPED_BY_ORCHESTRATOR'
    except Exception as error:
        result['error'] = str(error)
        raise
    finally:
        cleanup_errors = []
        for child in reversed(children):
            try:
                child.stop()
            except Exception as error:
                cleanup_errors.append(str(error))
        logs.close()
        for number, handler in previous.items():
            signal.signal(number, handler)
        if cleanup_errors:
            result.update(status='CLEANUP_FAILED', cleanup_errors=cleanup_errors)
        write_receipt(destination, 'lifecycle.json', result, s)
        require(not cleanup_errors, 'Owned graphics child cleanup failed')


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--supervisor', required=True)
    parser.add_argument('--lock', required=True)
    parser.add_argument('--sha256', required=True)
    parser.add_argument('--destination')
    parser.add_argument('--execute-reviewed-ci-preflight', action='store_true')
    args = parser.parse_args(argv)
    s = load_supervisor(args.supervisor)
    path = s.clean_path(args.lock)
    lock_identity = {'path': str(path), 'bytes': path.stat().st_size, 'sha256': args.sha256}
    s.file_pin(lock_identity)
    lock = s.decode_json(s.read_bounded(path, MIB), MIB)
    pins = validate_lock(lock, s)
    if not args.execute_reviewed_ci_preflight:
        print(json.dumps({'status': 'STATIC_INPUTS_VALID', 'runtime_evidence_observed': False,
                          'pair_acceptance': False}))
        return 0
    require(args.destination, 'Fresh absolute destination required')
    destination = s.clean_path(args.destination)
    require(not destination.exists() and destination.parent.is_dir(), 'Fresh destination required')
    execute(lock, pins, s, destination, lock_identity)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
