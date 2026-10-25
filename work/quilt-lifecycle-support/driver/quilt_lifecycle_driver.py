#!/usr/bin/env python3
"""Separately named QSL create/reopen source candidate; never original acceptance.

The original 21:09 driver, dependency locks, supervisor and round are untouched.
Only an independently reviewed source contract and the original fixed-round gate
can admit execution. This file does not select or renew a future recovery round.
"""
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time

HERE = Path(__file__).resolve().parent
ORIGINAL_DRIVER_SHA256 = '8b38fc5925168811670365a6ec95a8cadc7ddf6288a54fa33019b25def80216e'
CONTINUATION_SHA256 = 'cc6378e0b5dfc9433fdfccf1f5e8da45cd56a299912be1e229ac6b86aa93471f'
QUALIFIER_SHA256 = '1abca1a1b7cfe34f6d49aafd62ea0dbaaeb706d88bc10a3c887e08a4dd476045'
STAGING_SHA256 = '6ddc65d700e41340385e80d80ef5a7b025294224f31af4bacf86b181c5d9c825'
REPO='Nexa-MC/unified-infinity'
BRANCH='diagnostic/network-pair-20261006-a'
WORK_SECONDS=42*60
PAIR_SECONDS=650
PAIR_CLEANUP_SECONDS=30
STOP_SIGNALS=(signal.SIGTERM,signal.SIGINT,signal.SIGHUP)
SUPPORT='work/quilt-lifecycle-support'
# Exact tool owner selected by the unchanged diagnostic_pair_assembly producer.
# The separate logging-fix source project legitimately seals identical copies.
ORIGINAL_ASSEMBLY_TOOLS='work/api1/source-workspace/fml-unified/tools'
MODULE_PATHS={'pipeline':'pipeline/quilt_compile_pipeline.py','staging':'staging/quilt_lifecycle_staging.py',
              'sealer':'staging/quilt_phase_seal.py','continuation':'continuation/quilt_continuation.py',
              'qualifier':'qualification/quilt_lifecycle_qualification.py'}
COPIED_LOCKS=('runtime-inputs.lock.json','profiles/ffapi-core-dependency-lock.json','product-input-lock.json')
SOURCE_MEMBERS=('README.md','build.py','build/build-report.json','resources/infinity_native_quilt_probe.mixins.json',
    'resources/native-quilt-proof.txt','resources/quilt.mod.json','src/dev/infinity/quiltprobe/ClientProbe.java',
    'src/dev/infinity/quiltprobe/QuiltProbe.java','src/dev/infinity/quiltprobe/mixin/TickMixin.java')
COMPILE_MEMBERS=('build_recovery.py','RemapServer.java','AbiCheck.java','build_portable.py',
    'validate_portable.py','portable_io.py','reviewed-contract.json','validate_for_consumer.py')
SOURCE_DESTINATIONS=set(MODULE_PATHS.values())|{
    'driver/quilt_lifecycle_driver.py','continuation/owned_pair_run.py','source/source-recovery.json',
    'sources/accepted-v6-reconstruction-base.zip','sources/jdk-input-verification.json',
    'original/supervisor.py','original/finalize_pair.py','original/prepare_inputs.py'}|{
    'compile/'+name for name in COMPILE_MEMBERS}|{'source/four-loader/quilt-probe/'+name for name in SOURCE_MEMBERS}
FLAGS={'diagnostic_only':True,'baselineAcceptance':False,'gameAcceptance':False,
       'fullApiCompatibility':False,'qslNetworkAcceptance':False,
       'guiAcceptance':False,'qslForgeFacadeWireAcceptance':False}

def require(value,message):
    if not value:raise ValueError(message)

def profile_options(profile=None,build_proof=None):
    """Select only the reviewed portable profile, never infer it from artifacts."""
    if profile is None and build_proof is None:return {}
    require(profile is not None and build_proof is not None,
            'Refreshed execution requires both --profile and --build-proof')
    import refreshed_candidate
    import ffapi_sources
    require(str(profile)==refreshed_candidate.PROFILE_PATH==ffapi_sources.PROFILE_REL,
            'Only the exact bundled consumer-relative refreshed profile is supported')
    require(str(build_proof)==refreshed_candidate.PROOF_PATH,
            'The explicit build proof must name the fresh refreshed build output')
    return {'profile':str(profile),'build_proof':str(build_proof)}

def refreshed_binding(consumer,options):
    """Bind source-only preparation; this does not validate a completed build."""
    import refreshed_candidate
    import ffapi_sources
    profile=refreshed_candidate.load_profile(consumer,options['profile'])
    source=ffapi_sources.verify_sources(consumer)
    require(source['candidate_identity']==profile['coreIdentity'],
            'Refreshed source preparation belongs to another identity')
    require(source['ffapiInputsSha256']==profile['ffapiDelta']['sha256'],
            'Refreshed source preparation belongs to another scoped input manifest')
    return {'profile':refreshed_candidate.pin(consumer,options['profile']),
            'buildProofPath':options['build_proof'],'sourceIdentity':profile['coreIdentity'],
            'ffapiInputsSha256':source['ffapiInputsSha256']}

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

def source_module(name,path):
    spec=importlib.util.spec_from_file_location(name,path);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m

