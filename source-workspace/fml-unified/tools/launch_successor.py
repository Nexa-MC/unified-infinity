#!/usr/bin/env python3
"""Validate and launch the isolated source-fused successor; default mode never starts Java."""
import argparse,fcntl,importlib.util,json,os,pathlib,subprocess,time
HERE=pathlib.Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('assembler',HERE/'assemble_installation.py');a=importlib.util.module_from_spec(spec);spec.loader.exec_module(a)
environment_spec=importlib.util.spec_from_file_location('game_environment',HERE.parents[2]/'four-loader/launch-support/game_environment.py')
game_environment=importlib.util.module_from_spec(environment_spec);environment_spec.loader.exec_module(game_environment)

def live_jvms():
    result=[]
    for proc in pathlib.Path('/proc').glob('[0-9]*'):
        try:
            name=(proc/'comm').read_text().strip();stat=(proc/'stat').read_text();state=stat[stat.rfind(')')+2:].split()[0]
            rss=int((proc/'statm').read_text().split()[1])*os.sysconf('SC_PAGE_SIZE')
            if name in ('java','javac') and state!='Z' and rss>0:result.append({'pid':int(proc.name),'state':state,'rssBytes':rss})
        except (OSError,ValueError,IndexError):continue
    return result
def headroom(required):
    root=pathlib.Path('/sys/fs/cgroup')
    # Native target exposes its actual cgroup at this mount root; absent/unbounded values never pass.
    maximum=(root/'memory.max').read_text().strip()
    if maximum=='max':raise RuntimeError('Unbounded/missing cgroup cannot establish launch budget')
    current=int((root/'memory.current').read_text());maximum=int(maximum)
    stat=dict(line.split() for line in (root/'memory.stat').read_text().splitlines())
    immediate=max(0,maximum-current)
    credit=max(0,int(stat.get('inactive_file',0))-int(stat.get('file_dirty',0))-int(stat.get('file_writeback',0)))
    return {'maximumBytes':maximum,'currentBytes':current,'immediateBytes':immediate,'inactiveCleanFileCreditBytes':credit,'eligibleBytes':immediate+credit,'requiredBytes':required,'passed':immediate+credit>=required}
def main():
    parser=argparse.ArgumentParser();parser.add_argument('--spec',type=pathlib.Path,required=True);parser.add_argument('--expected-spec-sha256',required=True);parser.add_argument('--receipt',type=pathlib.Path,required=True);parser.add_argument('--expected-receipt-sha256',required=True);parser.add_argument('--execute',action='store_true');args=parser.parse_args()
    plan=a.load_pinned(args.spec,args.expected_spec_sha256);policy,java_args,java=a.prepare(plan)
    game=pathlib.Path(policy['gameDirectory']);env=game_environment.build_game_environment(os.environ,game,pathlib.Path(java).parent.parent,{})
    game_environment.create_private_environment_directories(game)
    verified=a.v.validate(args.receipt,args.expected_receipt_sha256,java_args,env)
    expected={pathlib.Path(row['path']).resolve():row['sha256'] for row in plan['userMods']}
    if len(expected) != len(plan['userMods']):raise RuntimeError('Duplicate approved user-mod path')
    # These copies are sealed test inputs only, never installed/trusted admission artifacts.
    # Their expected decision must still be established independently by the real BOOT scanner.
    untrusted_inputs=plan.get('expectedExcludedInputs',[])
    trusted_paths={(pathlib.Path(policy['installationDirectory'])/row['path']).resolve() for row in policy['artifacts']}
    for row in untrusted_inputs:
        original=pathlib.Path(row['path']);path=original.resolve()
        if row.get('expectedAction')!='EXCLUDE' or original.is_symlink() or path.parent!=game/'mods' or path in expected or path in trusted_paths:
            raise RuntimeError('Expected exclusion must be a distinct untrusted mods-folder input')
        if a.v.sha(pathlib.Path(row['source']))!=row['sha256']:raise RuntimeError('Expected-excluded original source changed')
        expected[path]=row['sha256']
    for artifact in policy['artifacts']:
        path=(pathlib.Path(policy['installationDirectory'])/artifact['path']).resolve()
        if path.parent==game/'mods':expected[path]=artifact['sha256']
    actual={p.resolve() for p in (game/'mods').iterdir() if p.suffix.lower()=='.jar'}
    if actual!=set(expected):raise RuntimeError('Successor mods folder differs from the exact approved input set')
    for path,digest in expected.items():
        if path.is_symlink() or a.v.sha(path)!=digest:raise RuntimeError('Original/staged mod input changed')
    for row in plan['userMods']:
        if a.v.sha(pathlib.Path(row['source']))!=row['sha256']:raise RuntimeError('Original user mod source changed')
    verified.update({'policyId':policy['policyId'],'gameDirectory':str(game),'userModCount':len(plan['userMods']),'expectedExcludedInputCount':len(untrusted_inputs),'modsFolderArchiveCount':len(actual),'minimalEnvironment':True,'rawArgumentsLogged':False,'executeRequested':args.execute,'heapMiB':plan.get('heapMiB',1536),'firstLaunchOnly':plan.get('firstLaunchOnly',False),'environmentPolicy':game_environment.public_policy_descriptor()['version']})
    print(json.dumps(verified,sort_keys=True),flush=True)
    if not args.execute:return
    with (game/'launch.lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        if plan.get('firstLaunchOnly') and (game/'launch-session.json').exists():raise RuntimeError('First-launch smoke attempt already recorded; inspect it before preparing another seal')
        running=live_jvms();memory=headroom(int(plan.get('memoryGateBytes',2048*1024*1024)))
        gate={'timestamp':time.time(),'liveJvms':running,'memory':memory};(game/'last-launch-gate.json').write_text(json.dumps(gate,indent=2)+'\n')
        print(json.dumps(gate,sort_keys=True),flush=True)
        if running or not memory['passed']:raise RuntimeError('Native JVM/headroom gate did not pass; no game was started')
        # All expensive hashing precedes this immediately adjacent memory gate and spawn.
        with (game/'fusion-client.log').open('w') as log:
            process=subprocess.Popen([java,*java_args],cwd=game,env=env,stdout=log,stderr=subprocess.STDOUT)
            session={'pid':process.pid,'startedUtcEpoch':time.time(),'receiptSha256':args.expected_receipt_sha256,'artifactSha256':verified['artifactSha256'],'argumentsSha256':verified['argumentsSha256'],'gameDirectory':str(game),'progressFile':str(game/'compat-progress.json'),'log':str(game/'fusion-client.log')}
            (game/'launch-session.json').write_text(json.dumps(session,indent=2)+'\n');print(json.dumps(session),flush=True)
            code=process.wait()
            recheck=dict(expected)
            for row in [*plan['userMods'],*untrusted_inputs]:recheck[pathlib.Path(row['source'])]=row['sha256']
            unchanged=True
            for path,digest in recheck.items():
                try:unchanged=unchanged and a.v.sha(path)==digest
                except OSError:unchanged=False
            session.update(exitCode=code,finishedUtcEpoch=time.time(),originalInputsUnchanged=unchanged,checkedInputPaths=len(recheck))
            (game/'launch-session.json').write_text(json.dumps(session,indent=2)+'\n');print(json.dumps({'exitCode':code,'log':session['log'],'originalInputsUnchanged':unchanged}),flush=True)
            raise SystemExit(code if unchanged else 1)
if __name__=='__main__':main()
