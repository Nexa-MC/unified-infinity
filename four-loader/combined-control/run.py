#!/usr/bin/env python3
"""Run one explicitly coordinated phase. Never rewrites/replaces an earlier world."""
import argparse
import datetime
import json
import pathlib
import re
import signal
import socket
import subprocess
import time
import tomllib
from common import HERE, ROOT, INPUTS, mixed, sha, valid_profile, both_ready, probe_evidence, verify_world


def property_matches(key, actual, expected):
    # java.util.Properties.store escapes ':' even inside values. Only this
    # known namespaced world-type property may use that equivalent spelling.
    return actual == expected or (key == 'level-type' and actual == expected.replace(':', r'\:'))


def check_inputs(lock, profile):
    assert lock['original_inputs'] == INPUTS, 'Combined original input set differs'
    for section in ('original_inputs', 'harness_files', 'fixture_sources'):
        for path, expected in lock[section].items():
            assert sha(ROOT / path) == expected, f'Changed {section}: {path}'
    entries = list((profile / 'mods').iterdir())
    assert all(p.is_file() and not p.is_symlink() and p.suffix == '.jar' for p in entries), 'Unexpected mod entry'
    assert {p.name: sha(p) for p in entries} == lock['mods'], 'Mod inventory/hash changed'
    assert mixed.manifest_tree(profile / 'libraries') == lock['libraries'], 'Runtime changed'
    assert sha(ROOT / '.toolchains/jdk-21.0.12.1+1/bin/java') == lock['java_sha256'], 'Java changed'
    for name, expected in lock['config_files'].items():
        assert sha(profile / name) == expected, 'Configuration changed: ' + name
    assert json.loads((profile / 'config/connector.json').read_text())['enableMixinSafeguard'] is True
    assert not [line for line in (profile / 'config/lithium.properties').read_text().splitlines() if line.strip() and not line.lstrip().startswith('#')], 'Lithium overrides disallowed'
    assert tomllib.loads((profile / 'config/neoforge-server.toml').read_text()).get('advertiseDedicatedServerToLan') is False, 'NeoForge root LAN advertisement must be off'
    assert (profile / 'eula.txt').read_text().strip() == 'eula=true'
    props = mixed.properties(profile / 'server.properties')
    assert all(property_matches(key, props.get(key), value) for key, value in lock['server_properties'].items()), 'Server setting changed'
    audit = profile / '.cache/connector/patch_audit.txt'
    assert not audit.exists() or re.search(r'^Failed: 0$', audit.read_text(), re.M), 'Failed safeguard audit disallows reopen'


class CombinedServer(mixed.Server):
    """Reuse exact mixed-pack commands, tick accounting, snapshots, and parser.

    Only startup/input ownership and the already-forced-chunk query differ.
    No command writes the persisted Quilt/Clumps evidence on reopen.
    """
    def __init__(self, profile, lock, phase, timeout, log_path):
        self.profile, self.which, self.tag = profile, 'unified', profile.name + '-' + phase
        self.cycle, self.phase, self.timeout = (1 if phase == 'create' else 2), phase, timeout
        self.proc = self.log = None
        self.lines, self.buffer, self.counter = [], b'', 0
        self.commands, self.steps, self.observations = [], [], []
        self.started, self.ready, self.saved, self.chunky = time.monotonic(), False, False, None
        self.mods, self.lock, self.log_path = lock['mods'], lock, log_path
        self.probe_barrier_passed = False
        self.forced_queries = 0
        self.freeze_acknowledged = False

    def launch(self):
        self.launch_args = [str(ROOT / '.toolchains/jdk-21.0.12.1+1/bin/java'), *mixed.JVM,
                            '-Djava.awt.headless=true', '-Dunified.clumpsProbe.phase=' + self.phase,
                            '-Dunified.quiltProbe.phase=' + self.phase, '@' + self.lock['argfile'], 'nogui']
        self.log = self.log_path.open('xb')
        self.proc = subprocess.Popen(self.launch_args, cwd=self.profile, stdin=subprocess.PIPE,
                                     stdout=subprocess.PIPE, stderr=subprocess.STDOUT, bufsize=0)
        self.wait(lambda: both_ready(self.lines), 300)
        self.ready = True
        self.probe_barrier_passed = True

    def pump(self, duration=.15):
        result = super().pump(duration)
        assert not any('UNIFIED_CLUMPS_PROBE FAIL' in line or 'NATIVE_QUILT_PROBE FAIL' in line for line in self.lines), 'Runtime companion failed'
        return result

    def command(self, command):
        assert self.probe_barrier_passed, 'Console work before both unchanged probes are ready'
        if command == 'forceload add 0 0':
            # Clumps creates this in its original create code and checks persistence
            # before ready on reopen. Read it; never repair lost state here.
            result = super().command('forceload query 0 0')
            assert any('Chunk at [0, 0] in Overworld' in line and 'is marked for force loading' in line for line in result), result
            self.forced_queries += 1
            return result
        result = super().command(command)
        if command == 'tick freeze':
            assert any('The game is frozen' in line for line in result), result
            self.freeze_acknowledged = True
        return result