def execute_step(consumer,step,deadline,refreshed=False,diagnostic=False):
    root=driver_paths(consumer,refreshed,diagnostic)['runtime'];root.mkdir(exist_ok=True);log=root/(step['name']+'.log')
    require(not log.exists(),'Repeated runtime preparation step')
    remaining=deadline-time.monotonic()
    require(remaining>0,'Cold job deadline expired before runtime command')
    timeout=min(step['timeoutSeconds'],remaining)
    print('COLD_STEP_START '+step['name'],flush=True)
    with log.open('w') as stream:
        result=bounded_process.run(step['command'],cwd=step['cwd'],env=step['environment'],stdout=stream,stderr=subprocess.STDOUT,timeout=timeout)
    receipt={'schema':1,'name':step['name'],'exitCode':result.returncode,'status':'PASS' if result.returncode==0 else 'FAILED',
             'command':step['command'],'log':compile_probe.record(log),'gameLaunched':False}
    write(root/(step['name']+'.json'),receipt)
    if result.returncode!=0:
        print(log.read_text(errors='replace')[-48000:],flush=True)
        # The failed exporter and all owned descendants have already exited.
        # Print the bounded diagnostic after the tail so it cannot be lost from
        # that tail; retain the original nonzero result and strict rejection.
        if step['name']=='export-official-client':
            try:generated_output_diagnostics.emit(consumer,deadline)
            except Exception as error:
                print('GENERATED_OUTPUT_DIAGNOSTIC_ERROR '+json.dumps({
                    'status':'DIAGNOSTIC_COLLECTION_FAILED','errorType':type(error).__name__}),flush=True)
    require(result.returncode==0,'Official preparation failed; see '+str(log))
    print('COLD_STEP_PASS '+step['name'],flush=True)

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

def work_budget(work_seconds=None):
    """Only narrow the historical work limit; cleanup remains separately bounded."""
    if work_seconds is None:return WORK_SECONDS
    require(type(work_seconds) is int and 1<=work_seconds<=WORK_SECONDS,
            '--work-seconds must be an integer between 1 and '+str(WORK_SECONDS))
    return work_seconds

def record(path):
    path=Path(path).absolute()
    require(path.resolve()==path and all(not p.is_symlink() for p in (path,*path.parents)),
            'Canonical source file required')
    before=path.stat();require(path.is_file() and before.st_nlink==1,'Regular unaliased source required')
    digest=hashlib.sha256(path.read_bytes()).hexdigest();after=path.stat()
    require((before.st_dev,before.st_ino,before.st_size,before.st_mtime_ns,before.st_ctime_ns)==
            (after.st_dev,after.st_ino,after.st_size,after.st_mtime_ns,after.st_ctime_ns),'Input changed during read')
    return {'path':str(path),'bytes':after.st_size,'sha256':digest}


def configure(repo):
    """Load the frozen original; no mutation of its globals or source files."""
    global seed_driver,compile_probe,bounded_process,generated_output_diagnostics,round_deadline
    global runtime_restore,build_candidate,pair_assembly,graphics_runner,seal_pair,runner_dependencies
    path=Path(repo)/'work/network-pair-cold-glue/driver.py'
    require(record(path)['sha256']==ORIGINAL_DRIVER_SHA256,'Original driver changed')
    sys.path.insert(0,str(path.parent))
    seed_driver=source_module('quilt_unchanged_seed_driver',path)
    for name in ('compile_probe','bounded_process','generated_output_diagnostics','round_deadline',
                 'runtime_restore','build_candidate','pair_assembly','graphics_runner','seal_pair','runner_dependencies'):
        globals()[name]=getattr(seed_driver,name)
    return seed_driver


def driver_paths(consumer,refreshed=False,diagnostic=False):
    root=Path(consumer)
    return {key:root/name for key,name in {
        'plan':'quilt-lifecycle-driver-plan.json','result':'quilt-lifecycle-result.json',
        'evidence':'runtime-evidence-quilt-lifecycle','runtime':'quilt-lifecycle-runtime-evidence',
        'graphics':'graphics-availability-quilt-lifecycle.json',
        'additional':'quilt-lifecycle-additional-inputs.json'}.items()}


def portable(root,row):
    path=Path(row['path']);require(path.is_relative_to(root),'Pin leaves caller consumer')
    return dict(row,path=path.relative_to(root).as_posix())


def absolute(root,row):
    path=Path(row['path']);require(not path.is_absolute() and '..' not in path.parts,'Portable pin required')
    result=dict(row,path=str(root/path));require(record(root/path)==result,'Portable pin changed')
    return result


def load_json(path):
    def pairs(items):
        result={}
        for key,value in items:
            require(key not in result,'Duplicate JSON key');result[key]=value
        return result
    return json.loads(Path(path).read_text(),object_pairs_hook=pairs)


def check_contract(contract,expected):
    require(record(contract)['sha256']==expected,'Explicit independently reviewed source contract hash required')
    value=load_json(contract)
    require(set(value)=={'schema','status','files','baselineAcceptance','gameAcceptance','fullApiCompatibility'}
            and value['schema']=='quilt-lifecycle-driver-source-contract-v1'
            and value['status']=='SOURCE_ONLY_CANDIDATE_NOT_EXECUTION_APPROVAL'
            and all(value[key] is False for key in ('baselineAcceptance','gameAcceptance','fullApiCompatibility')),
            'Source contract is not runtime approval')
    require(type(value['files']) is list and 15<=len(value['files'])<=64,'Bounded exact source contract required')
    seen=set()
    for row in value['files']:
        require(set(row)=={'source','destination','bytes','sha256'},'Exact source copy pin required')
        for key in ('source','destination'):
            p=Path(row[key]);require(not p.is_absolute() and '..' not in p.parts and p.as_posix()==row[key],
                                    'Canonical relative source path required')
        require(row['destination'] not in seen,'Duplicate source destination');seen.add(row['destination'])
    require(seen==SOURCE_DESTINATIONS,'Exact reviewed source destinations required; missing, extra or reserved destination refused')
    return value


