"""Focused source/ZIP fixtures. Full refreshed-build and game pipeline NOT exercised."""
from pathlib import Path
from types import SimpleNamespace
from unittest import mock
import ast
import hashlib
import inspect
import json
import tempfile
import unittest
import warnings
import zipfile
import diagnostic_pair_assembly as d
import seal_pair

PLACEHOLDER=b'{"schema":1,"approved":false}\n'

class DiagnosticAssemblyTests(unittest.TestCase):
    def test_exact_path_entry_rewrite_and_no_clock_renewal(self):
        old=Path('/fixture/baseline');new=Path('/fixture/diagnostic')
        stock=Path('/fixture/lib/loader.jar');derived=Path('/fixture/derived/loader.jar')
        command=['/jdk/bin/java','-p',str(stock)+':'+str(old/'libraries/other.jar'),
                 '-DlegacyClassPath='+str(stock)+':'+str(old/'a.jar'), '--gameDir',str(old),
                 '--untouched','/fixture/baseline-other', '--cutoff','1234.125']
        translated=d.rewrite_command(command,old,new,stock,derived)
        self.assertEqual(translated,['/jdk/bin/java','-p',str(derived)+':'+str(new/'libraries/other.jar'),
                 '-DlegacyClassPath='+str(derived)+':'+str(new/'a.jar'),'--gameDir',str(new),
                 '--untouched','/fixture/baseline-other','--cutoff','1234.125'])
        self.assertEqual(command[-1],'1234.125')
        self.assertNotIn('time.',inspect.getsource(d.rewrite_command))

    def test_absent_embedded_and_argument_file_stock_rejected(self):
        for command in [['java','-cp','/lib/loader.jar.extra'],['java','@args.txt'],
                        ['java','-cp','/lib/loader.jar','-Dnote=/lib/loader.jar.extra']]:
            with self.subTest(command=command),self.assertRaises(ValueError):
                d.rewrite_command(command,Path('/old'),Path('/new'),Path('/lib/loader.jar'),Path('/derived.jar'))

    def test_relocate_boundary_recursive_and_canonical_consumer_validation(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);old=root/'old';new=root/'new';old.mkdir();new.mkdir()
            value={'exact':str(old),'nested':[str(old/'a'),str(root/'old-other/a')],'unchanged':5}
            result=d.relocate(value,old,new)
            self.assertEqual(result,{'exact':str(new),'nested':[str(new/'a'),str(root/'old-other/a')],'unchanged':5})
            self.assertEqual(value['exact'],str(old))
            with self.assertRaises(ValueError):d.base.local(root,d.relocate(str(old/'../escape'),old,new))
            with self.assertRaises(ValueError):d.base.local(root,'/outside/fixture')
            (root/'link').symlink_to(new,target_is_directory=True)
            with self.assertRaises(ValueError):d.base.local(root,root/'link/file')

    def configure(self,kind='valid',existing=None,validator_failure=False):
        temp=tempfile.TemporaryDirectory();self.addCleanup(temp.cleanup);root=Path(temp.name)
        derivative=root/'source.jar';manifest=root/'manifest.json';manifest.write_text('{"fixture":true}')
        install=root/'installation';install.mkdir();owner=install/'boot.jar'
        spec_path=root/'spec.json';out=root/'output'
        names=[('unchanged.class',b'fixture-not-bytecode')]
        if kind!='missing':names.append((d.POLICY,PLACEHOLDER if kind not in ('configured','changed') else b'{"approved":true}'))
        if kind=='signed':names.append(('META-INF/FIXTURE.SF',b'signature fixture'))
        if kind=='duplicate':names.append(('unchanged.class',b'duplicate'))
        with warnings.catch_warnings():
            warnings.simplefilter('ignore',UserWarning)
            with zipfile.ZipFile(derivative,'w') as z:
                for n,b in names:z.writestr(n,b)
        before=derivative.read_bytes()
        if existing=='owner':owner.write_bytes(b'existing')
        if existing=='output':out.mkdir()
        policy={'installationDirectory':str(install),'artifacts':[{'role':'BOOT_OWNER','path':'boot.jar'}],
                'environment':{},'approved':True,'fixture_policy':True}
        args=['-cp',str(owner),'FixtureMain']
        prepare=mock.Mock(return_value=(policy,args,'/fixture/java'))
        def validate(receipt_path,expected,actual_args,environment):
            receipt=json.loads(receipt_path.read_text())
            self.assertEqual(expected,hashlib.sha256(receipt_path.read_bytes()).hexdigest())
            self.assertEqual(actual_args,args);self.assertEqual(environment,{})
            self.assertTrue(receipt['diagnostic_only']);self.assertFalse(receipt['baseline_acceptance'])
            with zipfile.ZipFile(owner) as archive:
                raw=archive.read(d.POLICY)
                self.assertEqual(json.loads(raw),policy)
                self.assertEqual(archive.read('unchanged.class'),b'fixture-not-bytecode')
                self.assertEqual(len(archive.namelist()),len(set(archive.namelist())))
            self.assertEqual(receipt['installationPolicySha256'],hashlib.sha256(raw).hexdigest())
            if validator_failure:raise ValueError('fixture validator failure')
            return {'classOwnerCount':1,'gameLaunched':False,'fixture_validation_only':True}
        validator=mock.Mock(side_effect=validate)
        assembler=SimpleNamespace(prepare=prepare,v=SimpleNamespace(validate=validator))
        error=None;result=None
        try:result=d.configure_unified(assembler,{'launchSource':{'fixture':True}},spec_path,derivative,manifest,out)
        except ValueError as e:error=e
        self.assertEqual(derivative.read_bytes(),before)
        return root,owner,out,result,error,prepare,validator

    def test_fresh_unapproved_derivative_gets_new_policy_without_changing_source(self):
        root,owner,out,result,error,prepare,validator=self.configure()
        self.assertIsNone(error);self.assertEqual(prepare.call_count,1);self.assertEqual(validator.call_count,1)
        command,report,pins=result
        self.assertEqual(command,['/fixture/java','-cp',str(owner),'FixtureMain'])
        self.assertTrue(report['diagnostic_only']);self.assertFalse(report['baseline_acceptance'])
        self.assertFalse(report['jvmStarted']);self.assertFalse(report['gameLaunched'])
        self.assertEqual(len(pins),3)

    def test_duplicate_signed_configured_missing_placeholder_refused(self):
        for kind in ['duplicate','signed','configured','missing']:
            with self.subTest(kind=kind):
                root,owner,out,result,error,prepare,validator=self.configure(kind)
                self.assertIsInstance(error,ValueError);self.assertIsNone(result)
                self.assertFalse(owner.exists());self.assertEqual(validator.call_count,0)

    def test_existing_owner_and_output_refused(self):
        for existing in ['owner','output']:
            with self.subTest(existing=existing):
                root,owner,out,result,error,prepare,validator=self.configure(existing=existing)
                self.assertIsInstance(error,ValueError);self.assertIsNone(result)
                self.assertEqual(validator.call_count,0)
                if existing=='owner':self.assertEqual(owner.read_bytes(),b'existing')
                else:self.assertFalse(owner.exists())

    def test_validator_rejection_not_reported_success(self):
        root,owner,out,result,error,prepare,validator=self.configure(validator_failure=True)
        self.assertIsInstance(error,ValueError);self.assertIsNone(result)
        self.assertFalse((out/'assembly-report.json').exists())

    def test_existing_assembly_root_refused_with_mocked_build_ancestry(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);(root/d.OUTPUT).mkdir(parents=True)
            manifest=root/'manifest';manifest.write_text('fixture')
            with mock.patch.object(d.build,'validate',return_value={}) as validation, \
                 mock.patch.object(seal_pair,'refreshed_assembly',return_value=(root/'baseline',{},[],root/'old')):
                with self.assertRaisesRegex(ValueError,'Fresh diagnostic assembly root'):
                    d.assemble(root,root,manifest,profile='fixture',build_proof='fixture')
                validation.assert_called_once()

    def test_configured_inventory_and_non_policy_payload_tampering_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);source=root/'source.jar';owner=root/'owner.jar'
            original=[(d.POLICY,PLACEHOLDER),('payload.class',b'original'),('resource',b'fixed')]
            def archive(path,entries):
                with warnings.catch_warnings():
                    warnings.simplefilter('ignore',UserWarning)
                    with zipfile.ZipFile(path,'w') as z:
                        for key,value in entries:z.writestr(key,value)
            archive(source,original)
            allowed=[(d.POLICY,b'{"approved":true}'),*original[1:]]
            archive(owner,allowed)
            d.verify_configured_entries(source,owner)
            variants={
                'changed':[(d.POLICY,b'new policy'),('payload.class',b'tampered'),original[2]],
                'added':allowed+[('new.class',b'added')],
                'removed':allowed[:-1],
                'duplicate':allowed+[('payload.class',b'original')],
            }
            for label,entries in variants.items():
                with self.subTest(tamper=label):
                    archive(owner,entries)
                    with self.assertRaises(ValueError):d.verify_configured_entries(source,owner)
            archive(owner,allowed)
            for placeholder in [b'{"schema":1,"approved":false}',b'{"schema":1,"approved":true}\n',b'{}']:
                with self.subTest(placeholder=placeholder):
                    archive(source,[(d.POLICY,placeholder),*original[1:]])
                    with self.assertRaisesRegex(ValueError,'Wrong unconfigured policy'):
                        d.verify_configured_entries(source,owner)

    def test_seal_source_manifest_pin_shared_lock_and_separate_roots(self):
        # Static contract check, not a substitute for a real consumer seal.
        source=inspect.getsource(seal_pair.create);tree=ast.parse(source)
        constants={n.value for n in ast.walk(tree) if isinstance(n,ast.Constant) and isinstance(n.value,str)}
        self.assertIn('ci/pair-seals-process-diagnostic',constants)
        self.assertIn('ci/pair-seals-refreshed',constants);self.assertIn('ci/pair-seals',constants)
        self.assertIn("serial=api/'ci/pair-seals'",source)
        self.assertIn("'pair_lock':str(serial/'serial-pair.lock')",source)
        self.assertIn("inputs.get(manifest_pin['path'])==manifest_pin",source)
        self.assertIn("base['diagnostic_profile']",source)
        self.assertIn('elif refreshed:',source)
        self.assertIn('diagnostic_manifest=None',source)

if __name__=='__main__':unittest.main()
