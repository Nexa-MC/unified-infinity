#!/usr/bin/env python3
"""Verify vendor-installed libraries and stage exact approved probe/QSL inputs."""
import argparse,concurrent.futures,hashlib,json,pathlib,shutil,urllib.request,zipfile
HERE=pathlib.Path(__file__).resolve().parent;ROOT=HERE.parents[1];PROFILE=ROOT/'run/quilt-native-probe';PROV=HERE/'provenance';UP=ROOT/'docs/four-loader/quilt/upstream'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def check(lib):
 g,n,v=lib['name'].split(':');relative=f'{g.replace(".","/")}/{n}/{v}/{n}-{v}.jar';p=PROFILE/'libraries'/relative
 assert p.is_file(),f'Installer incomplete: {p}'
 url=lib['url']+relative; checksum=None;algorithm=None
 for alg in ('sha256','sha1'):
  try:
   with urllib.request.urlopen(url+'.'+alg,timeout=45) as r:checksum=r.read().decode().strip().split()[0]
   algorithm=alg;break
  except urllib.error.HTTPError as e:
   if e.code!=404:raise
 assert checksum and hashlib.new(algorithm,p.read_bytes()).hexdigest()==checksum,f'Official checksum mismatch: {lib["name"]}'
 return {'coordinate':lib['name'],'path':str(p.relative_to(ROOT)),'sha256':sha(p),'url':url,'official_checksum_algorithm':algorithm,'official_checksum':checksum}
def main():
 parser=argparse.ArgumentParser();parser.add_argument('--probe-sha256',required=True);args=parser.parse_args()
 assert len(args.probe_sha256)==64 and all(c in '0123456789abcdef' for c in args.probe_sha256)
 assert (PROFILE/'quilt-server-launch.jar').is_file(),'Vendor installation must finish first'
 libs=json.loads((PROV/'quilt-server-0.30.1.json').read_text())['libraries']
 with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:verified=list(pool.map(check,libs))
 (PROV/'library-checksums.json').write_text(json.dumps(verified,indent=2)+'\n')
 mods=PROFILE/'mods';mods.mkdir(exist_ok=True)
 probe=ROOT/'four-loader/quilt-probe/build/unified-native-quilt-probe-0.1.0.jar';expected=args.probe_sha256
 assert sha(probe)==expected
 shutil.copy2(probe,mods/probe.name)
 for m in json.loads((ROOT/'docs/four-loader/quilt/bundled-initial.json').read_text())['modules']:
  source=ROOT/'docs/four-loader/quilt'/m['file'];assert sha(source)==m['sha256'];shutil.copy2(source,mods/source.name)
 assert len(list(mods.glob('*.jar')))==3
 original_eula=ROOT/'run/fabric-native/eula.txt';assert original_eula.read_text().strip()=='eula=true';shutil.copy2(original_eula,PROFILE/'eula.txt')
 assert not (PROFILE/'world').exists()
 (PROFILE/'server.properties').write_text('''server-ip=127.0.0.1
server-port=25621
online-mode=true
enable-rcon=false
enable-query=false
enable-status=false
enforce-secure-profile=true
white-list=true
enforce-whitelist=true
max-players=1
level-name=world
level-seed=30301
level-type=minecraft:normal
generate-structures=false
difficulty=peaceful
view-distance=2
simulation-distance=2
spawn-protection=0
max-tick-time=120000
motd=Project-owned native Quilt ABI control
''')
 runtime_paths=set(PROFILE.glob('*.jar')) | set((PROFILE/'libraries').rglob('*.jar')) | set((PROFILE/'mods').glob('*.jar')) | set((PROFILE/'versions').rglob('*.jar'))
 runtime_files=[{'path':str(p.relative_to(ROOT)),'sha256':sha(p)} for p in sorted(runtime_paths)]
 meta=json.loads((PROV/'quilt-meta-0.30.1.json').read_text())['loader']
 loader=PROFILE/'libraries/org/quiltmc/quilt-loader/0.30.1/quilt-loader-0.30.1.jar'
 reconciliation={alg:{'artifact_hash':hashlib.new(alg,loader.read_bytes()).hexdigest(),'meta_hash':val,'matches_hash_of_checksum_text':hashlib.new(alg,hashlib.new(alg,loader.read_bytes()).hexdigest().encode()).hexdigest()==val} for alg,val in meta['hashes'].items()}
 assert all(v['matches_hash_of_checksum_text'] for v in reconciliation.values())
 manifest=json.loads((ROOT/'source-workspace/gradle-cache/caches/neoformruntime/artifacts/minecraft_1.21.1_version_manifest.json').read_text())
 assert hashlib.sha1((PROFILE/'server.jar').read_bytes()).hexdigest()==manifest['downloads']['server']['sha1']
 lock={'loader':'0.30.1','minecraft':'1.21.1','qsl':'10.0.0-alpha.5+1.21.1','probe_sha256':expected,'mods':sorted(p.name for p in mods.glob('*.jar')),'java_sha256':sha(ROOT/'.toolchains/jdk-21.0.12.1+1/bin/java'),'runtime_files':runtime_files,'library_official_checksums':verified,'minecraft_official_download':manifest['downloads']['server'],'loader_meta_checksum_defect':reconciliation,'licenses':{'Quilt Loader':'Apache-2.0, official repository and bundled sources','QSL Base and Lifecycle':'Apache-2.0, original module quilt.mod.json and sources','probe':'Project-owned MIT fixture','Minecraft':'Mojang proprietary; preapproved local server EULA; not redistributed'},'installer_sha256':sha(PROV/'quilt-installer-0.15.1.jar'),'install_method':'Official Quilt installer CLI, 1.21.1 + 0.30.1, original generated launch JAR; no hand-assembled launcher','network':'Loopback only, online-mode=true, query/RCON/status disabled, no LAN advertiser, no accounts'}
 (HERE/'native-environment-lock.json').write_text(json.dumps(lock,indent=2)+'\n');print(json.dumps({'pinned_files':len(runtime_files),'loader_hash':sha(loader),'probe_hash':expected},indent=2))
if __name__=='__main__':main()
