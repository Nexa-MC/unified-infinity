"""Synthetic orchestration/receipt regression only; no game or CI acceptance."""
from contextlib import ExitStack
from pathlib import Path
from types import SimpleNamespace
from unittest import mock
import json
import subprocess
import sys
import tempfile
import unittest
import driver as d

class DiagnosticDriverTests(unittest.TestCase):
    def test_paths_disjoint(self):
        sets=[set(d.driver_paths('/fixture',r,g).values()) for r,g in [(False,False),(True,False),(True,True)]]
        for a,b in [(0,1),(0,2),(1,2)]:self.assertFalse(sets[a]&sets[b])

    def test_requires_refreshed_selection(self):
        with self.assertRaisesRegex(ValueError,'requires explicit refreshed'):
            d.prepare('/absent','/absent',diagnostic_fml=True)

    def test_ordinary_comparison_unchanged(self):
        reports={k:{'passed':True,'status':'PASS'} for k in ('native-neoforge','unified')}
        result=d.semantic_comparison(reports)
        self.assertEqual(result['status'],'BOTH_HOST_NONCE_CONTROLS_PASSED')
        self.assertNotIn('diagnostic_only',result)
        reports['unified']['passed']=False
        with self.assertRaises(ValueError):d.semantic_comparison(reports)

    def run_driver(self,raw_change=None,cleanup_fail=False,timeout=False):
        with tempfile.TemporaryDirectory() as tmp,ExitStack() as stack:
            repo=Path(tmp)/'repo';repo.mkdir();consumer=Path(tmp)/'consumer';consumer.mkdir()
            manifest=consumer/'diagnostic-manifest.json';manifest.write_text('{"fixture":true}')
            pin=d.compile_probe.record(manifest)
            profile={'manifest_path':pin['path'],'manifest_sha256':pin['sha256'],
                     'diagnostic_only':True,'baseline_acceptance':False}
            plan={'repoRoot':str(repo),'consumerRoot':str(consumer),'sourceCodeFiles':{},'dataFiles':{},
                  'graphics':{},'runtime':{'steps':[]},'diagnostic_only':True,'refreshedProfile':{'fixture':True}}
            d.driver_paths(consumer,True,True)['plan'].write_text(json.dumps(plan))
            stack.enter_context(mock.patch.dict(d.os.environ,{'GITHUB_ACTIONS':'true','GITHUB_REPOSITORY':d.REPO,
                'GITHUB_REF':'refs/heads/'+d.BRANCH,'GITHUB_EVENT_NAME':'push'},clear=True))
            stack.enter_context(mock.patch.object(d.os,'getuid',return_value=1000))
            stack.enter_context(mock.patch.object(d.time,'monotonic',return_value=100))
            stack.enter_context(mock.patch.object(d.signal,'signal',return_value=0))
            stack.enter_context(mock.patch('builtins.print'))
            stack.enter_context(mock.patch.object(d,'profile_options',return_value={'profile':'p','build_proof':'b'}))
            stack.enter_context(mock.patch.object(d,'refreshed_binding',return_value={'fixture':True}))
            stack.enter_context(mock.patch.object(d,'restore_with_deadline'))
            for obj,name in [(d.runtime_restore,'verify'),(d.build_candidate,'execute'),(d.compile_probe,'execute'),(d.pair_assembly,'assemble')]:
                stack.enter_context(mock.patch.object(obj,name))
            build=mock.Mock(return_value=manifest);assembly=mock.Mock()
            refreshed=SimpleNamespace(validate_full_build=mock.Mock(return_value={k:'fixture' for k in ['profileSha256','sourceIdentity','candidateIdentity','candidateIdentityKind']}),pin=mock.Mock(return_value={'fixture':True}))
            stack.enter_context(mock.patch.dict(sys.modules,{'diagnostic_fml_build':SimpleNamespace(execute=build),
                'diagnostic_pair_assembly':SimpleNamespace(assemble=assembly),'refreshed_candidate':refreshed}))
            stack.enter_context(mock.patch.object(d.graphics_runner,'availability',return_value={'missingInputs':[]}))
            graphics=stack.enter_context(mock.patch.object(d.graphics_runner,'execute',return_value={'status':'GRAPHICS_PREFLIGHT_READY','readyPath':'ready','handle':'handle'}))
            stop=stack.enter_context(mock.patch.object(d.graphics_runner,'stop',side_effect=OSError('cleanup fixture') if cleanup_fail else None,return_value={'status':'GRAPHICS_COLLECTOR_CLEANED'}))
            seal=stack.enter_context(mock.patch.object(d.seal_pair,'create',return_value={'supervisor':{'path':'fixture'},'spec':{'path':'fixture','sha256':'0'*64}}))
            waits=[];terms=[]
            def spawn(args,**kwargs):
                destination=Path(args[args.index('--destination')+1]);destination.mkdir()
                report={'passed':True,'status':'PASS','diagnostic_only':True,'baseline_acceptance':False,'diagnostic_profile':profile.copy()}
                if raw_change:raw_change(report,destination.name)
                (destination/'result.json').write_text(json.dumps(report))
                class Pair:
                    done=False
                    def wait(self,timeout):
                        waits.append(timeout)
                        if not self.done and timeout!=d.PAIR_CLEANUP_SECONDS and DiagnosticDriverTests.timeout_fixture:
                            raise subprocess.TimeoutExpired('fixture',timeout)
                        self.done=True;return 0
                    def poll(self):return 0 if self.done else None
                    def terminate(self):terms.append(True)
                return Pair()
            DiagnosticDriverTests.timeout_fixture=timeout
            stack.enter_context(mock.patch.object(d.subprocess,'Popen',side_effect=spawn))
            error=None
            try:d.execute(repo,consumer,profile='p',build_proof='b',work_seconds=1000,diagnostic_fml=True)
            except BaseException as e:error=e
            result=json.loads(d.driver_paths(consumer,True,True)['result'].read_text())
            self.assertFalse(result['gameAcceptance']);self.assertFalse(result['baselineAcceptance']);self.assertFalse(result['fullApiCompatibility']);self.assertTrue(result['diagnostic_only'])
            build.assert_called_once_with(repo,consumer,deadline=1100,profile='p',build_proof='b')
            assembly.assert_called_once_with(repo,consumer,manifest,profile='p',build_proof='b')
            self.assertEqual(graphics.call_args.kwargs['deadline'],1100)
            self.assertTrue(all(c.kwargs['diagnostic_manifest']==manifest for c in seal.call_args_list))
            self.assertFalse(d.driver_paths(consumer,True)['result'].exists())
            return result,error,waits,terms,stop.call_count

    def test_two_synthetic_passes_never_promote(self):
        r,e,waits,terms,stops=self.run_driver()
        self.assertIsNone(e);self.assertEqual(r['status'],'DIAGNOSTIC_TRANSPORT_CONTROLS_PASSED')
        self.assertEqual(waits,[d.PAIR_SECONDS,d.PAIR_SECONDS]);self.assertFalse(terms);self.assertEqual(stops,1)

    def test_missing_mixed_mismatched_metadata_rejected(self):
        changes=[lambda r:r.pop('diagnostic_profile'),lambda r:r.update(diagnostic_only=False),
                 lambda r:r.update(baseline_acceptance=True),
                 lambda r:r['diagnostic_profile'].update(manifest_sha256='f'*64),
                 lambda r:r['diagnostic_profile'].update(manifest_path='elsewhere'),
                 lambda r:r['diagnostic_profile'].update(diagnostic_only=False),
                 lambda r:r['diagnostic_profile'].update(diagnostic_only=1),
                 lambda r:r['diagnostic_profile'].update(baseline_acceptance=0)]
        for change in changes:
            with self.subTest(change=change):
                r,e,*_=self.run_driver(raw_change=lambda r,t:change(r) if t=='unified' else None)
                self.assertIsInstance(e,ValueError);self.assertEqual(r['status'],'FAILED')

    def test_cleanup_failure_cannot_promote(self):
        r,e,*_=self.run_driver(cleanup_fail=True)
        self.assertIsInstance(e,RuntimeError);self.assertEqual(r['status'],'CLEANUP_FAILED')

    def test_timeout_retains_owned_cleanup_and_budget(self):
        r,e,waits,terms,stops=self.run_driver(timeout=True)
        self.assertIsInstance(e,RuntimeError);self.assertEqual(waits,[d.PAIR_SECONDS,d.PAIR_CLEANUP_SECONDS])
        self.assertEqual(terms,[True]);self.assertEqual(stops,1);self.assertTrue(r['pairCleanup']['reaped'])

if __name__=='__main__':unittest.main()
