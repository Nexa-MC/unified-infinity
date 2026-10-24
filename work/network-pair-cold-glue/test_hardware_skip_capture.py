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
        driver.require_hardware_observation({'server':result,'client':result})
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

    def test_overlarge_log_and_marker_fail_closed(self):
        for content in (b'x'*(events.MAX_LOG_BYTES+1),
                        b'{"kind":"hardware_inventory_skip_diagnostic","padding":"'+b'x'*512+b'"}'):
            result=self.capture(content)
            with self.assertRaises(ValueError):
                driver.require_hardware_observation({'server':result,'client':result})

if __name__=='__main__':unittest.main()
