#!/usr/bin/env python3
"""Serial cold CI orchestration. Preparation is Python/file work only."""
import argparse
import importlib.util
import json
import os
import signal
from pathlib import Path
import subprocess
import sys
import time
import source_materialize
import runtime_restore
import build_candidate
import compile_probe
import pair_assembly
import graphics_runner
import seal_pair
import bounded_process
import runner_dependencies

HERE=Path(__file__).resolve().parent
REPO='Nexa-MC/unified-infinity'
BRANCH='diagnostic/network-pair-20261006-a'
WORK_SECONDS=42*60
PAIR_SECONDS=650
PAIR_CLEANUP_SECONDS=30
STOP_SIGNALS=(signal.SIGTERM,signal.SIGINT,signal.SIGHUP)

def require(value,message):
    if not value:raise ValueError(message)

def restore_with_deadline(function,*args,deadline):
    """Bound synchronous download/hash restoration; no child process is inside."""
    require(deadline>time.monotonic(),'Overall deadline expired before restoration')
    def expired(_signal,_frame):raise RuntimeError('Overall restoration deadline expired')
    old=signal.signal(signal.SIGALRM,expired)
    signal.setitimer(signal.ITIMER_REAL,deadline-time.monotonic())
    try:return function(*args)
    finally:
        signal.setitimer(signal.ITIMER_REAL,0)
        signal.signal(signal.SIGALRM,old)

def write(path,value):
    require(not path.exists(),'Refusing overwrite: '+str(path));path.parent.mkdir(parents=True,exist_ok=True);path.write_text(json.dumps(value,indent=2)+'\n')

def prepare(repo,consumer):
    repo=Path(repo).resolve(strict=True);consumer=Path(consumer).absolute()
    source=source_materialize.prepare(repo,consumer)
    runtime=runtime_restore.prepare(repo,consumer)
    build=build_candidate.prepare(consumer)
    probe=compile_probe.prepare(repo,consumer)
    pair=pair_assembly.prepare(repo,consumer)
    graphics=graphics_runner.prepare(repo,consumer)
    result={'schema':1,'status':'COLD_DRIVER_PREPARED_EXECUTION_UNTESTED','repository':REPO,'branch':BRANCH,
            'repoRoot':str(repo),'consumerRoot':str(consumer),'source':source,'runtime':runtime,'build':build,
            'probe':probe,'pair':pair,'graphics':graphics,'downloadsStarted':False,'jvmStarted':False,'gameLaunched':False,
            'sourceCodeFiles':{p.name:compile_probe.record(p) for p in HERE.glob('*.py')},
            'dataFiles':{p.name:compile_probe.record(p) for p in HERE.glob('*lock.json')},
            'remainingExecutionObservations':['Actual installed runner graphics availability','All cold public downloads and fallback URL availability','Installer/ModDev outputs and full candidate build','Real native/Unified distinct-process roundtrip']}
    write(consumer/'cold-driver-plan.json',result)
    return result

def source_module(name,path):
    spec=importlib.util.spec_from_file_location(name,path);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m

def restore_additional(consumer,plan):
    api=consumer/'work/api1';support=api/'ci/runtime-restore';downloader=source_module('verified_cold_downloader',support/'restore_inputs.py')
    runtime_lock=json.loads((support/'input-lock.json').read_text())
    seen={row['sha256']:api/row['path'] for row in runtime_lock['artifacts'] if 'sha256' in row}
    results=[]
    for filename,dest in [('core-dependency-lock.json',api),('product-input-lock.json',api),('original-mod-lock.json',consumer)]:
        path=HERE/filename;require(compile_probe.record(path)==plan['dataFiles'][filename],'Supplemental lock changed')
        lock=json.loads(path.read_text())
        for index,row in enumerate(lock['artifacts'],1):
            target=downloader.destination(dest,row['path'])
            source=seen.get(row['sha256'])
            if target.exists():downloader.validate(target,row)
            elif source and source.exists():
                downloader.validate(source,row);target.parent.mkdir(parents=True,exist_ok=True)
                import shutil
                shutil.copyfile(source,target);downloader.validate(target,row)
            else:downloader.restore(dest,row,set(lock['allowedHosts']))
            seen[row['sha256']]=target;results.append(compile_probe.record(target))
            if index%64==0 or index==len(lock['artifacts']):print('ADDITIONAL_INPUTS_VERIFIED '+filename+' '+str(index)+'/'+str(len(lock['artifacts'])),flush=True)
    write(consumer/'cold-additional-inputs.json',{'schema':1,'status':'EXACT_ADDITIONAL_INPUTS_VERIFIED','files':results,'gameLaunched':False})

