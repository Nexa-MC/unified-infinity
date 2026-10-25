import importlib.util,json,os,tempfile,time,unittest
from pathlib import Path
from unittest.mock import patch
import run as stage
class TestStage(unittest.TestCase):
 def test_original_four_inputs(self):
  rows=stage.forge_records();self.assertEqual(len(rows),4);self.assertEqual(len({r['sha256'] for r in rows}),4)
  self.assertTrue(all(r['urls'][0].startswith('https://maven.minecraftforge.net/') for r in rows))
 def test_budget_monotonic(self):
  import first_step_anchor as a
  deadline=stage.budget({'capturedMonotonic':100},now=110,wall=a.utc(a.START_UTC)+10);self.assertEqual(deadline,1120)
 def test_expired_absolute(self):
  import first_step_anchor as a
  with self.assertRaises(ValueError):stage.budget({'capturedMonotonic':100},now=110,wall=a.utc(a.CUTOFF_UTC)-200)
 def test_expired_local(self):
  import first_step_anchor as a
  with self.assertRaises(ValueError):stage.budget({'capturedMonotonic':100},now=1110,wall=a.utc(a.START_UTC))
 def test_pin_refuses_symlink(self):
  with tempfile.TemporaryDirectory() as td:
   p=Path(td)/'p';p.write_text('x');q=Path(td)/'q';q.symlink_to(p)
   with self.assertRaises(ValueError):stage.pin(q)
 def test_no_runtime_acceptance(self):
  self.assertEqual(set(stage.FALSE_FLAGS),{'gameLaunched','networkAcceptance','fullApiCompatibility','readyRuntimeBundle'})
  self.assertTrue(all(v is False for v in stage.FALSE_FLAGS.values()))
 def test_no_duplicate_outputs(self):
  with tempfile.TemporaryDirectory() as td:
   p=Path(td)/'r';stage.write(p,{'x':1})
   with self.assertRaises(FileExistsError):stage.write(p,{'x':2})
 def test_restore_deadline_before_call(self):
  with self.assertRaises(ValueError):stage.within(lambda: self.fail('called'),deadline=time.monotonic()-1)
 def test_real_source_prepare_only(self):
  repo=Path(__file__).resolve().parents[2];import sys
  sys.path.insert(0,str(repo/'work/network-pair-cold-glue'));import ffapi_sources,runtime_restore
  with tempfile.TemporaryDirectory() as td:
   root=Path(td)/'consumer';ffapi_sources.prepare(repo,root);r=runtime_restore.prepare(repo,root)
   self.assertEqual([s['name'] for s in r['steps']],['extract-toolchains','installer-client','installer-native-server','export-official-client','seal-official-client'])
   self.assertFalse(r['jvmStarted']);self.assertFalse(r['downloadsStarted']);self.assertFalse(r['missingOfficialInputs'])
if __name__=='__main__':unittest.main()
