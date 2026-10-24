"""Synthetic cutoff integration: no game, graphics, subprocess or real signals."""
from contextlib import ExitStack
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch
import supervisor as s

class PairWorkCutoff(unittest.TestCase):
    def test_default_and_narrowed_pair_deadline(self):
        for cutoff, expected in ((None,700),(150,150),(900,700)):
            with self.subTest(cutoff=cutoff),patch.object(s.time,'monotonic',return_value=100):
                pair=s.Pair({'target':'fixture'},Path('/unused'),proc=Mock(),work_cutoff=cutoff)
                self.assertEqual(pair.deadline,expected)
                pair.selector.close()
    def test_invalid_and_expired_cutoff(self):
        for value in (True,False,'150',float('nan'),float('inf'),float('-inf'),0,99,100):
            with self.subTest(value=value),patch.object(s.time,'monotonic',return_value=100):
                with self.assertRaisesRegex(ValueError,'cutoff'):s.pair_deadline(value)
    def test_near_deadline_does_not_renew_six_hundred_seconds(self):
        with patch.object(s.time,'monotonic',return_value=149):
            pair=s.Pair({'target':'fixture'},Path('/unused'),proc=Mock(),work_cutoff=150)
            self.assertEqual(pair.deadline,150)
            with patch.object(s.time,'monotonic',return_value=150):
                with self.assertRaisesRegex(ValueError,'deadline'):pair.pump()
            pair.selector.close()
    def main_fixture(self, cutoff, times):
        stack=ExitStack();self.addCleanup(stack.close)
        folder=stack.enter_context(tempfile.TemporaryDirectory());root=Path(folder)
        argv=['supervisor','--spec',str(root/'spec.json'),'--sha256','a'*64,
              '--execute-reviewed-ci-pair','--destination',str(root/'fresh')]
        if cutoff is not None:argv+=['--work-cutoff-monotonic',str(cutoff)]
        stack.enter_context(patch.object(s.sys,'argv',argv)) if hasattr(s,'sys') else stack.enter_context(patch('sys.argv',argv))
        stack.enter_context(patch.object(s.time,'monotonic',side_effect=times))
        for name,returned in [('clean_path',None),('digest','a'*64),('read_bounded',b'{}'),('decode_json',{}),
                              ('verify_pair_seal',None),('verify_spec',None),('unprivileged_runner',None)]:
            if name=='clean_path':stack.enter_context(patch.object(s,name,side_effect=Path))
            else:stack.enter_context(patch.object(s,name,return_value=returned))
        stack.enter_context(patch.object(s.signal,'signal',return_value=s.signal.SIG_DFL))
        timer=stack.enter_context(patch.object(s.signal,'setitimer'))
        pair=stack.enter_context(patch.object(s,'Pair'))
        pair.return_value.run.return_value={'status':'INCONCLUSIVE','passed':False,'game_launched':False}
        stack.enter_context(patch('builtins.print'))
        stack.enter_context(patch.object(s.subprocess,'Popen',side_effect=AssertionError('No subprocess allowed')))
        return timer,pair
    def test_main_alarm_and_pair_share_immutable_cutoff(self):
        timer,pair=self.main_fixture(150,[100,104])
        self.assertEqual(s.main(),1)
        self.assertEqual(timer.call_args_list[0].args,(s.signal.ITIMER_REAL,46))
        self.assertEqual(pair.call_args.kwargs,{'work_cutoff':150})
        self.assertEqual(timer.call_args_list[-1].args,(s.signal.ITIMER_REAL,0))
    def test_repeated_main_calls_consume_same_parent_cutoff(self):
        for entered, after_validation in ((100,104),(120,124),(145,149)):
            with self.subTest(entered=entered):
                timer,pair=self.main_fixture(150,[entered,after_validation])
                self.assertEqual(s.main(),1)
                self.assertEqual(timer.call_args_list[0].args,(s.signal.ITIMER_REAL,150-after_validation))
                self.assertEqual(pair.call_args.kwargs,{'work_cutoff':150})
                self.doCleanups()

    def test_validation_consumes_budget_and_expired_prevents_pair(self):
        timer,pair=self.main_fixture(150,[100,151])
        with self.assertRaisesRegex(ValueError,'expired during validation'):s.main()
        pair.assert_not_called();timer.assert_not_called()
    def test_main_default_retains_historical_budget(self):
        timer,pair=self.main_fixture(None,[])
        self.assertEqual(s.main(),1)
        self.assertEqual(timer.call_args_list[0].args,(s.signal.ITIMER_REAL,600))
        self.assertEqual(pair.call_args.kwargs,{})
    def test_invalid_cutoff_rejects_before_spec_read(self):
        for value in ('nan','inf','100'):
            with self.subTest(value=value),patch('sys.argv',['supervisor','--spec','/unused','--sha256','a'*64,'--execute-reviewed-ci-pair','--work-cutoff-monotonic',value]),patch.object(s.time,'monotonic',return_value=100),patch.object(s,'clean_path') as read:
                with self.assertRaises(ValueError):s.main()
                read.assert_not_called()

if __name__=='__main__':unittest.main()
