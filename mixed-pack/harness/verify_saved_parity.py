#!/usr/bin/env python3
"""Read-only canonical block-state/biome comparison of the nine generated targets."""
import argparse,hashlib,importlib.util,json,pathlib
HERE=pathlib.Path(__file__).resolve();SPEC=importlib.util.spec_from_file_location('mixed',HERE.with_name('run_mixed_pack.py'));m=importlib.util.module_from_spec(SPEC);SPEC.loader.exec_module(m)
def expand(container,count,minimum):
 palette=container['palette']
 if len(palette)==1:return [palette[0]]*count
 bits=max(minimum,(len(palette)-1).bit_length());per=64//bits;words=container['data']
 return [palette[((words[i//per]&((1<<64)-1))>>((i%per)*bits))&((1<<bits)-1)] for i in range(count)]
def canonical(chunk):
 return [{'y':s['Y'],'blocks':expand(s['block_states'],4096,4),'biomes':expand(s['biomes'],64,1)} for s in sorted(chunk['sections'],key=lambda x:x['Y']) if 'block_states' in s]
def digest(value):return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':')).encode()).hexdigest()
def execute(run_id):
 out={'run_id':run_id,'scope':'Read-only saved full target chunks: canonical block-state and biome arrays only; excludes ticking/entity/light/time metadata. Not a performance or broad-worldgen guarantee.','chunks':[]}
 for cx,cz in m.TARGET_CHUNKS:
  a=canonical(m.read_chunk(m.profile_path(run_id,'neoforge')/'world',cx,cz));b=canonical(m.read_chunk(m.profile_path(run_id,'unified')/'world',cx,cz))
  out['chunks'].append({'x':cx,'z':cz,'native_neoforge_sha256':digest(a),'unified_sha256':digest(b),'equal':a==b})
 out['passed']=all(c['equal'] for c in out['chunks']);m.emit_json(m.BASE/'logs'/f'{run_id}-saved-worldgen-parity.json',out)
 print(json.dumps(out,indent=2));return 0 if out['passed'] else 1
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--run-id',required=True);args=p.parse_args();raise SystemExit(execute(args.run_id))
