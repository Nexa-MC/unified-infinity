#!/usr/bin/env python3
"""Independent bounded, read-only NBT verification for native OP Tab acceptance."""
import argparse, gzip, hashlib, json, pathlib, sys
ROOT=pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'registry-probe'))
from region_nbt import MAX_NBT_BYTES, NBTReader

def verify(world):
    p=world/'level.dat'
    with gzip.open(p,'rb') as f: raw=f.read(MAX_NBT_BYTES+1)
    if len(raw)>MAX_NBT_BYTES:raise ValueError('NBT exceeds bounded decoder limit')
    reader=NBTReader(raw)
    if reader.number('B')!=10:raise ValueError('Expected NBT compound')
    reader.string();level=reader.payload(10)['Data']
    assert level['LevelName']=='quilt-optab-native',level['LevelName']
    assert level['DataVersion']==3955
    assert level['GameType']==1
    inv=level['Player']['Inventory']
    swords=[i for i in inv if i.get('id')=='minecraft:netherite_sword']
    assert len(swords)==1,swords
    sword=swords[0];components=sword['components']
    assert 'OP Sword' in components['minecraft:custom_name']
    enchants=components['minecraft:enchantments']['levels']
    assert enchants=={f'minecraft:{k}':127 for k in ['sharpness','fire_aspect','mending','unbreaking']},enchants
    assert any(i.get('id')=='minecraft:barrier' for i in inv),inv
    return {'result':'PASS','world':str(world),'worldName':level['LevelName'],'dataVersion':level['DataVersion'],'creative':True,'seed':level['WorldGenSettings']['seed'],'gameTime':level['Time'],'inventory':inv,'levelDatSha256':hashlib.sha256(p.read_bytes()).hexdigest(),'evidence':'Independent bounded decoding of actual saved NBT; OP Sword name and four level-127 enchantments plus barrier persist'}

def main():
    p=argparse.ArgumentParser();p.add_argument('--world',type=pathlib.Path,required=True);p.add_argument('--output',type=pathlib.Path,required=True);a=p.parse_args()
    result=verify(a.world);a.output.write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))

if __name__=='__main__':main()