def compile_layout():
    return {'schema':'quilt-compile-pipeline-layout-v1','paths':{
        'source_archive':SUPPORT+'/sources/accepted-v6-reconstruction-base.zip',
        'source_manifest':SUPPORT+'/source/source-recovery.json',
        'jdk_manifest':SUPPORT+'/sources/jdk-input-verification.json',
        'jdk_root':'work/api1/.toolchains/jdk-21.0.12.1+1',
        'compile_tools':SUPPORT+'/compile','staging_tool':SUPPORT+'/staging/quilt_lifecycle_staging.py',
        'lock_root':'work/network-pair-cold-glue','api_root':'work/api1'},'dependency_paths':{}}


def prepare(repo,consumer,*,profile,build_proof,support_source,source_contract,source_contract_sha256):
    repo=Path(repo).resolve(strict=True);consumer=Path(consumer).absolute()
    original=configure(repo);options=profile_options(profile,build_proof)
    require(options,'QSL lifecycle requires the exact refreshed candidate')
    source_contract=Path(source_contract).resolve(strict=True)
    contract=check_contract(source_contract,source_contract_sha256)
    source=Path(support_source).resolve(strict=True)
    payloads=[]
    for row in contract['files']:
        path=source/row['source'];pin=record(path)
        require(pin['bytes']==row['bytes'] and pin['sha256']==row['sha256'],'Source contract file changed')
        payloads.append((row,path.read_bytes(),pin))
    # The original source-only preparation remains unchanged. Its native/Fabric
    # profiles are pristine seed inputs, never targets of this driver's loop.
    seed=original.prepare(repo,consumer,profile=profile,build_proof=build_proof,
                          diagnostic_fml=True,fabric_network_probe=True)
    support=consumer/SUPPORT;require(not support.exists(),'Fresh QSL support root required');support.mkdir(parents=True)
    copied=[]
    for row,raw,old_pin in payloads:
        require(hashlib.sha256(raw).hexdigest()==row['sha256'],'Source changed while copying')
        path=support/row['destination'];path.parent.mkdir(parents=True,exist_ok=True)
        with path.open('xb') as stream:stream.write(raw)
        copied.append(record(path))
        require(record(Path(old_pin['path']))==old_pin,'Original source changed during preparation')
    contract_out=support/'source-contract.json'
    with contract_out.open('xb') as stream:stream.write(source_contract.read_bytes())
    require(record(contract_out)['sha256']==source_contract_sha256,'Copied source contract changed')
    # Explicit consumer-local paths only. Dependencies remain at original lock
    # destinations and are restored later by the unchanged cold restore owner.
    layout=compile_layout()
    # Original lock bytes are copied as metadata, never changed or re-resolved.
    for name in COPIED_LOCKS:
        source_lock=repo/'work/network-pair-cold-glue'/name
        target=consumer/'work/network-pair-cold-glue'/name
        if target.exists():require(record(target)==dict(record(source_lock),path=str(target)),'Existing copied lock differs')
        else:
            target.parent.mkdir(parents=True,exist_ok=True)
            with target.open('xb') as stream:stream.write(source_lock.read_bytes())
        copied.append(record(target))
    write(support/'compile-layout.json',layout)
    modules={name:record(support/relative) for name,relative in MODULE_PATHS.items()}
    require(modules['continuation']['sha256']==CONTINUATION_SHA256 and
            modules['qualifier']['sha256']==QUALIFIER_SHA256 and
            modules['staging']['sha256']==STAGING_SHA256,'Frozen continuation/qualifier/staging changed')
    plan={'schema':'quilt-lifecycle-driver-plan-v1','status':'QSL_SOURCE_PREPARED_EXECUTION_UNTESTED',
          'repoRoot':str(repo),'consumerRoot':str(consumer),'seedPlan':record(original.driver_paths(consumer,True,True)['plan']),
          'sourceContract':record(contract_out),'sourceContractSha256':source_contract_sha256,
          'driverSource':record(Path(__file__)),'originalDriver':record(repo/'work/network-pair-cold-glue/driver.py'),
          'modules':modules,'sourceInputs':copied,'layout':record(support/'compile-layout.json'),
          'profile':options,'phases':['create','reopen'],'seedControlsExecuted':False,
          'downloadsStarted':False,'jvmStarted':False,'gameLaunched':False,**FLAGS}
    write(driver_paths(consumer)['plan'],plan)
    return plan


