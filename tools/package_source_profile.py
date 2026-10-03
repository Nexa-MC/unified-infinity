#!/usr/bin/env python3
"""Package the immutable full-source accepted profile, excluding game and mod corpus."""
import hashlib,json,pathlib,zipfile
root=pathlib.Path(__file__).resolve().parent.parent
pins={
'source-workspace/artifacts/unified-infinity-source-connector-adapter-fart-1.21.1.jar':'c8921d6a6d3ff3bb47e12913fb867344d1fab7c233e5bce7a9f35a53fef5e65e',
'runtime-bundle/build/libs/unified-infinity-0.1.0-dev.jar':'3802215d427501040a432a54e1304e50bbd6758a4610efeea46b0a479641b61e',
'preload-ui/build/libs/unified-infinity-preload-0.1.0-dev.jar':'7b549d3725cbf63a529cf543aafa9ce1f9d0d65d3fe3cac93411f429e0955d99'}
entries={};artifacts=[]
for name,expected in pins.items():
 p=root/name;b=p.read_bytes();actual=hashlib.sha256(b).hexdigest()
 if actual!=expected:raise SystemExit('Artifact changed: '+name)
 dest='mods/'+p.name;entries[dest]=b;artifacts.append({'path':dest,'sha256':actual,'bytes':len(b)})
for name in ['THIRD_PARTY_NOTICES.md','docs/M5-FULL-SOURCE-ACCEPTANCE.md','docs/full-source-build/README.md','source-workspace/artifacts/unified-infinity-complete-connector-fart-adapter-sources.zip','source-workspace/upstream/Adapter-LICENSE.txt','source-workspace/upstream/FART-LICENSE.txt','integrated-loader/LICENSE','runtime-bundle/src/main/resources/META-INF/licenses/FFAPI-Apache-2.0.txt']:
 entries['sources-and-notices/'+name]=(root/name).read_bytes()
entries['profile-lock.json']=json.dumps({'product':'Unified ∞ Infinity','minecraft':'1.21.1','javaMinimum':21,'neoforge':'21.1.219','status':'private R&D alpha','artifacts':artifacts},indent=2).encode()
entries['README.txt']=('Unified Infinity full-source accepted research profile.\nRequires separately installed official Minecraft 1.21.1 / NeoForge 21.1.219 and Java 21.\nOnly one Connector core may be installed. FFAPI is bundled internally; do not add another Fabric API aggregate.\nSelect earlyWindowProvider="unifiedinfinity" in config/fml.toml for the custom client window.\nSet an absolute -Dunified.infinity.progressFile path for fresh startup progress.\nNo Minecraft game binaries, assets, account data, test worlds, or Lithium JAR are included.\nThis is not a standalone installer or a universal compatibility release.\nComplete modified core sources and notices accompany these binaries. Managed-host/preload sources are in the matching M5 source archive.\n').encode()
out=root/'checkpoints/unified-infinity-m5-runtime.zip'
with zipfile.ZipFile(out,'w',zipfile.ZIP_DEFLATED) as z:
 for n,b in sorted(entries.items()):z.writestr(n,b)
assert out.stat().st_size<15*1024*1024
print(json.dumps({'path':str(out),'bytes':out.stat().st_size,'sha256':hashlib.sha256(out.read_bytes()).hexdigest()}))
