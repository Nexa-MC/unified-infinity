"""Source-only baseline sealing tests; no runtime, graphics or external process."""
from pathlib import Path
import tempfile
import unittest

import seal_pair as seal

HERE = Path(__file__).resolve().parent
BASELINE = (HERE.parent / 'network-pair-assembly-local1/required-text-inputs/work/api1/run/'
            'api1-client-combined-plugin1/config/fabric/indigo-renderer.properties').read_bytes()


class IndigoSealing(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.path = self.root / 'client/config/fabric/indigo-renderer.properties'
        self.path.parent.mkdir(parents=True)
        self.path.write_bytes(BASELINE)
        self.roles = {'client': {'cwd': str(self.root / 'client')}}
        self.inputs = {str(self.path): seal.record(self.path)}
        self.out = self.root / 'pair-seals'
        self.out.mkdir()

    def create(self, target='unified'):
        return seal.seal_indigo_baseline(target, self.roles, self.inputs, self.out)

    def test_baseline_is_exact_independent_pinned_copy(self):
        row = self.create()
        self.assertEqual(row, seal.record(self.out / 'indigo-baseline.properties'))
        self.assertEqual(self.inputs[row['path']], row)
        self.assertEqual(Path(row['path']).read_bytes(), BASELINE)
        self.assertNotEqual(Path(row['path']).stat().st_ino, self.path.stat().st_ino)
        self.assertEqual(self.create(), row)

    def test_native_pair_creates_no_indigo_baseline(self):
        self.assertIsNone(self.create('native-neoforge'))
        self.assertEqual(list(self.out.iterdir()), [])

    def test_changed_original_or_unsealed_original_rejected(self):
        self.inputs = {}
        with self.assertRaisesRegex(ValueError, 'original Indigo role pin'):
            self.create()
        self.inputs = {str(self.path): seal.record(self.path)}
        self.path.write_bytes(BASELINE.replace(b'hybrid', b'flat'))
        with self.assertRaisesRegex(ValueError, 'changed before'):
            self.create()
        self.assertEqual(list(self.out.iterdir()), [])

    def test_existing_changed_or_symlink_baseline_rejected(self):
        path = self.out / 'indigo-baseline.properties'
        path.write_bytes(b'changed')
        with self.assertRaisesRegex(ValueError, 'Existing Indigo baseline changed'):
            self.create()
        path.unlink()
        path.symlink_to(self.path)
        with self.assertRaisesRegex(ValueError, 'Redirected Indigo baseline'):
            self.create()


if __name__ == '__main__':
    unittest.main()
