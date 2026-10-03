#!/usr/bin/env python3
"""Run one coordinated, bounded phase without modifying any accepted control world."""
import argparse
import datetime
import hashlib
import json
import os
import pathlib
import re
import select
import socket
import subprocess
import time
import tomllib
from prepare import valid_profile
from verify_world import verify

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parents[1]
PREFIX = 'UNIFIED_CLUMPS_PROBE'

def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def properties(path):
    return {key.strip(): value.strip() for line in path.read_text().splitlines()
            if line.strip() and not line.startswith('#') and '=' in line
            for key, value in [line.split('=', 1)]}

def check_lan(path, loader):
    config = tomllib.loads(path.read_text())
    value = config.get('server', {}).get('advertiseDedicatedServerToLan') if loader == 'native' else config.get('advertiseDedicatedServerToLan')
    assert value is False, 'LAN advertisement must be explicitly off: ' + str(path)

def check_inputs(lock, profile, phase):
    for section in ('runtime_files', 'original_inputs', 'fixture_sources'):
        for item in lock[section]:
            assert sha(ROOT / item['path']) == item['sha256'], f'Changed {section}: {item["path"]}'
    mods = list((profile / 'mods').iterdir())
    assert all(p.is_file() and p.suffix == '.jar' for p in mods), 'Unexpected mod input'
    assert {p.name: sha(p) for p in mods} == lock['mods'], 'Changed mod set'
    expected_jars = {item['path'] for item in lock['runtime_files'] if '/libraries/' in item['path'] and item['path'].endswith('.jar')}
    actual_jars = {str(p.relative_to(ROOT)) for p in (profile / 'libraries').rglob('*.jar')}
    assert actual_jars == expected_jars, 'Changed runtime JAR inventory'
    assert (profile / 'eula.txt').read_text().strip() == 'eula=true'
    props = properties(profile / 'server.properties')
    for key, expected in lock['server_properties'].items():
        assert props.get(key) == expected, f'Profile setting changed: {key}'
    check_lan(profile / lock['lan_disabled_config'], lock['loader'])
    if phase == 'reopen' and lock['loader'] == 'native':
        check_lan(profile / 'world/serverconfig/forge-server.toml', 'native')
    with socket.socket() as sock:
        sock.bind(('127.0.0.1', int(props['server-port'])))

