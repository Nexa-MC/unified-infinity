"""Deadline checks and a genuine harmless owned-process cleanup, not graphics acceptance."""
import importlib.util
import json
import os
from pathlib import Path
import platform
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import Mock, patch

HERE=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('graphics_owner_deadline',HERE/'graphics_preflight.py')
g=importlib.util.module_from_spec(spec);spec.loader.exec_module(g)

def cutoff(mono=100,wall=200,remaining=10):
    return dict(work_monotonic=mono+remaining,work_wall=wall+remaining,
                cleanup_monotonic=mono+remaining+90,cleanup_wall=wall+remaining+90)

class DeadlineTests(unittest.TestCase):
    def lease(self,value):
        with patch.object(g.time,'monotonic',return_value=100),patch.object(g.time,'time',return_value=200):
            return g.OwnerDeadline(value)
    def test_exact_finite_positive_bounded_cutoff(self):
        good=cutoff();self.assertEqual(self.lease(good).cutoff,good)
        cases=[None,{},dict(good,extra=0),cutoff(remaining=0),cutoff(remaining=-1),cutoff(remaining=2521)]
        for field in good:
            for bad in (True,False,None,'100',float('nan'),float('inf')):cases.append(dict(good,**{field:bad}))
        cases.extend([dict(good,cleanup_wall=301),dict(good,cleanup_monotonic=201),
                      dict(good,work_wall=230,cleanup_wall=320)])
        for value in cases:
            with self.subTest(value=value),self.assertRaises(ValueError):self.lease(value)
    def test_float_boundary_reserve_keeps_absolute_cutoffs(self):
        # Addition crosses the 1024 boundary; subtraction is not exactly 90.
        value=cutoff(mono=945.123456789,wall=1792797697.1234567)
        with patch.object(g.time,'monotonic',return_value=945.123456789), patch.object(g.time,'time',return_value=1792797697.1234567):
            lease=g.OwnerDeadline(value)
        self.assertEqual(lease.cutoff,value)
        with patch.object(g.time,'monotonic',return_value=value['work_monotonic']), patch.object(g.time,'time',return_value=value['work_wall']):
            self.assertEqual(lease.remaining(),0)
            with self.assertRaises(ValueError):lease.check()
        for field in ('cleanup_monotonic','cleanup_wall'):
            for delta in (-0.001,0.001):
                changed=dict(value);changed[field]+=delta
                with patch.object(g.time,'monotonic',return_value=945.123456789), patch.object(g.time,'time',return_value=1792797697.1234567), self.assertRaises(ValueError):g.OwnerDeadline(changed)
    def test_huge_finite_clock_does_not_expand_tolerance(self):
        huge=float(2**50);value=cutoff(mono=huge,wall=huge)
        for field in ('cleanup_monotonic','cleanup_wall'):
            for delta in (-0.5,0.5):
                changed=dict(value);changed[field]+=delta
                with patch.object(g.time,'monotonic',return_value=huge),patch.object(g.time,'time',return_value=huge),self.assertRaises(ValueError):g.OwnerDeadline(changed)
    def test_both_clock_bounds_and_no_rollback_extension(self):
        lease=self.lease(cutoff())
        for mono,wall,remaining in ((109,199,1),(101,210,0),(110,201,0),(105,205,5)):
            with patch.object(g.time,'monotonic',return_value=mono),patch.object(g.time,'time',return_value=wall):
                self.assertEqual(lease.remaining(),remaining)
                if remaining<=0:
                    with self.assertRaises(ValueError):lease.check()
        with patch.object(g.time,'monotonic',return_value=99),self.assertRaises(ValueError):lease.remaining()
    def test_cleanup_uses_separate_nonrenewable_reserve(self):
        lease=self.lease(cutoff())
        with patch.object(g.time,'monotonic',return_value=111),patch.object(g.time,'time',return_value=211):
            self.assertEqual(lease.remaining(cleanup=True),89)
            with self.assertRaises(ValueError):lease.check()
        with patch.object(g.time,'monotonic',return_value=200),patch.object(g.time,'time',return_value=300):
            self.assertEqual(lease.remaining(cleanup=True),0)
    def test_no_spawn_after_expiration(self):
        env=dict(GITHUB_ACTIONS='true',ImageOS='ubuntu24',ImageVersion='fixture')
        lock=dict(expected_runner=dict(ImageOS='ubuntu24',ImageVersion='fixture',machine=platform.machine()))
        with patch.dict(os.environ,env),patch.object(g,'OwnedChild') as child, \
             patch.object(g.time,'monotonic',return_value=100),patch.object(g.time,'time',return_value=200):
            with self.assertRaises(ValueError):g.execute(lock,{},Mock(),Path('/not-created'),owner_cutoff=cutoff(remaining=0))
            child.assert_not_called()
    def test_real_startup_expiry_reaps_term_ignoring_child(self):
        # No game or graphics executable: the production owner/lifecycle handles a
        # real Python sleeper. Its own alarm is a final safety net for test faults.
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);script=root/'exercise.py'
            script.write_text('''import importlib.util,json,os,platform,sys,time
from pathlib import Path
from unittest.mock import Mock,patch
spec=importlib.util.spec_from_file_location('g',sys.argv[1]);g=importlib.util.module_from_spec(spec);spec.loader.exec_module(g)
real=g.OwnedChild;owned=[]
def spawn(command,environment,destination):
    child=real([sys.executable,'-c',"import signal,time;signal.signal(signal.SIGTERM,signal.SIG_IGN);signal.alarm(8);print('READY',flush=True);time.sleep(60)"],environment,destination)
    owned.append(child);return child
s=Mock();s.Proc.return_value.identity.side_effect=lambda pid:dict(pid=pid,ppid=os.getpid())
s.Proc.return_value.inodes.return_value=set();s.read_bounded.return_value=b'header\\n'
s.write_new.side_effect=lambda path,value:Path(path).write_text(json.dumps(value))
mono,wall=time.monotonic(),time.time();cut=dict(work_monotonic=mono+.5,work_wall=wall+.5,cleanup_monotonic=mono+90.5,cleanup_wall=wall+90.5)
lock=dict(expected_runner=dict(ImageOS='ubuntu24',ImageVersion='fixture',machine=platform.machine()),display=':59321',tools=dict(xvfb='/unused/Xvfb',glxinfo='/unused/glxinfo'))
root=Path(sys.argv[2])/'actual';started=time.monotonic()
with patch.dict(os.environ,dict(GITHUB_ACTIONS='true',ImageOS='ubuntu24',ImageVersion='fixture')),patch.object(g,'OwnedChild',side_effect=spawn):
    try:g.execute(lock,{},s,root,owner_cutoff=cut)
    except ValueError as e:assert str(e) in ('Graphics owner cutoff exhausted','Xvfb startup timeout'),str(e)
    else:raise AssertionError('expected deadline rejection')
r=json.loads((root/'lifecycle.json').read_text())
assert r['status']=='FAILED' and r['pair_acceptance'] is False and r['owner_cutoff']==cut
assert r['cleanup_before_cutoff'] is True and r['cleanup']['all_reaped'] is True
assert len(owned)==1 and owned[0].result['returncode']==-9
assert not Path('/proc',str(owned[0].pid)).exists()
print('REAL_GRAPHICS_OWNER_DEADLINE_CLEANED',json.dumps(dict(elapsed=time.monotonic()-started,lifecycle=r)))
''')
            result=subprocess.run([sys.executable,str(script),str(HERE/'graphics_preflight.py'),d],capture_output=True,text=True,timeout=15)
            self.assertEqual(result.returncode,0,result.stdout+result.stderr)
            self.assertIn('REAL_GRAPHICS_OWNER_DEADLINE_CLEANED',result.stdout)
            print(result.stdout.strip())


