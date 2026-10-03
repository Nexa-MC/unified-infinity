#!/usr/bin/env python3
"""Pinned loopback native Quilt/QSL control with exact-once evidence checks."""
import argparse,datetime,hashlib,json,os,pathlib,re,select,socket,subprocess,time
from verify_world import verify
HERE=pathlib.Path(__file__).resolve().parent
ROOT=HERE.parents[1]
PROFILE=ROOT/'run/unified-quilt-probe-first'
LOGS=HERE/'logs'
STAGES=['pre_launch','init','method_reference','server_init','automatic_ready','ready','ready_to_save','stopped']
def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def parse(raw,phase,probe_sha):
    lines=raw.decode('utf-8',errors='replace').splitlines()
    markers=[line for line in lines if 'NATIVE_QUILT_PROBE' in line]
    counts={stage:sum(f'PASS stage={stage} ' in line for line in markers) for stage in STAGES}
    def index(stage):return next((i for i,line in enumerate(markers) if f'PASS stage={stage} ' in line),-1)
    ordered=all(index(a)<index(b) for a,b in [('pre_launch','init'),('init','method_reference'),('method_reference','server_init'),('server_init','ready'),('ready','ready_to_save'),('automatic_ready','ready'),('automatic_ready','ready_to_save'),('ready_to_save','stopped')])
    ready=next((line for line in markers if 'PASS stage=ready ' in line),'')
    pre=next((line for line in markers if 'PASS stage=pre_launch ' in line),'')
    tick=next((line for line in markers if 'PASS stage=ready_to_save ' in line),'')
    mixin=re.search(r'mixin_ticks=(\d+)',tick)
    class_count=sum('NATIVE_QUILT_PROBE CLASS_DEFINED' in line for line in markers)
    return {'markers':markers,'stage_counts':counts,'class_defined_count':class_count,'entrypoint_order_valid':ordered,
      'original_jar_identity_verified':all(x in pre for x in ['native_id=unified-quilt-probe','group=dev.infinity.probes','version=0.1.0+native',f'sha256={probe_sha}']),
      'saved_data_phase_verified':f'phase={phase}' in ready and 'marker=native_quilt_qsl_alpha5_v1' in ready and f'read_before_write={str(phase=="reopen").lower()}' in ready,
      'qsl_and_mixin_tick_verified':bool(mixin and int(mixin[1])>=5 and 'ticks=5 ' in tick and 'auto_ready=1' in tick),
      'loopback_binding_verified':any('Starting Minecraft server on 127.0.0.1:25621' in l for l in lines),
      'server_ready':any('Done (' in l and 'For help' in l for l in lines),
      'save_acknowledged':any('Saved the game' in l or 'Saved the world' in l for l in lines),
      'all_dimensions_saved':any('All dimensions are saved' in l for l in lines),
      'no_probe_failure':not any('NATIVE_QUILT_PROBE FAIL' in l or 'NATIVE_QUILT_PROBE PASS stage=client_init ' in l for l in lines)}
