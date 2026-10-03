#!/usr/bin/env python3
"""Replay sealed official NeoForge ModDevGradle development launch inputs."""
import argparse, datetime, hashlib, json, os, pathlib, shlex, subprocess, sys
from stage import ROOT, GAME, SOURCES
SETUP=ROOT/'four-loader/unified-client'
GENERATED=ROOT/'run/client-dev/development-build/moddev'
MANIFEST=GENERATED/'client-launch-inputs.json'
SEAL=SETUP/'evidence/direct-launch-seal.json'
JAVA=ROOT/'.toolchains/jdk-21.0.12.1+1/bin/java'

def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def check(p,h):
    if not p.is_file() or sha(p)!=h:raise RuntimeError(f'Frozen input changed: {p}')

def verify_mods():
    lock=json.loads((GAME/'profile-mods.lock.json').read_text())
    expected={pathlib.Path(p).name:h for p,h in SOURCES}
    if lock['test']!='08-four-loader-real-client' or len(lock['mods'])!=8:raise RuntimeError('Unexpected profile')
    if sorted(p.name for p in (GAME/'mods').glob('*.jar'))!=sorted(expected):raise RuntimeError('Direct mod set changed')
    for m in lock['mods']:
        p=ROOT/m['path']
        if p.parent!=GAME/'mods' or m['sha256']!=expected[p.name]:raise RuntimeError('Mod lock changed')
        check(p,m['sha256']);check(ROOT/m['source'],m['sha256'])
    return lock['mods']

def derive():
    mods=verify_mods();m=json.loads(MANIFEST.read_text())
    if m['mainClass']!='net.neoforged.devlaunch.Main' or pathlib.Path(m['gameDirectory'])!=GAME:raise RuntimeError('Unexpected development main/directory')
    if m['profileMods']!=mods or len(m['classpath'])!=97 or len(set(m['classpath']))!=97:raise RuntimeError('Resolved runtime differs from expected profile')
    if m['jvmArgs']!=['@'+str(GENERATED/'clientRunVmArgs.txt')] or m['args']!=['@'+str(GENERATED/'clientRunProgramArgs.txt')]:raise RuntimeError('Unexpected generated argument files')
    vmfile=GENERATED/'clientRunVmArgs.txt';argfile=GENERATED/'clientRunProgramArgs.txt'
    vm=shlex.split(vmfile.read_text(),comments=True);args=shlex.split(argfile.read_text(),comments=True)
    for value in ['-Xms256M','-Xmx1536M','-XX:ActiveProcessorCount=2']:
        if vm.count(value)!=1:raise RuntimeError(f'Expected resource bound missing: {value}')
    if [a for a in vm if a.startswith('-Xmx')]!=['-Xmx1536M']:raise RuntimeError('Conflicting heap bounds')
    if args[0]!='cpw.mods.bootstraplauncher.BootstrapLauncher' or args[args.index('--launchTarget')+1]!='forgeclientdev':raise RuntimeError('Unexpected official development target')
    if args[args.index('--fml.mcVersion')+1]!='1.21.1' or args[args.index('--fml.neoForgeVersion')+1]!='21.1.219':raise RuntimeError('Game/host version changed')
    for forbidden in ['--accessToken','--username','--uuid','--server','--quickPlayMultiplayer']:
        if forbidden in args or forbidden in vm:raise RuntimeError('Unexpected auth/server argument')
    environment=m['environment']
    if any(k not in ('MOD_CLASSES',) for k in environment):raise RuntimeError('Review unexpected official run environment field')
    files=[pathlib.Path(p) for p in m['classpath']]
    files += [MANIFEST,vmfile,argfile,GENERATED/'clientLegacyClasspath.txt',GENERATED/'clientLog4j2.xml',GENERATED/'artifacts/minecraft-1.21.1-clean.jar',GAME/'profile-mods.lock.json',JAVA]
    cpidx=vm.index('-p');files += [pathlib.Path(p) for p in vm[cpidx+1].split(os.pathsep)]
    files += [pathlib.Path(p) for p in (GENERATED/'clientLegacyClasspath.txt').read_text().splitlines() if p]
    records=[]
    for p in dict.fromkeys(files):
        empty_outputs={ROOT/'run/client-dev/development-build/classes/java/main',ROOT/'run/client-dev/development-build/resources/main'}
        if p in empty_outputs:
            if p.is_file() or (p.is_dir() and any(x.is_file() for x in p.rglob('*'))):raise RuntimeError('Unexpected classes/resources in the empty harness source set')
            records.append({'path':str(p),'kind':'declared-empty-source-output','sha256':None});continue
        if not p.is_file():raise RuntimeError(f'Missing official launch input: {p}')
        records.append({'path':str(p),'sha256':sha(p)})
    return {'command':[str(JAVA),*m['jvmArgs'],'-classpath',os.pathsep.join(m['classpath']),m['mainClass'],*m['args']],'workingDirectory':str(GAME),'environment':environment,'files':records,'mods':mods,'derivation':'Exact official ModDevGradle2.0.143 runClient main, combined actual classpath, JVM argument file, program argument file and explicit run environment; Gradle process is absent during game execution','accountArgumentsAdded':False,'resourceBounds':{'initialHeapMiB':256,'maxHeapMiB':1536,'activeProcessors':2}}

