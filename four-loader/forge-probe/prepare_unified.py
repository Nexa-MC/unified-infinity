#!/usr/bin/env python3
"""Prepare an isolated own-Forge probe on the existing one-owner NeoForge host."""
import argparse, hashlib, json, os, pathlib, shutil
HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parents[1]
def sha(path): return hashlib.sha256(path.read_bytes()).hexdigest()
def main():
    p = argparse.ArgumentParser()
    p.add_argument('--profile', default='unified-forge-probe-first')
    p.add_argument('--core', default='source-workspace/artifacts/unified-infinity-four-loader-first-bda743b2.jar')
    p.add_argument('--core-sha', default='bda743b2a0ed5cab72ac78ab4d75cb0a30384d8bba95dd76680639fe8ae697db')
    p.add_argument('--host', default='runtime-bundle/build-forge-candidate/libs/unified-infinity-0.1.0-dev.jar')
    p.add_argument('--host-sha', required=True)
    a=p.parse_args()
    assert '/' not in a.profile and a.profile.startswith('unified-forge-probe-')
    profile=ROOT/'run'/a.profile
    assert not profile.exists(), 'Preserve previous profile and evidence'
    probe=HERE/'build/unified-forge-probe-0.1.0.jar'
    provider=ROOT/'run/source-built-lithium-unified/mods/unified-infinity-preload-0.1.0-dev.jar'
    core=ROOT/a.core; host=ROOT/a.host
    assert sha(core)==a.core_sha
    assert sha(host)==a.host_sha
    assert sha(probe)=='3a016e8b8340c7c10b6490f15bb7452c1555363035c7373f4d81ccfacfde15fe'
    assert sha(provider)=='7b549d3725cbf63a529cf543aafa9ce1f9d0d65d3fe3cac93411f429e0955d99', 'Provider must retain accepted pin'
    baseline=ROOT/'run/neoforge-native'
    assert (baseline/'eula.txt').read_text().strip()=='eula=true', 'Existing accepted EULA required'
    profile.mkdir(); (profile/'mods').mkdir()
    (profile/'config').mkdir()
    (profile/'config/neoforge-server.toml').write_text('advertiseDedicatedServerToLan = false\n')
    shutil.copytree(baseline/'libraries',profile/'libraries',copy_function=os.link)
    shutil.copy2(baseline/'eula.txt',profile/'eula.txt')
    for source in [core,host,provider,probe]: shutil.copy2(source,profile/'mods'/source.name)
    props={
      'server-ip':'127.0.0.1','server-port':'25592','online-mode':'true','enable-rcon':'false','enable-query':'false','enable-status':'false',
      'enforce-secure-profile':'true','white-list':'true','enforce-whitelist':'true','max-players':'1','level-name':'world','level-seed':'5210',
      'view-distance':'2','simulation-distance':'2','spawn-protection':'0','max-tick-time':'60000','motd':'Private original Forge ABI probe on Unified',
      'difficulty':'peaceful','allow-nether':'true','generate-structures':'false','sync-chunk-writes':'true','pause-when-empty-seconds':'-1'}
    (profile/'server.properties').write_text(''.join(f'{k}={v}\n' for k,v in props.items()))
    runtime=sorted((profile/'libraries').rglob('*.jar'))+[profile/'libraries/net/neoforged/neoforge/21.1.219/unix_args.txt',ROOT/'.toolchains/jdk-21.0.12.1+1/bin/java']
    lock={'profile':str(profile.relative_to(ROOT)),'minecraft':'1.21.1','neoforge':'21.1.219','fml':'4.0.42','eventbus':'8.0.5',
      'core_sha256':sha(core),'host_sha256':sha(host),'provider_sha256':sha(provider),'probe_sha256':sha(probe),
      'source_namespace':'Mojmap production Forge52.1.0','server_properties':props,'mods':{x.name:sha(x) for x in sorted((profile/'mods').glob('*.jar'))},
      'runtime_files':[{'path':str(x.relative_to(ROOT)),'sha256':sha(x)} for x in runtime],
      'eula':'Reuses previously accepted Minecraft EULA, https://www.minecraft.net/en-us/eula',
      'neo_server_config':{'path':'config/neoforge-server.toml','required_root_value':{'advertiseDedicatedServerToLan':False}},
      'scope':'Isolated unchanged own Forge-only probe; no QSL or third-party Forge mod'}
    lock_path=HERE/(a.profile+'-environment-lock.json'); assert not lock_path.exists()
    lock_path.write_text(json.dumps(lock,indent=2)+'\n')
    (ROOT/'logs'/a.profile).mkdir()
    print(json.dumps({'profile':str(profile),'lock':str(lock_path),'lock_sha256':sha(lock_path),'mods':lock['mods']},indent=2))
if __name__=='__main__': main()
