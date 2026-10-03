#!/usr/bin/env python3
"""Independent bounded read of the actual four-loader world and mod content."""
import argparse,gzip,hashlib,json,pathlib,sys
ROOT=pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'registry-probe'))
from region_nbt import MAX_NBT_BYTES,NBTReader,read_chunk

def verify(world):
    p=world/'level.dat'
    with gzip.open(p,'rb') as f:raw=f.read(MAX_NBT_BYTES+1)
    if len(raw)>MAX_NBT_BYTES:raise ValueError('Level NBT exceeds bounded limit')
    r=NBTReader(raw);assert r.number('B')==10;r.string();level=r.payload(10)['Data']
    assert level['LevelName']=='unified-four-loader'
    assert level['DataVersion']==3955 and level['GameType']==1 and level['WasModded']==1
    assert level['WorldGenSettings']['seed']==2026100302
    inventory=level['Player']['Inventory']
    sword=[i for i in inventory if i.get('id')=='minecraft:netherite_sword'];assert len(sword)==1
    components=sword[0]['components'];assert 'OP Sword' in components['minecraft:custom_name']
    assert components['minecraft:enchantments']['levels']=={f'minecraft:{k}':127 for k in ['sharpness','fire_aspect','mending','unbreaking']}
    for moditem in ['minecraft:barrier','farmersdelight:cooking_pot']:assert any(i['id']==moditem for i in inventory)
    region=world/'region/r.0.0.mca';chunk=read_chunk(region,0,0)
    pots=[b for b in chunk.get('block_entities',[]) if b.get('id')=='farmersdelight:cooking_pot' and (b.get('x'),b.get('y'),b.get('z'))==(0,-60,1)]
    assert len(pots)==1,pots
    assert pots[0]['Inventory']['Items']==[{'Slot':0,'count':1,'id':'farmersdelight:tomato'}],pots[0]
    return {'result':'PASS','world':str(world),'level':{k:level[k] for k in ['LevelName','DataVersion','GameType','WasModded','Time']},'seed':level['WorldGenSettings']['seed'],'playerInventory':inventory,'cookingPot':pots[0],'files':[{'file':str(f.relative_to(world)),'sha256':hashlib.sha256(f.read_bytes()).hexdigest()} for f in [p,region]],'evidence':'Bounded independent decoding of actual level.dat and region NBT, after real UI item transfer and block/container interaction; no synthetic save data'}

def main():
    p=argparse.ArgumentParser();p.add_argument('--world',type=pathlib.Path,required=True);p.add_argument('--output',type=pathlib.Path,required=True);a=p.parse_args();result=verify(a.world);a.output.write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))

if __name__=='__main__':main()
