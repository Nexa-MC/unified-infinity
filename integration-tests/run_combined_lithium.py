#!/usr/bin/env python3
"""Unchanged official Lithium binary, isolated loopback create/save/reopen proof."""
import argparse, datetime, hashlib, json, os, pathlib, re, select, subprocess, time, signal, zipfile
ROOT=pathlib.Path(__file__).resolve().parent.parent
P=argparse.ArgumentParser(); P.add_argument('profile',choices=['native','unified']); P.add_argument('cycle',type=int,choices=[1,2]); P.add_argument('--tag-suffix',default=''); P.add_argument('--timeout',type=int,default=420); A=P.parse_args()
profile=ROOT/'run'/('combined-lithium-'+A.profile)
tag=f'combined-lithium-{A.profile}-{A.cycle}'+A.tag_suffix
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
jar='lithium-fabric-0.15.4+mc1.21.1.jar'; expected='92329d98c57f5a22091a0adb509fdb1d60113a5602c708b799b13134bad13baa'
assert sha(profile/'mods'/jar)==expected
mods={p.name:sha(p) for p in sorted((profile/'mods').glob('*.jar'))}
assert set(mods)==({jar,'fabric-api-0.116.7+1.21.1.jar'} if A.profile=='native' else {jar,'unified-infinity-0.1.0-dev.jar','unified-infinity-connector-2.0.0-beta.17+1.21.1-derived.jar','unified-infinity-preload-0.1.0-dev.jar'})
if A.profile=='unified':
 assert mods['unified-infinity-0.1.0-dev.jar']=='e0fbbe9f5a101df29429719bfd171b5e56c55afdeefa027f39f5d1a72b35715b'
 assert mods['unified-infinity-connector-2.0.0-beta.17+1.21.1-derived.jar']=='6acb0706519701e6816221a739e8f6d11d0bf280369ba87764b63f8345ef679c'
 assert mods['unified-infinity-preload-0.1.0-dev.jar']=='7b549d3725cbf63a529cf543aafa9ce1f9d0d65d3fe3cac93411f429e0955d99'
assert (profile/'eula.txt').read_text().strip()=='eula=true'
props=(profile/'server.properties').read_text().splitlines()
for required in ['server-ip=127.0.0.1',f'server-port={25572 if A.profile=="native" else 25571}','online-mode=true','enable-rcon=false','enable-query=false','level-name=world']:
 assert required in props,required
world=profile/'world'; before={str(p.relative_to(world)):sha(p) for p in world.rglob('*') if p.is_file()} if world.exists() else {}
assert ('level.dat' in before)==(A.cycle==2), 'First cycle must be fresh and second cycle must reuse saved world'
java=ROOT/'.toolchains/jdk-21.0.12.1+1/bin/java'
args=[str(java),'-Xms512M','-Xmx2G']
if A.profile=='native':
 args+=['-Dfabric.gameJarPath='+str(profile/'server.jar'),'-cp',os.pathsep.join(str(x) for x in sorted((profile/'libraries').rglob('*.jar')))+os.pathsep+str(profile/'server.jar'),'net.fabricmc.loader.impl.launch.knot.KnotServer','nogui']
else:args+=['@libraries/net/neoforged/neoforge/21.1.219/unix_args.txt','nogui']
if A.profile=='unified':
 config=profile/'config/connector.json'
 if config.exists():assert json.loads(config.read_text()).get('enableMixinSafeguard',True), 'Mixin safeguard must remain enabled'
 audit=profile/'.cache/connector/patch_audit.txt'
 last=ROOT/'integration-tests/last-combined-artifact.sha256'
 current=sha(profile/'mods'/'unified-infinity-connector-2.0.0-beta.17+1.21.1-derived.jar')
 if audit.exists() and re.search(r'^Failed: [1-9]',audit.read_text(),re.M):
  with zipfile.ZipFile(profile/'mods'/'unified-infinity-connector-2.0.0-beta.17+1.21.1-derived.jar') as archive:
   cacheclass=archive.read('org/sinytra/connector/infinity/ManagedConnectorTransformerEnvironment.class')
  assert b':lithium-trial:' in cacheclass, 'Failed audit requires source-versioned experimental cache identity'
  assert not last.exists() or last.read_text().strip()!=current, 'Refusing cached failed-audit restart; fix the source first'
 last.write_text(current+'\n')
