"""Bounded diagnostic observation is required, never executable admission evidence."""
import copy
import json
from pathlib import Path
import tempfile
import unittest
import diagnostic_log_events as events
import driver

class HardwareCaptureTests(unittest.TestCase):
    def capture(self, content):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'client.log';path.write_bytes(content)
            return events.extract(path)

    def test_exact_marker_preserved_and_both_roles_required(self):
        row=json.dumps(events.HARDWARE_ROW).encode()
        result=self.capture(row+b'\n')
        self.assertEqual(result['hardware_transforms'],[events.HARDWARE_ROW])
        self.assertFalse(result['admission_evidence'])
        self.assertFalse(result['baseline_acceptance'])
        self.assertFalse(result['absence_of_process_evidence'])
        client=self.capture(row+b'\n'+json.dumps(events.CPU_ROW).encode()+b'\n')
        driver.require_hardware_observation({'server':result,'client':client})
        with self.assertRaises(ValueError):driver.require_hardware_observation({'client':result})

    def test_missing_duplicate_and_invalid_markers_do_not_pass(self):
        good=json.dumps(events.HARDWARE_ROW).encode()
        altered=dict(events.HARDWARE_ROW,baseline_acceptance=True)
        numeric=dict(events.HARDWARE_ROW,diagnostic_only=1)
        extra=dict(events.HARDWARE_ROW,raw_path='not-to-be-exported')
        for content in (b'ordinary log\n',good+b'\n'+good+b'\n',
                        json.dumps(altered).encode(),json.dumps(numeric).encode(),
                        json.dumps(extra).encode(),b'prefix '+good,good.replace(b'"state":',b'"state":"TRANSFORMED","state":')):
            with self.subTest(content=content):
                result=self.capture(content)
                with self.assertRaises(ValueError):
                    driver.require_hardware_observation({'server':result,'client':result})
                self.assertNotIn('not-to-be-exported',json.dumps(result))

    def test_cpu_marker_exact_cardinality_and_role_binding(self):
        hw=json.dumps(events.HARDWARE_ROW).encode()+b'\n'
        cpu=json.dumps(events.CPU_ROW).encode()+b'\n'
        server=self.capture(hw);client=self.capture(hw+cpu)
        self.assertEqual(client['cpu_description_transforms'],[events.CPU_ROW])
        driver.require_hardware_observation({'server':server,'client':client})
        for captures in ({'server':server,'client':server}, {'server':client,'client':client},
                         {'server':client,'client':server}, {'server':server,'client':self.capture(cpu)},
                         {'server':server,'client':self.capture(hw+cpu+cpu)}):
            with self.subTest(captures=captures),self.assertRaises(ValueError):
                driver.require_hardware_observation(captures)
        overflow=self.capture(hw+cpu+cpu)
        self.assertEqual(len(overflow['cpu_description_transforms']),1)
        self.assertTrue(overflow['overflow'])
        self.assertEqual(overflow['status'],'INVALID_OR_INCOMPLETE')

    def test_cpu_malformed_types_extra_fields_and_overlong_rows_are_redacted(self):
        hw=json.dumps(events.HARDWARE_ROW).encode()+b'\n'
        secret='SECRET_CPU_DESCRIPTION_NOT_EXPORTED'
        variants=[dict(events.CPU_ROW,diagnostic_only=1),dict(events.CPU_ROW,baseline_acceptance=0),
                  dict(events.CPU_ROW,baseline_acceptance=True),dict(events.CPU_ROW,state=secret),
                  dict(events.CPU_ROW,raw_cpu=secret)]
        raw=json.dumps(events.CPU_ROW).encode()
        rows=[json.dumps(row).encode() for row in variants]+[b'prefix '+raw,
              raw.replace(b'"state":',b'"state":"TRANSFORMED","state":'),
              b'{"kind":"cpu_description_skip_diagnostic","raw":"'+secret.encode()+b'x'*512+b'"}']
        server=self.capture(hw)
        for row in rows:
            capture=self.capture(hw+row+b'\n')
            self.assertEqual(capture['status'],'INVALID_OR_INCOMPLETE')
            self.assertEqual(capture['malformed_rows'],1)
            self.assertEqual(capture['cpu_description_transforms'],[])
            self.assertNotIn(secret,json.dumps(capture))
            with self.assertRaises(ValueError):
                driver.require_hardware_observation({'server':server,'client':capture})

    def test_overlarge_log_and_marker_fail_closed(self):
        for content in (b'x'*(events.MAX_LOG_BYTES+1),
                        b'{"kind":"hardware_inventory_skip_diagnostic","padding":"'+b'x'*512+b'"}'):
            result=self.capture(content)
            with self.assertRaises(ValueError):
                driver.require_hardware_observation({'server':result,'client':result})

if __name__=='__main__':unittest.main()
