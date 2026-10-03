#!/usr/bin/env python3
import collections,hashlib,io,json,pathlib,zipfile
base=pathlib.Path(__file__).resolve().parent;repo=base.parent;t=base/'connector-combined';artifact=next((t/'build/libs').glob('*-full.jar'));control=next((base/'connector/build/libs').glob('*-full.jar'));sha=lambda b:hashlib.sha256(b).hexdigest()
with zipfile.ZipFile(artifact) as z,zipfile.ZipFile(control) as before:
 names=z.namelist();assert len(names)==len(set(names));classes=set(n for n in names if n.endswith('.class'));identity=json.loads(z.read('META-INF/unified-infinity/build-identity.json'))
 source_manifest={i['path']:i['sha256'] for i in identity['sources']}
 for n in ['InjectMixin.java','RedirectMixin.java','RemoveParameterTransformer.java']:
  source=next((t/'components/infinity-adapter/src/main/java').rglob(n));assert source_manifest[source.relative_to(t).as_posix()]==sha(source.read_bytes())
 proof={}
 for component in ['infinity-core','infinity-adapter','infinity-fart']:
  folder=t/f'components/{component}/build/classes/java/main';outputs=list(folder.rglob('*.class'))
  for f in outputs:
   n=f.relative_to(folder).as_posix();dest=('reloc/'+n) if component=='infinity-fart' else n;assert dest in classes,dest
   if component!='infinity-fart':assert z.read(dest)==f.read_bytes(),dest
  proof[component]={'compiled_classes':len(outputs),'all_packaged':True,'java_sources':len(list((t/f'components/{component}/src/main/java').rglob('*.java')))}
 assert not any(n.startswith('net/minecraftforge/fart/') for n in classes)
 services=[n for n in before.namelist() if n.startswith('META-INF/services/') and not n.endswith('/')]
 for n in services:assert z.read(n)==before.read(n),n
 assert set(services)=={n for n in names if n.startswith('META-INF/services/') and not n.endswith('/')}
 for component,version,license_name in [('infinity-fart','1.0.14-infinity','LICENSE-FART-LGPL-2.1.txt'),('infinity-adapter','2.0.43+1.21.1-infinity','LICENSE-Adapter-MIT.txt')]:
  sourcejar=f'META-INF/unified-infinity/sources/{component}-{version}-sources.jar';assert sourcejar in names
  assert f'META-INF/unified-infinity/{license_name}' in names
  with zipfile.ZipFile(io.BytesIO(z.read(sourcejar))) as sj:
   for f in (t/f'components/{component}/src/main/java').rglob('*.java'):assert sj.read(f.relative_to(t/f'components/{component}/src/main/java').as_posix())==f.read_bytes()
 # Reproduce the precise digest recipe, including binary dependencies and compiler.
 digest=hashlib.sha256()
 for item in identity['sources']:
  f=t/item['path'];assert sha(f.read_bytes())==item['sha256'];digest.update(item['path'].encode()+b'\0'+f.read_bytes()+b'\0')
 cache=base/'gradle-cache/caches/modules-2/files-2.1';lookup=collections.defaultdict(list)
 for f in cache.rglob('*.jar'):lookup[f.name].append(f)
 for item in identity['dependencies']:
  candidates=[f for f in lookup[item['filename']] if sha(f.read_bytes())==item['sha256']];assert candidates,item
  f=candidates[0];digest.update(item['filename'].encode()+b'\0'+f.read_bytes()+b'\0')
 digest.update(identity['compiler_runtime'].encode());assert digest.hexdigest()==identity['identity_sha256']
 assert identity['identity_sha256'].encode() in z.read('org/sinytra/connector/infinity/BuildIdentity.class')
 report={'schema':1,'status':'passed','artifact':artifact.relative_to(repo).as_posix(),'artifact_sha256':sha(artifact.read_bytes()),'cache_identity_sha256':identity['identity_sha256'],'source_identity_inputs':len(identity['sources']),'external_dependency_identity_inputs':len(identity['dependencies']),'identity_independently_reproduced':True,'compiled_source_components':proof,'service_descriptors_unchanged_from_source_baseline':services,'embedded_complete_fart_adapter_sources_match':True,'runtime_validation':'not-run-by-source-worker'}
(base/'provenance/combined-artifact-verification.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2))
