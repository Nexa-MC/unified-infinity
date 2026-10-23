import ast
import hashlib
from pathlib import Path
import tempfile
import time
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch
import supervisor as s

class ExecutableDiagnostic(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        (self.root / '123').mkdir()
        self.target = self.root / 'jspawnhelper'
        self.target.write_bytes(b'fixed synthetic executable')
        (self.root / '123/exe').symlink_to(self.target)
        self.row = dict(pid=123, start_ticks=7, pgrp=123, session=123)
        self.proc = SimpleNamespace(root=self.root, same=Mock(return_value=self.row))
    def run_observation(self):
        return s.rejected_child_executable(self.proc, self.row, time.monotonic()+2)
    def test_exact_hash_and_public_hint_without_path(self):
        value = self.run_observation()
        self.assertEqual(value['status'], 'OBSERVED_NOT_ADMITTED')
        self.assertEqual(value['sha256'], hashlib.sha256(self.target.read_bytes()).hexdigest())
        self.assertEqual(value['executable_basename_hint'], 'jspawnhelper')
        self.assertNotIn(str(self.root), str(value))
        self.assertEqual(self.proc.same.call_count, 3)
    def test_arbitrary_basename_is_withheld(self):
        other = self.root / 'PRIVATE_SECRET_abc'
        self.target.rename(other)
        (self.root/'123/exe').unlink(); (self.root/'123/exe').symlink_to(other)
        value=self.run_observation()
        self.assertEqual(value['executable_basename_hint'], 'WITHHELD')
        self.assertNotIn('PRIVATE_SECRET', str(value))
    def test_gone(self):
        (self.root/'123/exe').unlink()
        self.assertEqual(self.run_observation()['status'], 'GONE')
    def test_unreadable_does_not_echo_error(self):
        with patch.object(s.os, 'open', side_effect=PermissionError('SECRET')):
            value=self.run_observation()
        self.assertEqual(value['status'], 'UNREADABLE');self.assertNotIn('SECRET',str(value))
    def test_oversize_has_no_hash(self):
        with self.target.open('wb') as f: f.truncate(8*s.MIB+1)
        value=self.run_observation();self.assertEqual(value['status'],'OVERSIZE');self.assertNotIn('sha256',value)
    def test_process_reuse_discards_executable(self):
        self.proc.same.side_effect=[self.row,ValueError('changed')]
        value=self.run_observation();self.assertEqual(value['status'],'RACED_OR_UNAVAILABLE');self.assertNotIn('sha256',value)
    def test_executable_swap_discards_hash(self):
        with patch.object(s.os,'readlink',side_effect=[str(self.target),str(self.target)+'changed']):
            value=self.run_observation()
        self.assertEqual(value['status'],'RACED_OR_UNAVAILABLE');self.assertNotIn('sha256',value)
    def test_file_change_discards_hash(self):
        original=s.os.read
        def changing(fd,n):
            out=original(fd,n)
            if out:self.target.write_bytes(b'changed')
            return out
        with patch.object(s.os,'read',side_effect=changing):value=self.run_observation()
        self.assertEqual(value['status'],'RACED_OR_UNAVAILABLE');self.assertNotIn('sha256',value)
    def test_budget_expired_reads_nothing(self):
        with patch.object(s.os,'open') as op:
            value=s.rejected_child_executable(self.proc,self.row,0)
        self.assertEqual(value['status'],'BUDGET_EXHAUSTED');op.assert_not_called()
    def test_four_child_cap_and_exception_is_optional(self):
        with patch.object(s,'rejected_child_executable',side_effect=RuntimeError('SECRET')) as observe:
            value=s.rejected_children_diagnostics(self.proc,[self.row]*9)
        self.assertEqual(observe.call_count,4);self.assertTrue(value['truncated']);self.assertNotIn('SECRET',str(value))
    def test_diagnostic_source_never_reads_private_process_fields(self):
        source=Path(s.__file__).read_text().split('def rejected_child_executable',1)[1].split('class Proc:',1)[0]
        self.assertNotIn("/cmdline",source);self.assertNotIn("/environ",source);self.assertNotIn("/fd/",source)
    def test_pump_normalization_preserves_exact_rejection(self):
        source=Path(s.__file__).read_text()
        line="            self.report['unexpected_descendant_diagnostics'] = rejected_children_diagnostics(self.proc, escaped)\n"
        self.assertEqual(source.count(line),1)
        def pump_hash(text):
            tree=ast.parse(text);pair=next(n for n in tree.body if isinstance(n,ast.ClassDef) and n.name=='Pair')
            pump=next(n for n in pair.body if isinstance(n,ast.FunctionDef) and n.name=='pump')
            return hashlib.sha256(ast.dump(pump,include_attributes=False).encode()).hexdigest()
        normalized=source.replace(line,'',1)
        expected='72e7aa503dd93b56b1138cd280b7fa3e8e85d5892abd07ffe4a56147e7f37b78'
        self.assertEqual(pump_hash(normalized),expected)
        self.assertNotEqual(pump_hash(normalized.replace("raise ValueError('Unexpected game descendant or adopted helper')",'pass')),expected)

if __name__=='__main__':unittest.main()
