"""Synthetic four-role overlay flow; no actual full-build proof or game classes."""
import json
from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest
from unittest.mock import patch
import zipfile
import diagnostic_pair_assembly as d
import seal_pair

class FourRoleFlow(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name)
        self.original=self.root/d.base.REFRESHED_ASSEMBLED
        self.original.mkdir(parents=True)
        self.manifest=self.root/'manifest.json';self.manifest.write_text('{"synthetic":true}')
        self.stock=self.root/'stock.jar';self.native=self.root/'derived-native.jar';self.unified=self.root/'derived-unified.jar'
        for path in (self.stock,self.native,self.unified):
            with zipfile.ZipFile(path,'w') as z:
                z.writestr('net/neoforged/fml/loading/FMLLoader.class',b'not-real-bytecode')
                if path==self.unified:z.writestr(d.POLICY,b'{"schema":1,"approved":false}\n')
        self.assembler_path=self.root/'work/api1/source-workspace/fml-unified/tools/assemble_installation.py'
        self.assembler_path.parent.mkdir(parents=True);self.assembler_path.write_text('# fixture only')
        self.groups={}
        for target in ('native-neoforge','unified'):
            roles={};folder=self.original/target;folder.mkdir()
            for side in ('server','client'):
                game=folder/side;game.mkdir();(game/'options.txt').write_text('original')
                assembly=None
                if target=='unified':
                    (game/'installation').mkdir();owner=game/'installation/boot.jar'
                    with zipfile.ZipFile(owner,'w') as z:z.writestr('baseline',b'fixture')
                    spec={'installationDirectory':str(game),'gameDirectory':str(game),'launchSource':{'fixture':True},
                          'artifacts':[{'role':'BOOT_OWNER','path':'installation/boot.jar'}]}
                    spec_path=folder/(side+'-assembly-spec.json');d.base.save(spec_path,spec)
                    prior=folder/(side+'-configured');prior.mkdir();receipt=prior/'build-receipt.json'
                    d.base.save(receipt,{'assemblySpecSha256':d.base.sha(spec_path)})
                    assembly={'buildReceipt':str(receipt),'buildReceiptSha256':d.base.sha(receipt),
                              'configuredOwner':str(owner),'configuredOwnerSha256':d.base.sha(owner)}
                command=['/fixture/java','-cp',str(self.stock),'--gameDir',str(game)]
                files=[d.base.pin(self.stock),*[d.base.pin(p) for p in game.rglob('*') if p.is_file()]]
                role={'cwd':str(game),'command':command,'files':files,'original_mods':[],
                      'managed_mods':[],'probe_path':str(game/'probe.jar'),'assembly':assembly}
                roles[side]=d.base.save(folder/(side+'-launch-seal.json'),role)
            self.groups[target]={'port':25631 if target=='native-neoforge' else 25632,'roles':roles,'sourceFixture':{'fixture':True}}
        self.baseline=self.root/'baseline.json';d.base.save(self.baseline,{'groups':self.groups})
        self.baseline_value={'groups':self.groups}
        self.verified={'artifacts':{'native':self.native,'unified':self.unified},'inputPins':[]}
        self.proof_inputs=[d.base.pin(self.assembler_path)]
        def prepare(spec):
            policy={'installationDirectory':spec['installationDirectory'],'artifacts':spec['artifacts'],
                    'environment':{},'approved':True,'fixture':True}
            return policy,['-cp',str(Path(spec['installationDirectory'])/'installation/boot.jar')],'/fixture/java'
        def validate(receipt_path,expected,args,environment):
            self.assertEqual(d.base.sha(receipt_path),expected)
            return {'classOwnerCount':1,'gameLaunched':False,'fixture_validation_only':True}
        self.assembler=SimpleNamespace(prepare=prepare,v=SimpleNamespace(validate=validate))
        self.validator=SimpleNamespace(validate_command=lambda *args:None)
        self.patches=[patch.object(d.build,'validate',return_value=self.verified),
                      patch.object(seal_pair,'refreshed_assembly',return_value=(self.baseline,self.baseline_value,self.proof_inputs,self.original)),
                      patch.object(d.base,'module',side_effect=lambda name,path:self.validator if 'pair_validator' in name else self.assembler)]
        for p in self.patches:p.start();self.addCleanup(p.stop)

    def test_all_four_roles_assemble_and_revalidate_synthetic_flow(self):
        before={str(p):p.read_bytes() for p in self.original.rglob('*') if p.is_file()}
        result=d.assemble(self.root,self.root,self.manifest,profile='fixture',build_proof='fixture')
        _,value,pins,out=d.validate(self.root,self.root,self.manifest,profile='fixture',build_proof='fixture')
        self.assertEqual(result,self.root/d.RESULT);self.assertFalse(value['gameAcceptance'])
        self.assertEqual(len(value['groups']),2)
        self.assertTrue(all(p.read_bytes()==content for name,content in before.items() for p in [Path(name)]))
        for target,group in value['groups'].items():
            for side,row in group['roles'].items():
                role=json.loads(Path(row['path']).read_text());self.assertTrue(role['diagnostic_only'])
                self.assertEqual(role['cwd'],str(out/target/side))
                if target=='native-neoforge':self.assertIn(str(self.native),role['command'])
                else:self.assertIn(str(out/target/side/'installation/boot.jar'),role['command'])

    def test_options_mutation_is_allowed_only_after_pristine_overlay(self):
        d.assemble(self.root,self.root,self.manifest,profile='fixture',build_proof='fixture')
        (self.root/d.OUTPUT/'native-neoforge/client/options.txt').write_text('game changed options')
        d.validate(self.root,self.root,self.manifest,profile='fixture',build_proof='fixture')

