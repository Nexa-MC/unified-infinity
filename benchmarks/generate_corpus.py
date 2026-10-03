#!/usr/bin/env python3
"""Generate deterministic project-owned bytecode corpus; not third-party coverage."""
import argparse,pathlib,json,subprocess,zipfile,hashlib
root=pathlib.Path(__file__).resolve().parent.parent
p=argparse.ArgumentParser();p.add_argument('--jars',type=int,default=16);p.add_argument('--classes',type=int,default=128);a=p.parse_args()
if not(1<=a.jars<=64 and 1<=a.classes<=512):raise SystemExit('bounded corpus requires 1..64 JARs and1..512classes/JAR')
base=root/'benchmarks/build';src=base/'src';classes=base/'classes';out=base/'mods'
for d in [src,classes,out]:d.mkdir(parents=True,exist_ok=True)
sources=[]
for i in range(a.jars):
 package=f'dev.infinity.corpus.m{i:02d}';folder=src/pathlib.Path(*package.split('.'));folder.mkdir(parents=True,exist_ok=True)
 for j in range(a.classes):
  file=folder/f'C{j}.java';file.write_text(f'package {package}; public final class C{j} {{ public static int compute(int x) {{ return Integer.rotateLeft(x ^ {j}, {j%31+1}); }} }}\n');sources.append(str(file))
argsfile=base/'javac-args.txt';argsfile.write_text('\n'.join(sources)+'\n')
subprocess.run([str(root/'.toolchains/jdk-21.0.12.1+1/bin/javac'),'--release','21','-d',str(classes),'@'+str(argsfile)],check=True)
records=[]
for i in range(a.jars):
 jar=out/f'infinity-corpus-{i:02d}.jar';modid=f'infinity_corpus_{i:02d}';metadata={'schemaVersion':1,'id':modid,'version':'0.1.0','name':'Project-owned synthetic transform corpus','environment':'*','license':'MIT','depends':{'minecraft':'1.21.1','fabricloader':'>=0.16.0','java':'>=21'}}
 entries={'fabric.mod.json':json.dumps(metadata,sort_keys=True).encode(),'LICENSE':b'Project-owned R&D synthetic fixture. SPDX-License-Identifier: MIT\n'}
 for file in sorted((classes/f'dev/infinity/corpus/m{i:02d}').glob('*.class')):entries[str(file.relative_to(classes))]=file.read_bytes()
 with zipfile.ZipFile(jar,'w',zipfile.ZIP_DEFLATED) as z:
  for name,data in sorted(entries.items()):
   info=zipfile.ZipInfo(name,(1980,1,1,0,0,0));info.compress_type=zipfile.ZIP_DEFLATED;z.writestr(info,data)
 records.append({'name':jar.name,'sha256':hashlib.sha256(jar.read_bytes()).hexdigest(),'size':jar.stat().st_size,'classes':a.classes})
(root/'benchmarks/corpus-manifest.json').write_text(json.dumps({'kind':'project-owned synthetic non-gameplay transform corpus','jars':records,'warning':'not representative third-party mod behavior; no entrypoint or Mixin in synthetic jars'},indent=2)+'\n')
print(json.dumps({'jar_count':len(records),'class_count':a.jars*a.classes,'bytes':sum(x['size'] for x in records)}))