def stage_counts(markers, expected):
    found = []
    for line in markers:
        match = re.search(r'UNIFIED_CLUMPS_PROBE PASS stage=([a-z_]+)(?:\s|$)', line)
        if match:
            found.append(match.group(1))
    return {stage: found.count(stage) for stage in expected}, found

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--profile', required=True)
    parser.add_argument('--phase', choices=['create', 'reopen'], required=True)
    parser.add_argument('--timeout', type=int, default=600)
    args = parser.parse_args()
    assert valid_profile(args.profile)
    assert 30 <= args.timeout <= 600, 'Timeout must be bounded within 30..600 seconds'
    lock_path = HERE / (args.profile + '-lock.json')
    lock = json.loads(lock_path.read_text())
    profile = ROOT / lock['profile']
    assert profile == ROOT / 'run' / args.profile, 'Profile lock target differs'
    logs = ROOT / 'logs' / args.profile
    world = profile / 'world'
    check_inputs(lock, profile, args.phase)
    if args.phase == 'create':
        assert not world.exists(), 'Create requires fresh world; preserve earlier evidence'
        before = None
    else:
        assert (world / 'level.dat').is_file(), 'Reopen requires saved world'
        before = verify(profile, lock['expected_saved_marker'])
    log_path = logs / (args.phase + '.log')
    report_path = logs / (args.phase + '.json')
    assert not log_path.exists() and not report_path.exists(), 'Preserve existing phase evidence'
    command = [str(ROOT / '.toolchains/jdk-21.0.12.1+1/bin/java'), '-Xms512M', '-Xmx2G',
               '-Dunified.clumpsProbe.phase=' + args.phase, '@' + lock['argfile'], 'nogui']
    start = time.monotonic()
    ready = probe_ready = frozen = saved = stopped = freeze_requested = save_requested = stop_requested = timed_out = False
    markers, commands, diagnostics = [], [], []
    buffer = b''
    proc = subprocess.Popen(command, cwd=profile, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                            stderr=subprocess.STDOUT, bufsize=0)

    def send(command):
        commands.append({'elapsed_seconds': round(time.monotonic() - start, 3), 'command': command})
        proc.stdin.write((command + '\n').encode())
        proc.stdin.flush()

    def observe(line):
        nonlocal ready, probe_ready, frozen, saved, stopped, freeze_requested, save_requested, stop_requested
        if PREFIX in line:
            markers.append(line)
        if any(text in line for text in ('clumps.refmap', 'Mixin apply', 'InvalidMixin', 'InjectionError', 'ERROR', 'Exception')):
            diagnostics.append(line)
        if 'Done (' in line and 'For help' in line:
            ready = True
        if PREFIX + ' PASS stage=ready_to_save ' in line:
            probe_ready = True
        if 'The game is frozen' in line:
            frozen = True
        if ready and probe_ready and not freeze_requested:
            send('tick freeze')
            freeze_requested = True
        if frozen and not save_requested:
            send('save-all flush')
            save_requested = True
        if save_requested and ('Saved the game' in line or 'Saved the world' in line):
            saved = True
            if not stop_requested:
                send('stop')
                stop_requested = True
        if 'All dimensions are saved' in line:
            stopped = True
        if PREFIX + ' FAIL ' in line and not stop_requested:
            send('stop')
            stop_requested = True

    with log_path.open('wb') as log:
        while proc.poll() is None:
            if time.monotonic() - start > args.timeout:
                timed_out = True
                # Preserve the log; stop forcibly only after the fixed bound is reached.
                proc.terminate()
                try:
                    proc.wait(timeout=20)
                except subprocess.TimeoutExpired:
                    proc.kill()
                    proc.wait()
                break
            readable, _, _ = select.select([proc.stdout], [], [], .5)
            if not readable:
                continue
            chunk = os.read(proc.stdout.fileno(), 65536)
            if not chunk:
                continue
            log.write(chunk)
            log.flush()
            buffer += chunk
            while b'\n' in buffer:
                raw, buffer = buffer.split(b'\n', 1)
                observe(raw.decode('utf8', errors='replace'))
        tail = proc.stdout.read() or b''
        log.write(tail)
        for line in (buffer + tail).decode('utf8', errors='replace').splitlines():
            # A terminated process must never receive another stdin command.
            if PREFIX in line:
                markers.append(line)
            if 'All dimensions are saved' in line:
                stopped = True
            if any(text in line for text in ('clumps.refmap', 'Mixin apply', 'InvalidMixin', 'InjectionError', 'ERROR', 'Exception')):
                diagnostics.append(line)
    counts, found = stage_counts(markers, lock['expected_stages'][args.phase])
    try:
        if lock['loader'] == 'native':
            check_lan(world / 'serverconfig/forge-server.toml', 'native')
        after = verify(profile, lock['expected_saved_marker'])
        if before:
            assert after['orb']['uuid'] == before['orb']['uuid'], 'Saved survivor UUID changed during reopen'
            assert after['orb']['clumped_map'] == before['orb']['clumped_map'], 'Saved XP histogram changed during reopen'
    except (OSError, ValueError, KeyError, TypeError, AssertionError) as error:
        after = {'passed': False, 'error': str(error)}
    report = {
        'loader': lock['loader'], 'phase': args.phase,
        'timestamp_utc': datetime.datetime.now(datetime.timezone.utc).isoformat(),
        'command': command, 'console_commands': commands, 'exit_code': proc.returncode,
        'timed_out': timed_out, 'duration_seconds': round(time.monotonic() - start, 3),
        'server_ready': ready, 'tick_freeze_acknowledged': frozen, 'saved': saved, 'all_dimensions_saved': stopped,
        'markers': markers, 'stage_counts': counts, 'stage_order': found,
        'expected_stage_order': lock['expected_stages'][args.phase],
        'original_absent_refmap_warning': [line for line in diagnostics if 'clumps.refmap' in line],
        'diagnostics': diagnostics, 'lock_sha256': sha(lock_path), 'mods': lock['mods'],
        'core_sha256': lock['core_sha256'], 'host_sha256': lock['host_sha256'],
        'offline_world_before_launch': before, 'offline_world_after_stop': after,
        'controller_sha256': sha(pathlib.Path(__file__)), 'verifier_sha256': sha(HERE / 'verify_world.py'),
        'log_sha256': sha(log_path),
        'network': 'Loopback only; explicit loader-correct LAN advertisement off; online-mode=true; no RCON/query/status/player accounts',
        'coverage': 'Exact original Clumps startup, injected interface/Mixins, six-to-one natural merge, XP histogram/total conservation, save/read/reopen',
        'not_tested': ['XP pickup', 'PlayerXpEvent cancellation', 'mending/RepairEvent', 'ValueEvent', 'client rendering', 'external or real players'],
    }
    report['passed'] = bool(proc.returncode == 0 and not timed_out and ready and frozen and saved and stopped
                            and found == lock['expected_stages'][args.phase]
                            and all(count == 1 for count in counts.values()) and after['passed']
                            and not any(PREFIX + ' FAIL ' in line for line in markers))
    report_path.write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report, indent=2))
    return 0 if report['passed'] else 1

if __name__ == '__main__':
    raise SystemExit(main())
