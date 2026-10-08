"""Bounded regression checks for actual launch-role transformations."""
import unittest
from pathlib import Path
import assemble_pairs as a

class TransformChecks(unittest.TestCase):
    def test_native_server_keeps_official_library_paths(self):
        old=Path('/official'); new=Path('/fresh')
        argv=['java','-DlegacyClassPath=/official/a.jar:/official/b.jar','-DlibraryDirectory=/official/libraries','-Dprogress=/official/progress.json','main','nogui']
        result=a.move_profile(argv,old,new)
        self.assertIn(argv[1],result);self.assertIn(argv[2],result)
        self.assertIn('-Dprogress=/fresh/progress.json',result)
        self.assertEqual(result[-2:],['--gameDir','/fresh'])
        self.assertNotIn('--gameDir',argv)

    def test_duplicate_selector_rejected(self):
        with self.assertRaisesRegex(ValueError,'Duplicate option'):
            a.set_option(['--gameDir','a','--gameDir','b'],'--gameDir','c')

    def test_missing_selector_value_rejected(self):
        with self.assertRaisesRegex(ValueError,'Missing option'):
            a.set_option(['--gameDir'],'--gameDir','c')

    def role(self,side):
        cwd=Path('/profile');port=25631
        command=[str(a.JAVA),'-Xmx1280m','-XX:ActiveProcessorCount=2','-cp','/lib.jar','cpw.mods.bootstraplauncher.BootstrapLauncher',
                 '--launchTarget','forgeclientdev' if side=='client' else 'forgeserver','--gameDir',str(cwd)]
        if side=='server':command.append('nogui')
        else:
            for k,v in [('--username',a.NAME),('--uuid',a.UUID),('--accessToken','0'),('--quickPlayMultiplayer','127.0.0.1:25631')]:command.extend([k,v])
        files=[{'path':str(a.JAVA),'sha256':a.JAVA_SHA},{'path':'/lib.jar','sha256':'0'*64}]
        return command,cwd,port,files

    def test_literal_server_role(self):
        cmd,cwd,port,files=self.role('server');a.validate_command(cmd,'server',cwd,port,files)

    def test_literal_client_role(self):
        cmd,cwd,port,files=self.role('client');a.validate_command(cmd,'client',cwd,port,files)

    def test_wrong_side(self):
        cmd,cwd,port,files=self.role('client')
        with self.assertRaisesRegex(ValueError,'side/profile'):
            a.validate_command(cmd,'server',cwd,port,files)

    def test_remote_endpoint(self):
        cmd,cwd,port,files=self.role('client');cmd[-1]='example.com:25631'
        with self.assertRaisesRegex(ValueError,'endpoint'):
            a.validate_command(cmd,'client',cwd,port,files)

    def test_unpinned_code(self):
        cmd,cwd,port,files=self.role('server');cmd[cmd.index('-cp')+1]='/other.jar'
        with self.assertRaisesRegex(ValueError,'Unpinned explicit'):
            a.validate_command(cmd,'server',cwd,port,files)

    def test_hidden_response_file(self):
        cmd,cwd,port,files=self.role('server');cmd.insert(1,'@secret')
        with self.assertRaisesRegex(ValueError,'Opaque/injected'):
            a.validate_command(cmd,'server',cwd,port,files)

    def test_account_extra(self):
        cmd,cwd,port,files=self.role('client');cmd.extend(['--xuid','unexpected'])
        with self.assertRaisesRegex(ValueError,'Unapproved client'):
            a.validate_command(cmd,'client',cwd,port,files)

    def test_heap_override(self):
        cmd,cwd,port,files=self.role('server');cmd.insert(1,'-Xmx2560m')
        with self.assertRaisesRegex(ValueError,'Heap differs'):
            a.validate_command(cmd,'server',cwd,port,files)

if __name__=='__main__':unittest.main()
