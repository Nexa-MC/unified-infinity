import gzip,pathlib,struct,tempfile,unittest
from verify_world import read_nbt
class NBTVerification(unittest.TestCase):
 def test_valid(self):
  with tempfile.TemporaryDirectory() as d:
   p=pathlib.Path(d)/'data.dat';p.write_bytes(gzip.compress(b'\x0a\x00\x00\x08\x00\x06marker\x00\x02ok\x00'))
   self.assertEqual(read_nbt(p),{'marker':'ok'})
 def test_truncation_and_trailing(self):
  for raw in (b'\x0a\x00\x00\x08',b'\x0a\x00\x00\x00junk'):
   with self.subTest(raw=raw),tempfile.TemporaryDirectory() as d:
    p=pathlib.Path(d)/'data.dat';p.write_bytes(gzip.compress(raw))
    with self.assertRaises(ValueError):read_nbt(p)
if __name__=='__main__': unittest.main()
