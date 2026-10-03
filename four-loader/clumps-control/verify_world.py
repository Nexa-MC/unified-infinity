#!/usr/bin/env python3
"""Bounded, independent read-only inspection of the actual saved Clumps orb map.

The clumpedMap schema comes from the approved original Clumps 19.0.0.1
MixinExperienceOrb.addAdditionalSaveData/readAdditionalSaveData bytecode. No
runtime companion code is loaded by this verifier.
"""
import gzip
import hashlib
import io
import json
import math
import pathlib
import struct
import sys
import zlib

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT / 'registry-probe'))
from region_nbt import MAX_NBT_BYTES, NBTReader

EXPECTED_MAP = {'1': 1, '3': 1, '7': 2, '17': 1, '37': 1}
EXPECTED_XP = 72
MAX_ENTITY_FILES = 16
MAX_ENTITY_CHUNKS = 256

class StrictNBTReader(NBTReader):
    def payload(self, tag, depth=0):
        if depth > 100:
            raise ValueError('NBT nesting exceeds bounds')
        if tag in (11, 12):
            count = self.number('i')
            width = 4 if tag == 11 else 8
            if not 0 <= count <= MAX_NBT_BYTES // width:
                raise ValueError('Invalid NBT array size')
            raw = self.read(count * width)
            return list(struct.unpack('>' + ('i' if tag == 11 else 'q') * count, raw))
        if tag == 10:
            out = {}
            while (kind := self.number('B')) != 0:
                key = self.string()
                if key in out:
                    raise ValueError('Duplicate NBT compound key')
                out[key] = self.payload(kind, depth + 1)
            return out
        return super().payload(tag, depth)

def decode_nbt(raw):
    if len(raw) > MAX_NBT_BYTES:
        raise ValueError('Oversized NBT')
    reader = StrictNBTReader(raw)
    if reader.number('B') != 10:
        raise ValueError('Expected root compound')
    reader.string()
    out = reader.payload(10)
    if reader.data.read(1):
        raise ValueError('Trailing NBT bytes')
    return out

def read_nbt(path):
    with gzip.open(path, 'rb') as stream:
        raw = stream.read(MAX_NBT_BYTES + 1)
    return decode_nbt(raw)

def read_entity_chunk(path, slot):
    with path.open('rb') as stream:
        stream.seek(slot * 4)
        location = stream.read(4)
        if len(location) != 4:
            raise ValueError('Truncated region header')
        offset, sectors = int.from_bytes(location[:3], 'big'), location[3]
        if offset < 2 or not sectors:
            raise ValueError('Missing entity chunk')
        stream.seek(offset * 4096)
        length_raw = stream.read(4)
        if len(length_raw) != 4:
            raise ValueError('Truncated region length')
        length = int.from_bytes(length_raw, 'big')
        if not 1 <= length <= sectors * 4096 - 4:
            raise ValueError('Invalid region payload length')
        kind_raw = stream.read(1)
        if len(kind_raw) != 1:
            raise ValueError('Missing compression type')
        packed = stream.read(length - 1)
        if len(packed) != length - 1:
            raise ValueError('Truncated region payload')
    if kind_raw[0] == 2:
        inflater = zlib.decompressobj()
        raw = inflater.decompress(packed, MAX_NBT_BYTES + 1)
        if inflater.unconsumed_tail or inflater.unused_data or not inflater.eof:
            raise ValueError('Oversized, trailing or incomplete compressed NBT')
    elif kind_raw[0] == 1:
        with gzip.GzipFile(fileobj=io.BytesIO(packed)) as stream:
            raw = stream.read(MAX_NBT_BYTES + 1)
    elif kind_raw[0] == 3:
        raw = packed
    else:
        raise ValueError('Unsupported region compression type')
    return decode_nbt(raw)

def region_slots(path):
    with path.open('rb') as stream:
        header = stream.read(4096)
    # Minecraft opens untouched region files lazily: exactly zero bytes is an
    # empty placeholder. A nonzero short header remains a malformed file.
    if not header:
        return []
    if len(header) != 4096:
        raise ValueError('Truncated region header')
    return [slot for slot in range(1024) if header[slot * 4:slot * 4 + 4] != b'\0\0\0\0']

