"""Structural validator tests with synthetic ZIP entries, never executable class files or JVM tests."""
import importlib.util,json,pathlib,tempfile,unittest,zipfile
SPEC=importlib.util.spec_from_file_location('validator',pathlib.Path(__file__).resolve().parents[1]/'tools/validate_launch.py')
v=importlib.util.module_from_spec(SPEC);SPEC.loader.exec_module(v)
class Validation(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.root=pathlib.Path(self.tmp.name);self.args=['fixture-main'];self.environment={k:'' for k in ('MOD_CLASSES','JAVA_TOOL_OPTIONS','JDK_JAVA_OPTIONS','_JAVA_OPTIONS')}
        self.capability={'protocol':1,'runtimeModelOwner':'fml_loader','consumers':['ConnectorLocator','FabricModsDiscoverer','OrdinaryAdmissionGate','ManagedQuiltModules']}
    def tearDown(self):self.tmp.cleanup()
    def make(self,capability=True,duplicate=False):
        core=self.root/'consumer.jar'
        with zipfile.ZipFile(core,'w') as z:
            z.writestr('org/sinytra/connector/infinity/FmlCompatibilityComponent.class',b'synthetic-not-bytecode')
            if capability:z.writestr('META-INF/unified-admission/consumer-v1.json',json.dumps(self.capability))
            if duplicate:z.writestr(v.PREFIX+'AdmissionSession.class',b'synthetic-not-bytecode')
        game_artifacts=[]
        for role,entry in v.GAME_CLASSES.items():
            game=self.root/(role.lower()+'.jar')
            with zipfile.ZipFile(game,'w') as z:
                z.writestr(entry,b'synthetic-not-bytecode')
                z.writestr('META-INF/neoforge.mods.toml','modLoader="unified_internal"\nloaderVersion="[1]"\n')
            game_artifacts.append({'path':game.name,'sha256':v.sha(game),'role':role,'primaryIds':[]})
        owner=self.root/'owner.jar';properties={k:'' for k in ('java.class.path','jdk.module.path','legacyClassPath','legacyClassPath.file','fml.modFolders','fml.modFoldersFile')}
        policy={'schema':1,'approved':True,'installationDirectory':str(self.root),'gameDirectory':str(self.root),'launchTarget':'fixture','processArgumentsSha256':v.digest_strings(self.args),'properties':properties,'environment':self.environment,'argumentFiles':[],'embedded':[],'policyId':'synthetic-structural-test','artifacts':[{'path':'owner.jar','sha256':'SELF','role':'BOOT_OWNER','primaryIds':[]},{'path':'consumer.jar','sha256':v.sha(core),'role':'ADMISSION_CONSUMER','primaryIds':['connector']}]}
        policy['artifacts'].extend(game_artifacts)
        raw=(json.dumps(policy)+'\n').encode()
        with zipfile.ZipFile(owner,'w') as z:
            z.writestr('META-INF/unified-admission/installation.json',raw)
            for name in v.REQUIRED:z.writestr(v.PREFIX+name+'.class',b'synthetic-not-bytecode')
            for name in v.FML_REQUIRED:z.writestr(name,b'synthetic-not-bytecode')
        import hashlib
        receipt={'artifact':str(owner),'sha256':v.sha(owner),'installationPolicySha256':hashlib.sha256(raw).hexdigest()}
        path=self.root/'receipt.json';path.write_text(json.dumps(receipt));return path,v.sha(path)
    def test_valid_structural_receipt(self):
        p,h=self.make();self.assertEqual(v.validate(p,h,self.args,self.environment)['status'],'validated-before-jvm')
    def test_unreviewed_receipt(self):
        p,h=self.make()
        with self.assertRaisesRegex(ValueError,'Unreviewed'):v.validate(p,'0'*64,self.args,self.environment)
    def test_missing_consumer(self):
        p,h=self.make(capability=False)
        with self.assertRaisesRegex(KeyError,'consumer-v1.json'):v.validate(p,h,self.args,self.environment)
    def test_duplicate_runtime_owner(self):
        p,h=self.make(duplicate=True)
        with self.assertRaisesRegex(ValueError,'Split BOOT'):v.validate(p,h,self.args,self.environment)
    def test_changed_launch(self):
        p,h=self.make()
        with self.assertRaisesRegex(ValueError,'Launch arguments'):v.validate(p,h,['changed'],self.environment)
    def test_changed_bytes(self):
        p,h=self.make();(self.root/'consumer.jar').write_bytes(b'changed')
        with self.assertRaisesRegex(ValueError,'pinned artifact'):v.validate(p,h,self.args,self.environment)
    def test_changed_environment(self):
        p,h=self.make();env=dict(self.environment);env['MOD_CLASSES']='unexpected-output'
        with self.assertRaisesRegex(ValueError,'environment'):v.validate(p,h,self.args,env)
if __name__=='__main__':unittest.main()