# Exact reviewed execute deltas, reversed only to test the independently pinned predecessor.
REVIEWED_OWNER_DEADLINE_DELTAS = [("def execute(lock, pins, s, destination, lock_identity=None, owner_cutoff=None):\n    require(os.environ.get('GITHUB_ACTIONS') == 'true', 'Future GitHub CI mode only')\n    require(all(os.environ.get(key) == lock['expected_runner'][key]\n", "def execute(lock, pins, s, destination, lock_identity=None):\n    require(os.environ.get('GITHUB_ACTIONS') == 'true', 'Future GitHub CI mode only')\n    require(all(os.environ.get(key) == lock['expected_runner'][key]\n"), ("            platform.machine() == lock['expected_runner']['machine'], 'Runner image changed; review new lock')\n    require(hasattr(os, 'pidfd_open') and hasattr(signal, 'pidfd_send_signal'), 'Linux pidfd support required')\n    lease = OwnerDeadline(owner_cutoff)\n    proc = s.Proc()\n    # Reuse the frozen gate. No cgroup creation or relaxation when unavailable.\n", "            platform.machine() == lock['expected_runner']['machine'], 'Runner image changed; review new lock')\n    require(hasattr(os, 'pidfd_open') and hasattr(signal, 'pidfd_send_signal'), 'Linux pidfd support required')\n    proc = s.Proc()\n    # Reuse the frozen gate. No cgroup creation or relaxation when unavailable.\n"), ("    for number in (signal.SIGTERM, signal.SIGINT, signal.SIGHUP):\n        previous[number] = signal.signal(number, stop_signal)\n    deadline = lease.cutoff['work_monotonic']\n    result = {'schema': 1, 'status': 'FAILED', 'pair_acceptance': False,\n              'owner_cutoff': dict(lease.cutoff)}\n    try:\n        lease.check()\n        x = OwnedChild(xvfb_command, env, destination)\n        children.append(x)\n", "    for number in (signal.SIGTERM, signal.SIGINT, signal.SIGHUP):\n        previous[number] = signal.signal(number, stop_signal)\n    deadline = time.monotonic() + MAX_LIFETIME\n    result = {'schema': 1, 'status': 'FAILED', 'pair_acceptance': False}\n    try:\n        x = OwnedChild(xvfb_command, env, destination)\n        children.append(x)\n"), ("        identity = proc.identity(x.pid)\n        require(identity['ppid'] == os.getpid(), 'Xvfb is not our direct child')\n        startup_deadline = min(time.monotonic() + 15, deadline)\n        socket_path = '/tmp/.X11-unix/X' + display[1:]\n        while True:\n            lease.check()\n            require(not requested_stop and not x.reap(), 'Xvfb stopped during startup')\n            require(time.monotonic() < startup_deadline, 'Xvfb startup timeout')\n", "        identity = proc.identity(x.pid)\n        require(identity['ppid'] == os.getpid(), 'Xvfb is not our direct child')\n        startup_deadline = time.monotonic() + 15\n        socket_path = '/tmp/.X11-unix/X' + display[1:]\n        while True:\n            require(not requested_stop and not x.reap(), 'Xvfb stopped during startup')\n            require(time.monotonic() < startup_deadline, 'Xvfb startup timeout')\n"), ("                break\n        observed = process_libraries(x.pid, s)\n        lease.check()\n        gl = OwnedChild(gl_command, env, destination)\n        children.append(gl)\n        logs.add('glxinfo', gl)\n        probe_deadline = min(time.monotonic() + 30, deadline)\n        while not gl.reap():\n            lease.check()\n            require(not requested_stop and not x.reap(), 'Preflight interrupted or Xvfb exited')\n            require(time.monotonic() < probe_deadline, 'GLX probe timeout')\n            logs.drain()\n        # Drain both final pipes after wait4; EOF is mandatory and bounded.\n        drain_deadline = min(time.monotonic() + 2, deadline)\n        while any(key.data.startswith('glxinfo.') for key in logs.selector.get_map().values()):\n            lease.check()\n            require(time.monotonic() < drain_deadline, 'GLX output EOF timeout')\n            logs.drain()\n", "                break\n        observed = process_libraries(x.pid, s)\n        gl = OwnedChild(gl_command, env, destination)\n        children.append(gl)\n        logs.add('glxinfo', gl)\n        probe_deadline = time.monotonic() + 30\n        while not gl.reap():\n            require(not requested_stop and not x.reap(), 'Preflight interrupted or Xvfb exited')\n            require(time.monotonic() < probe_deadline, 'GLX probe timeout')\n            logs.drain()\n        # Drain both final pipes after wait4; EOF is mandatory and bounded.\n        drain_deadline = time.monotonic() + 2\n        while any(key.data.startswith('glxinfo.') for key in logs.selector.get_map().values()):\n            require(time.monotonic() < drain_deadline, 'GLX output EOF timeout')\n            logs.drain()\n"), ("        gate = s.memory_gate(proc, {'reserve_bytes': reserve})\n        s.no_new_oom_events(initial_gate)\n        lease.check()\n        validate_lock(lock, s)  # Post-execution file hashes are not self-generated pins.\n        lease.check()\n        receipt = {'schema': 1, 'display': display, 'xvfb_pid': x.pid,\n                   'xvfb_start_ticks': identity['start_ticks'], 'renderer': measured['renderer'],\n", "        gate = s.memory_gate(proc, {'reserve_bytes': reserve})\n        s.no_new_oom_events(initial_gate)\n        validate_lock(lock, s)  # Post-execution file hashes are not self-generated pins.\n        receipt = {'schema': 1, 'display': display, 'xvfb_pid': x.pid,\n                   'xvfb_start_ticks': identity['start_ticks'], 'renderer': measured['renderer'],\n"), ("                      'headroom_derivation': 'Xvfb VmHWM + glxinfo wait4 ru_maxrss + 256 MiB slack',\n                      'review_reference': lock['review_reference'], 'lock_identity': lock_identity}, s)\n        lease.check()\n        write_receipt(destination, 'ready.json', {'schema': 1, 'status': 'GRAPHICS_PREFLIGHT_READY',\n                      'pair_acceptance': False, 'graphics': graphics, 'inputs': spec['inputs'],\n                      'collector_pid': os.getpid(), 'maximum_lifetime_seconds': MAX_LIFETIME,\n                      'owner_cutoff': dict(lease.cutoff)}, s)\n        print(json.dumps({'status': 'GRAPHICS_PREFLIGHT_READY', 'ready': str(destination / 'ready.json')}), flush=True)\n        # The future orchestration keeps this collector alive for both serial\n        # pairs, then signals it. No game/consumer command is accepted here.\n        while not requested_stop:\n            lease.check()\n            require(not x.reap(), 'Owned Xvfb exited while consumers could be running')\n            proc.same(identity)\n", "                      'headroom_derivation': 'Xvfb VmHWM + glxinfo wait4 ru_maxrss + 256 MiB slack',\n                      'review_reference': lock['review_reference'], 'lock_identity': lock_identity}, s)\n        write_receipt(destination, 'ready.json', {'schema': 1, 'status': 'GRAPHICS_PREFLIGHT_READY',\n                      'pair_acceptance': False, 'graphics': graphics, 'inputs': spec['inputs'],\n                      'collector_pid': os.getpid(), 'maximum_lifetime_seconds': MAX_LIFETIME}, s)\n        print(json.dumps({'status': 'GRAPHICS_PREFLIGHT_READY', 'ready': str(destination / 'ready.json')}), flush=True)\n        # The future orchestration keeps this collector alive for both serial\n        # pairs, then signals it. No game/consumer command is accepted here.\n        while not requested_stop:\n            require(time.monotonic() < deadline, 'Graphics lifetime exhausted')\n            require(not x.reap(), 'Owned Xvfb exited while consumers could be running')\n            proc.same(identity)\n"), ("                             'children': cleanup_children,\n                             'all_reaped': not cleanup_errors and len(cleanup_children) == len(children)}\n        try:\n            result['cleanup_before_cutoff'] = lease.remaining(cleanup=True) > 0\n        except (ValueError, OSError, OverflowError):\n            result['cleanup_before_cutoff'] = False\n        if not result['cleanup_before_cutoff']:\n            result.update(status='CLEANUP_FAILED')\n        write_receipt(destination, 'lifecycle.json', result, s)\n        require(not cleanup_errors and result['cleanup_before_cutoff'], 'Owned graphics child cleanup failed or exceeded cutoff')\n", "                             'children': cleanup_children,\n                             'all_reaped': not cleanup_errors and len(cleanup_children) == len(children)}\n        write_receipt(destination, 'lifecycle.json', result, s)\n        require(not cleanup_errors, 'Owned graphics child cleanup failed')\n")]

def normalize_owner_deadline(source):
    for successor, predecessor in REVIEWED_OWNER_DEADLINE_DELTAS:
        if source.count(successor) != 1:
            raise ValueError('Expected exactly one reviewed owner deadline delta')
        source = source.replace(successor, predecessor)
    return source

if __name__=='__main__':unittest.main()
