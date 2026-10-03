import importlib.util,pathlib,tempfile,unittest
from collections.abc import Mapping

spec=importlib.util.spec_from_file_location('game_environment',pathlib.Path(__file__).with_name('game_environment.py'))
g=importlib.util.module_from_spec(spec);spec.loader.exec_module(g)

class ValueGuard(Mapping):
    def __init__(self):self.accessed=[]
    def __iter__(self):return iter(['DISPLAY','LANG','DUMMY_AUTH_TOKEN','JAVA_TOOL_OPTIONS','UNLISTED_VALUE'])
    def __len__(self):return 5
    def __contains__(self,key):return key in ['DISPLAY','LANG','DUMMY_AUTH_TOKEN','JAVA_TOOL_OPTIONS','UNLISTED_VALUE']
    def __getitem__(self,key):
        self.accessed.append(key)
        if key=='DISPLAY':return ':0'
        if key=='LANG':return 'en_US.UTF-8'
        raise AssertionError('An unlisted value was read')

class EnvironmentTests(unittest.TestCase):
    def test_does_not_read_or_copy_unlisted_values(self):
        source=ValueGuard();env=g.build_game_environment(source,pathlib.Path('/tmp/game'),pathlib.Path('/tmp/jdk'),{})
        self.assertEqual(source.accessed,['DISPLAY','LANG'])
        self.assertNotIn('DUMMY_AUTH_TOKEN',env);self.assertNotIn('UNLISTED_VALUE',env)

    def test_strips_credentials_jvm_injection_and_proxy_without_reading_them(self):
        blocked=['DUMMY_AUTH_TOKEN','TEST_API_KEY','PASSWORD','JAVA_TOOL_OPTIONS','JDK_JAVA_OPTIONS','_JAVA_OPTIONS','GRADLE_OPTS','CLASSPATH','LD_PRELOAD','LD_LIBRARY_PATH','NODE_OPTIONS','PYTHONPATH','HTTP_PROXY','HTTPS_PROXY','ALL_PROXY','NO_PROXY']
        source={key:'dummy-not-a-real-secret' for key in blocked}
        source.update(DISPLAY=':0',XAUTHORITY='/tmp/display-context')
        env=g.build_game_environment(source,pathlib.Path('/tmp/game'),pathlib.Path('/tmp/jdk'),{})
        self.assertFalse(set(blocked)&set(env));self.assertEqual(env['DISPLAY'],':0')

    def test_private_paths_and_explicit_official_fields(self):
        with tempfile.TemporaryDirectory() as t:
            root=pathlib.Path(t);env=g.build_game_environment({'HOME':'/unrelated','PATH':'/unrelated'},root,root/'jdk',{'MOD_CLASSES':'owned%%/owned/classes'})
            self.assertEqual(env['HOME'],str(root/'.launch-home'))
            self.assertEqual(env['MOD_CLASSES'],'owned%%/owned/classes')
            self.assertNotIn('/unrelated',env.values())
            g.create_private_environment_directories(root)
            self.assertTrue(all((root/n).is_dir() for n in g.PRIVATE_DIRECTORIES.values()))

    def test_unexpected_official_field_fails_closed(self):
        with self.assertRaises(ValueError):g.build_game_environment({},pathlib.Path('/tmp/game'),pathlib.Path('/tmp/jdk'),{'UNEXPECTED':'dummy'})

    def test_policy_descriptor_has_no_ambient_values(self):
        d=g.public_policy_descriptor();self.assertFalse(d['unlistedKeysInherited']);self.assertFalse(d['proxyVariablesInherited'])

    def test_private_directory_symlink_fails_closed(self):
        with tempfile.TemporaryDirectory() as t:
            root=pathlib.Path(t)/'game';root.mkdir();other=pathlib.Path(t)/'other';other.mkdir()
            (root/'.launch-home').symlink_to(other,target_is_directory=True)
            with self.assertRaises(ValueError):g.create_private_environment_directories(root)

if __name__=='__main__':unittest.main()
