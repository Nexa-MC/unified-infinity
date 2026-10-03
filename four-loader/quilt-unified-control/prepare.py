#!/usr/bin/env python3
import hashlib,json,pathlib,os,shutil,argparse,re
HERE=pathlib.Path(__file__).resolve().parent;ROOT=HERE.parents[1]
ap=argparse.ArgumentParser();ap.add_argument('--profile',required=True);ap.add_argument('--core',required=True);ap.add_argument('--core-sha',required=True);ap.add_argument('--host',required=True);ap.add_argument('--host-sha',required=True);a=ap.parse_args()
assert re.fullmatch('unified-quilt-probe-[A-Za-z0-9_-]+',a.profile)
PROFILE=ROOT/'run'/a.profile
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
inputs={
a.core:a.core_sha,
a.host:a.host_sha,
'run/source-built-lithium-unified/mods/unified-infinity-preload-0.1.0-dev.jar':'7b549d3725cbf63a529cf543aafa9ce1f9d0d65d3fe3cac93411f429e0955d99',
'four-loader/quilt-probe/build/unified-native-quilt-probe-0.1.0.jar':'f420e2021563d25931f1783f5a5744943dfbafc7557ae5c52ff2090331066b04'}
for name,digest in inputs.items():assert sha(ROOT/name)==digest,name
assert not PROFILE.exists(),'Preserve prior profile/evidence'
BASE=ROOT/'run/neoforge-native';assert (BASE/'eula.txt').read_text().strip()=='eula=true'
PROFILE.mkdir();(PROFILE/'mods').mkdir();(PROFILE/'config').mkdir();(PROFILE/'config/neoforge-server.toml').write_text('advertiseDedicatedServerToLan = false\n');shutil.copytree(BASE/'libraries',PROFILE/'libraries',copy_function=os.link);shutil.copy2(BASE/'eula.txt',PROFILE/'eula.txt')
for name in inputs:shutil.copy2(ROOT/name,PROFILE/'mods'/pathlib.Path(name).name)
props={'server-ip':'127.0.0.1','server-port':'25621','online-mode':'true','enable-rcon':'false','enable-query':'false','enable-status':'false','enforce-secure-profile':'true','white-list':'true','enforce-whitelist':'true','max-players':'1','level-name':'world','level-seed':'5210','view-distance':'2','simulation-distance':'2','spawn-protection':'0','max-tick-time':'60000','motd':'Private Unified native Quilt ABI probe','difficulty':'peaceful','allow-nether':'true','generate-structures':'false','sync-chunk-writes':'true','pause-when-empty-seconds':'-1'}
(PROFILE/'server.properties').write_text(''.join(f'{k}={v}\n' for k,v in props.items()))
runtime=sorted((PROFILE/'libraries').rglob('*.jar'))+[PROFILE/'libraries/net/neoforged/neoforge/21.1.219/unix_args.txt']
lock={'profile':str(PROFILE.relative_to(ROOT)),'inputs':inputs,'java_sha256':sha(ROOT/'.toolchains/jdk-21.0.12.1+1/bin/java'),'runtime_files':[{'path':str(p.relative_to(ROOT)),'sha256':sha(p)} for p in runtime],'mods':{p.name:sha(p) for p in (PROFILE/'mods').glob('*.jar')},'probe_sha256':inputs['four-loader/quilt-probe/build/unified-native-quilt-probe-0.1.0.jar'],'server_properties':props,'eula':'Previously accepted Minecraft EULA, reused unchanged','scope':'Original own native Quilt probe; only host internal pinned original base/lifecycle; one FML/FFLoader/Mixin/classloader pipeline'}
(HERE/(a.profile+'-environment-lock.json')).write_text(json.dumps(lock,indent=2)+'\n');(HERE/'logs'/a.profile).mkdir(parents=True);print(json.dumps(lock['mods'],indent=2))