def verify_plan(repo,consumer,options,source_contract_sha256):
    plan=load_json(driver_paths(consumer)['plan'])
    require(plan['schema']=='quilt-lifecycle-driver-plan-v1' and plan['repoRoot']==str(repo)
            and plan['consumerRoot']==str(consumer) and plan['profile']==options
            and plan['phases']==['create','reopen'] and plan['seedControlsExecuted'] is False,
            'Explicit QSL plan mismatch; an original/Fabric plan alone is never sufficient')
    require(plan['sourceContractSha256']==source_contract_sha256,'Explicit reviewed QSL source contract mismatch')
    support=consumer/SUPPORT
    contract_path=support/'source-contract.json'
    require(plan['sourceContract']==record(contract_path),'Prepared contract must use exact owned destination')
    contract=check_contract(contract_path,source_contract_sha256)
    expected=[];destinations={}
    for row in contract['files']:
        current=record(support/row['destination'])
        require(current['bytes']==row['bytes'] and current['sha256']==row['sha256'],
                'Copied source differs from independently reviewed contract')
        expected.append(current);destinations[row['destination']]=current
    for name in COPIED_LOCKS:
        current=record(consumer/'work/network-pair-cold-glue'/name)
        require(current==dict(record(repo/'work/network-pair-cold-glue'/name),path=current['path']),
                'Copied original lock changed')
        expected.append(current)
    require(plan['sourceInputs']==expected,'Prepared source roster differs from exact contract and original locks')
    expected_modules={name:destinations[relative] for name,relative in MODULE_PATHS.items()}
    require(plan['modules']==expected_modules,'Prepared module roster or location differs from reviewed sources')
    require(expected_modules['continuation']['sha256']==CONTINUATION_SHA256
            and expected_modules['qualifier']['sha256']==QUALIFIER_SHA256
            and expected_modules['staging']['sha256']==STAGING_SHA256,'Frozen source identity changed')
    require(plan['driverSource']==record(Path(__file__))
            and destinations['driver/quilt_lifecycle_driver.py']['sha256']==plan['driverSource']['sha256'],
            'Running driver does not match independently reviewed source contract')
    require(plan['originalDriver']==record(repo/'work/network-pair-cold-glue/driver.py')
            and plan['originalDriver']['sha256']==ORIGINAL_DRIVER_SHA256,'Original driver changed')
    require(plan['seedPlan']==record(seed_driver.driver_paths(consumer,True,True)['plan']),
            'Prepared pristine seed plan belongs elsewhere')
    require(plan['layout']==record(support/'compile-layout.json')
            and load_json(support/'compile-layout.json')==compile_layout(),'Prepared compiler layout changed')
    require(all(type(plan.get(key)) is type(value) and plan[key]==value for key,value in FLAGS.items()),
            'Source plan cannot grant acceptance')
    seed=load_json(plan['seedPlan']['path'])
    require(seed['repoRoot']==str(repo) and seed['consumerRoot']==str(consumer)
            and seed.get('diagnostic_only') is True and seed.get('fabricNetworkProbe') is True,
            'Exact diagnostic Fabric source seed required')
    for row in [*seed['sourceCodeFiles'].values(),*seed['dataFiles'].values()]:
        require(compile_probe.record(Path(row['path']))==row,'Cold source/lock changed after preparation')
    require(seed.get('refreshedProfile')==refreshed_binding(consumer,options),'Prepared refreshed profile changed')
    return plan,seed


def modules(plan):
    values={}
    for name,row in plan['modules'].items():
        require(record(Path(row['path']))==row,'Reviewed integration source changed')
        import types
        module=types.ModuleType('quilt_lifecycle_'+name);module.__file__=row['path']
        raw=Path(row['path']).read_bytes();require(hashlib.sha256(raw).hexdigest()==row['sha256'],'Source changed before import')
        exec(compile(raw,row['path'],'exec'),module.__dict__)
        require(record(Path(row['path']))==row,'Source changed during import');values[name]=module
    return values


def build_seed(repo,consumer,seed,options,deadline,result):
    print('RESTORE_START: pinned official runtime, assets and toolchain bytes',flush=True)
    restore_with_deadline(runtime_restore.restore,consumer/'work/api1',deadline=deadline)
    restore_with_deadline(seed_driver.restore_additional,consumer,seed,deadline=deadline)
    for step in seed['runtime']['steps']:
        require(time.monotonic()<deadline,'Cold job deadline exceeded')
        execute_step(consumer,step,deadline,refreshed=True,diagnostic=True)
    runtime_restore.verify(consumer/'work/api1')
    import refreshed_candidate, fabric_probe_pipeline, diagnostic_fml_build, diagnostic_pair_assembly
    print('SOURCE_BUILD_START',flush=True)
    build_candidate.execute(consumer,deadline=deadline,profile=options['profile'])
    verified=refreshed_candidate.validate_full_build(consumer,options['profile'],options['build_proof'])
    result['refreshedCandidate']={'profileSha256':verified['profileSha256'],'sourceIdentity':verified['sourceIdentity'],
        'candidateIdentity':verified['candidateIdentity'],'candidateIdentityKind':verified['candidateIdentityKind'],
        'buildProof':refreshed_candidate.pin(consumer,options['build_proof'])}
    compile_probe.execute(consumer,deadline=deadline)
    fabric=fabric_probe_pipeline.build(consumer,deadline,execute_step)
    pair_assembly.assemble(repo,consumer,offline_identity_reference='Isolated localhost tests with virtual APILocal identity',
        eula_reference='Existing Minecraft EULA acceptance for isolated local tests',**options)
    manifest=diagnostic_fml_build.execute(repo,consumer,deadline=deadline,**options)
    diagnostic_pair_assembly.assemble(repo,consumer,manifest,ffapi_probe_bundle=fabric,**options)
    result['diagnosticManifest']=compile_probe.record(Path(manifest));result['fabricProbeBundle']=fabric
    return manifest,fabric


