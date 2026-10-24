"""Synthetic binding/staging tests only, never genuine compilation/game evidence."""
from pathlib import Path
import copy
import importlib.util
import json
import tempfile
import unittest
from unittest.mock import patch
import zipfile

import fabric_probe_overlay as f


def supervisor_source():
    parent=Path(__file__).resolve().parents[1]
    candidates=[parent/'network-ci-supervisor-portable3/supervisor.py',
                parent/'published-1809/work/network-ci-supervisor-portable3/supervisor.py']
    return next(path for path in candidates if path.is_file())


class OverlayTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='ffapi-overlay-')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.source = self.root / 'new-probe/source'
        self.output = self.root / 'new-probe/build'
        self.source.mkdir(parents=True); self.output.mkdir()
        self.metadata = {'schemaVersion':1, 'id':f.MOD_ID, 'version':'0.1.0', 'environment':'*',
                         'entrypoints':f.ENTRYPOINTS,
                         'depends':{'minecraft':'1.21.1','fabricloader':'>=0.16.0',
                                    'fabric-networking-api-v1':'*','fabric-lifecycle-events-v1':'*'},
                         'custom':{'unified:diagnosticOnly':True,'unified:baselineAcceptance':False}}
        resources = {'build.gradle':b'// SYNTHETIC SOURCE BINDING FIXTURE ONLY\n', 'protocol-schema.json':b'{"fixture":true}\n',
                     'src/main/resources/fabric.mod.json':f.canonical(self.metadata)}
        rows = []
        for name,data in resources.items():
            p = self.source/name; p.parent.mkdir(parents=True,exist_ok=True); p.write_bytes(data)
            rows.append(dict(f.pin(self.root,p),path=name))
        self.source_manifest = self.source/'source-manifest.json'
        self.save(self.source_manifest,{'schema':1,'status':'SOURCE_ONLY_NOT_RUNTIME_ACCEPTANCE','files':rows})
        self.artifact = self.output/f.ARTIFACT_NAME
        with zipfile.ZipFile(self.artifact,'w') as archive:
            archive.writestr('fabric.mod.json',resources['src/main/resources/fabric.mod.json'])
            for value in f.ENTRYPOINTS.values(): archive.writestr(value[0].replace('.','/')+'.class',b'SYNTHETIC NOT EXECUTABLE')
        artifact_pin = f.pin(self.root,self.artifact); source_pin = f.pin(self.root,self.source_manifest)
        self.binding = self.output/'probe-build-binding.json'
        self.save(self.binding,{'schema':1,'status':'BUILT','source_manifest_sha256':source_pin['sha256'],
                               'artifact_path':str(self.artifact),'artifact_sha256':artifact_pin['sha256'],'artifact_bytes':artifact_pin['bytes']})
        self.result = self.output/'result.json'; self.save(self.result,{'synthetic_fixture':True,'compiled':False,'runtime_acceptance':False})
        evidence = self.root/'synthetic-remap-evidence.json'; self.save(evidence,{'synthetic_fixture':True,'executed':False})
        self.mapping = self.output/'namespace-proof.json'
        self.save(self.mapping,{'schema':f.MAPPING_SCHEMA,'status':'REMAP_VERIFIED_NOT_RUNTIME_ACCEPTANCE',
            'source_namespace':'mojang','artifact_namespace':'intermediary','runtime_namespace':'mojang',
            'mechanism':'pinned-fart-mojang-to-intermediary','source_manifest_sha256':source_pin['sha256'],
            'artifact_sha256':artifact_pin['sha256'],'evidence':[f.pin(self.root,evidence)]})
        self.bundle_path = self.output/'bundle.json'
        self.bundle = {'schema':f.BUNDLE_SCHEMA,'diagnostic_only':True,'baseline_acceptance':False,
                       **{key:f.pin(self.root,path) for key,path in [('artifact',self.artifact),('source_manifest',self.source_manifest),
                           ('build_binding',self.binding),('build_result',self.result),('namespace_proof',self.mapping)]}}
        self.save(self.bundle_path,self.bundle)
        self.reviewed = {'source_manifest_sha256':source_pin['sha256'],'artifact_sha256':artifact_pin['sha256'],
                         'namespace_proof_sha256':self.bundle['namespace_proof']['sha256']}
        self.baseline = self.root/'baseline/unified/client/mods'/f.LEGACY_NAME
        self.baseline.parent.mkdir(parents=True); self.baseline.write_bytes(b'SYNTHETIC NATIVE PROBE FIXTURE')
        self.legacy_sha=f.digest(self.baseline.read_bytes())
        self.baseline_pin=f.absolute_pin(self.root,self.baseline)
        self.overlay=self.root/'separate-ffapi-overlay'; self.game=self.overlay/'unified/client'
        mods=self.game/'mods'; mods.mkdir(parents=True)
        (mods/f.LEGACY_NAME).write_bytes(self.baseline.read_bytes())
        originals=[]
        for name in ('original-a.jar','original-b.jar','original-c.jar'):
            p=mods/name;p.write_bytes(b'SYNTHETIC ORIGINAL MOD');originals.append(str(p))
        self.before={'cwd':str(self.game),'command':['fixture-java','unchanged-argument'],
                     'original_mods':originals,'managed_mods':[], 'probe_path':str(mods/f.LEGACY_NAME),
                     'files':sorted([f.absolute_pin(self.root,p) for p in mods.iterdir()],key=lambda r:r['path']),
                     'diagnostic_only':True,'baseline_acceptance':False}

    def save(self,path,value): path.write_bytes(f.canonical(value)+b'\n')
    def verified(self): return f.verify_source_binding(self.root,f.pin(self.root,self.bundle_path),reviewed=self.reviewed)
    def stage(self):
        # Only the expected legacy digest is replaced for this synthetic fixture;
        # no production validator or supervisor function is mocked.
        with patch.object(f,'LEGACY_SHA256',self.legacy_sha):
            return f.stage_unified_probe(self.root,self.before,self.verified(),target='unified',
                                       baseline_probe=self.baseline_pin,overlay_root=self.overlay)
    def test_exact_binding_and_unified_only_delta(self):
        verified=self.verified();after,receipt=self.stage()
        self.assertEqual(after['command'],self.before['command'])
        self.assertEqual(after['original_mods'],self.before['original_mods'])
        self.assertEqual(after['managed_mods'],[])
        self.assertEqual(self.baseline.read_bytes(),b'SYNTHETIC NATIVE PROBE FIXTURE')
        self.assertFalse((self.game/'mods'/f.LEGACY_NAME).exists())
        self.assertEqual((self.game/'mods'/f.ARTIFACT_NAME).read_bytes(),self.artifact.read_bytes())
        with patch.object(f,'LEGACY_SHA256',self.legacy_sha):
            self.assertTrue(f.validate_staged_role(self.root,self.before,after,verified,receipt,
                                                baseline_probe=self.baseline_pin,overlay_root=self.overlay))
        binding=f.supervisor_binding(self.root,verified)
        self.assertEqual(binding['probe_path'],str(self.artifact));self.assertEqual(len(binding['source_receipts']),2)
    def test_native_target_refused_before_mutation(self):
        with self.assertRaisesRegex(ValueError,'Unified-only'):
            f.stage_unified_probe(self.root,self.before,self.verified(),target='native-neoforge',
                                 baseline_probe=self.baseline_pin,overlay_root=self.overlay)
        self.assertTrue((self.game/'mods'/f.LEGACY_NAME).exists())
        self.assertFalse((self.game/'mods'/f.ARTIFACT_NAME).exists())
    def test_missing_namespace_proof_refused(self):
        self.mapping.unlink()
        with self.assertRaises(FileNotFoundError): self.verified()
    def test_named_artifact_refused_even_with_consistent_rehashed_proof(self):
        mapping=json.loads(self.mapping.read_text());mapping['artifact_namespace']='mojang';self.save(self.mapping,mapping)
        self.bundle['namespace_proof']=f.pin(self.root,self.mapping);self.save(self.bundle_path,self.bundle)
        self.reviewed['namespace_proof_sha256']=self.bundle['namespace_proof']['sha256']
        with self.assertRaisesRegex(ValueError,'namespace route'):self.verified()
    def test_unknown_mapping_mechanism_refused(self):
        mapping=json.loads(self.mapping.read_text());mapping['mechanism']='trust-named-pass-through';self.save(self.mapping,mapping)
        self.bundle['namespace_proof']=f.pin(self.root,self.mapping);self.save(self.bundle_path,self.bundle)
        self.reviewed['namespace_proof_sha256']=self.bundle['namespace_proof']['sha256']
        with self.assertRaisesRegex(ValueError,'namespace route'):self.verified()
    def test_source_tamper_refused(self):
        (self.source/'build.gradle').write_bytes(b'changed')
        with self.assertRaisesRegex(ValueError,'Source/resource'):self.verified()
    def test_source_extra_file_refused(self):
        (self.source/'unreviewed.java').write_bytes(b'not allowed')
        with self.assertRaisesRegex(ValueError,'inventory'):self.verified()
    def test_artifact_tamper_refused(self):
        self.artifact.write_bytes(b'changed')
        with self.assertRaisesRegex(ValueError,'Changed'):self.verified()
    def test_build_binding_tamper_refused(self):
        binding=json.loads(self.binding.read_text());binding['artifact_path']=str(self.baseline);self.save(self.binding,binding)
        self.bundle['build_binding']=f.pin(self.root,self.binding);self.save(self.bundle_path,self.bundle)
        with self.assertRaisesRegex(ValueError,'build binding'):self.verified()
    def test_unreviewed_artifact_digest_refused(self):
        self.reviewed['artifact_sha256']='0'*64
        with self.assertRaisesRegex(ValueError,'identity'):self.verified()
    def test_zero_length_build_result_refused(self):
        self.result.write_bytes(b'')
        with self.assertRaisesRegex(ValueError,'Nonempty'):self.verified()
    def test_json_duplicate_refused(self):
        self.bundle_path.write_bytes(b'{"schema":1,"schema":1}')
        with self.assertRaisesRegex(ValueError,'Duplicate JSON'):self.verified()
    def test_symlink_source_refused(self):
        (self.source/'linked').symlink_to(self.source/'build.gradle')
        with self.assertRaisesRegex(ValueError,'Redirected'):self.verified()
    def test_extra_mod_refused_before_change(self):
        (self.game/'mods/extra.jar').write_bytes(b'not sealed')
        with self.assertRaisesRegex(ValueError,'Unexpected'):self.stage()
        self.assertTrue((self.game/'mods'/f.LEGACY_NAME).exists())
    def test_preexisting_new_probe_refused(self):
        (self.game/'mods'/f.ARTIFACT_NAME).write_bytes(self.artifact.read_bytes())
        with self.assertRaisesRegex(ValueError,'Unexpected|Stale'):self.stage()
    def test_changed_baseline_refused(self):
        self.baseline.write_bytes(b'changed')
        with self.assertRaisesRegex(ValueError,'Changed'):self.stage()
    def test_role_command_tamper_after_overlay_refused(self):
        after,receipt=self.stage();after['command'].append('unapproved')
        with patch.object(f,'LEGACY_SHA256',self.legacy_sha), self.assertRaisesRegex(ValueError,'unapproved role'):
            f.validate_staged_role(self.root,self.before,after,self.verified(),receipt,
                                  baseline_probe=self.baseline_pin,overlay_root=self.overlay)
    def test_legacy_emitter_reintroduced_refused(self):
        after,receipt=self.stage();(self.game/'mods'/f.LEGACY_NAME).write_bytes(self.baseline.read_bytes())
        with patch.object(f,'LEGACY_SHA256',self.legacy_sha), self.assertRaisesRegex(ValueError,'Legacy emitter'):
            f.validate_staged_role(self.root,self.before,after,self.verified(),receipt,
                                  baseline_probe=self.baseline_pin,overlay_root=self.overlay)
    def test_native_profile_path_refused_even_with_unified_target(self):
        wrong=copy.deepcopy(self.before);wrong['cwd']=str(self.overlay/'native-neoforge/client')
        with patch.object(f,'LEGACY_SHA256',self.legacy_sha), self.assertRaisesRegex(ValueError,'Unified diagnostic profile'):
            f.stage_unified_probe(self.root,wrong,self.verified(),target='unified',baseline_probe=self.baseline_pin,overlay_root=self.overlay)
    def test_legacy_expected_digest_is_not_optional(self):
        with self.assertRaisesRegex(ValueError,'Exact unchanged native'):
            f.stage_unified_probe(self.root,self.before,self.verified(),target='unified',baseline_probe=self.baseline_pin,overlay_root=self.overlay)
    def test_source_boolean_size_refused(self):
        manifest=json.loads(self.source_manifest.read_text());manifest['files'][0]['bytes']=True;self.save(self.source_manifest,manifest)
        self.bundle['source_manifest']=f.pin(self.root,self.source_manifest);self.save(self.bundle_path,self.bundle)
        self.reviewed['source_manifest_sha256']=self.bundle['source_manifest']['sha256']
        with self.assertRaisesRegex(ValueError,'strict source'):self.verified()
    def test_real_supervisor_strict_pin_and_protocol_contract(self):
        path=supervisor_source()
        spec=importlib.util.spec_from_file_location('ffapi_unchanged_supervisor',path)
        supervisor=importlib.util.module_from_spec(spec);spec.loader.exec_module(supervisor)
        sealed=f.supervisor_binding(self.root,self.verified())
        for row in sealed['inputs']:supervisor.file_pin(row,self.root)
        identity={'pid':1234,'start_ticks':5678}
        for role in ('server','client'):
            result={'schema':1,'role':role,'status':'PASS','nonce':23,'sequence':1,'counter_before':0,'counter_after':1,
                    'player_uuid':supervisor.IDENTITY,'player_name':supervisor.NAME,'port':25632,'pid':1234,'start_ticks':5678,
                    'main_thread':True,'loopback':True,'memory_connection':False,'dedicated_server':role=='server',
                    'remote_join':role=='client','phase':'PLAY','flow':'SERVERBOUND' if role=='server' else 'CLIENTBOUND','code':'ok'}
            supervisor.validate_probe(result,role,identity,23,25632)
            changed=dict(result,ffapi=True)
            with self.assertRaises(ValueError):supervisor.validate_probe(changed,role,identity,23,25632)


if __name__=='__main__':unittest.main()
