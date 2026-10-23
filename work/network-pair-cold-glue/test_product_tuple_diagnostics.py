import contextlib
import hashlib
import io
import json
from pathlib import Path
import tempfile
import time
import unittest
from unittest import mock
import zipfile
import product_tuple_diagnostics as d
import refreshed_candidate as r

class Diagnostics(unittest.TestCase):
    def test_success_silent(self):
        with mock.patch.object(r,'inspect_tuple',return_value={'ok':True}), mock.patch.object(d,'emit') as emit:
            self.assertEqual(d.inspect_tuple(None,None,None,None,None),{'ok':True})
            emit.assert_not_called()

    def test_failure_never_accepted_or_masked(self):
        failure=r.Invalid('Tuple no longer reproduces the observed build reference: product')
        for error in (None,RuntimeError('private/path/secret')):
            with mock.patch.object(r,'inspect_tuple',side_effect=failure), mock.patch.object(d,'emit',side_effect=error) as emit, contextlib.redirect_stdout(io.StringIO()) as out:
                with self.assertRaises(r.Invalid) as caught:d.inspect_tuple(None,None,None,None,None)
                self.assertIs(caught.exception,failure)
                emit.assert_called_once()
                self.assertNotIn('private/path',out.getvalue())

    def fixture(self, root):
        artifacts={}
        for role in ('service','game','fml','product'):
            path=root/(role+'.jar')
            with zipfile.ZipFile(path,'w') as z:z.writestr('private/secret/token.txt','sensitive contents')
            artifacts[role]={'path':path.name,'bytes':path.stat().st_size,'sha256':hashlib.sha256(path.read_bytes()).hexdigest()}
        return {'observedOutputReference':{key:'0'*64 for key in artifacts},'requiredTasks':{key:[] for key in ('core','product','fml')}},artifacts

    def report(self, root, profile, artifacts, deadline):
        with contextlib.redirect_stdout(io.StringIO()) as out:
            report=d.emit(root,profile,artifacts,{},deadline)
        self.assertLessEqual(len(out.getvalue().encode()),d.MAX_REPORT)
        self.assertNotIn(str(root),out.getvalue())
        self.assertNotIn('sensitive contents',out.getvalue())
        self.assertNotIn('private/secret',out.getvalue())
        return report

    def test_mismatch_full_hashes_and_redacted_zip(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);profile,artifacts=self.fixture(root)
            report=self.report(root,profile,artifacts,time.monotonic()+20)
            for row in report['outputs']:
                self.assertEqual(row['actualSha256'],artifacts[row['role']]['sha256'])
                self.assertEqual(row['expectedSha256'],'0'*64)
                self.assertEqual(row['status'],'HASH_MISMATCH')
            self.assertIn('payloadAggregateSha256',report['outputs'][-1]['zip'])

    def test_malformed_zip(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);profile,artifacts=self.fixture(root)
            (root/'product.jar').write_bytes(b'not a zip')
            report=self.report(root,profile,artifacts,time.monotonic()+20)
            self.assertEqual(report['outputs'][-1]['zipStatus'],'BadZipFile')
            self.assertFalse(report['complete'])

    def test_oversize_and_deadline(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);profile,artifacts=self.fixture(root)
            with mock.patch.object(d.safe,'MAX_FILE',1):
                report=self.report(root,profile,artifacts,time.monotonic()+20)
            self.assertTrue(all(row['status']=='FILE_SIZE_LIMIT' for row in report['outputs']))
            report=self.report(root,profile,artifacts,time.monotonic()-1)
            self.assertTrue(all(row['status']=='DEADLINE' for row in report['outputs']))

    def test_receipt_success_summary_without_raw_log(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);profile,artifacts=self.fixture(root)
            receipts={}
            for role in ('core','product','fml'):
                log=root/(role+'.log');log.write_text('> Task :check\nBUILD SUCCESSFUL\nprivate secret text')
                logpin=r.pin(root,log)
                receipt=root/(role+'.json')
                receipt.write_text(json.dumps({'log':logpin,'exitCode':0,'inputsBefore':'a','inputsAfter':'a'}))
                receipts[role]=r.pin(root,receipt)
                profile['requiredTasks'][role]=[':check']
            with contextlib.redirect_stdout(io.StringIO()) as out:
                report=d.emit(root,profile,artifacts,receipts,time.monotonic()+20)
            for row in report['receipts']:
                self.assertTrue(row['successfulExit'] and row['buildSuccessful'] and row['inputsUnchanged'])
                self.assertEqual(row['executedRequiredTaskCount'],1)
            self.assertNotIn('private secret text',out.getvalue())

    def test_complete_product_baseline_and_unknown_name_redaction(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);profile,artifacts=self.fixture(root)
            product=root/'product.jar'
            with zipfile.ZipFile(product,'w') as z:
                z.writestr('META-INF/MANIFEST.MF','safe reference')
            summary=d.safe._zip(product,[time.monotonic()+20,d.safe.MAX_HASH_WORK],False,64)
            baseline=root/'baseline.json'
            baseline.write_text(json.dumps({'sha256':'0'*64,'tupleHashes':profile['observedOutputReference'],
                'tupleBytes':{key:artifacts[key]['bytes'] for key in artifacts},'zip':summary}))
            with zipfile.ZipFile(product,'w') as z:
                z.writestr('META-INF/MANIFEST.MF','changed private contents')
                z.writestr('/private/secret/key','hidden')
            with mock.patch.object(d,'BASELINE','baseline.json'):
                report=self.report(root,profile,artifacts,time.monotonic()+20)
            samples=report['outputs'][-1]['zip']['samples']
            self.assertEqual(samples[0]['name'],'META-INF/MANIFEST.MF')
            self.assertFalse(samples[0]['payloadMatchesReference'])
            self.assertTrue(samples[0]['selectedGeneratedMetadata'])
            self.assertNotIn('name',samples[1])
            self.assertEqual(len(samples[1]['nameSha256']),64)

    def test_symlink_rejected_without_target_disclosure(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);profile,artifacts=self.fixture(root)
            (root/'product.jar').unlink()
            (root/'product.jar').symlink_to(root/'service.jar')
            report=self.report(root,profile,artifacts,time.monotonic()+20)
            self.assertEqual(report['outputs'][-1]['status'],'UNSAFE_PATH')

    def test_real_gate_still_rejects(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);profile,artifacts=self.fixture(root)
            with mock.patch.object(d,'emit') as emit:
                with self.assertRaisesRegex(r.Invalid,'observed build reference'):
                    d.inspect_tuple(root,profile,artifacts,{},time.monotonic()+20)
                emit.assert_called_once()

if __name__=='__main__':unittest.main()
