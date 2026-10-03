#!/usr/bin/env python3
"""Bounded, sequential, account-free real mixed-pack regression on exact archives.

Console control only. A new run-id creates new profiles, never replaces worlds.
Preparing profiles does not execute mod code. Execution must be separately approved.
"""
from __future__ import annotations
import argparse, datetime, gzip, hashlib, importlib.util, json, math, os
import pathlib, re, select, shutil, signal, socket, struct, subprocess, sys, time, zlib

ROOT = pathlib.Path(__file__).resolve().parents[2]
BASE = ROOT / 'mixed-pack'
HELPER = ROOT / 'integration-tests/run_lithium_hopper_parity.py'
spec = importlib.util.spec_from_file_location('hopper_harness_parsers', HELPER)
helper = importlib.util.module_from_spec(spec); spec.loader.exec_module(helper)
Nbt, Snbt, inventory = helper.Nbt, helper.Snbt, helper.inventory
FABRIC_LI = 'lithium-fabric-0.15.4+mc1.21.1.jar'
NEO_LI = 'lithium-neoforge-0.15.4+mc1.21.1.jar'
FABRIC_CH = 'Chunky-Fabric-1.4.23.jar'; NEO_CH = 'Chunky-NeoForge-1.4.23.jar'
FD = 'FarmersDelight-1.21.1-1.3.4.jar'; API = 'fabric-api-0.116.7+1.21.1.jar'
HOST = 'unified-infinity-0.1.0-dev.jar'
CORE = 'unified-infinity-connector-2.0.0-beta.17+1.21.1-derived.jar'
PRELOAD = 'unified-infinity-preload-0.1.0-dev.jar'
PINS = {
 FABRIC_LI:'92329d98c57f5a22091a0adb509fdb1d60113a5602c708b799b13134bad13baa',
 NEO_LI:'488f33216030c1cb0baa33e59de3d657d08d5795a6c2080c8c8bbbc133fc8757',
 FABRIC_CH:'3412b170247dde7351e0945d857e713bedf6fae05ab300aa74d06ffbde0ca07e',
 NEO_CH:'d72f235cf1f56f2c374f52c00bdda5034524b28142305a84cfc123a3f92ad274',
 FD:'139ad7696462c89c03eea463f805abffa552526c5dadaadae221dd9624cb197c',
 API:'08018cc48c97415a38016a00dbd5a2c7a460ba6b7a051690a8cb3dbb5e8482a4',
 HOST:'3802215d427501040a432a54e1304e50bbd6758a4610efeea46b0a479641b61e',
 CORE:'c8921d6a6d3ff3bb47e12913fb867344d1fab7c233e5bce7a9f35a53fef5e65e',
 PRELOAD:'7b549d3725cbf63a529cf543aafa9ce1f9d0d65d3fe3cac93411f429e0955d99',
}
SOURCES = {FABRIC_LI:ROOT/'docs/real-mod-trial'/FABRIC_LI, API:ROOT/'run/lithium-native/mods'/API,
 HOST:ROOT/'runtime-bundle/build/libs'/HOST,
 CORE:ROOT/'source-workspace/artifacts/unified-infinity-source-connector-adapter-fart-1.21.1.jar',
 PRELOAD:ROOT/'preload-ui/build/libs'/PRELOAD}
for name in (NEO_LI,FABRIC_CH,NEO_CH,FD): SOURCES[name]=BASE/'research/archives'/name
SETS = {'fabric':{FABRIC_LI,FABRIC_CH,API}, 'neoforge':{NEO_LI,NEO_CH,FD},
 'unified':{FABRIC_LI,FABRIC_CH,FD,HOST,CORE,PRELOAD}}
PORTS = {'fabric':25580,'neoforge':25581,'unified':25582}
SEED = '1211'; JVM = ['-Xms512M','-Xmx2G']
TARGET_CHUNKS = [(x,z) for x in range(127,130) for z in range(127,130)]
POSITIONS = {'source':(2,204,2), 'hopper':(2,203,2), 'sink':(2,202,2),
 'stove':(2,201,2), 'contents':(6,202,2), 'cutting_board':(9,202,2)}
sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
coords = lambda p: ' '.join(map(str,p))

def emit_json(path,data): path.write_text(json.dumps(data,indent=2)+'\n')
def stamp(): return datetime.datetime.now(datetime.timezone.utc).isoformat()
def profile_path(run_id,which): return ROOT/'run'/f'mixed-pack-{run_id}-{which}'
def manifest_tree(path):
 return {str(p.relative_to(path)):sha(p) for p in sorted(path.rglob('*')) if p.is_file()}
def properties(path):
 return dict(line.split('=',1) for line in path.read_text().splitlines() if '=' in line and not line.lstrip().startswith('#'))

def prepare(run_id,which):
 profile=profile_path(run_id,which)
 if profile.exists(): raise FileExistsError('Refusing to overwrite profile '+str(profile))
 source=ROOT/'run'/({'fabric':'lithium-native','neoforge':'neoforge-native','unified':'source-built-lithium-unified'}[which])
 for name in SETS[which]:
  assert SOURCES[name].is_file() and sha(SOURCES[name]) == PINS[name], 'Source hash mismatch: '+name
 profile.mkdir(parents=True); shutil.copytree(source/'libraries',profile/'libraries')
 (profile/'mods').mkdir(); (profile/'config').mkdir()
 for name in SETS[which]: shutil.copy2(SOURCES[name],profile/'mods'/name)
 (profile/'config/lithium.properties').write_text('# Unmodified default Lithium configuration; zero overrides.\n')
 if which=='fabric': shutil.copy2(source/'server.jar',profile/'server.jar')
 if which=='unified':
  shutil.copy2(source/'config/connector.json',profile/'config/connector.json')
  assert json.loads((profile/'config/connector.json').read_text())['enableMixinSafeguard'] is True
 assert (source/'eula.txt').read_text().strip()=='eula=true'
 shutil.copy2(source/'eula.txt',profile/'eula.txt')
 props={'server-ip':'127.0.0.1','server-port':PORTS[which],'online-mode':'true','enable-rcon':'false',
  'enable-query':'false','enable-status':'false','level-name':'world','level-seed':SEED,
  'level-type':'minecraft:normal','max-players':1,'view-distance':2,'simulation-distance':2,
  'spawn-protection':0,'difficulty':'peaceful','motd':'Private bounded mixed-pack regression',
  'enable-command-block':'false','sync-chunk-writes':'true','max-tick-time':60000}
 (profile/'server.properties').write_text(''.join(f'{k}={v}\n' for k,v in props.items()))
 doc={'profile':which,'created_utc':stamp(),'source_profile':str(source.relative_to(ROOT)),
  'mods':{n:sha(profile/'mods'/n) for n in sorted(SETS[which])},
  'libraries':manifest_tree(profile/'libraries'),'jvm_flags':JVM,'properties':props,
  'java_binary_sha256':sha(ROOT/'.toolchains/jdk-21.0.12.1+1/bin/java')}
 if which=='fabric': doc['server_jar_sha256']=sha(profile/'server.jar')
 emit_json(profile/'mixed-pack-profile.json',doc)
 return profile

