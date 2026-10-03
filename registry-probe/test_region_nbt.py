import struct
from pathlib import Path
import tempfile
import unittest
import zlib

from region_nbt import NBTReader, persisted_item, read_chunk


def text(value):
    value = value.encode("utf-8")
    return struct.pack(">H", len(value)) + value


def named(tag, name, value):
    return bytes([tag]) + text(name) + value


def integer(name, value):
    return named(3, name, struct.pack(">i", value))


def fixture(item_id="infinity_registry_probe:test_item", count=7, slot=0):
    stack = named(8, "id", text(item_id)) + integer("count", count) + named(1, "Slot", bytes([slot])) + b"\0"
    entity = (integer("x", 0) + integer("y", 64) + integer("z", 0)
              + named(8, "id", text("minecraft:chest"))
              + named(9, "Items", b"\x0a" + struct.pack(">i", 1) + stack) + b"\0")
    root = named(10, "", named(9, "block_entities", b"\x0a" + struct.pack(">i", 1) + entity) + b"\0")
    compressed = zlib.compress(root)
    chunk = struct.pack(">i", len(compressed) + 1) + b"\x02" + compressed
    assert len(chunk) <= 4096
    return b"\x00\x00\x02\x01" + b"\0" * (8192 - 4) + chunk + b"\0" * (4096 - len(chunk))


class RegionNBTTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.profile = Path(self.temp.name)
        self.region = self.profile / "world/region/r.0.0.mca"
        self.region.parent.mkdir(parents=True)

    def tearDown(self):
        self.temp.cleanup()

    def test_exact_persisted_item_passes(self):
        self.region.write_bytes(fixture())
        self.assertEqual(persisted_item(self.profile), {"id": "infinity_registry_probe:test_item", "count": 7, "Slot": 0})

    def test_wrong_id_fails(self):
        self.region.write_bytes(fixture(item_id="minecraft:air"))
        with self.assertRaises(AssertionError):
            persisted_item(self.profile)

    def test_wrong_count_fails(self):
        self.region.write_bytes(fixture(count=1))
        with self.assertRaises(AssertionError):
            persisted_item(self.profile)

    def test_wrong_slot_fails(self):
        self.region.write_bytes(fixture(slot=1))
        with self.assertRaises(AssertionError):
            persisted_item(self.profile)

    def test_missing_chunk_fails(self):
        self.region.write_bytes(bytes(8192))
        with self.assertRaises(ValueError):
            read_chunk(self.region)

    def test_truncated_chunk_fails(self):
        self.region.write_bytes(fixture()[:8200])
        with self.assertRaises((ValueError, zlib.error)):
            read_chunk(self.region)

    def test_oversized_length_fails(self):
        bad = bytearray(fixture())
        bad[8192:8196] = struct.pack(">i", 1000000)
        self.region.write_bytes(bad)
        with self.assertRaises(ValueError):
            read_chunk(self.region)

    def test_truncated_nbt_fails(self):
        with self.assertRaises(ValueError):
            NBTReader(b"\x00").number("i")


if __name__ == "__main__":
    unittest.main()
