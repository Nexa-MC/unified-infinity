import copy
import gzip
import pathlib
import struct
import tempfile
import unittest
import zlib
from prepare import valid_profile
from run import stage_counts, check_lan
from verify_world import EXPECTED_MAP, check_orbs, decode_nbt, read_entity_chunk, read_nbt, region_slots

class ControlTests(unittest.TestCase):
    def orb(self):
        return {'clumpedMap': dict(EXPECTED_MAP), 'UUID': [1, 2, 3, 4],
                'Pos': [8.5, 100.1, 8.5], 'Tags': ['unified_clumps_probe'], 'NoGravity': 1,
                'Value': 72, 'Count': 5}

    def test_zero_byte_region_placeholder_not_partial_header(self):
        with tempfile.TemporaryDirectory() as temp:
            path = pathlib.Path(temp) / 'empty.mca'
            path.write_bytes(b'')
            self.assertEqual(region_slots(path), [])
            for raw in (b'\0', b'\0' * 4095):
                path.write_bytes(raw)
                with self.assertRaises(ValueError):
                    region_slots(path)

    def test_exact_histogram_not_vanilla_count(self):
        self.assertEqual(check_orbs([self.orb()])['weighted_xp'], 72)
        self.assertEqual(check_orbs([self.orb()])['vanilla_count'], 5)
        bad = self.orb()
        bad['clumpedMap']['7'] = 1
        with self.assertRaises(AssertionError):
            check_orbs([bad])

    def test_equal_total_different_histogram_rejected(self):
        bad = self.orb()
        bad['clumpedMap'] = {'72': 1}
        with self.assertRaises(AssertionError):
            check_orbs([bad])

    def test_extra_or_absent_orb_rejected(self):
        for orbs in ([], [self.orb(), self.orb()]):
            with self.assertRaises(AssertionError):
                check_orbs(orbs)

    def test_identity_and_position_rejected(self):
        for key, value in [('UUID', None), ('Pos', [8, float('nan'), 8]),
                           ('Tags', []), ('NoGravity', 0), ('Pos', [100, 100, 100])]:
            bad = self.orb()
            bad[key] = value
            with self.subTest(key=key, value=value), self.assertRaises(AssertionError):
                check_orbs([bad])

    def test_nbt_strict_compound_and_uuid(self):
        raw = b'\x0a\x00\x00\x0b\x00\x04UUID' + struct.pack('>i4i', 4, 1, 2, 3, 4) + b'\x00'
        self.assertEqual(decode_nbt(raw), {'UUID': [1, 2, 3, 4]})
        for bad in (raw + b'x', raw[:-1], b'\x0a\0\0\x03\0\x01a\0\0\0\1\x03\0\x01a\0\0\0\2\0'):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                decode_nbt(bad)

    def test_gzip_saved_data(self):
        with tempfile.TemporaryDirectory() as temp:
            path = pathlib.Path(temp) / 'saved.dat'
            path.write_bytes(gzip.compress(b'\x0a\0\0\x08\0\x06marker\0\x02ok\0'))
            self.assertEqual(read_nbt(path), {'marker': 'ok'})

    def test_entity_region_bounds(self):
        raw = b'\x0a\0\0\x03\0\x0bDataVersion' + struct.pack('>i', 3955) + b'\0'
        packed = zlib.compress(raw)
        header = (2).to_bytes(3, 'big') + b'\1' + b'\0' * (8192 - 4)
        body = struct.pack('>I', len(packed) + 1) + b'\2' + packed
        with tempfile.TemporaryDirectory() as temp:
            path = pathlib.Path(temp) / 'r.0.0.mca'
            path.write_bytes(header + body + b'\0' * (4096 - len(body)))
            self.assertEqual(read_entity_chunk(path, 0), {'DataVersion': 3955})
            with self.assertRaises(ValueError):
                read_entity_chunk(path, 1)
            path.write_bytes(header + struct.pack('>I', 5000) + b'\2' + packed)
            with self.assertRaises(ValueError):
                read_entity_chunk(path, 0)

    def test_stage_prefix_collision_and_duplicates(self):
        counts, found = stage_counts(['UNIFIED_CLUMPS_PROBE PASS stage=merge x=1',
                                     'UNIFIED_CLUMPS_PROBE PASS stage=merged x=1',
                                     'UNIFIED_CLUMPS_PROBE PASS stage=merge x=2'], ['merge'])
        self.assertEqual(counts, {'merge': 2})
        self.assertEqual(found, ['merge', 'merged', 'merge'])

    def test_lan_loader_sections(self):
        with tempfile.TemporaryDirectory() as temp:
            path = pathlib.Path(temp) / 'config.toml'
            path.write_text('[server]\nadvertiseDedicatedServerToLan = false\n')
            check_lan(path, 'native')
            with self.assertRaises(AssertionError):
                check_lan(path, 'unified')
            path.write_text('advertiseDedicatedServerToLan = false\n')
            check_lan(path, 'unified')
            with self.assertRaises(AssertionError):
                check_lan(path, 'native')

    def test_profile_path_guard(self):
        for name in ('forge-native-clumps', 'forge-native-clumps-second', 'unified-forge-clumps-26b', 'clumps-native-v1'):
            self.assertTrue(valid_profile(name))
        for name in ('../forge-native-clumps', 'forge-native-probe', 'unified-forge-clumps/../../accepted'):
            self.assertFalse(valid_profile(name))

if __name__ == '__main__':
    unittest.main()
