"""Exact reviewed roots; unknown runtime trace paths remain prohibited."""
import unittest
import graphics_runner as g
class DiscoveryRoots(unittest.TestCase):
    def test_exact_egl_roots(self):
        self.assertEqual(g.REQUIRED['egl_dispatch'],'/usr/lib/x86_64-linux-gnu/libEGL.so.1')
        self.assertEqual(g.REQUIRED['mesa_egl'],'/usr/lib/x86_64-linux-gnu/libEGL_mesa.so.0')
        self.assertEqual(len(g.REQUIRED),6)
    def test_cache_is_not_claimed_as_package(self):
        import inspect
        s=inspect.getsource(g.observe)
        self.assertIn("if r['path'] != str(loader_cache)",s)
        self.assertIn("root-owned-ldconfig-cache",s)
        self.assertIn("Loader cache changed during installed observation",s)

class CacheSnapshot(unittest.TestCase):
    def snapshot(self, changed=False, oversized=False):
        import io, stat
        from types import SimpleNamespace
        from unittest import mock
        row = dict(st_dev=1,st_ino=2,st_size=3,st_mtime_ns=4,st_ctime_ns=5,st_mode=stat.S_IFREG|0o644,st_uid=0,st_gid=0)
        if oversized: row['st_size']=g.MIB+1
        before=SimpleNamespace(**row);after=SimpleNamespace(**{**row,'st_ino':3 if changed else 2})
        path=mock.MagicMock();path.__str__.return_value='/etc/ld.so.cache';path.lstat.return_value=after
        with mock.patch.object(g,'trusted_installed',return_value=path),mock.patch.object(g.os,'open',return_value=42) as opening,mock.patch.object(g.os,'fstat',return_value=before),mock.patch.object(g.os,'dup',return_value=43),mock.patch.object(g.os,'fdopen',return_value=io.BytesIO(b'abc')),mock.patch.object(g.os,'close') as close:
            try:return g.pin_loader_cache()
            finally:
                self.assertEqual(opening.call_args.args[1],g.os.O_RDONLY|g.os.O_NONBLOCK|g.os.O_NOFOLLOW)
                close.assert_called_once_with(42)
    def test_bounded_nofollow_snapshot(self):
        pin,identity=self.snapshot();self.assertEqual(pin['bytes'],3);self.assertEqual(identity[1],2)
    def test_replaced_inode_rejected(self):
        with self.assertRaisesRegex(ValueError,'changed'):self.snapshot(changed=True)
    def test_oversize_rejected_before_read(self):
        with self.assertRaisesRegex(ValueError,'excessive'):self.snapshot(oversized=True)
