#!/usr/bin/env python3
import hashlib,json,pathlib,zipfile,sys
root=pathlib.Path(__file__).resolve().parent.parent
names=['stress-upstream','stress-sequential','stress-bounded']
def inventory(name):
 out={}
 for p in sorted((root/'run'/name/'.cache/connector').glob('*.jar')):
  with zipfile.ZipFile(p) as z:
   out[p.name]={n:hashlib.sha256(z.read(n)).hexdigest() for n in sorted(z.namelist()) if not n.endswith('/')}
 return out
sets={name:inventory(name) for name in names};ref=sets[names[0]];comparisons=[]
for name in names[1:]:
 diffs=[]
 for jar in sorted(ref.keys()|sets[name].keys()):
  a=ref.get(jar,{});b=sets[name].get(jar,{})
  for entry in sorted(a.keys()|b.keys()):
   if a.get(entry)!=b.get(entry):diffs.append({'jar':jar,'entry':entry,'baseline':a.get(entry),'candidate':b.get(entry)})
 comparisons.append({'candidate':name,'archive_count':len(sets[name]),'entry_count':sum(len(v) for v in sets[name].values()),'all_entry_payloads_equal':not diffs,'differences':diffs})
r={'baseline':names[0],'baseline_archives':len(ref),'comparisons':comparisons,'scope':'all transformed JAR entry payloads, ignoring ZIP timestamps/compression/container bytes'}
(root/'logs/transform-differential.json').write_text(json.dumps(r,indent=2)+'\n');print(json.dumps(r,indent=2));raise SystemExit(0 if all(x['all_entry_payloads_equal'] for x in comparisons) else 1)