def guard(profile,which,cycle):
 meta=json.loads((profile/'mixed-pack-profile.json').read_text())
 entries=list((profile/'mods').iterdir())
 assert all(p.is_file() and p.suffix=='.jar' for p in entries),'Unexpected mod directory entry'
 mods={p.name:sha(p) for p in entries}
 assert set(mods)==SETS[which] and all(PINS[n]==h for n,h in mods.items()),'Exact mod-set/hash mismatch'
 assert manifest_tree(profile/'libraries')==meta['libraries'],'Runtime libraries changed'
 java=ROOT/'.toolchains/jdk-21.0.12.1+1/bin/java'
 assert sha(java)==meta['java_binary_sha256']
 if which=='fabric': assert sha(profile/'server.jar')==meta['server_jar_sha256']
 for k,v in {'server-ip':'127.0.0.1','server-port':str(PORTS[which]),'online-mode':'true',
  'enable-rcon':'false','enable-query':'false','enable-status':'false','level-name':'world','level-seed':SEED}.items():
  assert properties(profile/'server.properties').get(k)==v,(k,v)
 assert (profile/'eula.txt').read_text().strip()=='eula=true'
 flags=[x for x in (profile/'config/lithium.properties').read_text().splitlines() if x.strip() and not x.lstrip().startswith('#')]
 assert not flags,'Lithium overrides are disallowed'
 if which=='unified':
  assert json.loads((profile/'config/connector.json').read_text())['enableMixinSafeguard'] is True
  audit=profile/'.cache/connector/patch_audit.txt'
  assert not audit.exists() or re.search(r'^Failed: 0$',audit.read_text(),re.M),'Failed audit restart disallowed'
 assert (profile/'world/level.dat').exists()==(cycle==2),'Create/reopen world mismatch'
 with socket.socket() as sock: sock.bind(('127.0.0.1',PORTS[which]))
 return mods

COMMAND_ERRORS=('Unknown or incomplete command','Incorrect argument','Expected ','No block entity was found',
 'That position is not loaded','Unknown item','Unknown block','Invalid or unknown','Could not set the block','Nothing changed')