def check_runtime_shape(raw, phase):
    lines = raw.decode(errors='replace').splitlines()
    forge = [line for line in lines if 'Unified Forge ABI slice prepared source=' in line]
    expected = [digest for path, digest in INPUTS.items() if '/Clumps-' in path or '/clumps-probe/build/' in path]
    mixin = [line for line in lines if 'SpongePowered MIXIN Subsystem Version=' in line]
    return {'forge_prepared_lines': forge,
            'forge_two_originals_exactly_once': len(forge) == 2 and all(sum('sha256=' + digest in line for line in forge) == 1 for digest in expected),
            'forge_cache_hits': sum('cacheHit=true' in line for line in forge),
            'one_host_mixin_service': len(mixin) == 1 and 'Service=ModLauncher Env=SERVER' in mixin[0],
            'mixin_service_lines': mixin,
            'original_absent_refmap_warning': [line for line in lines if 'clumps.refmap' in line],
            'native_host_launch': sum('ModLauncher running:' in line and '--fml.neoForgeVersion, 21.1.219' in line and '--fml.fmlVersion, 4.0.42' in line for line in lines) == 1}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--profile', required=True)
    parser.add_argument('--phase', choices=['create', 'reopen'], required=True)
    parser.add_argument('--timeout', type=int, default=600)
    parser.add_argument('--runtime-slot-approved', action='store_true', required=True)
    args = parser.parse_args()
    assert valid_profile(args.profile) and 60 <= args.timeout <= 600
    profile, lock_path = ROOT / 'run' / args.profile, HERE / (args.profile + '-lock.json')
    lock = json.loads(lock_path.read_text())
    assert lock['profile'] == str(profile.relative_to(ROOT))
    check_inputs(lock, profile)
    with socket.socket() as sock:
        sock.bind(('127.0.0.1', int(lock['server_properties']['server-port'])))
    logs = ROOT / 'logs' / args.profile
    log_path, report_path = logs / (args.phase + '.log'), logs / (args.phase + '.json')
    assert not log_path.exists() and not report_path.exists(), 'Preserve existing phase evidence'
    before = None
    if args.phase == 'create':
        assert not (profile / 'world').exists(), 'Fresh world required'
    else:
        previous = json.loads((logs / 'create.json').read_text())
        assert previous['passed'], 'Create must pass before reopen'
        assert previous['world_after'] == mixed.manifest_tree(profile / 'world'), 'Saved world changed between cycles'
        before = verify_world(profile)
    world_before = mixed.manifest_tree(profile / 'world')
    server = CombinedServer(profile, lock, args.phase, args.timeout, log_path)
    report = {'passed': False, 'phase': args.phase, 'profile': str(profile.relative_to(ROOT)),
              'timestamp_utc': datetime.datetime.now(datetime.timezone.utc).isoformat(),
              'lock_sha256': sha(lock_path), 'scope': lock['scope'], 'world_before': world_before,
              'offline_world_before_launch': before,
              'network': 'Loopback only; root NeoForge LAN advertisement=false; online-mode=true; RCON/query/status off; no accounts/players',
              'not_tested': ['OP Tab/client acceptance', 'real-player XP pickup/cancellation/Mending', 'broad mod compatibility', 'performance']}
    def interrupt(signum, frame):
        raise InterruptedError('Signal ' + str(signum))
    signal.signal(signal.SIGINT, interrupt)
    signal.signal(signal.SIGTERM, interrupt)
    try:
        server.launch()
        mixed.first_cycle(server) if args.phase == 'create' else mixed.second_cycle(server)
        server.stop()
        server.log.flush()
        runtime = server.report()
        probes = probe_evidence(log_path.read_bytes(), args.phase)
        shape = check_runtime_shape(log_path.read_bytes(), args.phase)
        after = verify_world(profile)
        if before:
            assert before['clumps']['orb']['uuid'] == after['clumps']['orb']['uuid'], 'Clumps saved survivor changed'
            assert before['clumps']['orb']['clumped_map'] == after['clumps']['orb']['clumped_map'], 'Clumps XP changed'
            assert before['mixed_pack'] == after['mixed_pack'], 'Mixed-pack saved evidence changed'
            assert before['quilt']['saved_data_sha256'] == after['quilt']['saved_data_sha256'], 'Quilt SavedData changed'
        check_inputs(lock, profile)
        assert len(server.observations) == (1 if args.phase == 'create' else 2), 'Missing exact mixed snapshots'
        assert [step['requested'] for step in server.steps] == ([8, 260] if args.phase == 'create' else [8, 32]), 'Tick accounting differs'
        assert server.forced_queries == 1 and server.freeze_acknowledged
        if args.phase == 'create':
            assert runtime['chunky'] and runtime['chunky']['passed']
        else:
            assert shape['forge_cache_hits'] == 2, 'Expected both Forge cache hits on reopen'
        assert runtime['passed'] and probes['passed'] and shape['forge_two_originals_exactly_once'] and shape['one_host_mixin_service'] and shape['native_host_launch'], 'Combined runtime assertion failed'
        report.update({'passed': True, 'mixed_pack': runtime, 'probes': probes, 'host_evidence': shape,
                       'offline_world_after_stop': after, 'all_inputs_unchanged': True})
    except BaseException as error:
        report['failure'] = f'{type(error).__name__}: {error}'
    finally:
        server.cleanup()
        report['mixed_pack'] = server.report()
        report['command'] = getattr(server, 'launch_args', None)
        report['probe_barrier_passed'] = server.probe_barrier_passed
        report['forced_chunk_query_count'] = server.forced_queries
        report['freeze_acknowledged'] = server.freeze_acknowledged
        report['world_after'] = mixed.manifest_tree(profile / 'world')
        if log_path.exists():
            report['log_sha256'] = sha(log_path)
            report['probes'] = probe_evidence(log_path.read_bytes(), args.phase)
            report['host_evidence'] = check_runtime_shape(log_path.read_bytes(), args.phase)
        with report_path.open('x') as stream:
            stream.write(json.dumps(report, indent=2) + '\n')
        print(json.dumps({'passed': report['passed'], 'report': str(report_path), 'failure': report.get('failure')}, indent=2))
    return 0 if report['passed'] else 1

if __name__ == '__main__':
    raise SystemExit(main())
