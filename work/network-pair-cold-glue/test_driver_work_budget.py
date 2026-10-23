"""Optional shorter work deadline; no external commands, native or Java execution."""
from contextlib import ExitStack
import json
from pathlib import Path
import tempfile
import unittest
from unittest import mock
import driver as d

class WorkBudgetTests(unittest.TestCase):
    def test_default_is_historical_limit(self):
        self.assertEqual(d.WORK_SECONDS,2520)
        self.assertEqual(d.work_budget(),2520)

    def test_valid_narrowing_and_upper_endpoint(self):
        for value in (1,1500,2520):
            self.assertEqual(d.work_budget(value),value)

    def test_invalid_rejected_before_environment_paths_or_processes(self):
        for value in (0,-1,2521,100000,True,False,1.0,'1500'):
            with self.subTest(value=value), mock.patch.object(d.os,'getuid',side_effect=AssertionError('no platform probe')), mock.patch.object(d.subprocess,'run',side_effect=AssertionError('no process')):
                with self.assertRaisesRegex(ValueError,'work-seconds'):
                    d.execute('/does-not-exist','/does-not-exist',work_seconds=value)

    def test_real_execute_routes_short_deadline_and_retains_cleanup(self):
        for budget,expected in ((None,2620),(1500,1600),(1,101)):
            with self.subTest(budget=budget), tempfile.TemporaryDirectory() as folder, ExitStack() as patches:
                root=Path(folder);repo=root/'repo';repo.mkdir();consumer=root/'consumer';consumer.mkdir()
                plan={'repoRoot':str(repo),'consumerRoot':str(consumer),'sourceCodeFiles':{},'dataFiles':{},'graphics':{},'runtime':{'steps':[]}}
                (consumer/'cold-driver-plan.json').write_text(json.dumps(plan))
                patches.enter_context(mock.patch.dict(d.os.environ,{'GITHUB_ACTIONS':'true','GITHUB_REPOSITORY':d.REPO,'GITHUB_REF':'refs/heads/'+d.BRANCH,'GITHUB_EVENT_NAME':'push'},clear=True))
                patches.enter_context(mock.patch.object(d.os,'getuid',return_value=1000))
                patches.enter_context(mock.patch.object(d.time,'monotonic',return_value=100))
                patches.enter_context(mock.patch.object(d.subprocess,'run',side_effect=AssertionError('no subprocess')))
                patches.enter_context(mock.patch('builtins.print'))
                ensure=patches.enter_context(mock.patch.object(d.runner_dependencies,'ensure',side_effect=RuntimeError('stop before setup')))
                with self.assertRaisesRegex(RuntimeError,'stop before setup'):
                    d.execute(repo,consumer,allow_runner_package=True,work_seconds=budget)
                ensure.assert_called_once_with({},consumer,expected,allow_install=True)
                result=json.loads((consumer/'cold-pair-result.json').read_text())
                self.assertFalse(result['gameAcceptance'])
                self.assertEqual(result['pairCleanup']['status'],'NO_ACTIVE_PAIR')
                self.assertTrue(result['pairCleanup']['reaped'])

if __name__=='__main__':unittest.main()