def execute_step(consumer,step,deadline):
    root=consumer/'cold-runtime-evidence';root.mkdir(exist_ok=True);log=root/(step['name']+'.log')
    require(not log.exists(),'Repeated runtime preparation step')
    timeout=min(step['timeoutSeconds'],max(1,deadline-time.monotonic()))
    print('COLD_STEP_START '+step['name'],flush=True)
    with log.open('w') as stream:
        result=bounded_process.run(step['command'],cwd=step['cwd'],env=step['environment'],stdout=stream,stderr=subprocess.STDOUT,timeout=timeout)
    receipt={'schema':1,'name':step['name'],'exitCode':result.returncode,'status':'PASS' if result.returncode==0 else 'FAILED',
             'command':step['command'],'log':compile_probe.record(log),'gameLaunched':False}
    write(root/(step['name']+'.json'),receipt)
    if result.returncode!=0:print(log.read_text(errors='replace')[-48000:],flush=True)
    require(result.returncode==0,'Official preparation failed; see '+str(log))
    print('COLD_STEP_PASS '+step['name'],flush=True)

def semantic_comparison(reports):
    # Each untouched supervisor independently enforces exact nonce/direction,
    # socket, PID, thread, counter, disconnect and save invariants.
    require(set(reports)=={'native-neoforge','unified'},'Missing paired control')
    for target,report in reports.items():require(report.get('passed') is True and report.get('status')=='PASS','No actual runtime acceptance: '+target)
    return {'schema':1,'status':'BOTH_HOST_NONCE_CONTROLS_PASSED','nativePass':True,'unifiedPass':True,
            'sameProbeSha256':compile_probe.REFERENCE_JAR_SHA,'target':'Actual NeoForge host typed PLAY nonce roundtrip in distinct processes',
            'guiAcceptance':False,'qslForgeFacadeWireAcceptance':False,'fullApiCompatibility':False}

class DriverInterrupted(RuntimeError):
    pass


def interrupt_driver(number,_frame):
    raise DriverInterrupted('Cold driver interrupted by '+signal.Signals(number).name)


def cleanup_pair(active):
    """Only the retained Popen child may be signalled; never trust receipt PIDs."""
    if active is None:
        return {'status':'NO_ACTIVE_PAIR','reaped':True}
    result={'status':'PAIR_CLEANUP_FAILED','target':active['target'],'reaped':False}
    process=active['process']
    try:
        if process.poll() is None:
            process.terminate()  # The supervisor performs its own game cleanup.
        result.update(status='PAIR_SUPERVISOR_REAPED',reaped=True,
                      exitCode=process.wait(timeout=PAIR_CLEANUP_SECONDS))
    except BaseException as error:
        result['failure']=type(error).__name__+': '+str(error)
    return result