def resources():
    r={'utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'procSelfCgroup':pathlib.Path('/proc/self/cgroup').read_text()}
    for n in ['memory.max','memory.high','memory.current','memory.events','memory.events.local','memory.stat']:
        p=pathlib.Path('/sys/fs/cgroup')/n;r[n]=p.read_text() if p.exists() else None
    return r

def headroom_gate():
    r=resources();limit=int(r['memory.max']);current=int(r['memory.current'])
    stat={k:int(v) for k,v in (line.split() for line in r['memory.stat'].splitlines())}
    # Credit only clean inactive-file pages, never anon, shmem, active files or slab.
    reclaimable=max(0,stat.get('inactive_file',0)-stat.get('file_dirty',0)-stat.get('file_writeback',0))
    immediate=max(0,limit-current);budget=2048*1024*1024
    gate={'result':'PASS' if immediate+reclaimable>=budget else 'BLOCKED','requiredBytes':budget,'basis':'1536MiB configured Java heap plus512MiB conservative native/rendering overhead; only clean inactive-file credit','immediateHeadroomBytes':immediate,'cleanInactiveFileCreditBytes':reclaimable,'resources':r}
    target=SETUP/'evidence'/('headroom-gate-'+datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%S%f')+'.json')
    target.write_text(json.dumps(gate,indent=2)+'\n')
    if gate['result']!='PASS':raise RuntimeError(f'Headroom gate blocked: {immediate+reclaimable} bytes eligible, {budget} required; no game launched')
    return gate

def main():
    p=argparse.ArgumentParser();p.add_argument('--seal',action='store_true');p.add_argument('--launch',action='store_true');p.add_argument('--runtime-slot-approved',action='store_true');p.add_argument('--attempt',type=int);a=p.parse_args()
    d=derive()
    if a.seal:SEAL.write_text(json.dumps(d,indent=2)+'\n');print('Sealed official Unified development launch; no game started.');return
    if not(a.launch and a.runtime_slot_approved and a.attempt):raise SystemExit('Explicit launch, runtime-slot and attempt flags required')
    if json.loads(SEAL.read_text())!=d:raise RuntimeError('Sealed runtime changed')
    ps=subprocess.check_output(['ps','-eo','args'],text=True)
    if any('GradleDaemon' in l or 'GradleWrapperMain' in l for l in ps.splitlines()):raise RuntimeError('Wait for Gradle to exit')
    gate=headroom_gate()
    out=SETUP/f'evidence/client-{a.attempt}';out.mkdir(exist_ok=False)
    (out/'headroom-gate.json').write_text(json.dumps(gate,indent=2)+'\n')
    (out/'launch-derivation.json').write_text(json.dumps(d,indent=2)+'\n');(out/'resources-before.json').write_text(json.dumps(resources(),indent=2)+'\n')
    env=os.environ.copy();env.update(d['environment'])
    with (out/'launch.log').open('w') as f:
        proc=subprocess.Popen(d['command'],cwd=d['workingDirectory'],env=env,stdout=f,stderr=subprocess.STDOUT);(out/'pid.txt').write_text(str(proc.pid)+'\n');status=proc.wait()
    (out/'exit-status.txt').write_text(str(status)+'\n');(out/'resources-after.json').write_text(json.dumps(resources(),indent=2)+'\n')
    (out/'postlaunch-inputs.json').write_text(json.dumps(derive(),indent=2)+'\n')
    print(f'Unified client exited: {status}');raise SystemExit(status if status>=0 else 128-status)

if __name__=='__main__':main()