class ActualPreparePathBinding(unittest.TestCase):
    def test_pinned_original_prepare_binds_fresh_diagnostic_paths(self):
        import importlib.util
        import hashlib
        source=Path(__file__).resolve().parents[1]/'network-pair-assembly-local1/required-text-inputs/work/api1/source-workspace/fml-unified/tools/assemble_installation.py'
        self.assertEqual(hashlib.sha256(source.read_bytes()).hexdigest(),'07148f3909828a55ee9698a8ed9d96ad6bada651226ab1bf1fdff858c703b37a')
        spec=importlib.util.spec_from_file_location('actual_prepare_diagnostic_fixture',source)
        assembler=importlib.util.module_from_spec(spec);spec.loader.exec_module(assembler)
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);original=root/'official';old=root/'baseline';new=root/'diagnostic'
            for path in (original,old,new):path.mkdir()
            stock=original/'loader.jar';stock.write_bytes(b'path-only fixture, not bytecode')
            launch=root/'launch.json'
            command=['/fixture/java','-cp',str(stock),'-DlegacyClassPath='+str(stock),
                     'cpw.mods.bootstraplauncher.BootstrapLauncher','--gameDir',str(original),'--launchTarget','forgeserver']
            d.base.save(launch,{'workingDirectory':str(original),'command':command,'files':[d.base.pin(stock)]})
            source_spec={'installationDirectory':str(old),'gameDirectory':str(old),'policyId':'fixture',
                         'launchTarget':'forgeserver','launchSource':d.base.pin(launch),'embedded':[],
                         'pathReplacements':{str(stock):str(old/'installation/boot.jar')},
                         'artifacts':[{'role':'BOOT_OWNER','path':'installation/boot.jar','sha256':'SELF',
                                       'primaryIds':[],'provenance':{'fixture':True}}]}
            diagnostic_spec=d.relocate(source_spec,old,new)
            policy,args,java=assembler.prepare(diagnostic_spec)
            self.assertEqual(policy['installationDirectory'],str(new))
            self.assertEqual(policy['gameDirectory'],str(new))
            self.assertEqual(policy['properties']['java.class.path'],str(new/'installation/boot.jar'))
            self.assertEqual(policy['properties']['legacyClassPath'],str(new/'installation/boot.jar'))
            self.assertEqual(args[args.index('--gameDir')+1],str(new))
            self.assertEqual(policy['processArgumentsSha256'],assembler.v.digest_strings(args))
            self.assertFalse(any(str(old) in x for x in args))
            self.assertEqual(source_spec['installationDirectory'],str(old))
            # This executes the real source-owned prepare only, not its complete
            # BOOT class/API validator and not any JVM/game implementation.

if __name__=='__main__':unittest.main()
