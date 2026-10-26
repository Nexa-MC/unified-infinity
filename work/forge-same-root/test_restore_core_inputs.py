import hashlib
import io
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import patch
import urllib.error
import restore_core_inputs as r

class Response(io.BytesIO):
    status = 200
    def geturl(self): return 'https://original.example/a'

class Tests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.root = Path(self.tmp.name)
        self.data = b'original bytes'
        self.row = {'path':'store/a.jar','bytes':len(self.data),'sha256':hashlib.sha256(self.data).hexdigest(),
                    'urls':['https://original.example/a','https://original.example/b']}
        self.deadline = time.monotonic()+10
    def tearDown(self): self.tmp.cleanup()
    def test_denials_stop_without_second_url(self):
        for status in (401,403,407,451,429,500):
            with self.subTest(status=status), patch.object(r.urllib.request,'build_opener') as factory:
                factory.return_value.open.side_effect=urllib.error.HTTPError(self.row['urls'][0],status,'fail',{},None)
                with self.assertRaises(urllib.error.HTTPError):r.download(self.row,self.root/'a',{'original.example'},self.deadline)
                self.assertEqual(factory.return_value.open.call_count,1)
                self.assertEqual(list(self.root.iterdir()),[])
    def test_missing_only_next_locked_url(self):
        for status in (404,410):
            with self.subTest(status=status), patch.object(r.urllib.request,'build_opener') as factory:
                factory.return_value.open.side_effect=[urllib.error.HTTPError('u',status,'missing',{},None),Response(self.data)]
                result=r.download(self.row,self.root/'a',{'original.example'},self.deadline)
                self.assertEqual(factory.return_value.open.call_count,2);self.assertEqual(result['sha256'],self.row['sha256'])
                (self.root/'a').unlink()
    def test_wrong_hash_is_terminal(self):
        with patch.object(r.urllib.request,'build_opener') as factory:
            factory.return_value.open.return_value=Response(b'x'*len(self.data))
            with self.assertRaises(ValueError):r.download(self.row,self.root/'a',{'original.example'},self.deadline)
            self.assertEqual(factory.return_value.open.call_count,1);self.assertEqual(list(self.root.iterdir()),[])
    def test_same_root_copy_no_network(self):
        src=self.root/'source';src.write_bytes(self.data)
        with patch.object(r.urllib.request,'build_opener',side_effect=AssertionError('network')):
            result=r.seed(self.row,self.root,{self.row['sha256']:src},set(),self.deadline)
        self.assertEqual(result['method'],'same-root-exact-copy')
    def test_missing_fml_does_not_download(self):
        with patch.object(r.urllib.request,'build_opener',side_effect=AssertionError('network')):
            with self.assertRaises(ValueError):r.seed(self.row,self.root,{},set(),self.deadline,False)
    def test_redirect_and_path_escape(self):
        for url in ('http://original.example/a','https://other.example/a','https://user@original.example/a'):
            with self.assertRaises(ValueError):r.valid_url(url,{'original.example'})
        for path in ('../escape','/tmp/escape','a/../escape'):
            with self.assertRaises(ValueError):r.local(self.root,path)
        (self.root/'link').symlink_to(self.root/'store')
        with self.assertRaises(ValueError):r.local(self.root,'link/a')
    def test_expired_deadline_no_work(self):
        with self.assertRaises(TimeoutError):r.seed(self.row,self.root,{},set(),time.monotonic()-1)
        self.assertEqual(list(self.root.iterdir()),[])
    def test_actual_locks_only_read(self):
        repo=Path(__file__).resolve().parents[2]
        core=r.read_lock(repo/'work/network-pair-cold-glue/profiles/ffapi-core-dependency-lock.json',r.CORE_SHA)
        product=r.read_lock(repo/'work/network-pair-cold-glue/product-input-lock.json',r.PRODUCT_SHA)
        self.assertEqual(len(core['artifacts']),706)
        extras=[x for x in product['artifacts'] if x['path'] in r.QSL or (x.get('phase')=='snapshot' and '/1.2.1-SNAPSHOT/' in x['path'])]
        self.assertEqual(len(extras),6)
if __name__=='__main__': unittest.main()
