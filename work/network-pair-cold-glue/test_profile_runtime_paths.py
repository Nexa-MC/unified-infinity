"""Source-only opt-in/path rejection tests. No build, launch or successful seal.

Tests exercise real selection/path functions and fail-closed boundaries. The
injected rejection below verifies call propagation, not a successful build.
"""
import ast
from contextlib import ExitStack
import json
from pathlib import Path
import tempfile
import unittest
from unittest import mock

import driver
import refreshed_candidate as refreshed
import seal_pair


class ProfileRuntimePaths(unittest.TestCase):
    def prepare_without_processes(self,root,**kwargs):
        repo=Path(driver.__file__).resolve().parents[2]
        with ExitStack() as patches:
            for owner,name in ((driver.bounded_process,'run'),(driver.subprocess,'run'),(driver.subprocess,'Popen')):
                patches.enter_context(mock.patch.object(owner,name,side_effect=AssertionError('Source preparation must not start processes')))
            return driver.prepare(repo,root,**kwargs)

    def test_real_historical_source_only_preparation(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder)/'historical'
            result=self.prepare_without_processes(root)
            self.assertEqual(result['status'],'COLD_DRIVER_PREPARED_EXECUTION_UNTESTED')
            self.assertNotIn('refreshedProfile',result)
            self.assertEqual(json.loads((root/'cold-driver-plan.json').read_text()),result)
            self.assertFalse((root/'refreshed-driver-plan.json').exists())
            for key in ('downloadsStarted','jvmStarted','gameLaunched'):self.assertIs(result[key],False)

    def test_real_refreshed_source_only_preparation_without_binary_dependencies(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder)/'refreshed'
            result=self.prepare_without_processes(root,profile=refreshed.PROFILE_PATH,build_proof=refreshed.PROOF_PATH)
            self.assertEqual(result['status'],'REFRESHED_DRIVER_PREPARED_EXECUTION_UNTESTED')
            self.assertEqual(json.loads((root/'refreshed-driver-plan.json').read_text()),result)
            self.assertFalse((root/'cold-driver-plan.json').exists())
            self.assertEqual(result['refreshedProfile']['profile'],refreshed.pin(root,refreshed.PROFILE_PATH))
            self.assertEqual(result['build']['profileSha256'],result['refreshedProfile']['profile']['sha256'])
            self.assertEqual(result['build']['proofPath'],refreshed.PROOF_PATH)
            self.assertFalse(refreshed.local(root,refreshed.PROOF_PATH).exists())
            for key in ('downloadsStarted','jvmStarted','gameLaunched'):self.assertIs(result[key],False)
            profile=refreshed.load_profile(root,refreshed.PROFILE_PATH)
            dependencies=refreshed.identity_dependency_pins(root,profile,verify_bytes=False)
            self.assertEqual(len(dependencies),169)
            self.assertFalse(any(refreshed.local(root,row['path']).exists() for row in dependencies))
            with self.assertRaises((ValueError,OSError)):
                refreshed.validate_full_build(root,refreshed.PROFILE_PATH,refreshed.PROOF_PATH)
            self.assertFalse((root/'work/network-pair-refreshed-assembly').exists())
            self.assertFalse((root/'work/api1/ci/pair-seals-refreshed').exists())

    def test_historical_selection_remains_default(self):
        self.assertEqual(driver.profile_options(), {})
        with tempfile.TemporaryDirectory() as folder:
            paths=driver.driver_paths(folder)
            self.assertEqual(paths['plan'],Path(folder)/'cold-driver-plan.json')
            self.assertEqual(paths['result'],Path(folder)/'cold-pair-result.json')
            self.assertEqual(paths['evidence'],Path(folder)/'runtime-evidence')
            self.assertEqual(list(Path(folder).iterdir()),[])

    def test_refreshed_driver_outputs_are_disjoint(self):
        root=Path('/unused-test-root')
        old,new=driver.driver_paths(root),driver.driver_paths(root,True)
        self.assertEqual(set(old),set(new))
        self.assertFalse(set(old.values()) & set(new.values()))
        self.assertEqual(new['plan'],root/'refreshed-driver-plan.json')
        self.assertEqual(new['result'],root/'refreshed-pair-result.json')
        self.assertEqual(new['evidence'],root/'runtime-evidence-refreshed')

    def test_both_exact_explicit_arguments_propagate(self):
        expected={'profile':refreshed.PROFILE_PATH,'build_proof':refreshed.PROOF_PATH}
        self.assertEqual(driver.profile_options(**expected),expected)
        self.assertEqual(driver.profile_options(Path(refreshed.PROFILE_PATH),Path(refreshed.PROOF_PATH)),expected)

    def test_partial_selection_is_rejected(self):
        for kwargs in ({'profile':refreshed.PROFILE_PATH},{'build_proof':refreshed.PROOF_PATH}):
            with self.subTest(kwargs=kwargs), self.assertRaisesRegex(ValueError,'both'):
                driver.profile_options(**kwargs)

    def test_absolute_alias_escape_and_other_proof_are_rejected(self):
        for profile in ('/tmp/profile.json','../profile.json','work/other.json','./'+refreshed.PROFILE_PATH):
            with self.subTest(profile=profile), self.assertRaisesRegex(ValueError,'exact bundled'):
                driver.profile_options(profile,refreshed.PROOF_PATH)
        for proof in ('/tmp/proof.json','../proof.json','observed-tuple.json','cold-build-result.json'):
            with self.subTest(proof=proof), self.assertRaisesRegex(ValueError,'fresh refreshed'):
                driver.profile_options(refreshed.PROFILE_PATH,proof)

    def test_prepare_rejects_incomplete_selection_before_source_writes(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);repo=root/'repo';repo.mkdir();consumer=root/'consumer'
            with self.assertRaisesRegex(ValueError,'both'):
                driver.prepare(repo,consumer,profile=refreshed.PROFILE_PATH)
            self.assertFalse(consumer.exists())

    def test_non_ci_execution_is_still_rejected_before_any_work(self):
        with tempfile.TemporaryDirectory() as folder, mock.patch.dict(driver.os.environ,{'GITHUB_ACTIONS':'false'},clear=True):
            root=Path(folder);repo=root/'repo';repo.mkdir();consumer=root/'consumer';consumer.mkdir()
            with self.assertRaisesRegex(ValueError,'separately reviewed exact future pair branch'):
                driver.execute(repo,consumer,profile=refreshed.PROFILE_PATH,build_proof=refreshed.PROOF_PATH)
            self.assertEqual(list(consumer.iterdir()),[])

    def test_seal_rejects_missing_profile_or_proof_without_outputs(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);repo=root/'repo';repo.mkdir();consumer=root/'consumer';consumer.mkdir()
            for kwargs in ({'profile':refreshed.PROFILE_PATH},{'build_proof':refreshed.PROOF_PATH}):
                with self.subTest(kwargs=kwargs), self.assertRaisesRegex(ValueError,'both'):
                    seal_pair.create(repo,consumer,'unified',root/'missing-graphics.json','test rejection only',**kwargs)
                self.assertEqual(list(consumer.iterdir()),[])

    def test_seal_propagates_full_proof_rejection_before_assembly_graphics_or_jdk(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);repo=root/'repo';repo.mkdir();consumer=root/'consumer';consumer.mkdir()
            with mock.patch.object(refreshed,'validate_full_build',side_effect=ValueError('full proof remains missing')) as gate:
                with self.assertRaisesRegex(ValueError,'full proof remains missing'):
                    seal_pair.create(repo,consumer,'unified',root/'missing-graphics.json','test rejection only',
                                     profile=refreshed.PROFILE_PATH,build_proof=refreshed.PROOF_PATH)
            gate.assert_called_once_with(consumer,refreshed.PROFILE_PATH,refreshed.PROOF_PATH)
            self.assertEqual(list(consumer.iterdir()),[])

    def test_actual_missing_profile_cannot_reach_sealing(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);repo=root/'repo';repo.mkdir();consumer=root/'consumer';consumer.mkdir()
            with self.assertRaises((ValueError,OSError)):
                seal_pair.create(repo,consumer,'unified',root/'missing-graphics.json','test rejection only',
                                 profile=refreshed.PROFILE_PATH,build_proof=refreshed.PROOF_PATH)
            self.assertEqual(list(consumer.iterdir()),[])

    def test_shared_serialization_and_distinct_specs_preserve_frozen_supervisor(self):
        # No synthetic launch spec is manufactured to check this invariant.
        source=Path(seal_pair.__file__).read_text();ast.parse(source)
        self.assertIn("out=api/('ci/pair-seals-refreshed' if refreshed else 'ci/pair-seals')",source)
        self.assertIn("serial=api/'ci/pair-seals'",source)
        self.assertIn("'pair_lock':str(serial/'serial-pair.lock')",source)
        self.assertIn('seal_indigo_baseline(target,roles,inputs,serial)',source)
        self.assertIn('s.verify_spec(spec);s.verify_graphics(spec,s.Proc())',source)
        self.assertEqual(seal_pair.SUPERVISOR_SHA,'08d3cb82399f6167099307c7bc47ebaaeaff203c2decaf3effe07ac8a6c8cbe8')


if __name__=='__main__':unittest.main()
