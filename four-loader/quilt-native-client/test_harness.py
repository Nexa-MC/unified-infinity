import hashlib, importlib.util, json, pathlib, tempfile, unittest
from unittest.mock import patch
PATH=pathlib.Path(__file__).with_name('verify_profile.py')
spec=importlib.util.spec_from_file_location('quilt_client_verify',PATH)
v=importlib.util.module_from_spec(spec);spec.loader.exec_module(v)

class VerificationTests(unittest.TestCase):
    def test_checks_hash_and_missing_file(self):
        with tempfile.TemporaryDirectory() as d:
            p=pathlib.Path(d)/'test.jar';p.write_bytes(b'original')
            h=hashlib.sha256(b'original').hexdigest()
            v.checked(p,h)
            p.write_bytes(b'changed')
            with self.assertRaises(RuntimeError):v.checked(p,h)
            with self.assertRaises(RuntimeError):v.checked(p.with_name('absent.jar'),h)

    def test_mod_set_lock_and_bytes(self):
        with tempfile.TemporaryDirectory() as d:
            root=pathlib.Path(d);profile=root/'profile';mods=profile/'game/mods';mods.mkdir(parents=True)
            src=root/'original.jar';src.write_bytes(b'fixture');jar=mods/'original.jar';jar.write_bytes(src.read_bytes())
            h=hashlib.sha256(src.read_bytes()).hexdigest()
            lock={'mods':[{'source':'original.jar','path':'profile/game/mods/original.jar','sha256':h}]}
            lockfile=profile/'seed-report.json';lockfile.write_text(json.dumps(lock))
            with patch.object(v,'ROOT',root),patch.object(v,'PROFILE',profile),patch.object(v,'PINNED_MODS',{'original.jar':h}):
                self.assertEqual(len(v.verify_mods()),1)
                unexpected=mods/'unexpected.jar';unexpected.write_bytes(b'extra')
                with self.assertRaises(RuntimeError):v.verify_mods()
                unexpected.unlink();lock['mods'][0]['sha256']='0'*64;lockfile.write_text(json.dumps(lock))
                with self.assertRaises(RuntimeError):v.verify_mods()
                lock['mods'][0]['sha256']=h;lockfile.write_text(json.dumps(lock));jar.write_bytes(b'changed')
                with self.assertRaises(RuntimeError):v.verify_mods()

if __name__=='__main__':unittest.main()
