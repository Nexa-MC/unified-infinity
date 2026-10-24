"""Four-role/seal selection fixtures, not genuine build, graphics or runtime proof.

Only upstream complete build and BOOT assembler boundaries are mocked. The real
probe overlay, predecessor derivation, pin collection and seal selection run.
The seal test stops at the real finalizer boundary before any graphics/process.
"""
import copy
import json
import zipfile
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import patch
import diagnostic_pair_assembly as d
import seal_pair as seal
import fabric_probe_overlay as b
import fabric_probe_build_validation as build
import test_fabric_probe_overlay as probe_fixture
import test_diagnostic_flow_fixture as pair_fixture

class StopBeforeGraphics(Exception):pass

class FabricPairIntegration(unittest.TestCase):
    def setUp(self):
        self.probe=probe_fixture.OverlayTests();self.probe.setUp();self.addCleanup(self.probe.doCleanups)
        self.f=pair_fixture.FourRoleFlow()
        with patch.object(pair_fixture.tempfile,'TemporaryDirectory',return_value=SimpleNamespace(name=str(self.probe.root),cleanup=lambda:None)):
            self.f.setUp()
        self.addCleanup(self.f.doCleanups);self.root=self.f.root
        self.bound=self.probe.verified()
        self.descriptor={'bundle_pin':self.bound['bundle_pin'],'reviewed':self.bound['reviewed']}
        self.checked={'binding':self.bound,'inputPins':self.bound['inputs'],'descriptor':self.descriptor}
        self.patch=patch.object(build,'validate_bundle',return_value=self.checked);self.patch.start();self.addCleanup(self.patch.stop)
        with zipfile.ZipFile(self.probe.baseline,'w') as z:z.writestr('fixture.txt',b'SYNTHETIC OLD CONTROL')
        self.probe.legacy_sha=b.digest(self.probe.baseline.read_bytes())
        self.legacy=patch.object(b,'LEGACY_SHA256',self.probe.legacy_sha);self.legacy.start();self.addCleanup(self.legacy.stop)
        for target,group in self.f.groups.items():
            for side,pin in group['roles'].items():
                path=Path(pin['path']);role=json.loads(path.read_text());game=Path(role['cwd']);mods=game/'mods';mods.mkdir()
                old=mods/b.LEGACY_NAME;old.write_bytes(self.probe.baseline.read_bytes())
                original=mods/'original.jar';managed=mods/'managed.jar'
                for artifact,payload in [(original,b'FIXTURE ORIGINAL'),(managed,b'FIXTURE MANAGED')]:
                    with zipfile.ZipFile(artifact,'w') as z:z.writestr('fixture.txt',payload)
                role.update(probe_path=str(old),original_mods=[str(original)],managed_mods=[str(managed)])
                role['files'].extend(d.base.pin(p) for p in mods.iterdir());path.write_text(json.dumps(role));group['roles'][side]=d.base.pin(path)
        self.f.baseline.write_text(json.dumps(self.f.baseline_value))
        self.untouched={str(p):p.read_bytes() for p in self.f.original.rglob('*') if p.is_file()}
    def assemble(self):
        return d.assemble(self.root,self.root,self.f.manifest,profile='fixture',build_proof='fixture',ffapi_probe_bundle=self.descriptor)
    def validate(self):
        return d.validate(self.root,self.root,self.f.manifest,profile='fixture',build_proof='fixture',ffapi_probe_bundle=self.descriptor)
    def test_opt_in_only_unified_replaces_sole_probe(self):
        result=self.assemble();path,assembly,pins,out=self.validate()
        self.assertEqual(result,path);self.assertEqual(out,self.root/d.FFAPI_OUTPUT)
        self.assertFalse(assembly['baseline_acceptance']);self.assertFalse(assembly['gameLaunched'])
        for target,group in assembly['groups'].items():
            for side,row in group['roles'].items():
                role=json.loads(Path(row['path']).read_text());mods=Path(role['cwd'])/'mods'
                self.assertEqual(sorted(p.name for p in mods.iterdir()),sorted(['original.jar','managed.jar',b.ARTIFACT_NAME if target=='unified' else b.LEGACY_NAME]))
                self.assertEqual('ffapiProbeOverlay' in role,target=='unified')
                with zipfile.ZipFile(mods/'original.jar') as z:self.assertEqual(z.read('fixture.txt'),b'FIXTURE ORIGINAL')
                with zipfile.ZipFile(mods/'managed.jar') as z:self.assertEqual(z.read('fixture.txt'),b'FIXTURE MANAGED')
        for name,data in self.untouched.items():self.assertEqual(Path(name).read_bytes(),data)
        absolute={row['path']:row for row in pins}
        for row in self.bound['inputs']:self.assertEqual(absolute[str(self.root/row['path'])],dict(row,path=str(self.root/row['path'])))
    def test_client_options_remain_mutable_after_pristine_staging(self):
        self.assemble();(self.root/d.FFAPI_OUTPUT/'unified/client/options.txt').write_text('legitimate runtime update')
        self.validate()
    def test_non_probe_mutation_rejected_even_with_rehashed_overlay_chain(self):
        self.assemble();result=self.root/d.FFAPI_OUTPUT/'diagnostic-assembly.json';assembly=json.loads(result.read_text())
        rolepath=Path(assembly['groups']['unified']['roles']['client']['path']);role=json.loads(rolepath.read_text())
        proof=role['ffapiProbeOverlay'];beforepath=Path(proof['beforeRole']['path']);before=json.loads(beforepath.read_text())
        changed=Path(role['cwd'])/'mods/managed.jar';changed.write_bytes(b'CHANGED MANAGED MOD')
        for obj in [before,role]:obj['files']=[d.base.pin(changed) if row['path']==str(changed) else row for row in obj['files']]
        beforepath.write_bytes(b.canonical(before));proof['beforeRole']=d.base.pin(beforepath)
        receiptpath=Path(proof['receipt']['path']);receipt=json.loads(receiptpath.read_text())
        receipt['before_role_sha256']=b.digest(b.canonical(before));after=copy.deepcopy(role);after.pop('ffapiProbeOverlay')
        receipt['after_role_sha256']=b.digest(b.canonical(after));receiptpath.write_bytes(b.canonical(receipt));proof['receipt']=d.base.pin(receiptpath)
        rolepath.write_bytes(b.canonical(role));assembly['groups']['unified']['roles']['client']=d.base.pin(rolepath)
        replacements={str(beforepath):d.base.pin(beforepath),str(receiptpath):d.base.pin(receiptpath)}
        assembly['inputs']=[replacements.get(row['path'],row) for row in assembly['inputs']];result.write_bytes(b.canonical(assembly))
        with self.assertRaisesRegex(ValueError,'independently derived baseline'):self.validate()
    def test_missing_explicit_opt_in_does_not_select_ffapi_output(self):
        self.assemble()
        with self.assertRaises(FileNotFoundError):d.validate(self.root,self.root,self.f.manifest,profile='fixture',build_proof='fixture')
    def test_changed_bundle_rejected_before_output_mutation(self):
        with patch.object(build,'validate_bundle',side_effect=ValueError('changed build proof')):
            with self.assertRaisesRegex(ValueError,'changed build proof'):self.assemble()
        self.assertFalse((self.root/d.FFAPI_OUTPUT).exists())
    def test_actual_sealer_selects_new_probe_only_for_unified(self):
        self.assemble();captured=[]
        source=self.root/seal.SOURCE_RELATIVE;source.mkdir(parents=True)
        (source/'source-manifest.json').write_text(json.dumps({'files':[]}))
        output=self.root/seal.OUTPUT_RELATIVE;output.mkdir(parents=True)
        original=self.root/'baseline-control.jar';original.write_bytes(b'FIXTURE OLD CONTROL')
        (output/'probe-build-binding.json').write_text(json.dumps({'artifact_path':str(original)}));(output/'result.json').write_text('{"fixture":true}')
        helperpath=self.root/'work/network-pair-finalizer/prepare_inputs.py';helperpath.parent.mkdir(parents=True);helperpath.write_text('# fixture')
        (helperpath.parent/'source-manifest.json').write_text(json.dumps({'files':[dict(d.base.pin(helperpath),path='prepare_inputs.py')]}))
        helper=SimpleNamespace(jdk_closure=lambda:([],[],{'fixture':True}))
        def stop(base,*args):captured.append(base);raise StopBeforeGraphics()
        finalizer=SimpleNamespace(bind=stop)
        ready=self.root/'graphics-fixture.json';ready.write_text('{}')
        with patch.object(seal,'module',side_effect=lambda name,path:helper if 'jdk' in name else finalizer),patch.object(seal,'seal_indigo_baseline'):
            for target in ('native-neoforge','unified'):
                with self.assertRaises(StopBeforeGraphics):seal.create(self.root,self.root,target,ready,'fixture',profile='fixture',build_proof='fixture',diagnostic_manifest=self.f.manifest,ffapi_probe_bundle=self.descriptor)
        native,unified=captured
        self.assertEqual(native['probe_path'],str(original));self.assertEqual(native['probe_source_manifest'],str(source/'source-manifest.json'))
        selected=b.supervisor_binding(self.root,self.bound)
        for key in ('probe_path','probe_source_manifest','probe_build_receipt'):self.assertEqual(unified[key],selected[key])
        self.assertEqual(native['pair_lock'],unified['pair_lock']);self.assertEqual(native['port'],25631);self.assertEqual(unified['port'],25632)
        self.assertEqual(native['schema'],'prepared-network-ci-pair-v2');self.assertEqual(unified['schema'],native['schema'])
        for key in ('authorization','preparation_roots','diagnostic_profile'):self.assertEqual(unified[key],native[key])
        pins={row['path']:row for row in unified['inputs']}
        for row in self.checked['inputPins']:self.assertEqual(pins[str(self.root/row['path'])],dict(row,path=str(self.root/row['path'])))
        self.assertTrue(set(selected['source_receipts'])<=set(unified['source_receipts']))
    def test_probe_opt_in_without_diagnostic_profile_refused(self):
        with self.assertRaisesRegex(ValueError,'explicit diagnostic profile'):
            seal.create(self.root,self.root,'unified','unused','fixture',ffapi_probe_bundle=self.descriptor)

if __name__=='__main__':unittest.main()
