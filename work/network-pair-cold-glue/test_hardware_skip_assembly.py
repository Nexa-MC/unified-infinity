"""Real prepare/validate/configuration over synthetic ZIP inventory, not JVM/game proof.

No validator is mocked. Class entries below are deliberately non-executable fixture
bytes. This verifies policy/provenance propagation, not service discovery or class
transformation. Builder tests own exact approved provider/bytecode validation.
"""
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
import zipfile

import diagnostic_pair_assembly as d

SERVICE = 'META-INF/services/cpw.mods.modlauncher.serviceapi.ILaunchPluginService'
DESCRIPTOR = b'fixture.OriginalProvider\nfixture.SeparatelyApprovedHardwareDiagnostic\n'

class HardwareSkipConfiguredAssembly(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        source = Path(__file__).resolve().parents[2] / 'work/network-pair-assembly-local1/required-text-inputs/work/api1/source-workspace/fml-unified/tools/assemble_installation.py'
        self.assertEqual(d.base.sha(source), '07148f3909828a55ee9698a8ed9d96ad6bada651226ab1bf1fdff858c703b37a')
        spec = importlib.util.spec_from_file_location('hardware_fixture_actual_assembler', source)
        self.assembler = importlib.util.module_from_spec(spec); spec.loader.exec_module(self.assembler)
        self.validator = self.assembler.v
        self.original = self.root/'original-profile'; self.original.mkdir()
        self.game = self.root/'diagnostic-profile'; self.game.mkdir()
        self.stock = self.original/'stock-loader.jar'; self.jar(self.stock, {'fixture/original.class':b'original fixture'})
        self.manifest = self.root/'hardware-skip-manifest.json'
        self.manifest.write_text(json.dumps({'synthetic_fixture':True, 'diagnostic_only':True,
            'baseline_acceptance':False, 'behavior':'hardware-inventory-skip', 'gameAcceptance':False}))
        self.derivative = self.root/'separately-named-fml-derivative.jar'
        entries = {name:b'not executable class fixture' for name in self.validator.FML_REQUIRED}
        entries.update({self.validator.PREFIX+name+'.class':b'not executable class fixture' for name in self.validator.REQUIRED})
        entries.update({SERVICE:DESCRIPTOR, d.POLICY:b'{"schema":1,"approved":false}\n'})
        self.jar(self.derivative, entries)
        self.owner = self.game/'installation/boot.jar'
        artifacts=[]
        consumer={'org/sinytra/connector/infinity/FmlCompatibilityComponent.class':b'fixture',
            'META-INF/unified-admission/consumer-v1.json':json.dumps({'protocol':1,'runtimeModelOwner':'fml_loader',
            'consumers':['ConnectorLocator','FabricModsDiscoverer','OrdinaryAdmissionGate','ManagedQuiltModules']}).encode()}
        sets={'ADMISSION_CONSUMER':consumer}
        sets.update({role:{name:b'fixture','META-INF/neoforge.mods.toml':b'fixture'} for role,name in self.validator.GAME_CLASSES.items()})
        for role, payload in sets.items():
            path=self.game/'installation'/(role.lower()+'.jar');self.jar(path,payload)
            artifacts.append({'path':str(path.relative_to(self.game)), 'sha256':d.base.sha(path),
                'primaryIds':[], 'role':role, 'provenance':{'synthetic_fixture':True}})
        artifacts.append({'path':'installation/boot.jar','sha256':'SELF','primaryIds':[],
            'role':'BOOT_OWNER','provenance':{'synthetic_fixture':True}})
        self.launch=self.root/'original-launch.json'
        d.base.save(self.launch, {'workingDirectory':str(self.original),
            'command':['/fixture/java','-cp',str(self.stock),'cpw.mods.bootstraplauncher.BootstrapLauncher'],
            'files':[d.base.pin(self.stock)]})
        self.spec={'installationDirectory':str(self.game),'gameDirectory':str(self.game),
            'launchSource':d.base.pin(self.launch),'pathReplacements':{str(self.stock):str(self.owner)},
            'policyId':'fixture-separate-hardware-diagnostic','launchTarget':'forgeserver',
            'artifacts':artifacts,'embedded':[]}
        self.pristine={p:p.read_bytes() for p in [self.stock,self.launch,self.derivative,self.manifest]}

    @staticmethod
    def jar(path, entries):
        path.parent.mkdir(parents=True,exist_ok=True)
        with zipfile.ZipFile(path,'w') as archive:
            for name,payload in entries.items():archive.writestr(name,payload)

    def configure(self):
        return d.configure_unified(self.assembler,self.spec,self.root/'assembly-spec.json',
            self.derivative,self.manifest,self.root/'configured')

    def test_actual_validator_preserves_service_and_binds_separate_manifest(self):
        command, report, pins=self.configure()
        self.assertTrue(report['diagnostic_only']);self.assertFalse(report['baseline_acceptance'])
        self.assertFalse(report['gameLaunched']);self.assertFalse(report['jvmStarted'])
        receipt=json.loads(Path(report['buildReceipt']).read_text())
        d.require_scope(receipt); d.require_scope(report)
        self.assertEqual(receipt['diagnosticManifest'], d.base.pin(self.manifest))
        self.assertEqual(receipt['unconfiguredDerivative'], d.base.pin(self.derivative))
        with zipfile.ZipFile(self.owner) as archive:
            self.assertEqual(archive.read(SERVICE),DESCRIPTOR)
            policy=json.loads(archive.read(d.POLICY))
        self.assertEqual(policy['processArgumentsSha256'],self.validator.digest_strings(command[1:]))
        self.assertEqual(report['classOwnerCount'],1)
        for path, data in self.pristine.items():self.assertEqual(path.read_bytes(),data)
        d.verify_configured_entries(self.derivative,self.owner)

    def test_variant_manifest_changes_fail_original_receipt_pin(self):
        _, report, _=self.configure()
        receipt=json.loads(Path(report['buildReceipt']).read_text())
        original=self.manifest.read_bytes()
        for altered in (b'', b'{"diagnostic_only":true,"behavior":"different-scope"}'):
            self.manifest.write_bytes(altered)
            with self.assertRaisesRegex(ValueError,'Changed diagnostic or baseline input'):
                d.check(self.root,receipt['diagnosticManifest'])
        self.manifest.write_bytes(original)
        self.assertEqual(d.check(self.root,receipt['diagnosticManifest']),self.manifest)

    def test_owner_service_tamper_rejected_even_when_receipt_rehashed(self):
        command, report, _=self.configure()
        with zipfile.ZipFile(self.owner) as archive: entries={n:archive.read(n) for n in archive.namelist()}
        entries[SERVICE]=b'fixture.UnexpectedProvider\n';self.jar(self.owner,entries)
        receipt_path=Path(report['buildReceipt'])
        with self.assertRaisesRegex(ValueError,'BOOT owner changed'):
            self.validator.validate(receipt_path,d.base.sha(receipt_path),command[1:],{})
        receipt=json.loads(receipt_path.read_text());receipt['sha256']=d.base.sha(self.owner);receipt_path.write_text(json.dumps(receipt))
        # Generic launch validator hashes cannot establish derivative ancestry;
        # the actual assembly comparison is the mandatory additional boundary.
        with self.assertRaisesRegex(ValueError,'non-policy payload'):
            d.verify_configured_entries(self.derivative,self.owner)

    def test_empty_or_extra_configured_entries_rejected(self):
        self.configure()
        with zipfile.ZipFile(self.owner) as archive: pristine={n:archive.read(n) for n in archive.namelist()}
        for entries in [dict(pristine, **{SERVICE:b''}),dict(pristine, **{'fixture/unexpected.class':b'extra'})]:
            self.jar(self.owner,entries)
            with self.assertRaises(ValueError):d.verify_configured_entries(self.derivative,self.owner)

    def test_actual_validator_rejects_changed_arguments_and_runtime_input(self):
        command,report,_=self.configure();receipt=Path(report['buildReceipt'])
        with self.assertRaisesRegex(ValueError,'arguments differ'):
            self.validator.validate(receipt,d.base.sha(receipt),command[1:]+['unexpected'],{})
        artifact=self.game/self.spec['artifacts'][0]['path'];artifact.write_bytes(b'')
        with self.assertRaisesRegex(ValueError,'Invalid pinned artifact'):
            self.validator.validate(receipt,d.base.sha(receipt),command[1:],{})

class FourRoleScopeBinding(unittest.TestCase):
    """Actual overlay validator; upstream builder and class validator are mocked
    by the reusable four-role fixture. Not a full cold build or JVM test."""
    def test_scope_required_in_assembly_and_each_native_unified_role(self):
        from test_diagnostic_flow_fixture import FourRoleFlow
        fixture=FourRoleFlow();fixture.setUp();self.addCleanup(fixture.doCleanups)
        result=d.assemble(fixture.root,fixture.root,fixture.manifest,profile='fixture',build_proof='fixture')
        original=result.read_bytes();value=json.loads(original)
        self.assertEqual(d.OUTPUT,'work/network-pair-assembled-hardware-skip-diagnostic')
        d.require_scope(value)
        for target,group in value['groups'].items():
            for side,row in group['roles'].items():
                role_path=Path(row['path']);raw=role_path.read_bytes();role=json.loads(raw)
                d.require_scope(role)
                self.assertTrue(role['diagnostic_only']);self.assertFalse(role['baseline_acceptance'])
                role['behavioralChange']=False;role_path.write_text(json.dumps(role))
                mutated=json.loads(original);mutated['groups'][target]['roles'][side]=d.base.pin(role_path)
                result.write_text(json.dumps(mutated))
                with self.assertRaisesRegex(ValueError,'hardware-skip scope changed'):
                    d.validate(fixture.root,fixture.root,fixture.manifest,profile='fixture',build_proof='fixture')
                role_path.write_bytes(raw);result.write_bytes(original)
        for key in d.SCOPE:
            mutated=json.loads(original);del mutated[key];result.write_text(json.dumps(mutated))
            with self.assertRaisesRegex(ValueError,'hardware-skip scope changed'):
                d.validate(fixture.root,fixture.root,fixture.manifest,profile='fixture',build_proof='fixture')
        result.write_bytes(original)
        d.validate(fixture.root,fixture.root,fixture.manifest,profile='fixture',build_proof='fixture')

    def test_boolean_scope_cannot_be_integer_or_label_only(self):
        for key in ('behavioralChange','nonHardwareFieldsPreserved','gameJarBytesModified'):
            value=dict(d.SCOPE);value[key]=int(value[key])
            with self.assertRaisesRegex(ValueError,'scope changed'):d.require_scope(value)

if __name__=='__main__': unittest.main()