class Server:
 def __init__(self,profile,which,tag,cycle,timeout):
  self.profile,self.which,self.tag,self.cycle,self.timeout=profile,which,tag,cycle,timeout
  self.proc=None;self.log=None;self.lines=[];self.buffer=b'';self.counter=0;self.commands=[];self.steps=[]
  self.observations=[];self.started=time.monotonic();self.ready=False;self.saved=False;self.chunky=None
  self.mods=guard(profile,which,cycle)
 def launch(self):
  java=ROOT/'.toolchains/jdk-21.0.12.1+1/bin/java'; args=[str(java),*JVM]
  if self.which=='fabric':
   args+=['-Dfabric.gameJarPath='+str(self.profile/'server.jar'),'-cp',os.pathsep.join(str(x) for x in sorted((self.profile/'libraries').rglob('*.jar')))+os.pathsep+str(self.profile/'server.jar'),'net.fabricmc.loader.impl.launch.knot.KnotServer','nogui']
  else: args+=['@libraries/net/neoforged/neoforge/21.1.219/unix_args.txt','nogui']
  self.launch_args=args;self.log=(BASE/'logs'/(self.tag+'.log')).open('wb')
  self.proc=subprocess.Popen(args,cwd=self.profile,stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,bufsize=0)
  self.wait(lambda:any('Done (' in x and 'For help' in x for x in self.lines),300)
  self.ready=True
 def pump(self,duration=.15):
  if time.monotonic()-self.started>self.timeout: raise TimeoutError('Overall server deadline exceeded')
  r,_,_=select.select([self.proc.stdout],[],[],duration)
  if r:
   data=os.read(self.proc.stdout.fileno(),65536)
   if data:
    self.log.write(data);self.log.flush();self.buffer+=data
    while b'\n' in self.buffer:
     line,self.buffer=self.buffer.split(b'\n',1)
     self.lines.append(re.sub(r'\x1b\[[0-9;]*m','',line.decode(errors='replace')).replace('§',''))
    return True
  return False
 def drain(self):
  while self.pump(0): pass
  if self.buffer: self.lines.append(self.buffer.decode(errors='replace'));self.buffer=b''
 def wait(self,predicate,timeout=30):
  deadline=time.monotonic()+timeout
  while not predicate():
   self.pump()
   if self.proc.poll() is not None:
    self.drain()
    if predicate():return
    raise RuntimeError('Server exited early: '+str(self.proc.returncode))
   if time.monotonic()>deadline:raise TimeoutError('Server console response timed out')
 def send(self,command):
  self.commands.append(command);self.proc.stdin.write((command+'\n').encode());self.proc.stdin.flush()
 def command(self,command):
  start=len(self.lines);self.counter+=1;marker=f'MIXED_ACK_{self.counter:05d}'
  self.send(command);self.send('say '+marker)
  self.wait(lambda:any(marker in x for x in self.lines[start:]))
  result=self.lines[start:]
  for line in result: assert not any(err in line for err in COMMAND_ERRORS),line
  return result
 def time(self):
  lines=self.command('time query gametime')
  values=[int(m[1]) for x in lines if (m:=re.search(r'The time is (\d+)',x))]
  assert len(values)==1,lines
  return values[0]
 def step(self,n):
  before=self.time();self.command(f'tick step {n}');deadline=time.monotonic()+n/20+25
  while True:
   after=self.time()
   if after==before+n:break
   assert after<before+n,(before,n,after)
   if time.monotonic()>deadline:raise TimeoutError('Tick stepping stalled')
   self.pump(.15)
  self.steps.append({'requested':n,'before':before,'after':after,'exact':True})
 def block(self,label):
  lines=self.command('data get block '+coords(POSITIONS[label]))
  values=[x.split('has the following block data:',1)[1].strip() for x in lines if 'has the following block data:' in x]
  assert len(values)==1,lines
  return Snbt(values[0]).parse()
 def snapshot(self,stage,expected):
  raw={label:self.block(label) for label in expected};observed={k:normalize_entity(v) for k,v in raw.items()}
  result={'stage':stage,'observed':observed,'expected':expected,'raw':raw,'passed':observed==expected}
  self.observations.append(result);print(f'{self.tag}: {stage}: {result["passed"]}',flush=True)
  assert result['passed'],json.dumps(result,indent=2)
 def chunky_run(self):
  # Verify all four bounded selection fields before issuing start. Never trim.
  self.command('chunky world minecraft:overworld');self.command('chunky shape square')
  self.command('chunky center 2048 2048');self.command('chunky radius 16')
  selection='\n'.join(self.command('chunky selection'))
  for pattern in (r'World: minecraft:overworld',r'Shape: square',r'Center: 2,?048, 2,?048',r'Radius: 16(?:\.0)?(?:\D|$)'):
   assert re.search(pattern,selection),selection
  start=len(self.lines);began=time.monotonic();self.command('chunky start')
  try:self.wait(lambda:any('Task finished for ' in x for x in self.lines[start:]),120)
  except BaseException:
   self.send('chunky pause');raise
  lines=self.lines[start:];done=[x for x in lines if 'Task finished for ' in x];assert len(done)==1,done
  match=re.search(r'Processed: (\d+) chunks \(100(?:\.0+)?%\)',done[0]);assert match,done
  count=int(match[1]);assert 1<=count<=9,done
  self.chunky={'selection':selection,'completion':done[0],'processed_chunks':count,'maximum_target_chunks':9,
   'deadline_seconds':120,'elapsed_seconds':round(time.monotonic()-began,3),'target_chunks':TARGET_CHUNKS,'passed':True}
 def stop(self):
  self.saved=any('Saved the game' in x for x in self.command('save-all flush'));assert self.saved
  self.send('stop');self.wait(lambda:self.proc.poll() is not None,60);self.drain()
  assert self.proc.returncode==0 and any('All dimensions are saved' in x for x in self.lines)
 def cleanup(self):
  if self.proc and self.proc.poll() is None:
   try:
    self.send('chunky pause');self.send('stop');deadline=time.monotonic()+20
    while self.proc.poll() is None and time.monotonic()<deadline:
     try:self.pump(.1)
     except TimeoutError:break
    if self.proc.poll() is None:self.proc.terminate();self.proc.wait(timeout=10)
   except Exception:
    if self.proc.poll() is None:self.proc.kill();self.proc.wait()
  if self.proc:
   try:self.drain()
   except Exception:pass
  if self.log:self.log.close()
 def report(self):
  text='\n'.join(self.lines);audit=self.profile/'.cache/connector/patch_audit.txt'
  audit_text=audit.read_text() if audit.exists() else None
  audit_ok=self.which!='unified' or bool(audit_text and re.search(r'^Failed: 0$',audit_text,re.M))
  lithium_active=bool(re.search(r'Loaded configuration file for Lithium: \d+ options available, 0 override\(s\) found',text))
  versions={'lithium':bool(re.search(r'lithium.*0\.15\.4|Lithium 0\.15\.4',text,re.I)),
   'chunky':bool(re.search(r'chunky.*1\.4\.23',text,re.I))}
  if self.which!='fabric':versions['farmersdelight']=bool(re.search(r"Farmer.?s Delight 1\.3\.4|farmersdelight.*1\.3\.4",text,re.I))
  errors=[line for line in self.lines if '/ERROR]' in line or '/FATAL]' in line]
  fatal=bool(re.search(r'MixinApplyError|InvalidMixinException|InjectionError|NoSuchMethodError|NoSuchFieldError|ClassNotFoundException|NoClassDefFoundError|Exception in server tick loop|Failed to start the minecraft server',text))
  return {'profile':self.which,'cycle':self.cycle,'tag':self.tag,'ready':self.ready,'saved':self.saved,
   'exit_code':self.proc.returncode if self.proc else None,'duration_seconds':round(time.monotonic()-self.started,3),
   'input_mod_sha256':self.mods,'jvm_flags':JVM,'lithium_config_executed_zero_overrides':lithium_active,
   'versions_recognized':versions,'chunky':self.chunky,'snapshots':self.observations,'exact_tick_steps':self.steps,
   'commands':self.commands,'safeguard_audit_zero_failed':audit_ok,'safeguard_audit':audit_text,
   'error_log_lines':errors,'fatal_compatibility_exception':fatal,
   'passed':self.ready and self.saved and self.proc.returncode==0 and lithium_active and all(versions.values())
     and audit_ok and not fatal and all(o['passed'] for o in self.observations)}