def compile_quilt(consumer,plan,component,deadline,deadline_epoch):
    pipeline=component['pipeline'];layout=Path(plan['layout']['path']);operation=consumer/'work/quilt-lifecycle-compile-run'
    args=pipeline.prepare(consumer,layout,operation,deadline_epoch)
    require(args==pipeline.compiler_command(consumer,layout,operation,deadline_epoch),'Prepared compiler command changed')
    step={'name':'compile-quilt-lifecycle','command':args,'cwd':str(consumer),
          'environment':{'PATH':'/usr/bin:/bin','LANG':'C.UTF-8','TZ':'UTC','PYTHONDONTWRITEBYTECODE':'1'},
          'timeoutSeconds':360}
    execute_step(consumer,step,deadline,refreshed=True,diagnostic=True)
    # execute_step returns only after its unchanged owned process/descendant
    # cleanup is complete; no compiler child is launched by the glue module.
    result=pipeline.finalize(consumer,layout,operation,deadline_epoch)
    require(result['status']=='PASS_PIPELINE_COMPILE_STAGING_NOT_RUNTIME_ACCEPTANCE','Missing compile semantic gate')
    review=load_json(consumer/result['validatedProvenance']['path'])
    verified=component['staging'].verify_source_binding(consumer,result['bundle'],validated_provenance=review)
    bundle=load_json(consumer/result['bundle']['path'])
    fixture={key:absolute(consumer,bundle[key]) for key in ('artifact','source_manifest','compile_receipt')}
    reviewed={key+'_sha256':review[key+'_sha256'] for key in fixture}
    return result,verified,fixture,reviewed


def original_assembly_sources(consumer,input_rows,staging):
    """Bind one exact original producer tool role, not a global filename search.

    The full refreshed build seals both original and logging-fix source trees.
    Their tool copies are byte-identical but only the original canonical path is
    executed by diagnostic_pair_assembly. Other sealed copies remain provenance;
    they cannot substitute for, or create ambiguity within, that exact role.
    """
    tools=Path(consumer)/ORIGINAL_ASSEMBLY_TOOLS
    def unique_source(name,sha):
        expected=tools/name
        matches=[row for row in input_rows if row['path']==str(expected)]
        require(len(matches)==1,'Exactly one frozen original-role '+name+' must be present in independently sealed source closure')
        require(matches[0]['sha256']==sha,'Frozen original-role '+name+' source hash changed')
        require(record(expected)==matches[0],'Frozen original assembler source changed')
        return matches[0]
    assembler=unique_source('assemble_installation.py',staging.ASSEMBLER_SHA256)
    validator=unique_source('validate_launch.py',staging.VALIDATOR_SHA256)
    require(Path(validator['path']).parent==Path(assembler['path']).parent,'Original validator must be adjacent to assembler')
    return assembler,validator


def source_materialization_inputs(consumer,source,assembly,proof_inputs,staging,*,host_graphics=()):
    """Extract local producer contracts, retaining host graphics in the source seal.

    host_graphics is the exact typed result of the reviewed qualifier, not an
    external-path allowlist. The runtime caller always uses its strict public
    classifier after the unchanged original static/live source-seal gates.
    """
    require(record(Path(source['spec']['path']))==source['spec'],'Pristine source spec changed')
    source_spec=load_json(source['spec']['path']);inputs={row['path']:row for row in source_spec['inputs']}
    require(len(inputs)==len(source_spec['inputs']),'Duplicate pristine source input')
    hosts={row['path']:row for row in host_graphics}
    require(len(hosts)==len(host_graphics),'Duplicate classified host graphics input')
    for path,row in hosts.items():
        require(not Path(path).is_relative_to(consumer) and inputs.get(path)==row,
                'Classified host graphics must be exact external source pins')
    for row in proof_inputs:
        require(inputs.get(row['path'])==row,'Pristine seed spec misses independently validated proof input: '+row['path'])
    inputs[source['spec']['path']]=source['spec']
    source_roles=assembly['groups']['unified']['roles'];source_specs={};derivative=None;diagnostic_manifest=None
    require(set(source_roles)=={'server','client'},'Exact pristine source roles required')
    for side,row in source_roles.items():
        require(inputs.get(row['path'])==row and record(Path(row['path']))==row,'Unsealed source role')
        role=load_json(row['path']);owner=role['assembly']
        require('baseAssembly' not in owner,'Already staged/wrapped role cannot be a pristine source seed')
        receipt_path=Path(owner['buildReceipt']);receipt_pin=record(receipt_path)
        require(inputs.get(str(receipt_path))==receipt_pin and owner['buildReceiptSha256']==receipt_pin['sha256'],
                'Pristine diagnostic owner receipt is not sealed')
        receipt=load_json(receipt_path)
        require(receipt.get('schema')=='diagnostic-configured-fml-v1' and receipt.get('diagnostic_only') is True
                and receipt.get('baseline_acceptance') is False,'Exact original diagnostic owner schema required')
        source_specs[side]=receipt['assemblySpec']
        for item in (receipt['assemblySpec'],receipt['unconfiguredDerivative'],receipt['diagnosticManifest']):
            require(inputs.get(item['path'])==item and record(Path(item['path']))==item,'Unsealed original diagnostic ancestry')
        if derivative is None:
            derivative=receipt['unconfiguredDerivative'];diagnostic_manifest=receipt['diagnosticManifest']
        require(derivative==receipt['unconfiguredDerivative'] and diagnostic_manifest==receipt['diagnosticManifest'],
                'Mixed diagnostic derivative or manifest owners')
        for item in role['files']:
            if item['path'] not in inputs:
                require(item['path']==str(Path(role['cwd'])/'options.txt'),'Unexpected unsealed source role input')
                inputs[item['path']]=item
            else:require(inputs[item['path']]==item,'Pristine role pin conflicts with source spec')
    assembler,validator=original_assembly_sources(consumer,source_spec['inputs'],staging)
    local_inputs=[row for path,row in inputs.items() if path not in hosts]
    require(all(Path(row['path']).is_relative_to(consumer) for row in local_inputs),
            'Unclassified external input in pristine materialization closure')
    return {'source_roles':source_roles,'source_specs':source_specs,'source_inputs':local_inputs,
            'assembler_pin':assembler,'validator_pin':validator,'derivative_pin':derivative,
            'diagnostic_manifest_pin':diagnostic_manifest}


