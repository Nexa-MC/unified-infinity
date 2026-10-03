#!/usr/bin/env python3
"""Coordinated loopback-only native control, capturing a full create or reopen phase."""
import argparse
import datetime
import hashlib
import json
import os
import pathlib
import select
import subprocess
import time
from verify_world import verify

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parents[1]
PROFILE = ROOT / 'run/forge-native-probe'
LOGS = ROOT / 'logs/forge-native-probe'

def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--phase', choices=['create', 'reopen'], required=True)
    parser.add_argument('--timeout', type=int, default=600)
    args = parser.parse_args()
    pin = json.loads((HERE / 'native-environment-lock.json').read_text())
    for entry in pin['runtime_files']:
        assert sha(ROOT / entry['path']) == entry['sha256'], f'Runtime input changed: {entry["path"]}'
    assert (PROFILE / 'eula.txt').read_text().strip() == 'eula=true', 'No EULA acceptance'
    props = (PROFILE / 'server.properties').read_text().splitlines()
    for required in ('server-ip=127.0.0.1', 'online-mode=true', 'enable-rcon=false', 'enable-query=false'):
        assert required in props, required
    mods = sorted((PROFILE / 'mods').glob('*.jar'))
    assert len(mods) == 1 and sha(mods[0]) == pin['probe_sha256'], 'Only the pinned own probe may execute'
    assert sha(HERE / 'build/unified-forge-probe-0.1.0.jar') == pin['probe_sha256'], 'Original probe changed'
    world = PROFILE / 'world'
    before = None
    if args.phase == 'create':
        assert not world.exists(), 'Create must start with a new world; preserve any existing evidence'
    else:
        assert (world / 'level.dat').is_file(), 'Reopen requires the existing world'
        assert 'advertiseDedicatedServerToLan = false' in (world / 'serverconfig/forge-server.toml').read_text(), 'Disable native Forge LAN advertisements'
        before = verify(PROFILE)
    log_path = LOGS / f'native-{args.phase}.log'
    report_path = LOGS / f'native-{args.phase}.json'
    assert not log_path.exists() and not report_path.exists(), 'Preserve existing phase evidence'
    command = [str(ROOT / '.toolchains/jdk-21.0.12.1+1/bin/java'), '-Xms512M', '-Xmx2G',
               f'-Dunified.forgeProbe.phase={args.phase}',
               '@libraries/net/minecraftforge/forge/1.21.1-52.1.0/unix_args.txt', 'nogui']
    start = time.monotonic()
    ready = False
    probe_ready = False
    saved = False
    stopped = False
    save_requested = False
    timed_out = False
    markers = []
    buffer = b''
    proc = subprocess.Popen(command, cwd=PROFILE, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                            stderr=subprocess.STDOUT, bufsize=0)
    with log_path.open('wb') as log:
        while proc.poll() is None:
            if time.monotonic() - start > args.timeout:
                timed_out = True
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
                line = raw.decode('utf-8', errors='replace')
                if 'UNIFIED_FORGE_PROBE' in line:
                    markers.append(line)
                if 'Done (' in line and 'For help' in line:
                    ready = True
                if 'UNIFIED_FORGE_PROBE PASS stage=ready_to_save' in line:
                    probe_ready = True
                if ready and probe_ready and not save_requested:
                    proc.stdin.write(b'save-all flush\n')
                    proc.stdin.flush()
                    save_requested = True
                if 'Saved the game' in line or 'Saved the world' in line:
                    saved = True
                    proc.stdin.write(b'stop\n')
                    proc.stdin.flush()
                if 'All dimensions are saved' in line:
                    stopped = True
        tail = proc.stdout.read() or b''
        log.write(tail)
        markers.extend(line for line in tail.decode('utf-8', errors='replace').splitlines() if 'UNIFIED_FORGE_PROBE' in line)
        if b'All dimensions are saved' in tail:
            stopped = True
    stages = ['constructor', 'common_setup', 'enqueued_work', f'world_{args.phase}', 'server_started', 'post_tick', 'ready_to_save']
    stage_counts = {stage: sum(f'PASS stage={stage} ' in m for m in markers) for stage in stages}
    files = [world / 'level.dat', world / 'data/unified_forge_probe.dat', world / 'region/r.0.0.mca']
    try:
        after = verify(PROFILE)
    except (OSError, ValueError, KeyError, AssertionError) as error:
        after = {'passed': False, 'error': str(error)}
    report = {'phase': args.phase, 'timestamp_utc': datetime.datetime.now(datetime.timezone.utc).isoformat(),
              'loader': 'Forge 1.21.1-52.1.0', 'probe_sha256': pin['probe_sha256'],
              'command': command, 'exit_code': proc.returncode, 'timed_out': timed_out,
              'duration_seconds': round(time.monotonic() - start, 3), 'server_ready': ready,
              'save_acknowledged': saved, 'all_dimensions_saved': stopped,
              'stage_counts': stage_counts, 'markers': markers,
              'offline_world_before_launch': before, 'offline_world_after_stop': after,
              'native_environment_lock_sha256': sha(HERE / 'native-environment-lock.json'),
              'world_files': {str(p.relative_to(PROFILE)): sha(p) if p.is_file() else None for p in files},
              'network': 'loopback only; online-mode=true; RCON/query disabled; no player accounts',
              'scope': 'Original own Forge-only Item probe; no third-party mods; no custom block, client, Mixin, capability or network claim'}
    report['passed'] = (proc.returncode == 0 and not timed_out and ready and saved and stopped
                        and all(count == 1 for count in stage_counts.values())
                        and all(p.is_file() for p in files) and after['passed']
                        and not any('UNIFIED_FORGE_PROBE FAIL' in m for m in markers))
    report_path.write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report, indent=2))
    raise SystemExit(0 if report['passed'] else 1)

if __name__ == '__main__':
    main()
