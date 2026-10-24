"""Synthetic safe extractor fixtures, not process identity or runtime proof."""
from pathlib import Path
from unittest import mock
import hashlib
import inspect
import json
import tempfile
import unittest
import diagnostic_log_events as d
import driver

EVENT={'kind':'processbuilder_debug','requested_command':'LSCPU','caller':'OSHI_EXECUTING_COMMAND_RUN_NATIVE',
       'pid':12,'diagnostic_only':True,'admission_evidence':False}
STATUS={'kind':'processbuilder_diagnostic_status','state':'STARTED','diagnostic_only':True,'admission_evidence':False}
SECRET='SENTINEL_SECRET_DO_NOT_EMIT'

def line(value):return json.dumps(value,separators=(',',':')).encode()+b'\n'

class DiagnosticLogTests(unittest.TestCase):
    def extract(self,payload):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'server.log';path.write_bytes(payload)
            result=d.extract(path)
            self.assertFalse(result['observation_complete']);self.assertFalse(result['admission_evidence'])
            self.assertFalse(result['absence_of_process_evidence']);self.assertFalse(result['baseline_acceptance'])
            self.assertNotIn(SECRET,json.dumps(result))
            return result

    def test_valid_early_events_survive_tail_loss_and_pin_whole_log(self):
        payload=line(STATUS)+line(EVENT)+b'x'*40000+b'\n'
        self.assertNotIn(b'processbuilder_debug',payload[-32000:])
        r=self.extract(payload)
        self.assertEqual(r['events'],[EVENT]);self.assertEqual(r['statuses'],[STATUS])
        self.assertEqual(r['status'],'OBSERVED_INCOMPLETE')
        self.assertEqual(r['log_pin']['sha256'],hashlib.sha256(payload).hexdigest())
        self.assertEqual(r['log_pin']['bytes'],len(payload))

    def test_no_capture_is_unobserved_not_absence(self):
        for payload in [b'',b'ordinary '+SECRET.encode()+b'\n']:
            with self.subTest(payload=payload):self.assertEqual(self.extract(payload)['status'],'UNOBSERVED')
        r=d.extract('/nonexistent/diagnostic-fixture.log')
        self.assertEqual(r['status'],'UNOBSERVED');self.assertIsNone(r['log_pin'])

    def test_malformed_unknown_and_nonliteral_types_never_echo(self):
        variants=[dict(EVENT,pid=True),dict(EVENT,pid=0),dict(EVENT,pid=2147483648),dict(EVENT,pid=1.0),
                  dict(EVENT,requested_command=SECRET),dict(EVENT,caller=SECRET),dict(EVENT,extra=SECRET),
                  dict(EVENT,diagnostic_only=1),dict(EVENT,admission_evidence=0),dict(STATUS,state=SECRET),
                  dict(EVENT,caller=[])]
        for item in variants:
            with self.subTest(item=item):
                r=self.extract(line(item));self.assertEqual(r['status'],'INVALID_OR_INCOMPLETE')
                self.assertEqual(r['malformed_rows'],1);self.assertFalse(r['events']);self.assertFalse(r['statuses'])

    def test_malformed_directness_duplicate_key_and_line_cap(self):
        raw=line(EVENT).rstrip(b'\n')
        variants=[b'prefix '+raw+b' '+SECRET.encode(),b' '+raw,
                  b'{"kind":"processbuilder_debug","kind":"processbuilder_debug","secret":"'+SECRET.encode()+b'"}',
                  b'{"kind":"processbuilder_debug",'+SECRET.encode(),
                  b'{"kind":"processbuilder_debug","secret":"'+SECRET.encode()+b'x'*600+b'"}',
                  b'{"kind":"processbuilder_debug","secret":"\xff"}']
        for item in variants:
            with self.subTest(item=item[:50]):
                r=self.extract(item+b'\n');self.assertEqual(r['malformed_rows'],1)
                self.assertEqual(r['status'],'INVALID_OR_INCOMPLETE')

    def test_event_and_status_overflow_bounded(self):
        r=self.extract(line(EVENT)*65+line(STATUS)*3)
        self.assertEqual(len(r['events']),64);self.assertEqual(len(r['statuses']),2)
        self.assertTrue(r['overflow']);self.assertEqual(r['status'],'INVALID_OR_INCOMPLETE')
        r=self.extract(line(EVENT)*64+line(STATUS)*2)
        self.assertFalse(r['overflow']);self.assertEqual(r['status'],'OBSERVED_INCOMPLETE')

    def test_overcap_log_not_read_or_falsely_pinned(self):
        r=self.extract(b'x'*(d.MAX_LOG_BYTES+1))
        self.assertTrue(r['overflow']);self.assertIsNone(r['log_pin'])
        self.assertEqual(r['status'],'INVALID_OR_INCOMPLETE')
        r=self.extract(b'x'*d.MAX_LOG_BYTES)
        self.assertEqual(r['log_pin']['bytes'],d.MAX_LOG_BYTES)

    def test_symlink_and_directory_are_not_read(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp);file=path/'file';file.write_bytes(line(EVENT));link=path/'link';link.symlink_to(file)
            self.assertFalse(d.extract(link)['events']);self.assertFalse(d.extract(path)['events'])

    def test_changed_log_is_not_pinned_or_extracted(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'file';path.write_bytes(line(EVENT))
            original=d.os.fstat
            count=0
            def changed(fd):
                nonlocal count
                s=original(fd);count+=1
                if count==2:
                    from types import SimpleNamespace
                    return SimpleNamespace(st_dev=s.st_dev,st_ino=s.st_ino,st_size=s.st_size,
                        st_mtime_ns=s.st_mtime_ns+1,st_ctime_ns=s.st_ctime_ns)
                return s
            with mock.patch.object(d.os,'fstat',side_effect=changed):r=d.extract(path)
            self.assertTrue(r['log_changed']);self.assertIsNone(r['log_pin']);self.assertFalse(r['events'])

    def test_ordinary_driver_never_calls_extractor(self):
        from test_driver_cleanup import DriverCleanupTests
        with mock.patch.object(d,'extract',side_effect=AssertionError('ordinary extractor called')) as extractor:
            receipt,events,error,processes,graphics=DriverCleanupTests().run_driver()
        self.assertIsNone(error);self.assertTrue(receipt['gameAcceptance'])
        self.assertNotIn('diagnosticCaptures',receipt);extractor.assert_not_called()

    def test_driver_integration_is_opt_in_and_before_failed_code_raise(self):
        source=inspect.getsource(driver.execute)
        integration=source.index('import diagnostic_log_events')
        self.assertEqual(source[:integration].rstrip().splitlines()[-1].strip(),'if diagnostic_fml:')
        self.assertLess(source.index("if log.exists():print('ACTUAL_PAIR_LOG"),integration)
        self.assertLess(integration,source.index("require(code==0,'Actual pair failed:"))
        # Existing ordinary cleanup tests execute the ordinary path. This source
        # check prevents accidentally moving extraction outside the opt-in guard.

if __name__=='__main__':unittest.main()
