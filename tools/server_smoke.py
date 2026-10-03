#!/usr/bin/env python3
"""Run an authorized loopback-only NeoForge smoke test, save, stop and report."""
import argparse,datetime,hashlib,json,os,pathlib,select,subprocess,time
p=argparse.ArgumentParser();p.add_argument('profile',type=pathlib.Path);p.add_argument('--timeout',type=int,default=480);p.add_argument('--tag',required=True);p.add_argument('--jvm-arg',action='append',default=[]);p.add_argument('--jfr',action='store_true');p.add_argument('--require-marker');p.add_argument('--save-after-marker');p.add_argument('--loader',choices=['neoforge','fabric'],default='neoforge');a=p.parse_args()
root=pathlib.Path(__file__).resolve().parent.parent
profile=a.profile.resolve()
# Approval is deliberately required as a checked-in, non-default profile decision.
if (profile/'eula.txt').read_text().strip()!='eula=true':raise SystemExit('EULA has not been accepted for this profile')
props=(profile/'server.properties').read_text()
for needed in ['server-ip=127.0.0.1','online-mode=true','enable-rcon=false','enable-query=false']:
 if needed not in props.splitlines():raise SystemExit('Missing required loopback/test setting: '+needed)
java=root/'.toolchains/jdk-21.0.12.1+1/bin/java'
args=[str(java),'-Xms512M','-Xmx2G','@libraries/net/neoforged/neoforge/21.1.219/unix_args.txt','nogui']
if a.loader=='fabric':
 libs=list((profile/'libraries').rglob('*.jar'))
 cp=os.pathsep.join(str(x) for x in libs)+os.pathsep+str(profile/'server.jar')
 args=[str(java),'-Xms512M','-Xmx2G','-Dfabric.gameJarPath='+str(profile/'server.jar'),'-cp',cp,'net.fabricmc.loader.impl.launch.knot.KnotServer','nogui']
args[1:1]=a.jvm_arg
if a.jfr:args.insert(1,'-XX:StartFlightRecording=filename='+str(root/'logs'/f'{a.tag}.jfr')+',settings=profile,dumponexit=true')
log=root/'logs'/f'{a.tag}.log';report=root/'logs'/f'{a.tag}.json'
progress_path=next((pathlib.Path(x.split('=',1)[1]) for x in a.jvm_arg if x.startswith('-Dunified.infinity.progressFile=')),None)
if progress_path and not progress_path.resolve().is_relative_to(root/'logs'):raise SystemExit('Progress path must be under project logs')
phase_samples=[];last_phase=None;peak_before_commit_kib=0;commit_observed=False
input_mods={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted((profile/'mods').glob('*.jar'))}
start=time.monotonic();ready=False;saving=False;stopped=False;ready_seconds=None;max_rss_kib=0;max_hwm_kib=0;max_threads=0;marker_seen=False;save_requested=False
proc=subprocess.Popen(args,cwd=profile,stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,bufsize=0)
buffer=b'';deadline=start+a.timeout;stop_sent=None
with log.open('wb') as out:
 while proc.poll() is None:
  values={}
  try:
   status=pathlib.Path(f'/proc/{proc.pid}/status').read_text()
   values={x.split(':',1)[0]:x.split(':',1)[1].strip().split()[0] for x in status.splitlines() if ':' in x and x.split(':',1)[1].strip()}
   max_rss_kib=max(max_rss_kib,int(values.get('VmRSS',0)));max_hwm_kib=max(max_hwm_kib,int(values.get('VmHWM',0)));max_threads=max(max_threads,int(values.get('Threads',0)))
  except (OSError,StopIteration,ValueError):pass
  if not commit_observed:peak_before_commit_kib=max(peak_before_commit_kib,int(values.get('VmRSS',0)))
  if progress_path:
   try:
    phase=json.loads(progress_path.read_text());key=(phase.get('stage'),phase.get('status'))
    if key!=last_phase and len(phase_samples)<128:
     phase_samples.append({'observed_seconds':round(time.monotonic()-start,4),'stage':key[0],'status':key[1],'rss_kib':int(values.get('VmRSS',0)),'open_fds':len(list(pathlib.Path(f'/proc/{proc.pid}/fd').iterdir())),'pipeline_elapsed_ms':phase.get('elapsedMs')});last_phase=key
    if key==('commit','complete'):commit_observed=True
   except (OSError,ValueError):pass
  if time.monotonic()>deadline:
   proc.terminate()
   try:proc.wait(timeout=20)
   except subprocess.TimeoutExpired:proc.kill();proc.wait()
   break
  r,_,_=select.select([proc.stdout],[],[],.5)
  if not r:continue
  data=os.read(proc.stdout.fileno(),65536)
  if not data:continue
  out.write(data);out.flush();buffer+=data
  while b'\n' in buffer:
   line,buffer=buffer.split(b'\n',1)
   if a.require_marker and a.require_marker.encode() in line:marker_seen=True
   if b'Done (' in line and b'For help' in line and not ready:
    ready=True;ready_seconds=round(time.monotonic()-start,3)
    if not a.save_after_marker:
     proc.stdin.write(b'save-all flush\n');proc.stdin.flush();save_requested=True
   if ready and a.save_after_marker and a.save_after_marker.encode() in line and not save_requested:
    proc.stdin.write(b'save-all flush\n');proc.stdin.flush();save_requested=True
   if ready and (b'Saved the game' in line or b'Saved the world' in line) and not saving:
    saving=True;proc.stdin.write(b'stop\n');proc.stdin.flush();stop_sent=time.monotonic()
   if b'All dimensions are saved' in line:stopped=True
 try:out.write(proc.stdout.read() or b'')
 except Exception:pass
world=profile/'world'/'level.dat'
res={'tag':a.tag,'timestamp_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'exit_code':proc.returncode,'duration_seconds':round(time.monotonic()-start,3),'ready_marker':ready,'ready_seconds':ready_seconds,'peak_sampled_rss_kib':max_rss_kib,'kernel_rss_highwater_kib_observed':max_hwm_kib,'peak_sampled_threads':max_threads,'extra_jvm_args':a.jvm_arg,'input_mod_sha256':input_mods,'jfr_enabled':a.jfr,'phase_observations':phase_samples,'peak_rss_before_first_commit_observation_kib':peak_before_commit_kib if progress_path else None,'loader':a.loader,'jvm_flags':['-Xms512M','-Xmx2G'],'performance_limitations':'single run; RSS/Threads sampled at log/select intervals up to 0.5s; VmHWM read from Linux; tick metrics only if explicit probe marker present; no frame latency','save_command_acknowledged':saving,'all_dimensions_saved':stopped,'world_level_dat_exists':world.exists(),'world_level_dat_sha256':hashlib.sha256(world.read_bytes()).hexdigest() if world.exists() else None,'network':'127.0.0.1 only; online-mode=true; no RCON/query','scope':'server bootstrap + console save/stop; no client/render/player/network or third-party-mod parity evidence','required_marker':a.require_marker,'required_marker_seen':marker_seen if a.require_marker else None,'passed':proc.returncode==0 and ready and saving and world.exists() and (not a.require_marker or marker_seen)}
report.write_text(json.dumps(res,indent=2)+'\n');print(json.dumps(res));raise SystemExit(0 if res['passed'] else 1)