start=time.monotonic(); ready=False; saved=False; stopped=False; persistent=False; output=b''; buffer=b''; timeout=False
proc=subprocess.Popen(args,cwd=profile,stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,bufsize=0)
def interrupted(signum,frame):
 proc.terminate()
 try:proc.wait(timeout=15)
 except subprocess.TimeoutExpired:proc.kill();proc.wait()
 raise SystemExit(128+signum)
signal.signal(signal.SIGINT,interrupted)
signal.signal(signal.SIGTERM,interrupted)
def command(s):
 proc.stdin.write((s+'\n').encode()); proc.stdin.flush()
with (ROOT/'logs'/(tag+'.log')).open('wb') as log:
 while True:
  if time.monotonic()-start>A.timeout:
   timeout=True; proc.terminate()
   try:proc.wait(timeout=20)
   except subprocess.TimeoutExpired:proc.kill(); proc.wait()
   break
  rs,_,_=select.select([proc.stdout],[],[],0.25)
  if rs:
   chunk=os.read(proc.stdout.fileno(),65536)
   if not chunk:
    if proc.poll() is not None:break
    continue
   output+=chunk; buffer+=chunk; log.write(chunk); log.flush()
   while b'\n' in buffer:
    line,buffer=buffer.split(b'\n',1)
    if b'Done (' in line and b'For help' in line and not ready:
     ready=True
     if A.cycle==1:
      command('scoreboard objectives add lithium_trial dummy')
      command('scoreboard players set UnifiedInfinityTrial lithium_trial 1211154')
     command('scoreboard players get UnifiedInfinityTrial lithium_trial')
    if b'UnifiedInfinityTrial has 1211154 [lithium_trial]' in line and not persistent:
     persistent=True;command('save-all flush')
    if b'Saved the game' in line and not saved:
     saved=True;command('stop')
    if b'All dimensions are saved' in line:stopped=True
  if proc.poll() is not None:
   rest=proc.stdout.read() or b'';output+=rest;log.write(rest)
   if b'All dimensions are saved' in rest:stopped=True
   break
proc.wait(); text=output.decode(errors='replace')
after={str(p.relative_to(world)):sha(p) for p in world.rglob('*') if p.is_file()} if world.exists() else {}
# Native loader mod list and Lithium configuration logger prove recognition and executed mod code.
recognized=bool(re.search(r'(?:- lithium 0\.15\.4\+mc1\.21\.1|Lithium 0\.15\.4[+_]mc1\.21\.1 \(lithium\))',text,re.I))
active='Loaded configuration file for Lithium' in text
result={'profile':A.profile,'cycle':A.cycle,'timestamp_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'passed':proc.returncode==0 and ready and saved and stopped and persistent and recognized and active and 'level.dat' in after,'exit_code':proc.returncode,'timed_out':timeout,'ready':ready,'saved':saved,'all_dimensions_saved':stopped,'persistent_score_verified':persistent,'lithium_version_in_log':recognized,'lithium_config_code_executed':active,'same_original_fabric_jar':mods[jar]==expected,'input_mod_sha256':mods,'world_before':before,'world_after':after,'profile_network':f'127.0.0.1:{25572 if A.profile=="native" else 25571}; online-mode=true; RCON/query disabled','duration_seconds':round(time.monotonic()-start,3),'scope':'Unchanged Lithium server binary create/save/reopen. No performance, player, client/render, or exhaustive Mixin claim.'}
(ROOT/'logs'/(tag+'.json')).write_text(json.dumps(result,indent=2)+'\n')
print(json.dumps({k:v for k,v in result.items() if k not in ('world_before','world_after')},indent=2),flush=True)
raise SystemExit(0 if result['passed'] else 1)
