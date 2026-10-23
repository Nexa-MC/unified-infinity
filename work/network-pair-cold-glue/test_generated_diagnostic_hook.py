"""Failure-only hook tests; no subprocess, generator or game executes."""
from contextlib import redirect_stdout
import io
import json
from pathlib import Path
import tempfile
import time
import unittest
from unittest import mock
import driver


class FailureDiagnosticHook(unittest.TestCase):
    def exercise(self, name, code, diagnostic_error=None):
        with tempfile.TemporaryDirectory() as folder:
            consumer=Path(folder)
            step={'name':name,'command':['not-executed'],'cwd':folder,'environment':{},'timeoutSeconds':10}
            stream=io.StringIO()
            def command(*args,**kwargs):
                kwargs['stdout'].write('x'*60000+'\nORIGINAL_EXPORT_FAILURE\n')
                return mock.Mock(returncode=code)
            def diagnostics(*args):
                if diagnostic_error:raise diagnostic_error
                print('GENERATED_OUTPUT_DIAGNOSTIC {"diagnosticOnly":true}')
            with mock.patch.object(driver.bounded_process,'run',side_effect=command), \
                 mock.patch.object(driver.generated_output_diagnostics,'emit',side_effect=diagnostics) as emit, \
                 redirect_stdout(stream):
                if code:
                    with self.assertRaisesRegex(ValueError,'Official preparation failed'):
                        driver.execute_step(consumer,step,time.monotonic()+10)
                else:
                    driver.execute_step(consumer,step,time.monotonic()+10)
            receipt=json.loads((consumer/'cold-runtime-evidence'/(name+'.json')).read_text())
            return stream.getvalue(),emit.call_count,receipt

    def test_export_failure_keeps_original_rejection_and_prints_after_tail(self):
        text,calls,receipt=self.exercise('export-official-client',1)
        self.assertEqual(calls,1)
        self.assertEqual(receipt['status'],'FAILED')
        self.assertEqual(receipt['exitCode'],1)
        self.assertGreater(text.index('GENERATED_OUTPUT_DIAGNOSTIC'),text.index('ORIGINAL_EXPORT_FAILURE'))
        self.assertLess(len(text),49000)

    def test_success_starts_no_diagnostics(self):
        _,calls,receipt=self.exercise('export-official-client',0)
        self.assertEqual(calls,0);self.assertEqual(receipt['status'],'PASS')

    def test_other_failure_starts_no_diagnostics(self):
        _,calls,receipt=self.exercise('installer-client',1)
        self.assertEqual(calls,0);self.assertEqual(receipt['status'],'FAILED')

    def test_diagnostic_failure_cannot_mask_export_failure(self):
        text,calls,receipt=self.exercise('export-official-client',1,OSError('fixture detail'))
        self.assertEqual(calls,1)
        self.assertEqual(receipt['status'],'FAILED')
        self.assertIn('DIAGNOSTIC_COLLECTION_FAILED',text)
        self.assertNotIn('fixture detail',text)


if __name__=='__main__':unittest.main()
