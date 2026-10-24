"""Synthetic guards plus one real owned Python /proc/exe label; no JDK transition."""
import hashlib
import json
import subprocess
import sys
from pathlib import Path
import unittest
from unittest.mock import patch
import supervisor as s
import test_jdk_spawn_transition as fixture
from transition_target_preservation import without_transition_target_diagnostic, PREDECESSOR_SHA256

REAL_POPEN = subprocess.Popen

class TransitionTargetDiagnostic(unittest.TestCase):
    setUp = fixture.SpawnTransition.setUp
    ARGV = s.CPU_PROBE_ARGV
    snapshot = fixture.SpawnTransition.snapshot
    def reject(self, target):
        self.exe.unlink()
        self.exe.symlink_to(target)
        with self.assertRaisesRegex(ValueError, '^CPU probe transition target forbidden$') as error:
            self.snapshot()
        return error.exception
    def test_parent_java_label_still_rejected(self):
        e=self.reject(str(self.java))
        self.assertEqual(e.transition_target_diagnostic,dict(admission_evidence=False,identity_verified=False,path_label='PARENT_COMMAND_PATH',deleted_suffix=False))
    def test_deleted_parent_java_is_distinct_not_admitted(self):
        e=self.reject(str(self.java)+' (deleted)')
        self.assertEqual(e.transition_target_diagnostic['path_label'],'PARENT_COMMAND_PATH')
        self.assertTrue(e.transition_target_diagnostic['deleted_suffix'])
    def test_unrelated_executable_remains_unknown(self):
        e=self.reject('/private/secret/application')
        self.assertEqual(e.transition_target_diagnostic['path_label'],'OTHER_PATH')
        self.assertFalse(e.transition_target_diagnostic['deleted_suffix'])
        self.assertNotIn('/private',json.dumps(e.transition_target_diagnostic))
    def test_unrelated_deleted_executable_remains_unknown(self):
        e=self.reject('/private/secret/application (deleted)')
        self.assertEqual(e.transition_target_diagnostic['path_label'],'OTHER_PATH')
        self.assertTrue(e.transition_target_diagnostic['deleted_suffix'])
    def test_deleted_helper_is_not_parent_or_allowed(self):
        e=self.reject(str(self.spawn)+' (deleted)')
        self.assertEqual(e.transition_target_diagnostic['path_label'],'OTHER_PATH')
        self.assertTrue(e.transition_target_diagnostic['deleted_suffix'])
    def test_forwarding_does_no_proc_io(self):
        e=self.reject(str(self.java))
        with patch.object(s.os,'readlink',side_effect=AssertionError('unexpected reread')),patch.object(s,'read_bounded',side_effect=AssertionError('unexpected read')):
            result=s.cpu_probe_failure_diagnostic(e,self.helper,{})
        self.assertEqual(result['transition_target_diagnostic'],e.transition_target_diagnostic)
        self.assertFalse(result['admission_evidence'])
        self.assertFalse(result['previously_verified'])
        self.assertNotIn(str(self.java),json.dumps(result))
    def test_other_failures_have_no_target_claim(self):
        e=ValueError('CPU probe digest mismatch')
        self.assertNotIn('transition_target_diagnostic',s.cpu_probe_failure_diagnostic(e,self.helper,{}))
    def test_real_owned_child_exe_observation_is_label_only(self):
        # The guard metadata remains synthetic. Only this readlink observation
        # is from a live owned child; it does not prove JDK/helper identity.
        child = REAL_POPEN(
            [sys.executable, '-I', '-S', '-c',
             'import signal,sys; signal.alarm(5); sys.stdin.buffer.read(1)'],
            stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        observed = []
        real_path = Path('/proc') / str(child.pid) / 'exe'
        def observe(path):
            if Path(path) == self.exe:
                self.assertIsNone(child.poll())
                target = fixture.REAL_READLINK(real_path)
                observed.append(target)
                return target
            return fixture.REAL_READLINK(path)
        try:
            with patch.object(s.os, 'readlink', side_effect=observe):
                with self.assertRaisesRegex(ValueError, '^CPU probe transition target forbidden$') as error:
                    self.snapshot()
            self.assertEqual(len(observed), 1)
            self.assertTrue(Path(observed[0]).is_absolute())
            self.assertEqual(error.exception.transition_target_diagnostic,
                dict(admission_evidence=False, identity_verified=False,
                     path_label='OTHER_PATH', deleted_suffix=False))
            self.assertNotIn(observed[0], json.dumps(error.exception.transition_target_diagnostic))
            child.communicate(input=b'x', timeout=2)
            self.assertEqual(child.returncode, 0)
        finally:
            if child.poll() is None:
                child.kill()
            child.communicate(timeout=2)
        self.assertIsNotNone(child.returncode)

    def test_exact_predecessor_preserved(self):
        text=Path(s.__file__).read_text()
        self.assertEqual(hashlib.sha256(without_transition_target_diagnostic(text).encode()).hexdigest(),PREDECESSOR_SHA256)

if __name__=='__main__':unittest.main()
