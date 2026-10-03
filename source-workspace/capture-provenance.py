#!/usr/bin/env python3
"""Record bytes present in the isolated build cache; not a claim all were resolved or used."""
import datetime,hashlib,json,pathlib,subprocess
base=pathlib.Path(__file__).resolve().parent; repo=base.parent
cache=base/'gradle-cache/caches/modules-2/files-2.1'
entries=[]
for f in sorted(cache.rglob('*')):
 if f.is_file():
  parts=f.relative_to(cache).parts
  if len(parts)!=5: continue
  group,artifact,version,cache_sha1,name=parts
  entries.append({'group':group,'artifact':artifact,'requested_cache_version':version,'file':name,'cache_sha1':cache_sha1,'size':f.stat().st_size,'sha256':hashlib.sha256(f.read_bytes()).hexdigest(),'relative_path':f.relative_to(base).as_posix()})
p={'schema':1,'captured_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'status':'observed-cache-inventory-not-complete-resolution-lock','gradle':'8.11.1','java':'21.0.12.1+1-LTS','entries':entries}
(base/'provenance/cache-artifacts.json').write_text(json.dumps(p,indent=2)+'\n')
print(f'Captured {len(entries)} artifact files')
