#!/usr/bin/env python3
"""Read-only independent verification of native/custom-item region data and SavedData."""
import gzip
import json
import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT / 'registry-probe'))
from region_nbt import MAX_NBT_BYTES, NBTReader, read_chunk

def verify(profile):
    profile = pathlib.Path(profile)
    chunk = read_chunk(profile / 'world/region/r.0.0.mca')
    chests = [entity for entity in chunk.get('block_entities', [])
              if (entity.get('x'), entity.get('y'), entity.get('z')) == (0, 100, 0)]
    assert len(chests) == 1 and chests[0].get('id') == 'minecraft:chest', 'Missing unique persisted chest'
    items = chests[0].get('Items', [])
    assert len(items) == 1, 'Expected exactly one persisted item stack'
    actual = {key: items[0].get(key) for key in ('id', 'count', 'Slot')}
    expected = {'id': 'unified_forge_probe:anchor', 'count': 7, 'Slot': 0}
    assert actual == expected, f'Persisted stack mismatch: {actual}'
    with gzip.open(profile / 'world/data/unified_forge_probe.dat', 'rb') as f:
        payload = f.read(MAX_NBT_BYTES + 1)
    assert len(payload) <= MAX_NBT_BYTES, 'Oversized SavedData'
    nbt = NBTReader(payload)
    assert nbt.number('B') == 10, 'Expected root compound'
    nbt.string()
    data = nbt.payload(10)
    marker = data['data']['marker']
    assert marker == 'forge_52_1_0_probe_v1', f'SavedData marker mismatch: {marker}'
    return {'passed': True, 'chest_position': [0, 100, 0], 'item': actual, 'saved_data_marker': marker}

if __name__ == '__main__':
    print(json.dumps(verify(sys.argv[1]), indent=2))
