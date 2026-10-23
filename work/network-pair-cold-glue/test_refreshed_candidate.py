"""Synthetic verifier unit tests; these never produce candidate acceptance."""
import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest import mock
import refreshed_candidate as r
import build_candidate as b

class RefreshedTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)
        self.profile=json.loads((Path(r.__file__).parent/'profiles/ffapi-20261023.json').read_text())
        self.profile['requiredTasks']={'core':[':check'], 'product':[':check'], 'fml':[':jar']}
        self.commands=r.normalized_commands(self.root,self.profile)
        self.session={'sessionId':'new-invocation','startedUtc':'2026-10-23T11:00:00+00:00','inputsBinding':'inputs', 'commandsDigest':r.canonical_digest(self.commands)}
        self.log=self.root/'build.log';self.log.write_text('> Task :check\nBUILD SUCCESSFUL\n')
        cmd=self.commands['core']
        self.receipt={'schema':'portable-refreshed-build-receipt-v1','role':'core','profileSha256':r.PROFILE_SHA256,
                      'sessionId':self.session['sessionId'],'inputsBefore':'inputs','inputsAfter':'inputs',
                      'startedUtc':'2026-10-23T11:01:00+00:00','finishedUtc':'2026-10-23T11:02:00+00:00',
                      'exitCode':0,'gameTask':False,'workers':1,'activeProcessors':1,'perJvmHeapMiB':512,'timeoutSeconds':100,
                      'command':cmd,'commandDigest':r.canonical_digest(cmd),
                      'environment':{k:v.replace(str(self.root),'${CONSUMER}') for k,v in b.refreshed_environment(self.root,'core').items()},
                      'cwd':'${CONSUMER}/work/api1','log':r.pin(self.root,self.log),'outputs':[]}
    def validate(self,receipt=None):
        path=self.root/'receipt.json';path.write_text(json.dumps(receipt or self.receipt))
        return r.validate_receipt(self.root,r.pin(self.root,path),'core',self.profile,self.session)
    def test_valid_synthetic_receipt(self):self.assertEqual(self.validate()['exitCode'],0)
    def test_stale_session(self):
        self.receipt['sessionId']='old';self.assertRaises(r.Invalid,self.validate)
    def test_mixed_profile(self):
        self.receipt['profileSha256']='0'*64;self.assertRaises(r.Invalid,self.validate)
    def test_changed_inputs(self):
        self.receipt['inputsAfter']='changed';self.assertRaises(r.Invalid,self.validate)
    def test_predates_session(self):
        self.receipt['startedUtc']='2025';self.assertRaises(r.Invalid,self.validate)
    def test_partial_log(self):
        self.log.write_text('> Task :check\n');self.receipt['log']=r.pin(self.root,self.log);self.assertRaises(r.Invalid,self.validate)
    def test_missing_mandatory_task(self):
        self.log.write_text('BUILD SUCCESSFUL\n');self.receipt['log']=r.pin(self.root,self.log);self.assertRaises(r.Invalid,self.validate)
    def test_nonexecuted_task(self):
        for state in ('NO-SOURCE','SKIPPED','FAILED'):
            with self.subTest(state=state):
                self.log.write_text('> Task :check '+state+'\nBUILD SUCCESSFUL\n');self.receipt['log']=r.pin(self.root,self.log);self.assertRaises(r.Invalid,self.validate)
    def mutate_command(self,fn):
        fn(self.receipt['command']);self.receipt['commandDigest']=r.canonical_digest(self.receipt['command']);self.assertRaises(r.Invalid,self.validate)
    def test_verification_disabled(self):self.mutate_command(lambda x:x.append('--dependency-verification=off'))
    def test_conflicting_worker(self):self.mutate_command(lambda x:x.append('--max-workers=8'))
    def test_conflicting_heap(self):self.mutate_command(lambda x:x.append('-Dorg.gradle.jvmargs=-Xmx4g'))
    def test_wrong_project(self):self.mutate_command(lambda x:x.__setitem__(x.index('-p')+1,'${CONSUMER}/wrong'))
    def test_wrong_task(self):self.mutate_command(lambda x:x.append('runClient'))
    def test_wrong_jdk(self):self.mutate_command(lambda x:x.append('-Dorg.gradle.java.home=/usr/lib/jvm/default'))
    def test_wrong_gradle(self):self.mutate_command(lambda x:x.__setitem__(0,'/usr/bin/gradle'))
    def test_changed_java_home(self):
        self.receipt['environment']['JAVA_HOME']='/usr/lib/jvm/default';self.assertRaises(r.Invalid,self.validate)
    def test_unbounded_env_heap(self):
        self.receipt['environment']['_JAVA_OPTIONS']='-Xmx4g';self.assertRaises(r.Invalid,self.validate)
    def test_wrong_cwd(self):
        self.receipt['cwd']='${CONSUMER}/other';self.assertRaises(r.Invalid,self.validate)
    def test_stale_command_digest(self):
        self.receipt['commandDigest']='old';self.assertRaises(r.Invalid,self.validate)
    def test_stale_plan_digest(self):
        self.session['commandsDigest']='old';self.assertRaises(r.Invalid,self.validate)
    def test_path_escape(self):
        for path in ('../outside','/absolute','a/../b','a\\b','./a'):
            with self.subTest(path=path):self.assertRaises(r.Invalid,r.local,self.root,path)
    def test_symlink_escape(self):
        (self.root/'link').symlink_to('/tmp');self.assertRaises(r.Invalid,r.local,self.root,'link/file')
    def test_mutated_pin(self):
        row=r.pin(self.root,self.log);self.log.write_text('changed');self.assertRaises(r.Invalid,r.check_pin,self.root,row)
    def test_observed_only_proof_rejected(self):
        (self.root/'proof.json').write_text(json.dumps({'schema':'observed-tuple','runtimeAcceptance':False}))
        with mock.patch.object(r,'load_profile',return_value=self.profile):
            self.assertRaises(r.Invalid,r.validate_full_build,self.root,'profile.json','proof.json')
    def test_dependency_prepare_vs_execution(self):
        identity={'dependencies':[{'filename':'lib.jar','sha256':'a'*64}]}
        lock={'artifacts':[{'filename':'lib.jar','sha256':'a'*64,'bytes':1,'path':'libraries/lib.jar'}]}
        p={'expectedIdentity':{},'dependencyLock':{}}
        with mock.patch.object(r,'read_pin',side_effect=[identity,lock]):
            self.assertEqual(len(r.identity_dependency_pins(self.root,p,verify_bytes=False)),1)
        with mock.patch.object(r,'read_pin',side_effect=[identity,lock]):
            self.assertRaises(r.Invalid,r.identity_dependency_pins,self.root,p)
    def test_historical_plan_unchanged_identity(self):
        recipe=b.plan(self.root)
        self.assertEqual(recipe['baseSourceIdentity'],'54e5f302c1bad0de54a6845a50b128d6a2aa9f4fb9d44ec14c84c754d7fb21f6')
        self.assertEqual(recipe['expectedCandidateIdentity'],'ce4b907075e2892f39ee13ed75d19afc193ad602d9ecc8cb5eca03cea4181844')
        self.assertNotIn('--profile',recipe['coreCommand'])
    def test_profile_dispatch_only_explicit(self):
        with mock.patch.object(b,'prepare_refreshed',return_value='new') as selected:
            self.assertEqual(b.prepare(self.root,profile='profile.json'),'new');selected.assert_called_once_with(self.root,'profile.json')
    def test_profile_file_digest(self):
        self.assertEqual(r.sha(Path(r.__file__).parent/r.PROFILE_PATH.split('/')[-2]/'ffapi-20261023.json'),r.PROFILE_SHA256)

if __name__=='__main__':unittest.main()