def prepare_phases(repo,consumer,options,component,verified,manifest,fabric,graphics,deadline):
    import diagnostic_pair_assembly
    require(time.monotonic()<deadline,'Round expired before pristine seed seal')
    source=seal_pair.create(repo,consumer,'unified',graphics['readyPath'],
        'Pristine static source only for the isolated QSL lifecycle diagnostic; never execute this source control',
        diagnostic_manifest=manifest,ffapi_probe_bundle=fabric,**options)
    _,assembly,proof_inputs,_=diagnostic_pair_assembly.validate(repo,consumer,Path(manifest),ffapi_probe_bundle=fabric,**options)
    staging=component['staging'];sealer=component['sealer'];phases={}
    host_graphics=component['qualifier'].classify_graphics_inputs(consumer,load_json(source['spec']['path']),
        consumer/SUPPORT/'original/supervisor.py')
    inputs=source_materialization_inputs(consumer,source,assembly,proof_inputs,staging,host_graphics=host_graphics)
    (consumer/'work/quilt-lifecycle-seals').mkdir()
    for phase in ('create','reopen'):
        require(time.monotonic()<deadline,'Round expired before fresh phase materialization')
        manifest_pin,_=staging.materialize_unified_phase(consumer,verified,phase=phase,
            overlay_root=consumer/('work/quilt-lifecycle-'+phase),**inputs)
        phases[phase]=sealer.create_phase_seal(consumer,manifest_pin=manifest_pin,verified=verified,
            source_spec_pin=source['spec'],graphics_ready_pin=record(Path(graphics['readyPath'])),
            supervisor_pin=record(consumer/SUPPORT/'original/supervisor.py'),
            finalizer_pin=record(consumer/SUPPORT/'original/finalize_pair.py'),
            prepare_inputs_pin=record(consumer/SUPPORT/'original/prepare_inputs.py'),
            staging_pin=record(Path(staging.__file__)),output=consumer/('work/quilt-lifecycle-seals/'+phase+'.json'))
    return phases


def owner_sources(component,supervisor):
    _,sources=component['continuation'].source_identity(supervisor)
    require(sources['owner_source_sha256']==CONTINUATION_SHA256,'Frozen continuation source changed')
    return sources


def phase_command(phase,consumer,sealed,evidence,deadline,component,continuation_pin=None,sources=None):
    if phase=='create':
        return [sys.executable,sealed['supervisorForStaticValidation']['path'],'--spec',sealed['spec']['path'],
            '--sha256',sealed['spec']['sha256'],'--execute-reviewed-ci-pair','--destination',str(evidence),
            '--work-cutoff-monotonic',str(deadline)]
    require(phase=='reopen' and continuation_pin is not None and sources is not None,'Owned reopen continuation required')
    return [sys.executable,'-B',str(component['continuation'].__file__),'--root',str(consumer),
        '--spec',sealed['spec']['path'],'--spec-sha256',sealed['spec']['sha256'],
        '--continuation',continuation_pin['path'],'--continuation-sha256',continuation_pin['sha256'],
        '--supervisor',sealed['supervisorForStaticValidation']['path'],'--owner-source-sha256',sources['owner_source_sha256'],
        '--derivative-run-sha256',sources['derivative_run_sha256'],'--qualifier-sha256',QUALIFIER_SHA256,
        '--destination',str(evidence),'--work-cutoff-monotonic',str(deadline),'--execute-reviewed-quilt-reopen']
