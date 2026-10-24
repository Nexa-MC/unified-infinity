"""Local absolute clock contracts; no network or platform job-start claim."""
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest import mock
import first_step_anchor as a
import round_deadline as r

class FirstStepAnchorTests(unittest.TestCase):
    def fixture(self, root, offset=0):
        env={'GITHUB_ACTIONS':'true','GITHUB_REPOSITORY':a.REPOSITORY,'GITHUB_REF':'refs/heads/'+a.BRANCH,
             'GITHUB_EVENT_NAME':'push','GITHUB_JOB':'serial-pair','GITHUB_RUN_ATTEMPT':'1',
             'GITHUB_RUN_ID':'123','GITHUB_SHA':'a'*40,'RUNNER_NAME':'GitHub Actions 1','RUNNER_TEMP':str(root)}
        expected={'runId':123,'headSha':'a'*40,'runnerName':'GitHub Actions 1','attempt':1}
        return env

    def exercise(self, root, offset=0):
        env=self.fixture(root)
        with mock.patch.dict(os.environ,env,clear=True),mock.patch.object(a.time,'time',return_value=a.utc(a.START_UTC)+offset), mock.patch.object(a.time,'monotonic',return_value=100+offset),mock.patch('builtins.print'):
            anchor=a.create_anchor();self.assertEqual(anchor,a.read_anchor())
            self.assertEqual((root/a.ANCHOR_NAME).stat().st_mode & 0o777,0o600)
            return anchor

    def test_local_context_clock_and_private_file(self):
        with tempfile.TemporaryDirectory() as folder:self.exercise(Path(folder))

    def test_first_step_late_start_rejected_before_request_optimized_or_normal(self):
        source=Path(a.__file__).read_text()
        with tempfile.TemporaryDirectory() as folder:
            env=self.fixture(Path(folder))
            for optimize in (0,1,2):
                for offset in (-1,int(a.utc(a.CUTOFF_UTC)-a.utc(a.START_UTC)-a.JOB_SECONDS-a.CANCELLATION_SECONDS)+1,int(a.utc(a.CUTOFF_UTC)-a.utc(a.START_UTC))):
                    with self.subTest(optimize=optimize,offset=offset),mock.patch.dict(os.environ,env,clear=True), \
                         mock.patch.object(a.time,'time',return_value=a.utc(a.START_UTC)+offset), \
                         self.assertRaises(ValueError):
                        exec(compile(source,'bootstrap','exec',optimize=optimize),{'__name__':'__main__'})

    def test_first_step_exact_latest_boundary_and_no_overwrite(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);self.exercise(root,offset=int(a.utc(a.CUTOFF_UTC)-a.utc(a.START_UTC)-a.JOB_SECONDS-a.CANCELLATION_SECONDS))
            with self.assertRaises(FileExistsError):self.exercise(root,offset=int(a.utc(a.CUTOFF_UTC)-a.utc(a.START_UTC)-a.JOB_SECONDS-a.CANCELLATION_SECONDS))

    def test_anchor_cannot_renew_job_budget_after_later_prepare(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);self.exercise(root)
            env=self.fixture(root)
            with mock.patch.dict(os.environ,env,clear=True),mock.patch.object(a.time,'time',return_value=a.utc(a.START_UTC)+300),mock.patch.object(a.time,'monotonic',return_value=400):
                w=r.admit(r.ROUND_ID)
            self.assertEqual(w.work_seconds,1680)
            self.assertEqual(w.deadline,2080)
            self.assertEqual(w.owner_cutoff()['cleanup_monotonic'],2260)

    def test_anchor_host_context_mode_links_and_mutation_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);anchor=self.exercise(root);env=self.fixture(root);path=root/a.ANCHOR_NAME
            with mock.patch.dict(os.environ,env,clear=True),mock.patch.object(a.time,'time',return_value=a.utc(a.START_UTC)+1),mock.patch.object(a.time,'monotonic',return_value=101):
                for key,value in [('runId',999),('schema',True),('attempt',True),('kind','JOB_START'),
                    ('headSha','b'*40),('roundId','stale'),('bootId','other'),('capturedWall',float('nan')),
                    ('capturedMonotonic',102),('capturedWall',a.utc(a.CUTOFF_UTC))]:
                    path.write_text(json.dumps(dict(anchor,**{key:value})))
                    with self.subTest(key=key),self.assertRaises(ValueError):a.read_anchor()
                path.write_text(json.dumps(anchor));path.chmod(0o644)
                with self.assertRaises(ValueError):a.read_anchor()
                path.chmod(0o600);os.link(path,root/'hardlink')
                with self.assertRaises(ValueError):a.read_anchor()
                (root/'hardlink').unlink();path.rename(root/'target');path.symlink_to(root/'target')
                with self.assertRaises(OSError):a.read_anchor()

    def test_context_and_missing_anchor_fail_closed(self):
        with tempfile.TemporaryDirectory() as folder:
            env=self.fixture(Path(folder))
            for key,value in [('GITHUB_RUN_ATTEMPT','2'),('GITHUB_JOB','other'),('GITHUB_REPOSITORY','other'),
                              ('GITHUB_SHA','x'),('GITHUB_RUN_ID','01')]:
                with mock.patch.dict(os.environ,dict(env,**{key:value}),clear=True),self.assertRaises(ValueError):a.context()
            with mock.patch.dict(os.environ,env,clear=True),self.assertRaises(FileNotFoundError):a.read_anchor()

    def test_first_step_never_claims_actual_job_start_or_remaining_time(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);anchor=self.exercise(root,offset=120);env=self.fixture(root)
            self.assertNotIn('jobStartUtc',anchor);self.assertEqual(anchor['kind'],'FIRST_STEP_LOCAL_CLOCK')
            with mock.patch.dict(os.environ,env,clear=True),mock.patch.object(a.time,'time',return_value=a.utc(a.START_UTC)+120),mock.patch.object(a.time,'monotonic',return_value=220):
                w=r.admit(r.ROUND_ID)
            self.assertEqual(w.deadline,2200);self.assertEqual(w.work_seconds,1980)
            self.assertFalse(w.receipt()['jobStartKnown']);self.assertFalse(w.receipt()['remainingJobTimeGuaranteed'])

    def test_no_network_code_or_api_dependency(self):
        source=Path(a.__file__).read_text()
        for forbidden in ('urllib','requests','api.github.com','Authorization','choose_job','jobStartUtc'):
            self.assertNotIn(forbidden,source)

    def test_platform_early_timeout_cannot_extend_absolute_envelope(self):
        cutoff=a.utc(a.CUTOFF_UTC)
        for offset in (0,60,120,int(a.utc(a.CUTOFF_UTC)-a.utc(a.START_UTC)-a.JOB_SECONDS-a.CANCELLATION_SECONDS)):
            first=a.utc(a.START_UTC)+offset
            for earlier in (0,60,600,3600):
                actual_start=first-earlier
                self.assertLessEqual(actual_start+a.JOB_SECONDS+a.CANCELLATION_SECONDS,cutoff)
        # This proves an upper bound, not local cleanup before actual timeout.
        self.assertLess(a.utc(a.START_UTC)-600+a.JOB_SECONDS,a.utc(a.START_UTC)+1980+180)

if __name__=='__main__':unittest.main()
