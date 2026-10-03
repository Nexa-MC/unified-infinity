#!/usr/bin/env python3
"""Assemble the tested source-derived profile, never installing or publishing it."""
import hashlib,json,pathlib,zipfile
root=pathlib.Path(__file__).resolve().parent.parent
baseline=json.loads((root/'baseline-lock.json').read_text())
paths=[('loader-core','integrated-loader/build/libs/unified-infinity-connector-2.0.0-beta.17+1.21.1-derived.jar'),('api-implementation','runtime-bundle/build/libs/unified-infinity-0.1.0-dev.jar'),('client-preload','preload-ui/build/libs/unified-infinity-preload-0.1.0-dev.jar')]
artifacts=[];entries={};service_counts={}
for role,name in paths:
 p=root/name;data=p.read_bytes();sha=hashlib.sha256(data).hexdigest();destination='mods/'+p.name
 artifacts.append({'role':role,'path':destination,'sha256':sha,'bytes':len(data)})
 entries[destination]=data
 with zipfile.ZipFile(p) as z:
  for n in z.namelist():
   if n.startswith('META-INF/services/'):
    for line in z.read(n).decode().splitlines():
     provider=line.split('#',1)[0].strip()
     if provider:service_counts[(n,provider)]=service_counts.get((n,provider),0)+1
if any(n!=1 for n in service_counts.values()):raise SystemExit('Duplicate service-provider ownership in distribution')
core=next(x for x in artifacts if x['role']=='loader-core')
provenance=json.loads((root/'integrated-loader/build/provenance.json').read_text())
# The build's immutable output record must agree; never silently package stale binaries.
verification=json.loads((root/'integrated-loader/build/verification.json').read_text())
if core['sha256']!=verification['artifact_sha256']:raise SystemExit('Core build verification does not match current artifact')
lock={'schemaVersion':1,'product':'Unified ∞ Infinity','status':'private R&D source-integrated alpha; not a public release','minecraft':baseline['minecraft'],'minimumJava':21,'host':{'loader':'NeoForge','version':baseline['pins']['neoforge']},'artifacts':artifacts,'sourceForkIdentity':provenance,'topLevelServiceProviders':[{'service':s,'provider':p,'count':n} for (s,p),n in sorted(service_counts.items())],'evidence':{'dedicatedServer':'project-owned bytecode/Mixin probes verified; registry test in progress; consult checkpoint logs','client':'native provider verified; full game validation ongoing'},'installationPolicy':'Do not install both official Connector and this derived core. No separate FFAPI/Fabric API aggregate is needed. Existing third-party mod compatibility is not established.'}
entries['profile-lock.json']=(json.dumps(lock,indent=2)+'\n').encode()
entries['README.txt']=b'Unified Infinity private R&D profile for Minecraft1.21.1 / NeoForge21.1.219 / Java21.\nThis is not a standalone Minecraft launcher or universal compatibility release.\nUse one source-derived core only; do not combine it with original Connector.\nFFAPI is internally bundled in the API implementation artifact.\nThe preload provider is selected by config/fml.toml earlyWindowProvider="unifiedinfinity".\nUse a fresh absolute -Dunified.infinity.progressFile path for each launch.\nGame binaries/assets and EULA acceptance are not included.\nSource and detailed evidence accompany this runtime in the outer checkpoint.\n'
entries['THIRD_PARTY_NOTICES.md']=(root/'THIRD_PARTY_NOTICES.md').read_bytes()
for base in ['integrated-loader/LICENSE','integrated-loader/PATCHES.md','integrated-loader/upstream/FART-LICENSE.txt','integrated-loader/upstream/ForgeAutoRenamingTool-1.0.14-sources.jar','runtime-bundle/src/main/resources/META-INF/licenses/FFAPI-Apache-2.0.txt']:
 entries['sources-and-licenses/'+base]=(root/base).read_bytes()
for p in (root/'integrated-loader/src').rglob('*.java'):
 entries['sources-and-licenses/'+str(p.relative_to(root))]=p.read_bytes()
entries['sources-and-licenses/integrated-loader/build.py']=(root/'integrated-loader/build.py').read_bytes()
entries['sources-and-licenses/integrated-loader/upstream-source.patch']=(root/'integrated-loader/upstream-source.patch').read_bytes()
out=root/'artifacts/unified-infinity-source-integrated-alpha.zip';out.parent.mkdir(exist_ok=True)
with zipfile.ZipFile(out,'w',zipfile.ZIP_DEFLATED) as z:
 for name,data in sorted(entries.items()):
  info=zipfile.ZipInfo(name,(2026,10,3,0,0,0));info.compress_type=zipfile.ZIP_DEFLATED;z.writestr(info,data)
(root/'logs/distribution-lock.json').write_text(json.dumps(lock,indent=2)+'\n')
print(json.dumps({'path':str(out),'sha256':hashlib.sha256(out.read_bytes()).hexdigest(),'bytes':out.stat().st_size,'roles':[a['role'] for a in artifacts],'top_level_service_provider_uniqueness_verified':True}))