def check_orbs(orbs):
    assert len(orbs) == 1, f'Expected one saved XP orb; found {len(orbs)}'
    orb = orbs[0]
    actual = orb.get('clumpedMap')
    assert isinstance(actual, dict) and actual == EXPECTED_MAP, f'Saved clumpedMap differs: {actual}'
    assert all(type(value) is int and value > 0 for value in actual.values()), 'Non-positive or non-int multiplicity'
    total = sum(int(value) * count for value, count in actual.items())
    assert total == EXPECTED_XP, f'Weighted XP changed: {total}'
    pos = orb.get('Pos')
    assert isinstance(pos, list) and len(pos) == 3 and all(math.isfinite(x) for x in pos), 'Invalid orb position'
    assert all(abs(x - expected) <= 2 for x, expected in zip(pos, (8, 100, 8))), f'Orb left fixture arena: {pos}'
    assert 'unified_clumps_probe' in orb.get('Tags', []), 'Missing companion identity tag'
    assert orb.get('NoGravity') == 1, 'Orb gravity flag changed'
    uuid = orb.get('UUID')
    assert isinstance(uuid, list) and len(uuid) == 4 and all(type(n) is int for n in uuid), 'Missing orb UUID'
    return {'count': len(orbs), 'clumped_map': actual, 'weighted_xp': total,
            'original_orb_multiplicity': sum(actual.values()), 'uuid': uuid,
            'position': pos, 'vanilla_value': orb.get('Value'),
            'vanilla_count': orb.get('Count'), 'age': orb.get('Age')}

def verify(profile, expected_marker=None):
    world = pathlib.Path(profile) / 'world'
    level = read_nbt(world / 'level.dat')
    assert level['Data']['Version']['Id'] == 3955, 'Unexpected MC world DataVersion'
    saved_path = world / 'data/unified_clumps_probe.dat'
    saved = read_nbt(saved_path)
    marker = saved.get('data', {}).get('marker')
    if expected_marker is not None:
        assert marker == expected_marker, f'SavedData marker changed: {marker}'
    else:
        assert isinstance(marker, str) and marker, 'Missing companion saved marker'
    files = sorted((world / 'entities').glob('r.*.*.mca'))
    assert 0 < len(files) <= MAX_ENTITY_FILES, 'Missing/excessive saved entity regions'
    orbs, chunk_count = [], 0
    empty_files = []
    for path in files:
        if path.stat().st_size == 0:
            empty_files.append(str(path.relative_to(world)))
        for slot in region_slots(path):
            chunk_count += 1
            assert chunk_count <= MAX_ENTITY_CHUNKS, 'Excessive saved entity chunks'
            root = read_entity_chunk(path, slot)
            assert root.get('DataVersion') == 3955, 'Unexpected entity DataVersion'
            for entity in root.get('Entities', []):
                if entity.get('id') == 'minecraft:experience_orb':
                    orbs.append(entity)
    result = check_orbs(orbs)
    assert saved['data'].get('survivor') == result['uuid'], 'SavedData UUID differs from persisted entity UUID'
    return {'passed': True, 'orb': result, 'saved_data_marker': marker,
            'saved_data': saved.get('data'), 'entity_chunks_inspected': chunk_count,
            'empty_entity_region_placeholders': empty_files,
            'world_version': level['Data']['Version'],
            'files': {str(path.relative_to(world)): hashlib.sha256(path.read_bytes()).hexdigest()
                      for path in [world / 'level.dat', saved_path, *files]},
            'schema_evidence': 'Approved Clumps MixinExperienceOrb bytecode: clumpedMap compound, XP string keys, int multiplicities',
            'scope': 'One naturally merged six-orb clump persisted in a local world; no pickup, mending or player claim'}

if __name__ == '__main__':
    print(json.dumps(verify(sys.argv[1], sys.argv[2] if len(sys.argv) > 2 else None), indent=2))