def main():
    ap=argparse.ArgumentParser();ap.add_argument('--profile',default='unified-quilt-probe-first');ap.add_argument('--phase',choices=['create','reopen'],required=True);ap.add_argument('--attempt',default='1');ap.add_argument('--timeout',type=int,default=600);ap.add_argument('--runtime-slot-approved',action='store_true',required=True);a=ap.parse_args()
    global PROFILE,LOGS
    assert re.fullmatch('unified-quilt-probe-[A-Za-z0-9_-]+',a.profile)
    PROFILE=ROOT/'run'/a.profile
    if a.profile!='unified-quilt-probe-first':LOGS=HERE/'logs'/a.profile
    assert re.fullmatch('[A-Za-z0-9_-]+',a.attempt)
    lockpath=HERE/('unified-environment-lock.json' if a.profile=='unified-quilt-probe-first' else a.profile+'-environment-lock.json')
    lock=json.loads(lockpath.read_text())
    assert sha(ROOT/'.toolchains/jdk-21.0.12.1+1/bin/java')==lock['java_sha256'],'Java binary changed'
    for entry in lock['runtime_files']:assert sha(ROOT/entry['path'])==entry['sha256'],f'Input changed: {entry["path"]}'
    assert {p.name:sha(p) for p in (PROFILE/'mods').glob('*.jar')}==lock['mods'],'Runtime mods changed'
    assert 'advertiseDedicatedServerToLan = false' in (PROFILE/'config/neoforge-server.toml').read_text(),'LAN advertisement must be off'
    assert (PROFILE/'eula.txt').read_text().strip()=='eula=true'
    props=dict(l.split('=',1) for l in (PROFILE/'server.properties').read_text().splitlines() if '=' in l and not l.startswith('#'))
    for k,v in {'server-ip':'127.0.0.1','online-mode':'true','enable-rcon':'false','enable-query':'false','enable-status':'false','white-list':'true','enforce-whitelist':'true'}.items():assert props.get(k)==v,k
    assert sorted(p.name for p in (PROFILE/'mods').glob('*.jar'))==sorted(lock['mods'])
    with socket.socket() as sock:sock.bind(('127.0.0.1',int(props['server-port'])))
    before=None
    if a.phase=='create':assert not (PROFILE/'world').exists(),'Create requires a fresh world'
    else:before=verify(PROFILE)
    LOGS.mkdir(parents=True,exist_ok=True);log_path=LOGS/f'unified-{a.phase}-{a.attempt}.log';report_path=log_path.with_suffix('.json')
    assert not log_path.exists() and not report_path.exists(),'Preserve prior evidence'
    command=[str(ROOT/'.toolchains/jdk-21.0.12.1+1/bin/java'),'-Xms512M','-Xmx2G','-Djava.awt.headless=true',f'-Dunified.quiltProbe.phase={a.phase}','@libraries/net/neoforged/neoforge/21.1.219/unix_args.txt','nogui']
    start=time.monotonic();save_requested=False;stop_requested=False;timed_out=False;ready=False;probe_ready=False;buffer=b''
    proc=subprocess.Popen(command,cwd=PROFILE,stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,bufsize=0)
    with log_path.open('wb') as log:
      while proc.poll() is None:
        if time.monotonic()-start>a.timeout:
          timed_out=True;proc.terminate()
          try:proc.wait(timeout=20)
          except subprocess.TimeoutExpired:proc.kill();proc.wait()
          break
        readable,_,_=select.select([proc.stdout],[],[],.5)
        if not readable:continue
        chunk=os.read(proc.stdout.fileno(),65536)
        if not chunk:continue
        log.write(chunk);log.flush();buffer+=chunk
        while b'\n' in buffer:
          raw,buffer=buffer.split(b'\n',1);line=raw.decode('utf-8',errors='replace')
          if 'Done (' in line and 'For help' in line:ready=True
          if 'NATIVE_QUILT_PROBE PASS stage=ready_to_save ' in line:probe_ready=True
          if ready and probe_ready and not save_requested:
            proc.stdin.write(b'save-all flush\n');proc.stdin.flush();save_requested=True
          if save_requested and not stop_requested and ('Saved the game' in line or 'Saved the world' in line):
            proc.stdin.write(b'stop\n');proc.stdin.flush();stop_requested=True
      log.write(proc.stdout.read() or b'')
    result=parse(log_path.read_bytes(),a.phase,lock['probe_sha256'])
    try:after=verify(PROFILE)
    except (OSError,ValueError,KeyError,AssertionError) as error:after={'passed':False,'error':str(error)}
    result['all_runtime_inputs_unchanged']=all(sha(ROOT/e['path'])==e['sha256'] for e in lock['runtime_files']) and {p.name:sha(p) for p in (PROFILE/'mods').glob('*.jar')}==lock['mods']
    result.update({'phase':a.phase,'attempt':a.attempt,'timestamp_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'loader':'Unified native Quilt API on NeoForge21.1.219','qsl':'10.0.0-alpha.5+1.21.1 original base/lifecycle embedded in host','probe_sha256':lock['probe_sha256'],'command':command,'exit_code':proc.returncode,'timed_out':timed_out,'duration_seconds':round(time.monotonic()-start,3),'console_save_requested':save_requested,'console_stop_requested':stop_requested,'offline_world_before_launch':before,'offline_world_after_stop':after,'unified_environment_lock_sha256':sha(lockpath),'network':f'loopback 127.0.0.1:{props["server-port"]}; online-mode=true; RCON/query/status disabled; LAN advertisement configured off; no accounts','scope':'Own unchanged Quilt-only server ABI probe; internal original QSL on one NeoForge host; no original Quilt engine or external QSL JARs'})
    booleans=['entrypoint_order_valid','original_jar_identity_verified','saved_data_phase_verified','qsl_and_mixin_tick_verified','server_ready','save_acknowledged','all_dimensions_saved','no_probe_failure','loopback_binding_verified']
    result['passed']=proc.returncode==0 and not timed_out and result['class_defined_count']==1 and all(n==1 for n in result['stage_counts'].values()) and all(result[k] for k in booleans) and after['passed'] and result['all_runtime_inputs_unchanged']
    report_path.write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2));raise SystemExit(0 if result['passed'] else 1)
if __name__=='__main__':main()
