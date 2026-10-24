"""Preseal closure regression with actual file/semantic validators.

The four-role assembly fixture mocks upstream build/assembler ancestry and uses
non-executable ZIP payloads. No real finalizer/graphics/JVM/game is exercised.
Its actual diagnostic validator supplies proof pins; selected role input closure
is composed using seal_pair.create's documented selection rule. Supervisor hash,
property and ops validators are imported unchanged and are never mocked.
"""
import importlib.util
import json
from pathlib import Path
import unittest
import diagnostic_pair_assembly as d
import test_diagnostic_flow_fixture as fixture

class PresealedPairInputs(unittest.TestCase):
    def setUp(self):
        self.f=fixture.FourRoleFlow();self.f.setUp();self.addCleanup(self.f.doCleanups)
        source=Path(__file__).resolve().parents[1]/'network-ci-supervisor-portable3/supervisor.py'
        spec=importlib.util.spec_from_file_location('presealed_actual_supervisor',source)
        self.s=importlib.util.module_from_spec(spec);spec.loader.exec_module(self.s)
        # Add genuine mutable-file shapes BEFORE any assembly/pristine checks.
        for target,group in self.f.groups.items():
            row=group['roles']['server'];path=Path(row['path']);role=json.loads(path.read_text());game=Path(role['cwd'])
            (game/'server.properties').write_bytes(b'# source\nserver-port=25631\nwhite-list=true\n')
            (game/'ops.json').write_bytes(b'[]\n')
            role['files'].extend(d.base.pin(game/n) for n in ('server.properties','ops.json'))
            path.write_text(json.dumps(role));group['roles']['server']=d.base.pin(path)
        self.f.baseline.write_text(json.dumps(self.f.baseline_value))
        d.assemble(self.f.root,self.f.root,self.f.manifest,profile='fixture',build_proof='fixture')
        _,self.assembly,self.proof,self.out=d.validate(self.f.root,self.f.root,self.f.manifest,profile='fixture',build_proof='fixture')
        self.closures={}
        for target,group in self.assembly['groups'].items():
            pins={r['path']:r for r in self.proof}
            for row in group['roles'].values():
                role=json.loads(Path(row['path']).read_text());cwd=Path(role['cwd'])
                for pin in role['files']:
                    if pin['path'] != str(cwd/'options.txt'):pins[pin['path']]=pin
            self.closures[target]=pins
        self.native=self.out/'native-neoforge';self.unified=self.out/'unified'

    def validate_pins(self,target):
        for row in self.closures[target].values():self.s.file_pin(row,self.f.root)

    def test_native_live_files_excluded_and_permitted_normalization_preserves_unified(self):
        unified=self.closures['unified'];native=self.closures['native-neoforge']
        self.assertFalse(any(Path(p).is_relative_to(self.native/side) for p in unified for side in ('server','client')))
        self.assertIn(str(self.out/'native-neoforge/server-launch-seal.json'),unified)
        self.validate_pins('unified');self.validate_pins('native-neoforge')
        properties=self.native/'server/server.properties';ops=self.native/'server/ops.json'
        before=properties.read_bytes();properties.write_bytes(b'# serialized later\nwhite-list=true\nserver-port=25631\n');ops.write_bytes(b'[]')
        self.s.verify_server_properties(native[str(properties)],before,self.f.root/'properties-receipt.json',self.f.root)
        self.s.verify_empty_ops_serialization(native[str(ops)],self.f.root/'ops-receipt.json',self.f.root)
        with self.assertRaises(ValueError):self.s.file_pin(native[str(properties)],self.f.root)
        with self.assertRaises(ValueError):self.s.file_pin(native[str(ops)],self.f.root)
        self.validate_pins('unified')

    def test_selected_unified_and_shared_input_changes_rejected(self):
        selected=self.unified/'server/server.properties'
        shared=self.f.native  # Derivative is bound in both roles, including Unified.
        for path in (selected,shared):
            before=path.read_bytes();path.write_bytes(b'changed')
            with self.assertRaises(ValueError):self.validate_pins('unified')
            path.write_bytes(before)
        self.validate_pins('unified')

    def test_native_immutable_changes_and_nonsemantic_mutations_rejected(self):
        pins=self.closures['native-neoforge'];properties=self.native/'server/server.properties';ops=self.native/'server/ops.json'
        before=properties.read_bytes();properties.write_bytes(b'server-port=25632\nwhite-list=true\n')
        with self.assertRaisesRegex(ValueError,'semantic key/value change'):
            self.s.verify_server_properties(pins[str(properties)],before,self.f.root/'rejected-properties.json',self.f.root)
        ops.write_bytes(b'[{"name":"unexpected"}]')
        with self.assertRaisesRegex(ValueError,'Operators must remain exactly empty'):
            self.s.verify_empty_ops_serialization(pins[str(ops)],self.f.root/'rejected-ops.json',self.f.root)
        shared=self.f.stock;original=shared.read_bytes();shared.write_bytes(b'mutated immutable jar')
        with self.assertRaises(ValueError):self.s.file_pin(pins[str(shared)],self.f.root)
        shared.write_bytes(original)

if __name__=='__main__':unittest.main()