def execute(repo,consumer,allow_runner_package=False):
    require(os.environ.get('GITHUB_ACTIONS')=='true' and os.environ.get('GITHUB_REPOSITORY')==REPO
            and os.environ.get('GITHUB_REF')=='refs/heads/'+BRANCH and os.environ.get('GITHUB_EVENT_NAME')=='push',
            'Execution requires the separately reviewed exact future pair branch; no alternative publication route')
    require(os.getuid()!=0,'Unprivileged standard runner required')
    repo=Path(repo).resolve(strict=True);consumer=Path(consumer).resolve(strict=True)
    plan=json.loads((consumer/'cold-driver-plan.json').read_text())
    require(plan['repoRoot']==str(repo) and plan['consumerRoot']==str(consumer),'Consumer plan belongs elsewhere')
    for row in [*plan['sourceCodeFiles'].values(),*plan['dataFiles'].values()]:require(compile_probe.record(Path(row['path']))==row,'Cold source/lock changed after preparation')
    deadline=time.monotonic()+WORK_SECONDS;handle=None;active_pair=None;primary_error=None;previous={}
    result={'schema':1,'status':'INCOMPLETE','gameAcceptance':False,'reports':{}}
    spawning_pair=False;starting_graphics=False;cleaning_up=False;pending_stops=[]
    def stop_driver(number,frame):
        nonlocal cleaning_up
        # Return during Popen so ownership can be retained before unwinding.
        # Do not block OS signals: children would inherit that blocked mask.
        if spawning_pair or starting_graphics or cleaning_up:pending_stops.append(number)
        else:
            cleaning_up=True
            interrupt_driver(number,frame)
    def check_stops():
        nonlocal cleaning_up
        if pending_stops:
            cleaning_up=True
            interrupt_driver(pending_stops[0],None)
    try:
        for number in STOP_SIGNALS:previous[number]=signal.signal(number,stop_driver)
        if allow_runner_package:
            runner_dependencies.ensure(plan['graphics'],consumer,deadline,allow_install=True)
        availability=graphics_runner.availability(plan['graphics']);write(consumer/'graphics-availability.json',availability)
        require(not availability['missingInputs'],'Required installed runner graphics unavailable before downloads: '+json.dumps(availability['missingInputs']))
        print('RESTORE_START: pinned official runtime, assets and toolchain bytes',flush=True)
        restore_with_deadline(runtime_restore.restore,consumer/'work/api1',deadline=deadline)
        restore_with_deadline(restore_additional,consumer,plan,deadline=deadline)
        for step in plan['runtime']['steps']:
            require(time.monotonic()<deadline,'Cold job deadline exceeded')
            execute_step(consumer,step,deadline)
        runtime_restore.verify(consumer/'work/api1')
        print('SOURCE_BUILD_START',flush=True);build_candidate.execute(consumer,deadline=deadline)
        print('PROBE_COMPILE_START',flush=True);compile_probe.execute(consumer,deadline=deadline)
        pair_assembly.assemble(repo,consumer,offline_identity_reference='Isolated localhost tests with virtual APILocal identity',eula_reference='Existing Minecraft EULA acceptance for isolated local tests')
        require(time.monotonic()<deadline,'Cold job deadline exceeded before graphics')
        # Keep stop signals deferred through collector creation and the return
        # handoff. The runner checks pending stops only while cleanup owns it.
        starting_graphics=True
        try:
            graphics=graphics_runner.execute(plan['graphics'],deadline=deadline,interrupt_check=check_stops)
            handle=graphics.get('handle')
        finally:
            starting_graphics=False
        check_stops()
        require(graphics['status']=='GRAPHICS_PREFLIGHT_READY','Graphics did not produce real readiness: '+str(graphics.get('missingInputs')))
        reports={}
        for target in ('native-neoforge','unified'):
            require(time.monotonic()<deadline,'Cold job deadline exceeded before pair')
            sealed=seal_pair.create(repo,consumer,target,graphics['readyPath'],'Isolated native/Unified nonce diagnostic; publication approval tracked separately')
            evidence=consumer/'runtime-evidence'/target;evidence.parent.mkdir(exist_ok=True)
            args=[sys.executable,sealed['supervisor']['path'],'--spec',sealed['spec']['path'],'--sha256',sealed['spec']['sha256'],'--execute-reviewed-ci-pair','--destination',str(evidence)]
            print('ACTUAL_PAIR_START '+target,flush=True)
            # Defer stop signals across spawn/ownership assignment, so a signal
            # cannot strand a newly created child before finally can identify it.
            spawning_pair=True
            try:
                call=subprocess.Popen(args,cwd=consumer)
                active_pair={'process':call,'target':target}
            finally:
                spawning_pair=False
            if pending_stops:interrupt_driver(pending_stops[0],None)
            try:
                code=call.wait(timeout=min(PAIR_SECONDS,max(1,deadline-time.monotonic())))
            except subprocess.TimeoutExpired as error:
                raise RuntimeError('Pair time budget exhausted; owned supervisor cleanup required') from error
            active_pair=None  # wait reaped this owned supervisor before the next pair.
            report_path=evidence/'result.json'
            if report_path.exists():
                reports[target]=json.loads(report_path.read_text());result['reports'][target]=compile_probe.record(report_path)
                print('ACTUAL_PAIR_RECEIPT '+target+' '+report_path.read_text()[:256000],flush=True)
            for role in ('server','client'):
                log=evidence/(role+'.log')
                if log.exists():print('ACTUAL_PAIR_LOG '+target+' '+role+'\n'+log.read_text(errors='replace')[-32000:],flush=True)
            require(code==0,'Actual pair failed: '+target)
        result.update(semantic_comparison(reports),gameAcceptance=True)
        cleaning_up=True
    except BaseException as error:
        cleaning_up=True
        primary_error=error
        result.update(status='FAILED',gameAcceptance=False,failure=type(error).__name__+': '+str(error))
        if hasattr(error,'graphics_cleanup'):result['graphicsCleanup']=error.graphics_cleanup
        raise
    finally:
        cleaning_up=True
        # Repeated termination requests must not interrupt ordered cleanup or the
        # final failure receipt. Restore the caller's handlers after reporting.
        for number in previous:signal.signal(number,signal.SIG_IGN)
        try:
            errors=[]
            result['pairCleanup']=cleanup_pair(active_pair)
            if not result['pairCleanup']['reaped']:
                errors.append({'component':'pair',**result['pairCleanup']})
            if handle is not None:
                if not result['pairCleanup']['reaped']:
                    # Keep the display available to a supervisor still cleaning
                    # its games. Do not hard-kill it or infer child PIDs.
                    result['graphicsCleanup']={'status':'SKIPPED_PAIR_NOT_REAPED'}
                else:
                    try:result['graphicsCleanup']=graphics_runner.stop(handle)
                    except BaseException as error:
                        result['graphicsCleanup']={'status':'GRAPHICS_CLEANUP_FAILED',
                                                   'failure':type(error).__name__+': '+str(error)}
            if result.get('graphicsCleanup',{}).get('status')=='GRAPHICS_CLEANUP_FAILED':
                errors.append({'component':'graphics',**result['graphicsCleanup']})
            if errors:
                result.update(cleanupErrors=errors,gameAcceptance=False)
                if primary_error is None:result['status']='CLEANUP_FAILED'
            write(consumer/'cold-pair-result.json',result)
            print(json.dumps(result,sort_keys=True),flush=True)
            summary=os.environ.get('GITHUB_STEP_SUMMARY')
            if summary:
                try:
                    with open(summary,'a') as stream:stream.write('Native/Unified nonce diagnostic: '+result['status']+'\n\nOnly actual independently asserted host transport results count. GUI and QSL/Forge facade wire compatibility remain separate.\n')
                except OSError as error:
                    print('STEP_SUMMARY_FAILED '+str(error),file=sys.stderr,flush=True)
        finally:
            for number,handler in previous.items():signal.signal(number,handler)
    if result.get('cleanupErrors'):
        raise RuntimeError('Owned process cleanup failed; see cold-pair-result.json')
    return result

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('action',choices=['prepare','run']);p.add_argument('--repo-root',type=Path,required=True);p.add_argument('--consumer',type=Path,required=True);p.add_argument('--install-reviewed-runner-package',action='store_true');a=p.parse_args()
    value=prepare(a.repo_root,a.consumer) if a.action=='prepare' else execute(a.repo_root,a.consumer,a.install_reviewed_runner_package)
    print(json.dumps({'status':value['status'],'consumerRoot':str(a.consumer),'gameExecuted':a.action=='run'},indent=2))