def normalize_entity(value):
 entries=value.get('Inventory',{}).get('Items',[]) if value['id']=='farmersdelight:cooking_pot' else value.get('Items',[])
 return {'id':value['id'],'inventory':inventory(entries)}
def expected(which):
 output=[{'slot':8,'id':'farmersdelight:cooked_rice','count':2}] if which!='fabric' else [{'slot':0,'id':'minecraft:diamond','count':3}]
 answer={'source':{'id':'minecraft:chest','inventory':[]},'hopper':{'id':'minecraft:hopper','inventory':[]},
  'sink':{'id':'farmersdelight:cooking_pot' if which!='fabric' else 'minecraft:chest','inventory':output}}
 if which!='fabric':
  answer['contents']={'id':'minecraft:chest','inventory':[{'slot':i,'id':'farmersdelight:'+name,'count':n} for i,(name,n) in enumerate([('tomato',7),('cabbage',5),('rope',3),('iron_knife',1)])]}
  answer['cutting_board']={'id':'farmersdelight:cutting_board','inventory':[]}
 return answer

def first_cycle(s):
 s.command('gamerule randomTickSpeed 0');s.command('gamerule doMobSpawning false')
 s.command('gamerule doDaylightCycle false');s.command('gamerule doWeatherCycle false')
 s.chunky_run();s.command('tick freeze');s.command('forceload add 0 0');s.step(8)
 s.command('fill 0 199 0 12 206 4 minecraft:air')
 s.command('setblock '+coords(POSITIONS['source'])+' minecraft:chest')
 s.command('setblock '+coords(POSITIONS['hopper'])+' minecraft:hopper[facing=down]')
 if s.which=='fabric':
  s.command('setblock '+coords(POSITIONS['sink'])+' minecraft:chest')
  s.command('item replace block '+coords(POSITIONS['source'])+' container.0 with minecraft:diamond 3')
  s.step(48)
 else:
  s.command('setblock '+coords(POSITIONS['stove'])+' farmersdelight:stove[lit=true]')
  s.command('setblock '+coords(POSITIONS['sink'])+' farmersdelight:cooking_pot')
  s.command('data merge block '+coords(POSITIONS['sink'])+' {Inventory:{Size:9,Items:[{Slot:7,id:"minecraft:bowl",count:2}]}}')
  s.command('setblock '+coords(POSITIONS['contents'])+' minecraft:chest')
  for i,(name,n) in enumerate([('tomato',7),('cabbage',5),('rope',3),('iron_knife',1)]):
   s.command('item replace block '+coords(POSITIONS['contents'])+f' container.{i} with farmersdelight:{name} {n}')
  s.command('setblock 9 201 2 minecraft:stone')
  s.command('setblock '+coords(POSITIONS['cutting_board'])+' farmersdelight:cutting_board')
  s.command('item replace block '+coords(POSITIONS['source'])+' container.0 with farmersdelight:rice 2')
  s.step(260)
 s.snapshot('hopper_transfer_and_cooking' if s.which!='fabric' else 'native_fabric_hopper_transfer',expected(s.which))


