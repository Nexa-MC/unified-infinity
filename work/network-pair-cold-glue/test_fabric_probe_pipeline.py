"""Source/adapter unit regressions only; no Java, game or CI execution."""
from pathlib import Path
import tempfile,time,unittest
from unittest import mock
import fabric_probe_pipeline as p
class PipelineTests(unittest.TestCase):
 def test_source_prepare_and_mutation(self):
  repo=Path(__file__).resolve().parents[2]
  with tempfile.TemporaryDirectory() as tmp:
   root=Path(tmp);r=p.prepare(repo,root)
   self.assertFalse(r['compiled']);self.assertTrue(r['diagnostic_only'])
   p.verify_source(root)
   added=root/p.SOURCE/'src/main/java/Unreviewed.java';added.write_text('class Unreviewed {}')
   with self.assertRaisesRegex(ValueError,'source inventory'):p.verify_source(root)
   added.unlink();p.verify_source(root)
   with self.assertRaises(ValueError):p.prepare(repo,root)
   (root/p.SOURCE/'protocol-schema.json').write_text('{}')
   with self.assertRaises(ValueError):p.verify_source(root)
 def test_expired_before_any_build(self):
  with tempfile.TemporaryDirectory() as tmp,mock.patch.object(p,'verify_source',return_value=Path(tmp)),mock.patch.object(p,'configure') as config:
   with self.assertRaises(ValueError):p.build(tmp,time.monotonic()-1,mock.Mock())
   config.assert_not_called()
 def test_original_deadline_forwarded(self):
  import sys
  from types import SimpleNamespace
  with tempfile.TemporaryDirectory() as tmp,mock.patch.object(p,'verify_source',return_value=Path(tmp)),mock.patch.object(p,'configure',return_value={'fixture':True}):
   root=Path(tmp);(root/'work').mkdir();step=mock.Mock();bundle=mock.Mock(return_value={'fixture':True})
   deadline=time.monotonic()+30;before=time.time()
   with mock.patch.dict(sys.modules,{'fabric_probe_build_validation':SimpleNamespace(create_bundle=bundle)}):result=p.build(root,deadline,step)
   self.assertEqual(result,{'fixture':True});args=step.call_args.args
   self.assertEqual(args[2],deadline);self.assertTrue(step.call_args.kwargs['diagnostic'])
   command=args[1]['command'];epoch=float(command[command.index('--deadline-epoch')+1])
   self.assertLessEqual(epoch,before+30);self.assertGreater(epoch,before+27)
   self.assertNotIn('GITHUB_ACTIONS',args[1]['environment'])
if __name__=='__main__':unittest.main()
