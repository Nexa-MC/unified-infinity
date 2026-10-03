#!/usr/bin/env python3
"""Independent bounded read-only NBT verification of Quilt control SavedData."""
import gzip, hashlib, json, pathlib, sys
HERE=pathlib.Path(__file__).resolve().parent
ROOT=HERE.parents[1]
sys.path.insert(0,str(ROOT/'registry-probe'))
from region_nbt import MAX_NBT_BYTES, NBTReader
MARKER='native_quilt_qsl_alpha5_v1'
def read_nbt(path):
    with gzip.open(path,'rb') as stream: raw=stream.read(MAX_NBT_BYTES+1)
    if len(raw)>MAX_NBT_BYTES: raise ValueError('Oversized SavedData')
    reader=NBTReader(raw)
    if reader.number('B')!=10: raise ValueError('Expected root compound')
    reader.string()
    result=reader.payload(10)
    if reader.data.read(1): raise ValueError('Trailing NBT bytes')
    return result
def verify(profile):
    world=pathlib.Path(profile)/'world'
    saved=world/'data/unified_quilt_probe.dat'
    data=read_nbt(saved)
    if data.get('data',{}).get('marker')!=MARKER: raise AssertionError('SavedData marker mismatch')
    level=read_nbt(world/'level.dat')
    if level['Data']['Version']['Id']!=3955: raise AssertionError('Unexpected world DataVersion')
    return {'passed':True,'saved_data_marker':data['data']['marker'],'saved_data_version':data.get('DataVersion'),'world_version':level['Data']['Version'],'saved_data_sha256':hashlib.sha256(saved.read_bytes()).hexdigest(),'scope':'SavedData roundtrip only; registry object identity is verified by the original runtime probe'}
if __name__=='__main__': print(json.dumps(verify(sys.argv[1]),indent=2))