def second_cycle(s):
 s.command('tick freeze');s.command('forceload add 0 0');s.step(8)
 s.snapshot('reopened_persisted_content',expected(s.which));s.step(32)
 s.snapshot('reopened_stable_after_ticks',expected(s.which))
 lines=s.command('chunky progress')
 assert any('No tasks running' in x for x in lines),lines

def read_chunk(world,cx,cz):
 path=world/'region'/f'r.{cx//32}.{cz//32}.mca'
 raw=path.read_bytes();off=4*((cx%32)+(cz%32)*32);location=int.from_bytes(raw[off:off+4],'big')
 sector,count=location>>8,location&255;assert sector and count,('Chunk not saved',cx,cz)
 chunk=raw[sector*4096:(sector+count)*4096];length=int.from_bytes(chunk[:4],'big');kind=chunk[4]
 assert 0<length<=count*4096-4 and kind in (1,2,3),'Invalid or external region compression'
 payload=chunk[5:4+length];payload=gzip.decompress(payload) if kind==1 else zlib.decompress(payload) if kind==2 else payload
 value=Nbt(payload).parse();assert (value['xPos'],value['zPos'])==(cx,cz)
 return value

def block_state(chunk,pos):
 x,y,z=pos;sections=[s for s in chunk['sections'] if s['Y']==y//16];assert len(sections)==1
 states=sections[0]['block_states'];palette=states['palette']
 if len(palette)==1:return palette[0]
 bits=max(4,(len(palette)-1).bit_length());per_long=64//bits;index=(y%16)*256+(z%16)*16+x%16
 value=states['data'][index//per_long]&((1<<64)-1)
 return palette[(value>>((index%per_long)*bits))&((1<<bits)-1)]

def saved_evidence(profile,which):
 world=profile/'world';chunk=read_chunk(world,0,0);observed={};blocks={}
 for label in expected(which):
  position=POSITIONS[label];matches=[v for v in chunk['block_entities'] if tuple(v[k] for k in ('x','y','z'))==position]
  assert len(matches)==1,(label,matches)
  observed[label]=normalize_entity(matches[0]);blocks[label]=block_state(chunk,position)
 assert observed==expected(which),(observed,expected(which))
 expected_blocks={label:v['id'] for label,v in expected(which).items()}
 for label,name in expected_blocks.items():assert blocks[label]['Name']==name,(label,blocks[label])
 if which!='fabric':
  blocks['stove']=block_state(chunk,POSITIONS['stove'])
  assert blocks['stove']['Name']=='farmersdelight:stove' and blocks['stove']['Properties']['lit']=='true'
 generated=[]
 for cx,cz in TARGET_CHUNKS:
  value=read_chunk(world,cx,cz);assert value['Status']=='minecraft:full',(cx,cz,value['Status'])
  generated.append({'x':cx,'z':cz,'status':value['Status']})
 return {'inventories':observed,'block_states':blocks,'chunky_full_target_chunks':generated,
  'all_target_chunks_full':len(generated)==9,'on_disk_matches_console':True}


def execute(args):
 report={'run_id':args.run_id,'timestamp_utc':stamp(),'harness_sha256':sha(pathlib.Path(__file__)),
  'parser_helper_sha256':sha(HELPER),'seed':SEED,'jvm_flags':JVM,'profiles':[],
  'scope':'Exact real server mod set; bounded 9-target Chunky pregeneration, hopper capability/cooking, item/block registries, same-world restart and direct saved NBT. No client, gameplay, broad pack or performance claim.',
  'network':'Loopback only; online-mode true; query/RCON/status disabled; no accounts/players','passed':False}
 destination=BASE/'logs'/f'{args.run_id}-summary.json';active=None
 def interrupt(sig,frame):
  if active:active.cleanup()
  raise SystemExit(128+sig)
 signal.signal(signal.SIGINT,interrupt);signal.signal(signal.SIGTERM,interrupt)
 try:
  for which in args.profiles:
   profile=profile_path(args.run_id,which)
   if not profile.exists():prepare(args.run_id,which)
   entry={'profile':which,'path':str(profile.relative_to(ROOT)),'cycles':[]};report['profiles'].append(entry)
   prior=None
   for cycle in (1,2):
    before=manifest_tree(profile/'world')
    assert (not before) if cycle==1 else before==prior,'Saved world changed between cycles'
    tag=f'{args.run_id}-{which}-{cycle}';active=Server(profile,which,tag,cycle,args.timeout)
    result=None
    try:
     active.launch();first_cycle(active) if cycle==1 else second_cycle(active)
     active.stop();result=active.report();result['disk']=saved_evidence(profile,which)
     result['world_before']=before;prior=manifest_tree(profile/'world');result['world_after']=prior
     assert result['passed'],json.dumps(result,indent=2)
    except BaseException as exc:
     active.cleanup();result=active.report();result['passed']=False;result['failure']=f'{type(exc).__name__}: {exc}'
     raise
    finally:
     if result:entry['cycles'].append(result);emit_json(BASE/'logs'/(tag+'.json'),result)
     active.cleanup();active=None;emit_json(destination,report)
   entry['passed']=all(c['passed'] for c in entry['cycles'])
   print(which+': BOTH CYCLES + SAVED NBT PASS',flush=True)
  groups={p['profile']:p for p in report['profiles']}
  if 'neoforge' in groups and 'unified' in groups:
   signatures=lambda p:[(s['stage'],s['observed']) for c in p['cycles'] for s in c['snapshots']]
   report['native_neoforge_unified_functional_parity']=signatures(groups['neoforge'])==signatures(groups['unified'])
  report['passed']=all(p.get('passed') for p in report['profiles']) and report.get('native_neoforge_unified_functional_parity',True)
 except BaseException as exc:
  report['failure']=f'{type(exc).__name__}: {exc}';raise
 finally:
  emit_json(destination,report);print(json.dumps({'passed':report['passed'],'summary':str(destination),'failure':report.get('failure')}),flush=True)
 return 0 if report['passed'] else 1

if __name__=='__main__':
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--run-id',required=True)
 p.add_argument('--profiles',nargs='+',choices=list(SETS),default=list(SETS));p.add_argument('--prepare-only',action='store_true')
 p.add_argument('--timeout',type=int,default=480);args=p.parse_args();assert re.fullmatch('[a-z0-9-]+',args.run_id)
 (BASE/'logs').mkdir(exist_ok=True)
 if args.prepare_only:
  for which in args.profiles:print(prepare(args.run_id,which))
 else:sys.exit(execute(args))
