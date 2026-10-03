"""Small read-only NBT decoder for verifying one persisted Minecraft chunk.

Only reads local region data; never imports executable content from a save.
Bounds-checked parsing and a decompression size cap prevent unbounded reads.
"""
import gzip
import io
from pathlib import Path
import struct
import zlib

MAX_NBT_BYTES = 16 * 1024 * 1024


class NBTReader:
    def __init__(self, payload):
        self.data = io.BytesIO(payload)

    def read(self, length):
        if length < 0 or length > MAX_NBT_BYTES:
            raise ValueError("Invalid NBT length")
        value = self.data.read(length)
        if len(value) != length:
            raise ValueError("Truncated NBT")
        return value

    def number(self, fmt):
        return struct.unpack(">" + fmt, self.read(struct.calcsize(fmt)))[0]

    def string(self):
        return self.read(self.number("H")).decode("utf-8")

    def payload(self, tag, depth=0):
        if depth > 100:
            raise ValueError("NBT nesting exceeds bounds")
        if tag in (1, 2, 3, 4, 5, 6):
            return self.number({1: "b", 2: "h", 3: "i", 4: "q", 5: "f", 6: "d"}[tag])
        if tag == 7:
            return self.read(self.number("i"))
        if tag == 8:
            return self.string()
        if tag == 9:
            item_tag, length = self.number("B"), self.number("i")
            if not 0 <= length <= MAX_NBT_BYTES:
                raise ValueError("Invalid list length")
            return [self.payload(item_tag, depth + 1) for _ in range(length)]
        if tag == 10:
            result = {}
            while (item_tag := self.number("B")) != 0:
                name = self.string()
                result[name] = self.payload(item_tag, depth + 1)
            return result
        if tag in (11, 12):
            length = self.number("i")
            size = 4 if tag == 11 else 8
            self.read(length * size)
            return {"array_length": length}
        raise ValueError(f"Unsupported NBT tag {tag}")


def read_chunk(region, chunk_x=0, chunk_z=0):
    with Path(region).open("rb") as f:
        index = (chunk_x % 32) + (chunk_z % 32) * 32
        f.seek(index * 4)
        location = f.read(4)
        if len(location) != 4:
            raise ValueError("Truncated region header")
        offset, sectors = int.from_bytes(location[:3], "big"), location[3]
        if offset < 2 or not sectors:
            raise ValueError("Expected chunk is absent")
        f.seek(offset * 4096)
        length = int.from_bytes(f.read(4), "big")
        if not 1 <= length <= sectors * 4096 - 4:
            raise ValueError("Invalid region chunk length")
        compression = f.read(1)[0]
        compressed = f.read(length - 1)
    if compression == 2:
        inflater = zlib.decompressobj()
        payload = inflater.decompress(compressed, MAX_NBT_BYTES + 1)
        if inflater.unconsumed_tail or not inflater.eof:
            raise ValueError("Oversized or incomplete compressed chunk")
    elif compression == 1:
        with gzip.GzipFile(fileobj=io.BytesIO(compressed)) as gz:
            payload = gz.read(MAX_NBT_BYTES + 1)
    elif compression == 3:
        payload = compressed
    else:
        raise ValueError(f"Unsupported compression {compression}")
    if len(payload) > MAX_NBT_BYTES:
        raise ValueError("Chunk exceeds size cap")
    reader = NBTReader(payload)
    if reader.number("B") != 10:
        raise ValueError("Expected root compound")
    reader.string()
    return reader.payload(10)


def persisted_item(profile):
    chunk = read_chunk(Path(profile) / "world/region/r.0.0.mca")
    matches = [entity for entity in chunk.get("block_entities", [])
               if (entity.get("x"), entity.get("y"), entity.get("z")) == (0, 64, 0)]
    if len(matches) != 1 or matches[0].get("id") != "minecraft:chest":
        raise AssertionError("Expected exactly one persisted chest at 0 64 0")
    items = matches[0].get("Items", [])
    if len(items) != 1:
        raise AssertionError("Expected exactly one persisted stack")
    actual = {key: items[0].get(key) for key in ("id", "count", "Slot")}
    expected = {"id": "infinity_registry_probe:test_item", "count": 7, "Slot": 0}
    if actual != expected:
        raise AssertionError(f"Persisted stack mismatch: {actual!r}")
    return actual
