import io
import struct
import unittest
from unittest.mock import patch
import verify_world

def nbt_string(value):
    payload = value.encode('utf-8')
    return struct.pack('>H', len(payload)) + payload

def saved_data(marker):
    return b'\x0a\x00\x00\x0a' + nbt_string('data') + b'\x08' + nbt_string('marker') + nbt_string(marker) + b'\x00\x00'

def chunk(item='unified_forge_probe:anchor', count=7, slot=0, y=100):
    return {'block_entities': [{'id': 'minecraft:chest', 'x': 0, 'y': y, 'z': 0,
                              'Items': [{'id': item, 'count': count, 'Slot': slot}]}]}

class WorldVerificationTests(unittest.TestCase):
    def check(self, payload, marker='forge_52_1_0_probe_v1'):
        with patch.object(verify_world, 'read_chunk', return_value=payload), \
             patch.object(verify_world.gzip, 'open', return_value=io.BytesIO(saved_data(marker))):
            return verify_world.verify('/test-profile')

    def test_expected_world(self):
        self.assertTrue(self.check(chunk())['passed'])

    def test_wrong_custom_item_rejected(self):
        with self.assertRaises(AssertionError):
            self.check(chunk(item='minecraft:air'))

    def test_wrong_count_rejected(self):
        with self.assertRaises(AssertionError):
            self.check(chunk(count=1))

    def test_wrong_slot_rejected(self):
        with self.assertRaises(AssertionError):
            self.check(chunk(slot=1))

    def test_wrong_position_rejected(self):
        with self.assertRaises(AssertionError):
            self.check(chunk(y=64))

    def test_missing_chest_rejected(self):
        with self.assertRaises(AssertionError):
            self.check({'block_entities': []})

    def test_wrong_saved_data_rejected(self):
        with self.assertRaises(AssertionError):
            self.check(chunk(), marker='')

if __name__ == '__main__':
    unittest.main()
