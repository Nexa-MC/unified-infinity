import hashlib
import io
import json
from pathlib import Path
import signal
import tempfile
import time
import unittest
from unittest.mock import Mock, patch
import urllib.error
import strict_runtime_restore as s

class Response(io.BytesIO):
    status=200
    def geturl(self):return 'https://original.example/one'

class Tests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name)
        self.data=b'locked official bytes';self.row={'path':'ci/runtime-maven/test.jar','bytes':len(self.data),
            'sha1':hashlib.sha1(self.data).hexdigest(),'urls':['https://original.example/one','https://original.example/two'],
            'also_seed':['run/client-dev/libraries/test.jar']}
        support=self.root/'ci/runtime-restore';support.mkdir(parents=True)
        (support/'input-lock.json').write_text(json.dumps({'missingOfficialInputs':[],'allowedHosts':['original.example'],'artifacts':[self.row]}))
        self.runtime=Mock();self.runtime.verify_inputs.return_value={'status':'VERIFIED_PUBLIC_INPUTS_ONLY'}
        self.deadline=time.monotonic()+10
    def tearDown(self):self.tmp.cleanup()
    def test_sha1_original_and_alias_with_final_verification(self):
        with patch.object(s.transport.urllib.request,'build_opener') as factory:
            factory.return_value.open.return_value=Response(self.data)
            result=s.restore(self.root,self.runtime,self.deadline)
        self.assertEqual(result['restoredArtifacts'],1)
        self.assertEqual((self.root/self.row['path']).read_bytes(),self.data)
        self.assertEqual((self.root/self.row['also_seed'][0]).read_bytes(),self.data)
        self.assertEqual(self.runtime.verify_preparation.call_count,2)
        self.runtime.prepare_offline_installer_cache.assert_called_once_with(self.root)
        self.runtime.verify_inputs.assert_called_once_with(self.root)
        self.runtime.save.assert_called_once()
        self.assertEqual(signal.getitimer(signal.ITIMER_REAL),(0.0,0.0))
    def test_each_denial_stops_entire_runtime(self):
        for status in (401,403,407,451):
            with self.subTest(status=status),patch.object(s.transport.urllib.request,'build_opener') as factory:
                factory.return_value.open.side_effect=urllib.error.HTTPError('u',status,'denied',{},None)
                with self.assertRaises(urllib.error.HTTPError):s.restore(self.root,self.runtime,self.deadline)
                self.assertEqual(factory.return_value.open.call_count,1)
                self.runtime.verify_inputs.assert_not_called();self.runtime.save.assert_not_called()
                self.assertEqual(signal.getitimer(signal.ITIMER_REAL),(0.0,0.0))
    def test_all_digests_required(self):
        target=self.root/'a';target.write_bytes(self.data)
        row=dict(self.row,sha256='0'*64)
        with self.assertRaises(ValueError):s.transport.checked(target,row)
        row=dict(self.row,sha256=hashlib.sha256(self.data).hexdigest(),sha1='0'*40)
        with self.assertRaises(ValueError):s.transport.checked(target,row)
    def test_timeout_not_retried(self):
        with patch.object(s.transport.urllib.request,'build_opener') as factory:
            factory.return_value.open.side_effect=TimeoutError('deadline')
            with self.assertRaises(TimeoutError):s.restore(self.root,self.runtime,self.deadline)
            self.assertEqual(factory.return_value.open.call_count,1)
    def test_alarm_interrupts_blocking_download(self):
        old=signal.getsignal(signal.SIGALRM)
        with patch.object(s.transport.urllib.request,'build_opener') as factory:
            factory.return_value.open.side_effect=lambda *a,**kw:time.sleep(1)
            with self.assertRaises(TimeoutError):s.restore(self.root,self.runtime,time.monotonic()+0.02)
            self.assertEqual(factory.return_value.open.call_count,1)
        self.assertEqual(signal.getsignal(signal.SIGALRM),old)
        self.assertEqual(signal.getitimer(signal.ITIMER_REAL),(0.0,0.0))
        self.assertFalse(list(self.root.rglob('.restore-*')))
    def test_existing_alias_mismatch_stops(self):
        src=self.root/self.row['path'];src.parent.mkdir(parents=True);src.write_bytes(self.data)
        dest=self.root/self.row['also_seed'][0];dest.parent.mkdir(parents=True);dest.write_bytes(b'wrong')
        with patch.object(s.transport.urllib.request,'build_opener',side_effect=AssertionError('network')):
            with self.assertRaises(ValueError):s.restore(self.root,self.runtime,self.deadline)
        self.runtime.verify_inputs.assert_not_called()
if __name__=='__main__':unittest.main()
