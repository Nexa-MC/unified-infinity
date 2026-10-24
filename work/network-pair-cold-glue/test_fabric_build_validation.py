"""Retained real compile/remap proof validation, never reruns Java or games.

The path-relocated copies below are metadata/tamper fixtures, not fresh builds.
They preserve actual class/JAR bytes and exercise complete recipe revalidation.
Portable CI without this retained local proof skips these explicitly local tests.
"""
import copy
import json
from pathlib import Path
import shutil
import tempfile
import unittest
import zipfile
import fabric_probe_overlay as b
import fabric_probe_build_validation as v

REAL_OUTPUT=Path(__file__).resolve().parents[1]/'fabric-disconnect-handoff-2032/build-owned-2035'

@unittest.skipUnless((REAL_OUTPUT/'result.json').is_file(),'Retained local actual build proof not present')
class RetainedActualBuildValidation(unittest.TestCase):
    def setUp(self):
        self.root=REAL_OUTPUT.parents[1]
        self.temp=tempfile.TemporaryDirectory(prefix='proof-tamper-fixture-',dir=Path(__file__).parent);self.addCleanup(self.temp.cleanup)
        self.output=Path(self.temp.name)/'output'
        shutil.copytree(REAL_OUTPUT,self.output,ignore=shutil.ignore_patterns('sealed-sources','bundle.json','namespace-proof.json'))
        self.path=self.output/'result.json'
        self.result=self.relocate(json.loads(self.path.read_text()))
        self.write()
    def relocate(self,value):
        if isinstance(value,dict):return {k:self.relocate(v) for k,v in value.items()}
        if isinstance(value,list):return [self.relocate(v) for v in value]
        if isinstance(value,str):return value.replace(str(REAL_OUTPUT),str(self.output))
        return value
    def write(self):self.path.write_bytes(b.canonical(self.result)+b'\n')
    def validate(self):return v.semantic_result(self.root,self.path)
    def test_path_relocated_actual_proof_and_all_nonempty_supervisor_pins(self):
        actual=self.validate();self.assertEqual(actual['result']['checks'],184)
        import fabric_network_qualification as q
        supervisor,_=q.load_supervisor(REAL_OUTPUT.parents[1]/'published-1809/work/network-ci-supervisor-portable3/supervisor.py')
        for row in actual['inputPins']:
            self.assertGreater(row['bytes'],0);supervisor.file_pin(dict(row,path=str(self.root/row['path'])),self.root)
        empty=[row['log'] for row in self.result['phases'] if row['log']['bytes']==0]
        self.assertTrue(empty)
        self.assertTrue(all(row['sha256']==b.digest(b'') for row in empty))
        self.assertFalse(any(str(self.root/p['path'])==r['path'] for p in actual['inputPins'] for r in empty))
    def test_missing_owned_session_proof_rejected(self):
        del self.result['processOwnership'];self.write()
        with self.assertRaisesRegex(ValueError,'owned builder session proof'):self.validate()
    def test_forked_or_boolean_owner_session_rejected(self):
        self.result['processOwnership']['builderSession']=True;self.write()
        with self.assertRaisesRegex(ValueError,'outer-owned builder session'):self.validate()
    def test_wrong_phase_order_rejected(self):
        self.result['phases'].reverse();self.write()
        with self.assertRaisesRegex(ValueError,'ordered actual build phases'):self.validate()
    def test_boolean_phase_exit_rejected(self):
        self.result['phases'][0]['exitCode']=False;self.write()
        with self.assertRaisesRegex(ValueError,'Exact bounded build phase'):self.validate()
    def test_changed_command_rejected(self):
        self.result['phases'][0]['argv'].append('-Aunreviewed=yes');self.write()
        with self.assertRaisesRegex(ValueError,'Exact bounded build phase'):self.validate()
    def test_tampered_empty_log_rejected(self):
        phase=next(x for x in self.result['phases'] if x['log']['bytes']==0)
        Path(phase['log']['path']).write_bytes(b'unretained error')
        with self.assertRaisesRegex(ValueError,'log changed'):self.validate()
    def test_changed_remap_library_order_rejected(self):
        path=self.output/'libraries.txt';path.write_text(''.join(reversed(path.read_text().splitlines(keepends=True))))
        with self.assertRaisesRegex(ValueError,'library list'):self.validate()
    def test_changed_remap_roundtrip_product_rejected(self):
        path=self.output/'probe-roundtrip.jar'
        with zipfile.ZipFile(path,'a') as z:z.writestr('unreviewed.txt',b'changed')
        with self.assertRaisesRegex(ValueError,'remapping output inventory'):self.validate()
    def test_changed_executable_test_class_rejected(self):
        path=next((self.output/'test').rglob('*.class'));path.write_bytes(b'changed')
        with self.assertRaisesRegex(ValueError,'class output inventory'):self.validate()
    def test_nonempty_sourcepath_rejected(self):
        (self.output/'empty/Surprise.java').write_text('class Surprise {}')
        with self.assertRaisesRegex(ValueError,'sourcepath must stay exactly empty'):self.validate()
    def test_sibling_compiler_cannot_borrow_reviewed_jdk_pins(self):
        config=json.loads(Path(self.result['callerConfig']['path']).read_text())
        original=config['jdk_root'];config['jdk_root']=str(Path(original).with_name('unreviewed-jdk'))
        config_path=self.output/'changed-config.json';config_path.write_bytes(b.canonical(config));self.result['callerConfig']=b.absolute_pin(self.root,config_path)
        for phase in self.result['phases']:phase['argv']=[arg.replace(original,config['jdk_root']) for arg in phase['argv']]
        self.write()
        with self.assertRaisesRegex(ValueError,'Selected compiler root'):self.validate()
    def test_self_consistent_changed_classpath_cannot_relabel_official_inventory(self):
        config=json.loads(Path(self.result['callerConfig']['path']).read_text())
        export=json.loads(Path(config['classpath_export']['path']).read_text())
        export['inputs'][0],export['inputs'][1]=export['inputs'][1],export['inputs'][0]
        export_path=self.output/'changed-export.json';export_path.write_bytes(b.canonical(export));pin=b.absolute_pin(self.root,export_path)
        config['classpath_export']=pin;self.result['classpathSourceManifest']=pin
        config_path=self.output/'changed-config.json';config_path.write_bytes(b.canonical(config));self.result['callerConfig']=b.absolute_pin(self.root,config_path)
        self.result['classpathInputs'][0],self.result['classpathInputs'][1]=self.result['classpathInputs'][1],self.result['classpathInputs'][0];self.write()
        with self.assertRaisesRegex(ValueError,'path-independent compiler inventory'):self.validate()
    def test_unreviewed_source_identity_rejected(self):
        self.result['sourceManifest']['sha256']='0'*64;self.write()
        with self.assertRaises(ValueError):self.validate()
    def test_actual_bundle_descriptor_and_fresh_path_bundle_production(self):
        original=b.pin(self.root,REAL_OUTPUT/'bundle.json');descriptor=v.describe_bundle(self.root,original)
        self.assertEqual(descriptor['reviewed']['artifact_sha256'],v.ARTIFACT_SHA256)
        self.assertEqual(descriptor['reviewed']['source_manifest_sha256'],v.SOURCE_SHA256)
        binding={'schema':1,'status':'BUILT','source_manifest_sha256':v.SOURCE_SHA256,'artifact_path':self.result['artifact']['path'],
                 'artifact_sha256':v.ARTIFACT_SHA256,'artifact_bytes':self.result['artifact']['bytes']}
        (self.output/'probe-build-binding.json').write_bytes(b.canonical(binding))
        fresh=v.build_bundle(self.root,Path(self.result['sourceManifest']['path']).parent,self.output)
        self.assertNotEqual(fresh['reviewed']['namespace_proof_sha256'],descriptor['reviewed']['namespace_proof_sha256'])
        self.assertEqual(fresh['reviewed']['source_manifest_sha256'],descriptor['reviewed']['source_manifest_sha256'])
        self.assertEqual(fresh['reviewed']['artifact_sha256'],descriptor['reviewed']['artifact_sha256'])
        with self.assertRaisesRegex(ValueError,'Stale staged source tree'):
            v.build_bundle(self.root,Path(self.result['sourceManifest']['path']).parent,self.output)


    def test_missing_actual_handoff_marker_rejected(self):
        row=next(x for x in self.result['phases'] if x['name']=='actual-game-codecs')
        path=Path(row['log']['path']);data=path.read_bytes();data=b'\n'.join(x for x in data.splitlines() if not x.startswith(b'ACTUAL_DISCONNECT_HANDOFF '))+b'\n';path.write_bytes(data)
        row['log']['bytes']=len(data);row['log']['sha256']=b.digest(data);self.write()
        with self.assertRaisesRegex(ValueError,'disconnect handoff assertions absent'):self.validate()

if __name__=='__main__':unittest.main()
