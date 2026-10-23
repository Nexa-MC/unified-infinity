import unittest
from unittest.mock import Mock, patch
from pathlib import Path
from types import SimpleNamespace
import supervisor as s
HASH='ee5d244d47458564a6de33a7d08f8b72a1418c17469ebbd2e3fcc1136ad72c0f'
class FixedForms(unittest.TestCase):
 def setUp(self):self.proc=SimpleNamespace(root=Path('/synthetic'),same=Mock());self.row={'pid':123}
 def tag(self,raw):
  with patch.object(s,'read_bounded',return_value=raw),patch.object(s.time,'monotonic',return_value=0):return s.fixed_lshw_argv_tag(self.proc,self.row,HASH,1)
 def test_exact_forms(self):
  for raw,tag in [(b'lshw\0-class\0processor\0','OSHI_PROCESSOR_FORM'),(b'lshw\0-C\0display\0','OSHI_DISPLAY_FORM'),(b'lshw\0-C\0system\0','OSHI_SYSTEM_FORM')]:self.assertEqual(self.tag(raw),tag)
 def test_wrong_hash_reads_nothing(self):
  with patch.object(s,'read_bounded') as read:self.assertEqual(s.fixed_lshw_argv_tag(self.proc,self.row,'wrong',1),'NOT_CLASSIFIED');read.assert_not_called()
 def test_extra_secret_argument_not_emitted(self):self.assertEqual(self.tag(b'lshw\0-C\0display\0SECRET\0'),'OTHER_FORM')
 def test_missing_final_nul_and_different_argv0(self):
  for raw in [b'lshw\0-C\0display',b'/usr/bin/lshw\0-C\0display\0',b'lshw -C display\0']:self.assertEqual(self.tag(raw),'OTHER_FORM')
 def test_identity_race(self):self.proc.same.side_effect=ValueError('SECRET');self.assertEqual(self.tag(b'lshw\0-C\0display\0'),'UNAVAILABLE')
 def test_changed_bytes(self):
  with patch.object(s,'read_bounded',side_effect=[b'a',b'b']),patch.object(s.time,'monotonic',return_value=0):self.assertEqual(s.fixed_lshw_argv_tag(self.proc,self.row,HASH,1),'UNAVAILABLE')
 def test_oversize_and_read_error_are_opaque(self):
  for err in [ValueError('SECRET overflow'),PermissionError('SECRET')]:
   with patch.object(s,'read_bounded',side_effect=err),patch.object(s.time,'monotonic',return_value=0):self.assertEqual(s.fixed_lshw_argv_tag(self.proc,self.row,HASH,1),'UNAVAILABLE')
 def test_expired_budget(self):
  with patch.object(s,'read_bounded') as read,patch.object(s.time,'monotonic',return_value=2):self.assertEqual(s.fixed_lshw_argv_tag(self.proc,self.row,HASH,1),'UNAVAILABLE');read.assert_not_called()
