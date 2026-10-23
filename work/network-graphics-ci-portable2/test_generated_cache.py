"""Synthetic cache provenance checks; no native commands or cache writes."""
import copy
from pathlib import Path
from types import SimpleNamespace
import stat
import unittest
from unittest.mock import patch
import graphics_preflight as g
import test_graphics_preflight as baseline

class GeneratedCacheTests(unittest.TestCase):
    def setUp(self):
        self.sha = 'a' * 64
        self.pins = {'/etc/ld.so.cache': self.sha}
        self.generated = {'/etc/ld.so.cache': {'kind': 'root-owned-ldconfig-cache', 'sha256': self.sha}}
    def check(self):
        with patch.object(Path, 'resolve', side_effect=lambda strict=True: Path('/etc/ld.so.cache')), patch.object(Path, 'is_symlink', return_value=False), patch.object(Path, 'stat', return_value=SimpleNamespace(st_mode=stat.S_IFREG|0o644, st_size=1234, st_uid=0)):
            return g.validate_generated_config(self.generated, self.pins, baseline.S)
    def test_exact_cache_only(self):
        self.assertEqual(self.check(), {'/etc/ld.so.cache'})
    def test_other_or_missing_generated_input_rejected(self):
        for value in ({}, {'/tmp/cache': self.generated['/etc/ld.so.cache']}, {**self.generated, '/etc/other': {}}):
            self.generated = value
            with self.assertRaises(ValueError): self.check()
    def test_hash_kind_and_extra_claims_rejected(self):
        original = copy.deepcopy(self.generated)
        for field, value in (('sha256','b'*64), ('kind','package-owned'), ('package','libc-bin')):
            self.generated = copy.deepcopy(original);self.generated['/etc/ld.so.cache'][field]=value
            with self.assertRaises(ValueError): self.check()
    def test_untrusted_cache_and_ancestors_rejected(self):
        for uid,mode,size in ((1,stat.S_IFREG|0o644,12),(0,stat.S_IFREG|0o666,12),(0,stat.S_IFDIR|0o755,12),(0,stat.S_IFREG|0o644,0),(0,stat.S_IFREG|0o644,g.MIB+1)):
            with patch.object(Path,'resolve',return_value=Path('/etc/ld.so.cache')),patch.object(Path,'is_symlink',return_value=False),patch.object(Path,'stat',return_value=SimpleNamespace(st_uid=uid,st_mode=mode,st_size=size)):
                with self.assertRaises(ValueError):g.validate_generated_config(self.generated,self.pins,baseline.S)
    def test_redirect_rejected(self):
        with patch.object(Path,'resolve',return_value=Path('/tmp/cache')):
            with self.assertRaises(ValueError):g.validate_generated_config(self.generated,self.pins,baseline.S)

class CacheMappingTests(unittest.TestCase):
    def test_schema2_cache_is_separate_and_all_file_hashes_remain_required(self):
        from test_installed_provenance import InstalledProvenanceTests
        fixture=InstalledProvenanceTests('test_observed_receipt_accepts_exact_pins_without_archive_chain');fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        receipt=copy.deepcopy(fixture.receipt);receipt['schema']=2
        receipt['generated_config']={'/etc/ld.so.cache':{'kind':'root-owned-ldconfig-cache','sha256':'a'*64}}
        pins={r['path']:r['sha256'] for r in fixture.lock['inputs']};pins['/etc/ld.so.cache']='a'*64
        receipt['file_sha256']['/etc/ld.so.cache']='a'*64
        with patch.object(g,'validate_generated_config',return_value={'/etc/ld.so.cache'}):
            g.validate_installed_observations(receipt,fixture.lock,pins,baseline.S)
            receipt['file_packages']['/etc/ld.so.cache']='libc-bin:amd64=1'
            with self.assertRaisesRegex(ValueError,'package ownership'):g.validate_installed_observations(receipt,fixture.lock,pins,baseline.S)
            receipt['file_packages'].pop('/etc/ld.so.cache')
            receipt['file_sha256']['/etc/ld.so.cache']='b'*64
            with self.assertRaisesRegex(ValueError,'SHA-256'):g.validate_installed_observations(receipt,fixture.lock,pins,baseline.S)