def execute(repo,consumer,*,profile,build_proof,source_contract_sha256,round_id,
            work_seconds=None,allow_runner_package=False):
    repo=Path(repo).resolve(strict=True);consumer=Path(consumer).resolve(strict=True)
    configure(repo)
    budget=work_budget(work_seconds if work_seconds is not None else round_deadline.MAX_WORK_SECONDS)
    # No rolling deadline, no fallback, and no future round invented by this lane.
    require(round_id is not None,'Execution requires the separately reviewed fixed --round-id')
    window=round_deadline.admit(round_id,budget)
    require(os.environ.get('GITHUB_ACTIONS')=='true' and os.environ.get('GITHUB_REPOSITORY')==REPO
            and os.environ.get('GITHUB_REF')=='refs/heads/'+BRANCH and os.environ.get('GITHUB_EVENT_NAME')=='push',
            'Execution requires the separately reviewed exact future pair branch; no alternative publication route')
    require(os.getuid()!=0,'Unprivileged standard runner required')
    options=profile_options(profile,build_proof)
    require(options,'QSL lifecycle requires the exact refreshed profile and build proof')
    plan,seed=verify_plan(repo,consumer,options,source_contract_sha256)
    component=modules(plan);paths=driver_paths(consumer)
    deadline=window.deadline;deadline_epoch=window.wall_stop
    watchdog=round_deadline.Watchdog(window)
    handle=None;active_pair=None;primary_error=None;previous={}
    result={'schema':'quilt-lifecycle-driver-result-v1','status':'INCOMPLETE','reports':{},
            'seedControlsExecuted':False,'phases':['create','reopen'],**FLAGS}
    result['roundDeadline']=window.receipt()
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
        if watchdog is not None:
            watchdog.start()
            require(window.remaining()>=round_deadline.MIN_WORK_SECONDS,
                    'Plan validation consumed useful-work allowance; stop before downloads or setup')
        require(time.monotonic()<deadline,'Round work deadline expired before setup')
        if allow_runner_package:
            runner_dependencies.ensure(seed['graphics'],consumer,deadline,allow_install=True)
        availability=graphics_runner.availability(seed['graphics']);write(paths['graphics'],availability)
        require(not availability['missingInputs'],'Required installed runner graphics unavailable before downloads: '+json.dumps(availability['missingInputs']))
        manifest,fabric=build_seed(repo,consumer,seed,options,deadline,result)
        compiled,verified,fixture,reviewed=compile_quilt(consumer,plan,component,deadline,deadline_epoch)
        result['quiltCompile']=compiled
        require(time.monotonic()<deadline,'Cold job deadline exceeded before graphics')
        # Keep stop signals deferred through collector creation and the return
        # handoff. The runner checks pending stops only while cleanup owns it.
        starting_graphics=True
        try:
            graphics=graphics_runner.execute(seed['graphics'],deadline=deadline,interrupt_check=check_stops,
                                             owner_cutoff=window.owner_cutoff() if window is not None else None)
            handle=graphics.get('handle')
        finally:
            starting_graphics=False
        check_stops()
        require(graphics['status']=='GRAPHICS_PREFLIGHT_READY','Graphics did not produce real readiness: '+str(graphics.get('missingInputs')))
        phases=prepare_phases(repo,consumer,options,component,verified,manifest,fabric,graphics,deadline)
        require(set(phases)=={'create','reopen'},'Both fresh QSL phases must be sealed before any game')
        result['presealedInputs']={phase:sealed['spec'] for phase,sealed in phases.items()}
        sources=owner_sources(component,Path(phases['create']['supervisorForStaticValidation']['path']))
        continuation_pin=None;runner=None
        for target in ('create','reopen'):
            check_stops()
            require(time.monotonic()<deadline,'Cold job deadline exceeded before pair')
            sealed=phases[target]
            # Recheck the complete compile/staging closure while this phase is
            # still pristine. Never rerun pristine staging after world transfer.
            require(component['staging'].verify_source_binding(consumer,verified['bundle_pin'],
                validated_provenance=verified['validated_provenance'])==verified,'Compile/staging closure changed')
            component['sealer'].validate_phase_seal(consumer,spec_pin=sealed['spec'],
                derivation_pin=sealed['derivation'],verified=verified)
            if target=='reopen':
                continuation_pin=component['continuation'].prepare(consumer,
                    create_spec_pin=phases['create']['spec'],create_report_pin=result['reports']['create'],
                    reopen_spec_pin=sealed['spec'],fixture=fixture,reviewed=reviewed,
                    qualifier_source_pin=plan['modules']['qualifier'],supervisor_path=Path(sealed['supervisorForStaticValidation']['path']),
                    reviewed_owner_sources=sources,reviewed_qualifier_sha256=QUALIFIER_SHA256,
                    output=consumer/'work/quilt-lifecycle-world-continuation')
                runner={'owner_source':plan['modules']['continuation'],
                    'derivative_source':record(Path(component['continuation'].__file__).with_name('owned_pair_run.py')),
                    'continuation_receipt':continuation_pin,'reviewed_owner_sources':sources}
                result['continuation']=continuation_pin
                # World transfer does not authorize skipping nested compiler log
                # evidence. This check does not require a world-free profile.
                component['sealer'].validate_compiler_observations(consumer,verified=verified,
                    staging_pin=plan['modules']['staging'])
                check_stops()
                require(time.monotonic()<deadline,'Round expired after owned world copy')
            evidence=paths['evidence']/target;evidence.parent.mkdir(exist_ok=True)
            args=phase_command(target,consumer,sealed,evidence,deadline,component,continuation_pin,sources)
            print('ACTUAL_QUILT_PHASE_START '+target,flush=True)
            # Defer stop signals across spawn/ownership assignment, so a signal
            # cannot strand a newly created child before finally can identify it.
            remaining=deadline-time.monotonic()
            require(remaining>0,'Cold job deadline expired before pair spawn')
            spawning_pair=True
            try:
                call=subprocess.Popen(args,cwd=consumer)
                active_pair={'process':call,'target':target}
            finally:
                spawning_pair=False
            if pending_stops:interrupt_driver(pending_stops[0],None)
            try:
                code=call.wait(timeout=min(PAIR_SECONDS,max(0,deadline-time.monotonic())))
            except subprocess.TimeoutExpired as error:
                raise RuntimeError('Pair time budget exhausted; owned supervisor cleanup required') from error
            active_pair=None  # wait reaped this owned supervisor before the next pair.
            report_path=evidence/'result.json'
            if report_path.exists():
                result['reports'][target]=compile_probe.record(report_path)
                print('ACTUAL_QUILT_PHASE_RECEIPT '+target+' '+report_path.read_text()[:256000],flush=True)
            for role in ('server','client'):
                log=evidence/(role+'.log')
                if log.exists():print('ACTUAL_QUILT_PHASE_LOG '+target+' '+role+'\n'+log.read_text(errors='replace')[-32000:],flush=True)
            require(code==0,'Actual QSL phase failed: '+target)
            require(target in result['reports'],'Missing actual phase terminal report')
            if target=='create':
                qualified=component['qualifier'].validate_phase(consumer,phase='create',spec_pin=sealed['spec'],
                    report_pin=result['reports'][target],fixture=fixture,reviewed=reviewed,
                    supervisor_path=Path(sealed['supervisorForStaticValidation']['path']))
                checkpoint=consumer/'quilt-create-qualification.json';write(checkpoint,qualified)
                result['createQualification']=record(checkpoint)
        require(runner is not None,'Missing independently owned reopen lineage')
        component['sealer'].validate_compiler_observations(consumer,verified=verified,
            staging_pin=plan['modules']['staging'])
        qualified=component['qualifier'].validate_pair(consumer,create_spec_pin=phases['create']['spec'],
            create_report_pin=result['reports']['create'],reopen_spec_pin=phases['reopen']['spec'],
            reopen_report_pin=result['reports']['reopen'],fixture=fixture,reviewed=reviewed,
            supervisor_path=Path(phases['create']['supervisorForStaticValidation']['path']),runner=runner)
        require(qualified['status']=='QSL_LIFECYCLE_PERSISTENCE_EVIDENCE_VALIDATED'
                and qualified['synthetic_fixture'] is False,'Missing real two-phase QSL lifecycle qualification')
        checkpoint=consumer/'quilt-pair-qualification.json';write(checkpoint,qualified)
        result.update(status='DIAGNOSTIC_QSL_LIFECYCLE_PERSISTENCE_QUALIFIED',
                      lifecycleQualification=record(checkpoint),qslLifecyclePersistenceQualified=True)
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
            if watchdog is not None:
                try:watchdog.close()
                except BaseException as error:
                    errors.append({'component':'round-watchdog','failure':type(error).__name__+': '+str(error)})
                result['roundDeadline']['stopReason']=watchdog.reason
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
            result.update(FLAGS)
            if primary_error is not None or errors:result['qslLifecyclePersistenceQualified']=False
            write(paths['result'],result)
            print(json.dumps(result,sort_keys=True),flush=True)
            summary=os.environ.get('GITHUB_STEP_SUMMARY')
            if summary:
                try:
                    with open(summary,'a') as stream:stream.write('Isolated QSL lifecycle derivative only: '+result['status']+'\n\nOriginal loader/game, QSL networking, GUI and full-API acceptance remain false.\n')
                except OSError as error:
                    print('STEP_SUMMARY_FAILED '+str(error),file=sys.stderr,flush=True)
        finally:
            # Never expose a restored default handler to an unjoined stop thread.
            if watchdog is None or not watchdog.thread.is_alive():
                for number,handler in previous.items():signal.signal(number,handler)
    if result.get('cleanupErrors'):
        raise RuntimeError('Owned process cleanup failed; see '+str(paths['result']))
    return result


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action',choices=['prepare','run'])
    parser.add_argument('--repo-root',type=Path,required=True);parser.add_argument('--consumer',type=Path,required=True)
    parser.add_argument('--profile',required=True);parser.add_argument('--build-proof',required=True)
    parser.add_argument('--source-contract-sha256',required=True)
    parser.add_argument('--support-source',type=Path);parser.add_argument('--source-contract',type=Path)
    parser.add_argument('--round-id');parser.add_argument('--work-seconds',type=int)
    parser.add_argument('--install-reviewed-runner-closure',action='store_true')
    parser.add_argument('--execute-reviewed-quilt-lifecycle',action='store_true')
    args=parser.parse_args();work_budget(args.work_seconds)
    if args.action=='prepare':
        require(args.support_source is not None and args.source_contract is not None,'Explicit source contract and source root required')
        result=prepare(args.repo_root,args.consumer,profile=args.profile,build_proof=args.build_proof,
            support_source=args.support_source,source_contract=args.source_contract,source_contract_sha256=args.source_contract_sha256)
    else:
        require(args.execute_reviewed_quilt_lifecycle and args.round_id is not None,
                'Explicit QSL lifecycle opt-in and fixed reviewed round required')
        result=execute(args.repo_root,args.consumer,profile=args.profile,build_proof=args.build_proof,
            source_contract_sha256=args.source_contract_sha256,round_id=args.round_id,work_seconds=args.work_seconds,
            allow_runner_package=args.install_reviewed_runner_closure)
    print(json.dumps({'status':result['status'],'gameAcceptance':False,'baselineAcceptance':False,'fullApiCompatibility':False}))


if __name__=='__main__':main()
