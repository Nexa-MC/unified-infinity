#!/usr/bin/env python3
"""Replay exact official Loom IDE-style DLI inputs, after Gradle has exited."""
import argparse, datetime, hashlib, json, os, pathlib, shlex, subprocess, sys
from verify_profile import ROOT, PROFILE, checked, digest, verify_mods, verify_runtime
SETUP=ROOT/'four-loader/quilt-native-client'
JAVA=ROOT/'.toolchains/jdk-21.0.12.1+1/bin/java'
SEAL=PROFILE/'direct-launch-seal.json'

def derive(capture=False):
    verify_mods();validation=verify_runtime()
    p=PROFILE/'client-launch-inputs.json';m=json.loads(p.read_text())
    if pathlib.Path(m['gameDirectory']).resolve()!=(PROFILE/'game').resolve():raise RuntimeError('Unexpected game directory')
    if m['args']:raise RuntimeError('Unexpected custom program arguments')
    cp=os.pathsep.join(e['path'] for e in m['classpath'])
    at=[a[1:] for a in m['jvmArgs'] if a.startswith('@')]
    if len(at)!=1:raise RuntimeError('Expected one official Loom classpath argfile')
    captured=PROFILE/'official-loom-classpath.args'
    capture_record=PROFILE/'official-loom-classpath-origin.json'
    if capture:
        raw=pathlib.Path(at[0]).read_bytes()
        if shlex.split(raw.decode())!=['-classpath',cp]:raise RuntimeError('Official argfile differs from resolved classpath')
        captured.write_bytes(raw)
        capture_record.write_text(json.dumps({'originalTemporaryPath':at[0],'capturedPath':str(captured),'sha256':hashlib.sha256(raw).hexdigest()},indent=2)+'\n')
    origin=json.loads(capture_record.read_text())
    if origin['originalTemporaryPath']!=at[0]:raise RuntimeError('Captured argfile belongs to a different official preparation')
    checked(captured,origin['sha256'])
    if shlex.split(captured.read_text())!=['-classpath',cp]:raise RuntimeError('Captured official argfile differs from resolved classpath')
    args=[a for a in m['jvmArgs'] if not a.startswith('@')]
    expected={
        '-Dfabric.dli.config='+str(SETUP/'development/.gradle/quilt-loom-cache/launch.cfg'),
        '-Dfabric.dli.env=client','-Dfabric.dli.main=org.quiltmc.loader.impl.launch.knot.KnotClient',
        '-Xms256M','-Xmx1536M','-XX:ActiveProcessorCount=2',
    }
    if set(args)!=expected or len(args)!=len(expected):raise RuntimeError(f'Unexpected generated JVM arguments: {args}')
    cmd=[str(JAVA),*args,'-classpath',cp,m['mainClass'],*m['args']]
    return {'command':cmd,'workingDirectory':m['gameDirectory'],'manifestSha256':digest(p),'javaSha256':digest(JAVA),'officialClasspathArgfile':origin,'launchConfigSha256':validation['launchConfigSha256'],'runtimeValidation':validation,'derivation':'Exact official Quilt Loom runClient classpath and generated JVM/program arguments; only the temporary @classpath file is represented directly as -classpath, as in an IDE launch','accountArgumentsAdded':False}

def resources():
    result={'utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'procSelfCgroup':pathlib.Path('/proc/self/cgroup').read_text()}
    for name in ['memory.max','memory.high','memory.current','memory.events','memory.events.local']:
        p=pathlib.Path('/sys/fs/cgroup')/name;result[name]=p.read_text() if p.exists() else None
    return result

def main():
    p=argparse.ArgumentParser();p.add_argument('--seal',action='store_true');p.add_argument('--launch',action='store_true');p.add_argument('--runtime-slot-approved',action='store_true');p.add_argument('--attempt',type=int);a=p.parse_args()
    if a.seal:
        d=derive(capture=True);SEAL.write_text(json.dumps(d,indent=2)+'\n');print('Sealed exact official Loom IDE-style client launch; no game launched.');return
    if not(a.launch and a.runtime_slot_approved and a.attempt):raise SystemExit('Explicit --launch --runtime-slot-approved --attempt required')
    sealed=json.loads(SEAL.read_text());derived=derive()
    if sealed!=derived:raise RuntimeError('Generated developer launch changed after sealing')
    # Only a read-only process inventory: fail closed if a Gradle JVM remains.
    processes=subprocess.check_output(['ps','-eo','args'],text=True)
    if any('GradleDaemon' in line or 'GradleWrapperMain' in line for line in processes.splitlines()):raise RuntimeError('A Gradle JVM is still running; wait for its exit')
    out=SETUP/f'logs/client-{a.attempt}';out.mkdir(exist_ok=False)
    (out/'direct-launch-derivation.json').write_text(json.dumps(derived,indent=2)+'\n')
    (out/'resources-before.json').write_text(json.dumps(resources(),indent=2)+'\n')
    with (out/'launch.log').open('w') as f:
        proc=subprocess.Popen(derived['command'],cwd=derived['workingDirectory'],stdout=f,stderr=subprocess.STDOUT)
        (out/'pid.txt').write_text(str(proc.pid)+'\n');status=proc.wait()
    (out/'resources-after.json').write_text(json.dumps(resources(),indent=2)+'\n')
    (out/'exit-status.txt').write_text(str(status)+'\n')
    (out/'postlaunch-verification.json').write_text(json.dumps(verify_runtime(),indent=2)+'\n')
    print(f'Native client exited: {status}');raise SystemExit(status if status>=0 else 128-status)

if __name__=='__main__':main()
